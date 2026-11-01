"""The parts of the report of the PR coach about the pull request itself: the release
that it makes and its entry of the changelog, its coverage, its website and the parts
that its workflows add."""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
import unicodedata
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from blueprint.coach import MOST_REPORTS, ReportEntry
from blueprint.coverage_comment import COVERAGE_MARKER, Coverage
from blueprint.github import Api
from blueprint.pr_report import (
    CODE_LINES,
    CODE_WIDTH,
    DRAWN,
    ENTRY_LINES,
    MOST_PAGES,
    QUIET,
    REPORT_BYTES,
    REPORT_LENGTH,
    REPORT_TEXT,
    TABLE_COLUMNS,
    TABLE_ROWS,
    Artifact,
    Releases,
    Website,
    about,
    bump,
    coverage_part,
    newest_artifact,
    pending_release,
    read_report,
    release_part,
    shown_report,
    version_of,
    website_artifact,
    website_part,
    workflow_part,
    workflow_parts,
    wrapped,
)

ROOT = Path(__file__).parents[1]
REPO = "Dennis-Otto/demo"
SHA = "a" * 40
# How release-please releases the blueprint, below 1.0.0.
BLUEPRINT = Releases((0, 12, 0), frozenset({"feat", "fix", "perf", "revert"}), True)


class FakeApi:
    """GitHub with answers by path, and the paths it was asked for; gh run download
    writes the files of downloads for the name of the artifact into its folder."""

    def __init__(
        self,
        answers: dict[str, Any],
        downloads: dict[str, dict[str, bytes]] | None = None,
    ) -> None:
        self.answers = answers
        self.downloads = downloads or {}
        self.asked: list[str] = []

    def __call__(
        self, arguments: Sequence[str], body: str | None
    ) -> subprocess.CompletedProcess[str]:
        if arguments[0] == "run":
            return self.download(list(arguments))
        path = arguments[4].removeprefix(f"repos/{REPO}/")
        self.asked.append(path)
        status, data = (200, self.answers[path]) if path in self.answers else (404, {})
        return subprocess.CompletedProcess(
            arguments, 0, f"HTTP/2.0 {status} X\r\n\r\n{json.dumps(data)}", ""
        )

    def download(self, arguments: list[str]) -> subprocess.CompletedProcess[str]:
        name = arguments[arguments.index("--name") + 1]
        self.asked.append(" ".join(arguments[: arguments.index("--dir")]))
        if name not in self.downloads:
            return subprocess.CompletedProcess(arguments, 1, "", "no artifact")
        folder = Path(arguments[arguments.index("--dir") + 1])
        for file, data in self.downloads[name].items():
            (folder / file).write_bytes(data)
        return subprocess.CompletedProcess(arguments, 0, "", "")


def pull(title: str, body: str = "", number: int = 42) -> dict[str, Any]:
    return {
        "number": number,
        "title": title,
        "body": body,
        "head": {"sha": SHA, "ref": "feat/dark-mode"},
    }


def fragment(*lines: str, name: str = "changelog.d/dark-mode.md") -> dict[str, Any]:
    patch = "\n".join(["@@ -0,0 +1,3 @@", *(f"+{line}" for line in lines)])
    return {"filename": name, "status": "added", "patch": patch}


def no_release() -> tuple[int, tuple[int, int, int]] | None:
    return None


def text_of(
    title: str,
    body: str = "",
    files: Sequence[dict[str, Any]] = (),
    releases: Releases | None = BLUEPRINT,
    pending: tuple[int, tuple[int, int, int]] | None = None,
) -> str:
    part = release_part(pull(title, body), files, releases, lambda: pending)
    assert part is not None
    return part.text


# ---------------------------------------------------------------- the release


def test_the_releases_of_the_blueprint() -> None:
    manifest = json.loads((ROOT / ".release-please-manifest.json").read_text())

    releases = Releases.load(ROOT)

    assert releases is not None
    assert releases.version == version_of(manifest["."])
    assert releases.kinds == {"feat", "fix", "perf", "revert"}
    assert releases.minor_pre_major
    assert not releases.patch_pre_major


