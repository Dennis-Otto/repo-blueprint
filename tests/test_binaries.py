"""The binary files of Git that nobody can review: blueprint/binaries.py and the command
binaries, which the step *Binary files* of scripts/check.sh runs."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from blueprint.binaries import (
    EXECUTABLE,
    PROGRAM,
    SNIFFED,
    UNREVIEWABLE,
    Binary,
    binaries,
    problem,
)
from blueprint.cli import main

ELF = b"\x7fELF\x02\x01\x01\0\0\0"


def repository(folder: Path, files: dict[str, bytes]) -> Path:
    """A repository of git with these files in its index, and none committed."""
    subprocess.run(["git", "init", "--quiet", str(folder)], check=True)
    for name, content in files.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(content)
    subprocess.run(["git", "add", "--all"], cwd=folder, check=True)
    return folder


def test_text_passes_whatever_its_name() -> None:
    assert problem("tool.exe", b"#!/bin/sh\necho MZ\n") == ""
    assert problem("empty", b"") == ""


@pytest.mark.parametrize("start", EXECUTABLE)
def test_a_program_or_an_archive_fails_by_its_first_bytes(start: bytes) -> None:
    # Also with the name of a picture, or in the inputs of the fuzz tests.
    for path in ("tool", "logo.png", "fuzz/corpus/seed"):
        assert problem(path, start + b"\0rest") == PROGRAM, (path, start)


@pytest.mark.parametrize(
    "path",
    [
        "docs/images/screen.png",
        "docs/images/demo.GIF",
        "docs/video/tour.mp4",
        "fonts/body.woff2",
        "tests/data/scan.pdf",
        "fuzz/corpus/fuzz_render/table",
    ],
)
def test_pictures_videos_fonts_documents_and_fuzz_inputs_pass(path: str) -> None:
    assert problem(path, b"\x89PNG\r\n\x1a\n\0\0\0\rIHDR") == ""


@pytest.mark.parametrize(
    "path", ["tests/data/letter.docx", "tests/data/sheet.XLSX", "docs/book.epub"]
)
def test_a_document_that_is_a_zip_passes_by_its_name(path: str) -> None:
    assert problem(path, b"PK\x03\x04\x14\0\0\0") == ""
    # Only as a zip: another program or archive with such a name still fails.
    assert problem(path, ELF) == PROGRAM
    assert problem(path, b"\x1f\x8b\x08\0") == PROGRAM


@pytest.mark.parametrize(
    "path", ["data.bin", "lib/thing.pyc", "tests/fuzz/corpus/x", "README"]
)
def test_any_other_binary_file_fails(path: str) -> None:
    assert problem(path, b"data\0more") == UNREVIEWABLE


def test_the_files_of_git_that_nobody_can_review(tmp_path: Path) -> None:
    root = repository(
        tmp_path / "repository",
        {
            "README.md": b"# Demo\n",
            "empty.txt": b"",
            "docs/images/logo.png": b"\x89PNG\r\n\x1a\n\0\0\0\rIHDR",
            "fuzz/corpus/fuzz_render/table": b"| a |\0| b |\n",
            "bin/tool": ELF,
            "docs/images/disguised.png": ELF,
            "data.bin": b"data\0more",
            "gone.bin": b"data\0more",
            # A NUL after the first bytes that git reads is text, as git sees it.
            "late.txt": b"x" * SNIFFED + b"\0",
            ".gitignore": b"ignored.bin\n",
        },
    )
    (root / "gone.bin").unlink()
    (root / "new.jar").write_bytes(b"PK\x03\x04\x14\0\0\0")
    (root / "ignored.bin").write_bytes(b"data\0more")

    assert binaries(root) == [
        Binary("bin/tool", PROGRAM),
        Binary("data.bin", UNREVIEWABLE),
        Binary("docs/images/disguised.png", PROGRAM),
        Binary("new.jar", PROGRAM),
    ]


def test_the_command_names_each_file_and_the_fix(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    root = repository(tmp_path / "repository", {"bin/tool": ELF, "a.dat": b"\0"})

    assert main(["binaries"], root=root) == 1

    lines = capsys.readouterr().out.splitlines()
    assert lines[:2] == [f"a.dat: {UNREVIEWABLE}", f"bin/tool: {PROGRAM}"]
    assert lines[2].startswith("Remove the 2 file(s) from Git: a release builds what")
    assert "OSPS-QA-05.01 and 05.02" in lines[2]
    assert "Delete a file that isn't in Git yet" in lines[2]
    assert len(lines) == 3


def test_the_command_annotates_each_file_in_the_ci(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    root = repository(tmp_path / "repository", {"a,b.dat": b"\0"})

    assert main(["binaries"], root=root) == 1

    out = capsys.readouterr().out
    assert f"::error file=a%2Cb.dat,title=Binary files::a,b.dat {UNREVIEWABLE}\n" in out


def test_the_command_passes_without_such_a_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repository(tmp_path / "repository", {"logo.png": b"\x89PNG\0"})

    assert main(["binaries"], root=root) == 0

    assert capsys.readouterr().out == (
        "Every binary file is a picture, a video, a sound, a font, a document or an "
        "input of the fuzz tests.\n"
    )


def test_the_command_fails_outside_a_repository(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # git looks for a repository up to the folder of the tests, and no further.
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    (tmp_path / "folder").mkdir()

    assert main(["binaries"], root=tmp_path / "folder") == 2

    assert capsys.readouterr().err.startswith("blueprint.py: Command '['git'")
