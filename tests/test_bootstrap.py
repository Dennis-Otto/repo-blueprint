"""Tests of blueprint.py create against a simulated git and gh, and against a real git."""

from __future__ import annotations

import shlex
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from blueprint import bootstrap
from blueprint.bootstrap import CreateError, create

ANSWERS = """\
# Changes here will be overwritten by Copier; NEVER EDIT MANUALLY
_commit: v0.13.0
_src_path: gh:Dennis-Otto/repo-blueprint
description: A demo
owner: octo-org
project_name: Demo
project_slug: demo
"""
INIT = "git init --initial-branch=main"
ADD = "git add --all"
COMMIT = "git commit --signoff --message 'chore: start from the blueprint'"
GH = "gh repo create octo-org/demo --public --description 'A demo' --source . --remote origin --push"


class Shell:
    """git and gh as create runs them: each command answers as the test planned it,
    by default with success and no output, and every call is written down."""

    def __init__(self, answers: dict[str, tuple[int, str]] | None = None) -> None:
        self.answers = answers or {}
        self.calls: list[str] = []

    def __call__(
        self, arguments: Sequence[str], folder: Path
    ) -> subprocess.CompletedProcess[str]:
        command = shlex.join(arguments)
        self.calls.append(command)
        code, text = self.answers.get(command, (0, ""))
        return subprocess.CompletedProcess(
            list(arguments), code, "" if code else text, text if code else ""
        )


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / ".copier-answers.yml").write_text(ANSWERS, encoding="utf-8")
    return tmp_path


def a_repository(root: Path) -> None:
    """The folder is a Git repository already, as git init makes it."""
    (root / ".git").mkdir()


