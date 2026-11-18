"""The records of the decisions: blueprint/decisions.py and the command decisions, which
the step *Records of decisions* of scripts/check.sh runs in every repository.

Each record of a decision in docs/decisions/ has a number of its own: a new one that of
its pull request or of an issue that the pull request fixes, which the CI of the pull
request checks (decision 1033). The index docs/decisions/README.md lists each released
record at most once, in the order of the values of the numbers; pull requests leave it
alone, and the release writes the rows of the new records with `decisions --complete`.
So two pull requests that each add a record merge without a conflict of Git. The step
still fails when two records share a number, so that a merge of main into the second
branch, which the bot that keeps the branches current makes, shows the clash as a
failing check of that branch before it reaches main. The records that the template
gives a new repository are checked here, where no step reads them."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from shared import ROOT, git_environment

from blueprint.cli import main
from blueprint.decisions import (
    INDEX,
    TABLE,
    TEMPLATE,
    PullRequest,
    closed_issues,
    description_of,
    findings,
    fixed,
    names_of,
    next_free,
    numbered,
    numbers_of,
    own_number,
    pull_request_findings,
    pull_request_of,
    restated,
    row_of,
)

# The records of the blueprint, and those that the template gives a new repository.
FOLDERS = ["docs/decisions", "template/docs/decisions"]
HOW_TO_FIX = (
    "Another pull request took the number first, or a row of {folder}/README.md is "
    "wrong: give your record the number of its pull request, in the name of its file "
    "and in each link to it, and leave the index alone, which the release writes."
)
# The variables of the runner that tell the step which pull request it checks.
PULL_REQUEST_VARIABLES = ("GITHUB_REF", "GITHUB_SHA", "GITHUB_EVENT_PATH")


@pytest.fixture(autouse=True)
def no_pull_request_of_the_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test sees the pull request whose CI runs the tests: one that needs one
    sets its own."""
    for name in PULL_REQUEST_VARIABLES:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def own_git(monkeypatch: pytest.MonkeyPatch) -> None:
    """Git in the blueprint's own checkout, with the variables that point it there."""
    for name, value in git_environment(ROOT).items():
        monkeypatch.setenv(name, value)


# It asks Git for the files of the folder, which the copy of the mutation tests has no
# Git for.
@pytest.mark.mutation_unsafe
@pytest.mark.usefixtures("own_git")
@pytest.mark.parametrize("folder", FOLDERS)
def test_every_record_has_a_number_of_its_own_and_one_row(folder: str) -> None:
    names = names_of(ROOT, folder)
    index = (ROOT / folder / INDEX).read_text(encoding="utf-8")
    found = findings(names, index)
    assert found == [], "\n".join([HOW_TO_FIX.format(folder=folder), *found])


# It asks Git for the files of the folder, which the copy of the mutation tests has no
# Git for.
@pytest.mark.mutation_unsafe
@pytest.mark.usefixtures("own_git")
def test_the_folders_hold_records() -> None:
    # A test that finds no record passes on nothing.
    for folder in FOLDERS:
        records, found = numbered(names_of(ROOT, folder))
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
    # Its row came last, after the one of the record of main.
    index = index_of(row(A), row(B), row(C), row(clash))
    assert findings([*FOLDER, clash], index) == [
        "0003 is the number of 2 records: 0003-another.md, 0003-c.md"
    ]


def test_the_numbers_may_skip_since_a_record_takes_that_of_its_pull_request() -> None:
    later = "1033-e.md"
    index = index_of(row(A), row(B), row(C), row(later))
    assert findings([*FOLDER, later], index) == []


def test_the_index_lists_the_records_by_the_values_of_their_numbers() -> None:
    # Five digits after four: by the text, 10000 would come before 9999.
    ten_thousand, high = "10000-f.md", "9999-e.md"
    names = [*FOLDER, high, ten_thousand]
    in_order = index_of(row(A), row(B), row(C), row(high), row(ten_thousand, "10000"))
    assert findings(names, in_order) == []
    out_of_order = index_of(
        row(A), row(B), row(C), row(ten_thousand, "10000"), row(high)
    )
    assert findings(names, out_of_order) == [
        "the index lists 9999-e.md after 10000-f.md"
    ]
    assert fixed(out_of_order, names, text_of) == in_order


