"""Tests of the diagrams as pictures: blueprint/diagrams.py, which takes the ```mermaid
blocks of the Markdown into sources, and scripts/diagrams.sh, which checks and draws
them, in bash with a stub of Docker."""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest
from shell import BASH, in_bash

from blueprint.cli import main
from blueprint.diagrams import (
    LONGEST,
    Changes,
    Names,
    alt_text,
    changes,
    commit_request,
    committable,
    dedent,
    diagrams_of,
    extract,
    heading_before,
    keep,
    labels,
    markdown_pages,
    picture,
    report,
    slug,
    without_html,
)

ROOT = Path(__file__).parents[1]
GIT = shutil.which("git")

DIAGRAM = """\
flowchart TB
    accTitle: How a change ships
    accDescr: A pull request merges, and the release bot releases it.

    pr["Pull request"] --> main["main"]
"""
GERMAN = """\
flowchart TB
    accTitle: Wie eine Änderung ausgeliefert wird
    accDescr: Ein Pull Request wird gemergt.

    pr["Pull Request"] --> main["main"]
"""


def block(source: str, indent: str = "", fence: str = "```") -> str:
    lines = [f"{fence}mermaid", *source.splitlines(), fence]
    return "".join(f"{indent}{line}\n" if line else "\n" for line in lines)


def repository(root: Path, files: dict[str, str]) -> Path:
    """A git repository with these files."""
    assert GIT
    subprocess.run([GIT, "init", "--quiet", str(root)], check=True)
    # The files as they are, also where Git for Windows changes their line breaks.
    subprocess.run(
        [GIT, "-C", str(root), "config", "core.autocrlf", "false"], check=True
    )
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8", newline="\n")
    return root


# The tool


@pytest.mark.parametrize(
    ("title", "name"),
    [
        ("How a repository looks after itself", "how-a-repository-looks-after-itself"),
        (
            "Wie sich ein Repository selbst pflegt",
            "wie-sich-ein-repository-selbst-pflegt",
        ),
        ("Änderung, Öl, Übung und Fuß", "aenderung-oel-uebung-und-fuss"),
        ("  The `settings` as code (v1.2)!  ", "the-settings-as-code-v1-2"),
        ("Café — naïve", "cafe-naive"),
        ("", ""),
        ("…", ""),
    ],
)
def test_a_title_names_its_diagram(title: str, name: str) -> None:
    assert slug(title) == name


def test_a_long_title_is_cut_where_a_word_ends() -> None:
    title = "How the blueprint bot brings a new release to its open pull request " * 2
    name = slug(title)

    assert len(name) <= LONGEST
    assert name.startswith(
        "how-the-blueprint-bot-brings-a-new-release-to-its-open-pull-"
    )
    assert title.casefold().replace(" ", "-").startswith(name + "-")
    # A single word longer than that is cut where the name ends.
    assert slug("x" * 100) == "x" * LONGEST


@pytest.mark.parametrize(
    ("source", "alt"),
    [
        (
            DIAGRAM,
            "How a change ships: A pull request merges, and the release bot releases it.",
        ),
        (
            "flowchart TB\n  accTitle: Steps\n  accDescr {\n    One step,\n    then the next.\n  }\n",
            "Steps: One step, then the next.",
        ),
        ("flowchart TB\n  accTitle: Only a title\n", "Only a title"),
        ("flowchart TB\n  accDescr: Only a description\n", "Only a description"),
        ("flowchart TB\n  accTitle:\n  accDescr:\n  a --> b\n", "A diagram"),
        ("flowchart TB\n  accDescr {\n  }\n", "A diagram"),
        ("flowchart TB\n  a --> b\n", "A diagram"),
    ],
)
def test_the_alt_text_is_the_title_and_the_description(source: str, alt: str) -> None:
    assert alt_text(source) == alt


LABELLED = """\
flowchart TB
    subgraph cloud["Nextcloud"]
        a["Browser<br>app"] --> b(Paperless **ngx**)
        c{Decide} -->|yes| d[[`sync`]]
        e>Flag] --> f[(Database)] --> g["Browser<br/>app"]
    end
    classDef note fill:#fff
"""


@pytest.mark.parametrize(
    ("source", "heading", "alt"),
    [
        # Without accTitle and accDescr, the heading above and the labels of the nodes.
        (
            LABELLED,
            "How it works",
            "How it works: Nextcloud, Browser app, Paperless ngx, Decide, sync, Flag,"
            " Database",
        ),
        (
            LABELLED,
            "",
            "Nextcloud, Browser app, Paperless ngx, Decide, sync, Flag, Database",
        ),
        ("flowchart TB\n  a --> b\n", "Steps", "Steps"),
        # Only a flowchart has labels to name, after its front matter and comments.
        ("sequenceDiagram\n  A->>B: hi\n  B-->>A: ok\n", "", "A diagram"),
        ("xychart-beta\n  x-axis [a, b]\n  bar [1, 2]\n", "Costs", "Costs"),
        ("---\ntitle: T\n---\n%% A comment\ngraph LR\n  a[One]\n", "", "One"),
        ("", "", "A diagram"),
        # A node at the end of an arrow has its label too.
        ("flowchart TB\n  a-->b(Two)\n  c==>d>Three]\n", "", "Two, Three"),
        # The title and the description come first.
        (DIAGRAM, "How it works", alt_text(DIAGRAM)),
    ],
)
def test_a_diagram_without_a_title_is_told_by_its_heading_and_labels(
    source: str, heading: str, alt: str
) -> None:
    assert alt_text(source, heading) == alt


def test_a_diagram_names_at_most_ten_labels() -> None:
    source = "flowchart TB\n" + "".join(f"    n{i}[Step {i}]\n" for i in range(12))

    assert labels(source) == [f"Step {i}" for i in range(10)]


@pytest.mark.parametrize(
    ("text", "heading"),
    [
        ("# Demo\n\nText.\n", "Demo"),
        ("# Demo\n\n## How it works ##\n", "How it works"),
        (
            "## The [guide](docs/guide.md) of `blueprint.py` {#guide}\n",
            "The guide of blueprint.py",
        ),
        # Neither a comment in a block of code nor one in the front matter is a heading.
        ("---\n# a comment\n---\n# Page\n\n```bash\n# a comment\n```\n", "Page"),
        ("# Page\n\n~~~~\n# code\n~~~\n# still code\n~~~~\n", "Page"),
        ("    # code, by its indentation\nText.\n", ""),
        ("Text without a heading.\n", ""),
    ],
)
def test_the_heading_above_a_diagram(text: str, heading: str) -> None:
    assert heading_before(text, len(text)) == heading


@pytest.mark.parametrize(
    ("line", "cleaned"),
    [
        # Text of a picture, where only <br> breaks a line.
        ('    a["Branch from <code>main</code>"]', '    a["Branch from main"]'),
        (
            '    a["one<br/>two<BR />three<br>four"]',
            '    a["one<br>two<br>three<br>four"]',
        ),
        ('    a -- "<code>BETA</code>" --> b', '    a -- "BETA" --> b'),
        (
            "    a[\"<span class='x'>small</span> <sub>print</sub>\"]",
            '    a["small print"]',
        ),
        # Bold and italic need a label of Markdown.
        (
            '    a["<b>Files</b><br>an <i>entry</i> and <em>a</em> <strong>b</strong>"]',
            '    a["`**Files**<br>an *entry* and *a* **b**`"]',
        ),
        (
            '    a["`Already **Markdown** with <b>bold</b>`"]',
            '    a["`Already **Markdown** with **bold**`"]',
        ),
        # A label in brackets, without quotes.
        (
            "    a[Branch from <code>main</code><br/>now] --> b",
            "    a[Branch from main<br>now] --> b",
        ),
        # What only looks like HTML stays.
        (
            '    a["List<String>"] --> b{"a < b"}',
            '    a["List<String>"] --> b{"a < b"}',
        ),
        (
            "    class Shape {\n    <<interface>>",
            "    class Shape {\n    <<interface>>",
        ),
        ('    a["<b"]', '    a["<b"]'),
    ],
)
def test_labels_keep_only_what_a_picture_shows(line: str, cleaned: str) -> None:
    assert without_html(line) == cleaned


def test_the_front_matter_stays_as_it_is() -> None:
    source = '---\ntitle: "<b>As it is</b>"\n---\nflowchart TB\n    a["<b>bold</b>"]\n'

    assert without_html(source) == (
        '---\ntitle: "<b>As it is</b>"\n---\nflowchart TB\n    a["`**bold**`"]\n'
    )


def test_the_blocks_and_the_pictures_of_a_page_in_their_order() -> None:
    text = (
        "# Page\n\n"
        + block(DIAGRAM)
        + "\n"
        + picture("shown", Path("README.md"), "Shown")
        + "\n1. A step\n\n"
        + block(DIAGRAM, indent="   ", fence="~~~~")
        + "\n```mermaid\nnever closed\n"
    )

    found = diagrams_of(text)

    assert [(diagram.name, diagram.indent) for diagram in found] == [
        ("", ""),
        ("shown", ""),
        ("", "   "),
    ]
    assert found[0].source == DIAGRAM
    assert found[2].source == DIAGRAM
    assert text[found[0].start : found[0].end] == block(DIAGRAM)
    assert text[found[2].start : found[2].end] == block(DIAGRAM, "   ", "~~~~")


