"""Tests of what the processes of one run of the tests share."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest
import shared
from shared import INTERVAL, copy_of, once, run_folder


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