@pytest.mark.parametrize(
    ("manifest", "config", "expected"),
    [
        # No release-please.
        (None, None, None),
        ("{", None, None),
        ('["0.1.0"]', None, None),
        ('{".": "1.0.0"}', '["x"]', None),
        # The kinds of change that release-please shows when its config names none.
        ('{".": "1.0.0"}', None, Releases((1, 0, 0))),
        # A prerelease, from which the report names no version.
        ('{".": "1.0.0-beta.1"}', "{}", Releases(None)),
        # Flags at the top of the config, and sections that are no list.
        (
            '{".": "0.3.1"}',
            '{"bump-patch-for-minor-pre-major": true, "changelog-sections": "x"}',
            Releases((0, 3, 1), patch_pre_major=True),
        ),
        (
            '{".": "2.0.0"}',
            '{"packages": {".": {"changelog-sections": [{"type": "feat"}, '
            '{"type": "docs", "hidden": true}, "x"]}}}',
            Releases((2, 0, 0), frozenset({"feat"})),
        ),
    ],
)
def test_the_releases_of_a_repository(
    tmp_path: Path, manifest: str | None, config: str | None, expected: Releases | None
) -> None:
    if manifest is not None:
        (tmp_path / ".release-please-manifest.json").write_text(manifest)
    if config is not None:
        (tmp_path / "release-please-config.json").write_text(config)

    assert Releases.load(tmp_path) == expected


@pytest.mark.parametrize(
    ("releases", "kind", "breaking", "level"),
    [
        (Releases((1, 2, 3)), "feat", False, "minor"),
        (Releases((1, 2, 3)), "fix", False, "patch"),
        (Releases((1, 2, 3)), "docs", False, None),
        (Releases((1, 2, 3)), "docs", True, "major"),
        (Releases((0, 2, 3)), "fix", True, "major"),
        (Releases((0, 2, 3), minor_pre_major=True), "fix", True, "minor"),
        (Releases((1, 2, 3), minor_pre_major=True), "fix", True, "major"),
        (Releases((0, 2, 3), patch_pre_major=True), "feat", False, "patch"),
        (Releases((0, 2, 3), patch_pre_major=True), "perf", False, "patch"),
        (Releases(None, minor_pre_major=True), "feat", True, "major"),
    ],
)
def test_the_part_of_the_version_that_a_change_raises(
    releases: Releases, kind: str, breaking: bool, level: str | None
) -> None:
    assert releases.level(kind, breaking) == level


def test_a_bump_of_each_part() -> None:
    assert bump((1, 2, 3), "patch") == (1, 2, 4)
    assert bump((1, 2, 3), "minor") == (1, 3, 0)
    assert bump((1, 2, 3), "major") == (2, 0, 0)


def test_the_release_pull_request_of_release_please() -> None:
    def release(number: int, title: str, ref: str, repo: str = REPO) -> dict[str, Any]:
        return {
            "number": number,
            "title": title,
            "head": {"ref": ref, "repo": {"full_name": repo}},
        }

    branch = "release-please--branches--main"
    pulls = [
        release(1, "feat: dark mode", "feat/dark-mode"),
        # A fork can name its branch so, but it is no branch of the repository.
        release(2, "chore: release 9.0.0", branch, "fork/demo"),
        release(3, "chore: release the docs", branch),
        release(4, "chore: release 1.0.0-beta.1", branch),
        release(221, "chore(main): release v0.13.0", branch),
    ]
    api = FakeApi({"pulls?state=open&per_page=100&page=1": pulls})

    assert pending_release(Api(runner=api), REPO) == (221, (0, 13, 0))
    assert pending_release(Api(runner=FakeApi({})), REPO) is None


@pytest.mark.parametrize(
    ("title", "body", "pending", "expected"),
    [
        (
            "feat: dark mode",
            "",
            None,
            "📦 Merging this pull request makes the next release **0.13.0**, a minor "
            "release after 0.12.0.",
        ),
        (
            "fix(ui): crash on save",
            "",
            (221, (0, 13, 0)),
            "📦 This pull request goes into the next release, **0.13.0**, which the "
            "release pull request #221 has already.",
        ),
        (
            "feat: dark mode",
            "",
            (221, (0, 12, 1)),
            "📦 Merging this pull request makes the next release **0.13.0**, a minor "
            "release instead of 0.12.1 of #221.",
        ),
        (
            "feat!: drop the old settings",
            "",
            None,
            "📦 Merging this pull request makes the next release **0.13.0**, a minor "
            "release after 0.12.0. It is a breaking change, which makes a minor "
            "release while the version is below 1.0.0.",
        ),
        (
            "docs: the guide",
            "Some text.\r\n\r\nRelease-As: 1.0.0\r\n",
            None,
            "📦 The line `Release-As: 1.0.0` of the description makes the next release "
            "**1.0.0**.",
        ),
        (
            "docs: the guide",
            "",
            None,
            "This pull request releases nothing by itself: a change of the kind `docs` "
            "goes out with the next release that another one makes.",
        ),
    ],
)
def test_the_release_that_a_pull_request_makes(
    title: str,
    body: str,
    pending: tuple[int, tuple[int, int, int]] | None,
    expected: str,
) -> None:
    files = [fragment("### Features", "", "- A dark mode.")]

    text = text_of(title, body, files, pending=pending)

    assert text.startswith(f"#### Release\n\n{expected}\n\n<details>")


