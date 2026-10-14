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
import shutil
import subprocess
import sys
import textwrap
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from shell import BASH, in_bash

import blueprint.fixes
from blueprint import cli
from blueprint.coach import BOT, FIX_HEADLINE, Catalog
from blueprint.fixes import (
    BRANCH,
    HEADLINE,
    MADE_BY,
    OPT_OUT,
    SUGGESTED,
    Fixes,
    FixLoop,
    Suggestion,
    allowed,
    artifacts_of,
    blob_sha,
    changeable,
    collect,
    commit_onto_branch,
    downloader,
    expanded,
    files_of,
    fix_text,
    fixers,
    heal_main,
    is_text,
    keep,
    listing,
    load,
    placeable,
    plan,
    report_kept,
    run,
    run_until_done,
    runs_of,
    shown,
    shown_lines,
    suggest,
    suggestions_of,
    text_fixed,
)
from blueprint.github import Api, GitHubError

ROOT = Path(__file__).parents[1]
REPO = "o/r"
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
        ("Ruff", "ruff check --fix ."),
        ("Ruff", "ruff format ."),
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


@pytest.mark.parametrize("script", [".github/blueprint.py", "blueprint.py"])
def test_a_command_runs_the_tool_of_the_repository(tmp_path: Path, script: str) -> None:
    write(tmp_path, script, "")

    assert shown("{blueprint} fix text", tmp_path) == f"python3 {script} fix text"
    python = Path(sys.executable).as_posix()
    assert expanded("{blueprint} fix text", tmp_path).endswith(f" {script} fix text")
    assert python in expanded("{blueprint} fix text", tmp_path)
    assert expanded("ruff format .", tmp_path) == "ruff format ."


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
        self.modes: dict[str, str] = {}
        self.refs: dict[str, str] = {"main": SHA, "feature": SHA}
        self.pulls: list[dict[str, Any]] = []
        self.runs: list[dict[str, Any]] = []
        self.artifacts: dict[int, list[dict[str, Any]]] = {}
        self.downloads: dict[tuple[int, str], dict[str, bytes]] = {}
        self.review_comments: list[dict[str, Any]] = []
        self.patches: dict[str, str] = {}
        self.reviews: list[dict[str, Any]] = []
        self.comments: list[dict[str, Any]] = []
        self.created: list[dict[str, Any]] = []
        self.commit: dict[str, Any] = {
            "commit": {"message": "Add a feature"},
            "author": {"type": "User"},
            "files": [],
        }
        self.graphql: list[dict[str, Any]] = []
        self.graphql_fails = False
        # What happens to the branches while the bot commits, as a push would.
        self.on_commit: Callable[[FakeGitHub], None] = lambda github: None
        self.truncated = False
        self.calls: list[str] = []

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
        local = path.removeprefix(f"repos/{REPO}/")
        status, data = self.route(method, local, json.loads(body) if body else None)
        text = "" if data is None else json.dumps(data)
        return subprocess.CompletedProcess(
            arguments, 0, f"HTTP/2.0 {status} X\r\nA: b\r\n\r\n{text}", ""
        )

    def route(self, method: str, path: str, body: Any) -> tuple[int, Any]:
        paged = r"per_page=(\d+)&page=(\d+)"
        if found := re.fullmatch(
            r"actions/runs\?head_sha=(\w+)&event=(\w+)&per_page=100", path
        ):
            return 200, {"workflow_runs": self.runs if found[1] == SHA else []}
        if found := re.fullmatch(r"actions/runs/(\d+)/artifacts\?per_page=100", path):
            return 200, {"artifacts": self.artifacts.get(int(found[1]), [])}
        if found := re.fullmatch(r"git/trees/(\w+)\?recursive=1", path):
            data = tree(self.files, self.modes) | {"truncated": self.truncated}
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
            return 200, self.commit
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
                {"filename": name, "patch": patch}
                for name, patch in self.patches.items()
            ]
            return 200, self.page(items, found[2], found[3])
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
            self.refs[branch] = MADE
            return 200, {"data": {"createCommitOnBranch": {"commit": {"oid": MADE}}}}
        raise AssertionError(f"unexpected request {method} {path}")

    def page(self, items: list[Any], size: str, number: str) -> list[Any]:
        start = (int(number) - 1) * int(size)
        return items[start : start + int(size)]

    def writes(self) -> list[str]:
        return [call for call in self.calls if not call.startswith("GET ")]

    def pull(
        self, number: int = 42, fork: bool = False, labels: Sequence[str] = ()
    ) -> None:
        self.pulls.append(
            {
                "number": number,
                "state": "open",
                "labels": [{"name": label} for label in labels],
                "head": {
                    "sha": SHA,
                    "ref": "feature",
                    "repo": {"full_name": "someone/r" if fork else REPO},
                },
            }
        )


