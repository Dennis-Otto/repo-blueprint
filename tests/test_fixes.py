"""Tests of the fix bot: the commands of autofix that fix what a check found, the files
that they keep for the bot, and what the bot does with them after the checks, against
a simulated GitHub: one commit onto the branch of a pull request of the repository,
suggestions at their lines of one from a fork, and one pull request for main.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import workflow_steps
from hypothesis import given
from hypothesis import strategies as st
from shell import BASH
from workflow_steps import Answer, condition_of, step_in

import blueprint.fixes
import pins
from blueprint import cli
from blueprint.changelog import Fragment, fragment_problems
from blueprint.coach import BOT, DRAFT_HEADLINE, FIX_HEADLINE, Catalog
from blueprint.fixes import (
    BRANCH,
    HEADLINE,
    MADE_BY,
    MAIN_EVENTS,
    OPT_OUT,
    RIGHTS_FOLDERS,
    RIGHTS_SCRIPTS,
    SUGGESTED,
    Command,
    Fixes,
    FixLoop,
    Pushed,
    Suggestion,
    Watched,
    allowed,
    artifacts_of,
    blob_sha,
    changeable,
    changed,
    collect,
    commit_on_command,
    commit_onto_branch,
    decide_command,
    downloader,
    draft_of,
    expanded,
    files_of,
    fix_own,
    fix_text,
    fixers,
    for_unread,
    fragment_path,
    heal_main,
    is_command,
    is_text,
    keep,
    listing,
    load,
    needs_entry,
    own_fix,
    placeable,
    plan,
    report_kept,
    run,
    run_until_done,
    runs_of,
    runs_with_rights,
    shown,
    shown_lines,
    suggest,
    suggestions_of,
    text_fixed,
    watched,
    why_unread,
)
from blueprint.github import Api, GitHubError
from blueprint.migrate import LABELS, MIGRATIONS, MOVABLE
from blueprint.update import BRANCH as UPDATE_BRANCH

ROOT = Path(__file__).parents[1]
REPO = "o/r"
# The repository of a pull request from a fork.
FORK = "someone/r"
SHA = "a" * 40
OTHER = "b" * 40
MADE = "c0ffee" + "0" * 34
GIT = shutil.which("git")
needs_git = pytest.mark.skipif(GIT is None, reason="needs git")
needs_bash = pytest.mark.skipif(
    BASH is None or GIT is None, reason="the steps run in bash, Git Bash on Windows"
)


def write(root: Path, name: str, data: bytes | str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        data = data.encode()
    path.write_bytes(data)
    return path


def git(root: Path, *arguments: str) -> str:
    assert GIT
    return subprocess.run(
        [GIT, "-c", "user.name=T", "-c", "user.email=t@example.com", *arguments],
        cwd=root,
        check=True,
        capture_output=True,
        encoding="utf-8",
    ).stdout


def repository(root: Path, files: dict[str, bytes | str]) -> Path:
    """A repository of git with these files in its one commit."""
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "--quiet")
    git(root, "config", "core.autocrlf", "false")
    for name, data in files.items():
        write(root, name, data)
    git(root, "add", "--all")
    git(root, "commit", "--quiet", "--allow-empty", "-m", "start")
    return root


def kept(folder: Path, files: dict[str, bytes | str]) -> Path:
    """An artifact of fixes, as a check keeps it."""
    for name, data in files.items():
        write(folder / "files", name, data)
    return folder


# ---------------------------------------------------------------- the catalog


def test_the_steps_of_the_checks_fix_themselves_in_order() -> None:
    catalog = Catalog.load(ROOT)

    found = fixers(catalog, ROOT, "check (python)")

    assert found == [
        ("Text files", "{blueprint} fix text"),
        ("Pages in one column", "{blueprint} pages --fix"),
        ("Files of the project", "{blueprint} migrate --fix"),
        ("Changelog fragments", "{blueprint} fragments --fix"),
        ("Records of decisions", "{blueprint} decisions --fix"),
        ("Accepted advisories", "{blueprint} advisories --fix"),
        ("Lock files", "{blueprint} locks --fix"),
        ("Lock files match their sources", "{blueprint} locks --compile --fix"),
        ("Version", "{blueprint} fix version"),
        ("Ruff", "ruff check --fix ."),
        ("Ruff", "ruff format ."),
        # Of the blueprint alone, by its .github/checks.project.toml.
        ("Tests, with every line and branch covered", "{python} reference.py"),
        ("Tests, with every line and branch covered", "{python} pins.py"),
    ]
    # Without a check, as on your machine, the same.
    assert fixers(catalog, ROOT, None) == found


def test_another_check_fixes_itself_by_its_own_commands() -> None:
    catalog = Catalog.load(ROOT)

    assert fixers(catalog, ROOT, "markdown") == [
        ("markdown", 'npx markdownlint-cli2 --fix "**/*.md"')
    ]
    # A check whose findings need a person, and one without an explanation.
    assert fixers(catalog, ROOT, "dco") == []
    assert fixers(catalog, ROOT, "e2e") == []


def test_a_step_without_an_explanation_fixes_nothing(tmp_path: Path) -> None:
    write(
        tmp_path,
        ".github/checks.toml",
        '[step.Ruff]\nproblem = "a."\nwhy = "b."\nfix = "c."\n'
        'autofix = ["ruff format ."]\n',
    )
    write(tmp_path, "scripts/check.sh", 'step "Ruff"\nstep "Mypy"\n')

    assert fixers(Catalog.load(tmp_path), tmp_path, None) == [("Ruff", "ruff format .")]


def test_the_step_of_the_project_fixes_itself_within_its_if(tmp_path: Path) -> None:
    write(
        tmp_path,
        ".github/checks.project.toml",
        '[step."Checks of this project"]\nproblem = "a."\nwhy = "b."\nfix = "c."\n'
        'autofix = ["node scripts/check-l10n.mjs --write"]\n',
    )
    # As scripts/check.sh runs it: indented, and only with a scripts/check-project.sh.
    write(
        tmp_path,
        "scripts/check.sh",
        'step "Ruff"\nif [[ -f scripts/check-project.sh ]]; then\n'
        '  step "Checks of this project"\n  bash scripts/check-project.sh\nfi\n',
    )

    assert fixers(Catalog.load(tmp_path), tmp_path, "check (php)") == [
        ("Checks of this project", "node scripts/check-l10n.mjs --write")
    ]


# A lock file that Composer or npm refuses, as after a change of composer.json or
# package.json by hand, is locked again; one that they take stays as it is, also where
# another version of the tool would write it otherwise.
@needs_bash
@pytest.mark.parametrize(
    ("step", "tool", "check", "relock"),
    [
        (
            "Composer",
            "composer",
            "validate --no-check-publish --quiet",
            "update --minimal-changes --no-install --no-scripts --no-plugins "
            "--no-interaction",
        ),
        (
            "Package lock",
            "npm",
            "ci --dry-run --ignore-scripts --no-audit --no-fund",
            "install --package-lock-only --ignore-scripts --no-audit --no-fund",
        ),
    ],
)
@pytest.mark.parametrize("refused", [True, False])
def test_a_lock_file_is_locked_again_only_when_its_tool_refuses_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    step: str,
    tool: str,
    check: str,
    relock: str,
    refused: bool,
) -> None:
    calls = tmp_path / "calls"
    stub = write(
        tmp_path / "stubs",
        tool,
        f"#!/usr/bin/env bash\necho \"$*\" >> '{calls.as_posix()}'\n"
        f'[[ "$*" != "{check}" ]] || exit {int(refused)}\n',
    )
    stub.chmod(0o755)
    monkeypatch.setenv("PATH", f"{stub.parent}{os.pathsep}{os.environ['PATH']}")
    entry = Catalog.load(ROOT).step(step)
    assert entry

    said = run([(step, command) for command in entry.autofix], tmp_path, BASH)

    assert calls.read_text(encoding="utf-8").splitlines() == [
        check,
        *([relock] if refused else []),
    ]
    assert said == [f"- {step}: `{entry.autofix[0]}`"]


# The fix bot runs pins.py in the repository, a copy of the one of the blueprint. In the
# copy of the mutation tests, that is the code with the mutants, which asks mutmut for
# its configuration and finds none outside of mutants/ (#405).
@pytest.mark.mutation_unsafe
@needs_bash
def test_a_pin_that_disagrees_with_its_record_gets_its_sha256(tmp_path: Path) -> None:
    record = pins.load_record(ROOT)["sigstore/gitsign"]
    wrong = "0" * 64
    root = repository(
        tmp_path / "repo",
        {
            "pins.py": (ROOT / "pins.py").read_bytes(),
            ".github/pins.toml": pins.render_record({"sigstore/gitsign": record}),
            # By hand, or by a merge that took the line of the other side.
            ".github/sign-tag.sh": (
                "# renovate: datasource=github-releases depName=sigstore/gitsign\n"
                f"version={record.version}\n"
                f'sha256="{wrong}"\n'
            ),
        },
    )
    assert pins.check(root) != []
    commands = [
        (name, command)
        for name, command in fixers(Catalog.load(ROOT), ROOT, "check (python)")
        if "pins.py" in command
    ]

    said = run_until_done(commands, root, shell=BASH)

    assert said == ["- Tests, with every line and branch covered: `python3 pins.py`"]
    assert pins.check(root) == []
    assert (
        (root / ".github/sign-tag.sh")
        .read_text(encoding="utf-8")
        .endswith(f'sha256="{record.sha256}"\n')
    )
    # A file that the fix bot commits, as it would no workflow.
    assert changed(root) == [".github/sign-tag.sh"]
    assert allowed(".github/sign-tag.sh")
    assert not allowed(".github/workflows/verify-release.yml")


@pytest.mark.parametrize("script", [".github/blueprint.py", "blueprint.py"])
def test_a_command_runs_the_tool_of_the_repository(tmp_path: Path, script: str) -> None:
    write(tmp_path, script, "")

    assert shown("{blueprint} fix text", tmp_path) == f"python3 {script} fix text"
    python = Path(sys.executable).as_posix()
    assert expanded("{blueprint} fix text", tmp_path).endswith(f" {script} fix text")
    assert python in expanded("{blueprint} fix text", tmp_path)
    assert expanded("ruff format .", tmp_path) == "ruff format ."
    # A script of the repository runs with the Python of the bot as well.
    assert shown("{python} reference.py", tmp_path) == "python3 reference.py"
    assert expanded("{python} reference.py", tmp_path) == (
        f"{shlex.quote(python)} reference.py"
    )


# ---------------------------------------------------------------- in the check


@pytest.mark.skipif(BASH is None, reason="needs bash")
def test_each_command_runs_and_says_how_it_went(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    commands = [("One", "printf 'made\\n' > one.txt; echo log"), ("Two", "exit 3")]

    said = run(commands, tmp_path, shell=BASH)

    assert said == [
        "- One: `printf 'made\\n' > one.txt; echo log`",
        "- Two: `exit 3`, which ended with 3",
    ]
    assert (tmp_path / "one.txt").read_text(encoding="utf-8") == "made\n"
    # Their output goes to the log, not to the summary.
    assert "log" in capsys.readouterr().err


@pytest.mark.skipif(BASH is None, reason="needs bash")
def test_the_commands_run_in_the_bash_of_the_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: BASH)

    assert run([("One", "true")], tmp_path) == ["- One: `true`"]


@needs_bash
def test_the_commands_run_again_until_they_change_nothing_more(tmp_path: Path) -> None:
    root = repository(tmp_path / "repo", {"f.txt": ""})
    # A fix that leaves work for the next round, as one of Ruff for the format.
    step = 'case "$(cat f.txt)" in "") printf a > f.txt ;; a) printf ab > f.txt ;; esac'

    said = run_until_done([("Step", step)], root, shell=BASH)

    assert (root / "f.txt").read_text(encoding="utf-8") == "ab"
    assert said == [f"- Step: `{step}`"]


@needs_bash
def test_commands_that_never_end_their_work_run_only_so_often(tmp_path: Path) -> None:
    root = repository(tmp_path / "repo", {"f.txt": ""})

    run_until_done([("Step", "echo more >> f.txt")], root, shell=BASH)

    lines = (root / "f.txt").read_text(encoding="utf-8").splitlines()
    assert len(lines) == blueprint.fixes.ROUNDS


@needs_git
def test_keep_copies_the_files_that_a_command_changed(tmp_path: Path) -> None:
    root = repository(
        tmp_path / "repo",
        {"a.py": "a\n", ".github/b.toml": "b\n", "gone.txt": "g\n", "same.txt": "s\n"},
    )
    write(root, "a.py", "A\n")
    write(root, ".github/b.toml", "B\n")
    write(root, "new.txt", "new\n")
    (root / "gone.txt").unlink()
    folder = tmp_path / "fixes"

    assert keep(root, folder) == [".github/b.toml", "a.py"]
    assert (folder / "files/a.py").read_text(encoding="utf-8") == "A\n"
    assert (folder / "files/.github/b.toml").read_text(encoding="utf-8") == "B\n"
    assert not (folder / "files/new.txt").exists()
    assert not (folder / "files/gone.txt").exists()


@needs_git
def test_keep_leaves_no_folder_without_a_change(tmp_path: Path) -> None:
    root = repository(tmp_path / "repo", {"a.py": "a\n"})

    assert keep(root, tmp_path / "fixes") == []
    assert not (tmp_path / "fixes").exists()


def test_the_summary_names_the_files_that_the_commands_changed() -> None:
    assert report_kept([], kept=True) == ["They changed no file."]
    assert report_kept(["a.py"], kept=False) == [
        "They changed these files; commit them:",
        "",
        "- `a.py`",
    ]
    assert report_kept(["a.py"], kept=True)[-1] == "- `a.py`"
    assert "the fix bot commits" in report_kept(["a.py"], kept=True)[0]


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (b"one\r\ntwo\r\n", b"one\ntwo\n"),
        (b"one  \ntwo\t\n", b"one\ntwo\n"),
        (b"one\ntwo", b"one\ntwo\n"),
        (b"one \r\ntwo \t", b"one\ntwo\n"),
        (b"one \r \ntwo\n", b"one\ntwo\n"),
        (b"clean\n", b"clean\n"),
        (b"a\rb\n", b"a\rb\n"),
    ],
)
def test_a_text_file_gets_what_the_step_wants(before: bytes, after: bytes) -> None:
    assert text_fixed(before) == after


@given(st.binary())
def test_the_text_fix_is_done_at_once(data: bytes) -> None:
    fixed = text_fixed(data)

    assert text_fixed(fixed) == fixed
    assert fixed.endswith(b"\n")
    assert not re.search(rb"[ \t\r]\n", fixed)


def test_text_is_what_grep_takes_for_text() -> None:
    assert is_text("Grüße\n".encode())
    assert not is_text(b"a\0b")
    assert not is_text(b"\xff\xfe")


def check_the_text_files(root: Path) -> subprocess.CompletedProcess[str]:
    """The step Text files of scripts/check.sh, in the repository root."""
    check = (ROOT / "scripts/check.sh").read_text(encoding="utf-8")
    write(root, "scripts/check.sh", check[: check.index('step "Diagrams"')])
    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("GITHUB_")
    }
    assert BASH
    return subprocess.run(
        [BASH, "scripts/check.sh"],
        cwd=root,
        capture_output=True,
        encoding="utf-8",
        env=environment,
        check=False,
    )


@needs_bash
def test_the_text_fix_makes_the_step_pass(tmp_path: Path) -> None:
    files: dict[str, bytes | str] = {
        "crlf.md": b"one\r\ntwo\r\n",
        "spaces.py": b"x = 1  \n",
        "end.txt": b"no end",
        "LICENSE": b"license  \n",
        "LICENSES/MIT.txt": b"text  \n",
        "binary.bin": b"\0\x01 \n",
        "latin.txt": b"caf\xe9 \n",
        "empty.txt": b"",
        "lines.txt": b"\n\n",
        "gone.txt": b"gone \n",
        "clean.txt": b"clean\n",
        ".gitignore": b"ignored.txt\n",
    }
    root = repository(tmp_path / "repo", files)
    (root / "gone.txt").unlink()
    write(root, "new.txt", b"new \n")
    write(root, "ignored.txt", b"ignored \n")
    assert check_the_text_files(root).returncode == 1

    fixed = fix_text(root)

    assert fixed == ["crlf.md", "end.txt", "latin.txt", "new.txt", "spaces.py"]
    assert (root / "crlf.md").read_bytes() == b"one\ntwo\n"
    assert (root / "LICENSE").read_bytes() == b"license  \n"
    assert (root / "binary.bin").read_bytes() == b"\0\x01 \n"
    assert (root / "ignored.txt").read_bytes() == b"ignored \n"
    result = check_the_text_files(root)
    assert result.returncode == 0, result.stdout
    assert "Every text file is clean." in result.stdout


@needs_git
def test_the_text_fix_leaves_a_link_alone(tmp_path: Path) -> None:
    root = repository(tmp_path / "repo", {"target.txt": b"target \n"})
    try:
        (root / "link.txt").symlink_to("target.txt")
    except OSError:
        pytest.skip("this system makes no symbolic links without privileges")
    git(root, "add", "link.txt")

    assert fix_text(root) == ["target.txt"]
    assert (root / "link.txt").is_symlink()


# In the copy of the mutation tests, the tool that the test copies into the repository
# is the code with the mutants, whose format Ruff fixes as well.
@pytest.mark.mutation_unsafe
@needs_bash
def test_a_pull_request_with_mistakes_passes_after_its_fixes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The steps of a project: text files and Ruff, with the tools of the blueprint.
    ruff = shutil.which("ruff") or shutil.which(
        "ruff", path=str(Path(sys.executable).parent)
    )
    if ruff is None:
        pytest.skip("needs ruff")
    root = repository(tmp_path / "repo", {"README.md": "# Demo\n"})
    (root / ".github").mkdir()
    shutil.copy(ROOT / ".github/checks.toml", root / ".github/checks.toml")
    shutil.copy(ROOT / "blueprint.py", root / ".github/blueprint.py")
    shutil.copytree(
        ROOT / "blueprint",
        root / ".github/blueprint",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    check = (ROOT / "scripts/check.sh").read_text(encoding="utf-8")
    steps = check[: check.index('step "Diagrams"')]
    write(root, "scripts/check.sh", f'{steps}step "Ruff"\n"$RUFF" format --check .\n')
    git(root, "add", "--all")
    git(root, "commit", "--quiet", "-m", "tools")
    write(root, "app.py", "x  =  1   \nprint( x )\r\n")
    write(root, "README.md", "# Demo  \n\nNo end")
    git(root, "add", "--all")
    git(root, "commit", "--quiet", "-m", "the change")
    # As the job of the check runs it, with the tools on the PATH.
    monkeypatch.setenv(
        "PATH", os.pathsep.join([str(Path(ruff).parent), os.environ["PATH"]])
    )
    environment = {**os.environ, "RUFF": Path(ruff).as_posix()}

    def checks() -> int:
        assert BASH
        return subprocess.run(
            [BASH, "scripts/check.sh"],
            cwd=root,
            env=environment,
            capture_output=True,
            check=False,
        ).returncode

    assert checks() == 1
    code = cli.main(
        ["fix", "run", "check (python)", "--keep", str(tmp_path / "fixes")], root=root
    )

    assert code == 0
    summary = capsys.readouterr().out
    assert summary.startswith("### Fixed by a command\n")
    assert "- Text files: `python3 .github/blueprint.py fix text`" in summary
    assert "- `README.md`\n- `app.py`" in summary
    assert checks() == 0
    fixes = load([tmp_path / "fixes"])
    assert sorted(fixes.files) == ["README.md", "app.py"]
    assert fixes.files["app.py"] == b"x = 1\nprint(x)\n"


# The tool that the test copies into the repository is the code with the mutants in
# the copy of the mutation tests.
@pytest.mark.mutation_unsafe
@needs_bash
def test_a_fragment_with_a_typo_in_its_heading_heals_itself(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    changelog = "# Changelog\n\n## Unreleased\n\n## 1.0.0\n\n- First.\n"
    root = repository(
        tmp_path / "repo",
        {
            "CHANGELOG.md": changelog,
            "changelog.d/.gitkeep": "",
            "scripts/check.sh": 'step "Changelog fragments"\n',
        },
    )
    (root / ".github").mkdir()
    shutil.copy(ROOT / ".github/checks.toml", root / ".github/checks.toml")
    shutil.copy(ROOT / "blueprint.py", root / ".github/blueprint.py")
    shutil.copytree(
        ROOT / "blueprint",
        root / ".github/blueprint",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    git(root, "add", "--all")
    git(root, "commit", "--quiet", "-m", "tools")
    # The pull request of a branch of the repository, with the fragment of its change.
    write(root, "changelog.d/dark-mode.md", "### Fixes\n\n- **Dark mode:** works.\n")
    git(root, "add", "--all")
    git(root, "commit", "--quiet", "-m", "the change")

    code = cli.main(
        ["fix", "run", "check (python)", "--keep", str(tmp_path / "fixes")], root=root
    )

    assert code == 0
    summary = capsys.readouterr().out
    assert (
        "- Changelog fragments: `python3 .github/blueprint.py fragments --fix`"
        in summary
    )
    assert "- `changelog.d/dark-mode.md`" in summary
    # What the fix bot commits onto the branch, or suggests on a pull request from a
    # fork: the heading that the release reads.
    fixes = load([tmp_path / "fixes"])
    assert fixes.files == {
        "changelog.d/dark-mode.md": b"### Fixed\n\n- **Dark mode:** works.\n"
    }


# ---------------------------------------------------------------- what the checks kept


@pytest.mark.parametrize(
    ("path", "ok"),
    [
        ("README.md", True),
        (".github/checks.toml", True),
        ("src/demo/__init__.py", True),
        (".github/workflows/ci.yml", False),
        (".github/Workflows/ci.yml", False),
        (".git/config", False),
        (".GIT/hooks/pre-push", False),
        ("../outside.md", False),
        ("docs/a b.md", False),
        ("a//b.md", False),
        ("-rf.md", False),
    ],
)
def test_the_bot_writes_only_plain_paths_outside_git_and_the_workflows(
    path: str, ok: bool
) -> None:
    assert allowed(path) == ok


def test_the_fixes_of_the_checks_are_text_files_by_plain_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(blueprint.fixes, "MOST_BYTES", 10)
    first = kept(
        tmp_path / "1-fixes-check",
        {
            "a.py": "a = 1\n",
            "docs/b.md": "# B\n",
            "c d.md": "x\n",
            "big.txt": "x" * 11,
            "bin.dat": b"\0",
        },
    )
    second = kept(
        tmp_path / "2-fixes-markdown", {"docs/b.md": "# Other\n", "e.md": "e\n"}
    )

    fixes = load([first, second, tmp_path / "missing"])

    # The first check wins where two fixed a file.
    assert fixes.files == {"a.py": b"a = 1\n", "docs/b.md": b"# B\n", "e.md": b"e\n"}
    assert fixes.left == {
        "big.txt": "too large for a commit of the bot",
        "bin.dat": "no text file",
        "c d.md": "a path that the bot never writes",
    }


def test_one_commit_takes_only_so_many_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(blueprint.fixes, "MOST_FILES", 2)
    folder = kept(
        tmp_path / "1-fixes-check", {"a.md": "a\n", "b.md": "b\n", "c.md": "c\n"}
    )

    fixes = load([folder])

    assert list(fixes.files) == ["a.md", "b.md"]
    assert fixes.left == {"c.md": "one file too many for one commit"}


def test_the_bot_writes_no_link(tmp_path: Path) -> None:
    folder = kept(tmp_path / "1-fixes-check", {"a.md": "a\n"})
    try:
        (folder / "files/link.md").symlink_to("a.md")
        (folder / "files/folder").symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("this system makes no symbolic links without privileges")

    fixes = load([folder])

    assert fixes.files == {"a.md": b"a\n"}
    assert fixes.left == {
        "folder": "a link, which the bot never writes",
        "link.md": "a link, which the bot never writes",
    }


@needs_git
def test_the_id_of_a_file_is_that_of_git(tmp_path: Path) -> None:
    write(tmp_path, "a.txt", b"text\n")

    assert blob_sha(b"text\n") == git(tmp_path, "hash-object", "a.txt").strip()


def tree(
    files: dict[str, bytes], modes: dict[str, str] | None = None
) -> dict[str, Any]:
    modes = modes or {}
    return {
        "truncated": False,
        "tree": [
            {"path": "src", "mode": "040000", "type": "tree", "sha": "0" * 40},
            *(
                {
                    "path": path,
                    "mode": modes.get(path, "100644"),
                    "type": "blob",
                    "sha": blob_sha(data),
                }
                for path, data in files.items()
            ),
        ],
    }


def test_the_bot_changes_only_files_that_the_commit_has() -> None:
    files = {
        "a.py": ("100644", blob_sha(b"old\n")),
        "run.sh": ("100755", blob_sha(b"old\n")),
        "same.md": ("100644", blob_sha(b"same\n")),
        "link.md": ("120000", blob_sha(b"x")),
    }
    fixes = Fixes(
        {
            "a.py": b"new\n",
            "run.sh": b"new\n",
            "same.md": b"same\n",
            "link.md": b"new\n",
            "added.md": b"new\n",
        },
        {"left.md": "no text file"},
    )

    found = changeable(files, SHA, fixes)

    assert found.files == {"a.py": b"new\n", "run.sh": b"new\n"}
    assert found.left == {
        "added.md": "no file of aaaaaaa; the bot changes files, it adds none",
        "left.md": "no text file",
        "link.md": "no file of aaaaaaa; the bot changes files, it adds none",
    }


def test_the_listing_names_what_the_bot_left() -> None:
    assert listing(Fixes({"a.py": b""})) == ["- `a.py`"]
    assert listing(Fixes({"a.py": b""}, {"b c.md": "why"})) == [
        "- `a.py`",
        "",
        "Left to you:",
        "",
        "- `b c.md`: why",
    ]


# ---------------------------------------------------------------- a simulated GitHub


class FakeGitHub:
    """The parts of GitHub that the fix bot uses: the runs of a commit and their
    artifacts, its files, pull requests with their comments and reviews, branches and
    the commits of GraphQL."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {"app.py": b"x = 1\n"}
        # The files of a commit by its id, where they differ from those above.
        self.trees: dict[str, dict[str, bytes]] = {}
        self.modes: dict[str, str] = {}
        self.refs: dict[str, str] = {"main": SHA, "feature": SHA}
        self.pulls: list[dict[str, Any]] = []
        self.runs: list[dict[str, Any]] = []
        self.artifacts: dict[int, list[dict[str, Any]]] = {}
        self.downloads: dict[tuple[int, str], dict[str, bytes]] = {}
        self.review_comments: list[dict[str, Any]] = []
        self.patches: dict[str, str] = {}
        # The status of a file of a pull request, where it isn't "modified".
        self.statuses: dict[str, str] = {}
        # The commits of a pull request.
        self.pull_commits: list[dict[str, Any]] = []
        self.reviews: list[dict[str, Any]] = []
        self.comments: list[dict[str, Any]] = []
        self.created: list[dict[str, Any]] = []
        self.commit: dict[str, Any] = {
            "commit": {"message": "Add a feature"},
            "author": {"type": "User"},
            "files": [],
        }
        # Commits by their ids, where they differ from the one above.
        self.commits: dict[str, dict[str, Any]] = {}
        self.graphql: list[dict[str, Any]] = []
        self.graphql_fails = False
        # What happens to the branches while the bot commits, as a push would.
        self.on_commit: Callable[[FakeGitHub], None] = lambda github: None
        self.truncated = False
        self.calls: list[str] = []
        # The command /fix: the permissions of people, the comments by their ids, the
        # reactions to them, and the branches of the fork, which may refuse a commit.
        self.permissions: dict[str, str] = {"maintainer": "write"}
        self.issue_comments: dict[int, dict[str, Any]] = {}
        self.reactions: list[tuple[int, str]] = []
        self.reactions_fail = False
        self.fork_refs: dict[str, str] = {"feature": SHA}
        self.fork_refuses = False

    def __call__(
        self, arguments: Sequence[str], body: str | None
    ) -> subprocess.CompletedProcess[str]:
        if arguments[0] != "api":
            self.calls.append("gh " + " ".join(arguments))
            if list(arguments[:2]) == ["run", "download"]:
                run_id, name = int(arguments[2]), arguments[6]
                target = Path(arguments[8])
                for path, data in self.downloads[(run_id, name)].items():
                    write(target / "files", path, data)
            return subprocess.CompletedProcess(arguments, 0, "", "")
        method, path = arguments[3], arguments[4]
        self.calls.append(f"{method} {path}")
        if found := re.fullmatch(rf"repos/{FORK}/git/ref/heads/(.+)", path):
            sha = self.fork_refs.get(found[1])
            if not sha:
                return answered(arguments, 404, {})
            return answered(arguments, 200, {"object": {"sha": sha}})
        local = path.removeprefix(f"repos/{REPO}/")
        status, data = self.route(method, local, json.loads(body) if body else None)
        return answered(arguments, status, data)

    def route(self, method: str, path: str, body: Any) -> tuple[int, Any]:
        paged = r"per_page=(\d+)&page=(\d+)"
        if found := re.fullmatch(r"collaborators/([^/]+)/permission", path):
            if found[1] not in self.permissions:
                return 404, {"message": "Not Found"}
            return 200, {"permission": self.permissions[found[1]]}
        if found := re.fullmatch(r"issues/comments/(\d+)/reactions", path):
            assert method == "POST"
            if self.reactions_fail:
                return 403, {"message": "Resource not accessible by integration"}
            self.reactions.append((int(found[1]), body["content"]))
            return 201, {"id": 3, "content": body["content"]}
        if found := re.fullmatch(r"issues/comments/(\d+)", path):
            comment = self.issue_comments.get(int(found[1]))
            return (200, comment) if comment else (404, {"message": "Not Found"})
        if found := re.fullmatch(
            r"actions/runs\?head_sha=(\w+)&event=(\w+)&per_page=100", path
        ):
            runs = self.runs if found[1] == SHA else []
            return 200, {
                "workflow_runs": [
                    run for run in runs if run.get("event", found[2]) == found[2]
                ]
            }
        if found := re.fullmatch(r"actions/runs/(\d+)/artifacts\?per_page=100", path):
            return 200, {"artifacts": self.artifacts.get(int(found[1]), [])}
        if found := re.fullmatch(r"git/trees/(\w+)\?recursive=1", path):
            files = self.trees.get(found[1], self.files)
            data = tree(files, self.modes) | {"truncated": self.truncated}
            return 200, data
        if found := re.fullmatch(r"git/blobs/(\w+)", path):
            for content in self.files.values():
                if blob_sha(content) == found[1]:
                    return 200, {"content": base64.b64encode(content).decode()}
            return 404, {"message": "Not Found"}
        if found := re.fullmatch(r"git/ref/heads/(.+)", path):
            sha = self.refs.get(found[1])
            return (200, {"object": {"sha": sha}}) if sha else (404, {})
        if found := re.fullmatch(r"git/refs/heads/(.+)", path):
            if method == "DELETE":
                del self.refs[found[1]]
                return 204, None
            assert method == "PATCH"
            assert body["force"] is True
            self.refs[found[1]] = body["sha"]
            return 200, {}
        if method == "POST" and path == "git/refs":
            name = body["ref"].removeprefix("refs/heads/")
            assert name not in self.refs
            self.refs[name] = body["sha"]
            return 201, {"ref": body["ref"]}
        if found := re.fullmatch(r"commits/(\w+)", path):
            return 200, self.commits.get(found[1], self.commit)
        if found := re.fullmatch(r"users/(.+)", path):
            return 200, {"id": 41898282, "login": found[1]}
        if found := re.fullmatch(rf"pulls\?state=open&{paged}", path):
            return 200, self.page(self.pulls, *found.groups())
        if found := re.fullmatch(r"pulls\?state=open&head=([^&]+)", path):
            branch = found[1].split(":")[1]
            return 200, [
                pull
                for pull in self.pulls
                if pull["head"]["ref"] == branch and pull["state"] == "open"
            ]
        if found := re.fullmatch(r"pulls/(\d+)", path):
            pulls = [pull for pull in self.pulls if pull["number"] == int(found[1])]
            if method == "PATCH":
                pulls[0].update(body)
                return 200, pulls[0]
            return (200, pulls[0]) if pulls else (404, {})
        if method == "POST" and path == "pulls":
            pull = {
                "number": 77,
                "state": "open",
                "title": body["title"],
                "body": body["body"],
                "head": {"ref": body["head"], "repo": {"full_name": REPO}},
            }
            self.pulls.append(pull)
            self.created.append(body)
            return 201, pull
        if found := re.fullmatch(rf"pulls/(\d+)/files\?{paged}", path):
            items = [
                {
                    "filename": name,
                    "patch": patch,
                    "status": self.statuses.get(name, "modified"),
                }
                for name, patch in self.patches.items()
            ]
            return 200, self.page(items, found[2], found[3])
        if found := re.fullmatch(rf"pulls/(\d+)/commits\?{paged}", path):
            return 200, self.page(self.pull_commits, found[2], found[3])
        if found := re.fullmatch(rf"pulls/(\d+)/comments\?{paged}", path):
            return 200, self.page(self.review_comments, found[2], found[3])
        if found := re.fullmatch(r"pulls/(\d+)/reviews", path):
            assert method == "POST"
            self.reviews.append(body)
            return 200, {"id": 1}
        if found := re.fullmatch(r"issues/(\d+)/comments", path):
            assert method == "POST"
            self.comments.append(body | {"number": int(found[1])})
            return 201, {"id": 2}
        if path == "graphql":
            self.graphql.append(body)
            self.on_commit(self)
            if self.graphql_fails:
                return 200, {"errors": [{"message": "Expected branch to point to x"}]}
            branch = body["variables"]["input"]["branch"]["branchName"]
            if body["variables"]["input"]["branch"]["repositoryNameWithOwner"] == FORK:
                if self.fork_refuses:
                    refusal = "Resource not accessible by integration"
                    return 200, {"errors": [{"type": "FORBIDDEN", "message": refusal}]}
                self.fork_refs[branch] = MADE
                return 200, {
                    "data": {"createCommitOnBranch": {"commit": {"oid": MADE}}}
                }
            self.refs[branch] = MADE
            return 200, {"data": {"createCommitOnBranch": {"commit": {"oid": MADE}}}}
        raise AssertionError(f"unexpected request {method} {path}")

    def page(self, items: list[Any], size: str, number: str) -> list[Any]:
        start = (int(number) - 1) * int(size)
        return items[start : start + int(size)]

    def writes(self) -> list[str]:
        return [call for call in self.calls if not call.startswith("GET ")]

    def pull(
        self,
        number: int = 42,
        fork: bool = False,
        labels: Sequence[str] = (),
        editable: bool = False,
    ) -> None:
        self.pulls.append(
            {
                "number": number,
                "state": "open",
                "labels": [{"name": label} for label in labels],
                "base": {"ref": "main"},
                "maintainer_can_modify": editable,
                "head": {
                    "sha": SHA,
                    "ref": "feature",
                    "repo": {"full_name": FORK if fork else REPO},
                },
            }
        )


