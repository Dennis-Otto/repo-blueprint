"""Tests of the template: every kind of project renders completely and consistently."""

from __future__ import annotations

import configparser
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import tomllib
import warnings
from pathlib import Path

import pathspec
import pytest
from copier import run_copy
from shell import BASH

ROOT = Path(__file__).parents[1]
KINDS = [
    "home-assistant",
    "nextcloud-app",
    "github-action",
    "python-package",
    "node-package",
    "container",
    "generic",
]
# The delimiters of the template; no rendered file may hold them.
LEFTOVER = re.compile(r"\{=|=\}|\[%|%\]")
GUARD = "    # Not in the blueprint itself; generated repositories don't have this line.\n    if: github.repository != 'Dennis-Otto/repo-blueprint'\n"
PINNED = re.compile(
    r"uses: (?:\./|docker://[^@\s]+@sha256:[0-9a-f]{64}|[\w.-]+/[\w./-]+@[0-9a-f]{40})"
)
# The settings tool, which every repository gets in .github/: the script that starts
# it and every file of its package. The mutation tests run in a copy of the repository,
# where mutmut keeps what it knows of each module next to it, as cli.py.meta and
# cli.py.spans; those are no part of the tool.
TOOL = sorted(
    [
        "blueprint.py",
        *(
            f"blueprint/{path.name}"
            for path in (ROOT / "blueprint").iterdir()
            if path.is_file() and path.suffix not in (".meta", ".spans")
        ),
    ]
)


def render(destination: Path, **data: str | bool) -> Path:
    with warnings.catch_warnings():
        # Uncommitted changes of the blueprint render too, with a warning.
        warnings.simplefilter("ignore")
        run_copy(
            str(ROOT), destination, data=data, defaults=True, vcs_ref="HEAD", quiet=True
        )
    return destination


@pytest.fixture(scope="module")
def projects(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    return {
        kind: render(
            tmp_path_factory.mktemp(kind),
            project_name="Demo Project",
            description=f'A {kind} of the tests, with "quotes" and Ümlauts.',
            project_type=kind,
        )
        for kind in KINDS
    }


def text_files(project: Path) -> list[Path]:
    files = []
    for path in sorted(project.rglob("*")):
        if path.is_file() and ".git" not in path.parts and path.suffix != ".png":
            files.append(path)
    return files


def workflows(project: Path) -> dict[str, str]:
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in (project / ".github/workflows").glob("*.yml")
    }


def job_of(workflow: str, name: str) -> str:
    """The text of a job of a workflow, up to the next job."""
    start = workflow.index(f"\n  {name}:\n")
    end = re.compile(r"\n\n  [\w-]+:\n").search(workflow, start + 1)
    return workflow[start : end.start() if end else len(workflow)]


def condition_of(job: str) -> str:
    """The condition of a job, on one line."""
    found = re.search(r"^    if: (>-\n(?:      .+\n)+|.+)", job + "\n", re.M)
    assert found, job
    return " ".join(found[1].removeprefix(">-").split())


def triggers(workflow: str) -> dict[str, list[str]]:
    """The events that start a workflow, each with the lines of its settings, without
    their comments."""
    events: dict[str, list[str]] = {}
    settings: list[str] = []
    for line in workflow.split("\non:\n", 1)[1].splitlines():
        if line and not line.startswith(" "):
            break
        if re.match(r"  [\w-]+:", line):
            settings = events.setdefault(line.strip().split(":")[0], [])
        elif line.strip() and not line.lstrip().startswith("#"):
            settings.append(line)
    return events


def paths_of(workflow: str, event: str) -> list[str]:
    """The path filters of an event that starts a workflow, in their order."""
    settings = triggers(workflow)[event]
    patterns = []
    for line in settings[settings.index("    paths:") + 1 :]:
        if not line.startswith("      - "):
            break
        patterns.append(line.removeprefix("      - ").strip('"'))
    return patterns


def runs_for(patterns: list[str], changed: list[str]) -> bool:
    """Whether a change of these files starts a workflow with these path filters, as
    GitHub matches them: in their order, where a later ! takes a path out again."""

    def expression(pattern: str) -> str:
        parts = re.split(r"(\*\*/|\*\*|\*)", pattern)
        wildcards = {"**/": "(?:.*/)?", "**": ".*", "*": "[^/]*"}
        return "".join(wildcards.get(part, re.escape(part)) for part in parts)

    def included(path: str) -> bool:
        result = False
        for pattern in patterns:
            negated = pattern.startswith("!")
            if re.fullmatch(expression(pattern.removeprefix("!")), path):
                result = not negated
        return result

    return any(included(path) for path in changed)


def files_of(root: Path) -> list[str]:
    """The files of a repository, by their paths from its root."""
    if root == ROOT:
        listed = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            capture_output=True,
            check=True,
            text=True,
        ).stdout
        return [name for name in listed.split("\0") if name]
    return [
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(root).parts
    ]


def script_of(workflow: str, step: str) -> str:
    """The script of a step of a workflow, as the runner hands it to bash."""
    start = workflow.index(f"      - name: {step}\n")
    run = workflow.index("        run: |\n", start) + len("        run: |\n")
    lines = []
    for line in workflow[run:].splitlines(keepends=True):
        if line.strip() and not line.startswith("          "):
            break
        lines.append(line)
    return textwrap.dedent("".join(lines))


@pytest.mark.parametrize("kind", KINDS)
def test_no_template_syntax_is_left(projects: dict[str, Path], kind: str) -> None:
    for path in text_files(projects[kind]):
        text = path.read_text(encoding="utf-8")
        assert not LEFTOVER.search(text), path
        assert text == "" or text.endswith("\n"), path
        assert "\r" not in text, path
        assert not LEFTOVER.search(str(path.relative_to(projects[kind]))), path


@pytest.mark.parametrize("kind", KINDS)
def test_the_workflows_are_the_blueprints_own(
    projects: dict[str, Path], kind: str
) -> None:
    sources = ROOT / ".github/workflows"
    for name, text in workflows(projects[kind]).items():
        source_name = name
        if name == "ci.yml":
            flavor = re.search(r"^name: CI \((.+)\)$", text, re.M)
            assert flavor, "ci.yml names its flavor"
            source_name = f"ci-{flavor.group(1)}.yml"
        source = (sources / source_name).read_text(encoding="utf-8").replace(GUARD, "")
        if name == "fuzz.yml":
            source = source.replace(
                "stacks/fuzz/requirements.txt", "requirements-fuzz.txt"
            )
        if name == "docs.yml":
            source = source.replace(
                "stacks/docs/requirements-docs.txt", ".github/docs-requirements.txt"
            )
        if name == "codeql.yml":
            source = re.sub(
                r"        # The languages of this repository.*\n        language: \[.*\]\n",
                "",
                source,
            )
            text = re.sub(r"        language: \[.*\]\n", "", text)
        if name == "after-checks.yml":
            # The workflows it watches; the bots after the checks test them.
            watched = r"    # The (?:workflows of the )?checks of this repository.*\n(?:    # .*\n)*    workflows: \[.*\]\n"
            source = re.sub(watched, "", source)
            text = re.sub(watched, "", text)
        assert text == source, name


@pytest.mark.parametrize("kind", KINDS)
def test_every_action_is_pinned_to_a_commit(
    projects: dict[str, Path], kind: str
) -> None:
    for name, text in workflows(projects[kind]).items():
        for line in re.findall(r"uses: \S+", text):
            assert PINNED.match(line), f"{name}: {line}"


