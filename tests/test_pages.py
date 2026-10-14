"""Tests of the pages in one column: blueprint/pages.py, which finds the tables that set
a picture beside text and the cells with a width in the pages that GitHub shows, and
puts them in one column."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from blueprint.cli import main
from blueprint.pages import (
    CELL_WIDTH,
    PICTURE_BESIDE_TEXT,
    Layout,
    annotation,
    command,
    fixed,
    layouts,
    masked,
    pages,
    shown,
)

ROOT = Path(__file__).parents[1]
GIT = shutil.which("git")

# The features of a README as a table: the text in one cell, its picture in the other,
# as ha-autodarts had them.
FEATURES = """\
# Demo

## Features

<table>
  <tr>
    <td width="55%" valign="top">
      <h3>Play</h3>
      <ul>
        <li>X01 from 101 to 1001</li>
      </ul>
    </td>
    <td width="45%"><img src="docs/images/play.webp" alt="Animation: a game" width="100%"></td>
  </tr>
  <tr>
    <td width="55%" valign="top">
      <h3>Train</h3>
      <p>Eight training games.</p>
    </td>
    <td width="45%"><img src="docs/images/train.png" alt="The training card" width="100%"></td>
  </tr>
</table>

## Installation
"""
ONE_COLUMN = """\
# Demo

## Features

<h3>Play</h3>
<ul>
  <li>X01 from 101 to 1001</li>
</ul>

<img src="docs/images/play.webp" alt="Animation: a game" width="100%">

<h3>Train</h3>
<p>Eight training games.</p>

<img src="docs/images/train.png" alt="The training card" width="100%">

## Installation
"""


def lines(text: str) -> list[int]:
    return [layout.line for layout in layouts(text)]


def in_one_column(text: str) -> str:
    """The page after the fix, which leaves nothing to find."""
    column = fixed(text, layouts(text))
    assert layouts(column) == []
    return column


def repository(root: Path, files: dict[str, str]) -> Path:
    """A git repository with these files."""
    assert GIT
    subprocess.run([GIT, "init", "--quiet", str(root)], check=True)
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8", newline="\n")
    return root


def test_a_table_that_sets_a_picture_beside_text_fails() -> None:
    found = layouts(FEATURES)

    assert [(layout.line, layout.message) for layout in found] == [
        (5, PICTURE_BESIDE_TEXT)
    ]
    # One finding for the table, not one for each of its cells with a width.
    assert len(found[0].edits) == 1
    assert "<table>" in PICTURE_BESIDE_TEXT
    assert "picture below it" in PICTURE_BESIDE_TEXT


def test_the_fix_puts_the_text_of_each_row_before_its_picture() -> None:
    assert in_one_column(FEATURES) == ONE_COLUMN


def test_a_picture_on_the_left_comes_below_its_text_as_well() -> None:
    page = (
        "<table><tr>\n"
        '<td><img src="a.png" alt="A"></td>\n'
        "<td>The text of A.</td>\n"
        "</tr></table>\n"
    )

    assert in_one_column(page) == 'The text of A.\n\n<img src="a.png" alt="A">\n'


def test_a_table_of_data_passes() -> None:
    page = """\
<table>
  <thead>
    <tr><th>Entity</th><th>Wert</th></tr>
  </thead>
  <tbody>
    <tr><td><code>sensor.average</code></td><td>The 3-dart average</td></tr>
    <tr><td colspan="2">Every <a href="docs/entities.md">entity</a></td></tr>
  </tbody>
</table>

| Option | Default |
| --- | --- |
| ![Icon](docs/images/icon.png) | `true` |
"""

    assert layouts(page) == []


def test_a_picture_outside_of_a_table_passes() -> None:
    page = """\
Some text.

<img src="docs/images/card.png" alt="The card" width="100%">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/diagrams/a.dark.svg">
  <img src="docs/images/diagrams/a.svg" alt="A diagram">
</picture>

![A screenshot](docs/images/screenshot.png)
"""

    assert layouts(page) == []


def test_a_picture_deep_in_the_html_of_a_cell_counts() -> None:
    page = """\
<table>
  <tr>
    <td><div><p>The <b>scoreboard</b> on a tablet.</p></div></td>
    <td>
      <a href="docs/scoreboard.md">
        <picture>
          <source media="(prefers-color-scheme: dark)" srcset="docs/images/dark.png">
          <IMG SRC="docs/images/light.png" ALT="The scoreboard, 501 > 0">
        </picture>
      </a>
    </td>
  </tr>
