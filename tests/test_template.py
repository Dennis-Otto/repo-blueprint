"""Tests of the template: every kind of project renders completely and consistently."""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
import warnings
from pathlib import Path

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


def render(destination: Path, **data: str) -> Path:
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
        assert text == source


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
        "pyproject.toml",
        "release-please-config.json",
        "scripts/check.sh",
        ".github/CODEOWNERS",
        ".github/FUNDING.yml",
        ".github/findings.toml",
        ".github/pull_request_template.md",
        ".github/ISSUE_TEMPLATE/config.yml",
        ".github/ISSUE_TEMPLATE/feature_request.yml",
        ".github/social-preview/Dockerfile",
        ".github/actionlint.yaml",
        ".github/egress-firewall.yaml",
        ".github/dependency-review.yml",
    ):
        assert (ROOT / name).read_text(encoding="utf-8") == (project / name).read_text(
            encoding="utf-8"
        ), name
