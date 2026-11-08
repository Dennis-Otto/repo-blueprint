"""The Python of the blueprint reads what a program that it starts prints, and writes
what it sends to one, in UTF-8, whatever the code page of the machine. gh prints its
JSON in UTF-8, but Python decodes the text of a program with the code page of the
locale unless it is told otherwise: on Windows, cp1252, which has no character for the
byte 0x90 of an emoji such as 🔐 in the body of a pull request. The reader of the
output then fails in a thread of its own, and the answer arrives without any output."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from blueprint.github import Answer, Runner, run_gh, run_gh_as

ROOT = Path(__file__).parents[1]
# The Python of the blueprint that starts programs, other than its tests: the scripts
# at the root, which every repository gets in .github/ as well, the package and the
# scripts of .github/ and of the fuzz tests.
SOURCES = sorted(
    [
        *ROOT.glob("*.py"),
        *(ROOT / "blueprint").rglob("*.py"),
        *(ROOT / ".github").rglob("*.py"),
        *(ROOT / "fuzz").rglob("*.py"),
    ]
)
# The functions of subprocess that start a program and can read its output as text.
STARTS = frozenset({"run", "check_output", "check_call", "call", "Popen"})


def text_without_an_encoding(source: str) -> list[int]:
    """The lines of the calls of the source that start a program, read its output as
    text, with text or universal_newlines, and name no encoding for it."""
    lines = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        name = function.attr if isinstance(function, ast.Attribute) else None
        if isinstance(function, ast.Name):
            name = function.id
        if name not in STARTS:
            continue
        options = {keyword.arg: keyword.value for keyword in node.keywords}
        text = [options.get(word) for word in ("text", "universal_newlines")]
        as_text = any(
            value is not None
            and not (isinstance(value, ast.Constant) and not value.value)
            for value in text
        )
        encoding = options.get("encoding")
        unnamed = encoding is None or (
            isinstance(encoding, ast.Constant) and encoding.value is None
        )
        if as_text and unnamed:
            lines.append(node.lineno)
    return lines


@pytest.mark.parametrize(
    ("source", "lines"),
    [
        ('subprocess.run(["gh", "api", path], text=True)', [1]),
        ('subprocess.run(["gh"], capture_output=True, text=True, check=False)', [1]),
        ('subprocess.check_output(["git", "log"], universal_newlines=True)', [1]),
        ('subprocess.Popen(["gh"], text=as_text)', [1]),
        ('run(["gh"], text=True)', [1]),
        ('x = 1\nsubprocess.call(["gh"], text=True, **options)', [2]),
        ('subprocess.run(["gh"], text=True, encoding=None)', [1]),
        ('subprocess.run(["gh"], text=True, encoding="utf-8")', []),
        ('subprocess.run(["gh"], encoding="utf-8")', []),
        ('subprocess.run(["gh"], capture_output=True)', []),
        ('subprocess.run(["gh"], text=False, universal_newlines=None)', []),
        ('api.get("repos/o/r", text=True)', []),
        ('print("text", text=True)', []),
        ('(lambda: run)()(["gh"], text=True)', []),
    ],
)
def test_a_call_that_reads_text_without_an_encoding_is_found(
    source: str, lines: list[int]
) -> None:
    assert text_without_an_encoding(source) == lines


# mutmut's copy holds the mutants of each function next to it, one of which drops the
# encoding: the test of the runners below finds that one.
@pytest.mark.mutation_unsafe
def test_every_program_that_the_python_starts_speaks_utf_8() -> None:
    found = {
        path.relative_to(ROOT).as_posix(): lines
        for path in SOURCES
        if (lines := text_without_an_encoding(path.read_text("utf-8")))
    }
    assert found == {}


# A gh that answers as gh api --include does: the status line, a header and the body,
# whose fields hold characters that cp1252 lacks and the body sent to it, all as the
# bytes of UTF-8 that gh prints on every machine.
GH = r"""
import json, sys
sent = sys.stdin.buffer.read().decode("utf-8")
body = {"title": "❌ failed, ⏳ waiting, \U0001f510 signed", "sent": sent}
sys.stdout.buffer.write(
    b"HTTP/2.0 200 OK\r\nContent-Type: application/json\r\n\r\n"
    + json.dumps(body, ensure_ascii=False).encode("utf-8")
)
"""


@pytest.mark.parametrize(
    "runner", [run_gh, run_gh_as("the-token-of-the-job")], ids=["own", "as"]
)
def test_the_runners_of_gh_read_and_write_utf_8_on_every_machine(
    monkeypatch: pytest.MonkeyPatch, runner: Runner
) -> None:
    started = subprocess.run
    asked: list[Any] = []

    def run(command: list[str], **options: Any) -> subprocess.CompletedProcess[str]:
        asked.append(options.get("encoding"))
        # A body that the code page can't write would never reach the end of gh's
        # input, and gh would wait for it for ever: the test gives up instead.
        return started([sys.executable, "-c", GH], **options, timeout=60)

    monkeypatch.setattr(subprocess, "run", run)

    answer = Answer.of_request(runner(["api", "--include", "x"], "a reply ⏳ with 🔐"))

    # The code page of Linux and macOS is UTF-8 already, that of Windows isn't: each
    # runner asks for UTF-8 itself, so that it reads the same everywhere.
    assert asked == ["utf-8"]
    assert answer.status == 200
    assert answer.data == {
        "title": "❌ failed, ⏳ waiting, 🔐 signed",
        "sent": "a reply ⏳ with 🔐",
    }
