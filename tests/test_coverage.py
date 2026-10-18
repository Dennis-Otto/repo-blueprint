"""Tests of the coverage bot: a Cobertura or an LCOV report compared with that of main."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from xml.sax.saxutils import quoteattr

import pytest
from hypothesis import given
from hypothesis import strategies as st

from blueprint import cli
from blueprint.coverage_comment import (
    COVERAGE_MARKER,
    MOST_FILES,
    Coverage,
    coverage_comment,
    percent,
)


def report(**files: tuple[int, int]) -> str:
    """A Cobertura report with the given covered and total lines per file."""
    classes = []
    for name, (covered, lines) in files.items():
        hits = "".join(
            f'<line number="{number}" hits="{1 if number <= covered else 0}"/>'
            for number in range(1, lines + 1)
        )
        classes.append(
            f"<class filename={quoteattr(name + '.py')}><lines>{hits}</lines></class>"
        )
    return (
        '<?xml version="1.0" ?><coverage><packages><package><classes>'
        + "".join(classes)
        + "</classes></package></packages></coverage>"
    )


def test_a_report_counts_the_lines_of_each_file() -> None:
    coverage = Coverage.parse(report(a=(3, 4), b=(0, 0)))

    assert coverage.files == {"a.py": (3, 4), "b.py": (0, 0)}
    assert coverage.total == (3, 4)
    assert percent(0, 0) == 100.0


def test_classes_of_one_file_add_up() -> None:
    text = (
        '<coverage><packages><package><classes><class filename="a.php"><lines>'
        '<line number="1" hits="1"/><line number="2" hits="0"/></lines></class>'
        '<class filename="a.php"><lines><line number="3" hits="2"/></lines></class>'
        "</classes></package></packages></coverage>"
    )

    assert Coverage.parse(text).files == {"a.php": (2, 3)}


def with_sources(text: str, *sources: Path | str) -> str:
    listed = "".join(f"<source>{source}</source>" for source in sources)
    return text.replace("<coverage>", f"<coverage><sources>{listed}</sources>", 1)


def test_one_source_under_the_root_names_every_file_from_the_root(
    tmp_path: Path,
) -> None:
    # Such as PHPUnit's lib/, or the one folder that coverage.py measures.
    text = with_sources(report(**{"AppInfo/Application": (1, 2)}), tmp_path / "lib")

    assert Coverage.parse(text, tmp_path).files == {
        "lib/AppInfo/Application.py": (1, 2)
    }


@pytest.mark.parametrize("sources", [["."], ["lib", "src"], ["/elsewhere/lib"]])
def test_the_root_several_sources_or_another_place_keep_the_names(
    tmp_path: Path, sources: list[str]
) -> None:
    # An absolute folder, such as /elsewhere/lib, lies outside tmp_path.
    text = with_sources(report(a=(1, 1)), *(tmp_path / source for source in sources))

    assert Coverage.parse(text, tmp_path).files == {"a.py": (1, 1)}
    assert Coverage.parse(text).files == {"a.py": (1, 1)}


def lcov(**files: tuple[int, int]) -> str:
    """An LCOV report, as the test runner of Node writes it, with the given covered
    and total lines per file."""
    records = []
    for name, (covered, lines) in files.items():
        hits = "".join(
            f"DA:{number},{1 if number <= covered else 0}\n"
            for number in range(1, lines + 1)
        )
        records.append(
            f"TN:\nSF:{name}.ts\nFN:1,f\nFNDA:1,f\n{hits}LH:{covered}\nLF:{lines}\n"
            "end_of_record\n"
        )
    return "".join(records)


def test_an_lcov_report_counts_the_lines_of_each_file() -> None:
    coverage = Coverage.parse_lcov(lcov(**{"src/a": (3, 4), "src/b": (0, 0)}))

    assert coverage.files == {"src/a.ts": (3, 4), "src/b.ts": (0, 0)}
    assert coverage.total == (3, 4)


def test_the_records_of_one_file_in_lcov_add_up() -> None:
    # Hits as a number of any kind, a checksum after them, as some tools write, and
    # a line without its hits.
    text = (
        "SF:a.ts\nDA:1,1\nDA:2,0\nend_of_record\n"
        "SF:a.ts\nDA:3,2.5,abc\nDA:4\nDA:5,x\nend_of_record\n"
    )

    assert Coverage.parse_lcov(text).files == {"a.ts": (2, 5)}


def test_lines_of_lcov_outside_a_record_count_for_an_unnamed_file() -> None:
    text = "DA:1,1\nSF:a.ts\nDA:1,0\nend_of_record\nDA:2,0\n  \nno lcov\n"

    assert Coverage.parse_lcov(text).files == {"": (1, 2), "a.ts": (0, 1)}


def test_an_absolute_name_in_lcov_under_the_root_starts_at_the_root(
    tmp_path: Path,
) -> None:
    # c8 and Istanbul name each file by its absolute path; the test runner of Node by
    # its path from where the tests ran, which stays as it is, as one elsewhere does.
    elsewhere = (tmp_path.parent / "elsewhere/c.ts").as_posix()
    text = (
        f"SF:{(tmp_path / 'src/a.ts').as_posix()}\nDA:1,1\nend_of_record\n"
        "SF:src/b.ts\nDA:1,0\nend_of_record\n"
        f"SF:{elsewhere}\nDA:1,1\nend_of_record\n"
    )

    assert Coverage.parse_lcov(text, tmp_path).files == {
        "src/a.ts": (1, 1),
        "src/b.ts": (0, 1),
        elsewhere: (1, 1),
    }
    assert set(Coverage.parse_lcov(text).files) == {
        (tmp_path / "src/a.ts").as_posix(),
        "src/b.ts",
        elsewhere,
    }


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("coverage.xml", report(a=(1, 2))),
        ("lcov.info", lcov(a=(1, 2))),
        ("coverage.lcov.info", lcov(a=(1, 2))),
        ("report", report(a=(1, 2))),
    ],
)
def test_the_name_of_the_file_picks_the_format_of_its_report(
    tmp_path: Path, name: str, content: str
) -> None:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")

    assert Coverage.read(path).total == (1, 2)


def test_the_comment_shows_the_change_of_every_file() -> None:
    head = Coverage.parse(report(a=(4, 4), b=(1, 2), new=(1, 1)))
    base = Coverage.parse(report(a=(4, 4), b=(2, 2), gone=(1, 1)))

    comment = coverage_comment(head, base)

    assert comment.startswith(COVERAGE_MARKER)
    assert "| This pull request | 7 | 85.71 % |" in comment
    assert "| main | 7 | 100.00 % (-14.29) |" in comment
    assert "| `b.py` | 100.00 % | 50.00 % |" in comment
    assert "| `new.py` | new | 100.00 % |" in comment
    assert "| `gone.py` | 100.00 % | removed |" in comment
    assert "`a.py`" not in comment


def test_without_a_change_the_comment_says_so() -> None:
    coverage = Coverage.parse(report(a=(2, 2)))

    comment = coverage_comment(coverage, coverage)

    assert "(+0.00)" in comment
    assert "No file changes its coverage." in comment


def test_without_a_report_of_main_the_comment_shows_the_pull_request() -> None:
    comment = coverage_comment(Coverage.parse(report(a=(1, 2))), None)

    assert "| This pull request | 2 | 50.00 % |" in comment
    assert "main has no coverage report yet" in comment


# The names of the files and the hits of each line come from the coverage.xml of the
# pull request, which a pull request from a fork writes as it likes.


def cells(row: str) -> list[str]:
    """The cells of a row of a table, as GitHub splits it: at every pipe that no
    backslash escapes, also inside code."""
    assert row.startswith("| ")
    assert row.endswith(" |")
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", row)[1:-1]]


def is_code(text: str) -> bool:
    """Whether the text is one span of code, which shows the rest as it is: it ends
    only at a run of backticks as long as the one it starts with."""
    found = re.fullmatch(r"(`+)( ?)(.*)\2\1", text, re.S)
    if not found:
        return False
    return len(found[1]) not in {len(run) for run in re.findall(r"`+", found[3])}


def one_file(name: str, covered: int) -> Coverage:
    """The report of one file of two lines, named as in the attribute of its class."""
    return Coverage.parse(
        "<coverage><packages><package><classes>"
        f"<class filename={quoteattr(name)}><lines>"
        f'<line number="1" hits="1"/><line number="2" hits="{covered - 1}"/>'
        "</lines></class></classes></package></packages></coverage>"
    )


def rows_of_files(comment: str) -> list[str]:
    table = comment[comment.index("| File | main | This pull request |") :]
    return [line for line in table.splitlines()[2:] if line.startswith("| ")]


@pytest.mark.parametrize(
    ("name", "shown"),
    [
        # A heading, a link and a mention, after the code and the cell ended.
        (
            "a` | [x](https://e.vil) @team\n# Approved",
            r"``a` \| [x](https://e.vil) @team # Approved``",
        ),
        ("``b``", "``` ``b`` ```"),
        ("c\\|d", r"`c\\|d`"),
        ("<img src=x onerror=alert(1)>", "`<img src=x onerror=alert(1)>`"),
        ("e\r\n| --- |\N{LINE SEPARATOR}f", r"`e \| --- \| f`"),
        ("", "(unnamed file)"),
        (" \t\n", "(unnamed file)"),
        ("x" * 300, f"`{'x' * 199}\N{HORIZONTAL ELLIPSIS}`"),
    ],
)
def test_a_crafted_file_name_stays_code_in_its_cell(name: str, shown: str) -> None:
    (row,) = rows_of_files(coverage_comment(one_file(name, 1), one_file(name, 2)))

    assert cells(row) == [shown, "100.00 %", "50.00 %"]


@given(st.text())
def test_no_file_name_ends_its_code_its_cell_or_its_line(name: str) -> None:
    comment = coverage_comment(Coverage({name: (1, 2)}), Coverage({}))

    (row,) = rows_of_files(comment)
    shown, before, now = cells(row)
    assert is_code(shown) or shown == "(unnamed file)"
    assert (before, now) == ("new", "50.00 %")
    assert len(comment.splitlines()) == 11


def test_the_table_shows_the_first_files_and_counts_the_others() -> None:
    names = [f"f{number:03}" for number in range(MOST_FILES + 23)]
    head = Coverage.parse(report(**dict.fromkeys(names, (1, 2))))
    base = Coverage.parse(report(**dict.fromkeys(names, (2, 2))))

    comment = coverage_comment(head, base)

    rows = rows_of_files(comment)
    assert len(rows) == MOST_FILES
    assert rows[-1].startswith(f"| `f{MOST_FILES - 1:03}.py` |")
    assert comment.endswith(
        " |\n\n23 more files change their coverage; the artifact coverage of the"
        " checks has the whole report.\n"
    )


@pytest.mark.parametrize(
    "name",
    [
        # The longest code: a run of backticks, inside a run longer by one, of a
        # name cut to its longest length or just below it.
        lambda number: "`" * 300 + str(number),
        lambda number: "`" * 199 + chr(0x4E00 + number),
        lambda number: f"{number:03}" + "`" * 300,
    ],
)
def test_the_longest_comment_fits_into_one_comment_of_github(
    name: Callable[[int], str],
) -> None:
    names = [name(number) for number in range(2 * MOST_FILES)]
    head = Coverage(dict.fromkeys(names, (1, 2)))

    comment = coverage_comment(head, Coverage({}))

    assert len(rows_of_files(comment)) == MOST_FILES
    assert len(comment) < 65536


@pytest.mark.parametrize(
    ("hits", "covered"),
    [
        ("1", 1),
        ("1.5", 1),
        ("1e3", 1),
        ("0.0", 0),
        ("-1", 0),
        ("x", 0),
        ("", 0),
        ("nan", 0),
    ],
)
def test_hits_that_are_no_count_count_as_a_number_or_as_0(
    hits: str, covered: int
) -> None:
    text = (
        '<coverage><packages><package><classes><class filename="a.py"><lines>'
        f'<line number="1" hits="{hits}"/><line number="2"/></lines></class>'
        "</classes></package></packages></coverage>"
    )

    assert Coverage.parse(text).files == {"a.py": (covered, 2)}


@given(st.text(st.characters(codec="utf-8", exclude_categories=("Cc", "Cs", "Cn"))))
def test_no_hits_stop_the_bot(hits: str) -> None:
    text = (
        '<coverage><packages><package><classes><class filename="a.py"><lines>'
        f"<line number='1' hits={quoteattr(hits)}/></lines></class>"
        "</classes></package></packages></coverage>"
    )

    assert Coverage.parse(text).files["a.py"] in {(0, 1), (1, 1)}


def test_the_command_line_writes_the_comment(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    head = tmp_path / "head.xml"
    base = tmp_path / "base.xml"
    head.write_text(report(a=(1, 2)), encoding="utf-8")
    base.write_text(report(a=(2, 2)), encoding="utf-8")

    assert cli.main(["coverage", str(head), str(base)]) == 0
    assert "| `a.py` | 100.00 % | 50.00 % |" in capsys.readouterr().out

    assert cli.main(["coverage", str(head)]) == 0
    assert "main has no coverage report yet" in capsys.readouterr().out


def test_the_command_line_names_the_paths_from_where_it_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    head = tmp_path / "head.xml"
    head.write_text(with_sources(report(a=(1, 2)), tmp_path / "lib"), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert cli.main(["coverage", str(head)]) == 0
    assert "| This pull request | 2 | 50.00 % |" in capsys.readouterr().out
    assert Coverage.parse(head.read_text(encoding="utf-8"), Path.cwd()).files == {
        "lib/a.py": (1, 2)
    }


def test_the_command_line_compares_the_lcov_reports_of_node(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # As the PR coach downloads them: each as lcov.info, in a folder of its own.
    for folder, covered in (("head", 1), ("base", 2)):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "lcov.info").write_text(
            lcov(**{f"{tmp_path.as_posix()}/src/a": (covered, 2)}), encoding="utf-8"
        )
    monkeypatch.chdir(tmp_path)

    assert cli.main(["coverage", "head/lcov.info", "base/lcov.info"]) == 0
    assert "| `src/a.ts` | 100.00 % | 50.00 % |" in capsys.readouterr().out


# A report that is no XML, one that is no text of UTF-8, and an LCOV report that is
# no text of UTF-8.
@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("broken.xml", b"<coverage>"),
        ("broken.xml", b"<coverage>\xff</coverage>"),
        ("lcov.info", b"SF:\xff\n"),
    ],
)
def test_the_command_line_names_a_broken_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str, content: bytes
) -> None:
    broken = tmp_path / name
    broken.write_bytes(content)

    assert cli.main(["coverage", str(broken)]) == 2
    assert "blueprint.py:" in capsys.readouterr().err