def answered(
    arguments: Sequence[str], status: int, data: Any
) -> subprocess.CompletedProcess[str]:
    """What gh api --include answers: the status, the headers and the data."""
    text = "" if data is None else json.dumps(data)
    return subprocess.CompletedProcess(
        list(arguments), 0, f"HTTP/2.0 {status} X\r\nA: b\r\n\r\n{text}", ""
    )


def api_of(github: FakeGitHub) -> Api:
    return Api(runner=github)


# ---------------------------------------------------------------- collect


def run_of(
    run_id: int, name: str, status: str = "completed", conclusion: str = "failure"
) -> dict[str, Any]:
    return {
        "id": run_id,
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "head_branch": "main",
    }


# The workflows of a repository whose checks are its CI, Lint and Docs.
WATCHED = Watched(
    frozenset({"Lint", "CI (python)", "CI (node)", "Docs", "CodeQL"}),
    frozenset({"Lint", "CI (python)", "CI (node)", "Docs"}),
)
# The list of HomeDarts for Autodarts, with the tests of its own: Docker E2E, and
# Visual check by the answer test_workflows of the blueprint.
HOMEDARTS = (
    "CI (home-assistant), Docker E2E, Visual check, CodeQL, Dependency review, Docs, "
    "Lint, Pull request title, Secret scan, Fuzzing, Links, OSV-Scanner, "
    "Workflow security, Release"
)


def workflow(name: str, artifact: str = "") -> str:
    """The text of a workflow, with the step that keeps an artifact."""
    step = f"      - uses: upload\n        with:\n          name: {artifact}\n"
    return f"name: {name}\n\non:\n  pull_request:\n\njobs:\n  check:\n    steps:\n" + (
        step if artifact else "      - run: 'true'\n"
    )


def homedarts(root: Path, after_checks: str = "") -> Path:
    """The workflows that main has in a repository like HomeDarts for Autodarts, whose
    end-to-end tests have a fix and whose visual tests have none."""
    after = after_checks or (
        "name: After the checks\n\non:\n  workflow_run:\n"
        f"    workflows: [{HOMEDARTS}]\n    types: [completed]\n"
    )
    write(root, ".github/workflows/after-checks.yml", after)
    write(
        root,
        ".github/workflows/ci.yml",
        workflow("CI (home-assistant)", "fixes-check"),
    )
    write(root, ".github/workflows/lint.yml", workflow("Lint", "fixes-lint"))
    write(root, ".github/workflows/docs.yml", workflow("Docs", "fixes-docs"))
    write(root, ".github/workflows/e2e.yml", workflow("Docker E2E", "fixes-e2e"))
    write(root, ".github/workflows/visual.yml", workflow("Visual check"))
    write(root, ".github/workflows/codeql.yml", workflow("CodeQL"))
    return root


def test_the_runs_of_a_commit_that_keep_fixes() -> None:
    github = FakeGitHub()
    github.runs = [
        run_of(1, "Lint"),
        run_of(3, "Lint", conclusion="success"),
        run_of(2, "CI (python)"),
        # An older run of the same workflow, which the newer one replaces.
        run_of(0, "CI (python)", conclusion="cancelled"),
        run_of(4, "Off the list"),
        {"id": 5, "name": None, "status": None, "conclusion": None},
    ]

    found = runs_of(api_of(github), REPO, SHA, "pull_request", "main", WATCHED.listed)

    assert [(run.id, run.name, run.conclusion) for run in found] == [
        (2, "CI (python)", "failure"),
        (3, "Lint", "success"),
    ]
    assert (
        runs_of(api_of(github), REPO, OTHER, "pull_request", "feature", WATCHED.listed)
        == []
    )


def test_the_bot_goes_by_the_list_and_the_files_of_main(tmp_path: Path) -> None:
    write(
        homedarts(tmp_path),
        ".github/workflows/other.yaml",
        workflow("Other", "fixes-x"),
    )
    write(
        tmp_path,
        ".github/workflows/comment.yml",
        workflow("Secret scan") + "      # name: fixes-old\n",
    )
    write(tmp_path, ".github/workflows/unnamed.yml", "on: push\n")
    write(
        tmp_path,
        ".github/workflows/quoted.yml",
        'name: "Links"\n\njobs:\n  check:\n    steps:\n      - with:\n          name: "fixes-links"\n',
    )

    found = watched(tmp_path)

    # Every workflow of the list, in the order of no one.
    assert found.listed == frozenset(HOMEDARTS.split(", "))
    # Those that keep fixes by their files; one off the list counts for nothing.
    assert found.keeping == {
        "CI (home-assistant)",
        "Docker E2E",
        "Docs",
        "Links",
        "Lint",
    }
    # Docs keeps nothing on a pull request.
    for event in MAIN_EVENTS:
        assert found.awaited(event) == found.keeping
    assert found.awaited("pull_request") == found.keeping - {"Docs"}


def test_this_repository_lists_what_keeps_fixes() -> None:
    found = watched(ROOT)

    assert {"Lint", "Docs", "CI (python)", "Downstream"} <= found.keeping
    assert found.keeping <= found.listed
    assert {"CodeQL", "Release", "Variants"} <= found.listed - found.keeping
    # The weekly run of Downstream keeps the answers of the repositories on main, and
    # a run of a pull request keeps nothing: the bot doesn't wait for its quarter of an
    # hour there (#843).
    assert "Downstream" in found.awaited("schedule")
    assert "Downstream" not in found.awaited("pull_request")


@pytest.mark.parametrize(
    "after_checks",
    [
        # No workflow_run at all, an empty list and one that a variable sets.
        "name: After the checks\non:\n  push:\n",
        "name: After the checks\non:\n  workflow_run:\n    workflows: []\n",
        "name: After the checks\non:\n  workflow_run:\n    workflows: ${{ x }}\n",
    ],
)
def test_without_a_list_the_bot_takes_nothing(
    tmp_path: Path, after_checks: str, capsys: pytest.CaptureFixture[str]
) -> None:
    homedarts(tmp_path, after_checks)
    github = FakeGitHub()
    github.pull()
    github.runs = [run_of(1, "Lint")]
    github.artifacts = {1: [{"name": "fixes-lint"}]}
    output = tmp_path / "output"

    code = fix_collect(tmp_path, github, output)

    captured = capsys.readouterr()
    assert code == 1
    assert "lists no workflow" in captured.out
    assert "::error::" in captured.err
    # It stops before it asks GitHub for anything, and tells no step to commit.
    assert github.calls == []
    assert output.read_text(encoding="utf-8") == "stopped=true\n"