def test_a_breaking_change_of_the_description_makes_a_major_release() -> None:
    releases = Releases((1, 2, 3))
    body = "Drops the old settings.\n\nBREAKING CHANGE: the settings move."

    text = text_of("fix: the settings", body, releases=releases)

    assert "**2.0.0**, a major release after 1.2.3. It is a breaking change." in text


def test_a_prerelease_names_no_version() -> None:
    def ask() -> tuple[int, tuple[int, int, int]] | None:
        raise AssertionError("the release pull request says nothing here")

    part = release_part(pull("feat: dark mode"), [], Releases(None), ask)

    assert part is not None
    assert "makes the next release a minor release.\n" in part.text


@pytest.mark.parametrize(
    "title", ["Dark mode", "wip: dark mode", "Feat: dark mode", "feat(UI): x"]
)
def test_a_title_that_fails_its_check_says_nothing_of_the_release(title: str) -> None:
    assert release_part(pull(title), [], BLUEPRINT, no_release) is None


def test_no_release_please_says_nothing_of_the_release() -> None:
    assert release_part(pull("feat: x"), [], None, no_release) is None


def test_a_release_without_an_entry_lists_the_title() -> None:
    part = release_part(pull("fix: x"), [], BLUEPRINT, no_release)

    assert part is not None
    assert part.news
    # It says what the merge does, which a pull request that can't merge doesn't hear.
    assert part.after_merge
    assert part.text.endswith(
        "\n\nIt adds no entry to the changelog, so the notes of the release list its "
        "title."
    )


def test_a_change_that_releases_nothing_is_no_news() -> None:
    part = release_part(pull("ci: faster"), [], BLUEPRINT, no_release)

    assert part is not None
    assert not part.news
    assert "no entry" not in part.text
    # With an entry, it tells what the next release says of it.
    part = release_part(pull("docs: x"), [fragment("- x")], BLUEPRINT, no_release)
    assert part is not None
    assert part.news


def test_the_entry_from_a_fragment_and_the_changelog() -> None:
    files = [
        {"filename": "src/app.py", "status": "modified", "patch": "+print()"},
        {"filename": "changelog.d/old.md", "status": "removed", "patch": "-x"},
        {"filename": "changelog.d/sub/x.md", "status": "added", "patch": "+no"},
        fragment("### Features", "", "- **Dark mode:** for the settings."),
        {
            "filename": "CHANGELOG.md",
            "status": "modified",
            "patch": "@@ -8,3 +8,5 @@\n ## Unreleased\n+\n+### Bug fixes\n+- A fix.\n",
        },
        {"filename": "changelog.d/huge.md", "status": "added"},
    ]

    text = text_of("feat: dark mode", files=files)

    entry = text[text.index("```markdown\n") : text.index("\n```\n")]
    assert entry.splitlines()[1:] == [
        "### Features",
        "",
        "- **Dark mode:** for the settings.",
        "",
        "### Bug fixes",
        "- A fix.",
    ]
    assert "- `changelog.d/huge.md` changes too much for GitHub to show here." in text
    assert "no entry" not in text


def test_a_file_too_large_to_show_is_an_entry() -> None:
    files = [{"filename": "CHANGELOG.md", "status": "modified"}]

    text = text_of("feat: x", files=files)

    assert "<details>" not in text
    assert text.endswith("- `CHANGELOG.md` changes too much for GitHub to show here.")


def test_a_long_entry_is_wrapped_and_cut() -> None:
    words = " ".join(f"word{number}" for number in range(400))
    lines = [f"- {words}", *(f"- {number}" for number in range(ENTRY_LINES))]

    text = text_of("feat: x", files=[fragment(*lines)])

    entry = text[text.index("```markdown\n") : text.index("\n```\n")].splitlines()
    assert len(entry) == 1 + ENTRY_LINES
    assert all(len(line) <= 100 for line in entry)
    assert entry[2].startswith("  word")
    assert re.search(r"\n… and \d+ more lines\.\n", text)