def test_no_workflow_pins_an_action_to_a_branch() -> None:
    # zizmor reports a commit pin whose comment names no version (ref-version-mismatch)
    # as soon as the branch in the comment moves on, and the Findings workflow fails
    # until the pin catches up. A tool that follows its branch on purpose runs as an
    # image. Every workflow of a new repository is one of these.
    for path in sorted((ROOT / ".github/workflows").glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        for action, comment in re.findall(r"uses: (\S+@[0-9a-f]{40})( # \S+)?", text):
            # As Renovate tells a version from a branch: v1, 1.2.3.
            assert re.match(r" # v?\d", comment), f"{path.name}: {action}{comment}"


@pytest.mark.parametrize("project", ["blueprint", *KINDS])
def test_the_required_checks_exist(projects: dict[str, Path], project: str) -> None:
    root = ROOT if project == "blueprint" else projects[project]
    settings = tomllib.loads(
        (root / ".github/repository.toml").read_text(encoding="utf-8")
    )
    names = set()
    for text in workflows(root).values():
        names.update(re.findall(r"^    name: (.+)$", text, re.M))
    for check in settings["branch"]["required_checks"]:
        assert check in names, check


@pytest.mark.parametrize("kind", KINDS)
def test_the_versions_agree(projects: dict[str, Path], kind: str) -> None:
    project = projects[kind]
    assert json.loads(
        (project / ".release-please-manifest.json").read_text(encoding="utf-8")
    ) == {".": "0.0.0"}
    config = json.loads(
        (project / "release-please-config.json").read_text(encoding="utf-8")
    )["packages"]["."]
    for extra in config.get("extra-files", []):
        assert "0.0.0" in (project / extra["path"]).read_text(encoding="utf-8"), extra[
            "path"
        ]
    if config["release-type"] == "simple":
        assert (project / "version.txt").read_text(encoding="utf-8") == "0.0.0\n"


@pytest.mark.parametrize("kind", KINDS)
def test_dependabot_watches_existing_folders(
    projects: dict[str, Path], kind: str
) -> None:
    project = projects[kind]
    text = (project / ".github/dependabot.yml").read_text(encoding="utf-8")
    for directory in re.findall(r"directory: (\S+)", text):
        assert (project / directory.lstrip("/")).is_dir(), directory


@pytest.mark.parametrize("kind", KINDS)
def test_every_area_of_the_forms_has_a_label(
    projects: dict[str, Path], kind: str
) -> None:
    project = projects[kind]
    labels = tomllib.loads(
        (project / ".github/labels.toml").read_text(encoding="utf-8")
    )["label"]
    mapped = {option for label in labels for option in label.get("form_options", [])}
    form = (project / ".github/ISSUE_TEMPLATE/bug_report.yml").read_text(
        encoding="utf-8"
    )
    area = form.split("label: Area", 1)[1].split("validations:", 1)[0]
    for option in re.findall(r"^        - (.+)$", area, re.M):
        assert option in mapped or option == "Other", option


def test_someone_sets_every_label(projects: dict[str, Path]) -> None:
    for project in (ROOT, *projects.values()):
        text = (project / ".github/labels.toml").read_text(encoding="utf-8")
        setters = set(re.findall(r"^#   (\w+) ", text, re.MULTILINE))
        labels = tomllib.loads(text)["label"]
        assert {label["group"] for label in labels} <= setters, project
        # Dependabot updates one ecosystem and so sets no label of an ecosystem, only
        # dependencies; Renovate sets none.
        assert "dependencies" in {label["name"] for label in labels}, project
        assert "dependabot" not in setters, project


def test_the_composer_lock_belongs_to_the_composer_json(
    projects: dict[str, Path],
) -> None:
    project = projects["nextcloud-app"]
    manifest = json.loads((project / "composer.json").read_text(encoding="utf-8"))
    lock = json.loads((project / "composer.lock").read_text(encoding="utf-8"))
    keys = [
        "name",
        "version",
        "require",
        "require-dev",
        "conflict",
        "replace",
        "provide",
        "minimum-stability",
        "prefer-stable",
        "repositories",
        "extra",
    ]
    relevant = {key: manifest[key] for key in keys if key in manifest}
    relevant["config"] = {"platform": manifest["config"]["platform"]}
    encoded = json.dumps(dict(sorted(relevant.items())), separators=(",", ":")).replace(
        "/", "\\/"
    )

    assert manifest["name"] == "dennis-otto/demo-project"
    assert manifest["autoload"]["psr-4"] == {"OCA\\DemoProject\\": "lib/"}
    assert (
        lock["content-hash"]
        == hashlib.md5(encoded.encode(), usedforsecurity=False).hexdigest()
    )


def test_the_package_lock_belongs_to_the_package_json(
    projects: dict[str, Path],
) -> None:
    project = projects["node-package"]
    manifest = json.loads((project / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((project / "package-lock.json").read_text(encoding="utf-8"))
    root = lock["packages"][""]

    assert lock["name"] == root["name"] == manifest["name"] == "demo-project"
    assert root["devDependencies"] == manifest["devDependencies"]
    assert root["engines"] == manifest["engines"]
    assert root["license"] == manifest["license"]


@pytest.mark.parametrize(
    ("license_id", "first_line", "holder"),
    [
        ("MIT", "MIT License", True),
        ("MIT-0", "MIT No Attribution", True),
        ("BSD-3-Clause", "Copyright (c) ", True),
        ("Apache-2.0", "Apache License", False),
        ("GPL-3.0-or-later", "GNU GENERAL PUBLIC LICENSE", False),
        ("AGPL-3.0-or-later", "GNU AFFERO GENERAL PUBLIC LICENSE", False),
    ],
)
def test_the_license(
    tmp_path: Path, license_id: str, first_line: str, holder: bool
) -> None:
    project = render(
        tmp_path,
        project_name="Demo",
        description="A demo.",
        project_type="generic",
        license=license_id,
    )
    text = (project / "LICENSE").read_text(encoding="utf-8")
    source = (ROOT / "LICENSES" / f"{license_id}.txt").read_text(encoding="utf-8")

    assert first_line in text.split("\n", 1)[0]
    # One line break at the end, also where the SPDX text has a blank line there.
    assert text.endswith("\n")
    assert not text.endswith("\n\n")
    assert (project / "LICENSES" / f"{license_id}.txt").read_text(
        encoding="utf-8"
    ) == source
    assert f'SPDX-License-Identifier = "{license_id}"' in (
        project / "REUSE.toml"
    ).read_text(encoding="utf-8")
    if holder:
        assert "Copyright" in text
        assert "Dennis Otto" in text
        assert not re.search(
            r"<(year|owner|YEAR|COPYRIGHT HOLDER)>|\[(year|fullname)\]", text
        )
    else:
        # Long licenses stay verbatim, appendix included.
        assert text == source.rstrip("\n") + "\n"


def test_a_project_without_a_sponsor(tmp_path: Path) -> None:
    project = render(
        tmp_path,
        project_name="Demo",
        description="A demo.",
        project_type="generic",
        sponsor="",
    )

    assert not (project / ".github/FUNDING.yml").exists()
    assert "sponsor" not in (project / "README.md").read_text(encoding="utf-8").lower()


def test_the_blueprint_follows_its_own_template(tmp_path: Path) -> None:
    project = render(
        tmp_path,
        project_name="Repo Blueprint",
        project_slug="repo-blueprint",
        description="A Copier template for GitHub repositories, with tests, releases, security checks and bots built in, for seven kinds of projects.",
        project_type="github-action",
        python_package="blueprint",
        license="MIT-0",
        successor=True,
        homepage="https://dennis-otto.github.io/repo-blueprint/",
    )
    for name in (
        ".editorconfig",
        ".gitattributes",
        ".gitignore",
        ".python-version",
        "CODE_OF_CONDUCT.md",
        "GOVERNANCE.md",
        "LICENSE",
        "SECURITY.md",
        "SUPPORT.md",
        "release-please-config.json",
        "scripts/check.sh",
        ".github/FUNDING.yml",
        ".github/findings.toml",
        ".github/pull_request_template.md",
        ".github/ISSUE_TEMPLATE/config.yml",
        ".github/ISSUE_TEMPLATE/feature_request.yml",
        ".github/DISCUSSION_TEMPLATE/q-a.yml",
        ".github/DISCUSSION_TEMPLATE/ideas.yml",
        ".github/social-preview/Dockerfile",
        ".github/actionlint.yaml",
        ".github/egress-firewall.yaml",
        ".github/markdownlint.jsonc",
        ".github/prose/cspell.json",
        ".github/prose/package.json",
        ".github/prose/package-lock.json",
        ".github/cspell-words.txt",
        ".vale.ini",
        ".github/sign-tag.sh",
        ".github/renovate-blueprint.json5",
        ".github/mkdocs-blueprint.yml",
        ".github/mkdocs_blueprint.py",
        ".markdownlint-cli2.jsonc",
        ".markdownlint.jsonc",
        ".devcontainer/devcontainer.json",
        ".devcontainer/devcontainer-lock.json",
        ".devcontainer/Dockerfile",
        ".devcontainer/setup.sh",
    ):
        own = (ROOT / name).read_text(encoding="utf-8")
        if name == ".devcontainer/setup.sh":
            # The blueprint keeps the tools of the website in stacks/docs/, from where
            # every repository gets them as .github/docs-requirements.txt.
            own = own.replace(
                "stacks/docs/requirements-docs.txt", ".github/docs-requirements.txt"
            )
        assert own == (project / name).read_text(encoding="utf-8"), name


@pytest.mark.parametrize("kind", ["python-package", "github-action"])
def test_python_projects_are_fuzzed(projects: dict[str, Path], kind: str) -> None:
    project = projects[kind]

    assert (project / "fuzz/fuzz_demo_project.py").read_text(encoding="utf-8").count(
        "import atheris"
    ) == 1
    assert "atheris==" in (project / "requirements-fuzz.txt").read_text(
        encoding="utf-8"
    )
    assert "FuzzingID" not in (project / ".github/findings.toml").read_text(
        encoding="utf-8"
    )


@pytest.mark.parametrize("kind", KINDS)
def test_every_repository_gets_the_settings_tool(
    projects: dict[str, Path], kind: str
) -> None:
    github = projects[kind] / ".github"
    copies = sorted(
        path.relative_to(github).as_posix()
        for path in [github / "blueprint.py", *(github / "blueprint").iterdir()]
        if path.is_file()
    )

    assert copies == TOOL
    for name in TOOL:
        copy = (github / name).read_text(encoding="utf-8")
        assert copy == (ROOT / name).read_text(encoding="utf-8"), name


# In the copy of the mutation tests, the tool is the code with the mutants, which the
# variables of mutmut switch in the process that this test starts.
@pytest.mark.mutation_unsafe
@pytest.mark.parametrize("kind", KINDS)
def test_the_settings_tool_runs_in_every_repository(
    projects: dict[str, Path], kind: str
) -> None:
    # As the workflows run it: the script imports the package next to it.
    result = subprocess.run(
        [sys.executable, ".github/blueprint.py", "--help"],
        cwd=projects[kind],
        capture_output=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("usage: blueprint.py")
    assert "The settings of a repository as code" in result.stdout
    # Like the single file it was, the tool leaves no __pycache__ in the repository.
    assert not (projects[kind] / ".github/blueprint/__pycache__").exists()


def test_the_settings_tool_keeps_the_ruff_settings_of_the_blueprint() -> None:
    # Ruff uses the closest configuration of each file and no other: in a repository,
    # .github/blueprint/ keeps these settings, not those of the project.
    own = tomllib.loads((ROOT / "blueprint/ruff.toml").read_text(encoding="utf-8"))
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert own.pop("src") == [".."]
    assert own == pyproject["tool"]["ruff"]


def test_the_readme_of_an_integration_works_in_hacs(projects: dict[str, Path]) -> None:
    # HACS shows the README outside GitHub, where relative links lead nowhere.
    readme = (projects["home-assistant"] / "README.md").read_text(encoding="utf-8")

    for target in re.findall(r"\]\(([^)\s]+)\)", readme):
        assert target.startswith(("https://", "#")), target


def test_an_integration_is_validated_by_the_current_images_of_hacs_and_hassfest(
    projects: dict[str, Path],
) -> None:
    ci = (projects["home-assistant"] / ".github/workflows/ci.yml").read_text(
        encoding="utf-8"
    )
    # Their moving images, as their actions run them, but without the actions: a pin
    # to a commit of their branches falls behind with every commit to them.
    assert "uses: hacs/action" not in ci
    assert "uses: home-assistant/actions" not in ci
    hacs = job_of(ci, "hacs")
    assert hacs.endswith("\n            ghcr.io/hacs/action:main")
    # HACS reads the repository through the API, so the job checks nothing out.
    assert "actions/checkout" not in hacs
    # hassfest checks the checkout, read-only, exactly as the Variants workflow does.
    command = (
        'docker run --rm --volume "$PWD:/github/workspace:ro"'
        " ghcr.io/home-assistant/hassfest:latest\n"
    )
    assert command in job_of(ci, "hassfest")
    variants = (ROOT / ".github/workflows/variants.yml").read_text(encoding="utf-8")
    assert command.replace("$PWD", "$PWD/$PROJECT") in variants


def run_the_step_with_docker(
    tmp_path: Path, job: str, environment: dict[str, str]
) -> tuple[str, list[str]]:
    # The step runs in the folder workspace/, as in the checkout of a runner.
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    script = textwrap.dedent(
        job[job.index("        run: |\n") + len("        run: |\n") :]
    )
    (workspace / "step.sh").write_text(script, encoding="utf-8", newline="\n")
    # docker writes down what the container would get: its variables, its mounts,
    # with the folder of the step as $PWD, and its image.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(
        """#!/usr/bin/env bash
[[ "$1" == run ]] || exit 1
shift
while (($#)); do
  case "$1" in
    --rm) ;;
    --env) shift; if [[ "$1" == *=* ]]; then echo "env $1"; else echo "env $1=${!1}"; fi ;;
    --volume) shift; echo "volume ${1/#"$PWD"/\\$PWD}" ;;
    *) echo "image $1" ;;
  esac
  shift
done >> "$CALLS"
""",
        encoding="utf-8",
        newline="\n",
    )
    docker.chmod(0o755)
    calls = tmp_path / "calls"
    calls.touch()
    # As GitHub runs a step: bash -e.
    assert BASH
    result = subprocess.run(
        [BASH, "-e", "step.sh"],
        cwd=workspace,
        env={
            **os.environ,
            **environment,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "CALLS": str(calls),
        },
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout, calls.read_text(encoding="utf-8").splitlines()


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
def test_hacs_gets_the_inputs_of_its_action(
    projects: dict[str, Path], tmp_path: Path
) -> None:
    ci = (projects["home-assistant"] / ".github/workflows/ci.yml").read_text(
        encoding="utf-8"
    )
    hacs = job_of(ci, "hacs")
    # The inputs of the action reach its image as INPUT_ variables, as GitHub passes
    # them, and the event as a file, from which it reads the branch to validate.
    inputs = {
        name: value.strip('"').replace("${{ github.token }}", "the token")
        for name, value in re.findall(r"^          (INPUT_\w+): (.+)$", hacs, re.M)
    }
    event = (tmp_path / "event.json").as_posix()

    _, calls = run_the_step_with_docker(
        tmp_path,
        hacs,
        {**inputs, "GITHUB_REPOSITORY": "o/r", "GITHUB_EVENT_PATH": event},
    )

    assert calls == [
        "env INPUT_CATEGORY=integration",
        "env INPUT_COMMENT=false",
        "env INPUT_GITHUB_TOKEN=the token",
        "env GITHUB_REPOSITORY=o/r",
        "env GITHUB_EVENT_PATH=/github/workflow/event.json",
        f"volume {event}:/github/workflow/event.json:ro",
        "image ghcr.io/hacs/action:main",
    ]


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
def test_hassfest_shows_its_errors_as_annotations(
    projects: dict[str, Path], tmp_path: Path
) -> None:
    ci = (projects["home-assistant"] / ".github/workflows/ci.yml").read_text(
        encoding="utf-8"
    )
    runner_temp = tmp_path / "runner"
    runner_temp.mkdir()

    output, calls = run_the_step_with_docker(
        tmp_path, job_of(ci, "hassfest"), {"RUNNER_TEMP": runner_temp.as_posix()}
    )

    assert calls == [
        "volume $PWD:/github/workspace:ro",
        "image ghcr.io/home-assistant/hassfest:latest",
    ]
    # The problem matcher of its action turns each error and warning into one.
    assert f"::add-matcher::{runner_temp.as_posix()}/hassfest.json\n" in output
    matcher = json.loads((runner_temp / "hassfest.json").read_text(encoding="utf-8"))
    pattern = matcher["problemMatcher"][0]["pattern"][0]
    error = re.match(
        pattern["regexp"],
        "* [ERROR] [MANIFEST] Invalid manifest: value must be one of"
        " ['assumed_state', 'calculated'] at 'iot_class'. Got 'nonsense'",
    )
    assert error
    assert error[pattern["severity"]] == "ERROR"
    assert error[pattern["message"]].startswith("[MANIFEST] Invalid manifest: ")
    assert not re.match(pattern["regexp"], "Integrations: 1")


@pytest.mark.parametrize("kind", KINDS)
def test_python_projects_run_property_tests_every_night(
    projects: dict[str, Path], kind: str
) -> None:
    project = projects[kind]
    workflow = project / ".github/workflows/properties.yml"

    if kind in ("home-assistant", "python-package", "github-action"):
        assert workflow.exists()
        assert 'settings.register_profile("local"' in (
            project / "tests/conftest.py"
        ).read_text(encoding="utf-8")
    else:
        assert not workflow.exists()


def test_several_copyright_holders(tmp_path: Path) -> None:
    project = render(
        tmp_path,
        project_name="Demo",
        description="A demo.",
        project_type="generic",
        copyright="2024 Example contributors; 2026 Dennis Otto",
    )

    lines = (project / "LICENSE").read_text(encoding="utf-8").splitlines()
    assert lines[2:4] == [
        "Copyright (c) 2024 Example contributors",
        "Copyright (c) 2026 Dennis Otto",
    ]
    reuse = tomllib.loads((project / "REUSE.toml").read_text(encoding="utf-8"))
    assert reuse["annotations"][0]["SPDX-FileCopyrightText"] == [
        "2024 Example contributors",
        "2026 Dennis Otto",
        "Contributors to Demo",
    ]


@pytest.mark.parametrize("kind", KINDS)
def test_every_project_has_a_dev_container(
    projects: dict[str, Path], kind: str
) -> None:
    project = projects[kind]
    config = json.loads(
        (project / ".devcontainer/devcontainer.json").read_text(encoding="utf-8")
    )
    dockerfile = (project / ".devcontainer/Dockerfile").read_text(encoding="utf-8")
    setup = (project / ".devcontainer/setup.sh").read_text(encoding="utf-8")

    assert config["postCreateCommand"] == "bash .devcontainer/setup.sh"
    # Every Feature is locked; Docker for all, Node for the projects with a frontend.
    lock = json.loads(
        (project / ".devcontainer/devcontainer-lock.json").read_text(encoding="utf-8")
    )
    assert set(config["features"]) == set(lock["features"])
    node = "ghcr.io/devcontainers/features/node:2" in config["features"]
    assert node == (kind in ("home-assistant", "nextcloud-app"))
    if node:
        # The Features that Dependabot keeps current in the blueprint.
        watched = json.loads(
            (ROOT / "stacks/devcontainer/.devcontainer/devcontainer.json").read_text(
                encoding="utf-8"
            )
        )
        assert watched["features"] == config["features"]
    assert re.search(
        r"^FROM mcr\.microsoft\.com/devcontainers/\S+@sha256:[0-9a-f]{64}$",
        dockerfile,
        re.M,
    )
    assert "git config core.hooksPath .githooks" in setup
    # Where Git ignores the modes of the files, the hook gets its mode on disk.
    assert "chmod +x .githooks/*" in setup
    requirements = {
        "home-assistant": "requirements-test.txt",
        "python-package": "requirements-dev.txt",
        "github-action": "requirements-dev.txt",
    }
    if kind in requirements:
        assert f"-r {requirements[kind]}" in setup
        assert (project / requirements[kind]).exists()
        assert "charliermarsh.ruff" in config["customizations"]["vscode"]["extensions"]


def renders_a_script(path: Path) -> bool:
    """Whether the file of the blueprint is, or renders as, a script with a shebang:
    a file of the template that only includes another renders as that one."""
    text = path.read_bytes()
    include = re.fullmatch(rb'\[% include "([^"]+)" -%\]\n?', text)
    if include:
        text = (ROOT / include.group(1).decode()).read_bytes()
    return text.startswith(b"#!")


# It asks Git for the modes of the files, which the copy of the mutation tests has none
# of.
@pytest.mark.mutation_unsafe
def test_every_script_of_the_blueprint_is_executable_in_git() -> None:
    # Copier gives a file of a new repository the mode that Git has for it in the
    # template, on Windows too, and the blueprint bot brings a new mode to an existing
    # repository. Git runs a hook only when it is executable: the pre-push hook was a
    # plain file, which Git on Linux, macOS, in the dev container and in Codespaces
    # skipped, so that a push went through with failing checks.
    listing = subprocess.run(
        ["git", "ls-files", "--stage", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout.decode()
    modes = {}
    for entry in listing.split("\0")[:-1]:
        meta, path = entry.split("\t", 1)
        mode = meta.split(" ", 1)[0]
        # Files, not links or submodules.
        if mode in ("100644", "100755"):
            modes[path] = mode
    scripts = {path for path in modes if renders_a_script(ROOT / path)}
    executable = {path for path, mode in modes.items() if mode == "100755"}

    assert executable == scripts
    assert {
        ".githooks/pre-push",
        "template/.githooks/pre-push.jinja",
        "template/.github/sign-tag.sh.jinja",
        "template/.devcontainer/setup.sh.jinja",
        "template/scripts/check.sh.jinja",
    } <= scripts


# Copier asks Git for the modes of the files of the template, which the copy of the
# mutation tests has no Git for.
@pytest.mark.mutation_unsafe
@pytest.mark.skipif(os.name == "nt", reason="Windows has no executable files")
@pytest.mark.parametrize("kind", KINDS)
def test_every_script_of_a_new_repository_is_executable(
    projects: dict[str, Path], kind: str
) -> None:
    project = projects[kind]
    modes = {
        path.relative_to(project).as_posix(): path.stat().st_mode & 0o111
        for path in text_files(project)
    }
    scripts = {
        name for name in modes if (project / name).read_bytes().startswith(b"#!")
    }

    assert {name for name, mode in modes.items() if mode} == scripts
    assert all(modes[name] == 0o111 for name in scripts)
    assert {".githooks/pre-push", ".devcontainer/setup.sh", "scripts/check.sh"} <= (
        scripts
    )


# The author of the commits of the tests, whatever this computer has set up.
IDENTITY = ("-c", "user.name=Dev", "-c", "user.email=dev@example.com")


# It needs the modes that Copier takes from Git, which the copy of the mutation tests
# has no Git for.
@pytest.mark.mutation_unsafe
@pytest.mark.skipif(BASH is None, reason="the hook runs bash, Git Bash on Windows")
def test_the_hook_stops_a_push_whose_checks_fail(
    projects: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert BASH
    project = tmp_path / "project"
    remote = tmp_path / "remote.git"
    shutil.copytree(projects["generic"], project)
    # No configuration of this computer, such as signed commits, gets in the way, and
    # the hook finds the bash of the tests, Git Bash on Windows.
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("PATH", f"{Path(BASH).parent}{os.pathsep}{os.environ['PATH']}")

    def git(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *IDENTITY, *arguments],
            cwd=project,
            capture_output=True,
            encoding="utf-8",
            check=False,
        )

    assert git("init", "--quiet", "--bare", str(remote)).returncode == 0
    # A new repository as the README starts it, with the hook turned on as
    # CONTRIBUTING.md and the dev container turn it on.
    assert git("init", "--quiet").returncode == 0
    assert git("add", "--all").returncode == 0
    assert git("commit", "--quiet", "--message", "chore: start").returncode == 0
    assert git("config", "core.hooksPath", ".githooks").returncode == 0
    # Checks that say that they ran, and fail when FAIL is set.
    (project / "scripts/check.sh").write_text(
        'echo "The checks ran."\nexit "${FAIL:-0}"\n', encoding="utf-8", newline="\n"
    )

    monkeypatch.setenv("FAIL", "1")
    failed = git("push", str(remote), "HEAD:refs/heads/main")
    monkeypatch.delenv("FAIL")
    passed = git("push", str(remote), "HEAD:refs/heads/main")

    assert failed.returncode != 0, failed.stderr
    assert "The checks ran." in failed.stdout + failed.stderr
    assert "ignored" not in failed.stderr
    assert passed.returncode == 0, passed.stderr
    assert "The checks ran." in passed.stdout + passed.stderr


def hooks_step(check: str) -> str:
    start = check.index('step "Git hooks"')
    return check[start : check.index('step "Shell scripts"', start)]


@pytest.mark.parametrize("kind", KINDS)
def test_the_checks_look_at_the_modes_of_the_hooks(
    projects: dict[str, Path], kind: str
) -> None:
    check = (projects[kind] / "scripts/check.sh").read_text(encoding="utf-8")
    generic = (projects["generic"] / "scripts/check.sh").read_text(encoding="utf-8")

    # In every kind of project the same, right before the shell scripts.
    assert check.index('\nstep "Git hooks"\n') < check.index('\nstep "Shell scripts"\n')
    assert hooks_step(check) == hooks_step(generic)
    contributing = (projects[kind] / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "`git update-index --chmod=+x .githooks/pre-push`" in contributing


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
def test_the_checks_fail_while_git_would_skip_a_hook(
    projects: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert BASH
    check = (projects["generic"] / "scripts/check.sh").read_text(encoding="utf-8")
    repository = tmp_path / "repository"
    (repository / "scripts").mkdir(parents=True)
    # Its set-up, such as set -euo pipefail and the folder it runs in, and the step.
    script = check[: check.index('step "Text files"')] + hooks_step(check)
    (repository / "scripts/hooks.sh").write_text(script, encoding="utf-8", newline="\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")

    def git(*arguments: str) -> None:
        subprocess.run(["git", *arguments], cwd=repository, check=True)

    def step() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [BASH, "scripts/hooks.sh"],
            cwd=repository,
            capture_output=True,
            encoding="utf-8",
            check=False,
        )

    git("init", "--quiet")
    # The modes in Git alone, the same on every system: as on Windows, a new file is
    # a plain one.
    git("config", "core.fileMode", "false")
    without_hooks = step()
    (repository / ".githooks").mkdir()
    for hook in ("pre-commit", "pre-push"):
        (repository / ".githooks" / hook).write_text(
            "#!/bin/sh\n", encoding="utf-8", newline="\n"
        )
    git("add", ".githooks")
    plain = step()
    git("update-index", "--chmod=+x", ".githooks/pre-push")
    one_plain = step()
    git("update-index", "--chmod=+x", ".githooks/pre-commit")
    executable = step()

    # Every plain hook, and the command that makes them executable.
    assert (plain.returncode, plain.stdout) == (
        1,
        "\n== Git hooks\n"
        ".githooks/pre-commit: is not executable, so git skips it\n"
        ".githooks/pre-push: is not executable, so git skips it\n"
        "Make it executable and commit that: git update-index --chmod=+x"
        " .githooks/pre-commit .githooks/pre-push\n",
    )
    assert (one_plain.returncode, one_plain.stdout) == (
        1,
        "\n== Git hooks\n"
        ".githooks/pre-commit: is not executable, so git skips it\n"
        "Make it executable and commit that: git update-index --chmod=+x"
        " .githooks/pre-commit\n",
    )
    for passed in (without_hooks, executable):
        assert (passed.returncode, passed.stdout) == (
            0,
            "\n== Git hooks\nEvery hook in .githooks/ is executable.\n",
        ), passed.stderr


@pytest.mark.skipif(
    os.name == "nt" or BASH is None, reason="Windows has no executable files"
)
@pytest.mark.parametrize("file_mode", ["false", "true"])
def test_the_dev_container_makes_the_hook_executable_where_git_ignores_modes(
    projects: dict[str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    file_mode: str,
) -> None:
    assert BASH
    repository = tmp_path / "repository"
    (repository / ".devcontainer").mkdir(parents=True)
    (repository / ".githooks").mkdir()
    shutil.copy(
        projects["generic"] / ".devcontainer/setup.sh",
        repository / ".devcontainer/setup.sh",
    )
    hook = repository / ".githooks/pre-push"
    hook.write_text("#!/bin/sh\n", encoding="utf-8", newline="\n")
    # On disk, the hook of a repository whose hook Git has as a plain file.
    hook.chmod(0o644)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")

    def git(*arguments: str) -> str:
        return subprocess.run(
            ["git", *IDENTITY, *arguments],
            cwd=repository,
            capture_output=True,
            encoding="utf-8",
            check=True,
        ).stdout

    git("init", "--quiet")
    git("config", "core.fileMode", file_mode)
    git("add", "--all")
    git("commit", "--quiet", "--message", "chore: start")
    # Without mkdocs.yml, the set-up installs nothing.
    setup = subprocess.run(
        [BASH, ".devcontainer/setup.sh"],
        cwd=repository,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )

    assert setup.returncode == 0, setup.stdout + setup.stderr
    assert git("config", "core.hooksPath") == ".githooks\n"
    # Executable where Git ignores the modes; elsewhere the mode in Git applies, so
    # that the set-up changes nothing that Git would see.
    assert bool(hook.stat().st_mode & 0o111) == (file_mode == "false")
    assert git("status", "--porcelain") == ""


def test_the_link_check_asks_for_a_file_of_github_where_github_answers(
    projects: dict[str, Path],
) -> None:
    # github.com answers the page of a file with 503 at times; raw.githubusercontent.com
    # has the same file, and answers 404 for a missing one as well.
    config = (projects["generic"] / "lychee.toml").read_text(encoding="utf-8")
    [rule] = tomllib.loads(config)["remap"]
    pattern, replacement = rule.split()
    # Lychee writes a group of the regular expression as $1, Python as \g<1>.
    replacement = re.sub(r"\$(\d)", r"\\g<\1>", replacement)

    def remapped(url: str) -> str:
        return re.sub(pattern, replacement, url)

    raw = "https://raw.githubusercontent.com/owner/repo"
    blob = "https://github.com/owner/repo/blob"
    assert (
        remapped(f"{blob}/main/docs/guide.md#setup")
        == f"{raw}/main/docs/guide.md#setup"
    )
    assert remapped(f"{blob}/v1.0.0/LICENSE") == f"{raw}/v1.0.0/LICENSE"
    for url in (
        "https://github.com/owner/repo",
        "https://github.com/owner/repo/tree/main/docs",
        "https://github.com/owner/repo/issues/1",
    ):
        assert remapped(url) == url


def test_a_nextcloud_app_packages_only_what_it_needs(
    projects: dict[str, Path],
) -> None:
    project = projects["nextcloud-app"]
    ignored = (project / ".nextcloudignore").read_text(encoding="utf-8").split("\n")
    for path in (
        ".devcontainer",
        ".githooks",
        ".lycheeignore",
        "lychee.toml",
        "mkdocs.yml",
        "screenshots",
        # LICENSE carries the license text; LICENSES/ serves REUSE in the repository.
        "LICENSES",
    ):
        assert f"/{path}" in ignored, path
    # Every other file of the repository stays out of the package, also a new one.
    shipped = {"appinfo", "lib", "templates", "js", "css", "img", "l10n", "LICENSE"}
    shipped |= {"README.md", "CHANGELOG.md"}
    for entry in project.iterdir():
        assert entry.name in shipped or {entry.name, f"/{entry.name}"} & set(ignored), (
            entry.name
        )
    config = json.loads(
        (project / "release-please-config.json").read_text(encoding="utf-8")
    )["packages"]["."]
    # Lines of info.xml with the version elsewhere, such as screenshots at a tag.
    assert {"type": "generic", "path": "appinfo/info.xml"} in config["extra-files"]
    review = (project / ".github/dependency-review.yml").read_text(encoding="utf-8")
    assert "pkg:composer/netresearch/jsonmapper" in review
    assert "pkg:npm/%40cspell/dict-django" in review


def test_the_ci_builds_with_the_krankerl_of_the_release() -> None:
    pins = [
        dict(
            re.findall(
                r"(KRANKERL_(?:VERSION|SHA256)): (\S+)",
                (ROOT / ".github/workflows" / name).read_text(encoding="utf-8"),
            )
        )
        for name in ("ci-php.yml", "build-release.yml")
    ]
    assert len(pins[0]) == 2
    assert pins[0] == pins[1]


def test_a_nextcloud_app_follows_untrusted_input(projects: dict[str, Path]) -> None:
    check = (projects["nextcloud-app"] / "scripts/check.sh").read_text(encoding="utf-8")
    assert "vendor/bin/psalm --taint-analysis" in check


@pytest.mark.parametrize("kind", KINDS)
def test_secrets_stay_out_of_git(projects: dict[str, Path], kind: str) -> None:
    ignored = (projects[kind] / ".gitignore").read_text(encoding="utf-8").split("\n")
    for pattern in (".env", "*.pem", "*.key", "auth.json", "!.env.example"):
        assert pattern in ignored, pattern


def test_updates_reach_every_file_of_the_blueprint() -> None:
    # Copier matches _skip_if_exists like .gitignore; a pattern without a slash
    # would match at any depth and keep the blueprint's files from their updates.
    config = (ROOT / "copier.yml").read_text(encoding="utf-8")
    block = config.split("_skip_if_exists:", 1)[1].split("\n\n", 1)[0]
    skip = re.findall(r'^  - "?([^"\n]+?)"?$', block, re.MULTILINE)
    assert "/*.py" in skip
    # The patterns as Copier reads them.
    matcher = pathspec.PathSpec.from_lines("gitignore", skip)
    for owned in (
        "README.md",
        "CHANGELOG.md",
        "mkdocs.yml",
        "docs/index.md",
        "issue_assistant.py",
        "Dockerfile",
        "img/app.svg",
        "tests/test_demo.py",
        "custom_components/demo/__init__.py",
        ".github/labels.toml",
        "docs/security.md",
    ):
        assert matcher.match_file(owned), owned
    for updated in (
        *(f".github/{name}" for name in TOOL),
        ".devcontainer/Dockerfile",
        ".github/social-preview/Dockerfile",
        ".github/workflows/ci.yml",
        ".github/workflows/docs.yml",
        ".github/docs-requirements.txt",
        "docs/README.md",
        "scripts/check.sh",
    ):
        assert not matcher.match_file(updated), updated


def test_copying_runs_no_code_of_the_blueprint() -> None:
    # Without tasks, migrations or Jinja extensions, Copier only renders the template
    # in its sandbox and needs no --trust; docs/security.md promises it.
    config = (ROOT / "copier.yml").read_text(encoding="utf-8")
    for key in ("_tasks", "_migrations", "_jinja_extensions"):
        assert not re.search(rf"^{key}:", config, re.MULTILINE), key


@pytest.mark.parametrize("kind", KINDS)
def test_every_project_documents_its_security_and_its_roles(
    projects: dict[str, Path], kind: str
) -> None:
    def lines(name: str) -> list[str]:
        return (projects[kind] / name).read_text(encoding="utf-8").splitlines()

    security = lines("SECURITY.md")
    for heading in (
        "## Verify a release",
        "## Assurance case",
        "### Threat model",
        "### Trust boundaries",
        "### Secure design principles",
        "### Common weaknesses",
    ):
        assert heading in security, heading
    assert "gh release verify vX.Y.Z --repo Dennis-Otto/demo-project" in security
    # The assurance case leads to the security design of the software, which the
    # project keeps after the first copy.
    assert "(docs/security.md)" in "\n".join(security)
    design = lines("docs/security.md")
    for heading in (
        "## What you can expect",
        "## Trust boundaries",
        "## Threats and countermeasures",
        "## Residual risks",
    ):
        # Every section has its content for the kind of project.
        index = design.index(heading)
        assert design[index + 1] == "", heading
        assert design[index + 2].startswith(("- ", "1. ", "| ")), heading
    governance = lines("GOVERNANCE.md")
    assert "## Roles and responsibilities" in governance
    assert "the bus factor of the project is 1" in "\n".join(governance)
    assert "A successor is planned" in "\n".join(governance)
    contributing = lines("CONTRIBUTING.md")
    assert contributing[contributing.index("## Coding standards") + 2].startswith(
        "- **"
    )
    # A project with code requires tests for every new function and every fix.
    assert ("## Tests" in contributing) == (kind != "generic")


def test_a_release_names_the_files_to_verify(projects: dict[str, Path]) -> None:
    def security(kind: str) -> str:
        return (projects[kind] / "SECURITY.md").read_text(encoding="utf-8")

    assert "gh attestation verify demo_project.zip" in security("home-assistant")
    nextcloud = security("nextcloud-app")
    assert "gh attestation verify demo_project.tar.gz" in nextcloud
    assert "app-certificate-requests/master/demo_project/demo_project.crt" in nextcloud
    assert "gh attestation verify ./*.whl" in security("python-package")
    assert "npm audit signatures" in security("node-package")
    assert "oci://ghcr.io/dennis-otto/demo-project:X.Y.Z" in security("container")


@pytest.mark.parametrize("kind", ["github-action", "home-assistant", "nextcloud-app"])
def test_an_existing_repository_takes_no_sample_code(tmp_path: Path, kind: str) -> None:
    # An update would bring the samples back that an adopted repository deleted.
    project = render(
        tmp_path,
        project_name="Demo",
        description="A demo.",
        project_type=kind,
        sample_code=False,
    )
    for sample in (
        "tests",
        "fuzz",
        "docs/index.md",
        "src",
        "lib",
        "custom_components",
        "action.yml",
        "demo.py",
    ):
        assert not (project / sample).exists(), sample
    assert (project / "scripts/check.sh").exists()
    assert (project / ".github/workflows/ci.yml").exists()
    # The website waits for the pages of the project; the check docs passes until then.
    assert (project / "mkdocs.yml").exists()
    assert "sample_code: false" in (project / ".copier-answers.yml").read_text(
        encoding="utf-8"
    )


def test_the_area_labels_of_pull_requests_exist() -> None:
    labels = tomllib.loads((ROOT / ".github/labels.toml").read_text(encoding="utf-8"))
    defined = {label["name"] for label in labels["label"]}
    rules = (ROOT / ".github/labeler.yml").read_text(encoding="utf-8")
    used = set(re.findall(r'^"([^"]+)":$', rules, re.MULTILINE))
    assert used
    assert used <= defined, used - defined


@pytest.mark.parametrize("kind", KINDS)
def test_every_project_starts_with_area_rules(
    projects: dict[str, Path], kind: str
) -> None:
    rules = (projects[kind] / ".github/labeler.yml").read_text(encoding="utf-8")
    # No areas yet: an empty mapping, which the labeler accepts.
    assert rules.rstrip().endswith("{}")


def test_the_website_of_the_owner_lives_at_the_root(tmp_path: Path) -> None:
    project = render(
        tmp_path,
        project_name="Dennis Otto",
        project_slug="dennis-otto.github.io",
        description="The projects of the owner.",
        project_type="generic",
    )
    config = (project / "mkdocs.yml").read_text(encoding="utf-8")

    assert "\nsite_url: https://dennis-otto.github.io/\n" in config
    assert (
        "\nrepo_url: https://github.com/Dennis-Otto/dennis-otto.github.io\n" in config
    )


def test_the_issue_forms_point_to_the_documentation(tmp_path: Path) -> None:
    project = render(
        tmp_path,
        project_name="Demo Project",
        description="A project with a website.",
        project_type="generic",
        homepage="https://dennis-otto.github.io/demo-project/",
    )
    config = (project / ".github/ISSUE_TEMPLATE/config.yml").read_text(encoding="utf-8")

    assert config.index("name: Documentation") < config.index(
        "name: Security vulnerability"
    )
    assert "url: https://dennis-otto.github.io/demo-project/" in config


def test_a_designated_successor_continues_the_project(tmp_path: Path) -> None:
    project = render(
        tmp_path,
        project_name="Demo Project",
        description="An app with a successor.",
        project_type="nextcloud-app",
        successor=True,
    )
    governance = (project / "GOVERNANCE.md").read_text(encoding="utf-8")

    assert "GitHub's account successor setting" in governance
    assert "the bus factor of the project is 2" in governance
    assert "don't pass with the repository" in governance
    assert "A successor is planned" not in governance
    assert "bus factor of the project is 1" not in governance


@pytest.mark.parametrize("kind", KINDS)
def test_releases_are_announced_in_the_discussions(
    projects: dict[str, Path], kind: str
) -> None:
    project = projects[kind]
    for form in ("q-a.yml", "ideas.yml"):
        assert (project / ".github/DISCUSSION_TEMPLATE" / form).is_file(), form
    release = workflows(project)["release.yml"]
    publish = release[release.index("  publish:") :]
    publish = publish[: publish.index("\n  pypi:")]
    assert "discussions: write" in publish
    # Only a release for everybody, not a prerelease, is announced.
    assert publish.index("exit 0") < publish.index("--discussion-category")
    assert "has_discussions = true" in (project / ".github/repository.toml").read_text(
        encoding="utf-8"
    )


def test_a_project_without_discussions(tmp_path: Path) -> None:
    project = render(
        tmp_path,
        project_name="Demo",
        description="A demo.",
        project_type="generic",
        discussions=False,
    )

    assert not (project / ".github/DISCUSSION_TEMPLATE").exists()
    assert "discussions" not in (project / "SUPPORT.md").read_text(encoding="utf-8")
    assert "has_discussions = false" in (project / ".github/repository.toml").read_text(
        encoding="utf-8"
    )


def test_a_nextcloud_app_covers_every_line(projects: dict[str, Path]) -> None:
    project = projects["nextcloud-app"]
    check = (project / "scripts/check.sh").read_text(encoding="utf-8")
    assert "--coverage-cobertura build/coverage.xml" in check
    assert '["line-rate"]' in check
    assert "<directory>lib</directory>" in (project / "phpunit.xml").read_text(
        encoding="utf-8"
    )
    ci = (ROOT / ".github/workflows/ci-php.yml").read_text(encoding="utf-8")
    assert "coverage: pcov" in ci


@pytest.mark.parametrize("kind", KINDS)
def test_renovate_keeps_every_project_current(
    projects: dict[str, Path], kind: str
) -> None:
    project = projects[kind]
    entry = (project / ".github/renovate.json5").read_text(encoding="utf-8")
    # The project's file extends the blueprint's, so that its own rules come last.
    assert '"local>Dennis-Otto/demo-project//.github/renovate-blueprint.json5"' in entry
    rules = (project / ".github/renovate-blueprint.json5").read_text(encoding="utf-8")
    for setting in (
        'minimumReleaseAge: "7 days"',
        "platformAutomerge: true",
        "minimumReleaseAge: null",
        "copier: { enabled: false }",
        "devcontainer: { enabled: false }",
        '"pre-commit": { enabled: true }',
    ):
        assert setting in rules, setting
    # The weekly refresh of the lock files has no release date: it merges at once.
    refresh = re.search(
        r'matchUpdateTypes: \["lockFileMaintenance"\],\n\s+minimumReleaseAge: null,\n'
        r"\s+automerge: true,",
        rules,
    )
    assert refresh
    python = kind in ("home-assistant", "github-action", "python-package")
    # Ruff and its pre-commit hook run the same version.
    assert ('matchDepNames: ["ruff", "astral-sh/ruff-pre-commit"]' in rules) == python
    assert ('matchManagers: ["pip-compile", "pep621", "pre-commit"]' in rules) == python
    # The test plugin of Home Assistant, now and then on a beta, moves on its own.
    test_base = 'groupName: "the Home Assistant test base"'
    assert (test_base in rules) == (kind == "home-assistant")
    # The Nextcloud apps get only the releases that run on their oldest PHP.
    assert ('constraintsFiltering: "strict"' in rules) == (kind == "nextcloud-app")
    review = (project / ".github/dependency-review.yml").read_text(encoding="utf-8")
    assert ("- pkg:pypi/regex\n" in review) == (kind == "home-assistant")
    # The images of the scripts, also in a variable with quotes.
    pattern = re.search(r'^\s*"(\(\?:\^\|.*sha256.*)",$', rules, re.MULTILINE)
    assert pattern
    images = re.compile(json.loads(f'"{pattern[1]}"').replace("(?<", "(?P<"))
    digest = "sha256:" + "0" * 64
    for line in (
        f"  image: ghcr.io/owner/tool:v1.2.3@{digest}",
        f'IMAGE="mcr.microsoft.com/playwright:v1.63.0-noble@{digest}"',
        f"IMAGE=docker.io/library/python:3.14@{digest}",
    ):
        found = images.search(line)
        assert found, line
        assert found["currentDigest"] == digest
    # Dependabot keeps only the Features of the dev container and their lock file.
    dependabot = (project / ".github/dependabot.yml").read_text(encoding="utf-8")
    assert re.findall(r"package-ecosystem: (\S+)", dependabot) == ["devcontainers"]
    settings = (project / ".github/repository.toml").read_text(encoding="utf-8")
    assert "dependabot_security_updates = false" in settings


@pytest.mark.parametrize("kind", KINDS)
def test_renovate_follows_an_action_pinned_to_a_branch_at_once(
    projects: dict[str, Path], kind: str
) -> None:
    # A workflow of the project may still pin an action to a commit of a branch, with
    # the branch in its comment. Renovate looks such a pin up as a github-digest, for
    # which every commit to the branch is a new release: with the week of waiting, a
    # branch that moves every few days would never be followed, and zizmor reports
    # the pin all the while.
    rules = (projects[kind] / ".github/renovate-blueprint.json5").read_text(
        encoding="utf-8"
    )
    rule = re.search(
        r'\{\n(?:\s+//.*\n)+\s+matchManagers: \["github-actions"\],\n'
        r'\s+matchDatasources: \["github-digest"\],\n'
        r"\s+minimumReleaseAge: null,\n"
        r'\s+schedule: \["at any time"\],\n'
        r"\s+automerge: true,\n"
        r'\s+groupName: "the actions that follow a branch",\n\s+\},',
        rules,
    )
    assert rule
    # After the groups of the actions, so that its own group and schedule apply.
    for group in ("the actions", "the actions to a new major version"):
        assert rules.index(f'groupName: "{group}"') < rule.start(), group


# It asks Git for the files of the repository, which the copy of the mutation tests
# has none of.
@pytest.mark.mutation_unsafe
def test_renovate_compiles_every_lock_file_for_its_own_python() -> None:
    # Renovate installs pip-tools once per repository and run, for the Python of the
    # first lock file it compiles: the lock files of pip-compile share one Python, and
    # one for another Python is compiled with uv, for a Python with its patch level.
    pip_compile = {}
    uv = {}
    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True, text=True
    ).stdout.split("\0")
    for name in tracked:
        if not re.search(r"(^|/)requirements[^/]*\.txt$", name):
            continue
        header = "".join((ROOT / name).read_text(encoding="utf-8").splitlines(True)[:5])
        if found := re.search(
            r"autogenerated by pip-compile with Python (\S+)", header
        ):
            pip_compile[name] = found[1]
            # pip-tools 7.6.1 recorded it by mistake, and Renovate refuses it.
            assert "--no-index" not in header, name
        else:
            command = re.search(
                r"^#    uv pip compile .*--python-version (\d+\.\d+\.\d+) ",
                header,
                re.M,
            )
            assert command, name
            uv[name] = command[1]
    assert len(set(pip_compile.values())) == 1, pip_compile
    assert list(uv) == ["stacks/home-assistant/requirements-test.txt"]
    copier = (ROOT / "copier.yml").read_text(encoding="utf-8")
    python = re.search(r"stack == 'home-assistant' %\]([\d.]+)\[% else", copier)
    assert python
    assert uv["stacks/home-assistant/requirements-test.txt"].startswith(python[1] + ".")
    # The pinned test plugin makes a Home Assistant that needs a newer Python fail
    # its update, instead of an older Home Assistant being chosen.
    inputs = (ROOT / "stacks/home-assistant/requirements-test.in").read_text(
        encoding="utf-8"
    )
    assert re.search(r"^pytest-homeassistant-custom-component==\S+$", inputs, re.M)


def test_renovate_filters_composer_by_the_php_of_the_stack() -> None:
    composer = json.loads(
        (ROOT / "stacks/php/composer.json").read_text(encoding="utf-8")
    )
    platform = composer["config"]["platform"]["php"]
    expected = f'constraints: {{ php: "{".".join(platform.split(".")[:2])}.*" }}'
    for name in (
        ".github/renovate.json5",
        "template/.github/renovate-blueprint.json5.jinja",
    ):
        assert expected in (ROOT / name).read_text(encoding="utf-8"), name


def test_every_release_of_the_blueprint_rolls_out_one_repository_at_a_time(
    projects: dict[str, Path],
) -> None:
    rollout = (ROOT / ".github/workflows/rollout.yml").read_text(encoding="utf-8")
    plan = rollout[rollout.index("\n  plan:\n") : rollout.index("\n  rollout:\n")]
    job = rollout[rollout.index("\n  rollout:\n") :]
    # After a successful run of the Release workflow on main, and only in the blueprint.
    assert "workflows: [Release]" in rollout
    assert "branches: [main]" in rollout
    assert "github.event.workflow_run.conclusion == 'success'" in plan
    assert "github.repository == 'Dennis-Otto/repo-blueprint'" in plan
    # A run of any event can make a release: for a push only the merge of a release
    # pull request, whose title the merge commit starts with, so that the merges of
    # every other pull request start no runner.
    assert "github.event.workflow_run.event != 'push' ||" in plan
    prefix = "chore: release "
    assert (
        f"startsWith(github.event.workflow_run.head_commit.message, '{prefix}')" in plan
    )
    config = json.loads(
        (ROOT / "release-please-config.json").read_text(encoding="utf-8")
    )
    assert config["packages"]["."]["pull-request-title-pattern"].startswith(prefix)
    # The release that the run published, not the one at its commit: the job of the
    # Release workflow that makes it public tells.
    assert "HEAD_SHA" not in rollout
    release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "    name: publish the release\n" in release
    assert 'select(.name == "publish the release")' in plan
    # One repository after the other, every one of them, each with a token of its own
    # that can only start workflows and read; 15 looks at most before the next one.
    assert "      max-parallel: 1\n      fail-fast: false\n" in job
    assert "repository: ${{ fromJSON(needs.plan.outputs.repositories) }}" in job
    assert "repositories: ${{ matrix.repository }}" in job
    permissions = re.findall(r"^\s+permission-([\w-]+): (\w+)$", plan, re.M)
    assert permissions == [("metadata", "read")]
    permissions = re.findall(r"^\s+permission-([\w-]+): (\w+)$", job, re.M)
    assert permissions == [
        ("actions", "write"),
        ("checks", "read"),
        ("contents", "read"),
        ("pull-requests", "read"),
        ("statuses", "read"),
    ]
    assert "looks=15\n" in job
    assert "    timeout-minutes: 25\n" in job
    assert "gh workflow run blueprint-update.yml" in job
    # One rollout at a time in each repository, never for the whole workflow: GitHub
    # starts a Rollout run after every run of the Release workflow, and a group of the
    # workflow would let one that rolls nothing out cancel the waiting rollout of a
    # release. The group is on the job that a run without a release skips.
    assert not re.search(r"^concurrency:", rollout, re.M)
    assert re.findall(r"^\s+concurrency:$", rollout, re.M) == ["    concurrency:"]
    assert (
        "    concurrency:\n"
        "      group: rollout-${{ matrix.repository }}\n"
        "      cancel-in-progress: false\n"
    ) in job
    assert "    if: needs.plan.outputs.repositories != ''\n" in job
    zizmor = (ROOT / ".github/zizmor.yml").read_text(encoding="utf-8")
    assert "      - rollout.yml\n" in zizmor
    # The bot it starts can be started by hand; a project has no rollout of its own.
    for project in projects.values():
        update = project / ".github/workflows/blueprint-update.yml"
        assert "  workflow_dispatch:\n" in update.read_text(encoding="utf-8")
        assert not (project / ".github/workflows/rollout.yml").exists()


def test_renovate_runs_one_release_everywhere() -> None:
    pins = set()
    for name in ("renovate.yml", "variants.yml"):
        text = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
        pins |= set(
            re.findall(
                r"ghcr\.io/renovatebot/renovate:[\w.]+@sha256:[0-9a-f]{64}", text
            )
        )
        pins |= {
            f"ghcr.io/renovatebot/renovate:{version}"
            for version in re.findall(r"renovate-version: (\S+)", text)
        }
    assert len(pins) == 1, pins


def test_copier_updates_without_the_maintenance_of_git_in_the_background(
    projects: dict[str, Path],
) -> None:
    # Since Git 2.47, a commit starts git maintenance in the background, and copier
    # update deletes the repositories it commits to right away: the two collided now
    # and then, and the update failed with "Directory not empty".
    command = re.compile(r"^(?!\s*#).*\bcopier update\b", re.MULTILINE)
    settings = (
        'GIT_CONFIG_COUNT: "1"',
        "GIT_CONFIG_KEY_0: maintenance.auto",
        'GIT_CONFIG_VALUE_0: "false"',
    )
    steps = [
        (name, step)
        for root in (projects["generic"], ROOT)
        for name, text in workflows(root).items()
        for step in text.split("\n      - ")[1:]
        if command.search(step)
    ]

    # The blueprint bot of a project and of the blueprint itself, and Variants.
    assert sorted(name for name, _ in steps) == [
        "blueprint-update.yml",
        "blueprint-update.yml",
        "variants.yml",
    ]
    for name, step in steps:
        assert all(setting in step for setting in settings), name


# It starts the tool, which in the copy of the mutation tests is the code with the
# mutants, and the variables of mutmut switch them in that process too.
@pytest.mark.mutation_unsafe
@pytest.mark.parametrize("kind", KINDS)
def test_the_blueprint_bot_keeps_one_pull_request(
    projects: dict[str, Path], kind: str
) -> None:
    project = projects[kind]
    text = (project / ".github/workflows/blueprint-update.yml").read_text(
        encoding="utf-8"
    )
    steps = text.split("\n      - ")
    release = next(step for step in steps if "gh release view" in step)
    update = next(step for step in steps if "copier update --" in step)

    # Only to a published release: the Release workflow pushes the tag first.
    assert 'gh release view --repo "$source" --json tagName --jq .tagName' in release
    assert "TAG: ${{ steps.release.outputs.tag }}" in update
    assert "SOURCE: ${{ steps.release.outputs.source }}" in update
    assert '--source "$SOURCE"' in update
    assert 'copier update --defaults --conflict inline --vcs-ref "$TAG"' in update
    # The bot of main commits, copied before the update changes it, as the app whose
    # commits it may replace; the scratch branch of a commit without modes is per run.
    assert (
        update.index("cp -R .github/blueprint.py .github/blueprint")
        < update.index("copier update --")
        < update.index("git add --all")
        < update.index("update-commit")
    )
    assert "APP: ${{ steps.app.outputs.app-slug }}" in update
    assert '--app "${APP}[bot]"' in update
    assert '--run-id "$GITHUB_RUN_ID"' in update
    # The workflow no longer puts the branch back on main, which closed the pull
    # request, nor scans the whole repository for markers.
    for gone in ("force", "createCommitOnBranch", "git grep", "gh pr merge"):
        assert gone not in text, gone
    tool = (project / ".github/blueprint/update.py").read_text(encoding="utf-8")
    assert '"--disable-auto"' in tool
    assert 'f"{BRANCH}-{run_id}"' in tool
    assert 'BRANCH = "blueprint/update"' in tool
    result = subprocess.run(
        [sys.executable, ".github/blueprint.py", "update-commit", "--help"],
        cwd=project,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "--app APP" in result.stdout
    assert "--source SOURCE" in result.stdout


def run_the_release_step(tmp_path: Path, source: str) -> tuple[int, str, str]:
    """The step of the blueprint bot that finds the release to update to, with a gh
    that knows the releases of the blueprint and of a fork."""
    text = (ROOT / ".github/workflows/blueprint-update.yml").read_text(encoding="utf-8")
    step = next(step for step in text.split("\n      - ") if "gh release view" in step)
    script = textwrap.dedent(step.split("        run: |\n", 1)[1])
    (tmp_path / "step.sh").write_text(script, encoding="utf-8", newline="\n")
    (tmp_path / ".copier-answers.yml").write_text(
        f"_commit: v1.0.0\n_src_path: {source}\n", encoding="utf-8", newline="\n"
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(
        """#!/usr/bin/env bash
case "$*" in
  "release view --repo Dennis-Otto/repo-blueprint --json tagName --jq .tagName") echo v1.2.0 ;;
  "release view --repo Someone/blueprint --json tagName --jq .tagName") echo v0.3.0 ;;
  "release view --repo Someone/new --json tagName --jq .tagName") ;;
  *) echo "unexpected: gh $*" >&2; exit 1 ;;
esac
""",
        encoding="utf-8",
        newline="\n",
    )
    gh.chmod(0o755)
    output = tmp_path / "output"
    output.touch()
    environment = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "GITHUB_OUTPUT": str(output),
    }
    assert BASH
    result = subprocess.run(
        [BASH, "-e", "step.sh"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    return result.returncode, output.read_text(encoding="utf-8"), result.stdout


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize(
    ("source", "output"),
    [
        (
            "https://github.com/Dennis-Otto/repo-blueprint.git",
            "source=Dennis-Otto/repo-blueprint\ntag=v1.2.0\n",
        ),
        # A repository made from a fork updates to the fork's releases, whose tags
        # the fork has.
        ("gh:Someone/blueprint", "source=Someone/blueprint\ntag=v0.3.0\n"),
        (
            "https://github.com/Someone/blueprint",
            "source=Someone/blueprint\ntag=v0.3.0\n",
        ),
        # A blueprint that isn't on GitHub, a folder for a test, say.
        ("/home/me/repo-blueprint", "source=Dennis-Otto/repo-blueprint\ntag=v1.2.0\n"),
    ],
)
def test_the_blueprint_bot_updates_to_the_release_of_its_source(
    tmp_path: Path, source: str, output: str
) -> None:
    assert run_the_release_step(tmp_path, source)[:2] == (0, output)


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
def test_the_blueprint_bot_needs_a_published_release(tmp_path: Path) -> None:
    code, output, stdout = run_the_release_step(tmp_path, "gh:Someone/new")

    assert code == 1
    assert output == ""
    assert "::error::The blueprint Someone/new has no published release" in stdout


def test_the_branch_bot_brings_renovate_up_to_date_as_renovate_itself() -> None:
    text = (ROOT / ".github/workflows/update-branches.yml").read_text(encoding="utf-8")
    # Renovate's pull requests are brought up to date, but not the release bot's.
    assert 'startswith("renovate/")' not in text
    assert 'startswith("release-please--") | not' in text
    # A conflicting one Renovate builds anew: no label and no comment of the bot.
    skip = '[[ "$branch" == renovate/* && "$mergeable" == CONFLICTING ]]'
    assert text.index(skip) < text.index("--add-label merge-conflict")
    # The bot's merge commits come from the release app, as Renovate's own commits
    # do, so Renovate doesn't take the branch for edited and keeps it current.
    assert "client-id: ${{ vars.RELEASE_AUTOMATION_CLIENT_ID }}" in text
    bot = (ROOT / ".github/renovate-global.json5").read_text(encoding="utf-8")
    assert 'username: "dennis-otto-release-automation[bot]"' in bot
    assert 'gitAuthor: "dennis-otto-release-automation[bot] <' in bot


def test_a_beta_of_the_next_release_follows_every_change_for_users() -> None:
    release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    job = release[release.index("  release-please:") : release.index("\n  assets:")]
    assert "vars.BETA_CHANNEL == 'true'" in job
    assert "github.event_name == 'push'" in job
    assert "steps.release.outputs.release_created != 'true'" in job
    # Dependency updates make no beta; the outputs carry a beta like a release.
    assert '"${BASH_REMATCH[3]}" == deps*' in job
    assert "steps.release.outputs.tag_name || steps.beta.outputs.tag" in job
    assert 'gh release create "v$version" --draft --prerelease' in job


# The workflows of the required checks besides the tests, the same in every repository.
OTHER_CHECKS = {
    "CodeQL",
    "Dependency review",
    "Docs",
    "Lint",
    "Pull request title",
    "Secret scan",
}


def watched_after_the_checks(workflow: str) -> set[str]:
    watched = re.search(r"^    workflows: \[(.+)\]$", workflow, re.MULTILINE)
    assert watched
    return set(watched[1].split(", "))


def after_the_checks_job(name: str) -> str:
    after = (ROOT / ".github/workflows/after-checks.yml").read_text(encoding="utf-8")
    return job_of(after, name)


def test_the_bots_after_the_checks_watch_what_runs_in_the_blueprint() -> None:
    # The checks of every kind of project are only templates here, whose jobs skip.
    after = (ROOT / ".github/workflows/after-checks.yml").read_text(encoding="utf-8")
    assert watched_after_the_checks(after) == {"CI (python)", "Variants"} | OTHER_CHECKS
    assert "github.event.workflow_run.run_attempt == 1" in after


@pytest.mark.parametrize("kind", KINDS)
def test_the_bots_after_the_checks_watch_the_checks_of_the_project(
    projects: dict[str, Path], kind: str
) -> None:
    workflows = projects[kind] / ".github/workflows"
    after = (workflows / "after-checks.yml").read_text(encoding="utf-8")
    watched = watched_after_the_checks(after)
    names = {"Docker E2E"}
    for path in workflows.glob("*.yml"):
        name = re.search(r"^name: (.+)$", path.read_text(encoding="utf-8"), re.M)
        assert name, path
        if path.name in ("ci.yml", "action-test.yml"):
            names.add(name[1])
    assert watched == names | OTHER_CHECKS
    assert "the blueprint sets them" not in after
    assert not (workflows / "flaky.yml").exists()
    assert not (workflows / "coverage.yml").exists()


@pytest.mark.parametrize("project", ["blueprint", *KINDS])
def test_the_bot_for_cancelled_checks_watches_every_required_check(
    projects: dict[str, Path], project: str
) -> None:
    # A late run for an older commit may cancel the run of any of them.
    root = ROOT if project == "blueprint" else projects[project]
    settings = tomllib.loads(
        (root / ".github/repository.toml").read_text(encoding="utf-8")
    )
    required = set(settings["branch"]["required_checks"])
    watched = watched_after_the_checks(
        (root / ".github/workflows/after-checks.yml").read_text(encoding="utf-8")
    )
    providers = set()
    for path in (root / ".github/workflows").glob("*.yml"):
        text = path.read_text(encoding="utf-8")
        if required & set(re.findall(r"^    name: (.+)$", text, re.M)):
            name = re.search(r"^name: (.+)$", text, re.M)
            assert name, path
            providers.add(name[1])
            # Runs of a pull request cancel the older runs of the same one.
            assert "cancel-in-progress:" in text, path
    assert providers >= OTHER_CHECKS
    assert providers <= watched


def test_the_flaky_test_bot_leaves_the_other_required_checks_alone() -> None:
    # Their checks fail the same way again, or, as the changelog, pass once the pull
    # request changed: no flaky test either way.
    for job in ("rerun", "report"):
        listed = re.search(
            r"!contains\(fromJSON\('(\[.+?\])'\), github\.event\.workflow_run\.name\)",
            after_the_checks_job(job),
        )
        assert listed, job
        assert set(json.loads(listed[1])) == OTHER_CHECKS, job
    # A run that the bot for cancelled checks started again failed at first in no test.
    report = after_the_checks_job("report")
    assert report.index('attempts/1" --jq .conclusion)" == cancelled') < report.index(
        "gh issue create"
    )


def test_the_bot_for_cancelled_checks_only_starts_the_runs_of_the_head_again() -> None:
    job = after_the_checks_job("cancelled")
    assert "github.event.workflow_run.conclusion == 'cancelled'" in job
    events = """contains(fromJSON('["pull_request", "pull_request_target"]'), github.event.workflow_run.event)"""
    assert events in job
    # Twice at most, whatever cancels the run again.
    assert "github.event.workflow_run.run_attempt < 3" in job
    # It reads the runs, their checks and pull requests and starts a run again; it
    # checks out nothing.
    permissions = job[job.index("    permissions:\n") : job.index("    steps:\n")]
    assert permissions.splitlines()[1:] == [
        "      actions: write",
        "      checks: read",
        "      pull-requests: read",
    ]
    assert "actions/checkout" not in job
    # Every job of the run starts again, so that each of its checks reports.
    assert 'gh run rerun "$RUN"\n' in job
    assert "--failed" not in job
    # The values of the event reach the script as variables only.
    assert "${{" not in job[job.index("        run: |\n") :]


def run_the_bot_for_cancelled_checks(
    tmp_path: Path, pull: str, newer: str, message: str
) -> tuple[str, str]:
    job = after_the_checks_job("cancelled")
    script = textwrap.dedent(
        job[job.index("        run: |\n") + len("        run: |\n") :]
    )
    (tmp_path / "step.sh").write_text(script, encoding="utf-8", newline="\n")
    # gh answers as the API does, after the filters of jq.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(
        """#!/usr/bin/env bash
echo "$*" >> "$CALLS"
case "$*" in
  "api repos/o/r/commits/abc1234def/pulls --jq "*) printf '%s\\n' "$PULL" ;;
  "api repos/o/r/actions/workflows/3/runs?head_sha=abc1234def --paginate --jq "*) printf '%s\\n' "$NEWER" ;;
  "api repos/o/r/actions/runs/5/attempts/1/jobs --paginate --jq "*) printf '11\\n12\\n' ;;
  "api repos/o/r/check-runs/1"[12]"/annotations --paginate --jq .[].message") printf '%s\\n' "$MESSAGE" ;;
  "run rerun 5") ;;
  *) echo "unexpected: gh $*" >&2; exit 1 ;;
esac
""",
        encoding="utf-8",
        newline="\n",
    )
    gh.chmod(0o755)
    calls = tmp_path / "calls"
    summary = tmp_path / "summary"
    calls.touch()
    summary.touch()
    environment = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "GH_REPO": "o/r",
        "RUN": "5",
        "ATTEMPT": "1",
        "WORKFLOW": "3",
        "NAME": "CodeQL",
        "SHA": "abc1234def",
        "GITHUB_STEP_SUMMARY": str(summary),
        "CALLS": str(calls),
        "PULL": pull,
        "NEWER": newer,
        "MESSAGE": message,
    }
    # As GitHub runs a step: bash -e.
    assert BASH
    result = subprocess.run(
        [BASH, "-e", "step.sh"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return calls.read_text(encoding="utf-8"), summary.read_text(encoding="utf-8")


RACED = "Canceling since a higher priority waiting request for CodeQL-136 exists"


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize(
    ("pull", "newer", "message", "summary"),
    [
        # A newer push replaced the commit, or the pull request is closed.
        ("", "", RACED, "abc1234 is not the head of an open pull request"),
        # Another run of the same commit, such as one of an edited title, reports.
        ("136", "7", RACED, "A newer run of CodeQL for abc1234 reports"),
        # A person cancelled it.
        ("136", "", "The operation was canceled.", "it stays cancelled"),
        # A late run for an older commit cancelled the run for the head.
        ("136", "", RACED, "the head of #136; it runs again"),
    ],
)
def test_the_bot_for_cancelled_checks_starts_only_a_run_that_lost_a_race(
    tmp_path: Path, pull: str, newer: str, message: str, summary: str
) -> None:
    calls, written = run_the_bot_for_cancelled_checks(tmp_path, pull, newer, message)

    assert summary in written
    assert ("run rerun 5\n" in calls) == summary.endswith("it runs again")


def test_the_tests_start_the_bash_of_the_path() -> None:
    # A bare "bash" ran the steps in WSL on Windows, and scripts/check.sh failed there:
    # the first argument of a call or of a list or tuple, alone or after env; only the
    # search for it may name it. A search of the whole PATH finds the same WSL from
    # PowerShell or an IDE: every test takes BASH of tests/shell.py.
    bare = re.compile(r'(?:\[|(?<!which)\()\s*(?:"/usr/bin/env",\s*)?"bash"\s*[,\])]')
    anywhere = re.compile(r'which\(\s*"bash"\s*\)')
    for path in sorted((ROOT / "tests").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        assert not bare.search(text), path.name
        assert not anywhere.search(text), path.name


def test_the_checks_run_on_windows_as_well(projects: dict[str, Path]) -> None:
    # Contributors on Windows run scripts/check.sh in Git Bash; the other workflows
    # run on Linux only.
    windows = (ROOT / ".github/workflows/windows.yml").read_text(encoding="utf-8")
    assert "    runs-on: windows-latest\n" in windows
    assert "    shell: bash\n" in windows
    assert "run: pip install --require-hashes -r requirements-dev.txt\n" in windows
    assert "run: bash scripts/check.sh\n" in windows
    # Every week, and for each pull request that changes what the checks run, the
    # template that the tests render among it: its paths must be valid on Windows too.
    assert "  schedule:\n    - cron: " in windows
    paths = re.search(r"  pull_request:\n    paths:\n((?:      - .+\n)+)", windows)
    assert paths
    assert {line[8:].strip('"') for line in paths[1].splitlines()} >= {
        "**.py",
        "blueprint/**",
        "tests/**",
        "template/**",
        "includes/**",
        "copier.yml",
        "pyproject.toml",
        "requirements-dev.txt",
        "scripts/check.sh",
        ".github/workflows/windows.yml",
    }
    # A check of the blueprint alone, which no pull request has to wait for.
    settings = tomllib.loads(
        (ROOT / ".github/repository.toml").read_text(encoding="utf-8")
    )
    assert re.findall(r"^    name: (.+)$", windows, re.M) == ["check (Windows)"]
    assert "check (Windows)" not in settings["branch"]["required_checks"]
    for project in projects.values():
        assert not (project / ".github/workflows/windows.yml").exists()


# The release pull request: the branch of the release bot in this repository, not a
# branch of a fork that is named like it.
RELEASE_PULL_REQUEST = (
    "!startsWith(github.head_ref, 'release-please--') || "
    "github.event.pull_request.head.repo.full_name != github.repository"
)
# The scanners of pull requests, by workflow and job, each for the files it reads.
SCANNERS = {
    "fuzz.yml": "fuzz",
    "zizmor.yml": "zizmor",
    "osv-scanner.yml": "pull-request",
    "links.yml": "links",
}


def test_the_release_pull_request_runs_nothing_that_its_change_cannot_fail() -> None:
    # It changes the changelog and the version, which no kind of project renders and
    # no scanner reads, and the pull requests it releases ran every check already.
    flows = workflows(ROOT)
    skipped = {"variants.yml": "variant", "lint.yml": "prose", **SCANNERS}
    for name, job in skipped.items():
        assert RELEASE_PULL_REQUEST in condition_of(job_of(flows[name], job)), name


def test_one_check_stands_for_every_variant() -> None:
    variants = (ROOT / ".github/workflows/variants.yml").read_text(encoding="utf-8")
    gate = job_of(variants, "variants")
    assert "\n    name: variants\n" in gate
    assert "\n    needs: variant\n" in gate
    # Also after a variant failed, so that the check reports the failure.
    assert condition_of(gate) == "always()"
    settings = tomllib.loads(
        (ROOT / ".github/repository.toml").read_text(encoding="utf-8")
    )
    # A matrix that its condition skips reports none of its legs, so none is required.
    required = settings["branch"]["required_checks"]
    assert [check for check in required if check.startswith(("variant", "update"))] == [
        "variants"
    ]


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize(
    ("result", "passes"),
    [("success", True), ("skipped", True), ("failure", False), ("cancelled", False)],
)
def test_the_check_variants_passes_when_every_variant_passed_or_none_ran(
    tmp_path: Path, result: str, passes: bool
) -> None:
    variants = (ROOT / ".github/workflows/variants.yml").read_text(encoding="utf-8")
    script = script_of(variants, "Require every variant to pass, or none to run")
    (tmp_path / "step.sh").write_text(script, encoding="utf-8", newline="\n")
    assert BASH
    done = subprocess.run(
        [BASH, "-e", "step.sh"],
        cwd=tmp_path,
        env={**os.environ, "RESULT": result},
        capture_output=True,
        encoding="utf-8",
        check=False,
    )

    assert (done.returncode == 0) == passes, done.stderr


def test_a_merge_runs_only_what_keeps_a_baseline_of_main() -> None:
    # main takes a pull request only when it is up to date, so a merge gives main the
    # tree that the checks of the pull request passed with.
    flows = workflows(ROOT)
    for name in ("variants.yml", "lint.yml", "secret-scan.yml", "sbom.yml", "fuzz.yml"):
        assert "push" not in triggers(flows[name]), name
    # What depends on tools and sites that move on their own runs every week instead.
    for name in ("variants.yml", "secret-scan.yml", "sbom.yml", "fuzz.yml"):
        assert "schedule" in triggers(flows[name]), name
    # Every release carries an SBOM of its own; the weekly one is the repository's.
    assert set(triggers(flows["sbom.yml"])) == {"schedule", "workflow_dispatch"}
    # After every merge: the coverage of main, the newest Python, the analyses that code
    # scanning compares pull requests with, the website, the release and the branch bot.
    for name in (
        "ci-python.yml",
        "newest-python.yml",
        "codeql.yml",
        "zizmor.yml",
        "osv-scanner.yml",
        "scorecard.yml",
        "docs.yml",
        "release.yml",
        "update-branches.yml",
    ):
        assert triggers(flows[name])["push"] == ["    branches: [main]"], name


@pytest.mark.parametrize("project", ["blueprint", *KINDS])
def test_a_scanner_runs_in_the_pull_requests_that_change_what_it_reads(
    projects: dict[str, Path], project: str
) -> None:
    root = ROOT if project == "blueprint" else projects[project]
    flows = workflows(root)
    scanners = [name for name in SCANNERS if name in flows]
    filters = {name: paths_of(flows[name], "pull_request") for name in scanners}
    # Only Python projects are fuzzed.
    python = project in ("blueprint", "python-package", "github-action")
    assert ("fuzz.yml" in filters) == python

    def reads(scanner: str, path: str) -> bool:
        name = path.rsplit("/", 1)[-1]
        if scanner == "fuzz.yml":
            return path.endswith(".py") or path.startswith("fuzz/")
        if scanner == "zizmor.yml":
            return path.startswith(".github/workflows/") or path in (
                "action.yml",
                ".github/dependabot.yml",
                ".github/zizmor.yml",
            )
        if scanner == "osv-scanner.yml":
            return bool(re.search(r"requirements[^/]*\.txt$", name)) or name in (
                "package-lock.json",
                "composer.lock",
                "osv-scanner.toml",
            )
        return path.endswith(".md") and path != "CHANGELOG.md"

    for path in files_of(root):
        for scanner, patterns in filters.items():
            if reads(scanner, path):
                assert runs_for(patterns, [path]), f"{scanner}: {path}"
    # A change of the documentation starts only the link check, and the release pull
    # request, with the changelog and the version, starts none.
    for changed in (
        ["README.md", "docs/index.md"],
        ["CHANGELOG.md", "version.txt", ".release-please-manifest.json"],
    ):
        for scanner, patterns in filters.items():
            expected = scanner == "links.yml" and "README.md" in changed
            assert runs_for(patterns, changed) == expected, (scanner, changed)


@pytest.mark.parametrize("project", ["blueprint", *KINDS])
def test_a_required_check_never_waits_for_a_path_filter(
    projects: dict[str, Path], project: str
) -> None:
    # A workflow that its path filter leaves out reports none of its checks, and a
    # required check that never reports blocks the pull request for good.
    root = ROOT if project == "blueprint" else projects[project]
    settings = tomllib.loads(
        (root / ".github/repository.toml").read_text(encoding="utf-8")
    )
    required = set(settings["branch"]["required_checks"])
    providers = 0
    for name, text in workflows(root).items():
        if required & set(re.findall(r"^    name: (.+)$", text, re.M)):
            providers += 1
            events = triggers(text)
            assert {"pull_request", "pull_request_target"} & set(events), name
            for event in ("pull_request", "pull_request_target"):
                for line in events.get(event, []):
                    assert not line.startswith("    paths"), f"{name}: {line}"
    assert providers >= len(OTHER_CHECKS)


@pytest.mark.parametrize("project", ["blueprint", *KINDS])
def test_the_newest_python_checks_main_and_every_week(
    projects: dict[str, Path], project: str
) -> None:
    root = ROOT if project == "blueprint" else projects[project]
    flows = workflows(root)
    python = project in ("blueprint", "python-package", "github-action")
    assert ("newest-python.yml" in flows) == python
    for name, text in flows.items():
        if name != "newest-python.yml":
            assert "check (newest Python)" not in text, name
    if python:
        newest = flows["newest-python.yml"]
        # Not in pull requests: a new Python breaks them all alike, and none waits for
        # this check. A workflow of its own, so that it leaves the CI of main green.
        assert set(triggers(newest)) == {"push", "schedule", "workflow_dispatch"}
        assert "\n    name: check (newest Python)\n" in newest
        assert 'python-version: "3.x"\n          allow-prereleases: true\n' in newest
        assert "run: bash scripts/check.sh\n" in newest


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize(
    ("result", "open_issue", "call"),
    [
        # A failure opens the issue, or brings the open one up to date.
        ("failure", "", "issue create --title The checks fail with the newest Python"),
        ("failure", "7", "issue edit 7 --body"),
        # The weekly run closes it once the checks pass again.
        ("success", "7", "issue close 7"),
        ("success", "", ""),
    ],
)
def test_a_failure_with_the_newest_python_keeps_an_issue_open(
    tmp_path: Path, result: str, open_issue: str, call: str
) -> None:
    # No pull request shows the check, so its warning needs a place of its own.
    newest = (ROOT / ".github/workflows/newest-python.yml").read_text(encoding="utf-8")
    report = job_of(newest, "report")
    assert condition_of(report) == (
        "!cancelled() && github.ref == 'refs/heads/main' && "
        "(needs.newest-python.result == 'failure' || github.event_name == 'schedule')"
    )
    # Only the job without the code of the project may write issues.
    assert "\n    permissions:\n      issues: write\n    steps:" in report
    assert newest.count("issues: write") == 1
    (tmp_path / "step.sh").write_text(
        script_of(newest, "Keep the issue of the newest Python current"),
        encoding="utf-8",
        newline="\n",
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(
        """#!/usr/bin/env bash
if [[ "$1 $2" == "issue list" ]]; then
  echo "$OPEN"
  exit 0
fi
echo "$*" >> calls
""",
        encoding="utf-8",
        newline="\n",
    )
    gh.chmod(0o755)
    (tmp_path / "calls").touch()
    assert BASH
    done = subprocess.run(
        [BASH, "-e", "step.sh"],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "RESULT": result,
            "OPEN": open_issue,
            "URL": "https://github.com/o/r/actions/runs/1",
        },
        capture_output=True,
        encoding="utf-8",
        check=False,
    )

    assert done.returncode == 0, done.stderr
    calls = (tmp_path / "calls").read_text(encoding="utf-8")
    if not call:
        assert calls == ""
        return
    assert calls.startswith(call), calls
    assert ("The latest failure: https://github.com/o/r/actions/runs/1" in calls) == (
        result == "failure"
    )


def run_the_search_for_the_website(
    tmp_path: Path, root: Path, event: str, pages: str, fork: bool
) -> tuple[str, str]:
    docs = (ROOT / ".github/workflows/docs.yml").read_text(encoding="utf-8")
    script = tmp_path / "step.sh"
    script.write_text(
        script_of(docs, "Look for the website"), encoding="utf-8", newline="\n"
    )
    # gh answers as GitHub Pages does: its build type, or 404 where it is off.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(
        """#!/usr/bin/env bash
if [[ "$*" != "api repos/o/r/pages --jq .build_type" || -z "$PAGES" ]]; then
  exit 1
fi
echo "$PAGES"
""",
        encoding="utf-8",
        newline="\n",
    )
    gh.chmod(0o755)
    output = tmp_path / "output"
    output.touch()
    environment = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "EVENT": event,
        "FORK": str(fork).lower(),
        "GITHUB_REF": "refs/heads/main" if event == "push" else "refs/pull/1/merge",
        "GITHUB_REPOSITORY": "o/r",
        "GITHUB_OUTPUT": str(output),
        "PAGES": pages,
    }
    assert BASH
    result = subprocess.run(
        [BASH, "-e", script.as_posix()],
        cwd=root,
        env=environment,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout, output.read_text(encoding="utf-8")


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize(
    ("project", "event", "pages", "fork", "output", "notice"),
    [
        # Every pull request builds the website as the check docs.
        ("generic", "pull_request", "workflow", False, "build=true\n", ""),
        # main publishes it where GitHub Pages publishes from a workflow.
        ("generic", "push", "workflow", False, "publish=true\n", ""),
        (
            "generic",
            "push",
            "",
            False,
            "build=true\n",
            "doesn't publish from GitHub Actions",
        ),
        # The blueprint's Dashboard publishes it with the dashboard; main only builds it.
        (
            "blueprint",
            "push",
            "workflow",
            False,
            "build=true\n",
            "dashboard.yml publishes",
        ),
        # A fork of the blueprint runs no Dashboard, so its Docs publishes the website.
        ("blueprint", "push", "workflow", True, "publish=true\n", ""),
        ("none", "push", "workflow", False, "", "No website here"),
    ],
)
def test_the_docs_workflow_publishes_the_website_unless_another_workflow_does(
    projects: dict[str, Path],
    tmp_path: Path,
    project: str,
    event: str,
    pages: str,
    fork: bool,
    output: str,
    notice: str,
) -> None:
    roots = {"blueprint": ROOT, "none": tmp_path}
    root = roots.get(project) or projects[project]

    printed, written = run_the_search_for_the_website(
        tmp_path, root, event, pages, fork
    )

    assert written == output
    assert (notice in printed) if notice else printed == ""


@pytest.mark.parametrize("kind", KINDS)
def test_every_project_records_its_decisions(
    projects: dict[str, Path], kind: str
) -> None:
    decisions = projects[kind] / "docs/decisions"
    index = (decisions / "README.md").read_text(encoding="utf-8")
    for record in sorted(decisions.glob("0*.md")):
        if record.name != "0000-template.md":
            assert f"]({record.name})" in index, record.name
    assert (decisions / "0000-template.md").is_file()


def test_the_coverage_bot_reads_every_report_of_the_checks() -> None:
    after = (ROOT / ".github/workflows/after-checks.yml").read_text(encoding="utf-8")
    bot = after[after.index("\n  coverage:\n") :]
    listed = re.search(
        r"contains\(fromJSON\('(\[.+?\])'\), github\.event\.workflow_run\.name\)", bot
    )
    assert listed
    watched = set(json.loads(listed[1]))
    for path in (ROOT / ".github/workflows").glob("ci-*.yml"):
        ci = path.read_text(encoding="utf-8")
        if "name: coverage\n" in ci:
            name = re.search(r"^name: (.+)$", ci, re.MULTILINE)
            assert name, path
            assert name[1] in watched, name[1]


def test_the_coverage_report_of_the_blueprint_names_every_file_by_its_path() -> None:
    # Each folder under source becomes a source of the report, relative to which it
    # names the files, such as cli.py for blueprint/cli.py; with several, the coverage
    # comment can't tell them apart. Packages and modules by name keep one, the root.
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    run = config["tool"]["coverage"]["run"]
    assert "source" not in run
    assert "blueprint" in run["source_pkgs"]


@pytest.mark.parametrize("kind", KINDS)
def test_every_project_has_a_website(projects: dict[str, Path], kind: str) -> None:
    project = projects[kind]
    config = (project / "mkdocs.yml").read_text(encoding="utf-8")

    for line in (
        'site_name: "Demo Project"',
        f'site_description: "A {kind} of the tests, with \\"quotes\\" and Ümlauts."',
        "site_url: https://dennis-otto.github.io/demo-project/",
        "repo_url: https://github.com/Dennis-Otto/demo-project",
        "INHERIT: .github/mkdocs-blueprint.yml",
        "  - Home: index.md",
        # German pages follow the pattern of the comments.
        "#   i18n:",
        "#     enabled: true",
    ):
        assert f"\n{line}\n" in config, line
    # What every website shares is the blueprint's, which it keeps current; plugins
    # and Markdown extensions are mappings, so that those of a project merge with them.
    base = (project / ".github/mkdocs-blueprint.yml").read_text(encoding="utf-8")
    assert base == (ROOT / ".github/mkdocs-blueprint.yml").read_text(encoding="utf-8")
    for line in (
        "edit_uri: edit/main/docs/",
        "  name: material",
        "    - navigation.tabs",
        "  search: {}",
        "  privacy: {}",
        # The cards need Cairo, which Windows lacks: only the CI, where GitHub's
        # runners set CI to true, makes them, and a preview builds without them.
        "  social:\n    enabled: !ENV [CI, false]",
        "  glightbox: {}",
        "  git-revision-date-localized:",
        "  - .github/mkdocs_blueprint.py",
        "    strict: false",
        "  admonition: {}",
    ):
        assert f"\n{line}\n" in base, line
    assert "\n  - " not in base.split("\nplugins:\n")[1].split("\n\n")[0]
    # The languages come before the dates, which fail the build otherwise, and are off
    # until a project names its own; instant loading would break the language switch.
    assert "\n  i18n:\n    enabled: false\n    docs_structure: suffix\n" in base
    assert base.index("\n  i18n:\n") < base.index("\n  git-revision-date-localized:\n")
    assert "navigation.instant" not in base
    assert "/.cache/" in (project / ".gitignore").read_text(encoding="utf-8").split(
        "\n"
    )
    assert (
        (project / "docs/index.md")
        .read_text(encoding="utf-8")
        .startswith("# Demo Project\n")
    )
    # The tools of the Docs workflow are the blueprint's, which it keeps current.
    tools = (project / ".github/docs-requirements.txt").read_text(encoding="utf-8")
    assert tools == (ROOT / "stacks/docs/requirements-docs.txt").read_text(
        encoding="utf-8"
    )
    assert "mkdocs-material==" in tools
    docs = workflows(project)["docs.yml"]
    assert "pip install --require-hashes -r .github/docs-requirements.txt" in docs
    assert "repo-blueprint" not in docs.replace(
        "https://github.com/Dennis-Otto/repo-blueprint", ""
    )
    # The Docs workflow publishes it; only the blueprint has another workflow for that,
    # its Dashboard.
    publishers = [
        name
        for name, text in workflows(project).items()
        if "uses: actions/deploy-pages@" in text
    ]
    assert publishers == ["docs.yml"]
    settings = tomllib.loads(
        (project / ".github/repository.toml").read_text(encoding="utf-8")
    )
    assert settings["pages"] == {"build_type": "workflow"}
    assert "docs" in settings["branch"]["required_checks"]
    # A link out of docs/ leads nowhere on the website; such links go to GitHub.
    pages = (project / "docs").resolve()
    for page in pages.rglob("*.md"):
        text = page.read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^)\s#]+)", text):
            if "://" not in target:
                assert (page.parent / target).resolve().is_relative_to(pages), target


def test_the_tools_of_the_website_install_on_windows() -> None:
    # The plugin for the dates requires tzdata on Windows alone. pip-compile on Linux
    # left it out of the lock, and with --require-hashes pip refused all of it there.
    wanted = (ROOT / "stacks/docs/requirements-docs.in").read_text(encoding="utf-8")
    assert "\ntzdata\n" in wanted
    lock = (ROOT / "stacks/docs/requirements-docs.txt").read_text(encoding="utf-8")
    assert re.search(
        r"^tzdata==\S+ \\\n(?:    --hash=sha256:[0-9a-f]{64} \\\n)*"
        r"    --hash=sha256:[0-9a-f]{64}\n",
        lock,
        re.MULTILINE,
    )


def website_step(check: str) -> str:
    start = check.index('step "Website"')
    return check[start : check.index("if [[ -f scripts/check-project.sh ]]", start)]


@pytest.mark.parametrize("kind", KINDS)
def test_the_checks_build_the_website(projects: dict[str, Path], kind: str) -> None:
    check = (projects[kind] / "scripts/check.sh").read_text(encoding="utf-8")
    generic = (projects["generic"] / "scripts/check.sh").read_text(encoding="utf-8")

    # After the checks of the stack and before those of the project alone, the same
    # in every kind of project.
    website = check.index('\nstep "Website"\n')
    assert check.rindex('\nstep "') == website
    assert website < check.index("if [[ -f scripts/check-project.sh ]]")
    assert website_step(check) == website_step(generic)
    contributing = (projects[kind] / "CONTRIBUTING.md").read_text(encoding="utf-8")
    # On Windows with the launcher of python.org, which every install has, and not
    # with python, which can be the stub of the Microsoft Store.
    assert (
        "On Windows, use `py -3` in place of `python3` and `.venv-docs/Scripts/` in"
        " place of `.venv-docs/bin/`"
    ) in contributing
    assert "`bash scripts/check.sh` builds the website strictly as well" in contributing


# A MkDocs that records how the step calls it, and whether the folder it builds into
# is a new one under TMPDIR, and that fails like a strict build with a broken link
# when FAIL is set.
FAKE_MKDOCS = """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "${NO_MKDOCS_2_WARNING:-}" "$@" > "$CALLS"
if [[ "$4" == "$TMPDIR"/* && -d "$4" ]]; then
  echo "a new folder" >> "$CALLS"
fi
echo "<h1>Demo</h1>" > "$4/index.html"
echo "INFO    -  Building documentation to directory: $4"
if [[ -n "${FAIL:-}" ]]; then
  echo "WARNING -  Doc file 'index.md' contains a link 'nowhere.md', but the target is not found."
  echo "Aborted with 1 warnings in strict mode!"
  exit 1
fi
"""


def run_the_website_step(
    projects: dict[str, Path],
    tmp_path: Path,
    mkdocs: str,
    pages: tuple[str, ...] = ("mkdocs.yml", "docs/index.md"),
    fail: bool = False,
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    """The step Website of scripts/check.sh, in a repository with these pages and a
    fake MkDocs at this place: in .venv-docs, in an activated environment (VIRTUAL_ENV
    and its folder), alone on the PATH, or nowhere ("")."""
    check = (projects["generic"] / "scripts/check.sh").read_text(encoding="utf-8")
    repository = tmp_path / "repository"
    (repository / "scripts").mkdir(parents=True)
    # Its set-up, such as set -euo pipefail and the folder it runs in, and the step.
    script = check[: check.index('step "Text files"')] + website_step(check)
    (repository / "scripts/website.sh").write_text(
        script, encoding="utf-8", newline="\n"
    )
    for page in pages:
        (repository / page).parent.mkdir(parents=True, exist_ok=True)
        (repository / page).write_text("# Demo\n", encoding="utf-8", newline="\n")
    # The PATH without a MkDocs of this computer.
    path = [
        entry
        for entry in os.environ.get("PATH", os.defpath).split(os.pathsep)
        if not shutil.which("mkdocs", path=entry)
    ]
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in {"NO_MKDOCS_2_WARNING", "FAIL", "VIRTUAL_ENV"}
    }
    if mkdocs:
        if mkdocs == "PATH":
            fake = tmp_path / "bin/mkdocs"
            path.insert(0, str(fake.parent))
        elif mkdocs.startswith("VIRTUAL_ENV/"):
            # As its activation leaves it, in bash or in PowerShell on Windows.
            fake = tmp_path / "environment" / mkdocs.removeprefix("VIRTUAL_ENV/")
            environment["VIRTUAL_ENV"] = str(tmp_path / "environment")
            path.insert(0, str(fake.parent))
        else:
            fake = repository / mkdocs
        fake.parent.mkdir(parents=True, exist_ok=True)
        fake.write_text(FAKE_MKDOCS, encoding="utf-8", newline="\n")
        fake.chmod(0o755)
    temporary = tmp_path / "tmp"
    temporary.mkdir()
    calls = tmp_path / "calls"
    environment.update(
        PATH=os.pathsep.join(path), TMPDIR=str(temporary), CALLS=str(calls)
    )
    if fail:
        environment["FAIL"] = "1"
    assert BASH
    result = subprocess.run(
        [BASH, "scripts/website.sh"],
        cwd=repository,
        env=environment,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    return result, calls, temporary


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize(
    "mkdocs",
    [
        # The tools of the preview, as CONTRIBUTING.md and the dev container set
        # them up on Linux and macOS, and on Windows.
        ".venv-docs/bin/mkdocs",
        ".venv-docs/Scripts/mkdocs.exe",
        # The tools of an activated environment.
        "VIRTUAL_ENV/bin/mkdocs",
        "VIRTUAL_ENV/Scripts/mkdocs.exe",
    ],
)
def test_the_website_step_builds_the_website_strictly(
    projects: dict[str, Path], tmp_path: Path, mkdocs: str
) -> None:
    result, calls, temporary = run_the_website_step(projects, tmp_path, mkdocs)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "The website builds strictly." in result.stdout
    # Its log only when the build fails.
    assert "INFO" not in result.stdout + result.stderr
    recorded = calls.read_text(encoding="utf-8").splitlines()
    assert recorded[:4] == ["true", "build", "--strict", "--site-dir"]
    assert recorded[5:] == ["a new folder"]
    # The website goes again: nothing is left in the temporary folder.
    assert list(temporary.iterdir()) == []


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
def test_the_website_step_shows_why_the_build_fails(
    projects: dict[str, Path], tmp_path: Path
) -> None:
    result, _, temporary = run_the_website_step(
        projects, tmp_path, ".venv-docs/bin/mkdocs", fail=True
    )

    assert result.returncode == 1
    assert "contains a link 'nowhere.md', but the target is not found" in result.stdout
    # Which MkDocs failed, and where to find how to install it again.
    assert (
        "The website fails to build strictly with .venv-docs/bin/mkdocs; the log above"
        " says why.\nTools that are out of date or incomplete install again as"
        " CONTRIBUTING.md shows.\n"
    ) in result.stdout
    assert "The website builds strictly." not in result.stdout
    assert list(temporary.iterdir()) == []


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize(
    ("mkdocs", "pages", "message"),
    [
        # Without the tools, as in the CI, whose check docs builds the website.
        (
            "",
            ("mkdocs.yml", "docs/index.md"),
            "MkDocs is not installed here; the CI builds the website.",
        ),
        # A MkDocs from elsewhere, such as Homebrew or pipx, has neither the theme nor
        # the plugins of the website, and would fail every check.
        (
            "PATH",
            ("mkdocs.yml", "docs/index.md"),
            "MkDocs is not installed here; the CI builds the website.",
        ),
        # Without a home page, as before the first page of a project without sample
        # code, or without mkdocs.yml: no website, as in the Docs workflow.
        (
            ".venv-docs/bin/mkdocs",
            ("mkdocs.yml",),
            "No website here: it needs mkdocs.yml and a home page, docs/index.md.",
        ),
        (
            ".venv-docs/bin/mkdocs",
            ("docs/index.md",),
            "No website here: it needs mkdocs.yml and a home page, docs/index.md.",
        ),
    ],
)
def test_the_website_step_passes_without_tools_or_website(
    projects: dict[str, Path],
    tmp_path: Path,
    mkdocs: str,
    pages: tuple[str, ...],
    message: str,
) -> None:
    result, calls, _ = run_the_website_step(projects, tmp_path, mkdocs, pages)

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == f"\n== Website\n{message}\n"
    assert not calls.exists()


@pytest.mark.parametrize("kind", KINDS)
def test_the_dev_container_sets_up_the_tools_of_the_website(
    projects: dict[str, Path], kind: str
) -> None:
    setup = (projects[kind] / ".devcontainer/setup.sh").read_text(encoding="utf-8")
    tools = setup[setup.index("if [[ -f mkdocs.yml ]]; then") :]

    assert "\n  python3 -m venv .venv-docs\n" in tools
    assert (
        "\n  .venv-docs/bin/pip install --require-hashes -r .github/docs-requirements.txt\n"
        in tools
    )
    # The images of the Python projects have Python; the others get its venv first.
    python = "python3-venv" not in tools
    assert python == (kind in {"home-assistant", "github-action", "python-package"})
    if not python:
        assert tools.index("sudo apt-get update") < tools.index("python3 -m venv")
    # Last, so that the hook of the checks is set up even when they fail to install.
    assert setup.index("git config core.hooksPath") < setup.index(".venv-docs")


def test_the_clean_up_bot_keeps_the_work_of_others() -> None:
    bot = (ROOT / ".github/workflows/cleanup.yml").read_text(encoding="utf-8")
    # Only a branch that main holds completely goes.
    assert bot.index('if [[ "$ahead" == 0 ]]; then') < bot.index("--method DELETE")
    for kept in ("release-please--*", "renovate/*", "dependabot/*"):
        assert kept in bot, kept


def test_a_release_is_built_in_isolation() -> None:
    workflows_dir = ROOT / ".github/workflows"
    release = (workflows_dir / "release.yml").read_text(encoding="utf-8")
    build = (workflows_dir / "build-release.yml").read_text(encoding="utf-8")
    assets = release[release.index("  assets:") : release.index("\n  publish:")]
    assert "uses: ./.github/workflows/build-release.yml" in assets
    # The build gets the tag, its commit and the version as inputs, nothing else of
    # the caller.
    assert "needs." not in build
    for name in ("tag", "sha", "version"):
        line = f"      {name}: ${{{{ needs.release-please.outputs.{name} }}}}\n"
        assert line in assets, name
    assert "workflow_call:" in build
    verify = (workflows_dir / "verify-release.yml").read_text(encoding="utf-8")
    assert 'build="$GH_REPO/.github/workflows/build-release.yml"' in verify
    # The build signs a Nextcloud app with the key of the environment release, which a
    # called workflow sees only with the secrets of its caller.
    assert "secrets: inherit" in assets
    assert "environment:\n      name: release" in build


def test_a_release_left_as_a_draft_is_finished_by_hand() -> None:
    release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    job = release[release.index("  release-please:") : release.index("\n  assets:")]
    step = job[
        job.index("id: resume") : job.index("- name: Write the text of Unreleased")
    ]
    assert "github.event_name == 'workflow_dispatch'" in step
    assert "--json isDraft" in step
    for output in ("created", "tag", "sha", "version", "major"):
        line = next(
            line for line in job.splitlines() if line.strip().startswith(f"{output}:")
        )
        assert "steps.resume.outputs." in line, output


def test_release_tags_are_signed_and_verified_with_one_gitsign() -> None:
    sign = (ROOT / ".github/sign-tag.sh").read_text(encoding="utf-8")
    verify = (ROOT / ".github/workflows/verify-release.yml").read_text(encoding="utf-8")
    version = re.search(r"^version=(\S+)$", sign, re.MULTILINE)
    digest = re.search(r"^sha256=([0-9a-f]{64})$", sign, re.MULTILINE)
    assert version
    assert digest
    assert f"GITSIGN_VERSION: {version[1]}" in verify
    assert f"GITSIGN_SHA256: {digest[1]}" in verify
    release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    job = release[release.index("  release-please:") : release.index("\n  assets:")]
    assert "id-token: write" in job
    # The signed tag is there before release-please creates the release on it.
    assert job.index('bash .github/sign-tag.sh "$tag" "$commit"') < job.index(
        "googleapis/release-please-action"
    )


def test_every_release_run_signs_the_tag_of_a_merged_release() -> None:
    release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    start = release.index("      - name: Sign the tag of a release")
    step = release[start : release.index("      - name:", start + 1)]
    # Not only the push of the merge, which can be lost: the next run, a schedule or a
    # dispatch, signs the tag before release-please creates the release on it.
    assert "        if: steps.app.outputs.token != ''\n" in step
    assert "event_name" not in step
    assert "head_commit" not in step
    # The merged release pull requests come from the list of pull requests, which
    # doesn't lag behind a merge as their search does.
    assert 'pullRequests(labels: ["autorelease: pending"], states: MERGED' in step
    assert "gh pr list" not in step
    # A tag that exists already must be the signed one at the commit of the merge,
    # which sign-tag.sh checks (tests/test_sign_tag.py).
    assert 'bash .github/sign-tag.sh "$tag" "$commit"' in step
    # release-please creates a release only on a tag that the step signed: never on a
    # tag of its own, without a signature, for a release pull request merged after the
    # step looked, or in a run without the release app.
    assert "        id: sign\n" in step
    assert '          echo "signed=true" >> "$GITHUB_OUTPUT"\n' in step
    please = release[release.index("        id: release\n") :]
    please = please[: please.index("      - name:")]
    assert "googleapis/release-please-action@" in please
    skip = "skip-github-release: ${{ steps.sign.outputs.signed != 'true' }}"
    assert f"          {skip}\n" in please


def test_the_build_checks_the_tag_before_it_builds() -> None:
    build = (ROOT / ".github/workflows/build-release.yml").read_text(encoding="utf-8")
    inputs = build[build.index("    inputs:") : build.index("permissions:")]
    assert (
        "      sha:\n"
        "        description: The commit that the tag has to point at\n"
        "        required: true\n"
    ) in inputs
    step = build[
        build.index("      - name: Verify the tag before building") : build.index(
            "actions/checkout@"
        )
    ]
    # The script of the commit that runs the workflow, not the one of the tag.
    assert "contents/.github/sign-tag.sh?ref=$GITHUB_SHA" in step
    assert 'bash "$RUNNER_TEMP/sign-tag.sh" verify "$TAG" "$SHA"' in step
    assert "SHA: ${{ inputs.sha }}" in step
    release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    # The release at the merge, a beta at the commit of the run, and a draft taken up
    # at the last commit that changed the version.
    outputs = ("release", "beta", "resume")
    line = " || ".join(f"steps.{step}.outputs.sha" for step in outputs)
    assert f"      sha: ${{{{ {line} }}}}\n" in release
    assert 'echo "sha=$GITHUB_SHA"\n' in release
    manifest = "commits?path=.release-please-manifest.json&sha=$GITHUB_SHA&per_page=1"
    assert manifest in release


def test_a_release_of_an_hourly_run_is_verified_in_full() -> None:
    # Called by the release workflow, verify-release.yml has the event of its run,
    # which may be the hourly schedule; only its own weekly run is lenient.
    verify = (ROOT / ".github/workflows/verify-release.yml").read_text(encoding="utf-8")
    weekly = "github.event_name == 'schedule' && inputs.tag == ''"
    assert f"          WEEKLY: ${{{{ {weekly} }}}}\n" in verify
    assert "GITHUB_EVENT_NAME" not in verify
    assert verify.count('[[ "$WEEKLY" == true ]]') == 4
    release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    job = release[release.index("\n  verify:") :]
    assert "uses: ./.github/workflows/verify-release.yml" in job
    assert "      tag: ${{ needs.release-please.outputs.tag }}" in job


@pytest.mark.parametrize("kind", KINDS)
def test_the_code_of_a_project_meets_mutants_every_week(
    projects: dict[str, Path], kind: str
) -> None:
    project = projects[kind]
    mutation = project / ".github/workflows/mutation.yml"
    tools = project / ".github/mutation-requirements.txt"
    if kind in ("home-assistant", "python-package", "github-action"):
        assert mutation.is_file()
        assert "mutmut==" in tools.read_text(encoding="utf-8")
    elif kind == "nextcloud-app":
        assert mutation.is_file()
        assert not tools.exists()
    else:
        assert not mutation.exists()


def mutation_step(name: str, kind: str) -> str:
    """The script of a step of the Mutation workflow for one kind of code."""
    workflow = (ROOT / ".github/workflows/mutation.yml").read_text(encoding="utf-8")
    step = re.search(
        rf"      - name: {re.escape(name)}\n        if: .*== '{kind}'\n"
        r"(?:        (?!run: \|).*\n)*        run: \|\n((?:          .*\n|\n)+)",
        workflow,
    )
    assert step, name
    return textwrap.dedent(step[1])


def run_mutation_step(
    tmp_path: Path, name: str, kind: str, tools: dict[str, str], **variables: str
) -> tuple[int, str]:
    """Runs a step of the Mutation workflow in tmp_path/project as GitHub does, with
    stand-ins for its tools; the exit code and what it wrote to the summary."""
    step = tmp_path / "step.sh"
    step.write_text(mutation_step(name, kind), encoding="utf-8", newline="\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for tool, script in tools.items():
        (bin_dir / tool).write_text(
            f"#!/usr/bin/env bash\n{script}", encoding="utf-8", newline="\n"
        )
        (bin_dir / tool).chmod(0o755)
    (tmp_path / "temp").mkdir(exist_ok=True)
    summary = tmp_path / "summary"
    summary.touch()
    environment = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "RUNNER_TEMP": (tmp_path / "temp").as_posix(),
        "GITHUB_ENV": (tmp_path / "env").as_posix(),
        "GITHUB_STEP_SUMMARY": summary.as_posix(),
        "MUTMUT_LIMIT": "1m",
        **variables,
    }
    # As GitHub runs a step: bash -e.
    assert BASH
    result = subprocess.run(
        [BASH, "-e", step.as_posix()],
        cwd=tmp_path / "project",
        env=environment,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    return result.returncode, summary.read_text(encoding="utf-8")


def mutmut_list(config: configparser.ConfigParser, key: str) -> list[str]:
    """A list of setup.cfg as mutmut 3 reads it: one item on each line, else the whole
    value as one item."""
    value = config.get("mutmut", key)
    return [item for item in value.split("\n") if item] if "\n" in value else [value]


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize(
    ("files", "paths"),
    [
        # The modules of the root and its packages, as in the blueprint, but not the
        # tests and not the settings tool in .github/.
        (
            [
                "blueprint/__init__.py",
                "blueprint.py",
                "dashboard.py",
                "weekly.py",
                "conftest.py",
                "tests/__init__.py",
                ".github/blueprint/__init__.py",
            ],
            ["blueprint", "blueprint.py", "dashboard.py", "weekly.py"],
        ),
        (["src/demo/__init__.py", "tests/test_demo.py"], ["src"]),
        (
            ["custom_components/demo/__init__.py", "tests/test_init.py"],
            ["custom_components"],
        ),
    ],
)
def test_mutmut_mutates_the_code_of_every_kind_of_project(
    tmp_path: Path, files: list[str], paths: list[str]
) -> None:
    project = tmp_path / "project"
    others = ["pyproject.toml", "docs/index.md", ".github/workflows/mutation.yml"]
    for name in [*files, *others, ".git/HEAD"]:
        (project / name).parent.mkdir(parents=True, exist_ok=True)
        (project / name).touch()
    calls = tmp_path / "calls"

    code, _ = run_mutation_step(
        tmp_path,
        "Run the mutants against the tests",
        "python",
        {"mutmut": 'echo "$*" >> "$CALLS"\n'},
        CALLS=calls.as_posix(),
    )

    assert code == 0
    config = configparser.ConfigParser()
    config.read(project / "setup.cfg", encoding="utf-8")
    # Not "blueprint,blueprint.py,dashboard.py,weekly.py": mutmut 3 takes that for one
    # path, which it doesn't find, and mutates nothing.
    assert mutmut_list(config, "source_paths") == paths
    # The tests may read any file of the repository; Git stays the checkout's own.
    copied = mutmut_list(config, "also_copy")
    assert {".github", "docs", "pyproject.toml", "tests"} <= set(copied)
    assert not {".git", "setup.cfg"} & set(copied)
    assert mutmut_list(config, "pytest_add_cli_args") == ["-m", "not mutation_unsafe"]
    assert calls.read_text(encoding="utf-8").startswith("run --max-children ")


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("setup.cfg", "[mutmut]\nsource_paths=lib\n"),
        ("pyproject.toml", '[tool.mutmut]\nsource_paths = ["lib"]\n'),
    ],
)
def test_mutmut_keeps_the_configuration_of_a_project(
    tmp_path: Path, name: str, text: str
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / name).write_text(text, encoding="utf-8")

    code, _ = run_mutation_step(
        tmp_path, "Run the mutants against the tests", "python", {"mutmut": "true\n"}
    )

    assert code == 0
    assert (project / name).read_text(encoding="utf-8") == text
    assert (project / "setup.cfg").exists() == (name == "setup.cfg")


MUTANTS = """\
    demo.x_add__mutmut_1: killed
    demo.x_add__mutmut_2: survived
    demo.x_add__mutmut_3: no tests
"""
# The output of mutmut, whose spinner redraws the line of each phase with \r.
STOPPED = (
    "⠋ Generating mutants\r⠙ Generating mutants\r⠇ Generating mutants\n"
    "    done in 597ms (0 files mutated, 0 ignored, 0 unmodified)\n"
    "⠋ Running stats\r⠹ Running stats\n"
    "Stopping early, because we could not find any test case for any mutant.\n"
)


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize(
    ("results", "status", "code", "expected"),
    [
        (
            MUTANTS,
            "0",
            0,
            "**50 %** of the mutants were noticed by a test: 1 killed, 1 survived, 1 other.\n",
        ),
        (MUTANTS, "124", 0, "The run stopped at its time limit"),
        # A configuration that mutates nothing, in the words of mutmut, with the
        # last state of each line.
        (
            "",
            "1",
            1,
            "```text\n⠇ Generating mutants\n    done in 597ms (0 files mutated,"
            " 0 ignored, 0 unmodified)\n⠹ Running stats\nStopping early,",
        ),
        # No error of mutmut, but nothing measured either.
        ("", "0", 1, "No mutant ran. The end of the output of mutmut:\n"),
    ],
)
def test_the_score_of_mutmut_or_why_it_has_none(
    tmp_path: Path, results: str, status: str, code: int, expected: str
) -> None:
    (tmp_path / "project").mkdir()
    (tmp_path / "temp").mkdir()
    (tmp_path / "temp/run.txt").write_text(STOPPED, encoding="utf-8", newline="\n")

    exit_code, summary = run_mutation_step(
        tmp_path,
        "Report the score and the surviving mutants",
        "python",
        {"mutmut": 'printf "%s" "$RESULTS"\n'},
        RESULTS=results,
        status=status,
    )

    assert exit_code == code
    assert summary.startswith("### Mutation tests (mutmut)\n")
    assert expected in summary
    assert "⠋" not in summary
    assert ("\n- demo.x_add__mutmut_2\n" in summary) == bool(results)


# The end of the output of Infection.
INFECTION = """\
40 mutations were generated:
      35 mutants were killed by Test Framework
       5 covered mutants were not detected

Metrics:
         Mutation Score Indicator (MSI): 87%
         Mutation Code Coverage: 100%
         Covered Code MSI: 87%
"""


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize("bootstrap", [True, False])
def test_infection_runs_with_the_bootstrap_of_the_tests(
    tmp_path: Path, bootstrap: bool
) -> None:
    project = tmp_path / "project"
    (project / "tests").mkdir(parents=True)
    if bootstrap:
        (project / "tests/bootstrap.php").touch()
    calls = tmp_path / "calls"

    code, _ = run_mutation_step(
        tmp_path,
        "Run the mutants against the tests",
        "php",
        {"php": 'echo "$*" > "$CALLS"\nprintf "%s" "$OUTPUT"\n'},
        CALLS=calls.as_posix(),
        OUTPUT=INFECTION,
    )

    assert code == 0
    config = json.loads((project / "infection.json5").read_text(encoding="utf-8"))
    # The classes of Nextcloud, which Infection loads with the code of the app.
    assert config.get("bootstrap") == ("tests/bootstrap.php" if bootstrap else None)
    assert config["source"] == {"directories": ["lib"]}
    assert config["logs"]["summary"] == "build/infection-summary.log"
    # The score of the output, which no log of Infection has, for the dashboard.
    output = (project / "build/infection-output.log").read_text(encoding="utf-8")
    assert "Covered Code MSI: 87%" in output
    call = calls.read_text(encoding="utf-8")
    # A low score fails nothing, whatever minimum the project's configuration sets.
    assert " --min-msi=0 --min-covered-msi=0 " in call
    # The plain text that the report and the dashboard read, without colors.
    assert " --no-ansi " in call


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
def test_an_error_of_infection_fails_the_run(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "infection.json5").write_text("{}\n", encoding="utf-8")
    failing = "echo 'This application requires a PHP version matching \"^8.3\".' >&2\nexit 1\n"

    code, _ = run_mutation_step(
        tmp_path, "Run the mutants against the tests", "php", {"php": failing}
    )

    # Not hidden by the tail of its output, which succeeds.
    assert code == 1
    output = (project / "build/infection-output.log").read_text(encoding="utf-8")
    assert "requires a PHP version" in output
    assert (project / "infection.json5").read_text(encoding="utf-8") == "{}\n"


# The end of the output of Infection when its configuration finds no code to change;
# it ends well with a minimum score of 0.
NO_MUTANTS = """\
0 mutations were generated:
       0 mutants were killed by Test Framework

Metrics:
         Mutation Score Indicator (MSI): 0%
         Mutation Code Coverage: 0%
         Covered Code MSI: 0%

No mutations were generated for the selected code. Set a minimum MSI score to make this outcome fail.
"""


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize(
    ("output", "code", "expected"),
    [
        (
            INFECTION,
            0,
            "- Mutation Score Indicator (MSI): 87%\n- Mutation Code Coverage: 100%\n"
            "- Covered Code MSI: 87%\n",
        ),
        # A run that measures nothing fails: an error of Infection, no mutant, or
        # no output at all, as when its installation failed.
        (
            'Class "OCP\\AppFramework\\App" not found\n',
            1,
            'Infection reported no score. The end of its output:\n\n```text\nClass "OCP',
        ),
        (
            NO_MUTANTS,
            1,
            "Infection reported no score. The end of its output:\n\n```text\n"
            "0 mutations were generated:\n",
        ),
        (
            None,
            1,
            "Infection reported no score. The end of its output:\n\n```text\n```\n",
        ),
        # A later Infection that names its score in other words.
        (
            INFECTION.replace("Covered Code MSI", "Score"),
            1,
            "Infection reported no score.",
        ),
    ],
)
def test_the_score_of_infection_or_why_it_has_none(
    tmp_path: Path, output: str | None, code: int, expected: str
) -> None:
    build = tmp_path / "project/build"
    build.mkdir(parents=True)
    if output is not None:
        (build / "infection-output.log").write_text(output, encoding="utf-8")
    (build / "infection-summary.log").write_text("Total: 40\n", encoding="utf-8")

    exit_code, summary = run_mutation_step(tmp_path, "Report the score", "php", {})

    assert exit_code == code
    assert summary.startswith("### Mutation tests (Infection)\n")
    assert expected in summary
    assert summary.endswith("```text\nTotal: 40\n```\n")


def test_infection_gets_a_php_that_it_runs_on() -> None:
    # Infection 0.35 needs PHP 8.3, newer than the oldest PHP of a Nextcloud app, on
    # which its checks run.
    workflow = (ROOT / ".github/workflows/mutation.yml").read_text(encoding="utf-8")
    assert "INFECTION_VERSION: 0.35." in workflow
    versions = re.findall(r'php-version: "(\d+)\.(\d+)"', workflow)
    assert versions
    assert all((int(major), int(minor)) >= (8, 3) for major, minor in versions)


def test_a_pull_request_that_changes_how_the_mutants_run_tries_them() -> None:
    workflow = (ROOT / ".github/workflows/mutation.yml").read_text(encoding="utf-8")
    events = workflow[workflow.index("\non:\n") : workflow.index("\npermissions:")]
    for path in (
        ".github/workflows/mutation.yml",
        ".github/mutation-requirements.txt",
        "stacks/mutation/requirements.txt",
    ):
        assert f"      - {path}\n" in events, path
    # mutmut for a quarter of an hour, every week for hours; it keeps the mutants it
    # reached. Infection reports at its end only.
    limit = re.search(r"\n      MUTMUT_LIMIT: \$\{\{ (.+) \}\}\n", workflow)
    assert limit
    assert limit[1] == "github.event_name == 'pull_request' && '15m' || '320m'"
    assert workflow.count('timeout "$MUTMUT_LIMIT" mutmut run ') == 1
    assert (
        "timeout-minutes: ${{ github.event_name == 'pull_request' && 30 || 350 }}"
        in workflow
    )


@pytest.mark.parametrize("kind", ["home-assistant", "github-action", "python-package"])
def test_a_test_can_stay_out_of_the_mutation_tests(
    projects: dict[str, Path], kind: str
) -> None:
    def marker(path: Path) -> list[str]:
        config = tomllib.loads(path.read_text(encoding="utf-8"))
        markers: list[str] = config["tool"]["pytest"]["ini_options"]["markers"]
        return [line for line in markers if line.startswith("mutation_unsafe: ")]

    assert marker(ROOT / "pyproject.toml")
    assert marker(projects[kind] / "pyproject.toml") == marker(ROOT / "pyproject.toml")