def test_a_block_may_name_more_than_mermaid() -> None:
    found = diagrams_of("```mermaid title\na --> b\n````\n")

    assert [diagram.source for diagram in found] == ["a --> b\n"]
    assert not diagrams_of("```mermaidish\na --> b\n```\n")


def test_the_lines_of_a_block_lose_the_indentation_of_its_fence() -> None:
    assert dedent("   a\n\n      b  \n  c\n", "   ") == "a\n\n   b\n  c\n"


def test_a_picture_names_its_files_from_the_folder_of_its_page() -> None:
    root = picture("steps", Path("README.md"), 'A "quoted" <b>&</b> it\'s')
    decision = picture(
        "steps.de", Path("docs/decisions/0001-x.de.md"), "Schritte", "  "
    )

    assert root == (
        "<picture>\n"
        '  <source media="(prefers-color-scheme: dark)" srcset="docs/images/diagrams/steps.dark.svg">\n'
        '  <img src="docs/images/diagrams/steps.svg" alt="A &quot;quoted&quot; &lt;b&gt;&amp;&lt;/b&gt; it\'s">\n'
        "</picture>\n"
    )
    assert decision == (
        "  <picture>\n"
        '    <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/steps.de.dark.svg">\n'
        '    <img src="../images/diagrams/steps.de.svg" alt="Schritte">\n'
        "  </picture>\n"
    )


def test_a_name_is_taken_once(tmp_path: Path) -> None:
    (tmp_path / "docs/diagrams").mkdir(parents=True)
    (tmp_path / "docs/diagrams/steps.mmd").write_text("a\n", encoding="utf-8")
    names = Names(tmp_path)

    assert names.name("a\n", "other") == ("steps", False)
    assert names.name("b\n", "steps") == ("steps-2", True)
    assert names.name("c\n", "steps") == ("steps-3", True)
    assert names.name("d\n", "steps.de") == ("steps.de", True)
    assert names.name("e\n", "steps.de") == ("steps-2.de", True)
    assert names.name("c\n", "anything") == ("steps-3", False)
    assert (tmp_path / "docs/diagrams/steps-2.de.mmd").read_text(
        encoding="utf-8"
    ) == "e\n"


@pytest.mark.skipif(GIT is None, reason="the Markdown is what git lists")
def test_extract_turns_every_block_into_a_picture_of_a_source(tmp_path: Path) -> None:
    root = repository(
        tmp_path,
        {
            ".gitignore": "ignored.md\n",
            "ignored.md": block(DIAGRAM),
            "README.md": "# Demo\n\n"
            + block(DIAGRAM)
            + "\nText.\n\n1. A step:\n\n"
            + block("flowchart TB\n    a[<code>x</code>] --> b\n", indent="   ")
            + "\nThe end.\n",
            "README.de.md": "# Demo\n\n"
            + block(GERMAN)
            + "\n1. Ein Schritt:\n\n"
            + block("flowchart TB\n    a[<code>x</code>] --> b\n", indent="   "),
            "docs/guide.md": "# Guide\n\n" + block(DIAGRAM),
            "docs/other.de.md": block(GERMAN.replace("main", "dev"))
            + "\n"
            + block(GERMAN.replace("main", "test")),
            "docs/end.md": block("flowchart TB\n    a --> b\n").removesuffix("\n"),
        },
    )
    extracted = extract(root)

    assert [
        (item.page.as_posix(), item.source.as_posix(), item.new) for item in extracted
    ] == [
        ("README.md", "docs/diagrams/how-a-change-ships.mmd", True),
        # Without accTitle, the heading above names it.
        ("README.md", "docs/diagrams/demo.mmd", True),
        ("docs/end.md", "docs/diagrams/end-1.mmd", True),
        ("docs/guide.md", "docs/diagrams/how-a-change-ships.mmd", False),
        # The German page takes the names of the English one, and its second diagram
        # is the same as there.
        ("README.de.md", "docs/diagrams/how-a-change-ships.de.mmd", True),
        ("README.de.md", "docs/diagrams/demo.mmd", False),
        # Without an English page, the German titles name them.
        (
            "docs/other.de.md",
            "docs/diagrams/wie-eine-aenderung-ausgeliefert-wird.de.mmd",
            True,
        ),
        (
            "docs/other.de.md",
            "docs/diagrams/wie-eine-aenderung-ausgeliefert-wird-2.de.mmd",
            True,
        ),
    ]
    sources = root / "docs/diagrams"
    assert (sources / "how-a-change-ships.mmd").read_text(encoding="utf-8") == DIAGRAM
    assert (sources / "demo.mmd").read_text(encoding="utf-8") == (
        "flowchart TB\n    a[x] --> b\n"
    )
    assert (sources / "how-a-change-ships.de.mmd").read_text(encoding="utf-8") == GERMAN
    assert (root / "README.md").read_text(encoding="utf-8") == (
        "# Demo\n\n"
        + picture("how-a-change-ships", Path("README.md"), alt_text(DIAGRAM))
        + "\nText.\n\n1. A step:\n\n"
        + picture("demo", Path("README.md"), "Demo: x", "   ")
        + "\nThe end.\n"
    )
    assert (root / "docs/guide.md").read_text(encoding="utf-8") == (
        "# Guide\n\n"
        + picture("how-a-change-ships", Path("docs/guide.md"), alt_text(DIAGRAM))
    )
    assert '<img src="images/diagrams/how-a-change-ships.svg"' in (
        root / "docs/guide.md"
    ).read_text(encoding="utf-8")
    # A block at the end of a file without a line break is replaced the same way.
    assert (root / "docs/end.md").read_text(encoding="utf-8") == picture(
        "end-1", Path("docs/end.md"), "A diagram"
    ).removesuffix("\n")
    # What git ignores stays as it is.
    assert (root / "ignored.md").read_text(encoding="utf-8") == block(DIAGRAM)

    # Again, nothing changes.
    pages = {path: path.read_bytes() for path in root.rglob("*.md")}
    assert extract(root) == []
    assert {path: path.read_bytes() for path in root.rglob("*.md")} == pages


@pytest.mark.skipif(GIT is None, reason="the Markdown is what git lists")
def test_a_german_page_with_other_diagrams_names_them_itself(tmp_path: Path) -> None:
    root = repository(
        tmp_path,
        {
            "README.md": block(DIAGRAM),
            "README.de.md": block(GERMAN) + block(GERMAN.replace("main", "dev")),
        },
    )

    extracted = extract(root)

    assert [item.source.name for item in extracted] == [
        "how-a-change-ships.mmd",
        "wie-eine-aenderung-ausgeliefert-wird.de.mmd",
        "wie-eine-aenderung-ausgeliefert-wird-2.de.mmd",
    ]


@pytest.mark.skipif(GIT is None, reason="the Markdown is what git lists")
def test_the_pages_are_the_markdown_of_git_english_first(tmp_path: Path) -> None:
    root = repository(
        tmp_path,
        {
            "README.de.md": "",
            "README.md": "",
            "docs/a.de.md": "",
            "docs/z.md": "",
            "notes.txt": "",
            "gone.md": "",
        },
    )
    assert GIT
    subprocess.run([GIT, "add", "gone.md"], cwd=root, check=True)
    (root / "gone.md").unlink()

    assert markdown_pages(root) == [
        Path("README.md"),
        Path("docs/z.md"),
        Path("README.de.md"),
        Path("docs/a.de.md"),
    ]


@pytest.mark.skipif(GIT is None, reason="the Markdown is what git lists")
def test_the_command_lists_what_became_a_picture(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repository(tmp_path, {"README.md": block(DIAGRAM) + "\n" + block(DIAGRAM)})

    assert main(["diagrams", "extract"], root=root) == 0
    assert capsys.readouterr().out == (
        "README.md: docs/diagrams/how-a-change-ships.mmd\n"
        "README.md: docs/diagrams/how-a-change-ships.mmd, which was there already\n"
        "2 diagram(s) became pictures of their sources in docs/diagrams/.\n"
    )
    assert main(["diagrams", "extract"], root=root) == 0
    assert capsys.readouterr().out == "No ```mermaid block in the Markdown.\n"


def test_the_command_fails_outside_a_repository(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["diagrams", "extract"], root=tmp_path / "missing") == 2
    assert capsys.readouterr().err.startswith("blueprint.py: ")


# What the diagram bots commit


def kept(folder: Path, files: dict[str, str], deleted: str = "") -> Path:
    """A folder as the check keeps it for the diagram bot."""
    for name, text in files.items():
        path = folder / "files" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    if deleted:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "deleted.txt").write_text(deleted, encoding="utf-8", newline="\n")
    return folder