def test_a_row_twice_fails() -> None:
    assert findings(FOLDER, index_of(row(A), row(B), row(B), row(C))) == [
        "the index lists 0002-b.md 2 times"
    ]


def test_a_missing_row_is_no_finding_since_the_release_writes_it() -> None:
    assert findings(FOLDER, index_of(row(A), row(C))) == []


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


def test_a_folder_without_an_index_checks_the_numbers_alone() -> None:
    clash = "0003-another.md"
    assert findings([TEMPLATE, A, B, C], None) == []
    assert findings([TEMPLATE, A, B, C, clash], None) == [
        "0003 is the number of 2 records: 0003-another.md, 0003-c.md"
    ]


def test_the_next_free_number_follows_the_last() -> None:
    assert next_free(numbered(FOLDER)[0]) == 4
    assert next_free(numbered([INDEX, TEMPLATE])[0]) == 1
    assert next_free({1, 2, 1033}) == 1034


# The fix of the index.

RECORDS = {
    A: "# A\n\n- Status: accepted\n",
    B: "# B\n\n- Status: accepted\n",
    C: "# C\n\n- Status: accepted\n",
}


def text_of(name: str) -> str:
    return RECORDS[name]


def test_the_fix_leaves_an_index_in_order_as_it_is() -> None:
    index = index_of(row(A), row(B), row(C))
    assert fixed(index, FOLDER, text_of) == index


def test_the_fix_puts_the_rows_in_order() -> None:
    index = index_of(row(C), row(A), row(B))
    assert fixed(index, FOLDER, text_of) == index_of(row(A), row(B), row(C))


def test_the_fix_gives_a_row_the_number_of_its_file() -> None:
    index = index_of(row(A), row(B, "0003"), row(C))
    assert fixed(index, FOLDER, text_of) == index_of(row(A), row(B), row(C))


def test_a_row_may_link_its_record_with_dot_slash() -> None:
    index = index_of(*(row(name).replace("](", "](./") for name in (A, B, C)))
    assert findings(FOLDER, index) == []


def test_the_fix_gives_a_row_with_dot_slash_the_number_of_its_file_in_place() -> None:
    def dotted(file: str, number: str | None = None) -> str:
        return row(file, number).replace("](", "](./")

    index = index_of(dotted(A), dotted(B, "0003"), dotted(C))
    assert fixed(index, FOLDER, text_of) == index_of(dotted(A), dotted(B), dotted(C))


def test_the_fix_drops_a_second_copy_of_a_row() -> None:
    index = index_of(row(A), row(B), row(B), row(C))
    assert fixed(index, FOLDER, text_of) == index_of(row(A), row(B), row(C))


def test_the_fix_keeps_two_rows_of_one_record_that_differ() -> None:
    other = row(B).replace("A decision", "Another decision")
    index = index_of(row(A), row(B), other, row(C))
    assert fixed(index, FOLDER, text_of) == index
    assert findings(FOLDER, index) == ["the index lists 0002-b.md 2 times"]


def test_the_fix_adds_no_row_since_a_pull_request_leaves_the_index_alone() -> None:
    names = [*FOLDER, "1040-d.md"]
    index = index_of(row(C), row(A))
    texts = {**RECORDS, "1040-d.md": "# D\n"}
    assert fixed(index, names, texts.__getitem__) == index_of(row(A), row(C))


def test_the_complete_index_adds_the_row_of_a_record_from_its_title_and_status() -> (
    None
):
    names = [*FOLDER, "0004-d.md"]
    text = (
        "# The decision | in a few words\n\n- Status: replaced by [0005](0005-e.md)\n"
    )
    index = index_of(row(A), row(B), row(C))
    expected = index + (
        r"| [0004](0004-d.md) | The decision \| in a few words | replaced by "
        "[0005](0005-e.md) |\n"
    )
    texts = {**RECORDS, "0004-d.md": text}
    assert fixed(index, names, texts.__getitem__, complete=True) == expected
    assert findings(names, expected) == []


def test_the_complete_index_copies_the_status_of_each_record_into_its_row() -> None:
    # A pull request that amends 0002 changes only its record.
    amended = "# B\n\n- Status: accepted, amended by [1033](1033-d.md)\n"
    texts = {**RECORDS, B: amended, "1033-d.md": "# D | E\n\n- Status: accepted\n"}
    names = [*FOLDER, "1033-d.md"]
    index = index_of(row(A), row(B), row(C))
    assert fixed(index, names, texts.__getitem__, complete=True) == index_of(
        row(A),
        "| [0002](0002-b.md) | A decision | accepted, amended by [1033](1033-d.md) |\n",
        row(C),
        r"| [1033](1033-d.md) | D \| E | accepted |" + "\n",
    )