def api_of(github: FakeGitHub) -> Api:
    return Api(runner=github)


# ---------------------------------------------------------------- collect


def run_of(
    run_id: int, name: str, status: str = "completed", conclusion: str = "failure"
) -> dict[str, Any]:
    return {"id": run_id, "name": name, "status": status, "conclusion": conclusion}


def test_the_runs_of_a_commit_that_keep_fixes() -> None:
    github = FakeGitHub()
    github.runs = [
        run_of(1, "Lint"),
        run_of(3, "Lint", conclusion="success"),
        run_of(2, "CI (python)"),
        # An older run of the same workflow, which the newer one replaces.
        run_of(0, "CI (python)", conclusion="cancelled"),
        run_of(4, "CodeQL"),
        {"id": 5, "name": None, "status": None, "conclusion": None},
    ]

    found = runs_of(api_of(github), REPO, SHA, "pull_request")

    assert [(run.id, run.name, run.conclusion) for run in found] == [
        (2, "CI (python)", "failure"),
        (3, "Lint", "success"),
    ]
    assert runs_of(api_of(github), REPO, OTHER, "pull_request") == []


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
        tmp_path,
        downloader(api_of(github), REPO),
        wait,
    )

    assert found == []
    assert github.calls == [f"GET repos/{REPO}/actions/runs/1/artifacts?per_page=100"]


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
        api, REPO, 1, SHA, "pull_request", tmp_path, downloader(api, REPO), wait
    )

    assert waits == [30, 30]
    assert found == [tmp_path / "1-fixes-markdown", tmp_path / "2-fixes-check"]
    # Only the runs that failed kept fixes.
    downloads = [call for call in github.calls if call.startswith("gh run download")]
    assert downloads == [
        f"gh run download 1 --repo {REPO} --name fixes-markdown --dir {tmp_path / '1-fixes-markdown'}",
        f"gh run download 2 --repo {REPO} --name fixes-check --dir {tmp_path / '2-fixes-check'}",
    ]
    assert load(found).files == {"README.md": b"# Fixed\n", "app.py": b"x = 2\n"}


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
        api, REPO, 1, SHA, "pull_request", tmp_path, downloader(api, REPO), waits.append
    )

    assert len(waits) == blueprint.fixes.WAITS
    assert found == [tmp_path / "1-fixes-markdown"]


def test_main_looks_at_its_checks_also_when_the_run_kept_nothing(
    tmp_path: Path,
) -> None:
    github = FakeGitHub()
    github.runs = [run_of(2, "CI (python)", conclusion="success")]

    api = api_of(github)
    assert collect(api, REPO, 2, SHA, "push", tmp_path, downloader(api, REPO)) == []
    assert any("actions/runs?head_sha" in call for call in github.calls)


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


def test_the_bot_never_fixes_its_own_fixes_again() -> None:
    github = FakeGitHub()
    github.pull()
    github.commit = {
        "commit": {"message": f"{FIX_HEADLINE}\n\n{MADE_BY} x"},
        "author": {"type": "Bot"},
        "files": [{"filename": "app.py"}],
    }

    with pytest.raises(FixLoop, match="don't fix the same way twice"):
        plan(api_of(github), REPO, SHA, "pull_request", "feature", 42, FIXES)


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


