"""The comment of the coverage bot, from the Cobertura reports of a pull request
and of main.

The report of a pull request is its own: one from a fork writes the names of its
files and the hits of its lines as it likes. A name reaches the comment only as code
in its cell, so that it adds no Markdown, link or mention to what the bot says, and
hits that are no count count as a number or as 0."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

from blueprint.coach import code

COVERAGE_MARKER = "<!-- coverage-bot -->"
# The table shows the first files by name, each name in at most so many characters:
# GitHub takes a comment of up to 65,536 characters.
MOST_FILES = 100
NAME_LENGTH = 200


@dataclass(frozen=True)
class Coverage:
    """The lines of each file that the tests run, from a Cobertura report."""

    files: dict[str, tuple[int, int]]

    @classmethod
    def parse(cls, report: str, root: Path | None = None) -> Coverage:
        """A report names each file relative to the source that holds it, such as lib/
        of PHPUnit or a folder that coverage.py measures. With one source under root,
        every path starts at root; with several, the report doesn't say which source a
        file belongs to, and the names stay as they are."""
        tree = ElementTree.fromstring(report)
        sources = [Path(source.text or "") for source in tree.iter("source")]
        folder = ""
        if root is not None and len(sources) == 1 and sources[0].is_relative_to(root):
            folder = sources[0].relative_to(root).as_posix()
        files: dict[str, tuple[int, int]] = {}
        for element in tree.iter("class"):
            name = element.get("filename", "")
            if folder not in ("", "."):
                name = f"{folder}/{name}"
            lines = element.findall("./lines/line")
            covered = sum(1 for line in lines if runs(line.get("hits", "0")))
            have = files.get(name, (0, 0))
            files[name] = (have[0] + covered, have[1] + len(lines))
        return cls(files)

    @property
    def total(self) -> tuple[int, int]:
        return (
            sum(covered for covered, _ in self.files.values()),
            sum(lines for _, lines in self.files.values()),
        )


def runs(hits: str) -> bool:
    """Whether the tests run a line that many times: a count such as 1.5 counts as a
    number, one that is no number as 0."""
    try:
        return float(hits) > 0
    except ValueError:
        return False


def cell(name: str) -> str:
    """The name of a file as code in a cell of the table, on one line: no pipe of it
    ends the cell, which GitHub looks for inside code as well."""
    return code(name, NAME_LENGTH).replace("|", "\\|") or "(unnamed file)"


def percent(covered: int, lines: int) -> float:
    return 100.0 if lines == 0 else 100 * covered / lines


def coverage_comment(head: Coverage, base: Coverage | None) -> str:
    """The comment of the coverage bot: the coverage of a pull request, compared with
    that of main, and each file whose coverage differs, the first MOST_FILES by name."""
    covered, lines = head.total
    now = percent(covered, lines)
    rows = [
        COVERAGE_MARKER,
        "### Coverage",
        "",
        "| | Lines | Covered |",
        "| --- | ---: | ---: |",
        f"| This pull request | {lines} | {now:.2f} % |",
    ]
    if base is None:
        rows += ["", "main has no coverage report yet to compare with."]
        return "\n".join([*rows, ""])
    before = percent(*base.total)
    rows.append(f"| main | {base.total[1]} | {before:.2f} % ({now - before:+.2f}) |")
    changed = []
    for name in sorted(set(head.files) | set(base.files)):
        old = base.files.get(name)
        new = head.files.get(name)
        old_text = "new" if old is None else f"{percent(*old):.2f} %"
        new_text = "removed" if new is None else f"{percent(*new):.2f} %"
        if old_text != new_text:
            changed.append(f"| {cell(name)} | {old_text} | {new_text} |")
    if not changed:
        rows += ["", "No file changes its coverage."]
        return "\n".join([*rows, ""])
    rows += ["", "| File | main | This pull request |", "| --- | ---: | ---: |"]
    rows += changed[:MOST_FILES]
    if len(changed) > MOST_FILES:
        rows += [
            "",
            f"{len(changed) - MOST_FILES} more files change their coverage; the "
            "artifact coverage of the checks has the whole report.",
        ]
    return "\n".join([*rows, ""])