def test_the_entry_shows_only_as_code() -> None:
    lines = [
        "```",
        "- @someone [x](https://evil.example) ````",
        "\x1b[31mred\N{LINE SEPARATOR}",
    ]

    text = text_of("feat: x", files=[fragment(*lines)])

    fence = re.search(r"^(`{3,})markdown$", text, re.MULTILINE)
    assert fence
    assert len(fence[1]) == 5
    assert text.count(fence[1]) == 2
    assert "\x1b" not in text
    assert "\N{LINE SEPARATOR}" not in text


@pytest.mark.parametrize(
    ("lines", "expected"),
    [
        ([""], [""]),
        (
            ["  - nested " + "x " * 60],
            ["  - nested " + "x " * 44 + "x", "    " + "x " * 14 + "x"],
        ),
        (["1. " + "y " * 60], ["1. " + "y " * 48 + "y", "   " + "y " * 10 + "y"]),
        (["plain " * 20], ["plain " * 15 + "plain", "plain " * 3 + "plain"]),
    ],
)
def test_the_lines_of_an_entry_wrap_under_their_item(
    lines: list[str], expected: list[str]
) -> None:
    assert wrapped(lines) == expected


@given(st.lists(st.text()))
def test_every_entry_stays_in_its_block(lines: list[str]) -> None:
    text = text_of("feat: x", files=[fragment(*lines)])

    found = re.search(r"^(`{3,})markdown\n(.*)\n\1$", text, re.MULTILINE | re.DOTALL)
    if found is None:
        # An entry of blank lines alone shows nothing.
        assert "`" not in text.split("\n\n", 2)[-1]
        return
    assert not re.search(rf"^{found[1]}", found[2], re.MULTILINE)
    # No control character but the line breaks between the lines.
    assert not any(
        (unicodedata.category(char) == "Cc" and char != "\n")
        or char in "\N{LINE SEPARATOR}\N{PARAGRAPH SEPARATOR}"
        for char in found[2]
    )


# ---------------------------------------------------------------- coverage


def test_the_coverage_takes_the_place_of_the_coverage_bot() -> None:
    head = Coverage({"src/app.py": (2, 2)})
    base = Coverage({"src/app.py": (1, 2)})

    part = coverage_part(head, base)

    assert part.news
    assert part.replaces == COVERAGE_MARKER
    assert part.text.startswith("#### Coverage\n\n| | Lines | Covered |\n")
    assert "| `src/app.py` | 50.00 % | 100.00 % |" in part.text
    # No file changes its coverage, or main has none to compare with: no news.
    assert not coverage_part(head, head).news
    assert not coverage_part(head, None).news


# ---------------------------------------------------------------- the website


def test_the_website_of_the_blueprint() -> None:
    website = Website.load(ROOT)

    assert website == Website("https://dennis-otto.github.io/repo-blueprint/", True)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (None, None),
        ("site_name: x\n", Website("", False)),
        (
            "site_url: https://x.example/site\nplugins:\n#     - locale: de\n",
            Website("https://x.example/site/", False),
        ),
    ],
)
def test_the_website_of_a_repository(
    tmp_path: Path, text: str | None, expected: Website | None
) -> None:
    if text is not None:
        (tmp_path / "mkdocs.yml").write_text(text)

    assert Website.load(tmp_path) == expected


@pytest.mark.parametrize(
    ("name", "german", "address"),
    [
        ("docs/index.md", True, ""),
        ("docs/guide.md", True, "guide/"),
        ("docs/decisions/README.md", True, "decisions/"),
        ("docs/decisions/0001-x.md", True, "decisions/0001-x/"),
        ("docs/guide.de.md", True, "de/guide/"),
        ("docs/index.de.md", True, "de/"),
        ("docs/guide.de.md", False, "guide.de/"),
    ],
)
def test_the_address_of_a_page(name: str, german: bool, address: str) -> None:
    website = Website("https://x.example/", german)

    assert website.page(name) == f"https://x.example/{address}"


def changed(*names: str, status: str = "modified") -> list[dict[str, Any]]:
    return [{"filename": name, "status": status} for name in names]


