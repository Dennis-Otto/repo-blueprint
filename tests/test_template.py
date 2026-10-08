"""Tests of the template: every kind of project renders completely and consistently."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tomllib
import warnings
from pathlib import Path

import pathspec
import pytest
from copier import run_copy

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
# it and every file of its package.
TOOL = sorted(
    [
        "blueprint.py",
        *(
            f"blueprint/{path.name}"
            for path in (ROOT / "blueprint").iterdir()
            if path.is_file()
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
        assert text == source, name


@pytest.mark.parametrize("kind", KINDS)
def test_every_action_is_pinned_to_a_commit(
    projects: dict[str, Path], kind: str
) -> None:
    for name, text in workflows(projects[kind]).items():
        for line in re.findall(r"uses: \S+", text):
            assert PINNED.match(line), f"{name}: {line}"


@pytest.mark.parametrize("kind", KINDS)
def test_the_required_checks_exist(projects: dict[str, Path], kind: str) -> None:
    project = projects[kind]
    settings = tomllib.loads(
        (project / ".github/repository.toml").read_text(encoding="utf-8")
    )
    names = set()
    for text in workflows(project).values():
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
        assert (ROOT / name).read_text(encoding="utf-8") == (project / name).read_text(
            encoding="utf-8"
        ), name


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
    requirements = {
        "home-assistant": "requirements-test.txt",
        "python-package": "requirements-dev.txt",
        "github-action": "requirements-dev.txt",
    }
    if kind in requirements:
        assert f"-r {requirements[kind]}" in setup
        assert (project / requirements[kind]).exists()
        assert "charliermarsh.ruff" in config["customizations"]["vscode"]["extensions"]


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
    ):
        assert setting in rules, setting
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


def test_the_branch_bot_leaves_the_branches_of_renovate_alone() -> None:
    text = (ROOT / ".github/workflows/update-branches.yml").read_text(encoding="utf-8")
    assert 'startswith("renovate/") | not' in text


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


def test_the_flaky_test_bot_watches_every_test_workflow() -> None:
    flaky = (ROOT / ".github/workflows/flaky.yml").read_text(encoding="utf-8")
    watched = set(re.findall(r"^      - (.+)$", flaky, re.MULTILINE))
    names = set()
    for path in (ROOT / ".github/workflows").glob("ci-*.yml"):
        name = re.search(r"^name: (.+)$", path.read_text(encoding="utf-8"), re.M)
        assert name, path
        names.add(name[1])
    assert names
    assert names <= watched, names - watched
    assert "github.event.workflow_run.run_attempt == 1" in flaky


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
    bot = (ROOT / ".github/workflows/coverage.yml").read_text(encoding="utf-8")
    watched = set(re.findall(r"^      - (CI .+)$", bot, re.MULTILINE))
    for path in (ROOT / ".github/workflows").glob("ci-*.yml"):
        ci = path.read_text(encoding="utf-8")
        if "name: coverage\n" in ci:
            name = re.search(r"^name: (.+)$", ci, re.MULTILINE)
            assert name, path
            assert name[1] in watched, name[1]


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
        "  social: {}",
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
    # Only the blueprint leaves the publishing to its Dashboard workflow.
    assert "repo-blueprint" not in docs.replace(
        "https://github.com/Dennis-Otto/repo-blueprint", ""
    )
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
    # The build gets the tag and version as inputs, nothing else of the caller.
    assert "needs." not in build
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
    for output in ("created", "tag", "version", "major"):
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
    assert job.index('bash .github/sign-tag.sh "$tag"') < job.index(
        "googleapis/release-please-action"
    )


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
