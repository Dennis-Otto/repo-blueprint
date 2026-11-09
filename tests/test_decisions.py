"""Each record of a decision in docs/decisions/ has a number of its own, the next one
after the last, and the index docs/decisions/README.md lists each record once, in the
order of the numbers. Two pull requests that each take the next free number for a
record of their own merge without a conflict of Git, since their files have different
names: nothing else fails when two records share a number, when the index lists a
record twice, misses one or names a file that doesn't exist. These tests do, so that a
merge of main into the second branch, which the bot that keeps the branches current
makes, shows the clash as a failing test of that branch, with the numbers and the
files, before it reaches main."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from itertools import pairwise
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
# The records of the blueprint, and those that the template gives a new repository.
FOLDERS = ["docs/decisions", "template/docs/decisions"]
INDEX = "README.md"
# The record to copy, which is no decision and stays out of the index.
TEMPLATE = "0000-template.md"
# A record: four digits and the words of its title, such as 0001-record-decisions.md.
RECORD = re.compile(r"(?P<number>\d{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md")
# A row of the index, which names the record by its number and links its file, such as
# | [0001](0001-record-decisions.md) | Record the decisions ... | accepted |
ROW = re.compile(r"^\|\s*\[(?P<number>[^\]]*)\]\((?P<file>[^)]*)\)\s*\|", re.MULTILINE)
HOW_TO_FIX = (
    "Another pull request took the number first, or a record lost its row: give your "
    "record the next free number, in the name of its file and in its row of "
    "{folder}/README.md, and fix each link to it."
)


def numbered(names: Iterable[str]) -> tuple[dict[int, list[str]], list[str]]:
    """The records of a folder by their numbers, and the findings of the files that
    are neither a record, the template nor the index."""
    records: dict[int, list[str]] = defaultdict(list)
    found = []
    for name in sorted(names):
        if name in {INDEX, TEMPLATE}:
            continue
        match = RECORD.fullmatch(name)
        if match is None:
            found.append(f"{name} is no record: a record is named NNNN-its-title.md")
        else:
            records[int(match["number"])].append(name)
    return records, found


def number_findings(records: dict[int, list[str]]) -> list[str]:
    """Each number of two records or more, and each that the records skip: the numbers
    run from 0001 to the last, 0000 being the template's."""
    found = [
        f"{number:04d} is the number of {len(files)} records: {', '.join(files)}"
        for number, files in sorted(records.items())
        if len(files) > 1
    ]
    if 0 in records:
        found.append(f"0000 is the number of the template, not of {records[0][0]}")
    skipped = [
        number for number in range(1, max(records, default=0)) if number not in records
    ]
    if skipped:
        numbers = ", ".join(f"{number:04d}" for number in skipped)
        found.append(f"no record has the number {numbers}, which the numbers skip")
    return found


def index_findings(names: Iterable[str], index: str) -> list[str]:
    """Each record that the index lists twice, misses, names by another number or lists
    out of order, and each file that it names but the folder doesn't have."""
    files = set(names)
    rows = [(row["number"], row["file"]) for row in ROW.finditer(index)]
    found = []
    for file, times in sorted(Counter(file for _, file in rows).items()):
        if times > 1:
            found.append(f"the index lists {file} {times} times")
    for number, file in rows:
        match = RECORD.fullmatch(file)
        if file not in files or file in {INDEX, TEMPLATE}:
            found.append(f"the index names {file}, which is no record of the folder")
        elif match is not None and match["number"] != number:
            found.append(f"the index names {file} as {number}")
    listed = {file for _, file in rows}
    records, _ = numbered(files)
    found += [
        f"the index misses {file}"
        for number in sorted(records)
        for file in records[number]
        if file not in listed
    ]
    order = [file for _, file in rows]
    found += [
        f"the index lists {later} after {earlier}"
        for earlier, later in pairwise(order)
        if later < earlier
    ]
    return found


def findings(names: Iterable[str], index: str) -> list[str]:
    """What is wrong with the numbers of the records of a folder, from the names of its
    files, and with its index, from its text."""
    names = list(names)
    records, found = numbered(names)
    return found + number_findings(records) + index_findings(names, index)