def test_the_website_of_a_pull_request() -> None:
    website = Website("https://x.example/", True)
    link = "https://github.com/o/r/actions/runs/7/artifacts/9"
    files = [
        *changed("docs/guide.md", "docs/guide.de.md", "src/app.py"),
        *changed("docs/a b.md", "docs/(x).md", "docs/.hidden.md"),
        *changed("docs/gone.md", status="removed"),
    ]

    part = website_part(files, website, lambda: link)

    assert part is not None
    assert part.news
    assert part.text == (
        "#### Website\n\n"
        f"🌐 [The website of this pull request]({link}), as the check *docs* built "
        "it, stays for 7 days: unzip the artifact `website` into a folder, run "
        "`python3 -m http.server --directory website` and open http://localhost:8000."
        "\n\nThe pages that it changes, at their address after the merge:\n\n"
        "- [`docs/guide.md`](https://x.example/guide/)\n"
        "- [`docs/guide.de.md`](https://x.example/de/guide/)"
    )


def test_a_website_change_without_its_build_or_address() -> None:
    files = changed(*(f"docs/page{number}.md" for number in range(MOST_PAGES + 2)))

    part = website_part(files, Website("", False), lambda: None)

    assert part is not None
    assert "🌐 The check *docs* has kept no build of the website yet" in part.text
    assert "\n- `docs/page0.md`\n" in part.text
    assert part.text.endswith("\n- … and 2 more")


def test_a_change_of_the_website_without_a_page() -> None:
    part = website_part(changed("mkdocs.yml"), Website("", False), lambda: None)

    assert part is not None
    assert "The pages that it changes" not in part.text


def test_no_website_part_without_a_change_of_the_website_or_a_website() -> None:
    def ask() -> str | None:
        raise AssertionError("no artifact to look for")

    website = Website("https://x.example/", False)
    assert website_part(changed("src/app.py"), website, ask) is None
    assert website_part(changed("docs/x.md", status="removed"), website, ask) is None
    assert website_part(changed("docs/guide.md"), None, ask) is None


def test_the_artifact_of_the_website() -> None:
    path = "actions/artifacts?name=website&per_page=100"
    artifacts = [
        {"id": 1, "expired": False, "workflow_run": {"id": 5, "head_sha": "b" * 40}},
        {"id": 2, "expired": True, "workflow_run": {"id": 6, "head_sha": SHA}},
        {"id": 3, "expired": False, "workflow_run": {"id": 7, "head_sha": SHA}},
    ]

    found = website_artifact(
        Api(runner=FakeApi({path: {"artifacts": artifacts}})), REPO, SHA
    )

    assert found == f"https://github.com/{REPO}/actions/runs/7/artifacts/3"
    assert website_artifact(Api(runner=FakeApi({})), REPO, SHA) is None
    assert website_artifact(Api(runner=FakeApi({path: {}})), REPO, SHA) is None


# ---------------------------------------------------------------- the parts of workflows

CARD = ReportEntry("card-size", "The size of the card")
LISTED = "actions/artifacts?name=pr-report-card-size&per_page=100"
LINK = f"https://github.com/{REPO}/actions/runs/12/artifacts/3"


def kept(*artifacts: tuple[int, int, str, int]) -> dict[str, Any]:
    """The artifacts that the API lists, newest first: each run, id, commit and size."""
    return {
        "artifacts": [
            {
                "id": id_,
                "size_in_bytes": size,
                "workflow_run": {"id": run, "head_sha": sha},
            }
            for run, id_, sha, size in artifacts
        ]
    }


def test_the_newest_artifact_of_the_head() -> None:
    listed = kept((10, 1, "b" * 40, 1), (12, 3, SHA, 512), (11, 2, SHA, 9))
    listed["artifacts"].insert(
        1, {"id": 4, "expired": True, "workflow_run": {"id": 13, "head_sha": SHA}}
    )
    api = Api(runner=FakeApi({LISTED: listed}))

    found = newest_artifact(api, REPO, SHA, "pr-report-card-size")

    assert found == Artifact(12, 3, 512)
    assert found.link(REPO) == LINK
    assert newest_artifact(api, REPO, SHA, "pr-report-visual") is None


# A part with every kind of block, and text that would be Markdown, links, mentions
# and HTML, which all show as code.
PART = """# Card size

The card grows by **2 kB**: see [the log](https://evil.example) @someone.
It is still small.

| Module | main | this PR |
| :--- | ---: | :---: |
| `card.js` | 120 kB | 122 kB |
| a \\| b | 1 |
| x | y | z | more |

- one
  - nested
continued
* two
1. three

```js
const fence = "```";
```

<img src="https://evil.example/x.png">
"""

SHOWN = """**`Card size`**

`The card grows by **2 kB**: see [the log](https://evil.example) @someone. It is still small.`

| `Module` | `main` | `this PR` |
| :--- | ---: | :---: |
| `` `card.js` `` | `120 kB` | `122 kB` |
| `a \\| b` | `1` |  |
| `x` | `y` | `z` |

- `one`
  - `nested continued`
- `two`
- `three`

````js
const fence = "```";
````

`<img src="https://evil.example/x.png">`"""