@pytest.mark.skipif(GIT is None, reason="what changed is what git says")
def test_keep_copies_what_drawing_changed(tmp_path: Path) -> None:
    root = repository(
        tmp_path / "repository",
        {
            "README.md": "# Demo\n\n" + block(DIAGRAM),
            "docs/guide.md": "# Guide\n",
            "docs/diagrams/steps.mmd": DIAGRAM,
            "docs/images/diagrams/steps.svg": "<svg old>\n",
            "docs/images/diagrams/gone.svg": "<svg>\n",
            "src/app.py": "x = 1\n",
        },
    )
    commit(root, "Main")
    (root / "README.md").write_text("# Demo\n\nA picture\n", encoding="utf-8")
    (root / "docs/images/diagrams/steps.svg").write_text(
        "<svg new>\n", encoding="utf-8"
    )
    (root / "docs/images/diagrams/gone.svg").unlink()
    (root / "docs/diagrams/new.mmd").write_text(DIAGRAM, encoding="utf-8")
    # Anything else that changed stays out.
    (root / "src/app.py").write_text("x = 2\n", encoding="utf-8")
    folder = tmp_path / "kept"

    found = keep(root, folder)

    assert found == Changes(
        ("README.md", "docs/diagrams/new.mmd", "docs/images/diagrams/steps.svg"),
        ("docs/images/diagrams/gone.svg",),
    )
    assert sorted(
        path.relative_to(folder).as_posix()
        for path in folder.rglob("*")
        if path.is_file()
    ) == [
        "deleted.txt",
        "files/README.md",
        "files/docs/diagrams/new.mmd",
        "files/docs/images/diagrams/steps.svg",
    ]
    assert (folder / "files/README.md").read_text(encoding="utf-8") == (
        "# Demo\n\nA picture\n"
    )
    assert (folder / "deleted.txt").read_text(encoding="utf-8") == (
        "docs/images/diagrams/gone.svg\n"
    )
    assert changes(folder) == found

    commit(root, "Drawn")
    assert keep(root, tmp_path / "nothing") == Changes((), ())
    assert not (tmp_path / "nothing").exists()


@pytest.mark.parametrize(
    ("path", "allowed"),
    [
        ("docs/diagrams/steps.mmd", True),
        ("docs/diagrams/steps.de.mmd", True),
        ("docs/images/diagrams/steps.dark.svg", True),
        ("README.md", True),
        ("docs/decisions/0001-a_decision.md", True),
        (".github/ISSUE_TEMPLATE/bug.md", True),
        # Only sources in docs/diagrams/, only pictures in docs/images/diagrams/.
        ("docs/diagrams/steps.svg", False),
        ("docs/images/diagrams/steps.mmd", False),
        ("docs/images/diagrams/old/steps.svg", False),
        # Nothing else, nothing outside of the repository and nothing in .git.
        (".github/workflows/lint.yml", False),
        ("scripts/check.sh", False),
        ("../README.md", False),
        ("docs/../README.md", False),
        ("/README.md", False),
        ("docs//README.md", False),
        ("./README.md", False),
        (".git/info/README.md", False),
        ("docs/a page.md", False),
        ("docs/..md", False),
    ],
)
def test_the_bot_writes_only_sources_pictures_and_pages(
    path: str, allowed: bool
) -> None:
    assert committable(path) == allowed


@pytest.mark.parametrize(
    ("files", "deleted", "error"),
    [
        (
            {"docs/images/diagrams/steps.svg": "#!/bin/sh\n"},
            "",
            "docs/images/diagrams/steps.svg, which is no SVG picture",
        ),
        (
            {".github/workflows/lint.yml": "<svg >\n"},
            "",
            ".github/workflows/lint.yml, which is no source, picture or page",
        ),
        ({}, "README.md\n", "would delete README.md, which is no picture"),
        (
            {},
            "docs/images/diagrams/../../../x.svg\n",
            "would delete docs/images/diagrams/../../../x.svg",
        ),
        ({}, "", "hold nothing to commit"),
    ],
)
def test_the_bot_refuses_anything_else(
    tmp_path: Path, files: dict[str, str], deleted: str, error: str
) -> None:
    folder = kept(tmp_path / "kept", files, deleted)

    with pytest.raises(ValueError, match=re.escape(error)):
        changes(folder)


def test_the_bot_refuses_a_link(tmp_path: Path) -> None:
    folder = kept(tmp_path / "kept", {"README.md": "# Demo\n"})
    (tmp_path / "secret").mkdir()
    (tmp_path / "secret.md").write_text("A secret\n", encoding="utf-8")
    for name, target in (
        ("docs", tmp_path / "secret"),
        ("CHANGES.md", tmp_path / "secret.md"),
    ):
        try:
            (folder / "files" / name).symlink_to(target, target.is_dir())
        except OSError:
            pytest.skip("this system makes no symbolic links without privileges")
        with pytest.raises(ValueError, match=f"hold {name}, which is no source"):
            changes(folder)
        (folder / "files" / name).unlink()


def test_the_request_commits_what_the_check_kept(tmp_path: Path) -> None:
    folder = kept(
        tmp_path / "kept",
        {
            "README.md": "# Demo\n",
            "docs/diagrams/steps.mmd": DIAGRAM,
            "docs/images/diagrams/steps.svg": "<svg steps>\n",
        },
        "docs/images/diagrams/gone.svg\ndocs/images/diagrams/gone.dark.svg\n",
    )

    request = commit_request(folder, "o/r", "feature", "abc1234", "docs: x", "Body")

    assert "createCommitOnBranch" in request["query"]
    assert request["variables"] == {
        "input": {
            "branch": {"repositoryNameWithOwner": "o/r", "branchName": "feature"},
            "expectedHeadOid": "abc1234",
            "message": {"headline": "docs: x", "body": "Body"},
            "fileChanges": {
                "additions": [
                    {"path": path, "contents": base64.b64encode(text).decode()}
                    for path, text in (
                        ("README.md", b"# Demo\n"),
                        ("docs/diagrams/steps.mmd", DIAGRAM.encode()),
                        ("docs/images/diagrams/steps.svg", b"<svg steps>\n"),
                    )
                ],
                "deletions": [
                    {"path": "docs/images/diagrams/gone.dark.svg"},
                    {"path": "docs/images/diagrams/gone.svg"},
                ],
            },
        }
    }


def test_the_bot_says_which_blocks_became_pictures(tmp_path: Path) -> None:
    pictures = kept(
        tmp_path / "pictures",
        {"docs/images/diagrams/steps.svg": "<svg >\n"},
        "docs/images/diagrams/gone.svg\n",
    )
    pages = kept(
        tmp_path / "pages",
        {
            "README.md": "# Demo\n",
            "docs/diagrams/steps.mmd": DIAGRAM,
            "docs/images/diagrams/steps.svg": "<svg >\n",
        },
    )
    listed = (
        "- `README.md`: its `mermaid` blocks are pictures now\n"
        "- `docs/diagrams/steps.mmd`: the source of a diagram\n"
        "- `docs/images/diagrams/steps.svg`: drawn anew\n"
    )

    # Pictures drawn anew need no comment: the commit says it.
    assert report(pictures, "comment") == ""
    comment = report(pages, "comment")
    assert comment.startswith("The GitHub app, the stores and other renderers")
    assert f":\n\n{listed}\nChange a diagram in its source" in comment
    description = report(pictures, "pull-request")
    assert description.startswith("`main` has diagrams that not every reader sees")
    assert (
        "\n\n- `docs/images/diagrams/steps.svg`: drawn anew\n"
        "- `docs/images/diagrams/gone.svg`: deleted, its source is gone\n\n"
    ) in description
    assert description.endswith("as a picture of its source without it.\n")