def test_main_gets_a_pull_request_with_its_fixes() -> None:
    github = FakeGitHub()

    decided = plan(api_of(github), REPO, SHA, "push", "main", None, FIXES)

    assert decided.action == "pull-request"


def test_main_that_moved_on_leaves_it_to_its_newest_run() -> None:
    github = FakeGitHub()
    github.refs["main"] = OTHER

    decided = plan(api_of(github), REPO, SHA, "push", "main", None, FIXES)

    assert decided == blueprint.fixes.Plan(
        "", "main moved on from aaaaaaa; its newest run decides.\n"
    )


def test_main_without_fixes_closes_the_pull_request_of_its_fixes() -> None:
    github = FakeGitHub()
    assert plan(api_of(github), REPO, SHA, "push", "main", None, Fixes({})).action == ""
    github.pulls.append({"number": 9, "state": "open", "head": {"ref": BRANCH}})

    decided = plan(api_of(github), REPO, SHA, "push", "main", None, Fixes({}))

    assert (decided.action, decided.text) == (
        "close",
        "main needs the fixes of #9 no more.\n",
    )


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


def test_fix_collect_from_the_command_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    github = FakeGitHub()
    github.pull()
    github.runs = [run_of(1, "CI (python)")]
    github.artifacts = {1: [{"name": "fixes-check"}]}
    github.downloads = {(1, "fixes-check"): {"app.py": b"x = 2\n"}}
    output = tmp_path / "output"
    folder = tmp_path / "fixes"

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
            str(folder),
            "--output",
            str(output),
        ],
        api=api_of(github),
    )

    assert code == 0
    assert output.read_text(encoding="utf-8") == "action=commit\npull=42\n"
    assert capsys.readouterr().out == "#42 comes from a branch of this repository.\n"
    assert load([folder / "1-fixes-check"]).files == {"app.py": b"x = 2\n"}


def test_fix_collect_without_an_output_only_says_what_it_decided(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # On a machine, without $GITHUB_OUTPUT, the decision goes to the terminal alone.
    github = FakeGitHub()
    github.pull()
    github.runs = [run_of(1, "CI (python)")]
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
    )

    assert code == 0
    assert capsys.readouterr().out == "#42 comes from a branch of this repository.\n"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["fixes"]