def test_a_new_copy_becomes_a_repository_on_main(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    shell = Shell()

    assert create(root, "A demo", run=shell) == "octo-org/demo"

    assert shell.calls == [INIT, ADD, COMMIT, GH]
    shown = capsys.readouterr().out
    assert shown.startswith("Creating octo-org/demo on GitHub, public:\n")
    assert f"  {COMMIT}\n" in shown
    assert shown.endswith(
        "Created https://github.com/octo-org/demo, with the branch main.\n"
    )


def test_a_private_repository(root: Path) -> None:
    shell = Shell()

    create(root, "A demo", private=True, run=shell)

    assert shell.calls[-1] == GH.replace("--public", "--private")


def test_a_dry_run_only_shows_the_commands(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    shell = Shell()

    assert create(root, "A demo", dry_run=True, run=shell) is None

    assert shell.calls == []
    assert capsys.readouterr().out == "\n".join(
        [
            "create would make octo-org/demo on GitHub, public, with:",
            f"  {INIT}",
            f"  {ADD}",
            f"  {COMMIT}",
            f"  {GH}",
            "  python3 .github/blueprint.py settings apply",
            "  python3 .github/blueprint.py checklist",
            "Run it without --dry-run to do it.\n",
        ]
    )


def test_a_folder_that_pushes_to_a_remote_is_refused(root: Path) -> None:
    a_repository(root)
    shell = Shell({"git remote": (0, "origin\nupstream\n")})

    with pytest.raises(
        CreateError, match="pushes to origin, upstream already"
    ) as error:
        create(root, "A demo", run=shell)

    assert "python3 .github/blueprint.py settings apply" in str(error.value)
    assert shell.calls == ["git remote"]


def test_a_repository_of_git_init_moves_to_main(root: Path) -> None:
    a_repository(root)
    shell = Shell(
        {
            "git symbolic-ref --short HEAD": (0, "master\n"),
            "git rev-parse --verify --quiet HEAD": (1, ""),
        }
    )

    create(root, "A demo", run=shell)

    assert shell.calls == [
        "git remote",
        "git symbolic-ref --short HEAD",
        "git rev-parse --verify --quiet HEAD",
        "git branch --move main",
        ADD,
        COMMIT,
        GH,
    ]


def test_a_repository_with_its_first_commit_is_pushed_as_it_is(root: Path) -> None:
    a_repository(root)
    shell = Shell({"git symbolic-ref --short HEAD": (0, "main\n")})

    create(root, "A demo", run=shell)

    assert shell.calls == [
        "git remote",
        "git symbolic-ref --short HEAD",
        "git rev-parse --verify --quiet HEAD",
        "git status --porcelain",
        GH,
    ]


def test_changes_that_no_commit_holds_are_refused(root: Path) -> None:
    a_repository(root)
    shell = Shell(
        {
            "git symbolic-ref --short HEAD": (0, "main\n"),
            "git status --porcelain": (0, " M README.md\n"),
        }
    )

    with pytest.raises(CreateError, match="changes that no commit holds"):
        create(root, "A demo", run=shell)

    assert GH not in shell.calls


def test_a_command_that_fails_stops_create_with_its_message(root: Path) -> None:
    shell = Shell({COMMIT: (128, "Author identity unknown\n")})

    with pytest.raises(CreateError) as error:
        create(root, "A demo", run=shell)

    assert str(error.value) == f"{COMMIT} failed: Author identity unknown"
    assert shell.calls == [INIT, ADD, COMMIT]


def test_a_tool_that_is_not_installed_is_named(root: Path) -> None:
    def missing(
        arguments: Sequence[str], folder: Path
    ) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(arguments[0])

    with pytest.raises(CreateError, match=r"^git is not installed; create needs Git"):
        create(root, "A demo", run=missing)


def test_the_repository_named_by_the_option_wins(root: Path) -> None:
    (root / ".copier-answers.yml").unlink()
    shell = Shell()

    assert create(root, "A demo", repo="other/name", run=shell) == "other/name"

    assert shell.calls[-1].startswith("gh repo create other/name --public")


@pytest.mark.parametrize("answers", [None, "owner: octo-org\n"])
def test_without_the_answers_of_copier_create_asks_for_the_repository(
    root: Path, answers: str | None
) -> None:
    path = root / ".copier-answers.yml"
    if answers is None:
        path.unlink()
    else:
        path.write_text(answers, encoding="utf-8")

    with pytest.raises(CreateError, match="--repo OWNER/NAME"):
        create(root, "A demo", run=Shell())


def test_a_repository_without_its_owner_is_refused(root: Path) -> None:
    with pytest.raises(CreateError, match="no OWNER/NAME"):
        create(root, "A demo", repo="demo", run=Shell())


def test_the_answers_of_a_windows_checkout_are_read(root: Path) -> None:
    (root / ".copier-answers.yml").write_bytes(ANSWERS.replace("\n", "\r\n").encode())

    assert bootstrap.answered_repo(root) == "octo-org/demo"


@pytest.fixture
def plain_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Git without the configuration of the machine, which may sign every commit or
    name another first branch."""
    config = tmp_path / "gitconfig"
    config.write_text("[init]\n\tdefaultBranch = master\n", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "Test")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "test@example.com")


@pytest.mark.usefixtures("plain_git")
def test_the_first_commit_is_signed_off_on_main_with_every_file(
    tmp_path: Path,
) -> None:
    root = tmp_path / "demo"
    (root / "docs").mkdir(parents=True)
    (root / ".copier-answers.yml").write_text(ANSWERS, encoding="utf-8")
    (root / "docs/index.md").write_text("# Demo\n", encoding="utf-8")
    pushed: list[str] = []

    def git_and_simulated_gh(
        arguments: Sequence[str], folder: Path
    ) -> subprocess.CompletedProcess[str]:
        if arguments[0] == "gh":
            pushed.append(shlex.join(arguments))
            return subprocess.CompletedProcess(list(arguments), 0, "", "")
        return bootstrap.run_command(arguments, folder)

    create(root, "A demo", run=git_and_simulated_gh)

    def git(*arguments: str) -> str:
        return bootstrap.run_command(["git", *arguments], root).stdout.strip()

    assert pushed == [GH]
    # Main, although the configuration of Git names master as the first branch.
    assert git("symbolic-ref", "--short", "HEAD") == "main"
    assert git("log", "--format=%B") == (
        "chore: start from the blueprint\n\nSigned-off-by: Test <test@example.com>"
    )
    assert git("ls-files").split() == [".copier-answers.yml", "docs/index.md"]
    # Once committed, create would push it as it is.
    assert git("status", "--porcelain") == ""
