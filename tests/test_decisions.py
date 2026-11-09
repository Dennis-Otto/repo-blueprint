"""The records of the decisions: blueprint/decisions.py and the command decisions, which
the step *Records of decisions* of scripts/check.sh runs in every repository.

Each record of a decision in docs/decisions/ has a number of its own, the next one
after the last, and the index docs/decisions/README.md lists each record once, in the
order of the numbers. Two pull requests that each take the next free number for a
record of their own merge without a conflict of Git, since their files have different
names: nothing else fails when two records share a number, when the index lists a
record twice, misses one or names a file that doesn't exist. The step does, so that a
merge of main into the second branch, which the bot that keeps the branches current
makes, shows the clash as a failing check of that branch, with the numbers and the
files, before it reaches main. The records that the template gives a new repository
are checked here, where no step reads them."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from shared import ROOT, git_environment

from blueprint.cli import main
from blueprint.decisions import (
    INDEX,
    TABLE,
    TEMPLATE,
    findings,
    fixed,
    names_of,
    next_free,
    numbered,
    row_of,
)

# The records of the blueprint, and those that the template gives a new repository.
FOLDERS = ["docs/decisions", "template/docs/decisions"]
HOW_TO_FIX = (
    "Another pull request took the number first, or a record lost its row: give your "
    "record the next free number, in the name of its file and in its row of "
    "{folder}/README.md, and fix each link to it."
)


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


def test_a_folder_without_an_index_checks_the_numbers_alone() -> None:
    clash = "0003-another.md"
    assert findings([TEMPLATE, A, B, C], None) == []
    assert findings([TEMPLATE, A, B, C, clash], None) == [
        "0003 is the number of 2 records: 0003-another.md, 0003-c.md"
    ]


def test_the_next_free_number_follows_the_last() -> None:
    assert next_free(numbered(FOLDER)[0]) == 4
    assert next_free(numbered([INDEX, TEMPLATE])[0]) == 1


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


def test_the_fix_drops_a_second_copy_of_a_row() -> None:
    index = index_of(row(A), row(B), row(B), row(C))
    assert fixed(index, FOLDER, text_of) == index_of(row(A), row(B), row(C))


def test_the_fix_keeps_two_rows_of_one_record_that_differ() -> None:
    other = row(B).replace("A decision", "Another decision")
    index = index_of(row(A), row(B), other, row(C))
    assert fixed(index, FOLDER, text_of) == index
    assert findings(FOLDER, index) == ["the index lists 0002-b.md 2 times"]


def test_the_fix_adds_the_row_of_a_record_from_its_title_and_status() -> None:
    names = [*FOLDER, "0004-d.md"]
    text = (
        "# The decision | in a few words\n\n- Status: replaced by [0005](0005-e.md)\n"
    )
    index = index_of(row(A), row(B), row(C))
    expected = index + (
        r"| [0004](0004-d.md) | The decision \| in a few words | replaced by "
        "[0005](0005-e.md) |\n"
    )
    assert fixed(index, names, {**RECORDS, "0004-d.md": text}.__getitem__) == expected
    assert findings(names, expected) == []


def test_a_new_row_of_a_record_without_heading_or_status_takes_its_name() -> None:
    assert row_of("0004-the-new-way.md", "Text.\n") == (
        "| [0004](0004-the-new-way.md) | The new way |  |\n"
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
    assert fixed(index, names, texts.__getitem__) == index_of(
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


def test_the_fix_adds_the_rows_below_the_head_of_an_empty_table() -> None:
    index = index_of() + "\nMore text.\n"
    assert fixed(index, FOLDER, text_of) == (
        index_of(
            "| [0001](0001-a.md) | A | accepted |\n",
            "| [0002](0002-b.md) | B | accepted |\n",
            "| [0003](0003-c.md) | C | accepted |\n",
        )
        + "\nMore text.\n"
    )


def test_the_fix_adds_a_table_to_an_index_without_one() -> None:
    names = [INDEX, TEMPLATE, A]
    assert fixed("# Decisions", names, text_of) == (
        "# Decisions\n\n" + TABLE + "| [0001](0001-a.md) | A | accepted |\n"
    )
    assert fixed("", names, text_of) == TABLE + "| [0001](0001-a.md) | A | accepted |\n"
    assert fixed("# Decisions\n", [INDEX, TEMPLATE], text_of) == "# Decisions\n"


def test_the_fix_ends_each_line_of_a_last_row_that_moves() -> None:
    index = index_of(row(B), row(A)).removesuffix("\n")
    assert fixed(index, [INDEX, TEMPLATE, A, B], text_of) == index_of(row(A), row(B))


def test_the_fix_ends_the_head_of_a_table_that_ends_the_index() -> None:
    index = index_of().removesuffix("\n")
    assert fixed(index, [INDEX, TEMPLATE, A], text_of) == index_of(
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


def test_the_command_names_a_clash_and_the_next_free_number(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    clash = "0003-another.md"
    files = folder_of(index_of(row(A), row(B), row(C), row(clash)), A, B, C)
    root = repository(tmp_path / "repository", files | {clash: "# Another\n"})

    assert main(["decisions"], root=root) == 1

    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == (
        "docs/decisions: 0003 is the number of 2 records: 0003-another.md, 0003-c.md"
    )
    assert lines[1].startswith("Another pull request took the number first, or a file")
    assert "the next free number, 0004, in the name of its file" in lines[1]
    assert "of docs/decisions/README.md and in each link to it" in lines[1]
    assert lines[1].endswith("so no command renames one.")
    assert len(lines) == 2


def test_the_command_names_the_fix_of_the_index(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    root = repository(tmp_path / "repository", folder_of(index_of(row(A)), A, B))
    (root / ".github").mkdir()
    (root / ".github/blueprint.py").write_text("", encoding="utf-8")

    assert main(["decisions"], root=root) == 1

    assert capsys.readouterr().out == (
        "docs/decisions: the index misses 0002-b.md\n"
        "python3 .github/blueprint.py decisions --fix fixes what only the index gets "
        "wrong: the number of a row, the row of a renamed record, a row twice, a "
        "missing row and the order of the rows.\n"
    )


def test_the_command_annotates_the_index_in_the_ci(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    root = repository(tmp_path / "repository", folder_of(index_of(row(A)), A, B))

    assert main(["decisions"], root=root) == 1

    out = capsys.readouterr().out
    assert (
        "::error file=docs/decisions/README.md,title=Records of decisions::the index "
        "misses 0002-b.md\n"
    ) in out


def test_the_command_annotates_no_file_without_an_index_in_the_ci(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    files = folder_of("", A, C)
    del files[INDEX]
    root = repository(tmp_path / "repository", files)

    assert main(["decisions"], root=root) == 1

    out = capsys.readouterr().out
    assert (
        "::error title=Records of decisions::no record has the number 0002, which "
        "the numbers skip\n"
    ) in out


def test_the_command_fixes_the_index(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repository(
        tmp_path / "repository", folder_of(index_of(row(C), row(A), row(A)), A, B, C)
    )

    assert main(["decisions", "--fix"], root=root) == 0

    index = (root / "docs/decisions" / INDEX).read_text(encoding="utf-8")
    assert index == index_of(row(A), "| [0002](0002-b.md) | B | accepted |\n", row(C))
    assert capsys.readouterr().out == (
        "docs/decisions/README.md: the rows of the index are fixed\n"
        "Each of the 3 record(s) of docs/decisions/ has a number of its own, and its "
        "index lists each once, in order.\n"
    )


def test_the_command_leaves_a_clean_index_alone_on_a_fix(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The index lacks only the line break at its end, which the text files fix.
    index = index_of(row(A)).removesuffix("\n")
    root = repository(tmp_path / "repository", folder_of(index, A))

    assert main(["decisions", "--fix"], root=root) == 0

    assert (root / "docs/decisions" / INDEX).read_text(encoding="utf-8") == index
    assert "fixed" not in capsys.readouterr().out


def test_the_command_names_what_the_fix_leaves(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    other = row(B).replace("A decision", "Another decision")
    clash = "0003-another.md"
    files = folder_of(index_of(row(A), row(B), other, row(C)), A, B, C)
    root = repository(tmp_path / "repository", files | {clash: "# Another\n"})

    assert main(["decisions", "--fix"], root=root) == 1

    lines = capsys.readouterr().out.splitlines()
    assert lines[:3] == [
        "docs/decisions/README.md: the rows of the index are fixed",
        "docs/decisions: 0003 is the number of 2 records: 0003-another.md, 0003-c.md",
        "docs/decisions: the index lists 0002-b.md 2 times",
    ]
    assert "the next free number, 0004" in lines[3]
    assert lines[4] == (
        "The rows that these lines name need you: a row of a file that the folder "
        "doesn't have, or two rows of one record that say different things."
    )
    assert len(lines) == 5


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