def test_fix_collect_stops_a_loop(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    github = FakeGitHub()
    github.pull()
    github.runs = [run_of(1, "CI (python)")]
    github.artifacts = {1: [{"name": "fixes-check"}]}
    github.downloads = {(1, "fixes-check"): {"app.py": b"x = 2\n"}}
    github.commit = {"commit": {"message": FIX_HEADLINE}, "author": {"type": "Bot"}}

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


# ---------------------------------------------------------------- the workflows


def workflow(name: str) -> str:
    return (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")


def job_of(text: str, name: str) -> str:
    start = text.index(f"\n  {name}:\n")
    following = re.search(r"\n\n  [a-z][a-z0-9-]*:\n", text[start + 1 :])
    return text[start : start + 1 + following.start()] if following else text[start:]


def step_of(text: str, name: str) -> str:
    start = text.index(f"      - name: {name}\n")
    following = text.find("\n      - ", start + 1)
    comment = text.find("\n      # ", start + 1)
    ends = [end for end in (following, comment) if end != -1]
    return text[start : min(ends)] if ends else text[start:]


@pytest.mark.parametrize(
    "path",
    sorted((ROOT / ".github/workflows").glob("ci-*.yml")),
    ids=lambda path: path.name,
)
def test_the_check_of_each_kind_of_project_keeps_its_fixes(path: Path) -> None:
    check = job_of(path.read_text(encoding="utf-8"), "check")
    explain = step_of(check, "Explain the failure")
    name = re.search(r'CHECK: ("check \([a-z-]+\)")', explain)
    assert name

    fix = step_of(check, "Fix what a command can fix")
    keep_step = step_of(check, "Keep the fixes for the fix bot")

    # Fix first, explain second: the explanation stays the last step.
    assert check.index(fix) < check.index(keep_step) < check.index(explain)
    assert "fetch-depth: 2" in check
    assert (
        'if: failure() && contains(fromJSON(\'["pull_request", "push"]\'), github.event_name)'
        in fix
    )
    assert f"CHECK: {name[1]}" in fix
    assert "git checkout --quiet --force --detach HEAD^2" in fix
    assert 'fix run "$CHECK" --keep "$RUNNER_TEMP/fixes"' in fix
    assert "if: failure() && steps.fix.outcome == 'success'" in keep_step
    assert "name: fixes-check" in keep_step
    assert "if-no-files-found: ignore" in keep_step
    assert "include-hidden-files: true" in keep_step


def test_the_markdown_fixes_itself_on_the_head_of_the_pull_request() -> None:
    markdown = job_of(workflow("lint.yml"), "markdown")

    assert "fetch-depth: 2" in markdown
    head = step_of(markdown, "Check out the head of the pull request for the fixes")
    assert "if: failure() && github.event_name == 'pull_request'" in head
    fix = step_of(markdown, "Fix what markdownlint can fix")
    assert "continue-on-error: true" in fix
    assert "fix: true" in fix
    # The same action as the check, so that both have one version.
    action = re.findall(r"uses: (DavidAnson/markdownlint-cli2-action@\w+)", markdown)
    assert len(action) == 2
    assert len(set(action)) == 1
    keep_step = step_of(markdown, "Keep the fixes for the fix bot")
    assert "name: fixes-markdown" in keep_step
    assert markdown.index(keep_step) < markdown.index(
        "      - name: Explain the failure\n"
    )
    assert 'fix keep "$RUNNER_TEMP/fixes"' in step_of(
        markdown, "Keep the files that markdownlint fixed"
    )


def test_the_fix_bot_has_only_what_it_needs() -> None:
    bot = job_of(workflow("after-checks.yml"), "fixes")

    assert "    permissions:\n      actions: read #" in bot
    assert "      contents: read #" in bot
    assert "contents: write" not in bot.split("steps:")[0]
    # Each token of the release app has only what its step needs.
    branch = step_of(bot, "Create a token of the release app for the branch")
    assert re.findall(r"permission-[\w-]+: \w+", branch) == [
        "permission-contents: write"
    ]
    main = step_of(bot, "Create a token of the release app for main")
    assert re.findall(r"permission-[\w-]+: \w+", main) == [
        "permission-contents: write",
        "permission-pull-requests: write",
        "permission-workflows: write",
    ]
    # It checks out the tool of main, never the code of the pull request.
    assert "sparse-checkout: |\n            .github\n            blueprint" in bot
    assert "ref:" not in bot
    assert "github.event.workflow_run.conclusion == 'failure'" in bot
    assert "cancel-in-progress: false" in bot


# gh and python3 for the steps of the fix bot: each call on one line of $CALLS, with
# the line breaks of its arguments as \n.
STUB = r"""#!/usr/bin/env bash
args="$*"
printf '%s\n' "$(basename "$0") ${args//$'\n'/\\n}" >> "$CALLS"
case "$*" in
  "issue list "*) echo "${ISSUE:-}" ;;
esac
"""


def run_step(
    script: str, tmp_path: Path, **variables: str
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    stubs = tmp_path / "stubs"
    stubs.mkdir(exist_ok=True)
    for name in ("gh", "python3"):
        (stubs / name).write_text(STUB, encoding="utf-8", newline="\n")
        (stubs / name).chmod(0o755)
    (tmp_path / "step.sh").write_text(script, encoding="utf-8", newline="\n")
    calls = tmp_path / "calls"
    environment = {
        **os.environ,
        "STUBS": stubs.as_posix(),
        "CALLS": calls.as_posix(),
        "RUNNER_TEMP": (tmp_path / "runner").as_posix(),
        "GITHUB_OUTPUT": (tmp_path / "output").as_posix(),
        "GITHUB_STEP_SUMMARY": (tmp_path / "summary").as_posix(),
        **variables,
    }
    result = subprocess.run(
        in_bash("-e", (tmp_path / "step.sh").as_posix()),
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    made = calls.read_text(encoding="utf-8").splitlines() if calls.exists() else []
    return result, made


def script_of(step: str) -> str:
    run_at = step.index("        run: |\n") + len("        run: |\n")
    return textwrap.dedent(step[run_at:])


@needs_bash
def test_the_steps_of_the_fix_bot_pass_what_the_run_says(tmp_path: Path) -> None:
    bot = job_of(workflow("after-checks.yml"), "fixes")
    runner = (tmp_path / "runner").as_posix()

    result, made = run_step(
        script_of(step_of(bot, "Collect the fixes of the checks of the commit")),
        tmp_path,
        GH_REPO=REPO,
        RUN="5",
        SHA=SHA,
        EVENT="pull_request",
        BRANCH="feature",
        NUMBER="",
    )

    assert result.returncode == 0, result.stderr
    assert made == [
        f"python3 blueprint.py --repo {REPO} fix collect 5 --sha {SHA} --event pull_request"
        f" --branch feature --pull  --folder {runner}/fixes --output {(tmp_path / 'output').as_posix()}"
    ]
    for name, action in (
        ("Suggest the fixes on the pull request from a fork", "suggest"),
        ("Commit the fixes onto the branch of the pull request", "commit"),
        ("Keep the pull request with the fixes of main", "main"),
    ):
        (tmp_path / "calls").unlink()
        result, made = run_step(
            script_of(step_of(bot, name)),
            tmp_path,
            GH_REPO=REPO,
            SHA=SHA,
            PULL="42",
            BRANCH="feature",
            APP_SLUG="app",
            URL="https://run",
            BASE="main",
        )
        assert result.returncode == 0, result.stderr
        assert made[0].startswith(
            f"python3 blueprint.py --repo {REPO} fix {action} --sha {SHA}"
        )
        assert made[0].endswith(f"--folder {runner}/fixes")


@needs_bash
@pytest.mark.parametrize("pull", ["42", ""])
def test_the_fix_bot_says_on_the_pull_request_that_it_failed(
    tmp_path: Path, pull: str
) -> None:
    step = step_of(
        job_of(workflow("after-checks.yml"), "fixes"),
        "Say on the pull request that the fix bot failed",
    )

    result, made = run_step(script_of(step), tmp_path, PULL=pull, URL="https://run/9")

    assert result.returncode == 0, result.stderr
    if pull:
        assert made == [
            "gh pr comment 42 --body The fix bot couldn't fix the findings of this pull "
            "request that a command fixes (https://run/9); its summary says why. The PR "
            "coach names the command of each check that failed, which makes the fixes on "
            "your machine."
        ]
    else:
        assert made == []


@needs_bash
@pytest.mark.parametrize(
    ("failed", "issue", "last"),
    [
        (
            "true",
            "",
            "gh issue create --title The fix bot fails on main --label maintenance --body ",
        ),
        ("true", "7", "gh issue edit 7 --body "),
        (
            "false",
            "7",
            "gh issue close 7 --comment The fix bot passes again: https://run/9",
        ),
        ("false", "", ""),
    ],
)
def test_the_fix_bot_of_main_keeps_one_issue_of_its_failures(
    tmp_path: Path, failed: str, issue: str, last: str
) -> None:
    step = step_of(
        job_of(workflow("after-checks.yml"), "fixes"),
        "Keep the issue of the fix bot of main current",
    )

    result, made = run_step(
        script_of(step), tmp_path, FAILED=failed, ISSUE=issue, URL="https://run/9"
    )

    assert result.returncode == 0, result.stderr
    assert made[0].startswith("gh issue list --state open --search")
    if last:
        assert made[-1].startswith(last)
    else:
        assert made == made[:1]
