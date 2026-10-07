"""Tests of the changelog of releases: the text of Unreleased and release-please's list."""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

import blueprint

COMPARE = "https://github.com/Dennis-Otto/demo/compare/v1.2.2...v1.3.0"
PREAMBLE = "# Changelog\n\nAll notable changes, by release.\n\n"
OLDER = "## 1.2.2\n\n### Fixed\n\n- An older fix.\n"
CURATED = "### New\n\n- **Voices:** start a game by voice (#12).\n"
GENERATED = (
    f"## [1.3.0]({COMPARE}) (2026-10-08)\n\n\n### Features\n\n"
    "* start a game by voice ([#12](https://github.com/Dennis-Otto/demo/issues/12))\n"
)


def main_changelog(unreleased: str = CURATED) -> str:
    return f"{PREAMBLE}## Unreleased\n\n{unreleased}\n{OLDER}"


def branch_changelog(main: str, version: str = "1.3.0") -> str:
    """What release-please writes: its section before the first version heading."""
    entry = GENERATED.replace("1.3.0", version)
    index = main.index("\n## 1.2.2")
    return f"{main[:index]}\n\n{entry}\n{main[index + 1 :]}"


def test_the_text_of_unreleased_becomes_the_section_of_the_release() -> None:
    main = main_changelog()
    result = blueprint.release_changelog("1.3.0", main, branch_changelog(main))
    assert result == (
        f"{PREAMBLE}## Unreleased\n\n"
        f"## [1.3.0]({COMPARE}) (2026-10-08)\n\n{CURATED}\n{OLDER}"
    )


def test_without_text_the_section_lists_the_pull_requests() -> None:
    main = main_changelog(unreleased="")
    result = blueprint.release_changelog("1.3.0", main, branch_changelog(main))
    assert "## Unreleased\n\n## [1.3.0]" in result
    assert "### Features\n\n* start a game by voice" in result
    assert result.endswith(OLDER)


def test_the_first_release_keeps_the_preamble_that_release_please_replaces() -> None:
    main = f"{PREAMBLE}## Unreleased\n\n{CURATED}"
    # Without a version heading, release-please writes a new file.
    branch = "# Changelog\n\n## 0.1.0 (2026-10-08)\n\n\n### Features\n\n* the start\n"
    result = blueprint.release_changelog("0.1.0", main, branch)
    assert result == f"{PREAMBLE}## Unreleased\n\n## 0.1.0 (2026-10-08)\n\n{CURATED}"


def test_a_changelog_without_unreleased_gets_the_heading() -> None:
    main = f"{PREAMBLE}{OLDER}"
    result = blueprint.release_changelog("1.3.0", main, branch_changelog(main))
    assert result.startswith(f"{PREAMBLE}## Unreleased\n\n## [1.3.0]")
    assert "* start a game by voice" in result


def test_a_changelog_of_headings_alone_is_written_in_full() -> None:
    branch = "## 0.1.0 (2026-10-08)\n\n* the start\n"
    result = blueprint.release_changelog("0.1.0", "", branch)
    assert result == "## Unreleased\n\n## 0.1.0 (2026-10-08)\n\n* the start\n"


def test_a_prerelease_keeps_the_text_for_the_release() -> None:
    main = main_changelog()
    branch = branch_changelog(main, version="1.3.0-beta.1")
    result = blueprint.release_changelog("1.3.0-beta.1", main, branch)
    assert result.startswith(f"{PREAMBLE}## Unreleased\n\n{CURATED}\n## [1.3.0-beta.1]")
    assert "* start a game by voice" in result


def test_a_branch_without_the_section_stays_as_it_is() -> None:
    main = main_changelog()
    assert blueprint.release_changelog("2.0.0", main, main) == main


def test_writing_the_changelog_again_changes_nothing() -> None:
    main = main_changelog()
    once = blueprint.release_changelog("1.3.0", main, branch_changelog(main))
    assert blueprint.release_changelog("1.3.0", main, once) == once