</table>
"""

    assert lines(page) == [1]
    assert in_one_column(page) == (
        "<div><p>The <b>scoreboard</b> on a tablet.</p></div>\n"
        "\n"
        '<a href="docs/scoreboard.md">\n'
        "  <picture>\n"
        '    <source media="(prefers-color-scheme: dark)" srcset="docs/images/dark.png">\n'
        '    <IMG SRC="docs/images/light.png" ALT="The scoreboard, 501 > 0">\n'
        "  </picture>\n"
        "</a>\n"
    )


def test_a_table_inside_a_table_is_one_layout_that_a_person_takes_apart() -> None:
    page = """\
Text.

<table>
  <tr>
    <td>
      <table><tr><td>Inner</td><td><img src="a.png" alt="A"></td></tr></table>
    </td>
    <td width="40%">Beside</td>
  </tr>
</table>
"""
    found = layouts(page)

    assert [(layout.line, layout.edits) for layout in found] == [(3, ())]
    assert fixed(page, found) == page


def test_a_table_without_its_end_counts_to_the_end_of_the_page() -> None:
    page = "Text.\n\n<table><tr><td>A</td><td><img src='a.png'></td></tr>\n"
    found = layouts(page)

    assert [(layout.line, layout.edits) for layout in found] == [(3, ())]


@pytest.mark.parametrize(
    "page",
    [
        # Text before the table on its line, or after it.
        "Look: <table><tr><td>A</td><td><img src='a.png'></td></tr></table>\n",
        "<table><tr><td>A</td><td><img src='a.png'></td></tr></table> and more\n",
        # Content outside of its cells.
        "<table>\n<caption>Cards</caption>\n<tr><td>A</td><td><img src='a.png'></td></tr>\n</table>\n",
        "<table>\n<img src='a.png'>\n<tr><td>A</td></tr>\n</table>\n",
        # A comment between the cells, which the fix would lose.
        "<table><tr><td>A</td><!-- a note --><td><img src='a.png'></td></tr></table>\n",
    ],
)
def test_the_fix_leaves_a_table_alone_that_is_more_than_rows_and_cells(
    page: str,
) -> None:
    found = layouts(page)

    assert [(layout.line, layout.edits) for layout in found] == [(1, ())]


def test_the_fix_takes_cells_without_their_rows_or_their_ends() -> None:
    # HTML ends a cell at the next cell, and makes a row of cells without one.
    page = (
        "<table>\n"
        "  <td>First\n"
        "  <td><img src='a.png'>\n"
        "  <td>\n"
        "  </td>\n"
        "  <tr><th>Second</th><td>  </td><td><img src='b.png'></td></tr>\n"
        "  <tr></tr>\n"
        "</table>\n"
    )

    assert in_one_column(page) == (
        "First\n\n<img src='a.png'>\n\nSecond\n\n<img src='b.png'>\n"
    )


def test_each_caption_comes_before_its_picture() -> None:
    gallery = """\
<table>
  <tr>
    <td><img src="images/vertical.png" alt="Vertical" width="360"></td>
    <td><img src="images/board.png" alt="Board only" width="360"></td>
    <td></td>
  </tr>
  <tr>
    <td align="center"><code>layout: vertical</code></td>
    <td align="center"><code>layout: board</code></td>
    <td align="center">More to come</td>
  </tr>
</table>
"""
    above = """\
<table>
  <tr><td>Landscape</td><td>Portrait</td></tr>
  <tr><td><img src="l.png"></td><td><img src="p.png"></td></tr>
  <tr><td><img src="x.png"></td><td>Beside x</td></tr>
</table>
"""

    assert in_one_column(gallery) == (
        "<code>layout: vertical</code>\n\n"
        '<img src="images/vertical.png" alt="Vertical" width="360">\n\n'
        "<code>layout: board</code>\n\n"
        '<img src="images/board.png" alt="Board only" width="360">\n\n'
        "More to come\n"
    )
    assert in_one_column(above) == (
        'Landscape\n\n<img src="l.png">\n\nPortrait\n\n<img src="p.png">\n\n'
        'Beside x\n\n<img src="x.png">\n'
    )


def test_rows_of_different_lengths_go_row_by_row() -> None:
    page = (
        "<table>\n"
        "<tr><td><img src='a.png'></td><td><img src='b.png'></td></tr>\n"
        "<tr><td>Both</td></tr>\n"
        "</table>\n"
    )

    assert in_one_column(page) == "<img src='a.png'>\n\n<img src='b.png'>\n\nBoth\n"


def test_the_column_is_a_block_of_its_own_with_the_indentation_of_its_table() -> None:
    page = (
        "- An item\n"
        "  <table><tr><td>Text\n"
        "  </td><td><img src='a.png'></td></tr></table>\n"
        "  More of the item\n"
    )

    assert in_one_column(page) == (
        "- An item\n\n  Text\n\n  <img src='a.png'>\n\n  More of the item\n"
    )
    # At the end of a page without a line break as well.
    assert (
        in_one_column("<table><tr><td>A</td><td><img src='a.png'></td></tr></table>")
        == "A\n\n<img src='a.png'>"
    )


def test_a_cell_with_a_width_fails() -> None:
    page = """\