@pytest.mark.parametrize("folder", FOLDERS)
def test_every_record_has_a_number_of_its_own_and_one_row(folder: str) -> None:
    path = ROOT / folder
    names = [entry.name for entry in path.iterdir()]
    index = (path / INDEX).read_text(encoding="utf-8")
    found = findings(names, index)
    assert found == [], "\n".join([HOW_TO_FIX.format(folder=folder), *found])


def test_the_folders_hold_records() -> None:
    # A test that finds no record passes on nothing.
    for folder in FOLDERS:
        records, found = numbered(entry.name for entry in (ROOT / folder).iterdir())
        assert found == []
        assert 1 in records, folder


def row(file: str, number: str | None = None) -> str:
    return f"| [{number or file[:4]}]({file}) | A decision | accepted |\n"


def index_of(*rows: str) -> str:
    return (
        "# Decisions\n\nCopy [the template](0000-template.md).\n\n"
        "| Record | Decision | Status |\n| --- | --- | --- |\n" + "".join(rows)
    )


A = "0001-a.md"
B = "0002-b.md"
C = "0003-c.md"
FOLDER = [INDEX, TEMPLATE, A, B, C]


def test_a_folder_in_order_has_no_findings() -> None:
    assert findings(FOLDER, index_of(row(A), row(B), row(C))) == []


def test_two_records_of_one_number_fail_with_their_files() -> None:
    # Two pull requests each took 0003, and main merged into the second one.
    clash = "0003-another.md"
    index = index_of(row(A), row(B), row(clash), row(C))
    assert findings([*FOLDER, clash], index) == [
        "0003 is the number of 2 records: 0003-another.md, 0003-c.md"
    ]


def test_a_skipped_number_fails() -> None:
    later = "0005-e.md"
    index = index_of(row(A), row(B), row(C), row(later))
    assert findings([*FOLDER, later], index) == [
        "no record has the number 0004, which the numbers skip"
    ]


def test_a_row_twice_fails() -> None:
    assert findings(FOLDER, index_of(row(A), row(B), row(B), row(C))) == [
        "the index lists 0002-b.md 2 times"
    ]


def test_a_missing_row_fails() -> None:
    assert findings(FOLDER, index_of(row(A), row(C))) == ["the index misses 0002-b.md"]


def test_a_row_of_no_file_fails() -> None:
    # The second pull request renumbered its file, but not its row.
    gone = "0004-d.md"
    assert findings(FOLDER, index_of(row(A), row(B), row(C), row(gone))) == [
        "the index names 0004-d.md, which is no record of the folder"
    ]


def test_a_row_of_the_template_or_the_index_fails() -> None:
    index = index_of(row(TEMPLATE), row(A), row(B), row(C), row(INDEX, "0004"))
    assert findings(FOLDER, index) == [
        "the index names 0000-template.md, which is no record of the folder",
        "the index names README.md, which is no record of the folder",
    ]


def test_a_row_with_another_number_fails() -> None:
    index = index_of(row(A), row(B, "0003"), row(C))
    assert findings(FOLDER, index) == ["the index names 0002-b.md as 0003"]


def test_a_row_out_of_order_fails() -> None:
    assert findings(FOLDER, index_of(row(A), row(C), row(B))) == [
        "the index lists 0002-b.md after 0003-c.md"
    ]


def test_a_file_that_is_no_record_fails() -> None:
    stray = "0004 A decision.md"
    assert findings([*FOLDER, stray], index_of(row(A), row(B), row(C))) == [
        "0004 A decision.md is no record: a record is named NNNN-its-title.md"
    ]


def test_a_record_of_number_zero_fails() -> None:
    zero = "0000-another.md"
    index = index_of(row(zero), row(A), row(B), row(C))
    assert findings([*FOLDER, zero], index) == [
        "0000 is the number of the template, not of 0000-another.md"
    ]


def test_an_empty_folder_has_no_findings() -> None:
    assert findings([INDEX, TEMPLATE], index_of()) == []