def test_the_markdown_of_a_part_shows_as_data() -> None:
    assert shown_report(PART) == (SHOWN, False)


@pytest.mark.parametrize(
    ("text", "shown"),
    [
        # A row like that of a table, without the row below its head.
        ("| a | b |\nnext", "`| a | b | next`"),
        ("| a |\n| - |", "| `a` |\n| --- |"),
        # A heading closed by its marks, a block of code that never closes, and lines
        # of nothing but control characters.
        ("## Size ##\n\n\n~~~\nx", "**`Size`**\n\n```\nx\n```"),
        ("\x00\t\n\N{LINE SEPARATOR}", ""),
        ("1) a\n   b\n\nc", "- `a b`\n\n`c`"),
        # A mark that ends no heading, code inside a paragraph, which no fence opens,
        # and a fence of tildes, whose language may have backticks after it.
        (
            "# C#\n```a```\n\n~~~ py `x`\ny",
            "**`C#`**\n\n```` ```a``` ````\n\n```py\ny\n```",
        ),
        # A block that GitHub would draw as a diagram or a map shows as code.
        ("```mermaid\nflowchart TB\n```", "```\nflowchart TB\n```"),
        ("~~~ GeoJSON\n{}\n~~~", "```\n{}\n```"),
        # An item deeper than the one before it, or than none, as GitHub nests it.
        ("para\n    - deep", "`para`\n\n- `deep`"),
        ("- a\n      - c\n  - b", "- `a`\n  - `c`\n  - `b`"),
    ],
)
def test_the_blocks_of_a_part(text: str, shown: str) -> None:
    assert shown_report(text) == (shown, False)


LONG_LINES = {
    "fence": "```" + "a" * 60000 + "`",
    "heading": "# a" + " " * 60000 + "b",
    "row": "|" + "-" * 60000,
    "delimiter": "| " + "- " * 30000,
    "item": " " * 60000 + "x",
    "table": "|" + " |" * 30000 + "\n|" + "-|" * 30000,
}


@pytest.mark.parametrize("kind", LONG_LINES)
def test_a_long_line_of_a_fork_takes_no_long_time(kind: str) -> None:
    # Each pattern reads a line in one pass; one that tried again at every place
    # would take minutes for a line of the 64 kB of a report.md.
    started = time.perf_counter()

    shown_report(LONG_LINES[kind])

    assert time.perf_counter() - started < 5


def test_a_part_shows_so_much_of_its_tables_and_code() -> None:
    columns = "|" + "|".join(f"c{n}" for n in range(TABLE_COLUMNS + 2)) + "|"
    rows = "\n".join(f"| {n} |" for n in range(TABLE_ROWS + 3))
    lines = "\n".join(["x" * (CODE_WIDTH + 5)] * (CODE_LINES + 2))
    text, more = shown_report(f"{columns}\n|---|\n{rows}\n\n```\n{lines}\n```")

    assert not more
    head = text.split("\n", 1)[0]
    assert head.count("`c") == TABLE_COLUMNS
    assert text.count("\n| `") == TABLE_ROWS
    assert "\n\n… and 3 more rows.\n\n```\n" in text
    assert f"\n{'x' * CODE_WIDTH}\n" in text
    assert text.count("x" * CODE_WIDTH) == CODE_LINES
    assert text.endswith("\n```\n… and 2 more lines.")


def test_a_long_part_shows_what_fits() -> None:
    text, more = shown_report("\n\n".join(["word " * 150] * 20))

    assert more
    assert len(text) <= REPORT_LENGTH
    paragraph = "`" + ("word " * 150).strip() + "`"
    assert text.count(paragraph) == (REPORT_LENGTH + 2) // (len(paragraph) + 2)


# The lines that the report may show of a part: code on a line of its own, as an item
# of a list or bold, rows of a table whose cells are code, and the notes of a cut.
SPAN = r"(?P<m>`+)( ?)(?P<t>[^\n]*?)\2(?P=m)"


def is_code(text: str) -> bool:
    found = re.fullmatch(SPAN, text)
    return found is not None and len(found["m"]) not in {
        len(run) for run in re.findall(r"`+", found["t"])
    }


def is_row(line: str) -> bool:
    if not (line.startswith("| ") and line.endswith(" |")):
        return False
    values = re.split(r"(?<!\\) \| ", line[2:-2])
    return all(
        not value
        or (is_code(value.replace("\\|", "|")) and "|" not in value.replace("\\|", ""))
        for value in values
    )