<table>
  <tr><th WIDTH=30 align="left">Name</th><td data-width="2">Value</td></tr>
  <tr><td style="color: red" width='70%'>Kim</td><td>1</td></tr>
</table>

<td width="50%">A cell without its table</td>
<td>Another one, without a width</td>
"""

    assert [(layout.line, layout.message) for layout in layouts(page)] == [
        (2, CELL_WIDTH),
        (6, CELL_WIDTH),
    ]
    assert in_one_column(page) == page.replace(" WIDTH=30", "").replace(
        " width='70%'", ""
    ).replace(' width="50%"', "")
    assert "<td width=…>" in CELL_WIDTH


def test_code_and_comments_of_html_dont_count() -> None:
    table = "<table><tr><td>A</td><td><img src='a.png'></td></tr></table>"
    page = f"""\
```html
{table}
```

~~~~
{table}
~~~
still in the block
~~~~

- An item:

  ```markdown
  <td width="50%">{table}</td>
  ```

Inline: `{table}` and ``<td width="1">` ``, and a lone ` backtick.

<!-- {table}
-->

{table}
"""

    assert lines(page) == [22]
    assert masked("``` a\n<td>\n```\n``x``\n") == "     \n    \n   \n     \n"


def test_a_run_of_backticks_that_its_line_repeats_starts_no_block() -> None:
    page = "```inline``` code\n\n<table><tr><td>A</td><td><img src='a.png'></td></tr></table>\n"

    assert lines(page) == [3]


def test_a_block_of_code_without_its_end_hides_the_rest_of_the_page() -> None:
    page = "```\n<table><tr><td>A</td><td><img src='a.png'></td></tr></table>\n"

    assert layouts(page) == []


def test_german_pages_count_as_well() -> None:
    page = """\
# Übersicht

Die Anzeigetafel für Darts, mit Ümlauten und ß.

<table>
  <tr>
    <td width="55%" valign="top">
      <h3>Spielen</h3>
      <p>X01 von 101 bis 1001, Cricket und Partyspiele für größere Runden.</p>
    </td>
    <td width="45%"><img src="images/de/turnier.webp" alt="Animation: der Turnierbaum mit fünf Spielern" width="100%"></td>
  </tr>
</table>

