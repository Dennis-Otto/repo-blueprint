"""Tests of the coverage bot: a Cobertura report compared with that of main."""

from __future__ import annotations

from pathlib import Path

import pytest

from blueprint import cli
from blueprint.coverage_comment import (
    COVERAGE_MARKER,
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
        classes.append(f'<class filename="{name}.py"><lines>{hits}</lines></class>')
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


def test_the_command_line_names_a_broken_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = tmp_path / "broken.xml"
    broken.write_text("<coverage>", encoding="utf-8")

    assert cli.main(["coverage", str(broken)]) == 2
    assert "blueprint.py:" in capsys.readouterr().err
