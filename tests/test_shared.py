"""Tests of what the processes of one run of the tests share."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from importlib.util import cache_from_source
from pathlib import Path

import pytest
import shared
import yaml
from shared import INTERVAL, copy_of, load_yaml, once, run_folder


def made_elsewhere(folder: Path) -> None:
    pytest.fail(f"{folder} is another process's to make")


def test_the_folder_of_the_run_holds_that_of_each_process(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
    alone = run_folder(tmp_path_factory)
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw3")
    shared_by_all = run_folder(tmp_path_factory)

    assert alone == tmp_path_factory.getbasetemp()
    assert shared_by_all == tmp_path_factory.getbasetemp().parent


def test_the_processes_of_the_run_share_one_folder_for_their_bytecode(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    # A folder for each process compiles the standard library and Copier once in each.
    folder = str(run_folder(tmp_path_factory) / "pycache")

    assert sys.pycache_prefix == folder
    assert os.environ["PYTHONPYCACHEPREFIX"] == folder


def test_a_python_of_a_test_reads_the_bytecode_that_another_one_wrote(
    tmp_path: Path,
) -> None:
    module = tmp_path / "written_once.py"
    module.write_text("VALUE = 1\n", encoding="utf-8")
    command = [sys.executable, "-c", "import written_once"]

    subprocess.run(command, cwd=tmp_path, check=True)
    written = Path(cache_from_source(str(module)))
    before = written.stat().st_mtime_ns
    subprocess.run(command, cwd=tmp_path, check=True)

    assert written.stat().st_mtime_ns == before
    assert not (tmp_path / "__pycache__").exists()


@pytest.mark.parametrize(
    "text",
    [
        "on: push\nyes: [1, 1.5, 0x10, ~, 2026-11-01]\n",
        "base: &base {a: 1}\nderived:\n  <<: *base\n  b: |\n    text\n",
        '"quoted: key": "\u00dcmlaut"\n',
    ],
)
def test_the_fast_parser_reads_what_the_safe_one_reads(text: str) -> None:
    assert load_yaml(text) == yaml.safe_load(text)


def test_the_fast_parser_reads_the_workflows_as_the_safe_one_does() -> None:
    for workflow in (shared.ROOT / ".github/workflows").glob("*.yml"):
        text = workflow.read_text(encoding="utf-8")
        assert load_yaml(text) == yaml.safe_load(text), workflow.name


def test_no_test_parses_yaml_with_the_slow_parser() -> None:
    # The parser of Python took 23 of 460 seconds of all the processes of a run.
    slow = "yaml." + "safe_load("
    found = [
        path.name
        for path in Path(__file__).parent.glob("*.py")
        if path != Path(__file__) and slow in path.read_text(encoding="utf-8")
    ]

    assert not found


def test_a_folder_is_made_once(tmp_path: Path) -> None:
    made: list[Path] = []

    def make(folder: Path) -> None:
        made.append(folder)
        folder.mkdir()

    first = once(tmp_path / "project", make)
    again = once(tmp_path / "project", make)

    assert first == again == tmp_path / "project"
    assert made == [tmp_path / "project"]
    assert (tmp_path / "project.done").exists()


def test_a_process_waits_for_the_folder_that_another_one_makes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Another process has claimed the folder, and finishes it while this one waits.
    (tmp_path / "project.claim").mkdir()
    waits: list[float] = []

    def sleep(seconds: float) -> None:
        waits.append(seconds)
        (tmp_path / "project.done").touch()

    monkeypatch.setattr(time, "sleep", sleep)

    assert once(tmp_path / "project", made_elsewhere) == tmp_path / "project"
    assert waits == [INTERVAL]


def test_a_folder_that_failed_fails_for_every_process(tmp_path: Path) -> None:
    def make(folder: Path) -> None:
        raise OSError("No space left on device")

    with pytest.raises(OSError, match="No space left on device"):
        once(tmp_path / "project", make)
    # Another process learns why, instead of waiting for a folder that never comes.
    with pytest.raises(RuntimeError, match="OSError: No space left on device"):
        once(tmp_path / "project", make)


def test_a_process_waits_no_longer_than_its_patience(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "project.claim").mkdir()
    monkeypatch.setattr(shared, "PATIENCE", -1.0)

    with pytest.raises(TimeoutError, match=r"didn't make .*project within"):
        once(tmp_path / "project", made_elsewhere)


def test_the_copy_of_a_repository_has_its_files_as_git_sees_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Git without the configuration of the machine, which may sign every commit.
    config = tmp_path / "gitconfig"
    config.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    repository = tmp_path / "repository"
    (repository / "docs").mkdir(parents=True)
    for name, text in {
        ".gitignore": ".venv/\n",
        "docs/kept.md": "Committed.\n",
        "changed.md": "Committed.\n",
        "deleted.md": "Committed.\n",
    }.items():
        (repository / name).write_text(text, encoding="utf-8")
    identity = ["-c", "user.name=Dev", "-c", "user.email=dev@example.com"]
    for arguments in (
        ["init", "--quiet"],
        ["add", "--all"],
        [*identity, "commit", "--quiet", "--message", "The start"],
    ):
        subprocess.run(["git", *arguments], cwd=repository, check=True)
    (repository / "changed.md").write_text("Not yet committed.\n", encoding="utf-8")
    (repository / "deleted.md").unlink()
    (repository / "new.md").write_text("Not yet added.\n", encoding="utf-8")
    (repository / ".venv").mkdir()
    (repository / ".venv/pyvenv.cfg").write_text("home = /usr\n", encoding="utf-8")

    copy_of(repository, tmp_path / "copy")

    assert sorted(
        path.relative_to(tmp_path / "copy").as_posix()
        for path in (tmp_path / "copy").rglob("*")
        if path.is_file()
    ) == [".gitignore", "changed.md", "docs/kept.md", "new.md"]
    assert (tmp_path / "copy/changed.md").read_text(encoding="utf-8") == (
        "Not yet committed.\n"
    )


def test_no_test_sees_the_repository_that_runs_the_tests() -> None:
    assert "GIT_DIR" in shared.GIT_REPOSITORY_VARIABLES
    assert not set(shared.GIT_REPOSITORY_VARIABLES) & set(os.environ)


# It runs the tests in a copy of the repository again, which the copy of the mutation
# tests has no configuration of pytest for; it tests no code of the blueprint.
@pytest.mark.mutation_unsafe
def test_the_tests_leave_the_repository_that_git_dir_names_alone(
    tmp_path: Path,
) -> None:
    # Git sets GIT_DIR for its hooks in a worktree, such as the one before a push that
    # runs the tests, and an agent sets GIT_DIR and GIT_WORK_TREE for a worktree in a
    # container. A test that makes a repository of its own with git init and commits
    # must still leave that one alone: its commits, branches, configuration and
    # checkout.
    outer = tmp_path / "outer"
    outer.mkdir()
    environment = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": str(tmp_path / "gitconfig"),
        "GIT_CONFIG_NOSYSTEM": "1",
    }

    def git(*arguments: str) -> str:
        return subprocess.run(
            [
                "git",
                "-c",
                "user.name=Dev",
                "-c",
                "user.email=dev@example.com",
                *arguments,
            ],
            cwd=outer,
            capture_output=True,
            encoding="utf-8",
            env=environment,
            check=True,
        ).stdout

    def state() -> str:
        return (
            git("for-each-ref")
            + git("status", "--porcelain", "--untracked-files=all")
            + (outer / ".git/config").read_text(encoding="utf-8")
        )

    (outer / "README.md").write_text(
        "The repository that runs the tests.\n", encoding="utf-8"
    )
    git("init", "--quiet")
    git("add", "README.md")
    git("commit", "--quiet", "--message", "The start")
    # A change not yet committed, which a git add --all of a test would take in.
    (outer / "notes.md").write_text("Not yet committed.\n", encoding="utf-8")
    before = state()
    # A test that commits in a repository of its own.
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "-q",
            f"--basetemp={tmp_path / 'run'}",
            "tests/test_shared.py::"
            "test_the_copy_of_a_repository_has_its_files_as_git_sees_them",
        ],
        cwd=shared.ROOT,
        capture_output=True,
        encoding="utf-8",
        env={
            **environment,
            "GIT_DIR": str(outer / ".git"),
            "GIT_WORK_TREE": str(outer),
            "GIT_INDEX_FILE": str(outer / ".git/index"),
        },
        check=False,
    )

    assert state() == before
    assert run.returncode == 0, run.stdout + run.stderr
