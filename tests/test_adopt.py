"""Tests of blueprint.py adopt against a simulated git and gh."""

from __future__ import annotations

import json
import shlex
import subprocess
import tomllib
from collections.abc import Sequence
from pathlib import Path

import pytest
from preflight import NOT_FOUND
from shared import ROOT, without_the_version

from blueprint import adopt as adopt_module
from blueprint import cli
from blueprint.adopt import LABELS, AdoptError, adopt

REPO = "octo-org/demo"
PYTHON = (3, 13)
ANSWERS = "_commit: v1.18.2\nowner: octo-org\nproject_slug: demo\n"
CHANGELOG = "# Changelog\n\nWhat changed.\n\n## 1.2.3 - 2026-01-01\n\n- Things\n"
LABELS_TOML = (
    "# The labels of the project.\n\n"
    '[[label]]\nname = "bug"\ncolor = "d73a4a"\ndescription = "Broken"\n'
    'group = "type"\n\n'
    # GitHub ignores the case of a name: the project has the label dependencies.
    '[[label]]\nname = "Dependencies"\ncolor = "0366d6"\ndescription = "Updates"\n'
    'group = "release"\n'
)
RELEASE = json.dumps({"tag_name": "v1.2.3", "name": "1.2.3"})
ASKED = [
    "git --version",
    "git remote get-url origin",
    "gh --version",
    f"gh api repos/{REPO}",
    f"gh api repos/{REPO}/releases/latest",
]
SHOWN = [
    f"The preflight of adopt for {REPO}:",
    "  ✔ Python 3.13",
    "  ✔ Git 2.47.1",
    f"  ✔ origin pushes to {REPO}",
    "  ✔ GitHub CLI 2.62.0",
    f"  ✔ {REPO} is on GitHub",
    f"  ✔ the latest release of {REPO} is v1.2.3",
]
NEXT = [
    "What is left, as the guide says "
    "(https://dennis-otto.github.io/repo-blueprint/guide.html#an-existing-repository):",
    "  - Keep or remove each workflow above; put the checks of the project alone "
    "into .github/repository.project.toml and scripts/check-project.sh.",
    "  - Look at the diff, commit it with a sign-off and open the pull request.",
    "  - Once its new checks pass, run python3 .github/blueprint.py settings apply, "
    "and remove a classic branch protection of main that it names.",
]


class Shell:
    """git and gh as adopt runs them: by default an existing repository with the
    release v1.2.3, and every call is written down."""

    def __init__(self, answers: dict[str, tuple[int, str]] | None = None) -> None:
        self.answers: dict[str, tuple[int, str]] = {
            "git --version": (0, "git version 2.47.1\n"),
            "git remote get-url origin": (0, f"https://github.com/{REPO}.git\n"),
            "gh --version": (0, "gh version 2.62.0 (2024-11-14)\n"),
            f"gh api repos/{REPO}": (0, json.dumps({"full_name": REPO})),
            f"gh api repos/{REPO}/releases/latest": (0, RELEASE),
            **(answers or {}),
        }
        self.calls: list[str] = []

    def __call__(
        self, arguments: Sequence[str], folder: Path
    ) -> subprocess.CompletedProcess[str]:
        command = shlex.join(without_the_version(arguments))
        self.calls.append(command)
        if command not in self.answers:
            raise FileNotFoundError(arguments[0])
        code, text = self.answers[command]
        return subprocess.CompletedProcess(
            list(arguments), code, "" if code else text, text if code else ""
        )


def write(root: Path, path: str, text: str) -> None:
    (root / path).parent.mkdir(parents=True, exist_ok=True)
    (root / path).write_text(text, encoding="utf-8")


def read(root: Path, path: str) -> str:
    return (root / path).read_text(encoding="utf-8")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """An existing repository after copier copy: the files of the blueprint with the
    version 0.0.0 of a new one, and the changelog, the labels and a workflow of the
    project."""
    write(tmp_path, ".copier-answers.yml", ANSWERS)
    write(
        tmp_path,
        "release-please-config.json",
        json.dumps({"packages": {".": {"release-type": "simple"}}}),
    )
    write(tmp_path, ".release-please-manifest.json", '{\n  ".": "0.0.0"\n}\n')
    write(tmp_path, "version.txt", "0.0.0\n")
    write(tmp_path, "CHANGELOG.md", CHANGELOG)
    write(tmp_path, ".github/labels.toml", LABELS_TOML)
    write(
        tmp_path, ".github/blueprint/owned.txt", "# owned\n.github/workflows/ci.yml\n"
    )
    write(tmp_path, ".github/workflows/ci.yml", "name: CI\n")
    write(tmp_path, ".github/workflows/e2e.yaml", "name: E2E\n")
    write(tmp_path, ".github/workflows/README.md", "Not a workflow.\n")
    return tmp_path