Weiter geht es.
"""

    assert lines(page) == [5]
    assert in_one_column(page) == (
        "# Übersicht\n\n"
        "Die Anzeigetafel für Darts, mit Ümlauten und ß.\n\n"
        "<h3>Spielen</h3>\n"
        "<p>X01 von 101 bis 1001, Cricket und Partyspiele für größere Runden.</p>\n\n"
        '<img src="images/de/turnier.webp" alt="Animation: der Turnierbaum mit fünf Spielern" width="100%">\n\n'
        "Weiter geht es.\n"
    )


@pytest.mark.parametrize(
    ("name", "checked"),
    [
        ("README.md", True),
        ("README.de.md", True),
        ("readme.md", True),
        ("custom_components/demo/README.md", True),
        ("CONTRIBUTING.md", True),
        ("CONTRIBUTING.de.md", True),
        ("docs/index.md", True),
        ("docs/decisions/0001-record-decisions.md", True),
        ("docs/README.de.md", True),
        ("template/docs/index.md", True),
        ("docs/notes.txt", False),
        ("README.txt", False),
        ("CHANGELOG.md", False),
        ("SECURITY.md", False),
        ("notes/plan.md", False),
        ("docs.md", False),
    ],
)
def test_the_pages_that_github_shows(name: str, checked: bool) -> None:
    assert shown(Path(name)) is checked


def test_an_annotation_names_the_file_and_the_line() -> None:
    layout = Layout(35, PICTURE_BESIDE_TEXT)

    assert annotation(Path("docs/README.de.md"), layout) == (
        "::error file=docs/README.de.md,line=35,title=Pages in one column::"
        + PICTURE_BESIDE_TEXT
    )
    # A name can't end the properties of the command.
    assert annotation(Path("a,b:c%.md"), layout).startswith(
        "::error file=a%2Cb%3Ac%25.md,line=35,"
    )


def test_the_command_is_that_of_the_repository(tmp_path: Path) -> None:
    assert command(tmp_path) == "python3 blueprint.py"
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github/blueprint.py").write_text("", encoding="utf-8")
    assert command(tmp_path) == "python3 .github/blueprint.py"


@pytest.mark.skipif(GIT is None, reason="the pages are the files that git knows")
def test_the_check_names_each_layout_with_its_fix(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    root = repository(
        tmp_path,
        {
            "README.md": FEATURES,
            "docs/cards.de.md": "<td width='1'>A</td>\n",
            "docs/guide.md": "Text.\n",
            ".github/blueprint.py": "",
        },
    )

    assert main(["pages"], root=root) == 1
    output = capsys.readouterr().out
    assert output.splitlines() == [
        f"README.md:5: {PICTURE_BESIDE_TEXT}",
        f"docs/cards.de.md:1: {CELL_WIDTH}",
        "2 layout(s) set columns side by side, which the GitHub app and phones "
        "squeeze. A page has one column, so that it reads well everywhere: the text, "
        "and below it each picture at full width; a table is for tabular data, as "
        "CONTRIBUTING.md describes.",
        "python3 .github/blueprint.py pages --fix puts 2 of them in one column: the "
        "cells of a layout table one below the other, the text before its picture, "
        "and cells without their width.",
    ]
    assert (root / "README.md").read_text(encoding="utf-8") == FEATURES


@pytest.mark.skipif(GIT is None, reason="the pages are the files that git knows")
def test_the_ci_shows_each_layout_at_its_line(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    nested = "<table><tr><td><table><tr><td><img src='a.png'></td></tr></table></td></tr></table>\n"
    root = repository(tmp_path, {"docs/index.md": nested})

    assert main(["pages"], root=root) == 1
    output = capsys.readouterr().out.splitlines()
    assert output[0] == f"docs/index.md:1: {PICTURE_BESIDE_TEXT}"
    assert output[1] == (
        "::error file=docs/index.md,line=1,title=Pages in one column::"
        + PICTURE_BESIDE_TEXT
    )
    # Nothing that the fix can do.
    assert "--fix" not in output[-1]


@pytest.mark.skipif(GIT is None, reason="the pages are the files that git knows")
def test_the_fix_puts_the_pages_in_one_column(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    root = repository(
        tmp_path,
        {
            "README.md": FEATURES,
            "docs/guide.md": "Text.\n",
            # GitHub shows no changelog as a page of the repository.
            "CHANGELOG.md": FEATURES,
        },
    )

    assert main(["pages", "--fix"], root=root) == 0
    assert capsys.readouterr().out.splitlines() == [
        "README.md: 1 layout(s) in one column now",
        "The 2 page(s) that GitHub shows have one column.",
    ]
    assert (root / "README.md").read_text(encoding="utf-8") == ONE_COLUMN
    assert (root / "CHANGELOG.md").read_text(encoding="utf-8") == FEATURES
    assert main(["pages"], root=root) == 0
    assert capsys.readouterr().out == (
        "The 2 page(s) that GitHub shows have one column.\n"
    )


@pytest.mark.skipif(GIT is None, reason="the pages are the files that git knows")
def test_the_fix_leaves_what_it_cannot_take_apart_to_a_person(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    nested = "<table><tr><td><table><tr><td><img src='a.png'></td></tr></table></td></tr></table>\n"
    root = repository(
        tmp_path, {"README.md": "Text.\n\n" + nested, "docs/index.md": FEATURES}
    )

    assert main(["pages", "--fix"], root=root) == 1
    assert capsys.readouterr().out.splitlines() == [
        "docs/index.md: 1 layout(s) in one column now",
        f"README.md:3: {PICTURE_BESIDE_TEXT}",
        "1 layout(s) set columns side by side, which the GitHub app and phones "
        "squeeze. A page has one column, so that it reads well everywhere: the text, "
        "and below it each picture at full width; a table is for tabular data, as "
        "CONTRIBUTING.md describes.",
        "These are left to you: a table inside another one, a table without its end, "
        "or one with content outside of its cells or on its lines.",
    ]
    assert (root / "docs/index.md").read_text(encoding="utf-8") == ONE_COLUMN


def test_a_page_that_cannot_be_read_fails_the_check(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["pages"], root=tmp_path / "missing") == 2
    assert capsys.readouterr().err.startswith("blueprint.py: ")
    if GIT:
        root = repository(tmp_path / "repository", {})
        (root / "README.md").write_bytes(b"\xff\xfe broken")
        assert main(["pages"], root=root) == 2


# The pages are the files that Git knows, and the copy of the mutation tests has no Git.
@pytest.mark.mutation_unsafe
@pytest.mark.skipif(GIT is None, reason="the pages are the files that git knows")
def test_the_pages_of_the_blueprint_have_one_column() -> None:
    found = {
        page.as_posix(): layouts((ROOT / page).read_text(encoding="utf-8"))
        for page in pages(ROOT)
    }

    assert "README.md" in found
    assert "template/CHANGELOG.md" not in found
    assert {page: layout for page, layout in found.items() if layout} == {}