def assert_data(text: str) -> None:
    lines = text.split("\n") if text else []
    index = 0
    while index < len(lines):
        line = lines[index]
        opening = re.fullmatch(r"(`{3,})([A-Za-z0-9+-]*)", line)
        if opening:
            assert opening[2].lower() not in DRAWN, line
            end = lines.index(opening[1], index + 1)
            assert not any(opening[1] in inner for inner in lines[index + 1 : end])
            index = end + 1
            continue
        assert (
            not line
            or is_code(line)
            or (line.startswith("**") and line.endswith("**") and is_code(line[2:-2]))
            or (
                bool(re.fullmatch(r"(?: {2}){0,2}- (.+)", line))
                and is_code(line.lstrip(" ")[2:])
            )
            or is_row(line)
            or bool(re.fullmatch(r"\| (?::?---:? \| )*:?---:? \|", line))
            or bool(re.fullmatch(r"… and \d+ more (?:rows|lines)\.", line))
        ), line
        index += 1
    assert not any(
        (unicodedata.category(char) == "Cc" and char != "\n")
        or char in "\N{LINE SEPARATOR}\N{PARAGRAPH SEPARATOR}"
        for char in text
    )


MARKDOWN = st.sampled_from(
    [
        "| a | b |",
        "| --- | :-: |",
        "|x\\|`|`y|",
        "```",
        "~~~",
        "````py",
        "```mermaid",
        "~~~ math",
        "- item",
        "    * deep",
        "# head",
        "",
        "1. x",
        "<!-- quiet -->",
        "[a](https://evil.example) @me",
    ]
)


@given(st.lists(st.one_of(st.text(), MARKDOWN)))
def test_no_text_of_a_part_leaves_its_code(lines: list[str]) -> None:
    text, _ = shown_report("\n".join(lines))

    assert_data(text)


def test_the_part_of_a_workflow() -> None:
    entry = ReportEntry(
        "card-size", "Card size", "What the card weighs.", "<!-- size -->"
    )
    part = workflow_part(entry, REPO, Artifact(12, 3), "Grows.")

    assert part is not None
    assert part.text == (
        "#### Card size\n\nWhat the card weighs.\n\n`Grows.`\n\n"
        f"<sub>From the artifact [`pr-report-card-size`]({LINK}).</sub>"
    )
    assert part.news
    assert part.replaces == "<!-- size -->"


def test_a_quiet_part_is_no_news() -> None:
    part = workflow_part(CARD, REPO, Artifact(12, 3), f"{QUIET}\r\nThe same size.")

    assert part is not None
    assert not part.news
    assert "\n\n`The same size.`\n\n" in part.text
    # A part that says nothing, quiet or not, is none.
    assert workflow_part(CARD, REPO, Artifact(12, 3), QUIET) is None
    assert workflow_part(CARD, REPO, Artifact(12, 3), " \n") is None


def test_a_part_that_holds_more_says_so() -> None:
    part = workflow_part(CARD, REPO, Artifact(12, 3), "word\n\n" * 2000)

    assert part is not None
    assert part.text.endswith(
        f"[`pr-report-card-size`]({LINK}), which holds more.</sub>"
    )


def test_a_part_that_the_coach_cannot_read() -> None:
    # Neither says what an older comment of its workflow said, which therefore stays.
    card = ReportEntry("card-size", "The size of the card", replaces="<!-- size -->")
    large = workflow_part(card, REPO, Artifact(12, 3, REPORT_BYTES + 2048), None)
    unread = workflow_part(card, REPO, Artifact(12, 3, 10), None)

    assert large is not None
    assert large.news
    assert large.text == (
        f"#### The size of the card\n\nThe artifact [`pr-report-card-size`]({LINK}) "
        f"is {REPORT_BYTES // 1024 + 2} kB, more than the {REPORT_BYTES // 1024} kB "
        "that the PR coach reads; let its workflow keep `report.md` alone in it."
    )
    assert unread is not None
    assert not unread.news
    assert "couldn't read `report.md` of the artifact" in unread.text
    assert large.replaces == unread.replaces == ""


def test_the_report_of_an_artifact() -> None:
    name = "pr-report-card-size"
    downloads = {name: {"report.md": "Größer".encode() + b"\xff" + b"x" * REPORT_TEXT}}
    api = FakeApi({}, downloads)

    text = read_report(Api(runner=api), REPO, name, Artifact(12, 3))

    assert text is not None
    assert text.startswith("Größer\N{REPLACEMENT CHARACTER}x")
    assert len(text.encode()) == REPORT_TEXT + 2
    assert api.asked == [f"run download 12 --repo {REPO} --name {name}"]