def test_the_complete_index_keeps_the_status_of_a_row_whose_record_has_none() -> None:
    index = index_of(row(A), "| [0002](0002-b.md) | Other | cells | here |\n")
    texts = {A: "# A\n", B: "# B\n\n- Status: replaced\n"}
    assert fixed(index, [INDEX, A, B], texts.__getitem__, complete=True) == index


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        (
            "| [0001](0001-a.md) | A \\| B | old |\n",
            "| [0001](0001-a.md) | A \\| B | new \\| status |\n",
        ),
        # The last row may lack its line break, and the cells their spaces.
        ("| [0001](0001-a.md) |A|old|", "| [0001](0001-a.md) |A| new \\| status |"),
        (
            "| [0001](0001-a.md) | A | old |  \r\n",
            "| [0001](0001-a.md) | A | new \\| status |\r\n",
        ),
        # Two cells or four: not the table of the index, which stays as it is.
        ("| [0001](0001-a.md) | old |\n", "| [0001](0001-a.md) | old |\n"),
        (
            "| [0001](0001-a.md) | A | B | old |\n",
            "| [0001](0001-a.md) | A | B | old |\n",
        ),
    ],
)
def test_a_row_takes_the_status_of_its_record(line: str, expected: str) -> None:
    assert restated(line, "# A\n\n* Status: new | status\n") == expected
    # A record without a status leaves the row as it is.
    assert restated(line, "# A\n") == line


def test_a_new_row_of_a_record_without_heading_or_status_takes_its_name() -> None:
    assert row_of("0004-the-new-way.md", "Text.\n") == (
        "| [0004](0004-the-new-way.md) | The new way |  |\n"
    )
    assert row_of("10400-the-new-way.md", "Text.\n") == (
        "| [10400](10400-the-new-way.md) | The new way |  |\n"
    )


def test_the_fix_moves_a_row_to_the_renamed_file_of_its_record() -> None:
    # The second pull request moved its record from 0003 to 0004, but not its row.
    names = [*FOLDER, "0004-another.md"]
    index = index_of(row(A), row(B), row("0003-another.md"), row(C))
    assert fixed(index, names, text_of) == index_of(
        row(A), row(B), row(C), row("0004-another.md")
    )


def test_the_fix_leaves_a_row_of_a_file_that_is_gone_without_its_one_record() -> None:
    # Two records of the same title that no row names: which one is meant isn't sure.
    names = [*FOLDER, "0004-d.md", "0005-d.md"]
    texts = {**RECORDS, "0004-d.md": "# D\n", "0005-d.md": "# D again\n"}
    index = index_of(row(A), row(B), row(C), row("0006-d.md"), row(INDEX, "0007"))
    assert fixed(index, names, texts.__getitem__, complete=True) == index_of(
        row(A),
        row(B),
        row(C),
        "| [0004](0004-d.md) | D |  |\n",
        "| [0005](0005-d.md) | D again |  |\n",
        row("0006-d.md"),
        row(INDEX, "0007"),
    )


def test_the_fix_keeps_two_records_of_one_number_in_their_order() -> None:
    clash = "0003-another.md"
    index = index_of(row(A), row(C), row(clash), row(B))
    assert fixed(index, [*FOLDER, clash], text_of) == index_of(
        row(A), row(B), row(C), row(clash)
    )


def test_the_complete_index_adds_the_rows_below_the_head_of_an_empty_table() -> None:
    index = index_of() + "\nMore text.\n"
    assert fixed(index, FOLDER, text_of) == index
    assert fixed(index, FOLDER, text_of, complete=True) == (
        index_of(
            "| [0001](0001-a.md) | A | accepted |\n",
            "| [0002](0002-b.md) | B | accepted |\n",
            "| [0003](0003-c.md) | C | accepted |\n",
        )
        + "\nMore text.\n"
    )