@pytest.mark.skipif(GIT is None, reason="what changed is what git says")
def test_the_commands_of_the_diagram_bots(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repository(tmp_path / "repository", {"README.md": "# Demo\n"})
    commit(root, "Main")
    (root / "docs/images/diagrams").mkdir(parents=True)
    (root / "docs/images/diagrams/steps.svg").write_text("<svg >\n", encoding="utf-8")
    folder = tmp_path / "kept"

    assert main(["diagrams", "keep", str(folder)], root=root) == 0
    assert capsys.readouterr().out == "- `docs/images/diagrams/steps.svg`: drawn anew\n"

    arguments = ["diagrams", "commit", str(folder), "--branch", "b", "--head", "c0ffee"]
    assert main([*arguments, "--headline", "docs: x"], root=root) == 2
    assert capsys.readouterr().err == "blueprint.py: diagrams commit needs --repo\n"
    assert main(["--repo", "o/r", *arguments, "--headline", "docs: x"]) == 0
    request = json.loads(capsys.readouterr().out)
    assert request["variables"]["input"]["expectedHeadOid"] == "c0ffee"
    assert request["variables"]["input"]["message"] == {
        "headline": "docs: x",
        "body": "",
    }

    assert main(["diagrams", "report", str(folder)]) == 0
    assert capsys.readouterr().out == ""
    assert main(["diagrams", "report", str(folder), "--for", "pull-request"]) == 0
    assert "- `docs/images/diagrams/steps.svg`: drawn anew\n" in capsys.readouterr().out

    # What the check kept is checked before anything is committed.
    (folder / "files/docs/images/diagrams/steps.svg").write_text(
        "<x>", encoding="utf-8"
    )
    assert main(["--repo", "o/r", *arguments, "--headline", "docs: x"]) == 2
    assert capsys.readouterr().err.startswith("blueprint.py: The diagrams of the check")


# The script


# Docker, which draws each source of the input as two pictures that name it, and
# records how it was started; with FAIL, it fails like a source that doesn't parse,
# and STYLE stands for a new version of mermaid-cli, which draws them otherwise.
DOCKER = """#!/usr/bin/env bash
printf '%s\\n' "$@" > "$CALLS"
if [[ -n "${FAIL:-}" ]]; then
  echo "Error: Parse error on line 2" >&2
  exit 1
fi
input="$(mktemp -d)"
output="$(mktemp -d)"
tar -xf - -C "$input"
[[ -f "$input/draw.mjs" ]] || exit 3
for file in "$input"/*.mmd; do
  name="$(basename "$file" .mmd)"
  echo "<svg $name${STYLE:-}>" > "$output/$name.svg"
  echo "<svg $name dark${STYLE:-}>" > "$output/$name.dark.svg"
done
tar -cf - -C "$output" .
rm -rf "$input" "$output"
"""


# python3, which runs the Python of the tests.
PYTHON3 = '#!/usr/bin/env bash\nexec "$PYTHON" "$@"\n'


# What the script needs besides the commands that a test takes away.
NEEDED = ("git", "tar", "sed", "grep", "mktemp", "cp", "basename")


def without(*commands: str) -> str:
    """The PATH without the folders that hold these commands; a test skips where they
    share a folder with what the script needs, such as /usr/bin on Linux."""
    path = []
    for entry in os.environ.get("PATH", os.defpath).split(os.pathsep):
        if any(shutil.which(command, path=entry) for command in commands):
            if any(shutil.which(command, path=entry) for command in NEEDED):
                pytest.skip(
                    f"{entry} holds {', '.join(commands)} and what the script needs"
                )
            continue
        path.append(entry)
    return os.pathsep.join(path)


def script(
    root: Path,
    tmp_path: Path,
    *arguments: str,
    docker: bool = True,
    python: bool = True,
    fail: bool = False,
) -> subprocess.CompletedProcess[str]:
    """scripts/diagrams.sh of the blueprint in this repository, with the stubs of
    Docker and Python 3, or without them."""
    (root / "scripts").mkdir(exist_ok=True)
    shutil.copy(ROOT / "scripts/diagrams.sh", root / "scripts/diagrams.sh")
    stubs = tmp_path / "stubs"
    stubs.mkdir(exist_ok=True)
    for name, text, wanted in (
        ("docker", DOCKER, docker),
        ("python3", PYTHON3, python),
    ):
        stub = stubs / name
        stub.unlink(missing_ok=True)
        if wanted:
            stub.write_text(text, encoding="utf-8", newline="\n")
            stub.chmod(0o755)
    environment = {key: value for key, value in os.environ.items() if key != "FAIL"}
    hidden = ([] if docker else ["docker"]) + ([] if python else ["python3", "python"])
    environment.update(
        PATH=without(*hidden),
        STUBS=stubs.as_posix(),
        CALLS=(tmp_path / "calls").as_posix(),
        PYTHON=Path(sys.executable).as_posix(),
        PYTHONIOENCODING="utf-8",
    )
    if fail:
        environment["FAIL"] = "1"
    return subprocess.run(
        in_bash("scripts/diagrams.sh", *arguments),
        cwd=root,
        env=environment,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )


def drawn(root: Path) -> dict[str, str]:
    folder = root / "docs/images/diagrams"
    return {
        path.name: path.read_text(encoding="utf-8") for path in sorted(folder.glob("*"))
    }


needs_bash = pytest.mark.skipif(
    BASH is None or GIT is None, reason="the script runs in bash, Git Bash on Windows"
)
# In the copy of the mutation tests, the tool that a test copies into a repository
# is the code with the mutants, which the variables of mutmut switch in the process
# that the test starts, outside of the copy, where mutmut finds no configuration.
runs_a_copy_of_the_tool = pytest.mark.mutation_unsafe


@needs_bash
def test_the_check_passes_without_diagrams(tmp_path: Path) -> None:
    root = repository(tmp_path / "repository", {"README.md": "# Demo\n"})

    result = script(root, tmp_path, "--check")

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == "No diagrams here.\n"


@needs_bash
def test_a_block_is_a_warning_until_the_first_source(tmp_path: Path) -> None:
    root = repository(
        tmp_path / "repository",
        {
            ".gitignore": "ignored.md\n",
            "ignored.md": block(DIAGRAM),
            "README.md": "# Demo\n\n" + block(DIAGRAM),
            "docs/list.md": "1. A step\n\n" + block(DIAGRAM, indent="   ", fence="~~~"),
        },
    )

    result = script(root, tmp_path, "--check")

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == (
        "README.md:3: a ```mermaid block, which the GitHub app shows as code\n"
        "docs/list.md:3: a ```mermaid block, which the GitHub app shows as code\n"
        "A warning for now: bash scripts/diagrams.sh --extract turns each into a picture"
        " of a source in docs/diagrams/.\n"
    )


@needs_bash
def test_the_check_fails_on_what_doesnt_match(tmp_path: Path) -> None:
    root = repository(
        tmp_path / "repository",
        {
            "README.md": "# Demo\n\n"
            + block(DIAGRAM)
            + picture("shown", Path("README.md"), "Shown")
            + '<img src="docs/images/diagrams/gone.svg" alt="">\n',
            "docs/diagrams/shown.mmd": DIAGRAM,
            "docs/diagrams/half.mmd": 'flowchart TB\n    a["<b>bold</b>"]\n    b[<code>x</code>]\n',
            "docs/images/diagrams/shown.svg": "<svg>\n",
            "docs/images/diagrams/shown.dark.svg": "<svg>\n",
            "docs/images/diagrams/half.svg": "<svg>\n",
            "docs/images/diagrams/orphan.dark.svg": "<svg>\n",
        },
    )

    result = script(root, tmp_path, "--check")

    assert result.returncode == 1
    assert result.stdout == (
        "README.md:3: a ```mermaid block, which the GitHub app shows as code\n"
        "README.md:14: shows docs/images/diagrams/gone.svg, which doesn't exist\n"
        "docs/diagrams/half.mmd: its picture docs/images/diagrams/half.dark.svg is missing\n"
        "docs/diagrams/half.mmd:2: HTML, which the picture shows as text; only <br> breaks"
        ' a line, and **bold** and *italic* need a label in "`…`"\n'
        "docs/diagrams/half.mmd:3: HTML, which the picture shows as text; only <br> breaks"
        ' a line, and **bold** and *italic* need a label in "`…`"\n'
        "docs/images/diagrams/orphan.dark.svg: its source docs/diagrams/orphan.mmd is missing\n"
        "1 diagram(s) in a ```mermaid block; bash scripts/diagrams.sh --extract turns each"
        " into a picture of a source in docs/diagrams/.\n"
        "bash scripts/diagrams.sh draws the pictures of every source again, with Docker.\n"
    )


@runs_a_copy_of_the_tool
@needs_bash
def test_the_script_takes_out_checks_and_draws_the_diagrams(tmp_path: Path) -> None:
    root = repository(
        tmp_path / "repository",
        {
            "README.md": "# Demo\n\n" + block(DIAGRAM),
            "docs/images/diagrams/old.svg": "<svg>\n",
        },
    )
    # As in a repository made from the blueprint, the tool is in .github/.
    (root / ".github").mkdir()
    shutil.copy(ROOT / "blueprint.py", root / ".github/blueprint.py")
    shutil.copytree(
        ROOT / "blueprint",
        root / ".github/blueprint",
        ignore=shutil.ignore_patterns("__pycache__", "*.meta", "*.spans"),
    )

    result = script(root, tmp_path, "--extract")

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == (
        "README.md: docs/diagrams/how-a-change-ships.mmd\n"
        "1 diagram(s) became pictures of their sources in docs/diagrams/.\n"
        "Drew the 1 diagram(s) of docs/diagrams/ into docs/images/diagrams/.\n"
    )
    assert drawn(root) == {
        "how-a-change-ships.dark.svg": "<svg how-a-change-ships dark>\n",
        "how-a-change-ships.svg": "<svg how-a-change-ships>\n",
    }
    calls = (tmp_path / "calls").read_text(encoding="utf-8").splitlines()
    # Without network, with the image that Renovate keeps current.
    assert calls[:4] == ["run", "--rm", "--interactive", "--network"]
    assert calls[4] == "none"
    assert any(
        call.startswith("minlag/mermaid-cli:") and "@sha256:" in call for call in calls
    )

    check = script(root, tmp_path, "--check")
    assert check.returncode == 0, check.stdout
    assert (
        check.stdout == "Each of the 1 diagram(s) in docs/diagrams/ has its pictures.\n"
    )

    # Without sources, the pictures go too.
    shutil.rmtree(root / "docs/diagrams")
    result = script(root, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == "No diagrams in docs/diagrams/.\n"
    assert drawn(root) == {}


@needs_bash
def test_the_pictures_stay_when_drawing_fails(tmp_path: Path) -> None:
    root = repository(
        tmp_path / "repository",
        {
            "docs/diagrams/steps.mmd": DIAGRAM,
            "docs/images/diagrams/steps.svg": "<svg old>\n",
        },
    )

    failed = script(root, tmp_path, fail=True)
    missing = script(root, tmp_path, docker=False)

    assert failed.returncode == 1
    assert failed.stderr == (
        "Error: Parse error on line 2\nDrawing the diagrams failed; the log above says why.\n"
    )
    assert missing.returncode == 1
    assert missing.stderr.startswith("Drawing the diagrams needs Docker")
    assert drawn(root) == {"steps.svg": "<svg old>\n"}


@needs_bash
def test_taking_the_diagrams_out_needs_python(tmp_path: Path) -> None:
    root = repository(tmp_path / "repository", {"README.md": block(DIAGRAM)})

    result = script(root, tmp_path, "--extract", python=False)

    assert result.returncode == 1
    assert result.stderr == "Taking the diagrams out of the Markdown needs Python 3.\n"


@needs_bash
@pytest.mark.parametrize(("arguments", "code"), [(["--help"], 0), (["--draw"], 2)])
def test_the_script_says_how_to_use_it(
    tmp_path: Path, arguments: list[str], code: int
) -> None:
    root = repository(tmp_path / "repository", {})

    result = script(root, tmp_path, *arguments)

    assert result.returncode == code
    usage = result.stdout + result.stderr
    assert usage.startswith("bash scripts/diagrams.sh            draw the picture")
    assert "bash scripts/diagrams.sh --extract" in usage
    assert "bash scripts/diagrams.sh --check" in usage


# The check diagrams of Lint, the diagram bot of After the checks and that of main


def workflow_step(workflow: str, job: str, step: str) -> str:
    """The script of a step of a job, as the runner hands it to bash."""
    text = (ROOT / ".github/workflows" / workflow).read_text(encoding="utf-8")
    start = text.index(f"      - name: {step}\n", text.index(f"\n  {job}:\n"))
    run = text.index("        run: |\n", start) + len("        run: |\n")
    lines = []
    for line in text[run:].splitlines(keepends=True):
        if line.strip() and not line.startswith("          "):
            break
        lines.append(line)
    return textwrap.dedent("".join(lines))


def run_step(
    script: str, cwd: Path, tmp_path: Path, stubs: dict[str, str], **variables: str
) -> tuple[subprocess.CompletedProcess[str], str, str]:
    """A step as GitHub runs it, bash -e, with these stubs first on the PATH; its
    result, its outputs and its summary."""
    folder = tmp_path / "stubs"
    folder.mkdir(exist_ok=True)
    for name, text in {"python3": PYTHON3, **stubs}.items():
        (folder / name).write_text(text, encoding="utf-8", newline="\n")
        (folder / name).chmod(0o755)
    runner = tmp_path / "runner"
    runner.mkdir(exist_ok=True)
    output = tmp_path / "output"
    summary = tmp_path / "summary"
    output.write_text("", encoding="utf-8")
    summary.write_text("", encoding="utf-8")
    (tmp_path / "step.sh").write_text(script, encoding="utf-8", newline="\n")
    environment = {
        **os.environ,
        "STUBS": folder.as_posix(),
        "CALLS": (tmp_path / "calls").as_posix(),
        "PYTHON": Path(sys.executable).as_posix(),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "RUNNER_TEMP": runner.as_posix(),
        "GITHUB_OUTPUT": output.as_posix(),
        "GITHUB_STEP_SUMMARY": summary.as_posix(),
        "GITHUB_REPOSITORY": "o/r",
        **variables,
    }
    result = subprocess.run(
        in_bash("-e", (tmp_path / "step.sh").as_posix()),
        cwd=cwd,
        env=environment,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    return (
        result,
        output.read_text(encoding="utf-8"),
        summary.read_text(encoding="utf-8"),
    )


def git_in(root: Path, *arguments: str) -> str:
    assert GIT
    return subprocess.run(
        [GIT, "-c", "user.name=T", "-c", "user.email=t@example.com", *arguments],
        cwd=root,
        check=True,
        capture_output=True,
        encoding="utf-8",
    ).stdout.strip()


def commit(root: Path, message: str) -> None:
    git_in(root, "add", "--all")
    git_in(root, "commit", "--quiet", "--allow-empty", "-m", message)


def with_tools(root: Path) -> Path:
    """A repository as the blueprint makes one: scripts/diagrams.sh, and blueprint.py
    in .github/."""
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / "scripts/diagrams.sh", root / "scripts/diagrams.sh")
    (root / ".github").mkdir(exist_ok=True)
    shutil.copy(ROOT / "blueprint.py", root / ".github/blueprint.py")
    shutil.copytree(
        ROOT / "blueprint",
        root / ".github/blueprint",
        ignore=shutil.ignore_patterns("__pycache__"),
        dirs_exist_ok=True,
    )
    return root


def pull_request(
    root: Path, change: dict[str, str], main: dict[str, str] | None = None
) -> str:
    """The merge of a pull request with these changes into main, as the check checks
    it out: main and the head of the pull request are its parents. main may change
    meanwhile. Returns the head."""
    git_in(root, "branch", "-M", "main")
    git_in(root, "switch", "--quiet", "-c", "feature")
    for name, text in change.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8", newline="\n")
    commit(root, "The change")
    head = git_in(root, "rev-parse", "HEAD")
    git_in(root, "switch", "--quiet", "main")
    for name, text in (main or {}).items():
        (root / name).write_text(text, encoding="utf-8", newline="\n")
    commit(root, "Main moved on")
    git_in(root, "merge", "--quiet", "--no-ff", "--no-edit", "feature")
    return head


DRAW = (
    "lint.yml",
    "diagrams",
    "Draw the diagrams and compare them with the committed pictures",
)
MERGES = DIAGRAM.replace("ships", "merges")
MAIN = {
    "README.md": "# Demo\n",
    "docs/diagrams/steps.mmd": DIAGRAM,
    "docs/images/diagrams/steps.svg": "<svg steps>\n",
    "docs/images/diagrams/steps.dark.svg": "<svg steps dark>\n",
}


def files_of(folder: Path) -> dict[str, str]:
    return {
        path.relative_to(folder).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(folder.rglob("*"))
        if path.is_file()
    }


@runs_a_copy_of_the_tool
@needs_bash
def test_the_check_keeps_what_differs_for_the_bot(tmp_path: Path) -> None:
    root = with_tools(
        repository(
            tmp_path / "repository",
            {
                **MAIN,
                "README.md": "# Demo\n\n" + block(MERGES),
                "docs/images/diagrams/steps.svg": "<svg old>\n",
                "docs/images/diagrams/gone.svg": "<svg>\n",
            },
        )
    )
    commit(root, "Files")

    result, output, summary = run_step(
        workflow_step(*DRAW),
        root,
        tmp_path,
        {"docker": DOCKER},
        EVENT="workflow_dispatch",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert output == "stale=true\n"
    name = "how-a-change-merges"
    assert files_of(tmp_path / "runner/diagrams") == {
        "deleted.txt": "docs/images/diagrams/gone.svg\n",
        "files/README.md": "# Demo\n\n"
        + picture(name, Path("README.md"), alt_text(MERGES)),
        f"files/docs/diagrams/{name}.mmd": MERGES,
        f"files/docs/images/diagrams/{name}.svg": f"<svg {name}>\n",
        f"files/docs/images/diagrams/{name}.dark.svg": f"<svg {name} dark>\n",
        "files/docs/images/diagrams/steps.svg": "<svg steps>\n",
    }
    assert summary.startswith("### Diagrams\nThe GitHub app shows a `mermaid` block")
    assert "- `README.md`: its `mermaid` blocks are pictures now\n" in summary
    assert "- `docs/images/diagrams/gone.svg`: deleted, its source is gone\n" in summary
    assert "the diagram bot commits it for you in a minute" in summary


@runs_a_copy_of_the_tool
@needs_bash
@pytest.mark.parametrize(
    ("change", "drawn", "message"),
    [
        # Text alone, and a block that only a page in the change mentions.
        (
            {"README.md": "# Demo\n\nA `mermaid` block is code.\n"},
            False,
            "The pull request changes no diagram.\n",
        ),
        (
            {"docs/diagrams/steps.mmd": DIAGRAM + "\n"},
            True,
            "Every diagram is a picture of its source, as drawn.\n",
        ),
    ],
)
def test_the_check_passes_when_every_diagram_is_a_picture(
    tmp_path: Path, change: dict[str, str], drawn: bool, message: str
) -> None:
    root = with_tools(repository(tmp_path / "repository", MAIN))
    commit(root, "Main")
    pull_request(root, change)

    result, output, summary = run_step(
        workflow_step(*DRAW), root, tmp_path, {"docker": DOCKER}, EVENT="pull_request"
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert output == ""
    assert summary == message
    assert (tmp_path / "calls").exists() == drawn


@runs_a_copy_of_the_tool
@needs_bash
def test_a_block_waits_for_main_until_the_first_source(tmp_path: Path) -> None:
    # Right after the update of the blueprint, before the Diagrams workflow of main
    # moved the blocks, a pull request with a block passes.
    root = with_tools(repository(tmp_path / "repository", {"README.md": "# Demo\n"}))
    commit(root, "Main")
    pull_request(root, {"README.md": "# Demo\n\n" + block(DIAGRAM)})

    result, output, summary = run_step(
        workflow_step(*DRAW), root, tmp_path, {"docker": DOCKER}, EVENT="pull_request"
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert output == ""
    assert summary.startswith("No page of this repository shows a picture")
    assert summary.endswith("turns the blocks into pictures after the merge.\n")
    assert (root / "README.md").read_text(encoding="utf-8").endswith(block(DIAGRAM))
    assert not (tmp_path / "calls").exists()


@runs_a_copy_of_the_tool
@needs_bash
def test_the_update_leaves_sources_that_a_project_draws_itself(tmp_path: Path) -> None:
    # A repository that kept Mermaid sources in docs/diagrams/ before, drawn by a
    # script of its own into other pictures: the update of the blueprint, which
    # changes scripts/diagrams.sh, passes without pictures that no page shows.
    root = with_tools(
        repository(
            tmp_path / "repository",
            {
                "README.md": "# Demo\n\n![Steps](docs/images/en/steps-light.png)\n",
                "docs/diagrams/steps.en.mmd": 'flowchart TB\n    a["<b>A</b>"] --> b\n',
                "docs/diagrams/light.json": "{}\n",
            },
        )
    )
    commit(root, "Main")
    script_text = (root / "scripts/diagrams.sh").read_text(encoding="utf-8")
    pull_request(root, {"scripts/diagrams.sh": script_text + "# Updated\n"})

    result, output, summary = run_step(
        workflow_step(*DRAW), root, tmp_path, {"docker": DOCKER}, EVENT="pull_request"
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert output == ""
    assert summary.startswith("No page of this repository shows a picture")
    assert not (tmp_path / "calls").exists()
    check = script(root, tmp_path, "--check")
    assert check.returncode == 0, check.stdout + check.stderr
    assert check.stdout == (
        "No page shows a picture of docs/images/diagrams/ yet, so the sources in"
        " docs/diagrams/ are left as they are.\n"
    )
    extracted = script(root, tmp_path, "--extract")
    assert extracted.returncode == 0, extracted.stdout + extracted.stderr
    assert extracted.stdout.endswith(
        "No page shows a picture of docs/images/diagrams/ yet, so there is nothing to"
        " draw.\n"
    )
    assert not (root / "docs/images/diagrams").exists()
    assert script(root, tmp_path, "--adopted").returncode == 1

    # Once a page shows a picture, the sources need theirs.
    (root / "docs/guide.md").write_text(
        picture("steps", Path("docs/guide.md"), "Steps"), encoding="utf-8"
    )
    assert script(root, tmp_path, "--adopted").returncode == 0
    check = script(root, tmp_path, "--check")
    assert check.returncode == 1
    assert "docs/diagrams/steps.en.mmd: its picture" in check.stdout


# gh, as the API answers after the filters of jq.
GH = """#!/usr/bin/env bash
echo "gh $*" >> "$CALLS"
case "$*" in
  "run download 5 --name diagrams --dir "*)
    [[ -n "${ARTIFACT:-}" ]] || exit 1
    mkdir -p "$7" && cp -R "$ARTIFACT"/. "$7"
    ;;
  "api repos/o/r/commits/abc1234def --jq "*) printf '%s\\n' "${MESSAGE:-fix: a label}" ;;
  "api repos/o/r/git/ref/heads/feature --jq .object.sha") printf '%s\\n' "$HEAD" ;;
  "api repos/o/r/git/ref/heads/bot/diagrams") [[ -n "${EXISTS:-}" ]] ;;
  "api repos/o/r/git/ref/heads/bot/diagrams-next") [[ -n "${LEFT:-}" ]] ;;
  "api --method "*) ;;
  "api users/app[bot] --jq .id") echo 42 ;;
  "api graphql --input "*) cp "$4" "$REQUEST" && echo c0ffee ;;
  "pr list --head bot/diagrams --state open --json number --jq "*) echo "${OPEN:-}" ;;
  "pr comment "*|"pr create "*|"pr edit "*) cp "${@: -1}" "$BODY" ;;
  "pr merge "*|"pr close "*) ;;
  *) echo "unexpected: gh $*" >&2; exit 1 ;;
esac
"""
HEADLINE = "docs: draw the diagrams anew"
FETCH = ("after-checks.yml", "diagrams", "Fetch the diagrams that the check drew")
COMMIT = (
    "after-checks.yml",
    "diagrams",
    "Commit the diagrams onto the branch of the pull request",
)


@needs_bash
@pytest.mark.parametrize(
    ("artifact", "message", "code", "found", "summary"),
    [
        # Another check of Lint failed.
        (
            False,
            "",
            0,
            False,
            "The check diagrams kept nothing; another check failed.\n",
        ),
        (True, "", 0, True, ""),
        # The pictures of the bot's own commit differ again.
        (True, HEADLINE, 1, False, ""),
    ],
)
def test_the_diagram_bot_takes_what_the_check_kept(
    tmp_path: Path, artifact: bool, message: str, code: int, found: bool, summary: str
) -> None:
    folder = kept(tmp_path / "kept", {"docs/images/diagrams/steps.svg": "<svg >\n"})
    variables = {"ARTIFACT": folder.as_posix()} if artifact else {}
    if message:
        variables["MESSAGE"] = message

    result, output, written = run_step(
        workflow_step(*FETCH),
        tmp_path,
        tmp_path,
        {"gh": GH},
        GH_REPO="o/r",
        RUN="5",
        SHA="abc1234def",
        HEADLINE=HEADLINE,
        **variables,
    )

    assert result.returncode == code, result.stdout + result.stderr
    assert (output == "found=true\n") == found
    assert written == summary
    if code:
        assert "differ again from what their sources draw" in result.stdout
    if found:
        assert (
            tmp_path / "runner/diagrams/files/docs/images/diagrams/steps.svg"
        ).is_file()


def run_the_diagram_bot(
    root: Path, tmp_path: Path, folder: Path, head: str = "abc1234def"
) -> tuple[subprocess.CompletedProcess[str], str]:
    """The step of the diagram bot that commits what the check kept in folder."""
    shutil.copytree(folder, tmp_path / "runner/diagrams")
    result, _, summary = run_step(
        workflow_step(*COMMIT),
        root,
        tmp_path,
        {"gh": GH},
        GH_REPO="o/r",
        APP_SLUG="app",
        BRANCH="feature",
        NUMBER="7",
        SHA="abc1234def",
        HEAD=head,
        URL="https://github.com/o/r/actions/runs/5",
        HEADLINE=HEADLINE,
        REQUEST=(tmp_path / "request.json").as_posix(),
        BODY=(tmp_path / "body.md").as_posix(),
    )
    return result, summary


def calls(tmp_path: Path) -> list[str]:
    return (tmp_path / "calls").read_text(encoding="utf-8").splitlines()


@runs_a_copy_of_the_tool
@needs_bash
def test_the_diagram_bot_commits_the_pictures_onto_the_branch(tmp_path: Path) -> None:
    root = with_tools(tmp_path / "main")
    folder = kept(
        tmp_path / "kept",
        {
            "docs/images/diagrams/steps.svg": "<svg steps>\n",
            "docs/images/diagrams/steps.dark.svg": "<svg dark>\n",
        },
        "docs/images/diagrams/gone.svg\n",
    )

    result, summary = run_the_diagram_bot(root, tmp_path, folder)

    assert result.returncode == 0, result.stdout + result.stderr
    assert summary == "Committed the diagrams onto feature: c0ffee\n"
    request = json.loads((tmp_path / "request.json").read_text(encoding="utf-8"))
    commit = request["variables"]["input"]
    assert commit["branch"] == {
        "repositoryNameWithOwner": "o/r",
        "branchName": "feature",
    }
    # Only onto the commit whose diagrams the check drew.
    assert commit["expectedHeadOid"] == "abc1234def"
    assert commit["message"] == {
        "headline": HEADLINE,
        "body": "Drawn by scripts/diagrams.sh --extract from the sources in "
        "docs/diagrams/, in the check diagrams: https://github.com/o/r/actions/runs/5"
        "\n\nSigned-off-by: app[bot] <42+app[bot]@users.noreply.github.com>",
    }
    assert commit["fileChanges"] == {
        "additions": [
            {
                "path": "docs/images/diagrams/steps.dark.svg",
                "contents": base64.b64encode(b"<svg dark>\n").decode(),
            },
            {
                "path": "docs/images/diagrams/steps.svg",
                "contents": base64.b64encode(b"<svg steps>\n").decode(),
            },
        ],
        "deletions": [{"path": "docs/images/diagrams/gone.svg"}],
    }
    # Pictures drawn anew need no comment.
    assert not any(call.startswith("gh pr ") for call in calls(tmp_path))


@runs_a_copy_of_the_tool
@needs_bash
@pytest.mark.parametrize(
    "files",
    [
        {"docs/images/diagrams/steps.svg": "#!/bin/sh\n"},
        {".github/workflows/lint.yml": "<svg >\n"},
    ],
)
def test_the_diagram_bot_commits_nothing_but_diagrams(
    tmp_path: Path, files: dict[str, str]
) -> None:
    root = with_tools(tmp_path / "main")

    result, _ = run_the_diagram_bot(root, tmp_path, kept(tmp_path / "kept", files))

    assert result.returncode != 0
    assert "blueprint.py: The diagrams of the check hold" in result.stderr
    assert not (tmp_path / "request.json").exists()


@runs_a_copy_of_the_tool
@needs_bash
def test_the_diagram_bot_leaves_a_branch_that_moved_on(tmp_path: Path) -> None:
    folder = kept(tmp_path / "kept", {"docs/images/diagrams/steps.svg": "<svg >\n"})

    result, summary = run_the_diagram_bot(
        with_tools(tmp_path / "main"), tmp_path, folder, head="f00ba4"
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert summary == (
        "feature moved on from abc1234; the checks of its new head draw the diagrams again.\n"
    )
    assert not (tmp_path / "request.json").exists()


# gh, which only notes what it was asked.
GH_NOTES = '#!/usr/bin/env bash\nprintf "gh %s\\n" "$*" >> "$CALLS"\n'
FAILED = (
    "after-checks.yml",
    "diagrams",
    "Say on the pull request that the bot failed",
)


@needs_bash
@pytest.mark.parametrize(("number", "target"), [("7", "7"), ("", "feature")])
def test_a_diagram_bot_that_fails_says_so_on_the_pull_request(
    tmp_path: Path, number: str, target: str
) -> None:
    # The failed check promised the bot's commit; without it, the pull request learns
    # what to do itself.
    text = (ROOT / ".github/workflows/after-checks.yml").read_text(encoding="utf-8")
    job = text[text.index("\n  diagrams:\n") :]
    assert "        if: failure()\n" in job[job.index(f"      - name: {FAILED[2]}\n") :]

    result, _, _ = run_step(
        workflow_step(*FAILED),
        tmp_path,
        tmp_path,
        {"gh": GH_NOTES},
        GH_REPO="o/r",
        BRANCH="feature",
        NUMBER=number,
        URL="https://github.com/o/r/actions/runs/8",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert calls(tmp_path) == [
        f"gh pr comment {target} --body The diagram bot couldn't commit the diagrams"
        " of this pull request (https://github.com/o/r/actions/runs/8). Run"
        " `bash scripts/diagrams.sh --extract` with Docker and commit what it changes,"
        " or take the files from the artifact `diagrams` of the check *diagrams*."
    ]


def applied(root: Path, request: dict[str, Any]) -> None:
    """What GitHub does with the request of the bot: the commit on the branch."""
    changed = request["variables"]["input"]["fileChanges"]
    for addition in changed["additions"]:
        path = root / addition["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(addition["contents"]))
    for deletion in changed["deletions"]:
        (root / deletion["path"]).unlink()
    commit(root, request["variables"]["input"]["message"]["headline"])


@runs_a_copy_of_the_tool
@needs_bash
def test_a_pull_request_with_a_block_fixes_itself(tmp_path: Path) -> None:
    root = with_tools(
        repository(tmp_path / "repository", {**MAIN, "README.md": "# Demo\n\nText.\n"})
    )
    commit(root, "Main")
    # main moved on, which the commit of the bot onto the branch leaves out.
    head = pull_request(
        root,
        {"README.md": "# Demo\n\nText.\n\n" + block(MERGES)},
        main={"README.md": "# Demo of main\n\nText.\n"},
    )
    checked = tmp_path / "check"
    checked.mkdir()

    result, output, _ = run_step(
        workflow_step(*DRAW), root, checked, {"docker": DOCKER}, EVENT="pull_request"
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert output == "stale=true\n"
    # The bot commits what the check kept onto the head of the pull request.
    bot = tmp_path / "bot"
    bot.mkdir()
    shutil.copytree(checked / "runner/diagrams", tmp_path / "kept")
    result, summary = run_the_diagram_bot(
        with_tools(tmp_path / "main"), bot, tmp_path / "kept", head="abc1234def"
    )
    assert result.returncode == 0, result.stdout + result.stderr
    request = json.loads((bot / "request.json").read_text(encoding="utf-8"))
    assert sorted(
        addition["path"]
        for addition in request["variables"]["input"]["fileChanges"]["additions"]
    ) == [
        "README.md",
        "docs/diagrams/how-a-change-merges.mmd",
        "docs/images/diagrams/how-a-change-merges.dark.svg",
        "docs/images/diagrams/how-a-change-merges.svg",
    ]
    # One comment says which blocks became pictures.
    assert "gh pr comment 7 --body-file " in "\n".join(calls(bot))
    comment = (bot / "body.md").read_text(encoding="utf-8")
    assert "- `README.md`: its `mermaid` blocks are pictures now\n" in comment

    git_in(root, "switch", "--quiet", "feature")
    assert git_in(root, "rev-parse", "HEAD") == head
    applied(root, request)
    # The page of the head, without the change of main.
    assert (root / "README.md").read_text(encoding="utf-8") == (
        "# Demo\n\nText.\n\n"
        + picture("how-a-change-merges", Path("README.md"), alt_text(MERGES))
    )
    git_in(root, "switch", "--quiet", "main")
    git_in(root, "reset", "--quiet", "--hard", "HEAD^1")
    git_in(root, "merge", "--quiet", "--no-ff", "--no-edit", "feature")
    again = tmp_path / "again"
    again.mkdir()

    # The checks of the bot's commit pass.
    result, output, summary = run_step(
        workflow_step(*DRAW), root, again, {"docker": DOCKER}, EVENT="pull_request"
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert output == ""
    assert summary == "Every diagram is a picture of its source, as drawn.\n"
    check = script(root, tmp_path, "--check")
    assert check.returncode == 0, check.stdout + check.stderr


@runs_a_copy_of_the_tool
@needs_bash
def test_a_new_renderer_draws_the_pictures_anew(tmp_path: Path) -> None:
    # Renovate updates the image of mermaid-cli on a branch of the repository, and
    # the new version draws other pictures, which the bot commits.
    root = with_tools(repository(tmp_path / "repository", MAIN))
    commit(root, "Main")
    script_text = (root / "scripts/diagrams.sh").read_text(encoding="utf-8")
    updated = re.sub(r"@sha256:[0-9a-f]{64}", "@sha256:" + "1" * 64, script_text)
    pull_request(root, {"scripts/diagrams.sh": updated})

    result, output, _ = run_step(
        workflow_step(*DRAW),
        root,
        tmp_path,
        {"docker": DOCKER},
        EVENT="pull_request",
        STYLE=" v2",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert output == "stale=true\n"
    assert files_of(tmp_path / "runner/diagrams") == {
        "files/docs/images/diagrams/steps.svg": "<svg steps v2>\n",
        "files/docs/images/diagrams/steps.dark.svg": "<svg steps dark v2>\n",
    }
    assert "@sha256:" + "1" * 64 in (tmp_path / "calls").read_text(encoding="utf-8")


DRAW_MAIN = ("diagrams.yml", "draw", "Draw the diagrams of main")
PULL_REQUEST = (
    "diagrams.yml",
    "pull-request",
    "Open, update or close the pull request of the diagrams",
)


@runs_a_copy_of_the_tool
@needs_bash
@pytest.mark.parametrize("app", ["Iv23li", ""])
def test_the_diagrams_of_main_are_drawn_for_their_pull_request(
    tmp_path: Path, app: str
) -> None:
    root = with_tools(
        repository(
            tmp_path / "repository",
            {**MAIN, "docs/guide.md": "# Guide\n\n" + block(DIAGRAM)},
        )
    )
    commit(root, "A block that went around the check")

    result, output, summary = run_step(
        workflow_step(*DRAW_MAIN), root, tmp_path, {"docker": DOCKER}, APP=app
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert output == "drawn=true\nstale=true\n"
    if app:
        assert summary.startswith("### Diagrams\nThe pull request of the diagram bot")
        assert "::warning::" not in result.stdout
    else:
        # Without the release app, no pull request comes: the run says what to do.
        assert summary.startswith(
            "### Diagrams\nThe variable `RELEASE_AUTOMATION_CLIENT_ID` of the release"
            " app is empty, so no bot opens the pull request with these files. Run"
            " `bash scripts/diagrams.sh --extract` with Docker"
        )
        assert (
            "::warning::main has diagrams that not every reader sees" in result.stdout
        )
    assert "- `docs/guide.md`: its `mermaid` blocks are pictures now\n" in summary
    assert "files/docs/guide.md" in files_of(tmp_path / "runner/diagrams")

    commit(root, "Drawn")
    again = tmp_path / "again"
    again.mkdir()
    result, output, summary = run_step(
        workflow_step(*DRAW_MAIN), root, again, {"docker": DOCKER}, APP=app
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert output == "drawn=true\n"
    assert summary == "Every diagram of main is a picture of its source, as drawn.\n"


@runs_a_copy_of_the_tool
@needs_bash
@pytest.mark.parametrize(
    ("change", "commits", "drawn"),
    [
        # Text alone needs no Docker: the check of the pull request drew the rest.
        ({"README.md": "# Demo\n\nMore text.\n"}, 1, False),
        # A new block, a changed source, or more than one commit is drawn.
        ({"docs/guide.md": "# Guide\n\n" + block(MERGES)}, 1, True),
        ({"docs/diagrams/steps.mmd": DIAGRAM + "\n"}, 1, True),
        ({"README.md": "# Demo\n\nMore text.\n"}, 2, True),
    ],
)
def test_a_push_to_main_draws_only_what_may_have_changed(
    tmp_path: Path, change: dict[str, str], commits: int, drawn: bool
) -> None:
    root = with_tools(repository(tmp_path / "repository", MAIN))
    commit(root, "Main")
    before = git_in(root, "rev-parse", "HEAD")
    for number in range(commits):
        for name, text in change.items():
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text(text + "\n" * number, encoding="utf-8")
        commit(root, f"Push {number}")

    result, output, summary = run_step(
        workflow_step(*DRAW_MAIN),
        root,
        tmp_path,
        {"docker": DOCKER},
        EVENT="push",
        BEFORE=before,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "calls").exists() == drawn
    if drawn:
        assert output.startswith("drawn=true\n")
    else:
        assert output == ""
        assert summary == "The push changes no diagram and adds no `mermaid` block.\n"


def run_the_bot_of_main(
    tmp_path: Path,
    stale: bool,
    open_number: str = "",
    exists: bool = False,
    left: bool = False,
) -> tuple[subprocess.CompletedProcess[str], str, list[str]]:
    root = with_tools(tmp_path / "main")
    if stale:
        shutil.copytree(
            kept(tmp_path / "kept", {"docs/guide.md": "# Guide\n"}),
            tmp_path / "runner/diagrams",
        )
    result, _, summary = run_step(
        workflow_step(*PULL_REQUEST),
        root,
        tmp_path,
        {"gh": GH},
        GH_REPO="o/r",
        APP_SLUG="app",
        BRANCH="bot/diagrams",
        HEADLINE=HEADLINE,
        STALE="true" if stale else "",
        SHA="abc1234def",
        URL="https://github.com/o/r/actions/runs/6",
        OPEN=open_number,
        EXISTS="yes" if exists else "",
        LEFT="yes" if left else "",
        REQUEST=(tmp_path / "request.json").as_posix(),
        BODY=(tmp_path / "body.md").as_posix(),
    )
    return result, summary, calls(tmp_path)


@runs_a_copy_of_the_tool
@needs_bash
def test_the_bot_of_main_opens_one_pull_request_that_merges_itself(
    tmp_path: Path,
) -> None:
    result, summary, made = run_the_bot_of_main(tmp_path, stale=True)

    assert result.returncode == 0, result.stdout + result.stderr
    pull_request_list = (
        "gh pr list --head bot/diagrams --state open --json number "
        "--jq .[0].number // empty"
    )
    assert made == [
        pull_request_list,
        # The commit is made on a branch of its own, from the commit that was drawn.
        "gh api repos/o/r/git/ref/heads/bot/diagrams-next",
        "gh api --method POST repos/o/r/git/refs -f ref=refs/heads/bot/diagrams-next"
        " -f sha=abc1234def",
        "gh api users/app[bot] --jq .id",
        f"gh api graphql --input {(tmp_path / 'runner/commit.json').as_posix()}"
        " --jq .data.createCommitOnBranch.commit.oid",
        # The branch of the pull request starts at that commit.
        "gh api repos/o/r/git/ref/heads/bot/diagrams",
        "gh api --method POST repos/o/r/git/refs -f ref=refs/heads/bot/diagrams"
        " -f sha=c0ffee",
        "gh api --method DELETE repos/o/r/git/refs/heads/bot/diagrams-next",
        "gh pr create --base main --head bot/diagrams --title docs: draw the diagrams"
        f" anew --body-file {(tmp_path / 'runner/body.md').as_posix()}",
        "gh pr merge bot/diagrams --auto --squash",
    ]
    request = json.loads((tmp_path / "request.json").read_text(encoding="utf-8"))
    assert request["variables"]["input"]["branch"]["branchName"] == "bot/diagrams-next"
    assert request["variables"]["input"]["expectedHeadOid"] == "abc1234def"
    body = (tmp_path / "body.md").read_text(encoding="utf-8")
    assert body.startswith("`main` has diagrams that not every reader sees")
    assert summary == (
        "The pull request of the diagrams from bot/diagrams has the commit c0ffee, "
        "and merges itself once every check passes.\n"
    )


@runs_a_copy_of_the_tool
@needs_bash
def test_the_bot_of_main_updates_its_pull_request(tmp_path: Path) -> None:
    # A branch for the commit that a failed run left behind starts again, too.
    result, _, made = run_the_bot_of_main(
        tmp_path, stale=True, open_number="9", exists=True, left=True
    )

    assert result.returncode == 0, result.stdout + result.stderr
    moved = [call for call in made if call.startswith("gh api --method PATCH ")]
    # The head of the open pull request moves once, to the new commit, and never to
    # the commit of main, which would close the pull request.
    assert moved == [
        "gh api --method PATCH repos/o/r/git/refs/heads/bot/diagrams -f sha=c0ffee"
        " -F force=true",
    ]
    # The branch that a failed run left behind is never moved, which GitHub could
    # refuse, but made anew at the commit that was drawn, and removed at the end.
    scratch = [call for call in made if "bot/diagrams-next" in call]
    assert scratch == [
        "gh api repos/o/r/git/ref/heads/bot/diagrams-next",
        "gh api --method DELETE repos/o/r/git/refs/heads/bot/diagrams-next",
        "gh api --method POST repos/o/r/git/refs -f ref=refs/heads/bot/diagrams-next"
        " -f sha=abc1234def",
        "gh api --method DELETE repos/o/r/git/refs/heads/bot/diagrams-next",
    ]
    assert (
        f"gh pr edit 9 --body-file {(tmp_path / 'runner/body.md').as_posix()}" in made
    )
    assert not any(call.startswith("gh pr create") for call in made)
    assert made[-1] == "gh pr merge bot/diagrams --auto --squash"


@runs_a_copy_of_the_tool
@needs_bash
@pytest.mark.parametrize("open_number", ["9", ""])
def test_the_bot_of_main_closes_its_pull_request_once_main_is_fixed(
    tmp_path: Path, open_number: str
) -> None:
    result, summary, made = run_the_bot_of_main(
        tmp_path, stale=False, open_number=open_number
    )

    assert result.returncode == 0, result.stdout + result.stderr
    if open_number:
        assert made[1] == (
            "gh pr close 9 --delete-branch --comment `main` has every diagram as a"
            " picture of its source without this pull request:"
            " https://github.com/o/r/actions/runs/6"
        )
        assert summary == "main is fixed; closed #9.\n"
    else:
        assert len(made) == 1
        assert summary == ""


# gh for the issue of the diagram bot.
GH_ISSUES = """#!/usr/bin/env bash
echo "gh $*" >> "$CALLS"
case "$*" in
  "issue list "*) echo "${ISSUE:-}" ;;
  "issue create "*|"issue edit "*|"issue close "*) ;;
  *) echo "unexpected: gh $*" >&2; exit 1 ;;
esac
"""
REPORT = ("diagrams.yml", "report", "Keep the issue of the diagram bot current")


@needs_bash
@pytest.mark.parametrize(
    ("failed", "issue", "last"),
    [
        (
            "true",
            "",
            "gh issue create --title The diagram bot fails --label maintenance --body ",
        ),
        ("true", "12", "gh issue edit 12 --body "),
        (
            "false",
            "12",
            "gh issue close 12 --comment The diagram bot passes again:"
            " https://github.com/o/r/actions/runs/6",
        ),
        ("false", "", "gh issue list "),
    ],
)
def test_a_failed_run_of_the_bot_keeps_one_issue(
    tmp_path: Path, failed: str, issue: str, last: str
) -> None:
    result, _, _ = run_step(
        workflow_step(*REPORT),
        tmp_path,
        tmp_path,
        {"gh": GH_ISSUES},
        GH_REPO="o/r",
        FAILED=failed,
        ISSUE=issue,
        URL="https://github.com/o/r/actions/runs/6",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    # A body of more than one line takes more than one line of the calls.
    made = (tmp_path / "calls").read_text(encoding="utf-8")
    parts = made.split("\ngh ")
    assert parts[0].startswith(
        'gh issue list --state open --search "The diagram bot fails" in:title'
    )
    assert len(parts) == (1 if last.startswith("gh issue list") else 2)
    assert (parts[0] if len(parts) == 1 else "gh " + parts[-1]).startswith(last)
    if failed == "true":
        assert made.endswith(
            "\n\nThe latest failure: https://github.com/o/r/actions/runs/6\n"
        )
