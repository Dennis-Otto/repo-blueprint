"""The files that a release of the blueprint removed: MOVED of blueprint/migrate.py,
the lines of a project that still name one, the fix of a page of Markdown, and the
guard of the Variants workflow that no release forgets an entry (decision 1051)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from blueprint.cli import main
from blueprint.migrate import (
    KEEP,
    MOVED,
    MOVED_NEXT,
    OWNED,
    Named,
    move_lines,
    moved_lines,
    owned_paths,
    unlisted,
)

SCAN = ".github/workflows/secret-scan.yml"
REVIEW = ".github/workflows/dependency-review.yml"
QUICK = ".github/workflows/quick-checks.yml"
GONE = ".github/workflows/coverage.yml"
REMOVED: dict[str, str | None] = {SCAN: QUICK, REVIEW: QUICK, GONE: None}
REPO = "https://github.com/Dennis-Otto/demo"
# The badge of a README, as five repositories had it after release 1.22.0.
BADGE = (
    f"[![Secret scan]({REPO}/actions/workflows/secret-scan.yml/badge.svg)]"
    f"({REPO}/actions/workflows/secret-scan.yml)\n"
)
BADGE_FIXED = (
    f"[![Secret scan]({REPO}/actions/workflows/quick-checks.yml/badge.svg)]"
    f"({REPO}/actions/workflows/quick-checks.yml)\n"
)


def repository(tmp_path: Path, files: dict[str, str]) -> Path:
    """A repository made from the blueprint, with its owned.txt and its answers."""
    root = tmp_path / "demo"
    owned = "# The files of the blueprint.\n.github/blueprint/owned.txt\nSECURITY.md\n"
    for path, text in {
        OWNED: owned,
        ".copier-answers.yml": "owner: Dennis-Otto\nproject_slug: demo\n",
        **files,
    }.items():
        file = root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(text.encode("utf-8"))
    return root


def places(root: Path) -> list[tuple[str, int, str, str | None]]:
    return [
        (item.path, item.line, item.removed, item.new)
        for item in moved_lines(root, REMOVED)
    ]


def test_the_badge_of_a_removed_workflow_shows_the_one_that_took_its_place(
    tmp_path: Path,
) -> None:
    # The badge names the page of the workflow, never its path: both addresses move,
    # and the words of the project, such as the label Secret scan, stay.
    root = repository(
        tmp_path,
        {"README.md": f"# Demo\n\n{BADGE}", "docs/README.de.md": f"# Demo\n{BADGE}"},
    )
    found = moved_lines(root, REMOVED)
    assert [(item.path, item.line) for item in found] == [
        ("README.md", 3),
        ("README.md", 3),
        ("docs/README.de.md", 2),
        ("docs/README.de.md", 2),
    ]
    assert all(item.fixable and item.new == "quick-checks.yml" for item in found)
    assert move_lines(root, found) == found
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert readme == f"# Demo\n\n{BADGE_FIXED}"
    german = (root / "docs/README.de.md").read_text(encoding="utf-8")
    assert german == f"# Demo\n{BADGE_FIXED}"
    assert not moved_lines(root, REMOVED)


@pytest.mark.parametrize(
    "link",
    [
        f"{REPO}/blob/main/{SCAN}",
        f"{REPO}/raw/main/{SCAN}",
        f"https://github.com/dennis-otto/DEMO/tree/main/{SCAN}",
        f"https://raw.githubusercontent.com/Dennis-Otto/demo/main/{SCAN}",
        f"https://raw.githubusercontent.com/Dennis-Otto/demo/refs/heads/main/{SCAN}",
        f"../{SCAN}",
        f"/{SCAN}",
        f"../../blob/main/{SCAN}",
        "../../actions/workflows/secret-scan.yml",
        "/Dennis-Otto/demo/actions/workflows/secret-scan.yml/badge.svg",
        SCAN,
    ],
)
def test_a_link_of_this_repository_at_its_branch_moves(
    tmp_path: Path, link: str
) -> None:
    root = repository(tmp_path, {"docs/automation.md": f"See [it]({link}#L3).\n"})
    found = moved_lines(root, REMOVED)
    assert len(found) == 1
    move_lines(root, found)
    moved = link.replace("secret-scan", "quick-checks")
    text = (root / "docs/automation.md").read_text(encoding="utf-8")
    assert text == f"See [it]({moved}#L3).\n"


@pytest.mark.parametrize(
    "link",
    [
        # A tag, a commit or another branch shows the file as it was there.
        f"{REPO}/blob/v1.21.0/{SCAN}",
        f"{REPO}/blob/0123456789abcdef0123456789abcdef01234567/{SCAN}",
        f"../../blob/v1.0.0/{SCAN}",
        f"https://raw.githubusercontent.com/Dennis-Otto/demo/v1.0.0/{SCAN}",
        # Another repository has files of its own.
        f"https://github.com/Dennis-Otto/repo-blueprint/blob/main/{SCAN}",
        "https://github.com/Dennis-Otto/other/actions/workflows/secret-scan.yml",
        "https://example.com/actions/workflows/secret-scan.yml",
        f"https://example.com/{SCAN}",
        # Another file whose path ends the same, or starts so.
        f"tests/fixtures/{SCAN}",
        f"{SCAN}.bak",
        f"{SCAN}/more",
        "secret-scan.yml",
        "actions/workflows/secret-scan.yml",
    ],
)
def test_another_file_or_another_version_of_it_stays(tmp_path: Path, link: str) -> None:
    root = repository(tmp_path, {"README.md": f"See [it]({link}).\n"})
    assert not moved_lines(root, REMOVED)


def test_a_file_that_the_project_has_at_the_old_path_is_its_own(tmp_path: Path) -> None:
    root = repository(
        tmp_path, {"README.md": f"[Scan]({SCAN})\n", SCAN: "name: Our own scan\n"}
    )
    assert not moved_lines(root, REMOVED)


def test_history_files_of_the_blueprint_and_kept_lines_stay(tmp_path: Path) -> None:
    root = repository(
        tmp_path,
        {
            "CHANGELOG.md": f"- {SCAN} joined Quick checks.\n",
            "changelog.d/scan.md": f"- {SCAN} is gone.\n",
            "docs/decisions/0001-a-scan.md": f"We run {SCAN}.\n",
            # A file of the blueprint, which the update writes anew.
            "SECURITY.md": f"The scan: {SCAN}\n",
            "docs/history.md": f"Until 1.22.0: {SCAN} <!-- {KEEP} -->\n",
        },
    )
    assert not moved_lines(root, REMOVED)


def test_a_line_that_no_bot_changes_is_a_warning_for_a_person(tmp_path: Path) -> None:
    root = repository(
        tmp_path,
        {
            ".github/dependency-review.yml": f"# Rules of the review ({REVIEW}).\n",
            ".github/pull_request_template.md": f"Read {SCAN}.\n",
            ".github/workflows/ours.yml": f"# Like {SCAN}\n",
            "scripts/build.sh": f"cat {SCAN}\n",
            "docs/coverage.md": f"The [coverage]({GONE}) and its badge "
            f"{REPO}/actions/workflows/coverage.yml/badge.svg\n",
        },
    )
    assert places(root) == [
        (".github/dependency-review.yml", 1, REVIEW, QUICK),
        (".github/pull_request_template.md", 1, SCAN, QUICK),
        (".github/workflows/ours.yml", 1, SCAN, QUICK),
        ("docs/coverage.md", 1, GONE, None),
        ("docs/coverage.md", 1, GONE, None),
        ("scripts/build.sh", 1, SCAN, QUICK),
    ]
    found = moved_lines(root, REMOVED)
    assert not any(item.fixable for item in found)
    assert move_lines(root, found) == []
    assert found[0].describe() == (
        ".github/dependency-review.yml:1: names "
        f"{REVIEW}, which a release of the blueprint removed: {QUICK} takes its place"
    )
    assert found[3].describe() == (
        f"docs/coverage.md:1: names {GONE}, which a release of the blueprint removed "
        "and nothing replaces"
    )


def test_a_successor_outside_the_workflows_moves_the_path_but_not_the_badge(
    tmp_path: Path,
) -> None:
    root = repository(
        tmp_path,
        {"README.md": f"[{SCAN}]({REPO}/actions/workflows/secret-scan.yml)\n"},
    )
    found = moved_lines(root, {SCAN: "docs/scan.md"})
    assert [(item.new, item.fixable) for item in found] == [
        ("docs/scan.md", True),
        (None, False),
    ]
    # The page of the workflow has no successor of its kind, but the line names one.
    assert found[1].describe().endswith(": docs/scan.md takes its place")


def test_the_badge_names_the_workflow_that_takes_its_place(tmp_path: Path) -> None:
    root = repository(tmp_path, {"README.md": BADGE})
    [item, _] = moved_lines(root, REMOVED)
    assert item.new == "quick-checks.yml"
    assert item.describe() == (
        f"README.md:1: names {SCAN}, which a release of the blueprint removed: "
        f"{QUICK} takes its place"
    )


def test_only_a_repository_of_the_blueprint_is_searched(tmp_path: Path) -> None:
    # The blueprint itself has no owned.txt: its tests name the old paths on purpose.
    root = repository(tmp_path, {"README.md": f"{SCAN}\n"})
    (root / OWNED).unlink()
    assert not moved_lines(root, REMOVED)
    # An empty list searches nothing, as MOVED before its first entry.
    assert not moved_lines(repository(tmp_path / "2", {"README.md": SCAN}), {})
    assert not moved_lines(repository(tmp_path / "3", {"README.md": SCAN}))


def test_the_files_of_git_are_searched_and_only_text(tmp_path: Path) -> None:
    root = repository(
        tmp_path,
        {
            "README.md": f"{SCAN}\n",
            "ignored.md": f"{SCAN}\n",
            ".gitignore": "ignored.md\n",
            "picture.md": f"{SCAN}\0",
        },
    )
    (root / "latin.md").write_bytes(f"caf\xe9 {SCAN}".encode("latin-1"))
    (root / "large.md").write_text(f"{SCAN}\n" + "x" * 1_000_000, encoding="utf-8")
    subprocess.run(["git", "init", "--quiet"], cwd=root, check=True)
    assert places(root) == [("README.md", 1, SCAN, QUICK)]


def test_a_link_is_never_followed(tmp_path: Path) -> None:
    root = repository(tmp_path, {"target.md": f"{SCAN}\n"})
    try:
        (root / "link.md").symlink_to(root / "target.md")
    except OSError:
        pytest.skip("this machine makes no symbolic links")
    assert [item.path for item in moved_lines(root, REMOVED)] == ["target.md"]


def test_the_fix_keeps_the_line_endings_and_the_rest_of_the_line(
    tmp_path: Path,
) -> None:
    root = repository(
        tmp_path,
        {"README.md": f"One {SCAN} and {REVIEW}, ok\r\nTwo\r\n"},
    )
    move_lines(root, moved_lines(root, REMOVED))
    assert (root / "README.md").read_bytes() == (
        f"One {QUICK} and {QUICK}, ok\r\nTwo\r\n".encode()
    )


def test_the_first_entries_are_the_workflows_of_release_1_22_0() -> None:
    # Secret scan and Dependency review joined Quick checks (#1026); the bot of main
    # knows the pages of **/*.md from the next release on, so they wait in MOVED_NEXT.
    assert MOVED_NEXT == {SCAN: QUICK, REVIEW: QUICK}
    assert not MOVED


def test_the_command_fails_for_a_page_and_moves_it_with_fix(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setattr("blueprint.migrate.MOVED", REMOVED)
    root = repository(
        tmp_path,
        {
            "README.md": f"# Demo\n{BADGE}",
            ".github/dependency-review.yml": f"# {REVIEW}\n",
        },
    )
    assert main(["migrate"], root=root) == 1
    out = capsys.readouterr().out
    assert (
        "::error file=README.md,line=2,title=Files of the project::README.md:2:" in out
    )
    assert (
        "::warning file=.github/dependency-review.yml,line=1,title=Files of the "
        "project::.github/dependency-review.yml:1: names"
    ) in out
    assert f"says `{KEEP}` in a comment" in out
    assert main(["migrate", "--fix"], root=root) == 0
    assert "2 move(s) of a release done" in capsys.readouterr().out
    assert (root / "README.md").read_text(encoding="utf-8") == f"# Demo\n{BADGE_FIXED}"
    # What only a person changes fails nothing.
    assert main(["migrate"], root=root) == 0
    out = capsys.readouterr().out
    assert "::warning file=.github/dependency-review.yml" in out
    assert "have what the releases of the blueprint moved" in out


def test_the_command_names_the_lines_without_annotations_outside_the_ci(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr("blueprint.migrate.MOVED", REMOVED)
    root = repository(tmp_path, {"README.md": f"{SCAN}\n", "run.sh": f"# {SCAN}\n"})
    assert main(["migrate"], root=root) == 1
    out = capsys.readouterr().out
    assert "README.md:1: names" in out
    assert "run.sh:1: names" in out
    assert "::" not in out


OWNED_1_21 = f"# The files.\n.github/blueprint/owned.txt\n{QUICK}\n{REVIEW}\n{SCAN}\n"
FLAKY = ".github/workflows/flaky.yml"


def test_a_file_that_leaves_the_blueprint_needs_its_entry(tmp_path: Path) -> None:
    root = repository(tmp_path, {QUICK: ""})
    (root / OWNED).write_text(f".github/blueprint/owned.txt\n{QUICK}\n", "utf-8")
    # The entries of release 1.22.0 name both workflows that it removed.
    assert unlisted(OWNED_1_21, root) == []
    # A removal without its entry, as #1026 was, fails.
    assert unlisted(f"{OWNED_1_21}{FLAKY}\n", root) == [FLAKY]
    # A file that leaves owned.txt for the project, which still has it, is no removal.
    (root / FLAKY).write_text("", "utf-8")
    assert unlisted(f"{OWNED_1_21}{FLAKY}\n", root) == []
    # Without an owned.txt after the update, every file of before that is gone counts.
    (root / OWNED).unlink()
    assert unlisted(f"{OWNED_1_21}SECURITY.md\n", root) == [
        ".github/blueprint/owned.txt",
        "SECURITY.md",
    ]


def test_owned_txt_lists_its_paths_without_its_comments() -> None:
    assert owned_paths("# One\n\na\n  b  \n") == {"a", "b"}


def test_the_guard_of_the_variants_fails_with_each_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = repository(tmp_path, {})
    before = tmp_path / "owned.txt"
    before.write_text(f".github/blueprint/owned.txt\n{FLAKY}\n", "utf-8")
    assert main(["migrate", "--since", str(before)], root=root) == 1
    out = capsys.readouterr().out
    assert "::error title=A removed file without its entry::The update removes " in out
    assert f"{FLAKY}, a file of the blueprint" in out
    before.write_text(".github/blueprint/owned.txt\n", "utf-8")
    assert main(["migrate", "--since", str(before)], root=root) == 0
    assert "has its entry in MOVED" in capsys.readouterr().out


def test_a_place_names_its_file_and_line() -> None:
    item = Named("README.md", 2, 0, 3, SCAN, QUICK)
    assert item.describe().startswith("README.md:2: names ")
    assert item.fixable


def test_a_file_outside_the_workflows_is_found_by_its_path_alone(
    tmp_path: Path,
) -> None:
    # As .github/CODEOWNERS, which #77 removed with nothing in its place.
    owners = ".github/CODEOWNERS"
    root = repository(tmp_path, {"docs/review.md": f"See [the owners]({owners}).\n"})
    assert [
        (item.path, item.new, item.fixable)
        for item in moved_lines(root, {owners: None})
    ] == [("docs/review.md", None, False)]