def test_the_complete_index_adds_a_table_to_an_index_without_one() -> None:
    names = [INDEX, TEMPLATE, A]
    assert fixed("# Decisions", names, text_of, complete=True) == (
        "# Decisions\n\n" + TABLE + "| [0001](0001-a.md) | A | accepted |\n"
    )
    assert fixed("", names, text_of, complete=True) == (
        TABLE + "| [0001](0001-a.md) | A | accepted |\n"
    )
    assert fixed("# Decisions\n", [INDEX, TEMPLATE], text_of, complete=True) == (
        "# Decisions\n"
    )
    assert fixed("# Decisions", names, text_of) == "# Decisions"


def test_the_fix_ends_each_line_of_a_last_row_that_moves() -> None:
    index = index_of(row(B), row(A)).removesuffix("\n")
    assert fixed(index, [INDEX, TEMPLATE, A, B], text_of) == index_of(row(A), row(B))


def test_the_complete_index_ends_the_head_of_a_table_that_ends_the_index() -> None:
    index = index_of().removesuffix("\n")
    assert fixed(index, [INDEX, TEMPLATE, A], text_of, complete=True) == index_of(
        "| [0001](0001-a.md) | A | accepted |\n"
    )


# The command, in a repository of Git.


def repository(folder: Path, files: dict[str, str]) -> Path:
    """A repository of git with these files of docs/decisions/ in its index."""
    subprocess.run(["git", "init", "--quiet", str(folder)], check=True)
    for name, content in files.items():
        path = folder / "docs/decisions" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
    subprocess.run(["git", "add", "--all"], cwd=folder, check=True)
    return folder


def folder_of(index: str, *names: str) -> dict[str, str]:
    """The files of a folder of records: its index, the template and these records."""
    return {INDEX: index, TEMPLATE: "# The decision\n"} | {
        name: RECORDS[name] for name in names
    }


def test_the_names_are_those_right_in_the_folder_that_git_has(tmp_path: Path) -> None:
    root = repository(
        tmp_path / "repository",
        folder_of(index_of(row(A)), A) | {"images/0002-picture.md": ""},
    )
    (root / ".gitignore").write_text("*.bak\n", encoding="utf-8")
    (root / "docs/decisions/0002-b.md.bak").write_text("", encoding="utf-8")
    (root / "docs/decisions/0003-c.md").write_text("", encoding="utf-8")
    (root / "docs/decisions/0001-a.md").unlink()

    assert names_of(root) == [TEMPLATE, "0003-c.md", INDEX]