def test_a_report_after_a_byte_order_mark_is_still_quiet() -> None:
    # Some editors on Windows begin a file of UTF-8 with one.
    name = "pr-report-card-size"
    downloads = {name: {"report.md": f"\ufeff{QUIET}\nThe same.".encode()}}

    text = read_report(Api(runner=FakeApi({}, downloads)), REPO, name, Artifact(12, 3))

    assert text == f"{QUIET}\nThe same."
    part = workflow_part(CARD, REPO, Artifact(12, 3), text)
    assert part is not None
    assert not part.news


@pytest.mark.parametrize(
    "downloads",
    [
        # gh can't download it, or it holds no report.md, or a folder by that name.
        {},
        {"pr-report-card-size": {"other.md": b"x"}},
    ],
)
def test_an_artifact_without_a_report(downloads: dict[str, dict[str, bytes]]) -> None:
    api = Api(runner=FakeApi({}, downloads))

    assert read_report(api, REPO, "pr-report-card-size", Artifact(12, 3)) is None


def test_a_report_that_is_a_link_is_none(tmp_path: Path) -> None:
    target = tmp_path / "secret"
    target.write_text("secret", encoding="utf-8")

    def link(
        arguments: Sequence[str], body: str | None
    ) -> subprocess.CompletedProcess[str]:
        folder = Path(arguments[list(arguments).index("--dir") + 1])
        try:
            os.symlink(target, folder / "report.md")
        except OSError:  # pragma: no cover - Windows without the right to make links
            pytest.skip("no symbolic links here")
        return subprocess.CompletedProcess(arguments, 0, "", "")

    assert read_report(Api(runner=link), REPO, "pr-report-x", Artifact(12, 3)) is None


def test_the_parts_of_the_workflows_of_a_pull_request() -> None:
    entries = [ReportEntry(f"p{n}", f"Part {n}") for n in range(MOST_REPORTS + 1)]
    listed = {
        f"actions/artifacts?name=pr-report-p{n}&per_page=100": kept(
            (20 + n, 30 + n, SHA, size)
        )
        for n, size in [(0, 10), (1, REPORT_BYTES + 1), (2, 10), (3, 10), (5, 10)]
    }
    downloads = {
        "pr-report-p0": {"report.md": b"First."},
        "pr-report-p3": {"report.md": b""},
    }
    api = FakeApi(listed, downloads)

    parts = workflow_parts(Api(runner=api), REPO, SHA, entries)

    # p0 has its report, p1 is too large to download, p2 couldn't be downloaded, p3
    # says nothing, p4 kept no artifact, and p5 is one more than a catalog may declare.
    assert [part.text.split("\n", 1)[0] for part in parts] == [
        "#### Part 0",
        "#### Part 1",
        "#### Part 2",
    ]
    assert [part.news for part in parts] == [True, True, False]
    downloaded = [asked for asked in api.asked if asked.startswith("run download")]
    assert downloaded == [
        f"run download 20 --repo {REPO} --name pr-report-p0",
        f"run download 22 --repo {REPO} --name pr-report-p2",
        f"run download 23 --repo {REPO} --name pr-report-p3",
    ]
    assert not any("pr-report-p5" in asked for asked in api.asked)


# ---------------------------------------------------------------- the parts


def test_the_parts_of_a_pull_request() -> None:
    files = [fragment("### Features", "- x"), *changed("docs/guide.md")]
    api = FakeApi(
        {
            "pulls/42/files?per_page=100&page=1": files,
            "pulls?state=open&per_page=100&page=1": [],
            "actions/artifacts?name=website&per_page=100": {"artifacts": []},
            LISTED: kept((12, 3, SHA, 10)),
        },
        {"pr-report-card-size": {"report.md": b"Grows."}},
    )
    coverage = (Coverage({"a.py": (1, 1)}), None)

    parts = about(
        Api(runner=api), REPO, pull("feat: dark mode"), ROOT, coverage, [CARD]
    )

    # The parts of the workflows follow those of the coach.
    assert [part.text.split("\n", 1)[0] for part in parts] == [
        "#### Release",
        "#### Coverage",
        "#### Website",
        "#### The size of the card",
    ]
    assert about(Api(runner=api), REPO, pull("Dark mode"), ROOT) == [parts[2]]
