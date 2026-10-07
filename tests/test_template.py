"""Tests of the template: every kind of project renders completely and consistently."""

from __future__ import annotations

import hashlib
import json
import re
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
        ".github/CODEOWNERS",
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
        ".github/renovate-blueprint.json5",
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
    copy = (projects[kind] / ".github/blueprint.py").read_text(encoding="utf-8")

    assert copy == (ROOT / "blueprint.py").read_text(encoding="utf-8")


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
        "screenshots",
        # LICENSE carries the license text; LICENSES/ serves REUSE in the repository.
        "LICENSES",
    ):
        assert f"/{path}" in ignored, path
    config = json.loads(
        (project / "release-please-config.json").read_text(encoding="utf-8")
    )["packages"]["."]
    # Lines of info.xml with the version elsewhere, such as screenshots at a tag.
    assert {"type": "generic", "path": "appinfo/info.xml"} in config["extra-files"]
    review = (project / ".github/dependency-review.yml").read_text(encoding="utf-8")
    assert "pkg:composer/netresearch/jsonmapper" in review


def test_the_ci_builds_with_the_krankerl_of_the_release() -> None:
    pins = [
        dict(
            re.findall(
                r"(KRANKERL_(?:VERSION|SHA256)): (\S+)",
                (ROOT / ".github/workflows" / name).read_text(encoding="utf-8"),
            )
        )
        for name in ("ci-php.yml", "release.yml")
    ]
    assert len(pins[0]) == 2
    assert pins[0] == pins[1]


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
        "issue_assistant.py",
        "Dockerfile",
        "img/app.svg",
        "tests/test_demo.py",
        "custom_components/demo/__init__.py",
        ".github/labels.toml",
    ):
        assert matcher.match_file(owned), owned
    for updated in (
        ".github/blueprint.py",
        ".devcontainer/Dockerfile",
        ".github/social-preview/Dockerfile",
        ".github/workflows/ci.yml",
        "docs/README.md",
        "scripts/check.sh",
    ):
        assert not matcher.match_file(updated), updated


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
        "src",
        "lib",
        "custom_components",
        "action.yml",
        "demo.py",
    ):
        assert not (project / sample).exists(), sample
    assert (project / "scripts/check.sh").exists()
    assert (project / ".github/workflows/ci.yml").exists()
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