def test_adopt_writes_what_an_existing_repository_lacks(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    shell = Shell()

    assert adopt(root, run=shell, python=PYTHON)

    # The preflight only asks.
    assert shell.calls == ASKED
    added = [label["name"] for label in LABELS if label["name"] != "dependencies"]
    assert capsys.readouterr().out == "\n".join(
        [
            *SHOWN,
            "adopt writes:",
            "  .release-please-manifest.json: the version 1.2.3",
            "  version.txt: the version 1.2.3",
            "  CHANGELOG.md: the heading ## Unreleased",
            f"  .github/labels.toml: the labels of the bots {', '.join(added)}",
            "Workflows that the blueprint doesn't bring, to keep or to remove:",
            "  .github/workflows/e2e.yaml",
            *NEXT,
            "",
        ]
    )
    assert read(root, ".release-please-manifest.json") == '{\n  ".": "1.2.3"\n}\n'
    assert read(root, "version.txt") == "1.2.3\n"
    assert read(root, "CHANGELOG.md") == (
        "# Changelog\n\nWhat changed.\n\n## Unreleased\n\n## 1.2.3 - 2026-01-01\n\n"
        "- Things\n"
    )
    labels = read(root, ".github/labels.toml")
    assert labels.startswith(LABELS_TOML + "\n# The labels of the bots")
    parsed = tomllib.loads(labels)["label"]
    assert [label["name"] for label in parsed] == ["bug", "Dependencies", *added]
    assert parsed[2:] == [label for label in LABELS if label["name"] in added]

    # A second run finds nothing more to write.
    assert adopt(root, run=shell, python=PYTHON)
    shown = capsys.readouterr().out
    assert (
        "Nothing is missing: the version, the changelog and the labels are there.\n"
        in shown
    )
    assert "writes" not in shown


def test_the_labels_are_those_of_the_template() -> None:
    # The template has no condition in it, so TOML reads it as it is.
    template = tomllib.loads(
        (ROOT / "template/.github/labels.toml.jinja").read_text(encoding="utf-8")
    )["label"]
    of_the_bots = [
        label
        for label in template
        if label["group"] == "release"
        or label["name"] in ("maintenance", "no-bot-fixes")
    ]
    assert of_the_bots == list(LABELS)


def test_a_package_keeps_its_version_in_the_manifest_alone(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(
        root,
        "release-please-config.json",
        json.dumps({"packages": {".": {"release-type": "python"}}}),
    )
    (root / "version.txt").unlink()
    # Every workflow is one of the blueprint.
    (root / ".github/workflows/e2e.yaml").unlink()

    assert adopt(root, run=Shell(), python=PYTHON)

    shown = capsys.readouterr().out
    assert "  .release-please-manifest.json: the version 1.2.3\n" in shown
    assert "Workflows that" not in shown
    assert not (root / "version.txt").exists()


def test_a_dry_run_writes_nothing(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}

    assert adopt(root, dry_run=True, run=Shell(), python=PYTHON)

    shown = capsys.readouterr().out
    assert "adopt would write:\n  .release-please-manifest.json" in shown
    assert shown.endswith(
        "  .github/workflows/e2e.yaml\nRun it without --dry-run to write them.\n"
    )
    assert {path: path.read_bytes() for path in root.rglob("*") if path.is_file()} == (
        before
    )

    # With nothing to write, a dry run says only that.
    adopt(root, run=Shell(), python=PYTHON)
    capsys.readouterr()
    assert adopt(root, dry_run=True, run=Shell(), python=PYTHON)
    assert "Run it without" not in capsys.readouterr().out


def test_a_version_given_needs_no_release_on_github(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    shell = Shell()

    assert adopt(root, version="2.0.0-beta.1", run=shell, python=PYTHON)

    assert shell.calls == ASKED[:-1]
    shown = capsys.readouterr().out
    assert "  ✔ the version of the latest release is 2.0.0-beta.1\n" in shown
    assert read(root, "version.txt") == "2.0.0-beta.1\n"

    with pytest.raises(AdoptError, match=r"v2 is no version such as 1.2.3"):
        adopt(root, version="v2", run=shell, python=PYTHON)


@pytest.mark.parametrize(
    ("tag", "version"),
    [("1.4.0", "1.4.0"), ("demo-v0.9.1", "0.9.1"), ("v3.0.0-rc.2", "3.0.0-rc.2")],
)
def test_the_version_is_the_end_of_the_tag(root: Path, tag: str, version: str) -> None:
    answer = {
        f"gh api repos/{REPO}/releases/latest": (0, json.dumps({"tag_name": tag}))
    }

    assert adopt(root, run=Shell(answer), python=PYTHON)

    assert read(root, "version.txt") == f"{version}\n"


def test_a_repository_without_a_release_stays_at_0_0_0(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    answer = {f"gh api repos/{REPO}/releases/latest": (1, NOT_FOUND)}

    assert adopt(root, run=Shell(answer), python=PYTHON)

    shown = capsys.readouterr().out
    assert (
        f"  ✔ {REPO} has no release yet: the version stays 0.0.0, and the first "
        "release of the release bot is 0.1.0\n"
    ) in shown
    assert ".release-please-manifest.json:" not in shown
    assert read(root, "version.txt") == "0.0.0\n"


@pytest.mark.parametrize(
    ("answers", "shown"),
    [
        (
            {
                f"gh api repos/{REPO}/releases/latest": (
                    0,
                    json.dumps({"tag_name": "x"}),
                )
            },
            [
                f"  ✘ the latest release of {REPO} has the tag x, which names no "
                "version",
                "      name it: python3 .github/blueprint.py adopt --version X.Y.Z",
            ],
        ),
        (
            {
                f"gh api repos/{REPO}/releases/latest": (
                    1,
                    "gh: Server Error (HTTP 500)",
                )
            },
            [
                f"  ✘ GitHub didn't say which release of {REPO} is the latest: gh: "
                "Server Error (HTTP 500)",
                "      name it: python3 .github/blueprint.py adopt --version X.Y.Z",
            ],
        ),
        (
            {f"gh api repos/{REPO}": (1, NOT_FOUND)},
            [
                f"  ✘ GitHub has no repository {REPO}: adopt completes one that exists",
                "      for a new repository: python3 .github/blueprint.py create",
            ],
        ),
        (
            {
                f"gh api repos/{REPO}": (
                    1,
                    "To get started with GitHub CLI, run: gh auth login",
                )
            },
            [
                "  ✘ gh is not signed in to github.com",
                "      gh auth login --hostname github.com",
            ],
        ),
        (
            {"git remote get-url origin": (2, "error: No such remote 'origin'")},
            [
                "  ✘ this folder has no origin, and adopt completes a repository on "
                "GitHub",
                f"      git remote add origin https://github.com/{REPO}.git",
            ],
        ),
        (
            {"git remote get-url origin": (0, "git@github.com:octo-org/other.git\n")},
            [
                f"  ✘ origin pushes to octo-org/other, and the answers name {REPO}",
                "      name the repository: python3 .github/blueprint.py --repo "
                "octo-org/other adopt",
            ],
        ),
        (
            {"git remote get-url origin": (0, "https://example.com/demo.git\n")},
            [
                f"  ✘ origin pushes to https://example.com/demo.git, and the answers name {REPO}"
            ],
        ),
    ],
)
def test_the_preflight_stops_adopt_before_it_writes(
    root: Path,
    answers: dict[str, tuple[int, str]],
    shown: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    before = read(root, "version.txt")

    assert not adopt(root, run=Shell(answers), python=PYTHON)

    out = capsys.readouterr().out
    assert "\n".join(shown) in out
    assert out.endswith(
        "Fix what is marked with ✘, then run python3 .github/blueprint.py adopt "
        "again; it wrote nothing.\n"
    )
    assert read(root, "version.txt") == before


def test_a_missing_tool_stops_adopt(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    shell = Shell()
    del shell.answers["git --version"]
    del shell.answers["gh --version"]

    assert not adopt(root, run=shell, python=(3, 11))

    assert shell.calls == ["git --version", "gh --version"]
    out = capsys.readouterr().out
    assert "  ✘ Python 3.11: the tools of the new repository need Python 3.12" in out
    assert "  ✘ Git is not installed\n" in out
    assert (
        "  ✘ GitHub CLI is not installed\n"
        "      install GitHub CLI: https://github.com/cli/cli#installation\n"
    ) in out


def test_a_repository_that_github_doesnt_answer_for_still_asks_for_its_release(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    answer = {f"gh api repos/{REPO}": (1, "gh: Bad Gateway (HTTP 502)")}

    assert adopt(root, run=Shell(answer), python=PYTHON)

    assert (
        f"  · GitHub didn't say whether it has {REPO}: gh: Bad Gateway (HTTP 502)\n"
        f"  ✔ the latest release of {REPO} is v1.2.3\n"
    ) in capsys.readouterr().out


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (None, "# Changelog\n\n## Unreleased\n"),
        (
            "# Changelog\n\nNothing yet.\n\n",
            "# Changelog\n\nNothing yet.\n\n## Unreleased\n",
        ),
        ("# Changelog\n\n## [Unreleased]\n\n- A fix\n", None),
    ],
)
def test_the_changelog_gets_its_heading_unreleased(
    root: Path, before: str | None, after: str | None
) -> None:
    if before is None:
        (root / "CHANGELOG.md").unlink()
    else:
        write(root, "CHANGELOG.md", before)

    assert adopt(root, run=Shell(), python=PYTHON)

    assert read(root, "CHANGELOG.md") == (after or before)


@pytest.mark.parametrize("before", [None, "\n"])
def test_a_repository_without_labels_gets_those_of_the_bots(
    root: Path, before: str | None
) -> None:
    if before is None:
        (root / ".github/labels.toml").unlink()
    else:
        write(root, ".github/labels.toml", before)

    assert adopt(root, run=Shell(), python=PYTHON)

    text = read(root, ".github/labels.toml")
    assert text.startswith("# Every label of the repository.")
    assert tomllib.loads(text)["label"] == list(LABELS)


@pytest.mark.parametrize(
    ("path", "text", "message"),
    [
        (".github/labels.toml", "[[label]\n", r"\.github/labels\.toml is no TOML"),
        ("release-please-config.json", "{}", "names no release-type"),
        ("release-please-config.json", "[", "names no release-type"),
    ],
)
def test_a_file_that_adopt_cant_read_is_named(
    root: Path, path: str, text: str, message: str
) -> None:
    write(root, path, text)

    with pytest.raises(AdoptError, match=message):
        adopt(root, run=Shell(), python=PYTHON)


def test_adopt_needs_the_files_of_copier_copy(root: Path) -> None:
    (root / ".github/blueprint/owned.txt").unlink()

    with pytest.raises(AdoptError, match=r"owned\.txt is missing: run copier copy"):
        adopt(root, run=Shell(), python=PYTHON)

    (root / "release-please-config.json").unlink()
    write(root, ".github/blueprint/owned.txt", "")
    (root / ".github/workflows/ci.yml").unlink()
    (root / ".github/workflows/e2e.yaml").unlink()
    (root / ".github/workflows/README.md").unlink()
    (root / ".github/workflows").rmdir()
    with pytest.raises(AdoptError, match=r"release-please-config.json names no"):
        adopt(root, run=Shell(), python=PYTHON)


def test_the_command_line_runs_adopt(
    root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    shell = Shell()
    monkeypatch.setattr(adopt_module, "run_command", shell)

    assert cli.main(["adopt", "--dry-run"], root=root) == 0
    assert "adopt would write:" in capsys.readouterr().out

    shell.answers[f"gh api repos/{REPO}"] = (1, NOT_FOUND)
    assert cli.main(["adopt"], root=root) == 1

    assert cli.main(["adopt", "--version", "one"], root=root) == 2
    assert capsys.readouterr().err == "blueprint.py: one is no version such as 1.2.3\n"

    (root / ".copier-answers.yml").unlink()
    assert cli.main(["adopt"], root=root) == 2
    assert capsys.readouterr().err.startswith(
        "blueprint.py: .copier-answers.yml names no owner and project_slug"
    )
    # Named on the command line, the repository needs no answers.
    shell.answers[f"gh api repos/{REPO}"] = (0, "{}")
    assert cli.main(["--repo", REPO, "adopt"], root=root) == 0
