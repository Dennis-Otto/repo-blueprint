"""The gh of the tests that run the steps of the workflows: it answers each call as the
test planned it and writes the call down, with what gh would have read for it.

tests/workflow_steps.py puts a script named gh first on the PATH of the step, which
starts this file with the Python of the tests. The test plans its answers in the file
$FAKE_GH_ANSWERS, a JSON list in which the first answer whose `args` match all the
arguments of the call, joined by spaces, answers it: with `out` on stdout, `err` on
stderr and `code` as the exit code, or with `json` through the filter of --jq, as gh
prints the answer of the API; to gh release download with --output, `out` goes into
that file, as the asset does. An answer with `once` answers one call only, so that a
later one answers the next. A call without an answer fails, as an unexpected call of
the real gh would do harm, and so does a call of gh api that doesn't ask right after
`api` for the version of the API in $FAKE_GH_VERSION, as every step asks with
--header "$API_VERSION_HEADER": the answers and the log hold the call without it.
"""

from __future__ import annotations

import itertools
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# The options whose value gh reads as a file, "-" for stdin, and the fields whose
# value after @ it reads so.
FILES = ("--body-file", "--input", "--notes-file", "-F", "--field")


def read(arguments: list[str]) -> dict[str, str]:
    """What gh reads for the call, by its option: the file of --body-file, --input and
    --notes-file, and the file of a field such as -F body=@file, by "-F body"."""
    found: dict[str, str] = {}
    for option, value in itertools.pairwise(arguments):
        if option not in FILES:
            continue
        name = option
        if option in ("-F", "--field"):
            key, at, value = value.partition("=@")
            if not at:
                continue
            name = f"{option} {key}"
        if value == "-":
            found[name] = sys.stdin.read()
        else:
            path = Path(value)
            found[name] = (
                path.read_text(encoding="utf-8") if path.is_file() else "<missing>"
            )
    return found


def filtered(answer: Any, arguments: list[str]) -> tuple[str, str, int]:
    """The JSON of an answer as gh prints it: through the filter of --jq, or as it is.
    Through --jq, gh prints a string raw, null as an empty line and other values as
    compact JSON, one result on each line."""
    flags = [index for index, word in enumerate(arguments) if word in ("--jq", "-q")]
    if not flags or flags[-1] + 1 >= len(arguments):
        return json.dumps(answer) + "\n", "", 0
    # Only here: gh starts about 1600 times in a run of the tests, and most of its
    # calls need neither module, whose import takes a quarter of its start.
    import shutil
    import subprocess

    jq = shutil.which("jq")
    if jq is None:
        return "", "fake gh: an answer through --jq needs jq\n", 127
    done = subprocess.run(
        [jq, "-c", arguments[flags[-1] + 1]],
        input=json.dumps(answer).encode(),
        capture_output=True,
        check=False,
    )
    printed = "".join(
        f"{shown(json.loads(line))}\n"
        for line in done.stdout.decode().replace("\r\n", "\n").splitlines()
    )
    return printed, done.stderr.decode(), done.returncode


def shown(value: Any) -> str:
    """One result of --jq as gh prints it."""
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return json.dumps(value, separators=(",", ":"))


def main(arguments: list[str]) -> int:
    if arguments[:1] == ["api"]:
        if arguments[1:3] != ["--header", os.environ["FAKE_GH_VERSION"]]:
            joined = " ".join(arguments)
            sys.stderr.write(f"fake gh: gh api asks for no version: gh {joined}\n")
            return 1
        arguments = arguments[:1] + arguments[3:]
    joined = " ".join(arguments)
    answers = json.loads(Path(os.environ["FAKE_GH_ANSWERS"]).read_text("utf-8"))
    used_file = Path(os.environ["FAKE_GH_USED"])
    used = set(used_file.read_text(encoding="utf-8").split())
    record = {"args": arguments, "read": read(arguments)}
    with Path(os.environ["FAKE_GH_LOG"]).open("a", encoding="utf-8") as log:
        log.write(json.dumps(record) + "\n")
    for index, answer in enumerate(answers):
        if answer["once"] and str(index) in used:
            continue
        if not re.fullmatch(answer["args"], joined, re.DOTALL):
            continue
        if answer["once"]:
            with used_file.open("a", encoding="utf-8") as file:
                file.write(f"{index}\n")
        out, err, code = answer["out"], answer["err"], answer["code"]
        if "json" in answer:
            out, failed, failure = filtered(answer["json"], arguments)
            err, code = err + failed, failure or code
        # gh release download --output writes the asset into that file, as gh does,
        # when the answer is no error.
        target = downloaded_to(arguments)
        if target and not int(code):
            Path(target).write_bytes(out.encode())
            out = ""
        # Bytes, so that Python on Windows ends no line with CRLF, as gh doesn't.
        sys.stdout.buffer.write(out.encode())
        sys.stderr.buffer.write(err.encode())
        return int(code)
    sys.stderr.write(f"fake gh: no answer for: gh {joined}\n")
    return 1


def downloaded_to(arguments: list[str]) -> str:
    """The file of --output of gh release download, which gets the asset: empty for any
    other call, and for "-", which is stdout."""
    if arguments[:2] != ["release", "download"]:
        return ""
    for option, value in itertools.pairwise(arguments):
        if option in ("--output", "-O") and value != "-":
            return value
    return ""


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