def test_a_section_of_the_version_on_main_is_replaced() -> None:
    main = f"{PREAMBLE}## Unreleased\n\n{CURATED}\n## v1.3.0\n\n- stale\n\n{OLDER}"
    branch = f"{PREAMBLE}{GENERATED}\n{OLDER}"
    result = blueprint.release_changelog("1.3.0", main, branch)
    assert "stale" not in result
    assert result.count("1.3.0") == 2  # the heading and the comparison


@given(
    st.lists(
        st.text(alphabet="abc xyz-*.#()", min_size=1, max_size=20).filter(
            lambda line: not line.startswith("## ")
        ),
        max_size=6,
    )
)
def test_the_text_of_unreleased_reaches_the_release_once(lines: list[str]) -> None:
    text = "\n".join(lines)
    main = main_changelog(unreleased=f"{text}\n" if text.strip() else "")
    once = blueprint.release_changelog("1.3.0", main, branch_changelog(main))
    assert blueprint.release_changelog("1.3.0", main, once) == once
    release = blueprint.Changelog.parse(once)
    assert release.sections[0] == ("## Unreleased", "\n\n")
    if text.strip():
        assert release.sections[1][1].strip("\n") == text.strip("\n")
    assert once.endswith(OLDER)


def test_the_notes_show_the_text_and_then_every_pull_request() -> None:
    main = main_changelog()
    changelog = blueprint.release_changelog("1.3.0", main, branch_changelog(main))
    notes = blueprint.release_notes("1.3.0", changelog, GENERATED)
    assert notes.startswith(CURATED)
    assert "<summary>Every pull request of this release</summary>" in notes
    assert "### Features\n\n* start a game by voice" in notes
    assert f"[Compare with the previous release]({COMPARE})" in notes
    assert notes.endswith("</details>\n")
    # A second run of the release job leaves the notes as they are.
    assert blueprint.release_notes("1.3.0", changelog, notes) == notes


def test_notes_without_text_are_those_of_release_please() -> None:
    main = main_changelog(unreleased="")
    changelog = blueprint.release_changelog("1.3.0", main, branch_changelog(main))
    assert blueprint.release_notes("1.3.0", changelog, GENERATED) == GENERATED
    assert blueprint.release_notes("9.9.9", changelog, GENERATED) == GENERATED


def test_notes_of_release_please_without_a_heading() -> None:
    changelog = f"{PREAMBLE}## 1.3.0\n\n{CURATED}"
    notes = blueprint.release_notes("1.3.0", changelog, "* a pull request\n")
    assert notes.startswith(CURATED)
    assert "* a pull request" in notes
    assert "Compare" not in notes


def test_the_command_line_writes_the_changelog_and_the_notes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main = main_changelog()
    files = {
        "main.md": main,
        "branch.md": branch_changelog(main),
        "notes.md": GENERATED,
    }
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    paths = {name: str(tmp_path / name) for name in files}

    assert (
        blueprint.main(
            ["changelog", "release", "1.3.0", paths["main.md"], paths["branch.md"]]
        )
        == 0
    )
    changelog = capsys.readouterr().out
    assert changelog == blueprint.release_changelog(
        "1.3.0", main, branch_changelog(main)
    )
    (tmp_path / "release.md").write_text(changelog, encoding="utf-8")
    assert (
        blueprint.main(
            [
                "changelog",
                "notes",
                "1.3.0",
                str(tmp_path / "release.md"),
                paths["notes.md"],
            ]
        )
        == 0
    )
    assert capsys.readouterr().out.startswith(CURATED)


def test_the_command_line_names_a_missing_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = str(tmp_path / "missing.md")
    assert blueprint.main(["changelog", "notes", "1.3.0", missing, missing]) == 2
    assert "missing.md" in capsys.readouterr().err
