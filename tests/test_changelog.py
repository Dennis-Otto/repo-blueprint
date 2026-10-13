"""Tests of the changelog of releases: the text of Unreleased and release-please's list."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from blueprint import cli
from blueprint.changelog import (
    KINDS,
    Changelog,
    Fragment,
    FragmentError,
    add_unreleased,
    beta_notes,
    fragment_problems,
    known_headings,
    merge_headings,
    read_fragments,
    release_changelog,
    release_notes,
    released_fragments,
    version_heading,
)

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
    result = release_changelog("1.3.0", main, branch_changelog(main))
    assert result == (
        f"{PREAMBLE}## Unreleased\n\n"
        f"## [1.3.0]({COMPARE}) (2026-10-08)\n\n{CURATED}\n{OLDER}"
    )


def test_without_text_the_section_lists_the_pull_requests() -> None:
    main = main_changelog(unreleased="")
    result = release_changelog("1.3.0", main, branch_changelog(main))
    assert "## Unreleased\n\n## [1.3.0]" in result
    assert "### Features\n\n* start a game by voice" in result
    assert result.endswith(OLDER)


def test_the_first_release_keeps_the_preamble_that_release_please_replaces() -> None:
    main = f"{PREAMBLE}## Unreleased\n\n{CURATED}"
    # Without a version heading, release-please writes a new file.
    branch = "# Changelog\n\n## 0.1.0 (2026-10-08)\n\n\n### Features\n\n* the start\n"
    result = release_changelog("0.1.0", main, branch)
    assert result == f"{PREAMBLE}## Unreleased\n\n## 0.1.0 (2026-10-08)\n\n{CURATED}"


def test_a_changelog_without_unreleased_gets_the_heading() -> None:
    main = f"{PREAMBLE}{OLDER}"
    result = release_changelog("1.3.0", main, branch_changelog(main))
    assert result.startswith(f"{PREAMBLE}## Unreleased\n\n## [1.3.0]")
    assert "* start a game by voice" in result


def test_a_changelog_of_headings_alone_is_written_in_full() -> None:
    branch = "## 0.1.0 (2026-10-08)\n\n* the start\n"
    result = release_changelog("0.1.0", "", branch)
    assert result == "## Unreleased\n\n## 0.1.0 (2026-10-08)\n\n* the start\n"


def test_a_prerelease_keeps_the_text_for_the_release() -> None:
    main = main_changelog()
    branch = branch_changelog(main, version="1.3.0-beta.1")
    result = release_changelog("1.3.0-beta.1", main, branch)
    assert result.startswith(f"{PREAMBLE}## Unreleased\n\n{CURATED}\n## [1.3.0-beta.1]")
    assert "* start a game by voice" in result


def test_a_branch_without_the_section_stays_as_it_is() -> None:
    main = main_changelog()
    assert release_changelog("2.0.0", main, main) == main


def test_writing_the_changelog_again_changes_nothing() -> None:
    main = main_changelog()
    once = release_changelog("1.3.0", main, branch_changelog(main))
    assert release_changelog("1.3.0", main, once) == once


def test_a_section_of_the_version_on_main_is_replaced() -> None:
    main = f"{PREAMBLE}## Unreleased\n\n{CURATED}\n## v1.3.0\n\n- stale\n\n{OLDER}"
    branch = f"{PREAMBLE}{GENERATED}\n{OLDER}"
    result = release_changelog("1.3.0", main, branch)
    assert "stale" not in result
    assert result.count("1.3.0") == 2  # the heading and the comparison


@given(
    st.lists(
        st.text(alphabet="abc xyz-*.#()", min_size=1, max_size=20).filter(
            lambda line: not line.startswith(("## ", "### "))
        ),
        max_size=6,
    )
)
def test_the_text_of_unreleased_reaches_the_release_once(lines: list[str]) -> None:
    text = "\n".join(lines)
    main = main_changelog(unreleased=f"{text}\n" if text.strip() else "")
    once = release_changelog("1.3.0", main, branch_changelog(main))
    assert release_changelog("1.3.0", main, once) == once
    release = Changelog.parse(once)
    assert release.sections[0] == ("## Unreleased", "\n\n")
    if text.strip():
        assert release.sections[1][1].strip("\n") == text.strip("\n")
    assert once.endswith(OLDER)


def test_a_kind_of_change_that_two_pull_requests_start_is_one_heading() -> None:
    unreleased = (
        "### Features\n\n- **Voices:** start a game by voice (#12).\n\n"
        "### Bug fixes\n\n- A fix (#13).\n\n"
        "### Features\n\n- **Cards:** a new card (#14).\n"
    )
    main = main_changelog(unreleased=unreleased)
    result = release_changelog("1.3.0", main, branch_changelog(main))

    assert result.count("### Features") == 1
    assert (
        "### Features\n\n- **Voices:** start a game by voice (#12).\n"
        "- **Cards:** a new card (#14).\n\n### Bug fixes\n\n- A fix (#13).\n\n## 1.2.2"
    ) in result
    assert release_changelog("1.3.0", main, result) == result


def test_merged_headings_keep_an_introduction_and_paragraphs() -> None:
    text = (
        "A word first.\n\n### Notes\n\nA paragraph.\n\n"
        "### Empty\n\n### Notes\n\nAnother one.\n\n### Empty\n"
    )

    assert merge_headings(text) == (
        "A word first.\n\n### Notes\n\nA paragraph.\n\nAnother one.\n\n### Empty\n"
    )


def test_a_beta_shows_each_kind_of_change_once() -> None:
    unreleased = "### Features\n\n- One (#1).\n\n### Features\n\n- Two (#2).\n"
    notes = beta_notes("1.3.0-beta.1", main_changelog(unreleased=unreleased))

    assert "### Features\n\n- One (#1).\n- Two (#2).\n" in notes


def test_the_notes_show_the_text_and_then_every_pull_request() -> None:
    main = main_changelog()
    changelog = release_changelog("1.3.0", main, branch_changelog(main))
    notes = release_notes("1.3.0", changelog, GENERATED)
    assert notes.startswith(CURATED)
    assert "\n## Every pull request of this release\n\n### Features\n" in notes
    assert "### Features\n\n* start a game by voice" in notes
    assert notes.endswith(f"[Compare with the previous release]({COMPARE})\n")
    # A second run of the release job leaves the notes as they are.
    assert release_notes("1.3.0", changelog, notes) == notes


def test_notes_without_text_are_those_of_release_please() -> None:
    main = main_changelog(unreleased="")
    changelog = release_changelog("1.3.0", main, branch_changelog(main))
    assert release_notes("1.3.0", changelog, GENERATED) == GENERATED
    assert release_notes("9.9.9", changelog, GENERATED) == GENERATED


def test_notes_of_release_please_without_a_heading() -> None:
    changelog = f"{PREAMBLE}## 1.3.0\n\n{CURATED}"
    notes = release_notes("1.3.0", changelog, "* a pull request\n")
    assert notes.startswith(CURATED)
    assert "* a pull request" in notes
    assert "Compare" not in notes


def test_the_command_line_writes_the_changelog_and_the_notes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Without changelog.d/ in the folder, the release has no fragments.
    monkeypatch.chdir(tmp_path)
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
        cli.main(
            ["changelog", "release", "1.3.0", paths["main.md"], paths["branch.md"]]
        )
        == 0
    )
    changelog = capsys.readouterr().out
    assert changelog == release_changelog("1.3.0", main, branch_changelog(main))
    (tmp_path / "release.md").write_text(changelog, encoding="utf-8")
    assert (
        cli.main(
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
    assert cli.main(["changelog", "notes", "1.3.0", missing, missing]) == 2
    assert "missing.md" in capsys.readouterr().err


def test_a_bot_adds_an_entry_under_its_heading() -> None:
    main = main_changelog(unreleased="### Changed\n\n- a\n\n### Fixed\n\n- b\n")
    result = add_unreleased(main, "Changed", "- Supports Nextcloud 36.")
    assert (
        "### Changed\n\n- a\n- Supports Nextcloud 36.\n\n### Fixed\n\n- b\n" in result
    )
    assert result.endswith(OLDER)
    # A second run adds nothing.
    assert add_unreleased(result, "Changed", "- Supports Nextcloud 36.") == result


def test_a_bot_adds_the_heading_and_unreleased_when_they_are_missing() -> None:
    fixed = main_changelog(unreleased="### Fixed\n\n- b\n")
    assert "- b\n\n### Changed\n\n- c\n\n## 1.2.2" in add_unreleased(
        fixed, "Changed", "- c"
    )
    empty = main_changelog(unreleased="")
    assert "## Unreleased\n\n### Changed\n\n- c\n\n## 1.2.2" in add_unreleased(
        empty, "Changed", "- c"
    )
    heading_alone = main_changelog(unreleased="### Changed\n")
    assert "## Unreleased\n\n### Changed\n\n- c\n\n## 1.2.2" in add_unreleased(
        heading_alone, "Changed", "- c"
    )
    without = f"{PREAMBLE}{OLDER}"
    assert add_unreleased(without, "Changed", "- c") == (
        f"{PREAMBLE}## Unreleased\n\n### Changed\n\n- c\n\n{OLDER}"
    )


def test_the_command_line_adds_an_entry(tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(main_changelog(unreleased=""), encoding="utf-8")

    assert cli.main(["unreleased", "Changed", "- c", "--file", str(changelog)]) == 0
    assert "### Changed\n\n- c\n" in changelog.read_text(encoding="utf-8")
    assert (
        cli.main(["unreleased", "Changed", "- c", "--file", str(tmp_path / "x")]) == 2
    )


def test_a_beta_shows_what_main_holds() -> None:
    notes = beta_notes("1.3.0-beta.2", main_changelog())

    assert notes.startswith("A beta of the next release, 1.3.0, ")
    assert CURATED.strip() in notes
    assert notes.endswith("\n")


def test_a_beta_without_text_says_so() -> None:
    notes = beta_notes("1.3.0-beta.1", main_changelog(unreleased=""))

    assert "not described yet" in notes
    assert beta_notes("1.3.0-beta.1", PREAMBLE) == notes


def test_the_command_line_writes_the_notes_of_a_beta(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(main_changelog(), encoding="utf-8")

    assert cli.main(["beta", "1.3.0-beta.1", "--file", str(changelog)]) == 0

    assert capsys.readouterr().out == beta_notes("1.3.0-beta.1", main_changelog())


# Fragments: a file of its own in changelog.d/ for each pull request, which conflicts
# with nothing; the release takes them in with the text of Unreleased.

FEATURE = "### Features\n\n- **Cards:** a new card (#14).\n"
FIX = "### Bug fixes\n\n- **Token:** stays secret (#15).\n"


def fragment(name: str, text: str) -> Fragment:
    return Fragment(f"changelog.d/{name}", text)


def section_of(changelog: str, version: str = "1.3.0") -> str:
    """The text of the section of the version, without the blank lines around it."""
    log = Changelog.parse(changelog)
    found = log.find(version_heading(version))
    assert found is not None
    return log.sections[found][1].strip("\n")


def test_the_fragments_join_the_text_of_unreleased_in_the_section() -> None:
    main = main_changelog()
    fragments = [
        fragment("a-cards.md", f"{FEATURE}\n### Bug fixes\n\n- A fix of a (#16).\n"),
        fragment("b-token.md", FIX),
        fragment("c-voices.md", "### New\n\n- **Voices:** in German too (#17).\n"),
    ]

    result = release_changelog("1.3.0", main, branch_changelog(main), fragments)

    # The headings of Unreleased first, then the kinds that only the fragments bring,
    # each kind with the entries of the fragments by their names.
    assert section_of(result) == (
        "### New\n\n- **Voices:** start a game by voice (#12).\n"
        "- **Voices:** in German too (#17).\n\n"
        "### Features\n\n- **Cards:** a new card (#14).\n\n"
        "### Bug fixes\n\n- A fix of a (#16).\n- **Token:** stays secret (#15)."
    )
    assert result.startswith(f"{PREAMBLE}## Unreleased\n\n## [1.3.0]")
    assert result.endswith(OLDER)
    # A second run of the release bot changes nothing.
    assert release_changelog("1.3.0", main, result, fragments) == result
    assert released_fragments("1.3.0", result, fragments) == [
        "changelog.d/a-cards.md",
        "changelog.d/b-token.md",
        "changelog.d/c-voices.md",
    ]


def test_fragments_alone_list_the_kinds_of_change_in_their_order() -> None:
    main = main_changelog(unreleased="")
    fragments = [
        fragment("a-fix.md", "### Fixed\n\n- First fix.\n"),
        fragment("b-security.md", "### Security\n\n- A secret.\n"),
        fragment("c-added.md", "### Added\n\n- An addition.\n"),
        fragment("d-fix.md", "### Fixed\n\n- Second fix.\n"),
    ]

    result = release_changelog("1.3.0", main, branch_changelog(main), fragments)

    assert section_of(result) == (
        "### Added\n\n- An addition.\n\n"
        "### Fixed\n\n- First fix.\n- Second fix.\n\n"
        "### Security\n\n- A secret."
    )
    # Not the list of release-please, which only a release without text shows.
    assert "start a game by voice" not in result


def test_a_prerelease_leaves_the_fragments_for_the_release() -> None:
    main = main_changelog()
    branch = branch_changelog(main, version="1.3.0-beta.1")
    fragments = [fragment("b-token.md", FIX)]

    result = release_changelog("1.3.0-beta.1", main, branch, fragments)

    assert result.startswith(f"{PREAMBLE}## Unreleased\n\n{CURATED}\n## [1.3.0-beta.1]")
    assert "stays secret" not in result
    assert released_fragments("1.3.0-beta.1", branch, fragments) == []


def test_no_fragment_leaves_before_release_please_writes_the_section() -> None:
    main = main_changelog()
    fragments = [fragment("b-token.md", FIX)]

    assert release_changelog("2.0.0", main, main, fragments) == main
    assert released_fragments("2.0.0", main, fragments) == []


@given(
    st.lists(
        st.tuples(
            st.sampled_from(KINDS),
            st.lists(st.text(alphabet="abcxyz ", min_size=1, max_size=8), min_size=1),
        ),
        max_size=6,
    )
)
def test_every_entry_of_the_fragments_reaches_the_release_once(
    contents: list[tuple[str, list[str]]],
) -> None:
    main = main_changelog()
    fragments = [
        fragment(
            f"f{number}.md",
            f"### {kind}\n\n"
            + "".join(
                f"- {number}.{index} {entry}\n" for index, entry in enumerate(entries)
            ),
        )
        for number, (kind, entries) in enumerate(contents)
    ]

    once = release_changelog("1.3.0", main, branch_changelog(main), fragments)

    section = section_of(once)
    for number, (_, entries) in enumerate(contents):
        for index in range(len(entries)):
            assert section.count(f"- {number}.{index} ") == 1
    assert CURATED.strip() in section
    assert Changelog.parse(once).sections[0] == ("## Unreleased", "\n\n")
    assert release_changelog("1.3.0", main, once, fragments) == once
    assert len(released_fragments("1.3.0", once, fragments)) == len(fragments)


def test_a_beta_shows_the_fragments_too() -> None:
    notes = beta_notes("1.3.0-beta.1", main_changelog(), [fragment("b-token.md", FIX)])

    assert f"{CURATED}\n{FIX}" in notes


@pytest.mark.parametrize(
    ("name", "text", "problem"),
    [
        # A name that a release or the check might read differently.
        (
            "fix token.md",
            FIX,
            "changelog.d/fix token.md: is no fragment. Name a fragment with letters, "
            "digits, dots, dashes and underscores, ending in .md, such as "
            "changelog.d/dark-mode.md.",
        ),
        ("notes.txt", FIX, "changelog.d/notes.txt: is no fragment."),
        ("empty.md", " \n\n", "changelog.d/empty.md: says nothing."),
        (
            "early.md",
            f"The token stays secret.\n\n{FIX}",
            "changelog.d/early.md: starts with `The token stays secret.` outside a "
            "heading.",
        ),
        (
            "section.md",
            f"{FIX}\n## 1.4.0\n\n- More.\n",
            "changelog.d/section.md: has the heading `## 1.4.0`, which would start a "
            "section of the changelog of its own.",
        ),
        (
            "typo.md",
            "### Fixes\n\n- A fix.\n",
            "changelog.d/typo.md: `### Fixes` is no kind of change of the changelog. "
            "Did you mean `### Fixed`? The kinds: Breaking changes, Features, Added, "
            "Changes, Changed, Deprecated, Removed, Bug fixes, Fixed, Performance, "
            "Security, New.",
        ),
        ("case.md", "### bug fixes\n\n- A fix.\n", "Did you mean `### Bug fixes`?"),
        (
            "unknown.md",
            "### Zebras\n\n- A zebra.\n",
            "changelog.d/unknown.md: `### Zebras` is no kind of change of the "
            "changelog. The kinds: Breaking changes,",
        ),
        (
            "bare.md",
            f"### Features\n\n{FIX}",
            "changelog.d/bare.md: `### Features` has no entry. Write one below it, or "
            "remove the heading.",
        ),
        # Text of the fragment stays code on one line, cut to length.
        (
            "long.md",
            "### " + "`x` " * 30 + "\n\n- A fix.\n",
            "changelog.d/long.md: `### 'x' 'x' 'x' 'x' 'x' 'x' 'x' 'x' 'x' 'x' 'x' "
            "'x' 'x' 'x'…` is no kind",
        ),
    ],
)
def test_a_fragment_that_a_release_cannot_take_in_is_named_with_its_fix(
    name: str, text: str, problem: str
) -> None:
    main = main_changelog()
    problems = fragment_problems([fragment("good.md", FIX), fragment(name, text)], main)

    assert len(problems) == 1
    assert problem in problems[0]
    with pytest.raises(FragmentError) as raised:
        release_changelog("1.3.0", main, branch_changelog(main), [fragment(name, text)])
    assert raised.value.problems == problems
    assert str(raised.value) == problems[0]
    with pytest.raises(FragmentError):
        beta_notes("1.3.0-beta.1", main, [fragment(name, text)])


def test_a_fragment_takes_the_headings_that_the_changelog_has() -> None:
    project = fragment("voices.md", "### New\n\n- Voices.\n")

    # The changelog of the tests has "### New" and "### Fixed"; a new one has none.
    assert known_headings(main_changelog()) == [*KINDS, "New"]
    assert fragment_problems([project], main_changelog()) == []
    assert "is no kind of change" in fragment_problems([project], PREAMBLE)[0]


def test_the_fragments_are_read_by_their_names(tmp_path: Path) -> None:
    folder = tmp_path / "changelog.d"
    folder.mkdir()
    (folder / ".gitkeep").touch()
    (folder / "b-token.md").write_text(FIX, encoding="utf-8")
    (folder / "a-cards.md").write_text(FEATURE, encoding="utf-8")
    (folder / "sub").mkdir()

    # A folder in it counts, so that the check names it.
    assert read_fragments(folder) == [
        fragment("a-cards.md", FEATURE),
        fragment("b-token.md", FIX),
        fragment("sub", ""),
    ]
    assert read_fragments(tmp_path / "missing") == []


def write_fragments(folder: Path, **fragments: str) -> None:
    folder.mkdir(parents=True)
    (folder / ".gitkeep").touch()
    for name, text in fragments.items():
        (folder / f"{name}.md").write_text(text, encoding="utf-8")


def test_the_command_line_writes_the_release_and_the_fragments_it_takes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # In the root of the repository, with changelog.d/ next to CHANGELOG.md.
    monkeypatch.chdir(tmp_path)
    main = main_changelog()
    write_fragments(tmp_path / "changelog.d", **{"b-token": FIX, "a-cards": FEATURE})
    Path("main.md").write_text(main, encoding="utf-8")
    for version in ("1.3.0", "1.3.0-beta.1"):
        Path(f"{version}.md").write_text(
            branch_changelog(main, version=version), encoding="utf-8"
        )

    arguments = ["changelog", "release", "1.3.0", "main.md", "1.3.0.md"]
    assert cli.main([*arguments, "--taken", "taken.txt"]) == 0
    expected = release_changelog(
        "1.3.0",
        main,
        branch_changelog(main),
        [fragment("a-cards.md", FEATURE), fragment("b-token.md", FIX)],
    )
    assert capsys.readouterr().out == expected
    assert Path("taken.txt").read_bytes() == (
        b"changelog.d/a-cards.md\nchangelog.d/b-token.md\n"
    )
    # A prerelease takes none, and without --taken nothing is written.
    beta = ["changelog", "release", "1.3.0-beta.1", "main.md", "1.3.0-beta.1.md"]
    assert cli.main([*beta, "--taken", "taken.txt"]) == 0
    assert "stays secret" not in capsys.readouterr().out
    assert Path("taken.txt").read_text(encoding="utf-8") == ""
    assert cli.main([*arguments, "--fragments", "elsewhere"]) == 0
    assert capsys.readouterr().out == release_changelog(
        "1.3.0", main, branch_changelog(main)
    )


def test_the_command_line_stops_a_release_at_a_fragment_with_a_problem(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "changelog.d"
    write_fragments(folder, typo="### Fixes\n\n- A fix.\n", empty="")
    main = tmp_path / "main.md"
    main.write_text(main_changelog(), encoding="utf-8")
    branch = tmp_path / "branch.md"
    branch.write_text(branch_changelog(main_changelog()), encoding="utf-8")
    taken = tmp_path / "taken.txt"

    code = cli.main(
        [
            "changelog",
            "release",
            "1.3.0",
            str(main),
            str(branch),
            "--fragments",
            str(folder),
            "--taken",
            str(taken),
        ]
    )

    out, err = capsys.readouterr()
    assert code == 1
    assert out == ""
    assert err.splitlines() == [
        "blueprint.py: changelog.d/empty.md: says nothing. Write what changes for "
        "users below a heading such as `### Features` or `### Bug fixes`.",
        "blueprint.py: changelog.d/typo.md: `### Fixes` is no kind of change of the "
        "changelog. Did you mean `### Fixed`? The kinds: Breaking changes, Features, "
        "Added, Changes, Changed, Deprecated, Removed, Bug fixes, Fixed, "
        "Performance, Security, New.",
    ]
    assert not taken.exists()


def test_the_command_line_writes_the_notes_of_a_beta_with_the_fragments(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(main_changelog(), encoding="utf-8")
    write_fragments(tmp_path / "changelog.d", **{"b-token": FIX})
    arguments = ["beta", "1.3.0-beta.1", "--file", str(changelog)]

    assert cli.main([*arguments, "--fragments", str(tmp_path / "changelog.d")]) == 0

    assert capsys.readouterr().out == beta_notes(
        "1.3.0-beta.1", main_changelog(), [fragment("b-token.md", FIX)]
    )


def test_the_command_line_checks_the_fragments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("CHANGELOG.md").write_text(main_changelog(), encoding="utf-8")
    write_fragments(
        tmp_path / "changelog.d", **{"a-voices": "### New\n\n- Voices.\n", "b-fix": FIX}
    )

    assert cli.main(["fragments"]) == 0
    assert capsys.readouterr().out == "The 2 fragment(s) in changelog.d/ are fine.\n"
    # Without the changelog, only the kinds of change are headings of a fragment.
    assert cli.main(["fragments", "--file", "missing.md"]) == 1
    assert capsys.readouterr().out.startswith(
        "changelog.d/a-voices.md: `### New` is no kind of change of the changelog."
    )
    assert cli.main(["fragments", "--folder", "elsewhere"]) == 0
    assert capsys.readouterr().out == "The 0 fragment(s) in elsewhere/ are fine.\n"


def git(repository: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-c", "user.name=Dev", "-c", "user.email=dev@example.com", *arguments],
        cwd=repository,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )


def test_pull_requests_with_fragments_merge_one_after_another_without_a_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    repository = tmp_path / "repository"
    repository.mkdir()

    def commit(message: str, **files: str | None) -> None:
        for name, text in files.items():
            path = repository / name
            if text is None:
                assert git(repository, "rm", "--quiet", name).returncode == 0
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
            assert git(repository, "add", name).returncode == 0
        assert git(repository, "commit", "--quiet", "-m", message).returncode == 0

    def merge(branch: str) -> subprocess.CompletedProcess[str]:
        assert git(repository, "switch", "--quiet", "main").returncode == 0
        return git(repository, "merge", "--no-edit", "--quiet", branch)

    assert git(repository, "init", "--quiet", "--initial-branch=main").returncode == 0
    commit(
        "chore: start",
        **{"CHANGELOG.md": main_changelog(""), "changelog.d/.gitkeep": ""},
    )
    # Three pull requests from the same main; two with fragments, one the old way.
    branches = {
        "cards": {"changelog.d/cards.md": FEATURE},
        "token": {"changelog.d/token.md": FIX},
        "voices": {"CHANGELOG.md": main_changelog()},
        "later": {"changelog.d/later.md": "### Fixed\n\n- Later.\n"},
    }
    for branch, files in branches.items():
        assert (
            git(repository, "switch", "--quiet", "-c", branch, "main").returncode == 0
        )
        commit(f"feat: {branch}", **files)
    for branch in ("cards", "token", "voices"):
        assert merge(branch).returncode == 0, branch

    # The release pull request: the section of the release, without the fragments.
    assert git(repository, "switch", "--quiet", "-c", "release", "main").returncode == 0
    changelog = (repository / "CHANGELOG.md").read_text(encoding="utf-8")
    fragments = read_fragments(repository / "changelog.d")
    branch = branch_changelog(changelog)
    released = release_changelog("1.3.0", changelog, branch, fragments)
    commit(
        "chore: release 1.3.0",
        **{"CHANGELOG.md": released},
        **dict.fromkeys(released_fragments("1.3.0", branch, fragments)),
    )
    assert merge("release").returncode == 0
    # A pull request with a fragment from before the release merges after it, too.
    assert merge("later").returncode == 0

    changelog = (repository / "CHANGELOG.md").read_text(encoding="utf-8")
    section = section_of(changelog)
    for entry in ("start a game by voice", "a new card", "stays secret"):
        assert changelog.count(entry) == 1
        assert entry in section
    assert sorted(path.name for path in (repository / "changelog.d").iterdir()) == [
        ".gitkeep",
        "later.md",
    ]
    # Two pull requests that both write under Unreleased conflict, as before.
    for name, entry in (("one", "- One.\n"), ("two", "- Two.\n")):
        assert git(repository, "switch", "--quiet", "-c", name, "main").returncode == 0
        commit(
            f"fix: {name}", **{"CHANGELOG.md": main_changelog(f"### Fixed\n\n{entry}")}
        )
    assert merge("one").returncode == 0
    assert merge("two").returncode != 0