def test_the_command_passes_on_records_in_order(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repository(tmp_path / "repository", folder_of(index_of(row(A)), A))

    assert main(["decisions"], root=root) == 0

    assert capsys.readouterr().out == (
        "Each of the 1 record(s) of docs/decisions/ has a number of its own, and its "
        "index lists each once, in order.\n"
    )


def test_the_command_passes_without_records(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repository(tmp_path / "repository", {})

    assert main(["decisions"], root=root) == 0

    assert capsys.readouterr().out == (
        "docs/decisions/ holds no records of decisions, so nothing to check.\n"
    )


def test_the_command_checks_the_numbers_of_a_folder_without_index(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    files = folder_of("", A)
    del files[INDEX]
    root = repository(tmp_path / "repository", files)

    assert main(["decisions", "--fix"], root=root) == 0

    assert capsys.readouterr().out == (
        "Each of the 1 record(s) of docs/decisions/ has a number of its own; the "
        "folder has no index, README.md.\n"
    )


def test_the_command_names_a_clash_and_how_to_fix_it(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    clash = "0003-another.md"
    files = folder_of(index_of(row(A), row(B), row(C)), A, B, C)
    root = repository(tmp_path / "repository", files | {clash: "# Another\n"})

    assert main(["decisions"], root=root) == 1

    lines = capsys.readouterr().out.splitlines()
    assert lines == [
        "docs/decisions: 0003 is the number of 2 records: 0003-another.md, 0003-c.md",
        "Another pull request took the number first, or a file is no record: a new "
        "record takes the number of its pull request or that of an issue that the "
        "pull request fixes, which its description names as Fixes #…, in the name of "
        "its file and in each link to it. Only you can choose which record moves, so "
        "no command renames one.",
    ]


def test_the_command_names_the_fix_of_the_index(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    index = index_of(row(B), row(A))
    root = repository(tmp_path / "repository", folder_of(index, A, B))
    (root / ".github").mkdir()
    (root / ".github/blueprint.py").write_text("", encoding="utf-8")

    assert main(["decisions"], root=root) == 1

    assert capsys.readouterr().out == (
        "docs/decisions: the index lists 0001-a.md after 0002-b.md\n"
        "python3 .github/blueprint.py decisions --fix fixes what only the index gets "
        "wrong: the number of a row, the row of a renamed record, a row twice and the "
        "order of the rows.\n"
    )


def test_the_command_annotates_the_index_in_the_ci(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    index = index_of(row(A), row(A))
    root = repository(tmp_path / "repository", folder_of(index, A))

    assert main(["decisions"], root=root) == 1

    out = capsys.readouterr().out
    assert (
        "::error file=docs/decisions/README.md,title=Records of decisions::the index "
        "lists 0001-a.md 2 times\n"
    ) in out


def test_the_command_annotates_no_file_without_an_index_in_the_ci(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    files = folder_of("", A, C) | {"0003-another.md": "# Another\n"}
    del files[INDEX]
    root = repository(tmp_path / "repository", files)

    assert main(["decisions"], root=root) == 1

    out = capsys.readouterr().out
    assert (
        "::error title=Records of decisions::0003 is the number of 2 records: "
        "0003-another.md, 0003-c.md\n"
    ) in out


def test_the_command_fixes_the_index(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repository(
        tmp_path / "repository", folder_of(index_of(row(C), row(A), row(A)), A, B, C)
    )

    assert main(["decisions", "--fix"], root=root) == 0

    # The fix of a pull request adds no row: the release does.
    index = (root / "docs/decisions" / INDEX).read_text(encoding="utf-8")
    assert index == index_of(row(A), row(C))
    assert capsys.readouterr().out == (
        "docs/decisions/README.md: the rows of the index are fixed\n"
        "Each of the 3 record(s) of docs/decisions/ has a number of its own, and its "
        "index lists each once, in order.\n"
    )


def test_the_command_completes_the_index_as_the_release_does(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    new = "1033-d.md"
    files = folder_of(index_of(row(C), row(A)), A, B, C) | {
        B: "# B\n\n- Status: accepted, amended by [1033](1033-d.md)\n",
        new: "# D\n\n- Status: accepted\n",
    }
    root = repository(tmp_path / "repository", files)

    assert main(["decisions", "--complete"], root=root) == 0

    index = (root / "docs/decisions" / INDEX).read_text(encoding="utf-8")
    assert index == index_of(
        row(A),
        "| [0002](0002-b.md) | B | accepted, amended by [1033](1033-d.md) |\n",
        row(C),
        "| [1033](1033-d.md) | D | accepted |\n",
    )
    assert capsys.readouterr().out.startswith(
        "docs/decisions/README.md: the rows of the index are fixed\n"
    )
    # Written once, the index is complete, and the release writes nothing again.
    assert main(["decisions", "--complete"], root=root) == 0
    assert "fixed" not in capsys.readouterr().out
    assert (root / "docs/decisions" / INDEX).read_text(encoding="utf-8") == index


def test_the_command_takes_either_the_fix_or_the_complete_index(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repository(tmp_path / "repository", folder_of(index_of(row(A)), A))

    with pytest.raises(SystemExit):
        main(["decisions", "--fix", "--complete"], root=root)

    assert "not allowed with argument" in capsys.readouterr().err


def test_the_command_leaves_a_clean_index_alone_on_a_fix(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The index lacks only the line break at its end, which the text files fix.
    index = index_of(row(A)).removesuffix("\n")
    root = repository(tmp_path / "repository", folder_of(index, A))

    assert main(["decisions", "--fix"], root=root) == 0

    assert (root / "docs/decisions" / INDEX).read_text(encoding="utf-8") == index
    assert "fixed" not in capsys.readouterr().out


def test_the_command_names_no_fix_that_changes_nothing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The row of a file that is gone, with no record of its title: only you can fix it.
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    index = index_of(row(A), row("0002-gone.md"))
    root = repository(tmp_path / "repository", folder_of(index, A))

    assert main(["decisions", "--fix"], root=root) == 1

    assert (root / "docs/decisions" / INDEX).read_text(encoding="utf-8") == index
    out = capsys.readouterr().out
    assert "fixed" not in out
    assert "the index names 0002-gone.md, which is no record of the folder" in out


@pytest.mark.parametrize(
    ("action", "written"),
    [
        # The fix finds nothing that it may change; the complete index adds the row
        # of the second record of 0003.
        ("--fix", []),
        ("--complete", ["docs/decisions/README.md: the rows of the index are fixed"]),
    ],
)
def test_the_command_names_what_the_fix_leaves(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    written: list[str],
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    other = row(B).replace("A decision", "Another decision")
    clash = "0003-another.md"
    files = folder_of(index_of(row(A), row(B), other, row(C)), A, B, C)
    root = repository(tmp_path / "repository", files | {clash: "# Another\n"})

    assert main(["decisions", action], root=root) == 1

    lines = capsys.readouterr().out.splitlines()
    assert lines[: len(written) + 2] == [
        *written,
        "docs/decisions: 0003 is the number of 2 records: 0003-another.md, 0003-c.md",
        "docs/decisions: the index lists 0002-b.md 2 times",
    ]
    assert lines[-2].startswith("Another pull request took the number first")
    assert lines[-1] == (
        "The rows that these lines name need you: a row of a file that the folder "
        "doesn't have, or two rows of one record that say different things."
    )
    assert len(lines) == len(written) + 4


# A new record takes the number of its pull request, or of an issue that it fixes.


def git(root: Path, *arguments: str) -> str:
    """What git prints in the repository, as a commit of nobody in particular."""
    return subprocess.run(
        [
            "git",
            *("-c", "user.name=Test", "-c", "user.email=test@example.com"),
            *("-c", "commit.gpgsign=false", "-c", "core.autocrlf=false"),
            *arguments,
        ],
        cwd=root,
        capture_output=True,
        encoding="utf-8",
        check=True,
    ).stdout.strip()


def add(root: Path, files: dict[str, str]) -> None:
    """These files of docs/decisions/, in a commit."""
    for name, content in files.items():
        path = root / "docs/decisions" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
    git(root, "add", "--all")
    git(root, "commit", "--quiet", "--message", "Records")


def pull_request_checkout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    records: dict[str, str],
    *,
    number: int = 1040,
    description: str | None = "Fixes #1033",
    main: dict[str, str] | None = None,
) -> Path:
    """The checkout that the CI of pull request #number makes: the merge of its
    branch, which adds the records, into main, as GitHub makes it, with the
    variables of the runner and its event."""
    root = tmp_path / "repository"
    root.mkdir(parents=True)
    git(root, "init", "--quiet", "--initial-branch=main")
    add(root, main or folder_of(index_of(row(A), row(B)), A, B))
    git(root, "switch", "--quiet", "--create", "feature")
    add(root, records)
    git(root, "switch", "--quiet", "main")
    add(root, {"0003-c.md": RECORDS[C]})
    git(root, "merge", "--quiet", "--no-ff", "--no-edit", "feature")
    event = tmp_path / "event.json"
    pull = {"number": number, "body": description}
    event.write_text(json.dumps({"pull_request": pull}), encoding="utf-8")
    monkeypatch.setenv("GITHUB_REF", f"refs/pull/{number}/merge")
    monkeypatch.setenv("GITHUB_SHA", git(root, "rev-parse", "HEAD"))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return root


@pytest.mark.parametrize(
    "name",
    ["1040-the-number-of-the-pull-request.md", "1033-the-number-of-its-issue.md"],
)
def test_a_new_record_with_the_number_of_its_pull_request_or_issue_passes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    name: str,
) -> None:
    root = pull_request_checkout(tmp_path, monkeypatch, {name: "# New\n"})

    assert main(["decisions"], root=root) == 0

    assert capsys.readouterr().out == (
        "Each of the 4 record(s) of docs/decisions/ has a number of its own, and its "
        "index lists each once, in order.\n"
    )


def test_a_new_record_with_the_next_free_number_fails_with_the_number_to_take(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = pull_request_checkout(tmp_path, monkeypatch, {"0004-d.md": "# D\n"})
    monkeypatch.setenv("GITHUB_ACTIONS", "true")

    assert main(["decisions"], root=root) == 1

    lines = capsys.readouterr().out.splitlines()
    finding = (
        "0004-d.md of pull request #1040 takes the number 1040, or that of an issue "
        "that it fixes, 1033"
    )
    assert lines[0] == f"docs/decisions: {finding}"
    assert lines[1] == (
        "::error file=docs/decisions/README.md,title=Records of decisions::" + finding
    )
    assert lines[2].startswith(
        "Another pull request took the number first, or a file is no record: a new "
        "record takes the number of its pull request, 1040, or that of an issue"
    )
    assert len(lines) == 3


def test_the_records_of_main_and_a_renamed_one_keep_their_numbers(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # main brought 0003 since the branch left it, and the branch renames 0002.
    root = pull_request_checkout(
        tmp_path,
        monkeypatch,
        {"0002-b-in-other-words.md": "# B\n"},
        description=None,
        main=folder_of(index_of(row(A)), A, B),
    )
    git(root, "rm", "--quiet", "docs/decisions/0002-b.md")

    assert main(["decisions"], root=root) == 0

    assert "has a number of its own" in capsys.readouterr().out


def test_a_record_of_main_with_the_number_of_the_pull_request_leaves_it_the_next(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A young repository: its pull request #2 meets the template's 0002.
    taken = pull_request_checkout(
        tmp_path / "taken", monkeypatch, {"0002-mine.md": "# Mine\n"}, number=2
    )
    assert main(["decisions"], root=taken) == 1
    out = capsys.readouterr().out
    assert "0002 is the number of 2 records: 0002-b.md, 0002-mine.md" in out
    assert "the number of its pull request, 0004, or that of an issue" in out

    # Main holds 0001 to 0003: the next number above them is the pull request's.
    root = pull_request_checkout(
        tmp_path / "next", monkeypatch, {"0005-mine.md": "# Mine\n"}, number=2
    )
    assert main(["decisions"], root=root) == 1
    assert (
        "docs/decisions: 0005-mine.md of pull request #2 takes the number 0004, the "
        "next one above the records of main, since one of them has 0002, or that of "
        "an issue that it fixes, 1033\n"
    ) in capsys.readouterr().out

    passing = pull_request_checkout(
        tmp_path / "passing", monkeypatch, {"0004-mine.md": "# Mine\n"}, number=2
    )
    assert main(["decisions"], root=passing) == 0


def test_without_the_records_of_main_the_step_checks_only_that_numbers_are_unique(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A job that checks out another commit than the merge, such as the head.
    root = pull_request_checkout(tmp_path, monkeypatch, {"0004-d.md": "# D\n"})
    monkeypatch.setenv("GITHUB_SHA", "0" * 40)

    assert main(["decisions"], root=root) == 0

    assert capsys.readouterr().out.splitlines()[0] == (
        "The records of main aren't in this checkout of pull request #1040, which the "
        "merge of fetch-depth 2 brings, so the step checks only that each number is a "
        "record's own."
    )


def test_the_pull_request_comes_from_the_ref_the_commit_and_the_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = pull_request_checkout(tmp_path, monkeypatch, {"1040-d.md": "# D\n"})
    environment = {
        "GITHUB_REF": "refs/pull/1040/merge",
        "GITHUB_SHA": git(root, "rev-parse", "HEAD"),
        "GITHUB_EVENT_PATH": str(tmp_path / "event.json"),
    }

    assert pull_request_of(root, environment) == PullRequest(
        1040, frozenset({1, 2, 3}), frozenset({1033})
    )
    # Outside a pull request, such as on your machine or in a push to main.
    assert pull_request_of(root, {}) is None
    assert pull_request_of(root, {"GITHUB_REF": "refs/heads/main"}) is None
    # The merge without its parents, as a checkout of depth 1 has it.
    first = git(root, "rev-list", "--max-parents=0", "HEAD")
    git(root, "checkout", "--quiet", "--detach", first)
    alone = {**environment, "GITHUB_SHA": first}
    assert pull_request_of(root, alone) == PullRequest(1040, None, frozenset({1033}))


def test_the_numbers_of_a_commit_that_the_checkout_lacks_are_unknown(
    tmp_path: Path,
) -> None:
    root = repository(tmp_path / "repository", folder_of(index_of(row(A)), A))
    assert numbers_of(root, "HEAD") is None
    git(root, "commit", "--quiet", "--message", "Records")
    assert numbers_of(root, "HEAD") == frozenset({1})
    assert numbers_of(root, "HEAD^1") is None


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"pull_request": {"number": 7, "body": "Fixes #12"}}, "Fixes #12"),
        # Another pull request, a description without text, or no pull request.
        ({"pull_request": {"number": 8, "body": "Fixes #12"}}, ""),
        ({"pull_request": {"number": 7, "body": None}}, ""),
        ({"pull_request": "seven"}, ""),
        ({"push": {}}, ""),
        (["not", "an", "event"], ""),
    ],
)
def test_the_description_comes_from_the_event_of_the_pull_request(
    tmp_path: Path, payload: object, expected: str
) -> None:
    event = tmp_path / "event.json"
    event.write_text(json.dumps(payload), encoding="utf-8")
    assert description_of(str(event), 7) == expected


def test_an_event_that_cant_be_read_has_no_description(tmp_path: Path) -> None:
    broken = tmp_path / "event.json"
    broken.write_text("{not json", encoding="utf-8")
    assert description_of(str(broken), 7) == ""
    assert description_of(str(tmp_path / "missing.json"), 7) == ""
    assert description_of("", 7) == ""


def test_the_issues_that_a_description_closes_are_those_that_github_closes() -> None:
    description = (
        "Fixes #1033 and closes #12.\nResolved: #7, fix #8, Closed #9, resolve #10.\n"
        "Refs #11, see #13, fixes o/r#14, prefixes #15, Fixes#16, #17"
    )
    assert closed_issues(description) == {1033, 12, 7, 8, 9, 10}
    assert closed_issues("") == set()


def test_the_own_number_of_a_pull_request_is_its_own_unless_main_has_it() -> None:
    assert own_number({1, 2, 3}, 1040) == 1040
    assert own_number({1, 2, 3}, 2) == 4
    assert own_number(set(), 1) == 1


def test_a_new_record_needs_its_number_only_where_main_is_known() -> None:
    records = {1: [A], 4: ["0004-d.md"], 1033: ["1033-e.md"], 1040: ["1040-f.md"]}
    known = PullRequest(1040, frozenset({1}), frozenset({1033}))
    assert pull_request_findings(records, known) == [
        "0004-d.md of pull request #1040 takes the number 1040, or that of an issue "
        "that it fixes, 1033"
    ]
    # Without an issue, and with an issue whose number a record of main has.
    alone = PullRequest(1040, frozenset({1, 4}), frozenset({1}))
    assert pull_request_findings(records, alone) == [
        "1033-e.md of pull request #1040 takes the number 1040"
    ]
    several = PullRequest(1040, frozenset({1}), frozenset({1033, 4}))
    assert pull_request_findings(records, several) == []
    assert pull_request_findings(records, PullRequest(1040, None, frozenset())) == []


def test_two_pull_requests_that_each_add_a_record_merge_without_a_conflict(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    root = tmp_path / "repository"
    root.mkdir()
    git(root, "init", "--quiet", "--initial-branch=main")
    add(root, folder_of(index_of(row(A), row(B)), A, B))
    # Each pull request adds its record and leaves the index alone.
    for branch, record in (("first", "1040-first.md"), ("second", "1041-second.md")):
        git(root, "switch", "--quiet", "--create", branch, "main")
        add(root, {record: f"# {branch.title()}\n\n- Status: accepted\n"})
        assert main(["decisions"], root=root) == 0
    git(root, "switch", "--quiet", "main")
    git(root, "merge", "--quiet", "--no-ff", "--no-edit", "first")
    # The branch bot merges main into the second one: Git finds no conflict.
    git(root, "switch", "--quiet", "second")
    git(root, "merge", "--quiet", "--no-ff", "--no-edit", "main")
    assert main(["decisions"], root=root) == 0
    git(root, "switch", "--quiet", "main")
    git(root, "merge", "--quiet", "--no-ff", "--no-edit", "second")
    # The release writes the rows of both.
    assert main(["decisions", "--complete"], root=root) == 0
    index = (root / "docs/decisions" / INDEX).read_text(encoding="utf-8")
    assert index.endswith(
        "| [1040](1040-first.md) | First | accepted |\n"
        "| [1041](1041-second.md) | Second | accepted |\n"
    )
    assert "fixed" in capsys.readouterr().out


def test_the_command_fails_outside_a_repository(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # git looks for a repository up to the folder of the tests, and no further.
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    (tmp_path / "folder").mkdir()

    assert main(["decisions"], root=tmp_path / "folder") == 2

    err = capsys.readouterr().err
    assert err.startswith("blueprint.py: Command "), err
    assert err.endswith(" returned non-zero exit status 128.\n"), err