def test_without_the_file_of_the_list_the_bot_stops(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    github = FakeGitHub()

    assert fix_collect(tmp_path, github, tmp_path / "output") == 2

    assert "after-checks.yml" in capsys.readouterr().err
    assert github.calls == []


def test_the_fixes_that_a_run_kept() -> None:
    github = FakeGitHub()
    github.artifacts[1] = [
        {"name": "fixes-check"},
        {"name": "fixes-markdown", "expired": True},
        {"name": "coverage"},
        {"name": None},
    ]

    assert artifacts_of(api_of(github), REPO, 1) == ["fixes-check"]
    assert artifacts_of(api_of(github), REPO, 2) == []


def test_a_pull_request_whose_run_kept_no_fix_has_nothing_to_wait_for(
    tmp_path: Path,
) -> None:
    github = FakeGitHub()
    github.runs = [run_of(1, "Lint"), run_of(2, "CI (python)", status="in_progress")]

    def wait(seconds: float) -> None:
        raise AssertionError("no wait")

    found = collect(
        api_of(github),
        REPO,
        1,
        SHA,
        "pull_request",
        "feature",
        tmp_path,
        downloader(api_of(github), REPO),
        WATCHED,
        wait,
    )

    assert found.folders == []
    assert github.calls == [
        f"GET repos/{REPO}/actions/runs?head_sha={SHA}&event=pull_request&per_page=100",
        f"GET repos/{REPO}/actions/runs/1/artifacts?per_page=100",
    ]


@pytest.mark.parametrize("conclusion", ["success", "cancelled", "timed_out"])
def test_a_run_that_did_not_fail_holds_no_runner_for_what_it_kept(
    tmp_path: Path, conclusion: str
) -> None:
    # The job now follows a run that passed, which may hold an artifact: a first attempt
    # that kept a fix and passed the second time, or a fixture bot of a project's own.
    github = FakeGitHub()
    github.runs = [
        run_of(1, "Lint", conclusion=conclusion),
        run_of(2, "CI (python)", status="in_progress", conclusion=""),
    ]
    github.artifacts = {1: [{"name": "fixes-lint"}]}

    def wait(seconds: float) -> None:
        raise AssertionError("no wait")

    found = collect(
        api_of(github),
        REPO,
        1,
        SHA,
        "pull_request",
        "feature",
        tmp_path,
        downloader(api_of(github), REPO),
        WATCHED,
        wait,
    )

    assert found.folders == []
    assert not any("/artifacts" in call for call in github.calls)


def test_a_run_that_runs_again_still_holds_its_fix(tmp_path: Path) -> None:
    # A failed run that started again counts as running, so its artifact keeps the job.
    github = FakeGitHub()
    github.runs = [run_of(1, "Lint", status="in_progress", conclusion="")]
    github.artifacts = {1: [{"name": "fixes-lint"}]}
    waits = []

    def wait(seconds: float) -> None:
        waits.append(seconds)
        github.runs[0].update(status="completed", conclusion="success")

    found = collect(
        api_of(github),
        REPO,
        1,
        SHA,
        "pull_request",
        "feature",
        tmp_path,
        downloader(api_of(github), REPO),
        WATCHED,
        wait,
    )

    assert waits
    assert found.folders == []


def test_a_run_with_no_fix_takes_the_fix_of_the_run_whose_job_it_replaced(
    tmp_path: Path,
) -> None:
    # GitHub keeps one pending job of a branch, so the job of a failed Lint can give way
    # to that of a failed Links, which kept nothing; the fix of Lint isn't lost for it.
    github = FakeGitHub()
    github.runs = [run_of(1, "Lint"), run_of(2, "Links")]
    github.artifacts = {1: [{"name": "fixes-lint"}]}
    github.downloads = {(1, "fixes-lint"): {"README.md": b"# Fixed\n"}}
    api = api_of(github)

    found = collect(
        api,
        REPO,
        2,
        SHA,
        "pull_request",
        "feature",
        tmp_path,
        downloader(api, REPO),
        Watched(frozenset({"Lint", "Links"}), frozenset({"Lint"})),
    )

    assert load(found.folders).files == {"README.md": b"# Fixed\n"}


@pytest.mark.parametrize(
    "line",
    [
        "name: fixes-e2e",
        "name: fixes-e2e-${{ strategy.job-index }}",
        "name: fixes-paperless-ngx-${{ matrix.line }}",
        "name: 'fixes-e2e'",
    ],
)
def test_a_workflow_keeps_fixes_by_every_form_of_the_name(
    tmp_path: Path, line: str
) -> None:
    # A matrix job names one artifact for each leg, or its second upload fails.
    root = tmp_path / "main"
    write(
        root,
        ".github/workflows/after-checks.yml",
        "on:\n  workflow_run:\n    workflows: [Docker E2E]\n",
    )
    write(
        root,
        ".github/workflows/e2e.yml",
        f"name: Docker E2E\n\njobs:\n  e2e:\n    steps:\n      - with:\n          {line}\n",
    )

    assert watched(root).keeping == {"Docker E2E"}


def test_the_bot_waits_for_the_other_checks_that_fix_and_takes_all_their_fixes(
    tmp_path: Path,
) -> None:
    github = FakeGitHub()
    github.runs = [
        run_of(1, "Lint"),
        run_of(2, "CI (python)", status="in_progress", conclusion=""),
        run_of(3, "CI (node)", conclusion="success"),
    ]
    github.artifacts = {
        1: [{"name": "fixes-markdown"}],
        2: [{"name": "fixes-check"}],
        3: [{"name": "fixes-check"}],
    }
    github.downloads = {
        (1, "fixes-markdown"): {"README.md": b"# Fixed\n"},
        (2, "fixes-check"): {"app.py": b"x = 2\n"},
    }
    waits: list[float] = []

    def wait(seconds: float) -> None:
        waits.append(seconds)
        if len(waits) == 2:
            github.runs[1].update(status="completed", conclusion="failure")

    api = api_of(github)
    found = collect(
        api,
        REPO,
        1,
        SHA,
        "pull_request",
        "main",
        tmp_path,
        downloader(api, REPO),
        WATCHED,
        wait,
    )

    assert waits == [30, 30]
    assert found.late == ()
    assert found.folders == [tmp_path / "1-fixes-markdown", tmp_path / "2-fixes-check"]
    # Only the runs that failed kept fixes.
    downloads = [call for call in github.calls if call.startswith("gh run download")]
    assert downloads == [
        f"gh run download 1 --repo {REPO} --name fixes-markdown --dir {tmp_path / '1-fixes-markdown'}",
        f"gh run download 2 --repo {REPO} --name fixes-check --dir {tmp_path / '2-fixes-check'}",
    ]
    assert load(found.folders).files == {
        "README.md": b"# Fixed\n",
        "app.py": b"x = 2\n",
    }


def test_the_bot_waits_only_a_while(tmp_path: Path) -> None:
    github = FakeGitHub()
    github.runs = [
        run_of(1, "Lint"),
        run_of(2, "CI (python)", status="queued", conclusion=""),
    ]
    github.artifacts = {1: [{"name": "fixes-markdown"}]}
    github.downloads = {(1, "fixes-markdown"): {"README.md": b"# Fixed\n"}}
    waits: list[float] = []

    api = api_of(github)
    found = collect(
        api,
        REPO,
        1,
        SHA,
        "pull_request",
        "main",
        tmp_path,
        downloader(api, REPO),
        WATCHED,
        waits.append,
    )

    assert len(waits) == blueprint.fixes.WAITS
    assert found.folders == [tmp_path / "1-fixes-markdown"]
    # It says which one still runs, from the same look as the fixes that it downloaded.
    assert found.late == ("CI (python)",)


def test_a_check_in_a_workflow_of_the_project_waits_with_the_others(
    tmp_path: Path,
) -> None:
    # The end-to-end tests of HomeDarts for Autodarts keep a fix of their own, so that
    # one commit holds it together with the one of Lint.
    github = FakeGitHub()
    github.runs = [
        run_of(1, "Lint"),
        run_of(2, "Docker E2E", status="in_progress", conclusion=""),
    ]
    github.artifacts = {
        1: [{"name": "fixes-lint"}],
        2: [{"name": "fixes-e2e"}],
    }
    github.downloads = {
        (1, "fixes-lint"): {"README.md": b"# Fixed\n"},
        (2, "fixes-e2e"): {"tests/e2e/snapshot.txt": b"new\n"},
    }
    waits: list[float] = []

    def wait(seconds: float) -> None:
        waits.append(seconds)
        github.runs[1].update(status="completed", conclusion="failure")

    api = api_of(github)
    workflows = watched(homedarts(tmp_path / "main"))
    found = collect(
        api,
        REPO,
        1,
        SHA,
        "pull_request",
        "feature",
        tmp_path / "fixes",
        downloader(api, REPO),
        workflows,
        wait,
    )

    assert waits == [30]
    assert load(found.folders).files == {
        "README.md": b"# Fixed\n",
        "tests/e2e/snapshot.txt": b"new\n",
    }


def test_the_bot_waits_for_no_workflow_that_keeps_no_fix(tmp_path: Path) -> None:
    # The tests in a browser of the project and the scanners run long and keep nothing:
    # the fix of Lint doesn't wait for them, and the next run of the checks starts anyway.
    github = FakeGitHub()
    github.runs = [
        run_of(1, "Lint"),
        run_of(2, "Visual check", status="in_progress", conclusion=""),
        run_of(3, "CodeQL", status="queued", conclusion=""),
    ]
    github.artifacts = {1: [{"name": "fixes-lint"}]}
    github.downloads = {(1, "fixes-lint"): {"README.md": b"# Fixed\n"}}

    def wait(seconds: float) -> None:
        raise AssertionError("no wait")

    api = api_of(github)
    found = collect(
        api,
        REPO,
        1,
        SHA,
        "pull_request",
        "feature",
        tmp_path / "fixes",
        downloader(api, REPO),
        watched(homedarts(tmp_path / "main")),
        wait,
    )

    assert load(found.folders).files == {"README.md": b"# Fixed\n"}


def test_every_workflow_of_the_list_counts_also_without_a_step_on_main(
    tmp_path: Path,
) -> None:
    # A workflow whose artifact comes from a composite action, where the bot doesn't
    # look: nothing waits for it, and its own end starts the bot, which reads it.
    github = FakeGitHub()
    github.runs = [run_of(2, "Visual check")]
    github.artifacts = {2: [{"name": "fixes-visual"}]}
    github.downloads = {(2, "fixes-visual"): {"docs/card.md": b"# Card\n"}}

    api = api_of(github)
    found = collect(
        api,
        REPO,
        2,
        SHA,
        "pull_request",
        "feature",
        tmp_path / "fixes",
        downloader(api, REPO),
        watched(homedarts(tmp_path / "main")),
    )

    assert load(found.folders).files == {"docs/card.md": b"# Card\n"}


def test_a_workflow_off_the_list_of_main_keeps_nothing_for_the_bot(
    tmp_path: Path,
) -> None:
    # A pull request, also one from a fork, adds a workflow, or renames one, as it likes.
    github = FakeGitHub()
    github.runs = [run_of(1, "Lint"), run_of(2, "My own checks")]
    github.artifacts = {
        1: [{"name": "fixes-lint"}],
        2: [{"name": "fixes-mine"}],
    }
    github.downloads = {
        (1, "fixes-lint"): {"README.md": b"# Fixed\n"},
        (2, "fixes-mine"): {"app.py": b"import evil\n"},
    }

    api = api_of(github)
    found = collect(
        api,
        REPO,
        1,
        SHA,
        "pull_request",
        "feature",
        tmp_path / "fixes",
        downloader(api, REPO),
        watched(homedarts(tmp_path / "main")),
    )

    assert load(found.folders).files == {"README.md": b"# Fixed\n"}
    assert not any("fixes-mine" in call for call in github.calls)


def test_only_a_run_that_failed_or_docs_on_main_keeps_fixes(tmp_path: Path) -> None:
    # On a pull request, a run that passed found nothing to fix, whatever it kept.
    github = FakeGitHub()
    github.runs = [
        run_of(1, "Lint"),
        run_of(2, "Docs", conclusion="success"),
        run_of(3, "Docker E2E", conclusion="success"),
        run_of(4, "Visual check", conclusion="cancelled"),
    ]
    github.artifacts = {
        1: [{"name": "fixes-lint"}],
        2: [{"name": "fixes-docs"}],
        3: [{"name": "fixes-e2e"}],
        4: [{"name": "fixes-visual"}],
    }
    github.downloads = {(1, "fixes-lint"): {"README.md": b"# Fixed\n"}}

    api = api_of(github)
    found = collect(
        api,
        REPO,
        1,
        SHA,
        "pull_request",
        "feature",
        tmp_path / "fixes",
        downloader(api, REPO),
        watched(homedarts(tmp_path / "main")),
    )

    assert found.folders == [tmp_path / "fixes/1-fixes-lint"]


def test_docs_keeps_the_fixes_of_main_alone_also_when_it_passes(
    tmp_path: Path,
) -> None:
    # The first run of the accessibility check on main accepts what the website has,
    # passes, and keeps the file for the fix bot.
    github = FakeGitHub()
    github.runs = [
        run_of(1, "Docs", conclusion="success"),
        run_of(2, "CI (python)", conclusion="success"),
    ]
    github.artifacts = {
        1: [{"name": "fixes-docs"}],
        2: [{"name": "fixes-old"}],
    }
    github.downloads = {
        (1, "fixes-docs"): {".github/a11y-accepted.toml": b"# Accepted\n"}
    }

    api = api_of(github)
    found = collect(
        api, REPO, 1, SHA, "push", "main", tmp_path, downloader(api, REPO), WATCHED
    )

    # Another check that passed keeps nothing that counts, such as what an earlier
    # attempt of it kept.
    assert found.folders == [tmp_path / "1-fixes-docs"]


@pytest.mark.parametrize("event", MAIN_EVENTS)
def test_main_looks_at_its_checks_also_when_the_run_kept_nothing(
    tmp_path: Path, event: str
) -> None:
    github = FakeGitHub()
    github.runs = [run_of(2, "CI (python)", conclusion="success")]

    api = api_of(github)
    assert (
        collect(
            api, REPO, 2, SHA, event, "main", tmp_path, downloader(api, REPO), WATCHED
        ).folders
        == []
    )
    assert any("actions/runs?head_sha" in call for call in github.calls)


def test_main_takes_the_fixes_of_a_commit_from_each_event_that_ran_its_checks(
    tmp_path: Path,
) -> None:
    # GitHub missed the schedule of one check, so bot health started it by hand: its
    # fixes and those of the other check of the weekly run end in one pull request. The
    # newest run of a check counts, and a pull request with the same head isn't main.
    github = FakeGitHub()
    github.runs = [
        run_of(1, "CI (python)", conclusion="success") | {"event": "push"},
        run_of(2, "Lint") | {"event": "schedule"},
        run_of(3, "CI (python)") | {"event": "workflow_dispatch"},
        run_of(4, "CI (python)", conclusion="success") | {"event": "pull_request"},
        # By hand on a branch at the same commit, which keeps no fix and isn't main.
        run_of(5, "CI (python)", conclusion="success")
        | {"event": "workflow_dispatch", "head_branch": "feature"},
    ]
    github.artifacts = {2: [{"name": "fixes-lint"}], 3: [{"name": "fixes-check"}]}
    github.downloads = {
        (2, "fixes-lint"): {"README.md": b"# Fixed\n"},
        (3, "fixes-check"): {"app.py": b"x = 2\n"},
    }

    api = api_of(github)
    found = collect(
        api, REPO, 2, SHA, "schedule", "main", tmp_path, downloader(api, REPO), WATCHED
    )

    assert found.folders == [tmp_path / "2-fixes-lint", tmp_path / "3-fixes-check"]
    assert load(found.folders).files == {
        "README.md": b"# Fixed\n",
        "app.py": b"x = 2\n",
    }


def test_a_weekly_run_doesnt_take_up_a_check_that_passed_since(tmp_path: Path) -> None:
    # What an earlier run of the commit kept counts no more once the newest run of its
    # check passes, as a run by hand after a failure of one day.
    github = FakeGitHub()
    github.runs = [
        run_of(1, "Lint") | {"event": "schedule"},
        run_of(2, "Lint", conclusion="success") | {"event": "workflow_dispatch"},
    ]
    github.artifacts = {1: [{"name": "fixes-lint"}]}

    api = api_of(github)
    assert (
        collect(
            api,
            REPO,
            2,
            SHA,
            "schedule",
            "main",
            tmp_path,
            downloader(api, REPO),
            WATCHED,
        ).folders
        == []
    )


def test_docs_keeps_a_fix_of_main_only_in_the_run_of_a_push(tmp_path: Path) -> None:
    # A run by hand of the same commit accepts nothing that the bot would take, and
    # hides no run of a push either.
    github = FakeGitHub()
    github.runs = [
        run_of(1, "Docs", conclusion="success") | {"event": "workflow_dispatch"}
    ]
    github.artifacts = {1: [{"name": "fixes-docs"}]}

    api = api_of(github)
    assert (
        collect(
            api,
            REPO,
            1,
            SHA,
            "schedule",
            "main",
            tmp_path,
            downloader(api, REPO),
            WATCHED,
        ).folders
        == []
    )
    assert not any("run download" in call for call in github.calls)


def test_main_takes_the_fix_of_a_workflow_of_the_project_too(tmp_path: Path) -> None:
    github = FakeGitHub()
    github.runs = [
        run_of(1, "CI (home-assistant)", conclusion="success"),
        run_of(2, "Docker E2E"),
    ]
    github.artifacts = {2: [{"name": "fixes-e2e"}]}
    github.downloads = {(2, "fixes-e2e"): {"app.py": b"x = 2\n"}}

    api = api_of(github)
    found = collect(
        api,
        REPO,
        1,
        SHA,
        "push",
        "main",
        tmp_path / "fixes",
        downloader(api, REPO),
        watched(homedarts(tmp_path / "main")),
    )
    fixes = load(found.folders)

    assert fixes.files == {"app.py": b"x = 2\n"}
    assert plan(api, REPO, SHA, "push", "main", None, fixes).action == "pull-request"


# ---------------------------------------------------------------- plan


FIXES = Fixes({"app.py": b"x = 2\n"})


def test_a_pull_request_of_the_repository_gets_a_commit() -> None:
    github = FakeGitHub()
    github.pull()

    decided = plan(api_of(github), REPO, SHA, "pull_request", "feature", 42, FIXES)

    assert (decided.action, decided.number) == ("commit", 42)


def test_a_pull_request_from_a_fork_gets_suggestions() -> None:
    github = FakeGitHub()
    github.pull(number=43, fork=True)

    # A run from a fork names no pull request; its commit finds it.
    decided = plan(api_of(github), REPO, SHA, "pull_request", "main", None, FIXES)

    assert (decided.action, decided.number) == ("suggest", 43)
    assert decided.text == "#43 comes from a fork.\n"


@pytest.mark.parametrize(
    ("labels", "fixes", "text"),
    [
        (
            [OPT_OUT],
            FIXES,
            "#42 has the label no-bot-fixes: the bot leaves it alone.\n",
        ),
        ([], Fixes({}), "No command fixed what the checks of #42 found.\n"),
    ],
)
def test_the_bot_leaves_a_pull_request_alone(
    labels: list[str], fixes: Fixes, text: str
) -> None:
    github = FakeGitHub()
    github.pull(labels=labels)

    decided = plan(api_of(github), REPO, SHA, "pull_request", "feature", 42, fixes)

    assert (decided.action, decided.text) == ("", text)


def test_the_bot_leaves_a_commit_that_is_no_head_alone() -> None:
    decided = plan(
        api_of(FakeGitHub()), REPO, SHA, "pull_request", "feature", None, FIXES
    )

    assert decided.action == ""
    assert decided.text == "aaaaaaa is no longer the head of an open pull request.\n"


def bot_commit(parent: str) -> dict[str, Any]:
    return {
        "commit": {"message": f"{FIX_HEADLINE}\n\n{MADE_BY} x"},
        "author": {"type": "Bot"},
        "files": [{"filename": "app.py"}],
        "parents": [{"sha": parent}],
    }


def test_the_bot_makes_one_more_commit_onto_its_own() -> None:
    # The checks of the bot's commit find what another check fixes: a Ruff fix after
    # the CI ended late, or markdownlint's fix of a file whose text the CI fixed.
    github = FakeGitHub()
    github.pull()
    github.commits[SHA] = bot_commit("b" * 40)

    decided = plan(api_of(github), REPO, SHA, "pull_request", "feature", 42, FIXES)

    assert (decided.action, decided.number) == ("commit", 42)


def test_the_bot_never_fixes_its_own_fixes_again() -> None:
    github = FakeGitHub()
    github.pull()
    github.commits[SHA] = bot_commit("b" * 40)
    github.commits["b" * 40] = bot_commit("c" * 40)

    with pytest.raises(FixLoop, match="don't fix the same way twice"):
        plan(api_of(github), REPO, SHA, "pull_request", "feature", 42, FIXES)


def test_a_draft_of_the_changelog_takes_no_round_of_the_fixes() -> None:
    # A draft comes once for each pull request, whatever the checks fix after it.
    github = FakeGitHub()
    github.pull()
    github.commits[SHA] = bot_commit("b" * 40)
    github.commits["b" * 40] = {
        "commit": {"message": DRAFT_HEADLINE},
        "author": {"type": "Bot"},
        "parents": [{"sha": "c" * 40}],
    }

    decided = plan(api_of(github), REPO, SHA, "pull_request", "feature", 42, FIXES)

    assert decided.action == "commit"


def test_a_bot_branch_gets_its_commit_too() -> None:
    # Renovate's commits are a bot's too, but not the fix bot's.
    github = FakeGitHub()
    github.pull()
    github.commit = {
        "commit": {"message": "fix(deps): update ruff"},
        "author": {"type": "Bot"},
    }

    assert (
        plan(
            api_of(github), REPO, SHA, "pull_request", "renovate/ruff", 42, FIXES
        ).action
        == "commit"
    )


@pytest.mark.parametrize(
    ("pull", "why"),
    [
        # Renovate's and Dependabot's merge once green, by themselves.
        ({"user": {"type": "Bot"}}, "bot"),
        ({"user": {"type": "Bot"}, "auto_merge": None}, "bot"),
        # A person's merges after another look, unless its auto-merge is on.
        (
            {"user": {"type": "User"}, "auto_merge": {"merge_method": "squash"}},
            "auto-merge",
        ),
        ({"user": {"type": "User"}, "auto_merge": None}, ""),
        ({}, ""),
    ],
)
def test_the_bot_knows_whether_anyone_reads_its_commit_before_the_merge(
    pull: dict[str, Any], why: str
) -> None:
    github = FakeGitHub()
    github.pull()
    github.pulls[0].update(pull)

    decided = plan(api_of(github), REPO, SHA, "pull_request", "feature", 42, FIXES)

    assert why_unread(pull) == why
    assert (decided.action, decided.unread) == ("commit", why)


@pytest.mark.parametrize(
    ("path", "with_rights"),
    [
        # The paths of the issue #837, and blueprint.py with its code.
        (".github/blueprint.py", True),
        ("blueprint/cli.py", True),
        ("Blueprint/CLI.py", True),
        ("blueprint.py", True),
        ("weekly.py", True),
        ("scripts/check.sh", True),
        ("pyproject.toml", True),
        (".github/actions/a/action.yml", True),
        (".github/renovate.json5", True),
        (".github/repository.toml", True),
        (".github/workflows/ci.yml", True),
        ("requirements-dev.txt", True),
        # The template reaches every repository made from the blueprint.
        ("template/README.md.jinja", True),
        # What runs only in a check, or nowhere.
        ("tests/conftest.py", False),
        ("app.py", False),
        ("src/blueprint.py", False),
        ("docs/blueprint/index.md", False),
        ("README.md", False),
    ],
)
def test_what_decides_what_a_workflow_runs_or_runs_with_its_rights(
    path: str, with_rights: bool
) -> None:
    assert runs_with_rights(path) is with_rights


def test_the_scripts_with_rights_are_those_that_the_workflows_run() -> None:
    named = {
        found[1]
        for workflow in (ROOT / ".github/workflows").glob("*.yml")
        for found in re.finditer(
            r"python3 \"?([a-z_]+\.py)\b", workflow.read_text(encoding="utf-8")
        )
    }

    assert named == RIGHTS_SCRIPTS


@pytest.mark.parametrize("event", MAIN_EVENTS)
def test_main_gets_a_pull_request_with_its_fixes(event: str) -> None:
    github = FakeGitHub()

    decided = plan(api_of(github), REPO, SHA, event, "main", None, FIXES)

    assert decided.action == "pull-request"


@pytest.mark.parametrize("event", MAIN_EVENTS)
def test_main_that_moved_on_leaves_it_to_its_newest_run(event: str) -> None:
    github = FakeGitHub()
    github.refs["main"] = OTHER

    decided = plan(api_of(github), REPO, SHA, event, "main", None, FIXES)

    assert decided == blueprint.fixes.Plan(
        "", "main moved on from aaaaaaa; its newest run decides.\n"
    )


@pytest.mark.parametrize("event", MAIN_EVENTS)
def test_main_without_fixes_closes_the_pull_request_of_its_fixes(event: str) -> None:
    github = FakeGitHub()
    assert plan(api_of(github), REPO, SHA, event, "main", None, Fixes({})).action == ""
    github.pulls.append({"number": 9, "state": "open", "head": {"ref": BRANCH}})

    decided = plan(api_of(github), REPO, SHA, event, "main", None, Fixes({}))

    assert (decided.action, decided.text) == (
        "close",
        "main needs the fixes of #9 no more.\n",
    )


def test_main_keeps_the_pull_request_of_fixes_that_expired() -> None:
    # A scanner fails on a main that stood still for days, with Lint still red: its
    # fixes are gone, which doesn't say that main needs them no more.
    github = FakeGitHub()
    github.pulls.append({"number": 9, "state": "open", "head": {"ref": BRANCH}})
    github.runs = [run_of(1, "Lint"), run_of(2, "CodeQL")]
    github.artifacts = {1: [{"name": "fixes-lint", "expired": True}]}

    decided = plan(
        api_of(github),
        REPO,
        SHA,
        "schedule",
        "main",
        None,
        Fixes({}),
        WATCHED.listed,
    )

    assert decided.action == ""
    assert "#9 stays open" in decided.text


# ---------------------------------------------------------------- a commit onto the branch


def test_the_fixes_become_one_signed_off_commit_on_the_branch() -> None:
    github = FakeGitHub()

    said = commit_onto_branch(
        api_of(github), REPO, "feature", SHA, FIXES, "app", "https://run"
    )

    assert said == "The fix bot committed c0ffee0 onto `feature`:\n\n- `app.py`\n"
    (request,) = github.graphql
    change = request["variables"]["input"]
    assert change["branch"] == {
        "repositoryNameWithOwner": REPO,
        "branchName": "feature",
    }
    assert change["expectedHeadOid"] == SHA
    assert change["message"] == {
        "headline": HEADLINE,
        "body": f"{MADE_BY} https://run\n\nSigned-off-by: app[bot] "
        "<41898282+app[bot]@users.noreply.github.com>",
    }
    assert change["fileChanges"] == {
        "additions": [
            {"path": "app.py", "contents": base64.b64encode(b"x = 2\n").decode()}
        ]
    }


def test_fixes_that_the_branch_has_make_no_commit() -> None:
    github = FakeGitHub()

    said = commit_onto_branch(
        api_of(github),
        REPO,
        "feature",
        SHA,
        Fixes({"app.py": b"x = 1\n", "new.md": b"n\n"}),
        "app",
        "u",
    )

    assert said.startswith("Every fix is in the branch already.\n\n\nLeft to you:")
    assert github.graphql == []


def test_a_branch_that_moved_on_fixes_itself_again() -> None:
    github = FakeGitHub()
    github.refs["feature"] = OTHER

    said = commit_onto_branch(api_of(github), REPO, "feature", SHA, FIXES, "app", "u")

    assert said == "feature moved on from aaaaaaa; its checks fix it again.\n"
    assert github.graphql == []


def test_a_push_while_the_bot_commits_wins() -> None:
    github = FakeGitHub()
    github.graphql_fails = True

    def push(fake: FakeGitHub) -> None:
        fake.refs["feature"] = OTHER

    github.on_commit = push

    said = commit_onto_branch(api_of(github), REPO, "feature", SHA, FIXES, "app", "u")

    assert said == "feature moved on from aaaaaaa; its checks fix it again.\n"


def test_a_commit_that_fails_otherwise_fails_the_bot() -> None:
    github = FakeGitHub()
    github.graphql_fails = True

    with pytest.raises(GitHubError, match="Expected branch"):
        commit_onto_branch(api_of(github), REPO, "feature", SHA, FIXES, "app", "u")


# What a check of a pull request of Renovate or of main could write, by a dependency of
# the branch that runs in it: the code that the jobs with the key of the release app run.
WITH_RIGHTS = {"blueprint/cli.py": b"evil = 1\n", ".github/blueprint.py": b"evil = 2\n"}


def with_rights(github: FakeGitHub) -> Fixes:
    """The fixes of app.py and of two files that run with rights, which the commit has."""
    github.files |= {path: b"good = 1\n" for path in WITH_RIGHTS}
    return Fixes(FIXES.files | WITH_RIGHTS)


@pytest.mark.parametrize(
    ("unread", "reason"),
    [
        ("bot", "a bot opened the pull request"),
        ("auto-merge", "the pull request merges by itself"),
        # A step that doesn't say counts as unread.
        (None, "nobody may read the commit"),
        ("unknown", "nobody may read the commit"),
    ],
)
def test_an_unread_commit_leaves_what_runs_with_rights_to_a_person(
    unread: str | None, reason: str
) -> None:
    github = FakeGitHub()
    fixes = with_rights(github)

    said = commit_onto_branch(
        api_of(github), REPO, "feature", SHA, fixes, "app", "u", unread
    )

    (request,) = github.graphql
    assert [
        addition["path"]
        for addition in request["variables"]["input"]["fileChanges"]["additions"]
    ] == ["app.py"]
    assert said.startswith("The fix bot committed c0ffee0 onto `feature`:")
    for path in WITH_RIGHTS:
        assert f"- `{path}`: decides what a workflow runs, and {reason}" in said
    assert said.endswith("so a person commits its fix\n")


def test_an_unread_commit_of_nothing_but_what_runs_with_rights_is_none() -> None:
    github = FakeGitHub()
    with_rights(github)

    said = commit_onto_branch(
        api_of(github), REPO, "feature", SHA, Fixes(WITH_RIGHTS), "app", "u", "bot"
    )

    assert said.startswith("The bot leaves every fix to a person.\n\n\nLeft to you:")
    assert "`blueprint/cli.py`" in said
    assert github.graphql == []


def test_the_author_reads_every_fix_of_a_branch_of_a_person() -> None:
    # Decision 0023: a person who merges by hand sees the commit in the pull request.
    github = FakeGitHub()
    fixes = with_rights(github)

    said = commit_onto_branch(
        api_of(github), REPO, "feature", SHA, fixes, "app", "u", ""
    )

    assert "Left to you" not in said
    (request,) = github.graphql
    assert len(request["variables"]["input"]["fileChanges"]["additions"]) == 3


def test_what_nobody_reads_keeps_every_other_reason() -> None:
    fixes = Fixes(WITH_RIGHTS, {"a.bin": "no text file"})

    left = for_unread(fixes, "main")

    assert left.files == {}
    assert list(left.left) == [".github/blueprint.py", "a.bin", "blueprint/cli.py"]
    assert left.left["a.bin"] == "no text file"


def test_the_update_of_the_blueprint_is_unread_by_its_branch() -> None:
    github = FakeGitHub()
    github.pull()
    github.pulls[0]["user"] = {"type": "Bot"}
    github.pulls[0]["head"]["ref"] = UPDATE_BRANCH

    decided = plan(api_of(github), REPO, SHA, "pull_request", UPDATE_BRANCH, 42, FIXES)

    assert (decided.action, decided.unread) == ("commit", "update")
    # A person's branch of that name is still read by its author.
    assert why_unread({"user": {"type": "User"}, "head": {"ref": UPDATE_BRANCH}}) == ""


def test_the_update_of_the_blueprint_gets_the_move_of_a_migration() -> None:
    # Decision 0111: the update merges by itself once the bot committed the move.
    github = FakeGitHub()
    fixes = with_rights(github)
    github.files[LABELS] = b'group = "decision"\n'
    fixes = Fixes(fixes.files | {LABELS: b'group = "contribution"\n'})

    said = commit_onto_branch(
        api_of(github), REPO, "feature", SHA, fixes, "app", "u", "update"
    )

    (request,) = github.graphql
    assert [
        addition["path"]
        for addition in request["variables"]["input"]["fileChanges"]["additions"]
    ] == ["app.py", LABELS]
    for path in WITH_RIGHTS:
        assert f"- `{path}`: decides what a workflow runs, and the update" in said
    # On any other pull request that nobody reads, the file stays with a person.
    assert LABELS in for_unread(Fixes({LABELS: b""}), "bot").left


def test_a_migration_moves_only_data_that_the_bot_may_commit() -> None:
    # The bot of main decides, so a new path comes to MOVABLE before its migration.
    assert {migration.path for migration in MIGRATIONS} <= MOVABLE
    for path in MOVABLE:
        assert not path.startswith((".github/workflows/", ".github/actions/"))
        assert path.endswith(".toml")
        assert path.split("/")[0] not in RIGHTS_FOLDERS


def test_too_many_files_for_one_answer_stop_the_bot() -> None:
    github = FakeGitHub()
    github.truncated = True

    with pytest.raises(GitHubError, match="too many for one answer"):
        files_of(api_of(github), REPO, SHA)


# ---------------------------------------------------------------- suggestions


def test_a_suggestion_of_one_line_and_of_several() -> None:
    one = Suggestion("a.py", 3, 3, ("x = 1",))
    several = Suggestion("a.py", 3, 5, ("x = 1", "y = 2"))
    deleted = Suggestion("a.py", 2, 2, ())
    fenced = Suggestion("a.md", 1, 1, ("```sh",))

    assert one.comment() == {
        "path": "a.py",
        "line": 3,
        "side": "RIGHT",
        "body": f"{SUGGESTED}\n\n```suggestion\nx = 1\n```",
    }
    assert several.comment()["start_line"] == 3
    assert several.comment()["start_side"] == "RIGHT"
    assert several.key() == ("a.py", 5, 3, several.body)
    assert one.key() == ("a.py", 3, None, one.body)
    # No lines delete the lines; a fence of the file can't close the suggestion.
    assert deleted.body.endswith("\n\n```suggestion\n```")
    assert fenced.body.endswith("\n\n````suggestion\n```sh\n````")


@pytest.mark.parametrize(
    ("before", "after", "expected", "rest"),
    [
        # A line that changes.
        ("a\nb  \nc\n", "a\nb\nc\n", [(2, 2, ("b",))], False),
        # Lines that go.
        ("a\nb\nc\n", "a\nc\n", [(2, 2, ())], False),
        # A line that comes, after the line before it.
        ("a\nc\n", "a\nb\nc\n", [(1, 1, ("a", "b"))], False),
        # A line that comes first, before the first line.
        ("b\n", "a\nb\n", [(1, 1, ("a", "b"))], False),
        # The end of the file, which no suggestion shows.
        ("a\nb", "a\nb\n", [], True),
        ("a  \nb", "a\nb\n", [(1, 1, ("a",))], True),
        # Line endings, and a file of no lines.
        ("a\r\nb\r\n", "a\nb\n", [], True),
        ("", "\n", [], True),
        # GitHub counts lines by newlines only: a form feed is no line of its own.
        ("a\fb\nc  \n", "a\fb\nc\n", [(2, 2, ("c",))], False),
    ],
)
def test_the_suggestions_of_a_fix(
    before: str,
    after: str,
    expected: list[tuple[int, int, tuple[str, ...]]],
    rest: bool,
) -> None:
    found, more = suggestions_of("a.md", before, after)

    assert [(item.start, item.end, item.lines) for item in found] == expected
    assert more == rest


def test_a_suggestion_of_too_many_lines_is_left_to_the_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(blueprint.fixes, "SUGGESTION_LINES", 2)

    found, rest = suggestions_of("a.md", "a\nb\nc\nd\n", "A\nB\nC\nd\n")

    assert found == []
    assert rest


def test_a_suggestion_goes_only_where_the_pull_request_shows_lines() -> None:
    patch = "@@ -1,3 +1,4 @@\n a\n+b\n c\n d\n@@ -10 +11 @@\n-x\n+y\n@@ -20,2 +22,0 @@\n-p\n-q\n"
    hunks = shown_lines(patch)

    assert hunks == [(1, 4), (11, 11)]
    assert placeable(Suggestion("a", 2, 4, ()), hunks)
    assert placeable(Suggestion("a", 11, 11, ()), hunks)
    assert not placeable(Suggestion("a", 4, 5, ()), hunks)
    assert not placeable(Suggestion("a", 12, 12, ()), hunks)


def fork_with_fixes(github: FakeGitHub) -> Fixes:
    """A pull request from a fork whose checks fixed three files."""
    github.pull(fork=True)
    github.files = {
        "app.py": b"x  =  1\ny = 2\nz  =  3\n",
        "README.md": b"# Title  \n\nText\n",
        "crlf.md": b"a\r\nb\r\n",
        "far.md": b"one \n" + b"line\n" * 30 + b"two \n",
    }
    github.patches = {
        "app.py": "@@ -0,0 +1,3 @@\n+x  =  1\n+y = 2\n+z  =  3\n",
        "README.md": "@@ -1,3 +1,3 @@\n-# Title\n+# Title  \n \n Text\n",
        "crlf.md": "@@ -0,0 +1,2 @@\n+a\n+b\n",
        "far.md": "@@ -30,3 +30,3 @@\n line\n-two\n+two \n line\n",
    }
    return Fixes(
        {
            "app.py": b"x = 1\ny = 2\nz = 3\n",
            "README.md": b"# Title\n\nText\n",
            "crlf.md": b"a\nb\n",
            "far.md": b"one\n" + b"line\n" * 30 + b"two\n",
        }
    )


def test_a_pull_request_from_a_fork_gets_its_fixes_as_suggestions() -> None:
    github = FakeGitHub()
    fixes = fork_with_fixes(github)

    said = suggest(api_of(github), REPO, 42, SHA, fixes)

    assert said == "Suggested 4 fix(es) on #42.\n"
    (review,) = github.reviews
    assert review["commit_id"] == SHA
    assert review["event"] == "COMMENT"
    assert [(item["path"], item["line"]) for item in review["comments"]] == [
        ("app.py", 1),
        ("app.py", 3),
        ("README.md", 1),
        ("far.md", 32),
    ]
    assert review["comments"][0]["body"].endswith("```suggestion\nx = 1\n```")
    # The fixes that no suggestion shows: line endings, and lines that the pull request
    # doesn't show.
    assert review["body"].startswith("### The fix bot\n\n")
    assert review["body"].endswith("on your machine:\n\n- `crlf.md`\n- `far.md`")
    assert "more follow" not in review["body"]


def test_the_bot_suggests_a_fix_once_and_only_so_many(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(blueprint.fixes, "SUGGESTIONS", 1)
    github = FakeGitHub()
    fixes = fork_with_fixes(github)
    made = Suggestion("README.md", 1, 1, ("# Title",))
    github.review_comments = [
        {
            "user": {"login": BOT},
            "path": "README.md",
            "line": 1,
            "start_line": None,
            "body": made.body,
        },
        # The same text of someone else counts as no suggestion of the bot.
        {
            "user": {"login": "someone"},
            "path": "app.py",
            "line": 1,
            "start_line": None,
            "body": Suggestion("app.py", 1, 1, ("x = 1",)).body,
        },
    ]

    said = suggest(api_of(github), REPO, 42, SHA, fixes)

    assert said == "Suggested 1 fix(es) on #42.\n"
    (review,) = github.reviews
    assert [(item["path"], item["line"]) for item in review["comments"]] == [
        ("app.py", 1)
    ]
    assert "\n\n2 more follow once you push these.\n\n" in review["body"]


def test_no_new_suggestion_makes_no_review() -> None:
    github = FakeGitHub()
    github.pull(fork=True)
    github.files = {"crlf.md": b"a\r\nb\r\n"}
    github.patches = {"crlf.md": "@@ -0,0 +1,2 @@\n+a\n+b\n"}

    said = suggest(api_of(github), REPO, 42, SHA, Fixes({"crlf.md": b"a\nb\n"}))

    assert said == "No new suggestion for #42; the PR coach names the commands.\n"
    assert github.reviews == []


# ---------------------------------------------------------------- main


def test_main_gets_one_pull_request_that_merges_itself() -> None:
    github = FakeGitHub()
    github.refs[f"{BRANCH}-next"] = OTHER

    said = heal_main(api_of(github), REPO, SHA, "main", FIXES, "app", "https://run")

    assert said == (
        f"#77 from {BRANCH} has the fixes of main in c0ffee0, and merges itself once "
        "every check passes.\n"
    )
    # The commit starts from the commit of main, on a branch of its own that starts
    # anew, and the branch of the pull request starts at it.
    assert (
        github.graphql[0]["variables"]["input"]["branch"]["branchName"]
        == f"{BRANCH}-next"
    )
    assert github.graphql[0]["variables"]["input"]["expectedHeadOid"] == SHA
    assert github.refs[BRANCH] == MADE
    assert f"{BRANCH}-next" not in github.refs
    (created,) = github.created
    assert created["title"] == HEADLINE
    assert (created["head"], created["base"]) == (BRANCH, "main")
    assert created["body"].startswith("`main` has findings of its checks")
    assert "- `app.py`" in created["body"]
    assert created["body"].endswith(
        "The checks of `main` that found them: https://run\n"
    )
    assert github.calls[-1] == f"gh pr merge 77 --repo {REPO} --auto --squash"


def test_main_updates_its_one_pull_request() -> None:
    github = FakeGitHub()
    github.pulls.append(
        {"number": 9, "state": "open", "head": {"ref": BRANCH}, "body": "old"}
    )
    github.refs[BRANCH] = OTHER

    said = heal_main(api_of(github), REPO, SHA, "main", FIXES, "app", "https://run")

    assert said.startswith(f"#9 from {BRANCH} has the fixes of main in c0ffee0")
    assert github.created == []
    assert github.pulls[0]["body"].startswith("`main` has findings")
    # The head of the open pull request moves to the new commit, never to main.
    assert f"PATCH repos/{REPO}/git/refs/heads/{BRANCH}" in github.calls
    assert github.refs[BRANCH] == MADE


def healed_pull(github: FakeGitHub, parent: str, files: dict[str, bytes]) -> None:
    """An open pull request of the fixes of main, one commit on parent."""
    github.pulls.append(
        {
            "number": 9,
            "state": "open",
            "head": {"ref": BRANCH, "sha": OTHER},
            "body": "old",
            "auto_merge": {"merge_method": "squash"},
        }
    )
    github.refs[BRANCH] = OTHER
    github.commits[OTHER] = {"parents": [{"sha": parent}]}
    github.trees[OTHER] = files


def test_main_leaves_a_pull_request_with_the_same_fixes_alone() -> None:
    # Each failed check of the weekly run starts the bot, and the second run finds what
    # the first one made: a new commit would only start the checks of the pull request
    # again, and a stuck one would run them anew each week.
    github = FakeGitHub()
    healed_pull(github, SHA, {"app.py": b"x = 2\n"})

    said = heal_main(api_of(github), REPO, SHA, "main", FIXES, "app", "https://run")

    assert said == f"#9 from {BRANCH} holds these fixes of main already.\n"
    assert github.refs[BRANCH] == OTHER
    assert github.graphql == []
    assert github.pulls[0]["body"] == "old"
    assert [call for call in github.calls if not call.startswith("GET ")] == []


def test_main_asks_again_for_the_merge_of_a_pull_request_with_the_same_fixes() -> None:
    # The run that made the commit failed to ask, and the next one must not leave the
    # pull request to wait for a person: that is all it writes.
    github = FakeGitHub()
    healed_pull(github, SHA, {"app.py": b"x = 2\n"})
    github.pulls[0]["auto_merge"] = None

    said = heal_main(api_of(github), REPO, SHA, "main", FIXES, "app", "https://run")

    assert said == f"#9 from {BRANCH} holds these fixes of main already.\n"
    assert github.refs[BRANCH] == OTHER
    assert [call for call in github.calls if not call.startswith("GET ")] == [
        f"gh pr merge 9 --repo {REPO} --auto --squash"
    ]


@pytest.mark.parametrize(
    ("parent", "files"),
    [
        # It starts from an older commit of main, or holds other fixes.
        (OTHER, {"app.py": b"x = 2\n"}),
        (SHA, {"app.py": b"x = 3\n"}),
        (SHA, {"app.py": b"x = 2\n", "more.py": b"y = 2\n"}),
    ],
)
def test_main_moves_a_pull_request_with_other_fixes(
    parent: str, files: dict[str, bytes]
) -> None:
    github = FakeGitHub()
    healed_pull(github, parent, files)

    said = heal_main(api_of(github), REPO, SHA, "main", FIXES, "app", "https://run")

    assert said.startswith(f"#9 from {BRANCH} has the fixes of main in c0ffee0")
    assert github.refs[BRANCH] == MADE


@pytest.mark.parametrize("fixes", [Fixes({}), Fixes({"app.py": b"x = 1\n"})])
def test_main_that_needs_no_fix_closes_the_pull_request(fixes: Fixes) -> None:
    github = FakeGitHub()
    github.pulls.append({"number": 9, "state": "open", "head": {"ref": BRANCH}})
    github.refs[BRANCH] = OTHER

    said = heal_main(api_of(github), REPO, SHA, "main", fixes, "app", "https://run")

    assert said == "main needs the fixes no more; closed #9.\n"
    assert github.comments == [
        {"body": "`main` needs none of these fixes any more: https://run", "number": 9}
    ]
    assert github.pulls[0]["state"] == "closed"
    assert BRANCH not in github.refs


def test_main_without_fixes_and_without_a_pull_request_is_fine() -> None:
    github = FakeGitHub()

    said = heal_main(api_of(github), REPO, SHA, "main", Fixes({}), "app", "u")

    assert said == "main needs no fix that a command makes.\n"
    assert github.writes() == []


def test_the_pull_request_of_main_holds_nothing_that_runs_with_rights() -> None:
    # It merges itself, so what a check of main wrote must not reach main through it.
    github = FakeGitHub()
    fixes = with_rights(github)

    said = heal_main(api_of(github), REPO, SHA, "main", fixes, "app", "https://run")

    assert said.startswith(f"#77 from {BRANCH} has the fixes of main in c0ffee0")
    (request,) = github.graphql
    assert [
        addition["path"]
        for addition in request["variables"]["input"]["fileChanges"]["additions"]
    ] == ["app.py"]
    (created,) = github.created
    assert "Left to you:" in created["body"]
    assert (
        "- `blueprint/cli.py`: decides what a workflow runs, and the pull request of "
        "main merges itself, without a person reading the commit, so a person commits "
        "its fix"
    ) in created["body"]
    assert "- `.github/blueprint.py`: decides what a workflow runs" in created["body"]


def test_main_with_nothing_but_fixes_with_rights_opens_no_pull_request() -> None:
    github = FakeGitHub()
    with_rights(github)

    said = heal_main(api_of(github), REPO, SHA, "main", Fixes(WITH_RIGHTS), "app", "u")

    assert said.startswith("main has no fix that the bot commits.\n\nLeft to you:\n")
    assert "- `blueprint/cli.py`: decides what a workflow runs" in said
    assert github.writes() == []


def test_main_with_nothing_but_fixes_with_rights_closes_its_pull_request() -> None:
    # Its old commit may hold such a fix, which must not merge itself either.
    github = FakeGitHub()
    with_rights(github)
    healed_pull(github, SHA, github.files | WITH_RIGHTS)

    said = heal_main(
        api_of(github), REPO, SHA, "main", Fixes(WITH_RIGHTS), "app", "https://run"
    )

    assert said.startswith(
        "main has no fix that the bot commits; closed #9.\n\nLeft to you:\n"
    )
    assert github.comments == [
        {
            "body": "`main` has no fix left that the bot commits; a person commits "
            "the rest: https://run",
            "number": 9,
        }
    ]
    assert github.pulls[0]["state"] == "closed"
    assert BRANCH not in github.refs


# ---------------------------------------------------------------- the command line


@needs_git
def test_fix_text_from_the_command_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repository(tmp_path / "repo", {"a.md": b"a  \n", "b.md": b"b\n"})

    assert cli.main(["fix", "text"], root=root) == 0
    assert capsys.readouterr().out == (
        "a.md: LF line endings, no trailing whitespace, a line break at its end\n"
        "1 text file(s) fixed.\n"
    )
    assert cli.main(["fix", "text"], root=root) == 0
    assert capsys.readouterr().out == "Every text file is clean.\n"


@needs_git
def test_fix_keep_from_the_command_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repository(tmp_path / "repo", {"a.md": b"a\n"})
    write(root, "a.md", b"A\n")

    assert cli.main(["fix", "keep", str(tmp_path / "fixes")], root=root) == 0
    assert capsys.readouterr().out.endswith("from a fork:\n\n- `a.md`\n")
    assert (tmp_path / "fixes/files/a.md").read_bytes() == b"A\n"


@needs_bash
def test_fix_run_on_your_machine(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repository(
        tmp_path / "repo",
        {
            ".github/checks.toml": '[step.Format]\nproblem = "a."\nwhy = "b."\n'
            'fix = "c."\nautofix = ["true"]\n',
            "scripts/check.sh": 'step "Format"\n',
        },
    )
    monkeypatch.setattr(shutil, "which", lambda name: BASH)

    assert cli.main(["fix", "run"], root=root) == 0
    out = capsys.readouterr().out
    assert "The commands that fix what the steps of scripts/check.sh found" in out
    assert out.endswith(
        "- Format: `true`\n\n`git diff` shows what they changed; commit it.\n"
    )
    assert cli.main(["fix", "run", "markdown"], root=root) == 0
    assert (
        capsys.readouterr().out
        == "No command of the explanations fixes what markdown found.\n"
    )


def test_fix_run_with_a_broken_catalog(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(tmp_path, ".github/checks.toml", "[step.Format]\nautofix = 3\n")

    assert cli.main(["fix", "run"], root=tmp_path) == 2
    assert "blueprint.py: .github/checks.toml" in capsys.readouterr().err


def fix_collect(root: Path, github: FakeGitHub, output: Path, run: str = "1") -> int:
    """Runs fix collect for a pull request as its step does, in the files of main."""
    return cli.main(
        [
            "--repo",
            REPO,
            "fix",
            "collect",
            run,
            "--sha",
            SHA,
            "--event",
            "pull_request",
            "--branch",
            "feature",
            "--pull",
            "42",
            "--folder",
            str(root / "fixes"),
            "--output",
            str(output),
        ],
        api=api_of(github),
        root=root,
    )


def test_fix_collect_from_the_command_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    github = FakeGitHub()
    github.pull()
    github.runs = [run_of(1, "CI (home-assistant)")]
    github.artifacts = {1: [{"name": "fixes-check"}]}
    github.downloads = {(1, "fixes-check"): {"app.py": b"x = 2\n"}}
    output = tmp_path / "output"
    folder = tmp_path / "fixes"

    code = fix_collect(homedarts(tmp_path), github, output)

    assert code == 0
    assert output.read_text(encoding="utf-8") == "action=commit\npull=42\n"
    assert capsys.readouterr().out == "#42 comes from a branch of this repository.\n"
    assert load([folder / "1-fixes-check"]).files == {"app.py": b"x = 2\n"}

    # The pull request of Renovate: the step of the commit learns that nobody reads it.
    github.pulls[0]["user"] = {"type": "Bot"}
    output.unlink()

    assert fix_collect(homedarts(tmp_path), github, output) == 0
    assert output.read_text(encoding="utf-8") == "action=commit\npull=42\nunread=bot\n"


class Unavailable(FakeGitHub):
    """GitHub in an outage, as on 9 November 2026: every call of its API fails."""

    def route(self, method: str, path: str, body: Any) -> tuple[int, Any]:
        return 503, {"message": "Service unavailable"}


@pytest.mark.parametrize("runner", [True, False])
def test_the_fix_bot_ends_with_a_notice_when_github_keeps_failing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    waits: list[float],
    monkeypatch: pytest.MonkeyPatch,
    runner: bool,
) -> None:
    # Its next run after the checks does what this one couldn't, and the run of the
    # bot mails no one (decision 0155).
    github = Unavailable()
    output = tmp_path / "output"
    folder = tmp_path / "runner"
    folder.mkdir()
    if runner:
        monkeypatch.setenv("RUNNER_TEMP", str(folder))

    assert fix_collect(homedarts(tmp_path), github, output) == 0
    out, err = capsys.readouterr()
    assert out == ""
    assert err.startswith(
        "::notice title=GitHub is unavailable::GitHub kept failing (GitHub answered 503"
    )
    assert "Nothing to do for a person." in err
    assert waits == [10, 20, 40]
    # The steps after it, which commit or suggest, learn of nothing to do, and the
    # step of the issue of main learns that the job sat out an outage, on a runner.
    assert not output.exists()
    assert (folder / "github-sat-out").exists() is runner


def test_the_command_fix_fails_when_github_keeps_failing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The person who asked for the fixes learns that they didn't come.
    github = commented(Unavailable())

    assert fix_command(homedarts(tmp_path), github, tmp_path / "output") == 2
    assert capsys.readouterr().err.startswith("blueprint.py: GitHub answered 503")


@pytest.mark.parametrize("event", ["schedule", "workflow_dispatch"])
def test_fix_collect_takes_the_weekly_run_of_main(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], event: str
) -> None:
    github = FakeGitHub()
    github.runs = [run_of(1, "Lint")]
    github.artifacts = {1: [{"name": "fixes-lint"}]}
    github.downloads = {(1, "fixes-lint"): {"app.py": b"x = 2\n"}}
    output = tmp_path / "output"

    code = cli.main(
        [
            "--repo",
            REPO,
            "fix",
            "collect",
            "1",
            "--sha",
            SHA,
            "--event",
            event,
            "--branch",
            "main",
            "--folder",
            str(tmp_path / "fixes"),
            "--output",
            str(output),
        ],
        api=api_of(github),
        root=homedarts(tmp_path / "main"),
    )

    assert code == 0
    assert output.read_text(encoding="utf-8") == "action=pull-request\npull=\n"
    assert capsys.readouterr().out == "main needs fixes that a command makes.\n"


def test_fix_collect_leaves_open_the_pull_request_of_fixes_that_expired(
    tmp_path: Path,
) -> None:
    # A failed scanner starts the bot on main, where Lint's fixes of days ago are gone.
    github = FakeGitHub()
    github.pulls.append({"number": 9, "state": "open", "head": {"ref": BRANCH}})
    github.runs = [run_of(1, "Lint"), run_of(2, "CodeQL")]
    github.artifacts = {1: [{"name": "fixes-lint", "expired": True}]}
    output = tmp_path / "output"

    code = cli.main(
        [
            "--repo",
            REPO,
            "fix",
            "collect",
            "2",
            "--sha",
            SHA,
            "--event",
            "schedule",
            "--branch",
            "main",
            "--folder",
            str(tmp_path / "fixes"),
            "--output",
            str(output),
        ],
        api=api_of(github),
        root=homedarts(tmp_path / "main"),
    )

    assert code == 0
    assert output.read_text(encoding="utf-8") == "action=\npull=\n"


def test_fix_collect_without_an_output_only_says_what_it_decided(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # On a machine, without $GITHUB_OUTPUT, the decision goes to the terminal alone.
    github = FakeGitHub()
    github.pull()
    github.runs = [run_of(1, "Lint")]
    github.artifacts = {1: [{"name": "fixes-check"}]}
    github.downloads = {(1, "fixes-check"): {"app.py": b"x = 2\n"}}

    code = cli.main(
        [
            "--repo",
            REPO,
            "fix",
            "collect",
            "1",
            "--sha",
            SHA,
            "--event",
            "pull_request",
            "--branch",
            "feature",
            "--pull",
            "42",
            "--folder",
            str(tmp_path / "fixes"),
        ],
        api=api_of(github),
        root=homedarts(tmp_path / "main"),
    )

    assert code == 0
    assert capsys.readouterr().out == "#42 comes from a branch of this repository.\n"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["fixes", "main"]


def test_fix_collect_stops_a_loop(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    github = FakeGitHub()
    github.pull()
    github.runs = [run_of(1, "Lint")]
    github.artifacts = {1: [{"name": "fixes-check"}]}
    github.downloads = {(1, "fixes-check"): {"app.py": b"x = 2\n"}}
    github.commits[SHA] = bot_commit("b" * 40)
    github.commits["b" * 40] = bot_commit("c" * 40)

    code = cli.main(
        [
            "--repo",
            REPO,
            "fix",
            "collect",
            "1",
            "--sha",
            SHA,
            "--event",
            "pull_request",
            "--branch",
            "feature",
            "--folder",
            str(tmp_path / "fixes"),
        ],
        api=api_of(github),
        root=homedarts(tmp_path / "main"),
    )

    assert code == 1
    said = capsys.readouterr()
    assert said.err.startswith("::error::The commands of the checks changed")
    assert said.out.startswith("The commands of the checks changed")


@pytest.mark.parametrize(
    ("sha", "pull"), [("abc", "1"), (SHA, "1; rm"), ("A" * 40, "")]
)
def test_the_bot_takes_only_a_commit_and_a_number(
    sha: str, pull: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = cli.main(
        ["fix", "suggest", "--sha", sha, "--pull", pull, "--folder", str(tmp_path)],
        api=api_of(FakeGitHub()),
    )

    assert code == 2
    assert "a commit is 40 hex digits" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("fork", "action", "said"),
    [
        (False, "commit", "The fix bot committed c0ffee0"),
        (True, "suggest", "Suggested 1 fix(es) on #42."),
    ],
)
def test_a_check_in_a_workflow_of_the_project_fixes_itself(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    fork: bool,
    action: str,
    said: str,
) -> None:
    # The end-to-end tests of HomeDarts for Autodarts fail and keep a fix; Lint passes.
    # From the end of their run to the commit, or the suggestion on a fork.
    github = FakeGitHub()
    github.pull(fork=fork)
    github.patches = {"app.py": "@@ -1 +1 @@\n-x = 1\n+x = 1\n"}
    github.runs = [run_of(1, "Lint", conclusion="success"), run_of(2, "Docker E2E")]
    github.artifacts = {2: [{"name": "fixes-e2e"}]}
    github.downloads = {(2, "fixes-e2e"): {"app.py": b"x = 2\n"}}
    root = homedarts(tmp_path)
    output = tmp_path / "output"

    assert fix_collect(root, github, output, run="2") == 0
    assert f"action={action}\n" in output.read_text(encoding="utf-8")
    capsys.readouterr()

    place = (
        ["--pull", "42"]
        if fork
        else ["--branch", "feature", "--app", "app", "--url", "u"]
    )
    code = cli.main(
        [
            "--repo",
            REPO,
            "fix",
            action,
            "--sha",
            SHA,
            *place,
            "--folder",
            str(tmp_path / "fixes"),
        ],
        api=api_of(github),
    )

    assert code == 0
    assert capsys.readouterr().out.startswith(said)
    assert github.graphql if not fork else github.reviews


def fix_bot_starts(
    name: str,
    event: str = "pull_request",
    conclusion: str = "failure",
    branch: str = "feature",
    head: str = REPO,
    fork: bool = False,
    heads: Sequence[str] = (SHA,),
) -> bool:
    """Whether the job of the fix bot starts after a run, by its condition, whose few
    expressions Python reads alike. heads are those of the open pull requests of its
    branch, which the event names."""
    condition = condition_of(workflow_steps.job("after-checks.yml", "fixes"))
    expression = re.sub(r"!(?!=)", " not ", condition)
    expression = expression.replace("&&", " and ").replace("||", " or ")
    expression = expression.replace(
        "contains(github.event.workflow_run.pull_requests.*.head.sha, "
        "github.event.workflow_run.head_sha)",
        "github.event.workflow_run.head_sha in heads",
    )
    run = SimpleNamespace(
        name=name,
        event=event,
        conclusion=conclusion,
        head_sha=SHA,
        head_branch=branch,
        head_repository=SimpleNamespace(full_name=head),
    )
    return bool(
        eval(
            expression,
            {
                "heads": heads,
                "github": SimpleNamespace(
                    repository=REPO,
                    event=SimpleNamespace(
                        workflow_run=run,
                        repository=SimpleNamespace(fork=fork, default_branch="main"),
                    ),
                ),
                "contains": lambda items, item: item in items,
                "fromJSON": json.loads,
            },
        )
    )


@pytest.mark.parametrize(
    "name",
    ["Lint", "CI (python)", "Docker E2E", "Visual check", "CodeQL", "Docs"],
)
def test_the_fix_bot_starts_after_every_workflow_that_failed(name: str) -> None:
    assert fix_bot_starts(name)
    assert fix_bot_starts(name, "push", branch="main")
    assert not fix_bot_starts(name, "push", "cancelled", "main")
    # Also in a weekly run of main, by its schedule or by hand.
    assert fix_bot_starts(name, "schedule", branch="main")
    assert fix_bot_starts(name, "workflow_dispatch", branch="main")
    # Not on another branch or event, not for a fork's main, not in a fork.
    assert not fix_bot_starts(name, "push")
    assert not fix_bot_starts(name, "schedule")
    assert not fix_bot_starts(name, "repository_dispatch", branch="main")
    assert not fix_bot_starts(name, "push", branch="main", head="someone/r")
    assert not fix_bot_starts(name, fork=True)


@pytest.mark.parametrize(
    ("name", "starts"),
    [
        ("Lint", True),
        ("Docs", True),
        ("CI (python)", True),
        # A project's own check may keep fixes, and a late one has to close their pull
        # request. Those that never keep one have nothing to say about main.
        ("Docker E2E", True),
        ("Visual check", True),
        ("Windows", False),
        ("Downstream", False),
        ("CodeQL", False),
        ("Release", False),
    ],
)
def test_the_fix_bot_looks_at_main_after_its_checks_passed(
    name: str, starts: bool
) -> None:
    assert fix_bot_starts(name, "push", "success", "main") is starts


def one_job(root: Path, github: FakeGitHub, output: Path, run: str) -> str:
    """What the job of the fix bot decides after a run, on a runner of its own."""
    shutil.rmtree(root / "fixes", ignore_errors=True)
    output.unlink(missing_ok=True)
    assert fix_collect(root, github, output, run=run) == 0
    return output.read_text(encoding="utf-8").splitlines()[0].removeprefix("action=")


def commit_of_the_job(root: Path, github: FakeGitHub) -> int:
    """Commits what the job collected, as its next step does."""
    return cli.main(
        [
            "--repo",
            REPO,
            "fix",
            "commit",
            "--sha",
            SHA,
            "--branch",
            "feature",
            "--app",
            "app",
            "--url",
            "u",
            "--folder",
            str(root / "fixes"),
        ],
        api=api_of(github),
    )


def committed_paths(github: FakeGitHub) -> set[str]:
    changes = github.graphql[0]["variables"]["input"]["fileChanges"]
    return {item["path"] for item in changes["additions"]}


def a_commit_with_a_late_run(fork: bool = False) -> FakeGitHub:
    """Lint failed and kept a fix, and the end-to-end tests of the commit still run."""
    github = FakeGitHub()
    github.pull(fork=fork)
    github.files = {"README.md": b"# Title \n", "app.py": b"x = 1\n"}
    github.runs = [
        run_of(1, "Lint"),
        run_of(2, "Docker E2E", status="in_progress", conclusion=""),
    ]
    github.artifacts = {1: [{"name": "fixes-lint"}], 2: [{"name": "fixes-e2e"}]}
    github.downloads = {
        (1, "fixes-lint"): {"README.md": b"# Title\n"},
        (2, "fixes-e2e"): {"app.py": b"x = 2\n"},
    }
    return github


@pytest.mark.parametrize(
    ("conclusion", "paths"),
    [
        ("failure", {"README.md", "app.py"}),
        ("success", {"README.md"}),
        ("cancelled", {"README.md"}),
        ("timed_out", {"README.md"}),
    ],
)
def test_the_job_after_the_run_that_ends_last_commits_every_fix_once(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    conclusion: str,
    paths: set[str],
) -> None:
    monkeypatch.setattr(blueprint.fixes, "WAITS", 0)
    github = a_commit_with_a_late_run()
    root = homedarts(tmp_path)
    output = tmp_path / "output"

    # The job after Lint has waited as long as it may, and commits nothing.
    assert one_job(root, github, output, "1") == ""
    said = capsys.readouterr().out
    assert said.startswith(f"Still running after the wait for {SHA[:7]}: `Docker E2E`.")
    assert github.writes() == [
        call for call in github.writes() if call.startswith("gh run download")
    ]

    # However the run ends, its end starts the job, which finds the fix of Lint: none lost.
    github.runs[1].update(status="completed", conclusion=conclusion)
    assert fix_bot_starts("Docker E2E", conclusion=conclusion)
    assert one_job(root, github, output, "2") == "commit"
    assert commit_of_the_job(root, github) == 0
    assert len(github.graphql) == 1
    assert committed_paths(github) == paths

    # A job of the same commit that waited behind it finds the new head: none twice.
    github.pulls[0]["head"]["sha"] = MADE
    capsys.readouterr()
    assert one_job(root, github, output, "2") == ""
    assert "no longer the head" in capsys.readouterr().out
    assert len(github.graphql) == 1


def test_a_run_that_ends_during_the_wait_needs_no_job_of_its_own(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The job that waits sees the end at its last look and commits; the job of that run,
    # which waited behind it in the group of the branch, then finds the new head.
    monkeypatch.setattr(blueprint.fixes, "WAITS", 1)
    github = a_commit_with_a_late_run()
    root = homedarts(tmp_path)
    workflows = watched(root)
    api = api_of(github)

    def wait(_: float) -> None:
        github.runs[1].update(status="completed", conclusion="failure")

    found = collect(
        api,
        REPO,
        1,
        SHA,
        "pull_request",
        "feature",
        root / "fixes",
        downloader(api, REPO),
        workflows,
        wait,
    )

    assert found.late == ()
    decided = plan(
        api,
        REPO,
        SHA,
        "pull_request",
        "feature",
        42,
        load(found.folders),
        workflows.listed,
        found.late,
    )
    assert decided.action == "commit"
    assert commit_of_the_job(root, github) == 0
    assert committed_paths(github) == {"README.md", "app.py"}

    github.pulls[0]["head"]["sha"] = MADE
    assert one_job(root, github, tmp_path / "output", "2") == ""
    assert len(github.graphql) == 1


def test_a_commit_of_the_bot_counts_only_once_its_run_has_ended(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The commit before was the bot's as well, so this is its last one in a row: it goes
    # to all the fixes of the commit, not to a part that leaves none for what ends later,
    # and a stop waits as well until it is certain that there is something to stop for.
    monkeypatch.setattr(blueprint.fixes, "WAITS", 0)
    github = a_commit_with_a_late_run()
    github.commits[SHA] = bot_commit("b" * 40)
    github.commits["b" * 40] = bot_commit("c" * 40)
    root = homedarts(tmp_path)
    output = tmp_path / "output"

    assert one_job(root, github, output, "1") == ""
    assert "Still running" in capsys.readouterr().out

    github.runs[1].update(status="completed", conclusion="failure")
    output.unlink()
    assert fix_collect(root, github, output, run="2") == 1
    assert "changed the files of the fix bot" in capsys.readouterr().err
    # The step that speaks on the pull request knows this from a job that merely failed.
    assert output.read_text(encoding="utf-8") == "stopped=true\n"


def test_a_fork_gets_the_suggestions_of_what_has_ended(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A suggestion starts no checks and comes once, so there is no reason to hold it back;
    # the run that ends later adds its own when it fails, and starts no job when it passes.
    monkeypatch.setattr(blueprint.fixes, "WAITS", 0)
    github = a_commit_with_a_late_run(fork=True)

    assert one_job(homedarts(tmp_path), github, tmp_path / "output", "1") == "suggest"
    assert capsys.readouterr().out == "#42 comes from a fork.\n"
    assert (tmp_path / "fixes/1-fixes-lint").is_dir()


def fix_collect_of_main(
    root: Path, github: FakeGitHub, folder: Path, output: Path, event: str
) -> str:
    """What fix collect writes for a run of main."""
    output.unlink(missing_ok=True)
    assert (
        cli.main(
            [
                "--repo",
                REPO,
                "fix",
                "collect",
                "1",
                "--sha",
                SHA,
                "--event",
                event,
                "--branch",
                "main",
                "--folder",
                str(folder),
                "--output",
                str(output),
            ],
            api=api_of(github),
            root=root,
        )
        == 0
    )
    return output.read_text(encoding="utf-8")


def test_a_late_run_on_main_leaves_the_pull_request_of_its_fixes_open(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(blueprint.fixes, "WAITS", 0)
    github = FakeGitHub()
    github.pulls = [
        {"number": 7, "state": "open", "head": {"ref": BRANCH, "repo": {}}},
    ]
    github.runs = [
        run_of(1, "Lint", conclusion="success"),
        run_of(2, "CI (home-assistant)", status="in_progress", conclusion=""),
    ]
    output = tmp_path / "output"
    root = homedarts(tmp_path / "main")
    folder = tmp_path / "fixes"

    # Lint passed, and the tests that still run may need these fixes again.
    assert (
        fix_collect_of_main(root, github, folder, output, "push") == "action=\npull=\n"
    )
    said = capsys.readouterr().out
    assert said.startswith(
        f"Still running after the wait for {SHA[:7]}: `CI (home-assistant)`."
    )
    assert "#7 stays open" in said

    # They pass as well: main needs the fixes no more.
    github.runs[1].update(status="completed", conclusion="success")
    assert fix_bot_starts("CI (home-assistant)", "push", "success", "main")
    assert fix_bot_starts("Docker E2E", "push", "success", "main")
    assert (
        fix_collect_of_main(root, github, folder, output, "push")
        == "action=close\npull=\n"
    )


def test_a_late_run_on_main_holds_back_no_fix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The pull request of main cancels no run of main, and the job that follows brings it
    # up to date: unlike a branch, a part of the fixes costs nothing there. And a weekly
    # run that passes starts no job, so nothing would come after it.
    monkeypatch.setattr(blueprint.fixes, "WAITS", 0)
    github = FakeGitHub()
    github.runs = [
        run_of(1, "Lint"),
        run_of(2, "CI (home-assistant)", status="in_progress", conclusion=""),
    ]
    github.artifacts = {1: [{"name": "fixes-lint"}]}
    github.downloads = {(1, "fixes-lint"): {"app.py": b"x = 2\n"}}

    assert (
        fix_collect_of_main(
            homedarts(tmp_path / "main"),
            github,
            tmp_path / "fixes",
            tmp_path / "output",
            "schedule",
        )
        == "action=pull-request\npull=\n"
    )
    assert not fix_bot_starts("CI (home-assistant)", "schedule", "success", "main")


# How a run can end but by failing, as GitHub names it.
ENDS = ("success", "cancelled", "timed_out", "skipped", "neutral", "startup_failure")


@pytest.mark.parametrize("conclusion", ENDS)
@pytest.mark.parametrize("name", ["Lint", "CI (python)", "Docker E2E", "Visual check"])
def test_a_run_of_a_check_starts_the_fix_bot_however_it_ends(
    name: str, conclusion: str
) -> None:
    # Whichever run of the commit ends last has to find the fixes of the others, and the
    # condition of the job can't know which workflows keep fixes.
    assert fix_bot_starts(name, conclusion=conclusion)
    # Not for a commit that a newer push replaced, or a pull request that has closed.
    assert not fix_bot_starts(name, conclusion=conclusion, heads=())
    assert not fix_bot_starts(name, conclusion=conclusion, heads=("other",))
    # Nor for a fork, whose suggestions wait for nothing, nor in a fork of the repository.
    assert not fix_bot_starts(name, conclusion=conclusion, head="someone/r")
    assert not fix_bot_starts(name, conclusion=conclusion, fork=True)


@pytest.mark.parametrize(
    "name",
    [
        "Variants",
        "Windows",
        "Issue assistant sync",
        "Downstream",
        "CodeQL",
        "Dependency review",
        "Docs",
        "Pull request title",
        "Secret scan",
        "Fuzzing",
        "Links",
        "OSV-Scanner",
        "Workflow security",
        "Renovate",
        "Release",
    ],
)
def test_a_workflow_that_keeps_nothing_starts_the_fix_bot_only_when_it_fails(
    name: str,
) -> None:
    assert fix_bot_starts(name)
    for conclusion in ENDS:
        assert not fix_bot_starts(name, conclusion=conclusion)


def test_the_list_of_those_that_keep_nothing_names_no_workflow_that_does() -> None:
    condition = condition_of(workflow_steps.job("after-checks.yml", "fixes"))
    left_out, of_main = re.findall(r"!contains\(fromJSON\('(\[[^']*\])'\)", condition)

    assert left_out == of_main
    # Docs keeps nothing on a pull request, which is why the bot doesn't wait for it.
    assert "Docs" in json.loads(left_out)
    assert not watched(ROOT).awaited("pull_request") & set(json.loads(left_out))


def test_fix_commit_suggest_and_main_from_the_command_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "fixes"
    kept(folder / "1-fixes-check", {"app.py": "x = 2\n"})
    github = FakeGitHub()

    assert (
        cli.main(
            [
                "--repo",
                REPO,
                "fix",
                "commit",
                "--sha",
                SHA,
                "--branch",
                "feature",
                "--app",
                "app",
                "--url",
                "u",
                "--folder",
                str(folder),
            ],
            api=api_of(github),
        )
        == 0
    )
    assert capsys.readouterr().out.startswith("The fix bot committed c0ffee0")

    fork = FakeGitHub()
    fork.pull(fork=True)
    fork.patches = {"app.py": "@@ -1 +1 @@\n-x\n+x = 1\n"}
    assert (
        cli.main(
            [
                "--repo",
                REPO,
                "fix",
                "suggest",
                "--sha",
                SHA,
                "--pull",
                "42",
                "--folder",
                str(folder),
            ],
            api=api_of(fork),
        )
        == 0
    )
    assert capsys.readouterr().out == "Suggested 1 fix(es) on #42.\n"

    main = FakeGitHub()
    assert (
        cli.main(
            [
                "--repo",
                REPO,
                "fix",
                "main",
                "--sha",
                SHA,
                "--base",
                "main",
                "--app",
                "app",
                "--url",
                "u",
                "--folder",
                str(tmp_path / "missing"),
            ],
            api=api_of(main),
        )
        == 0
    )
    assert capsys.readouterr().out == "main needs no fix that a command makes.\n"


# ---------------------------------------------------------------- the title and the entry


def own_pull(
    github: FakeGitHub,
    title: str = "feat: add a dark mode",
    ref: str = "feat/dark-mode",
    author: str = "User",
    labels: Sequence[str] = (),
    fork: bool = False,
) -> None:
    """The pull request of a person, from a branch at the commit of the checks."""
    github.pull(labels=labels, fork=fork)
    github.pulls[0].update(title=title, user={"type": author})
    github.pulls[0]["head"]["ref"] = ref
    github.refs[ref] = SHA


def draft_commit() -> dict[str, Any]:
    return {"commit": {"message": f"{DRAFT_HEADLINE}\n\nMade from the title"}}


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("feat: add a dark mode", "### Features\n\n- Add a dark mode.\n"),
        ("fix: keep the token secret.", "### Bug fixes\n\n- Keep the token secret.\n"),
        ("perf: read the file once", "### Performance\n\n- Read the file once.\n"),
        ("feat!: drop Python 3.12", "### Breaking changes\n\n- Drop Python 3.12.\n"),
        (
            "fix(ui)!: drop the old look",
            "### Breaking changes\n\n- **ui:** drop the old look.\n",
        ),
        (
            "feat(settings): add a dark mode",
            "### Features\n\n- **settings:** add a dark mode.\n",
        ),
        (
            "fix: `gh` waits for its token",
            "### Bug fixes\n\n- `gh` waits for its token.\n",
        ),
    ],
)
def test_the_draft_of_an_entry_says_what_the_title_says(
    title: str, expected: str
) -> None:
    assert draft_of(title) == expected
    assert fragment_problems([Fragment("changelog.d/a.md", expected)], "") == []


@pytest.mark.parametrize(
    "title",
    [
        # Nothing for users, or no Conventional Commit: the check asks for no entry.
        "docs: add a guide",
        "Add a dark mode",
        # Nothing to say.
        "feat: ...",
        # What the bot writes into a page and into the notes of a release stays text.
        "fix: the <details> stay open",
        "fix: thank @someone for the report",
        "feat: a [link](https://example.com) of its own",
        "fix: see https://example.com",
        "fix: see HTTP://example.com",
        "feat: open www.example.com",
        # A mark of a block of Markdown, which would make the entry that block, and
        # other punctuation, which starts no sentence.
        "fix: # heading",
        "fix: - item",
        "feat: * item",
        "fix: + item",
        "fix: > quote",
        "fix: 1. first",
        "fix: 1) first",
        "fix: | cell",
        "fix: , and more",
        "fix:: double",
        "fix: --- rule",
        "fix: . end",
        "fix: / root",
        "fix: $HOME expands",
    ],
)
def test_a_title_that_could_be_more_than_words_gets_no_draft(title: str) -> None:
    assert draft_of(title) == ""


@given(st.text(min_size=1), st.sampled_from(["feat", "fix", "perf", "feat!", "fix(a)"]))
def test_every_draft_is_a_fragment_that_the_release_takes_in(
    words: str, kind: str
) -> None:
    text = draft_of(f"{kind}: {words}")
    if not text:
        return
    assert fragment_problems([Fragment("changelog.d/a.md", text)], "") == []
    assert text.count("\n") == 3
    assert not re.search(r"[<@]|\]\(|://|\bwww\.", text, re.I)
    # One item of a list, whose words begin as words, never a second mark of a block.
    entry = text.splitlines()[2]
    assert re.match(
        r"- (\*\*\S|[^\W_]|[`\"'\u201c\u2018\u201e(]|(?:[./]|--?)[^\W_])", entry
    ), entry
    assert not re.match(r"- \d+[.)](\s|$)", entry), entry


@pytest.mark.parametrize(
    ("branch", "taken", "expected"),
    [
        ("feat/dark-mode", (), "changelog.d/dark-mode.md"),
        ("feature/dark-mode", (), "changelog.d/dark-mode.md"),
        ("dark-mode", (), "changelog.d/dark-mode.md"),
        ("feat-dark-mode", (), "changelog.d/feat-dark-mode.md"),
        # A folder that is no type stays in the name.
        ("dennis/dark-mode", (), "changelog.d/dennis-dark-mode.md"),
        ("feat/ui/dark mode!", (), "changelog.d/ui-dark-mode.md"),
        ("feat/.hidden.", (), "changelog.d/hidden.md"),
        # A branch of nothing but signs takes the number of the pull request.
        ("feat/---", (), "changelog.d/pull-42.md"),
        ("feat/" + "a" * 300, (), "changelog.d/" + "a" * 80 + ".md"),
        # The entry of another pull request that waits for its release stays its own.
        ("feat/dark-mode", ("changelog.d/dark-mode.md",), "changelog.d/dark-mode-2.md"),
        (
            "feat/dark-mode",
            ("changelog.d/Dark-Mode.md", "changelog.d/dark-mode-2.md"),
            "changelog.d/dark-mode-3.md",
        ),
        # When in doubt, the bot commits nothing.
        (
            "feat/x",
            ("changelog.d/x.md", *(f"changelog.d/x-{n}.md" for n in range(2, 10))),
            "",
        ),
    ],
)
def test_the_name_of_a_draft_comes_from_the_branch_and_is_free(
    branch: str, taken: Sequence[str], expected: str
) -> None:
    path = fragment_path(branch, taken, 42)

    assert path == expected
    if path:
        assert allowed(path)
        assert (
            fragment_problems([Fragment(path, "### Features\n\n- A card.\n")], "") == []
        )


@given(st.text(), st.lists(st.text()))
def test_every_name_of_a_draft_is_one_new_file_of_the_fragments(
    branch: str, taken: list[str]
) -> None:
    path = fragment_path(branch, taken, 42)
    if path:
        assert re.fullmatch(r"changelog\.d/[A-Za-z0-9][A-Za-z0-9._-]*\.md", path)
        assert path.lower() not in {name.lower() for name in taken}


def needs(title: str, author: str, files: Sequence[tuple[str, str]]) -> bool:
    return needs_entry(
        title,
        {"user": {"type": author}},
        [{"filename": name, "status": status} for name, status in files],
    )


# The pull requests of the check of the title: whether the bot drafts an entry, and the
# exit code of the check, which fails for a missing entry and for a file that is no
# fragment.
ENTRY_CASES = [
    ("feat: a card", "User", [], True, 1),
    ("fix: a crash", "User", [("app.py", "modified")], True, 1),
    ("perf(api): quicker", "User", [("app.py", "modified")], True, 1),
    ("feat!: a card", "User", [("changelog.d/.gitkeep", "added")], True, 1),
    # A fragment that main has already is the entry of another pull request.
    ("feat: a card", "User", [("changelog.d/old.md", "modified")], True, 1),
    ("feat: a card", "User", [("changelog.d/old.md", "renamed")], True, 1),
    ("feat: a card", "User", [("changelog.d/old.md", "removed")], True, 1),
    ("feat: a card", "User", [("CHANGELOG.md", "removed")], True, 1),
    # An entry of its own.
    ("feat: a card", "User", [("changelog.d/card.md", "added")], False, 0),
    ("feat: a card", "User", [("changelog.d/card.md", "copied")], False, 0),
    ("feat: a card", "User", [("CHANGELOG.md", "modified")], False, 0),
    # Nothing for users, or an update, or a bot.
    ("docs: a guide", "User", [], False, 0),
    ("Feat: a card", "User", [], False, 0),
    ("feat: a card", "Bot", [], False, 0),
    ("fix(deps): bump", "User", [], False, 0),
    ("fix(deps-dev): bump", "User", [], False, 0),
    # A file that is no fragment fails by itself, and its author meant one.
    ("feat: a card", "User", [("changelog.d/my fix.md", "added")], False, 1),
    ("feat: a card", "User", [("changelog.d/notes.txt", "added")], False, 1),
]


@pytest.mark.parametrize(("title", "author", "files", "expected", "code"), ENTRY_CASES)
def test_the_bot_asks_for_an_entry_where_the_check_does(
    title: str,
    author: str,
    files: Sequence[tuple[str, str]],
    expected: bool,
    code: int,
) -> None:
    assert needs(title, author, files) is expected


@needs_bash
@pytest.mark.skipif(
    shutil.which("jq") is None, reason="the check of the entry needs jq"
)
@pytest.mark.parametrize(("title", "author", "files", "expected", "code"), ENTRY_CASES)
def test_the_check_of_the_entry_decides_as_the_bot_does(
    tmp_path: Path,
    title: str,
    author: str,
    files: Sequence[tuple[str, str]],
    expected: bool,
    code: int,
) -> None:
    # The check itself, with the same pull requests: when it fails for a missing entry,
    # and only then, the bot drafts one.
    listed = [{"filename": name, "status": status} for name, status in files]
    done = workflow_steps.run_step(
        tmp_path,
        "pull-request-title.yml",
        "title",
        "Require an entry in the changelog for a change for users",
        answers=[Answer(r"api repos/o/r/pulls/42/files .*", json=listed)],
        env={"GH_REPO": REPO, "NUMBER": "42", "TITLE": title, "AUTHOR": author},
    )

    assert done.returncode == code, done.stderr
    assert ("title=No entry in the changelog" in done.stdout) is expected


def test_a_title_in_the_wrong_form_is_corrected_alone() -> None:
    github = FakeGitHub()
    own_pull(github, title="Docs: Add a guide")

    found = own_fix(api_of(github), REPO, SHA, 42)

    assert (found.number, found.title, found.path) == (42, "docs: add a guide", "")
    # Deciding writes nothing.
    assert github.writes() == []

    said = fix_own(api_of(github), REPO, SHA, 42, "app", "https://run")

    assert github.pulls[0]["title"] == "docs: add a guide"
    assert github.writes() == [f"PATCH repos/{REPO}/pulls/42"]
    assert github.graphql == []
    assert said == (
        "The fix bot set the title of #42 to `docs: add a guide`: only its form "
        "differed, and its type and breaking mark decide the version.\n"
    )


def test_a_pull_request_without_its_entry_gets_one_draft_as_a_new_file() -> None:
    github = FakeGitHub()
    own_pull(github)

    said = fix_own(api_of(github), REPO, SHA, 42, "app", "https://run")

    (request,) = github.graphql
    change = request["variables"]["input"]
    assert change["expectedHeadOid"] == SHA
    assert change["branch"]["branchName"] == "feat/dark-mode"
    assert change["message"] == {
        "headline": DRAFT_HEADLINE,
        "body": "Made from the title of the pull request after https://run\n\n"
        "Signed-off-by: app[bot] <41898282+app[bot]@users.noreply.github.com>",
    }
    # Exactly one new file, which the bot built itself, and nothing else.
    assert change["fileChanges"] == {
        "additions": [
            {
                "path": "changelog.d/dark-mode.md",
                "contents": base64.b64encode(
                    b"### Features\n\n- Add a dark mode.\n"
                ).decode(),
            }
        ]
    }
    assert "PATCH" not in " ".join(github.writes())
    assert said == (
        "The fix bot committed c0ffee0, a draft of the entry of the changelog from the "
        "title: `changelog.d/dark-mode.md`. Read it, and say in the words of a user what "
        "changes for them.\n"
    )


def test_a_corrected_title_and_its_draft_come_together() -> None:
    # The check asks for no entry as long as the title is no Conventional Commit, so the
    # bot looks at the title that it sets; a second run would only cost a runner.
    github = FakeGitHub()
    own_pull(github, title="Fix: Crash on save.", ref="fix/save")

    said = fix_own(api_of(github), REPO, SHA, 42, "app", "https://run")

    assert github.pulls[0]["title"] == "fix: crash on save"
    (request,) = github.graphql
    (added,) = request["variables"]["input"]["fileChanges"]["additions"]
    assert added["path"] == "changelog.d/save.md"
    assert base64.b64decode(added["contents"]) == (
        b"### Bug fixes\n\n- Crash on save.\n"
    )
    # The title first: a commit starts the checks of the title anew.
    assert [call.split()[0] for call in github.writes()] == ["PATCH", "POST"]
    assert said.count("\n") == 2


def test_the_draft_keeps_clear_of_the_files_of_the_commit() -> None:
    github = FakeGitHub()
    own_pull(github)
    github.files = {"changelog.d/dark-mode.md": b"### Features\n\n- Another card.\n"}

    found = own_fix(api_of(github), REPO, SHA, 42)

    assert found.path == "changelog.d/dark-mode-2.md"
    assert "Another card" not in found.draft


def test_the_draft_keeps_clear_of_a_fragment_of_the_base_branch() -> None:
    # A branch that is behind has no such file, but it would conflict with main.
    github = FakeGitHub()
    own_pull(github)
    github.files = {"README.md": b"# A project\n"}
    github.trees["main"] = {"changelog.d/dark-mode.md": b"### Features\n\n- A card.\n"}

    found = own_fix(api_of(github), REPO, SHA, 42)

    assert found.path == "changelog.d/dark-mode-2.md"


@pytest.mark.parametrize(
    ("change", "said"),
    [
        (
            {"labels": [{"name": OPT_OUT}]},
            f"#42 has the label {OPT_OUT}: the bot leaves it alone.\n",
        ),
        (
            {"head": {"sha": SHA, "ref": "x", "repo": {"full_name": "someone/r"}}},
            "#42 comes from a fork, which the bot leaves to the PR coach.\n",
        ),
        (
            {"head": {"sha": "b" * 40, "ref": "x", "repo": {"full_name": REPO}}},
            "aaaaaaa is no longer the head of an open pull request.\n",
        ),
        (
            {"state": "closed"},
            "aaaaaaa is no longer the head of an open pull request.\n",
        ),
    ],
)
def test_the_title_and_the_entry_leave_a_pull_request_alone(
    change: dict[str, Any], said: str
) -> None:
    github = FakeGitHub()
    own_pull(github, title="Feat: a card")
    github.pulls[0].update(change)

    assert fix_own(api_of(github), REPO, SHA, 42, "app", "https://run") == said
    assert github.writes() == []


NOTHING = (
    "#42 has nothing that the bot corrects or drafts by itself; the check says what it "
    "needs.\n"
)


@pytest.mark.parametrize(
    "title",
    [
        # The type is unclear: the PR coach suggests, as ever.
        "Add a dark mode",
        "Feature: add a dark mode",
        # A draft that would be more than words.
        "fix: the <details> stay open",
    ],
)
def test_the_bot_commits_nothing_when_in_doubt(title: str) -> None:
    github = FakeGitHub()
    own_pull(github, title=title)

    assert fix_own(api_of(github), REPO, SHA, 42, "app", "https://run") == NOTHING
    assert github.writes() == []


def test_a_pull_request_that_needs_no_fragment_gets_none() -> None:
    github = FakeGitHub()
    own_pull(github)
    github.patches = {"changelog.d/card.md": ""}
    github.statuses = {"changelog.d/card.md": "added"}

    assert own_fix(api_of(github), REPO, SHA, 42).path == ""


def test_the_bot_drafts_once_for_each_pull_request() -> None:
    # Whoever deleted the draft doesn't want it: the check explains from now on.
    github = FakeGitHub()
    own_pull(github)
    github.pull_commits = [{"commit": {"message": "feat: a card"}}, draft_commit()]

    assert fix_own(api_of(github), REPO, SHA, 42, "app", "https://run") == NOTHING
    assert github.graphql == []


def test_a_branch_that_moved_on_gets_its_draft_from_its_own_checks() -> None:
    github = FakeGitHub()
    own_pull(github)

    def push(github: FakeGitHub) -> None:
        github.refs["feat/dark-mode"] = "b" * 40

    github.on_commit = push
    github.graphql_fails = True

    assert fix_own(api_of(github), REPO, SHA, 42, "app", "https://run") == (
        "feat/dark-mode moved on from aaaaaaa; its checks fix it again.\n"
    )


def test_a_commit_that_fails_on_a_branch_that_stands_still_says_so() -> None:
    github = FakeGitHub()
    own_pull(github)
    github.graphql_fails = True

    with pytest.raises(GitHubError, match="Expected branch"):
        fix_own(api_of(github), REPO, SHA, 42, "app", "https://run")


def test_a_fix_of_the_checks_never_adds_a_fragment() -> None:
    # The exception is the draft that the bot builds itself: a file that a check kept
    # stays a fix of a file that the commit has already, also in changelog.d/.
    github = FakeGitHub()
    fixes = Fixes({"changelog.d/new.md": b"### Features\n\n- A card.\n"})

    said = commit_onto_branch(
        api_of(github), REPO, "feature", SHA, fixes, "app", "https://run"
    )

    assert github.graphql == []
    assert "the bot changes files, it adds none" in said


def fix_own_command(github: FakeGitHub, *rest: str) -> int:
    return cli.main(
        ["--repo", REPO, "fix", "own", "--sha", SHA, "--pull", "42", *rest],
        api=api_of(github),
    )


def test_fix_own_decides_and_then_fixes_from_the_command_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    github = FakeGitHub()
    own_pull(github, title="Docs: Add a guide")
    output = tmp_path / "output"

    assert fix_own_command(github, "--output", str(output)) == 0
    assert output.read_text(encoding="utf-8") == "action=fix\npull=42\n"
    assert capsys.readouterr().out == (
        "#42 has what the bot fixes by itself:\n\n- the title: `docs: add a guide`\n"
    )
    assert github.writes() == []

    assert fix_own_command(github, "--app", "app", "--url", "https://run") == 0
    assert capsys.readouterr().out.startswith("The fix bot set the title of #42")
    assert github.pulls[0]["title"] == "docs: add a guide"


def test_fix_own_without_an_output_only_says_what_it_decided(
    capsys: pytest.CaptureFixture[str],
) -> None:
    github = FakeGitHub()
    own_pull(github)

    assert fix_own_command(github) == 0
    assert capsys.readouterr().out == (
        "#42 has what the bot fixes by itself:\n\n"
        "- a draft of the entry of the changelog: `changelog.d/dark-mode.md`\n"
    )


def test_fix_own_with_nothing_to_do_starts_no_token(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    github = FakeGitHub()
    own_pull(github, title="Add a dark mode")
    output = tmp_path / "output"

    assert fix_own_command(github, "--output", str(output)) == 0
    assert output.read_text(encoding="utf-8") == "action=\npull=\n"
    assert "nothing that the bot corrects" in capsys.readouterr().out


def test_fix_own_needs_a_commit_by_its_id(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(
        ["--repo", REPO, "fix", "own", "--sha", "main", "--pull", "42"],
        api=api_of(FakeGitHub()),
    )

    assert code == 2
    assert "a commit is 40 hex digits" in capsys.readouterr().err


# ---------------------------------------------------------------- the workflows


# The weekly run of the checks that keep fixes, at one time, so that one commit of the
# fix bot holds what they fix; the template moves the time for each repository.
WEEKLY_RUN = re.compile(
    r'^  schedule:\n(?:    #.*\n)*    - cron: "30 4 \* \* 3"\n', re.MULTILINE
)


@pytest.mark.parametrize(
    "path",
    sorted((ROOT / ".github/workflows").glob("ci-*.yml")),
    ids=lambda path: path.name,
)
def test_the_check_of_each_kind_of_project_keeps_its_fixes(path: Path) -> None:
    check = workflow_steps.job(path.name, "check")
    explain = step_in(check, "Explain the failure")
    name = explain["env"]["CHECK"]
    assert re.fullmatch(r"check \([a-z-]+\)", name)

    fix = step_in(check, "Fix what a command can fix")
    keep_step = step_in(check, "Keep the fixes for the fix bot")

    # Fix first, explain second: the explanation stays the last step.
    steps = check["steps"]
    assert steps.index(fix) < steps.index(keep_step) < steps.index(explain)
    assert steps[-1] == explain
    assert any(
        step.get("with", {}).get("fetch-depth") == 2
        for step in steps
        if step.get("uses", "").startswith("actions/checkout@")
    )
    assert " ".join(condition_of(fix).split()) == (
        'failure() && (contains(fromJSON(\'["pull_request", "push", "schedule"]\'),'
        " github.event_name) || (github.event_name == 'workflow_dispatch' &&"
        " github.ref_name == github.event.repository.default_branch))"
    )
    # Each week on main, so that what no commit changes repairs itself.
    assert WEEKLY_RUN.search(path.read_text(encoding="utf-8"))
    assert fix["env"]["CHECK"] == name
    assert "git checkout --quiet --force --detach HEAD^2" in fix["run"]
    # On main too, only what the commands change is a fix.
    assert "git checkout --quiet --force HEAD -- ." in fix["run"]
    assert 'fix run "$CHECK" --keep "$RUNNER_TEMP/fixes"' in fix["run"]
    # fix version compares the manifest with that of main, other than in the pull
    # request of the release bot, which is a branch of this repository.
    assert fix["env"]["RELEASE"] == (
        "${{ startsWith(github.head_ref, 'release-please--') && "
        "github.event.pull_request.head.repo.full_name == github.repository }}"
    )
    assert fix["run"].index('FIX_BASE="$(git rev-parse HEAD^1)"') < (
        fix["run"].index("git checkout --quiet --force --detach HEAD^2")
    )
    assert condition_of(keep_step) == "failure() && steps.fix.outcome == 'success'"
    assert keep_step["with"]["name"] == "fixes-check"
    assert keep_step["with"]["if-no-files-found"] == "ignore"
    assert keep_step["with"]["include-hidden-files"] is True


def merged(root: Path) -> tuple[str, str]:
    """A repository whose commit is the merge of a pull request into main, as the CI
    checks it out: main and the head of the pull request, as its two parents."""
    git(root, "init", "--quiet", "--initial-branch=main")
    git(root, "config", "commit.gpgsign", "false")
    git(root, "commit", "--quiet", "--allow-empty", "-m", "start")
    git(root, "checkout", "--quiet", "-b", "feature")
    git(root, "commit", "--quiet", "--allow-empty", "-m", "the pull request")
    head = git(root, "rev-parse", "HEAD").strip()
    git(root, "checkout", "--quiet", "main")
    git(root, "commit", "--quiet", "--allow-empty", "-m", "main moved on")
    base = git(root, "rev-parse", "HEAD").strip()
    git(root, "merge", "--quiet", "--no-ff", "--no-edit", "feature")
    return base, head


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize(
    "path",
    sorted((ROOT / ".github/workflows").glob("ci-*.yml")),
    ids=lambda path: path.name,
)
@pytest.mark.parametrize("release", ["false", "true"])
def test_the_fix_step_names_main_for_fix_version(
    tmp_path: Path, path: Path, release: str
) -> None:
    assert BASH
    fix = step_in(workflow_steps.job(path.name, "check"), "Fix what a command can fix")
    taken = fix["run"][: fix["run"].index("script=")]
    base, head = merged(tmp_path)
    environment = {
        name: value for name, value in os.environ.items() if name != "FIX_BASE"
    }

    done = subprocess.run(
        [
            BASH,
            "-eo",
            "pipefail",
            "-c",
            taken + 'printf "%s\\n" "${FIX_BASE-none}" "$(git rev-parse HEAD)"\n',
        ],
        cwd=tmp_path,
        env={**environment, "EVENT": "pull_request", "RELEASE": release},
        capture_output=True,
        encoding="utf-8",
        check=True,
    )

    # The commands run on the head, and fix version reads main from FIX_BASE; the
    # release bot's pull request changes the manifest itself, so it names none.
    assert done.stdout.split() == [base if release == "false" else "none", head]


def test_the_markdown_fixes_itself_on_the_head_of_the_pull_request() -> None:
    # In the job lint, which runs every linter, since its own job markdown is gone.
    lint = workflow_steps.job("lint.yml", "lint")
    steps = lint["steps"]

    # The whole history, with the head of the pull request as the second parent of
    # its merge, onto which the fix bot commits.
    assert any(
        step.get("with", {}).get("fetch-depth") == 0
        for step in steps
        if step.get("uses", "").startswith("actions/checkout@")
    )
    head = step_in(lint, "Take the commit that the fixes start from")
    assert " ".join(condition_of(head).split()) == (
        "${{ !cancelled() && steps.markdown.outcome == 'failure' &&"
        ' (contains(fromJSON(\'["pull_request", "schedule"]\'), github.event_name) ||'
        " (github.event_name == 'workflow_dispatch' &&"
        " github.ref_name == github.event.repository.default_branch)) }}"
    )
    assert head["env"]["EVENT"] == "${{ github.event_name }}"
    assert head["run"] == (
        'if [[ "$EVENT" == pull_request ]]; then\n'
        "  git checkout --quiet --force --detach HEAD^2\n"
        "fi\n"
    )
    fix = step_in(lint, "Fix what markdownlint can fix")
    assert fix["continue-on-error"] is True
    assert fix["with"]["fix"] is True
    # The same action as the check, so that both have one version.
    action = [
        step["uses"]
        for step in steps
        if step.get("uses", "").startswith("DavidAnson/markdownlint-cli2-action@")
    ]
    assert len(action) == 2
    assert len(set(action)) == 1
    keep_step = step_in(lint, "Keep the fixes for the fix bot")
    assert keep_step["with"]["name"] == "fixes-lint"
    assert steps.index(head) < steps.index(fix) < steps.index(keep_step)
    assert steps.index(keep_step) < steps.index(step_in(lint, "Explain the failure"))
    assert (
        'fix keep "$RUNNER_TEMP/fixes"'
        in (step_in(lint, "Keep the files that markdownlint fixed")["run"])
    )


def test_lint_runs_on_main_every_week_without_the_image_of_its_diagrams() -> None:
    text = (ROOT / ".github/workflows/lint.yml").read_text(encoding="utf-8")
    assert WEEKLY_RUN.search(text)
    # The Diagrams workflow looks after the pictures of main: a weekly run, by its
    # schedule or as bot health starts it by hand, pulls no large image for them. The
    # job of a pull request, and of a run by hand on another branch, stays.
    assert condition_of(workflow_steps.job("lint.yml", "diagrams")) == (
        "github.event_name != 'schedule' &&"
        " github.ref_name != github.event.repository.default_branch"
    )


def test_a_weekly_run_starts_the_fix_bot_only_when_it_fails() -> None:
    bot = workflow_steps.job("after-checks.yml", "fixes")
    for event in ("schedule", "workflow_dispatch"):
        assert fix_bot_starts("Lint", event, branch="main")
        assert fix_bot_starts("CI (python)", event, branch="main")
        # A quiet week starts no job of the bot, so it takes no runner.
        assert not fix_bot_starts("Lint", event, "success", "main")
        assert not fix_bot_starts("CI (python)", event, "success", "main")
        # Only that of main, not one by hand on a branch or from a fork.
        assert not fix_bot_starts("Lint", event)
        assert not fix_bot_starts("Lint", event, branch="main", head="someone/r")
    issue = step_in(bot, "Keep the issue of the fix bot of main current")
    assert condition_of(issue) == (
        "always() && github.event.workflow_run.event != 'pull_request'"
        " && steps.blocks.outcome != 'failure'"
    )


def test_the_fix_bot_has_only_what_it_needs() -> None:
    bot = workflow_steps.job("after-checks.yml", "fixes")

    # The token of the job only reads the code, and writes no more than the issue of
    # the bot of main and the suggestions and comments on a pull request.
    assert bot["permissions"] == {
        "actions": "read",
        "contents": "read",
        "issues": "write",
        "pull-requests": "write",
    }
    # Each token of the release app has only what its step needs.
    branch = step_in(bot, "Create a token of the release app for the branch")
    assert permissions_of(branch) == {"permission-contents": "write"}
    main = step_in(bot, "Create a token of the release app for main")
    assert permissions_of(main) == {
        "permission-contents": "write",
        "permission-pull-requests": "write",
        "permission-workflows": "write",
    }
    # It checks out the tool of main, never the code of the pull request.
    [checkout] = [
        step
        for step in bot["steps"]
        if step.get("uses", "").startswith("actions/checkout@")
    ]
    assert checkout["with"]["sparse-checkout"].startswith(".github\nblueprint\n")
    assert "ref" not in checkout["with"]
    assert "github.event.workflow_run.conclusion == 'failure'" in condition_of(bot)
    assert bot["concurrency"]["cancel-in-progress"] is False


def permissions_of(step: dict[str, Any]) -> dict[str, str]:
    """The permissions that a step asks a token of the release app for."""
    return {
        key: value
        for key, value in step["with"].items()
        if key.startswith("permission-")
    }


# gh answers the calls of the steps of the fix bot that write, and python3 runs no
# tool: each call of it is written down.
WRITES = Answer(r"(?:pr comment|issue (?:create|edit|close)) .*")
PR_COMMENTS = Answer(r"pr view \d+ --json comments --jq \.comments\[\]\.body")
PYTHON3 = {"python3": workflow_steps.recording("python3")}


def run_fix_bot_step(
    tmp_path: Path,
    step: str,
    answers: Sequence[Answer] = (WRITES,),
    **variables: str,
) -> workflow_steps.StepResult:
    """Runs a step of the fix bot as GitHub does, with the fake gh."""
    return workflow_steps.run_step(
        tmp_path,
        "after-checks.yml",
        "fixes",
        step,
        answers=answers,
        env=variables,
        stubs=PYTHON3,
    )


@needs_bash
def test_the_steps_of_the_fix_bot_pass_what_the_run_says(tmp_path: Path) -> None:
    runner = (tmp_path / "runner").as_posix()
    output = (tmp_path / "github/output").as_posix()

    done = run_fix_bot_step(
        tmp_path,
        "Collect the fixes of the checks of the commit",
        RUN="5",
        SHA=SHA,
        EVENT="pull_request",
        BRANCH="feature",
        NUMBER="",
    )

    assert done.returncode == 0, done.stderr
    assert done.stubbed == [
        f"python3 blueprint.py --repo {REPO} fix collect 5 --sha {SHA} --event pull_request"
        f" --branch feature --pull  --folder {runner}/fixes --output {output}"
    ]
    for name, action in (
        ("Suggest the fixes on the pull request from a fork", "suggest"),
        ("Commit the fixes onto the branch of the pull request", "commit"),
        ("Keep the pull request with the fixes of main", "main"),
    ):
        done = run_fix_bot_step(
            tmp_path,
            name,
            SHA=SHA,
            PULL="42",
            BRANCH="feature",
            APP_SLUG="app",
            URL="https://run",
            BASE="main",
            UNREAD="",
        )
        assert done.returncode == 0, done.stderr
        assert done.stubbed[0].startswith(
            f"python3 blueprint.py --repo {REPO} fix {action} --sha {SHA}"
        )
        assert done.stubbed[0].endswith(f"--folder {runner}/fixes")
        assert done.calls == []
    # The commit learns from the collect why nobody reads it, and an empty answer
    # stays an answer: the author reads it.
    for unread in ("bot", ""):
        done = run_fix_bot_step(
            tmp_path,
            "Commit the fixes onto the branch of the pull request",
            SHA=SHA,
            BRANCH="feature",
            APP_SLUG="app",
            URL="https://run",
            UNREAD=unread,
        )
        assert done.returncode == 0, done.stderr
        assert f" --branch feature --unread {unread} --app app " in done.stubbed[0]


def title_bot_starts(
    name: str = "Pull request title",
    event: str = "pull_request_target",
    conclusion: str = "failure",
    head: str = REPO,
    fork: bool = False,
    heads: Sequence[str] = (SHA,),
) -> bool:
    """Whether the job of the title and the entry starts after a run, by its condition."""
    condition = condition_of(workflow_steps.job("after-checks.yml", "own-branch"))
    expression = re.sub(r"!(?!=)", " not ", condition)
    expression = expression.replace("&&", " and ").replace("||", " or ")
    expression = expression.replace(
        "contains(github.event.workflow_run.pull_requests.*.head.sha, "
        "github.event.workflow_run.head_sha)",
        "github.event.workflow_run.head_sha in heads",
    )
    run = SimpleNamespace(
        name=name,
        event=event,
        conclusion=conclusion,
        head_sha=SHA,
        head_repository=SimpleNamespace(full_name=head),
    )
    return bool(
        eval(
            expression,
            {
                "heads": heads,
                "github": SimpleNamespace(
                    repository=REPO,
                    event=SimpleNamespace(
                        workflow_run=run,
                        repository=SimpleNamespace(fork=fork),
                    ),
                ),
            },
        )
    )


def test_the_title_and_the_entry_start_the_bot_only_on_a_branch_of_this_repository() -> (
    None
):
    assert title_bot_starts()
    # Only after the check of the title, and only when it failed.
    assert not title_bot_starts(conclusion="success")
    assert not title_bot_starts(conclusion="cancelled")
    assert not title_bot_starts("Lint", "pull_request")
    assert not title_bot_starts("Area labels")
    assert not title_bot_starts(event="pull_request")
    # Not from a fork, and not in one.
    assert not title_bot_starts(head="someone/r")
    assert not title_bot_starts(fork=True)
    # Not for a commit that a newer push replaced, or whose pull request has closed.
    assert not title_bot_starts(heads=("b" * 40,))
    assert not title_bot_starts(heads=())


def test_the_job_of_the_title_and_the_entry_has_only_what_it_needs() -> None:
    job = workflow_steps.job("after-checks.yml", "own-branch")

    assert job["permissions"] == {"contents": "read", "pull-requests": "write"}
    app = step_in(job, "Create a token of the release app for the pull request")
    assert permissions_of(app) == {
        "permission-contents": "write",
        "permission-pull-requests": "write",
    }
    # The token comes only when the bot has something to do.
    assert condition_of(step_in(job, "Check that the release app is set up")) == (
        "steps.own.outputs.action == 'fix'"
    )
    # It checks out the tool of main, never the code of the pull request.
    [checkout] = [
        step
        for step in job["steps"]
        if step.get("uses", "").startswith("actions/checkout@")
    ]
    assert checkout["with"]["sparse-checkout"].startswith(".github\nblueprint\n")
    assert "ref" not in checkout["with"]
    assert job["concurrency"]["cancel-in-progress"] is False
    # A group of its own: a commit of the fix bot takes the place of no job here, and
    # GitHub keeps only one pending job of a group. The commit checks the head itself.
    fixes = workflow_steps.job("after-checks.yml", "fixes")
    assert job["concurrency"]["group"] != fixes["concurrency"]["group"]


@needs_bash
def test_the_steps_of_the_title_and_the_entry_pass_what_the_run_says(
    tmp_path: Path,
) -> None:
    output = (tmp_path / "github/output").as_posix()

    done = workflow_steps.run_step(
        tmp_path,
        "after-checks.yml",
        "own-branch",
        "Decide what the bot fixes of the title and the entry",
        env={"GH_REPO": REPO, "SHA": SHA, "NUMBER": "42"},
        stubs=PYTHON3,
    )

    assert done.returncode == 0, done.stderr
    assert done.stubbed == [
        f"python3 blueprint.py --repo {REPO} fix own --sha {SHA} --pull 42 "
        f"--output {output}"
    ]

    done = workflow_steps.run_step(
        tmp_path,
        "after-checks.yml",
        "own-branch",
        "Set the title and commit the draft of the entry",
        env={
            "GH_REPO": REPO,
            "SHA": SHA,
            "PULL": "42",
            "APP_SLUG": "app",
            "URL": "https://run",
        },
        stubs=PYTHON3,
    )

    assert done.returncode == 0, done.stderr
    assert done.stubbed[-1] == (
        f"python3 blueprint.py --repo {REPO} fix own --sha {SHA} --pull 42 --app app "
        "--url https://run"
    )


@needs_bash
@pytest.mark.parametrize("pull", ["42", ""])
def test_the_job_of_the_title_says_on_the_pull_request_that_it_failed(
    tmp_path: Path, pull: str
) -> None:
    done = workflow_steps.run_step(
        tmp_path,
        "after-checks.yml",
        "own-branch",
        "Say on the pull request that the fix bot failed",
        answers=(WRITES,),
        env={"PULL": pull, "URL": "https://run/9"},
        stubs=PYTHON3,
    )

    assert done.returncode == 0, done.stderr
    if pull:
        assert done.commands == [
            "pr comment 42 --body The fix bot couldn't correct the title or draft the "
            "entry of the changelog of this pull request (https://run/9); its summary "
            "says why. The PR coach says what each needs."
        ]
    else:
        assert done.calls == []


def test_the_explanations_say_what_the_bot_fixes_of_the_title_and_the_entry() -> None:
    catalog = Catalog.load(ROOT)
    for name in ("conventional title", "changelog"):
        entry = catalog.check(name)
        assert entry
        assert "Not yet" not in entry.manual
        assert "#429" not in entry.manual
        assert "the fix bot" in entry.fix


@needs_bash
@pytest.mark.parametrize("pull", ["42", ""])
def test_the_fix_bot_says_on_the_pull_request_that_it_failed(
    tmp_path: Path, pull: str
) -> None:
    done = run_fix_bot_step(
        tmp_path,
        "Say on the pull request that the fix bot failed",
        (WRITES, PR_COMMENTS),
        PULL=pull,
        SHA=SHA,
        URL="https://run/9",
    )

    assert done.returncode == 0, done.stderr
    if pull:
        assert done.called("pr comment") == [
            "pr comment 42 --body The fix bot couldn't fix the findings of this pull "
            "request that a command fixes (https://run/9); its summary says why. The PR "
            "coach names the command of each check that failed, which makes the fixes on "
            f"your machine.<!-- the fix bot failed on {SHA} -->"
        ]
    else:
        assert done.calls == []


@needs_bash
def test_the_fix_bot_says_it_failed_once_for_each_commit(tmp_path: Path) -> None:
    # A job follows every run of a commit, so a stop would repeat itself after each.
    done = run_fix_bot_step(
        tmp_path,
        "Say on the pull request that the fix bot failed",
        (
            WRITES,
            Answer(
                PR_COMMENTS.args,
                out=f"Something else\nIt failed.<!-- the fix bot failed on {SHA} -->\n",
            ),
        ),
        PULL="42",
        SHA=SHA,
        URL="https://run/9",
    )

    assert done.returncode == 0, done.stderr
    assert done.called("pr comment") == []

    # Another commit of the pull request has its own say.
    done = run_fix_bot_step(
        tmp_path,
        "Say on the pull request that the fix bot failed",
        (
            WRITES,
            Answer(
                PR_COMMENTS.args, out="It failed.<!-- the fix bot failed on old -->\n"
            ),
        ),
        PULL="42",
        SHA=SHA,
        URL="https://run/9",
    )

    assert done.returncode == 0, done.stderr
    assert len(done.called("pr comment")) == 1


def test_a_failed_job_after_a_run_that_did_not_fail_says_nothing_without_a_finding() -> (
    None
):
    bot = workflow_steps.job("after-checks.yml", "fixes")
    step = step_in(bot, "Say on the pull request that the fix bot failed")
    assert condition_of(step) == (
        "failure() && github.event.workflow_run.event == 'pull_request' && "
        "(github.event.workflow_run.conclusion == 'failure' || "
        "steps.collect.outputs.stopped == 'true' || "
        "steps.collect.outputs.action != '') && "
        "steps.blocks.outcome != 'failure'"
    )


@needs_bash
@pytest.mark.parametrize(
    ("failed", "issue", "last"),
    [
        (
            "true",
            "",
            "issue create --title The fix bot fails on main --label maintenance --body ",
        ),
        ("true", "7", "issue edit 7 --body "),
        (
            "false",
            "7",
            "issue close 7 --comment The fix bot passes again: https://run/9",
        ),
        ("false", "", ""),
    ],
)
def test_the_fix_bot_of_main_keeps_one_issue_of_its_failures(
    tmp_path: Path, failed: str, issue: str, last: str
) -> None:
    done = run_fix_bot_step(
        tmp_path,
        "Keep the issue of the fix bot of main current",
        (Answer(r"issue list --state open .*", f"{issue}\n" if issue else ""), WRITES),
        FAILED=failed,
        URL="https://run/9",
    )

    assert done.returncode == 0, done.stderr
    made = done.commands
    assert made[0].startswith("issue list --state open --search")
    if last:
        assert made[-1].startswith(last)
    else:
        assert made == made[:1]


# The steps of the fix bot in bash in an outage of GitHub, as on 9 November 2026:
# they end with a notice, their run mails no one, and a write that GitHub failed,
# which it may have done, goes out only once (#786).
SLEEP = {"sleep": workflow_steps.recording("sleep")}
UNAVAILABLE = "HTTP 503: Service Unavailable\n"
NOTICE = "::notice title=GitHub is unavailable::GitHub kept failing (HTTP 50"
SAYS = "Say on the pull request that the fix bot failed"
KEEPS = "Keep the issue of the fix bot of main current"


@needs_bash
@pytest.mark.parametrize(
    ("step", "failing", "variables"),
    [
        (SAYS, r"pr view 42 .*", {"PULL": "42", "SHA": SHA, "URL": "https://run/9"}),
        (KEEPS, r"issue list .*", {"FAILED": "true", "URL": "https://run/9"}),
        (KEEPS, r"issue list .*", {"FAILED": "false", "URL": "https://run/9"}),
    ],
)
def test_a_step_of_the_fix_bot_ends_with_a_notice_when_github_keeps_failing(
    tmp_path: Path, step: str, failing: str, variables: dict[str, str]
) -> None:
    done = workflow_steps.run_step(
        tmp_path,
        "after-checks.yml",
        "fixes",
        step,
        answers=(Answer(failing, err=UNAVAILABLE, code=1), WRITES),
        env=variables,
        stubs=SLEEP,
    )

    assert done.returncode == 0, done.stderr
    assert len(done.called(failing)) == 4
    assert done.stubbed == ["sleep 10", "sleep 20", "sleep 40"]
    assert done.stdout.startswith(NOTICE)
    assert not done.called(WRITES.args)
    # The steps after it learn that the job sat out an outage.
    assert (done.runner_temp / "github-sat-out").exists()


@needs_bash
def test_the_issue_of_the_fix_bot_of_main_stays_open_after_an_outage(
    tmp_path: Path,
) -> None:
    # A step before, such as fix main or the token of the release app, sat out an
    # outage of GitHub, so the job passed without doing anything: that is no run
    # that passes again, and the issue stays as it is.
    done = workflow_steps.run_step(
        tmp_path,
        "after-checks.yml",
        "fixes",
        KEEPS,
        answers=(Answer(r"issue list --state open .*", "7\n"), WRITES),
        env={"FAILED": "false", "URL": "https://run/9"},
        files={"$RUNNER_TEMP/github-sat-out": ""},
    )

    assert done.returncode == 0, done.stderr
    assert done.commands == []


@needs_bash
@pytest.mark.parametrize(
    ("job", "step", "answers", "write", "variables"),
    [
        (
            "fixes",
            SAYS,
            (PR_COMMENTS,),
            r"pr comment 42 .*",
            {"PULL": "42", "SHA": SHA, "URL": "https://run/9"},
        ),
        (
            "fixes",
            KEEPS,
            (Answer(r"issue list --state open .*", "7\n"),),
            r"issue close 7 .*",
            {"FAILED": "false", "URL": "https://run/9"},
        ),
        (
            "fixes",
            KEEPS,
            (Answer(r"issue list --state open .*", ""),),
            r"issue create .*",
            {"FAILED": "true", "URL": "https://run/9"},
        ),
        (
            "own-branch",
            SAYS,
            (),
            r"pr comment 42 .*",
            {"PULL": "42", "URL": "https://run/9"},
        ),
    ],
)
def test_a_write_of_the_fix_bot_that_github_fails_goes_out_once(
    tmp_path: Path,
    job: str,
    step: str,
    answers: tuple[Answer, ...],
    write: str,
    variables: dict[str, str],
) -> None:
    done = workflow_steps.run_step(
        tmp_path,
        "after-checks.yml",
        job,
        step,
        answers=(*answers, Answer(write, err="HTTP 502: Bad Gateway\n", code=1)),
        env=variables,
        stubs=SLEEP,
    )

    assert done.returncode == 0, done.stderr
    assert len(done.called(write)) == 1
    assert done.stubbed == []
    assert done.stdout.startswith(NOTICE)


@needs_bash
def test_an_issue_of_the_fix_bot_that_github_fails_to_edit_is_edited_again(
    tmp_path: Path,
) -> None:
    # An edit does the same the second time.
    edit = r"issue edit 7 .*"
    done = workflow_steps.run_step(
        tmp_path,
        "after-checks.yml",
        "fixes",
        KEEPS,
        answers=(
            Answer(r"issue list --state open .*", "7\n"),
            Answer(edit, err="HTTP 502: Bad Gateway\n", code=1, once=True),
            WRITES,
        ),
        env={"FAILED": "true", "URL": "https://run/9"},
        stubs=SLEEP,
    )

    assert done.returncode == 0, done.stderr
    assert len(done.called(edit)) == 2
    assert done.stubbed == ["sleep 10"]
    assert NOTICE not in done.stdout


# ---------------------------------------------------------------- the command /fix


@pytest.mark.parametrize(
    ("body", "given"),
    [
        ("/fix", True),
        ("  /fix  \n", True),
        ("/fix\nThe format, please.", True),
        ("/fixed it", False),
        ("> /fix", False),
        ("Could you /fix this?", False),
        ("", False),
    ],
)
def test_the_command_is_the_first_line_alone(body: str, given: bool) -> None:
    assert is_command(body) is given


def with_a_fix(
    github: FakeGitHub, fork: bool = False, editable: bool = False
) -> FakeGitHub:
    """A pull request whose Lint failed and kept a fix of app.py, which it changes."""
    github.pull(fork=fork, editable=editable)
    github.runs = [run_of(1, "Lint")]
    github.artifacts = {1: [{"name": "fixes-lint"}]}
    github.downloads = {(1, "fixes-lint"): {"app.py": b"x = 2\n"}}
    github.patches = {"app.py": "@@ -1 +1 @@\n-x = 0\n+x = 1\n"}
    return github


def no_wait(seconds: float) -> None:
    """The bot waits for nothing in a test."""


def decided(
    github: FakeGitHub,
    folder: Path,
    user: str = "maintainer",
    wait: Callable[[float], None] = no_wait,
) -> Command:
    api = api_of(github)
    return decide_command(
        api, REPO, 42, user, folder, downloader(api, REPO), WATCHED, wait
    )


def test_a_branch_of_the_repository_gets_the_commit_at_the_command(
    tmp_path: Path,
) -> None:
    found = decided(with_a_fix(FakeGitHub()), tmp_path)

    assert found == Command(
        "commit", "#42 comes from a branch of this repository.\n", SHA, REPO, "feature"
    )
    assert load([tmp_path / "1-fixes-lint"]).files == {"app.py": b"x = 2\n"}


def test_a_fork_that_allows_edits_gets_the_commit_at_the_command(
    tmp_path: Path,
) -> None:
    found = decided(with_a_fix(FakeGitHub(), fork=True, editable=True), tmp_path)

    assert found == Command(
        "commit",
        "#42 comes from a fork whose author allows edits by maintainers.\n",
        SHA,
        FORK,
        "feature",
    )


def test_a_fork_that_allows_no_edits_gets_the_suggestions_at_the_command(
    tmp_path: Path,
) -> None:
    found = decided(with_a_fix(FakeGitHub(), fork=True), tmp_path)

    assert (found.action, found.repository) == ("suggest", FORK)
    assert found.text.startswith(
        "#42 comes from a fork whose author allows no edits by maintainers, so no bot "
        "may commit onto its branch: the bot suggests the fixes at their lines"
    )
    assert "With **Allow edits by maintainers** turned on, `/fix` commits" in found.text


def test_the_label_that_turns_off_the_bot_leaves_the_command_alone(
    tmp_path: Path,
) -> None:
    github = with_a_fix(FakeGitHub())
    github.pulls[0]["labels"] = [{"name": OPT_OUT}]

    assert decided(github, tmp_path).action == "commit"


@pytest.mark.parametrize(
    ("user", "permission"),
    [("reader", "read"), ("triager", "triage"), ("stranger", "none")],
)
def test_only_a_person_with_write_access_starts_the_bot(
    tmp_path: Path, user: str, permission: str
) -> None:
    github = with_a_fix(FakeGitHub())
    if permission != "none":
        github.permissions[user] = permission

    found = decided(github, tmp_path, user)

    assert found == Command(
        "",
        "Only a person with write access to this repository starts the fix bot with "
        f"`/fix`; `{user}` has the permission `{permission}`.\n",
    )
    # It reads nothing of the pull request.
    assert github.calls == [f"GET repos/{REPO}/collaborators/{user}/permission"]


@pytest.mark.parametrize("permission", ["admin", "write"])
def test_a_person_with_write_access_starts_the_bot(
    tmp_path: Path, permission: str
) -> None:
    github = with_a_fix(FakeGitHub())
    github.permissions["owner"] = permission

    assert decided(github, tmp_path, "owner").action == "commit"


def test_the_command_waits_for_the_checks_that_still_run(tmp_path: Path) -> None:
    # Unlike a job after a run, the command finds a check that has yet to fail.
    github = with_a_fix(FakeGitHub())
    github.runs[0].update(status="in_progress", conclusion="")
    waits: list[float] = []

    def wait(seconds: float) -> None:
        waits.append(seconds)
        github.runs[0].update(status="completed", conclusion="failure")

    found = decided(github, tmp_path, wait=wait)

    assert waits == [30]
    assert found.action == "commit"


def test_a_check_that_outlasts_the_wait_holds_the_command_back(
    tmp_path: Path,
) -> None:
    github = with_a_fix(FakeGitHub())
    github.runs.append(run_of(2, "CI (python)", status="in_progress", conclusion=""))
    waits: list[float] = []

    found = decided(github, tmp_path, wait=waits.append)

    assert len(waits) == 28
    assert found == Command(
        "",
        "Still running after the wait for aaaaaaa: `CI (python)`. The bot commits "
        "nothing yet, so that one commit holds every fix: say `/fix` again once they "
        "have ended.\n",
    )


def test_a_head_without_a_fix_takes_no_commit_at_the_command(tmp_path: Path) -> None:
    github = FakeGitHub()
    github.pull()
    github.runs = [run_of(1, "Lint")]

    assert decided(github, tmp_path) == Command(
        "",
        "No command fixed what the checks of aaaaaaa found; the PR coach names what "
        "is left and how to fix it.\n",
    )


@pytest.mark.parametrize(
    ("change", "text"),
    [
        ({"state": "closed"}, "#42 is no open pull request.\n"),
        (
            {"head": {"sha": SHA, "ref": "feature", "repo": None}},
            "The fork of #42 is gone, so no commit can reach its branch.\n",
        ),
    ],
)
def test_a_pull_request_that_no_commit_can_reach_takes_none(
    tmp_path: Path, change: dict[str, Any], text: str
) -> None:
    github = with_a_fix(FakeGitHub())
    github.pulls[0].update(change)

    assert decided(github, tmp_path) == Command("", text)
    assert not (tmp_path / "1-fixes-lint").exists()


def fork_files(github: FakeGitHub) -> Fixes:
    """A pull request from a fork that allows edits, with fixes of a file that it
    changes, of a script that decides what a workflow runs, and of a file that it
    doesn't change."""
    github.pull(fork=True, editable=True)
    github.files = {
        "app.py": b"x  =  1\n",
        "scripts/build.sh": b"echo  hi\n",
        "other.py": b"y  =  1\n",
    }
    github.patches = {
        "app.py": "@@ -1 +1 @@\n-x\n+x  =  1\n",
        "scripts/build.sh": "@@ -1 +1 @@\n-echo\n+echo  hi\n",
    }
    return Fixes(
        {
            "app.py": b"x = 1\n",
            "other.py": b"y = 1\n",
            "scripts/build.sh": b"echo hi\n",
        }
    )


def pushed(github: FakeGitHub, fixes: Fixes, repository: str = FORK) -> Pushed:
    return commit_on_command(
        api_of(github),
        REPO,
        42,
        repository,
        "feature",
        SHA,
        fixes,
        "app",
        "https://github.com/o/r/pull/42#issuecomment-7",
    )


def test_the_command_commits_onto_the_branch_of_a_fork_only_what_it_changes() -> None:
    github = FakeGitHub()

    done = pushed(github, fork_files(github))

    assert done == Pushed(
        "The fix bot committed c0ffee0 onto `someone/r:feature`:\n\n- `app.py`\n\n"
        "Left to you:\n\n"
        "- `other.py`: no file that the pull request changes\n"
        "- `scripts/build.sh`: decides what a workflow runs, so a person commits its "
        "fix\n\n"
        "The checks of the new head run once GitHub lets them, which on a fork may "
        "wait for a person to approve them.\n"
    )
    (request,) = github.graphql
    given = request["variables"]["input"]
    assert given["branch"] == {"repositoryNameWithOwner": FORK, "branchName": "feature"}
    assert given["expectedHeadOid"] == SHA
    assert [item["path"] for item in given["fileChanges"]["additions"]] == ["app.py"]
    assert given["message"]["headline"] == HEADLINE
    assert given["message"]["body"].startswith(
        f"{MADE_BY} aaaaaaa, at the command "
        "https://github.com/o/r/pull/42#issuecomment-7\n\nSigned-off-by: app[bot] "
    )
    assert github.fork_refs["feature"] == MADE
    assert github.refs["feature"] == SHA


def test_a_fork_that_refuses_the_commit_gets_the_suggestions() -> None:
    github = FakeGitHub()
    github.fork_refuses = True

    done = pushed(github, fork_files(github))

    assert done.to_suggest
    assert done.text.startswith(
        "GitHub refused the commit of the fix bot onto `someone/r:feature`: `GraphQL "
        "answered [{'type': 'FORBIDDEN', 'message': 'Resource not accessible by "
        "integration'}]`. So the fixes stay what a fork gets without the command: "
        "the bot suggests them at their lines"
    )
    assert github.fork_refs["feature"] == SHA


def test_a_branch_of_the_repository_that_refuses_the_commit_fails_the_bot() -> None:
    github = FakeGitHub()
    github.pull()
    github.graphql_fails = True

    with pytest.raises(GitHubError, match="Expected branch"):
        pushed(github, Fixes({"app.py": b"x = 2\n"}), REPO)


def test_the_command_commits_onto_a_branch_of_the_repository_what_the_head_has() -> (
    None
):
    # Every file of the head, as the bot after the checks commits them.
    github = FakeGitHub()
    github.pull()
    github.files = {"app.py": b"x  =  1\n", "scripts/build.sh": b"echo  hi\n"}

    done = pushed(
        github, Fixes({"app.py": b"x = 1\n", "scripts/build.sh": b"echo hi\n"}), REPO
    )

    assert done == Pushed(
        "The fix bot committed c0ffee0 onto `feature`:\n\n- `app.py`\n"
        "- `scripts/build.sh`\n"
    )
    assert github.refs["feature"] == MADE


def test_a_branch_that_moved_on_takes_no_commit_at_the_command() -> None:
    github = FakeGitHub()
    fixes = fork_files(github)
    github.fork_refs["feature"] = OTHER

    done = pushed(github, fixes)

    assert done == Pushed(
        "`someone/r:feature` moved on from aaaaaaa, so the bot commits nothing: say "
        "`/fix` again once the checks of its new head have ended.\n"
    )
    assert github.graphql == []


def test_a_push_while_the_bot_commits_at_the_command_wins() -> None:
    github = FakeGitHub()
    fixes = fork_files(github)
    github.fork_refuses = True

    def push(github: FakeGitHub) -> None:
        github.fork_refs["feature"] = OTHER

    github.on_commit = push

    done = pushed(github, fixes)

    assert not done.to_suggest
    assert done.text.startswith("`someone/r:feature` moved on from aaaaaaa")


def test_a_fork_with_no_fix_for_its_branch_gets_the_suggestions() -> None:
    github = FakeGitHub()
    github.pull(fork=True, editable=True)
    github.files = {"pyproject.toml": b"[x]\na  =  1\n"}
    github.patches = {"pyproject.toml": "@@ -1,2 +1,2 @@\n [x]\n-a\n+a  =  1\n"}

    done = pushed(github, Fixes({"pyproject.toml": b"[x]\na = 1\n"}))

    assert done == Pushed(
        "No fix is left to commit.\n\nLeft to you:\n\n- `pyproject.toml`: decides "
        "what a workflow runs, so a person commits its fix\n",
        True,
    )
    assert github.graphql == []


def test_a_branch_that_has_every_fix_takes_no_commit_at_the_command() -> None:
    github = FakeGitHub()
    github.pull()

    done = pushed(github, Fixes({"app.py": b"x = 1\n"}), REPO)

    assert done == Pushed("No fix is left to commit.\n")
    assert github.graphql == []


def fix_command(
    root: Path, github: FakeGitHub, output: Path, comment: str = "7"
) -> int:
    """Runs fix command as its step does, in the files of main."""
    return cli.main(
        [
            "--repo",
            REPO,
            "fix",
            "command",
            "--pull",
            "42",
            "--comment",
            comment,
            "--folder",
            str(root / "fixes"),
            "--output",
            str(output),
        ],
        api=api_of(github),
        root=root,
    )


def commented(github: FakeGitHub, body: str = "/fix") -> FakeGitHub:
    github.issue_comments[7] = {"body": body, "user": {"login": "maintainer"}}
    return github


@pytest.mark.parametrize("fork", [False, True])
def test_fix_command_from_the_command_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], fork: bool
) -> None:
    github = commented(with_a_fix(FakeGitHub(), fork=fork, editable=True))
    output = tmp_path / "output"

    code = fix_command(homedarts(tmp_path), github, output)

    assert code == 0
    assert output.read_text(encoding="utf-8") == (
        f"command=true\naction=commit\nsha={SHA}\n"
        f"repository={FORK if fork else REPO}\nbranch=feature\n"
        f"fork={str(fork).lower()}\n"
    )
    assert capsys.readouterr().out.startswith("#42 comes from a")
    # The person sees at once that the bot took the command.
    assert github.reactions == [(7, "eyes")]
    assert load([tmp_path / "fixes" / "1-fixes-lint"]).files == {"app.py": b"x = 2\n"}


def test_fix_command_says_nothing_to_another_comment(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    github = commented(with_a_fix(FakeGitHub()), "/fixed it, thanks")
    output = tmp_path / "output"

    assert fix_command(homedarts(tmp_path), github, output) == 0

    assert capsys.readouterr().out == "Comment 7 is no command of the fix bot.\n"
    assert not output.exists()
    assert github.reactions == []
    # Nor to a comment that is gone.
    assert fix_command(tmp_path, github, output, "8") == 0
    assert not output.exists()


def test_fix_command_goes_on_when_it_cannot_react(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    github = commented(with_a_fix(FakeGitHub()))
    github.reactions_fail = True
    output = tmp_path / "output"

    assert fix_command(homedarts(tmp_path), github, output) == 0

    captured = capsys.readouterr()
    assert "::warning::The fix bot couldn't react to the command" in captured.err
    assert "action=commit\n" in output.read_text(encoding="utf-8")


def test_fix_command_without_a_list_takes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    homedarts(
        tmp_path, "name: After the checks\non:\n  workflow_run:\n    workflows: []\n"
    )
    github = commented(with_a_fix(FakeGitHub()))
    output = tmp_path / "output"

    assert fix_command(tmp_path, github, output) == 1

    captured = capsys.readouterr()
    assert "lists no workflow" in captured.out
    assert "::error::" in captured.err
    # The answer says that the bot failed, and no step commits.
    assert output.read_text(encoding="utf-8") == "command=true\n"


@pytest.mark.parametrize(("refuses", "suggests"), [(False, "false"), (True, "true")])
def test_fix_commit_at_the_command_from_the_command_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], refuses: bool, suggests: str
) -> None:
    folder = tmp_path / "fixes"
    kept(folder / "1-fixes-lint", {"app.py": "x = 2\n"})
    github = with_a_fix(FakeGitHub(), fork=True, editable=True)
    github.fork_refuses = refuses
    output = tmp_path / "output"

    code = cli.main(
        [
            "--repo",
            REPO,
            "fix",
            "commit",
            "--sha",
            SHA,
            "--branch",
            "feature",
            "--repository",
            FORK,
            "--pull",
            "42",
            "--app",
            "app",
            "--url",
            "u",
            "--folder",
            str(folder),
            "--output",
            str(output),
        ],
        api=api_of(github),
    )

    assert code == 0
    assert output.read_text(encoding="utf-8") == f"suggest={suggests}\n"
    said = capsys.readouterr().out
    assert said.startswith("GitHub refused" if refuses else "The fix bot committed")


def command_starts(
    body: str = "/fix",
    association: str = "COLLABORATOR",
    pull_request: bool = True,
    state: str = "open",
    fork: bool = False,
) -> bool:
    """Whether the job of the command starts after a comment, by its condition, whose
    few expressions Python reads alike."""
    condition = condition_of(workflow_steps.job("commands.yml", "fix"))
    expression = re.sub(r"!(?!=)", " not ", condition)
    expression = expression.replace("&&", " and ").replace("||", " or ")
    event = SimpleNamespace(
        repository=SimpleNamespace(fork=fork),
        issue=SimpleNamespace(
            pull_request={"url": "u"} if pull_request else None, state=state
        ),
        comment=SimpleNamespace(body=body, author_association=association),
    )
    return bool(
        eval(
            expression,
            {
                "github": SimpleNamespace(event=event),
                "contains": lambda items, item: item in items,
                "fromJSON": json.loads,
                "startsWith": lambda text, start: text.lower().startswith(
                    start.lower()
                ),
            },
        )
    )


def test_the_command_starts_the_bot_only_for_a_comment_that_may_be_one() -> None:
    assert command_starts()
    assert command_starts("/fix\nThe format, please.", "OWNER")
    assert command_starts(association="MEMBER")
    # The bot reads the comment itself, so a word that only starts like it takes a
    # runner for nothing, and says nothing.
    assert command_starts("/fixed it")
    assert not command_starts("Thanks!")
    assert not command_starts(association="CONTRIBUTOR")
    assert not command_starts(association="NONE")
    # Not on an issue, a closed pull request or in a fork of the repository.
    assert not command_starts(pull_request=False)
    assert not command_starts(state="closed")
    assert not command_starts(fork=True)


def suggestion_after(
    action: str, fork: str = "true", ready: str = "true", suggests: str = ""
) -> bool:
    """Whether the job suggests the fixes, by the condition of the step."""
    found = workflow_steps.step(
        "commands.yml", "fix", "Suggest the fixes on the pull request from a fork"
    )
    expression = condition_of(found).replace("&&", " and ").replace("||", " or ")
    steps = SimpleNamespace(
        decide=SimpleNamespace(outputs=SimpleNamespace(action=action, fork=fork)),
        **{"release-app": SimpleNamespace(outputs=SimpleNamespace(ready=ready))},
        commit=SimpleNamespace(outputs=SimpleNamespace(suggest=suggests)),
    )
    expression = expression.replace("steps.release-app.", "release_app.")
    return bool(
        eval(expression, {"steps": steps, "release_app": getattr(steps, "release-app")})
    )


def test_a_fork_gets_the_suggestions_wherever_the_commit_cannot_reach_it() -> None:
    assert suggestion_after("suggest")
    assert suggestion_after("commit", suggests="true")
    assert suggestion_after("commit", ready="")
    assert not suggestion_after("commit", suggests="false")
    assert not suggestion_after("")
    # A branch of the repository has the commit, or the bot says why not.
    assert not suggestion_after("commit", fork="false", ready="")
    assert not suggestion_after("commit", fork="false", suggests="true")


def test_the_command_runs_nothing_of_the_pull_request() -> None:
    found = workflow_steps.workflow("commands.yml")
    assert set(found["on"]) == {"issue_comment"}
    assert found["on"]["issue_comment"] == {"types": ["created"]}
    assert found["permissions"] == {}
    job = workflow_steps.job("commands.yml", "fix")
    assert job["permissions"] == {
        "actions": "read",
        "contents": "read",
        "pull-requests": "write",
    }
    checkout = next(
        step for step in job["steps"] if "actions/checkout" in step.get("uses", "")
    )
    # main alone, as the workflow runs on the default branch for a comment.
    assert set(checkout["with"]) == {"persist-credentials", "sparse-checkout"}
    token = step_in(job, "Create a token of the release app for the branch")
    assert {key for key in token["with"] if key.startswith("permission-")} == {
        "permission-contents",
        "permission-pull-requests",
    }
    assert token["with"]["permission-pull-requests"] == "read"
    # The comment is data that only the condition of the job and blueprint.py read.
    for step in job["steps"]:
        assert "comment.body" not in json.dumps(step)


ANSWER = "$RUNNER_TEMP/answer.md"


@needs_bash
@pytest.mark.parametrize(
    ("variables", "files", "body"),
    [
        (
            {"ACTION": "commit", "READY": "true", "FAILED": "false"},
            {ANSWER: "#42 comes from a fork.\nThe fix bot committed c0ffee0.\n"},
            "### The fix bot at `/fix`\n\n#42 comes from a fork.\n"
            "The fix bot committed c0ffee0.\n",
        ),
        (
            {"ACTION": "commit", "READY": "", "FAILED": "false"},
            {ANSWER: "#42 comes from a fork.\n"},
            "### The fix bot at `/fix`\n\n#42 comes from a fork.\n\nThis repository "
            "has no release app set up, which the fix bot needs to commit; the summary "
            "of the run (https://run/9) says how to set it up.\n",
        ),
        (
            {"ACTION": "", "READY": "", "FAILED": "true"},
            {},
            "### The fix bot at `/fix`\n\n\nThe fix bot failed (https://run/9); its "
            "summary says why. The PR coach names the command of each check that "
            "failed, which makes the fixes on your machine.\n",
        ),
    ],
)
def test_the_bot_answers_each_command(
    tmp_path: Path, variables: dict[str, str], files: dict[str, str], body: str
) -> None:
    done = workflow_steps.run_step(
        tmp_path,
        "commands.yml",
        "fix",
        "Answer the command on the pull request",
        answers=(Answer(r"pr comment 42 --body-file .*"),),
        env={"PULL": "42", "URL": "https://run/9", **variables},
        files=files,
    )

    assert done.returncode == 0, done.stderr
    assert done.read_by("pr comment 42", "--body-file") == [body]


@needs_bash
@pytest.mark.parametrize(
    ("step", "code"),
    [
        ("Decide what the fix bot does at the command", 0),
        ("Decide what the fix bot does at the command", 1),
        ("Commit the fixes onto the branch of the pull request", 1),
        ("Suggest the fixes on the pull request from a fork", 1),
    ],
)
def test_what_the_bot_says_goes_into_the_answer_and_its_failure_stops_it(
    tmp_path: Path, step: str, code: int
) -> None:
    done = workflow_steps.run_step(
        tmp_path,
        "commands.yml",
        "fix",
        step,
        env={
            "PULL": "42",
            "COMMENT": "7",
            "SHA": SHA,
            "APP_SLUG": "app",
            "HEAD_REPO": FORK,
            "BRANCH": "feature",
            "URL": "https://c",
        },
        stubs={
            "python3": workflow_steps.recording(
                "python3", f'echo "#42 comes from a fork."; exit {code}'
            )
        },
        files={ANSWER: "Before.\n"},
    )

    # The step fails with blueprint.py, not only with tee.
    assert done.returncode == code, done.stderr
    assert done.summary == "#42 comes from a fork.\n"
    answer = done.runner_temp / "answer.md"
    assert answer.read_text(encoding="utf-8") == "Before.\n#42 comes from a fork.\n"
