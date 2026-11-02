"""What a release moves in a file of the project: blueprint/migrate.py and the command
migrate, which the step *Files of the project* of scripts/check.sh runs."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from blueprint.cli import main
from blueprint.migrate import (
    LABELS,
    Migration,
    contribution_labels,
    migrate,
)

# As every repository of the blueprint has it up to the release that moves the labels.
OLD = """# group decides who sets a label:
#   type       the kind of an issue
#   decision   set by the maintainer only
#   release    set by the bots

[[label]]
name = "bug"
color = "d73a4a"
description = "Something isn't working"
group = "type"

# Decisions

[[label]]
name = "wontfix"
color = "ffffff"
description = "This will not be worked on"
group = "decision"

[[label]]
name = "help wanted"
color = "008672"
description = "Extra attention is needed"
group = "decision"

[[label]]
name = "good first issue"
color = "7057ff"
description = "Good for newcomers"
group = "decision"

[[label]]
name = "no-bot-fixes"
color = "c5def5"
description = "The fix bot leaves this pull request alone"
group = "decision"

# Release: set from the title of a pull request

[[label]]
name = "release"
color = "5319e7"
description = "The pull request of the release bot"
group = "release"
"""

NEW = """# group decides who sets a label:
#   type       the kind of an issue
#   decision   set by the maintainer only
#   contribution set by the maintainer; the assistant's digest names candidates
#   release    set by the bots

[[label]]
name = "bug"
color = "d73a4a"
description = "Something isn't working"
group = "type"

# Decisions

[[label]]
name = "wontfix"
color = "ffffff"
description = "This will not be worked on"
group = "decision"

[[label]]
name = "no-bot-fixes"
color = "c5def5"
description = "The fix bot leaves this pull request alone"
group = "decision"

# Contribution: the assistant's digest suggests the first of these labels

[[label]]
name = "good first issue"
color = "7057ff"
description = "Good for newcomers"
group = "contribution"

[[label]]
name = "help wanted"
color = "008672"
description = "Extra attention is needed"
group = "contribution"

# Release: set from the title of a pull request

[[label]]
name = "release"
color = "5319e7"
description = "The pull request of the release bot"
group = "release"
"""


def groups(text: str) -> dict[str, str]:
    return {label["name"]: label["group"] for label in tomllib.loads(text)["label"]}


def project(tmp_path: Path, text: str = OLD) -> Path:
    path = tmp_path / LABELS
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return tmp_path


def test_the_labels_move_to_a_section_of_their_own() -> None:
    assert contribution_labels(OLD) == NEW


def test_the_digest_names_good_first_issue_first() -> None:
    # The first label of the group is the one that the digest tells the maintainer to
    # add, and every repository has help wanted first up to this move.
    moved = list(groups(contribution_labels(OLD)))
    assert moved.index("good first issue") == moved.index("help wanted") - 1


def test_moved_labels_have_nothing_left_to_move() -> None:
    assert contribution_labels(NEW) == NEW


def test_a_comment_behind_the_group_declines_the_move() -> None:
    declined = OLD.replace(
        'description = "Good for newcomers"\ngroup = "decision"\n',
        'description = "Good for newcomers"\ngroup = "decision" # no candidates\n',
    )
    moved = contribution_labels(declined)
    assert groups(moved)["good first issue"] == "decision"
    assert groups(moved)["help wanted"] == "contribution"
    assert 'group = "decision" # no candidates\n' in moved


def test_labels_that_declined_both_leave_the_file_as_it_is() -> None:
    declined = OLD.replace(
        'needed"\ngroup = "decision"\n', 'needed"\ngroup = "decision" # ours\n'
    ).replace(
        'newcomers"\ngroup = "decision"\n', 'newcomers"\ngroup = "decision" # no\n'
    )
    assert contribution_labels(declined) == declined


def test_a_repository_without_the_labels_stays_as_it_is() -> None:
    text = '[[label]]\nname = "bug"\ngroup = "decision"\n'
    assert contribution_labels(text) == text


def test_a_block_without_a_name_stays_as_it_is() -> None:
    text = '[[label]]\ngroup = "decision"\n'
    assert contribution_labels(text) == text


def test_labels_at_the_end_of_the_file_move_there() -> None:
    text = (
        '[[label]]\nname = "bug"\ngroup = "type"\n\n'
        '[[label]]\nname = "help wanted"\ngroup = "decision"'
    )
    assert contribution_labels(text) == (
        '[[label]]\nname = "bug"\ngroup = "type"\n\n'
        "# Contribution: the assistant's digest suggests the first of these labels\n\n"
        '[[label]]\nname = "help wanted"\ngroup = "contribution"\n'
    )


def test_a_file_of_only_these_labels_starts_with_their_section() -> None:
    moved = contribution_labels(
        '[[label]]\nname = "good first issue"\ngroup = "decision"\n'
    )
    assert moved.startswith("# Contribution: ")
    assert groups(moved) == {"good first issue": "contribution"}


def test_the_comment_at_the_top_names_the_group_once() -> None:
    named = (
        "#   decision   set by the maintainer only\n"
        "#   contribution ours\n\n"
        '[[label]]\nname = "help wanted"\ngroup = "decision"\n'
    )
    assert contribution_labels(named).count("#   contribution") == 1


def test_the_check_names_what_is_left_and_writes_nothing(tmp_path: Path) -> None:
    root = project(tmp_path)
    found = migrate(root, fix=False)
    assert [migration.path for migration in found] == [LABELS]
    assert (root / LABELS).read_text(encoding="utf-8") == OLD


def test_the_fix_moves_it(tmp_path: Path) -> None:
    root = project(tmp_path)
    assert migrate(root, fix=True)
    assert (root / LABELS).read_bytes().decode() == NEW
    assert not migrate(root, fix=False)


def test_a_repository_without_the_file_has_nothing_to_move(tmp_path: Path) -> None:
    assert not migrate(tmp_path, fix=True)


def test_each_migration_moves_on_what_the_one_before_wrote(tmp_path: Path) -> None:
    root = project(tmp_path, "one\n")
    migrations = (
        Migration(LABELS, "first", lambda text: text.replace("one", "two")),
        Migration(LABELS, "second", lambda text: text.replace("two", "three")),
    )
    assert [item.summary for item in migrate(root, True, migrations)] == [
        "first",
        "second",
    ]
    assert (root / LABELS).read_text(encoding="utf-8") == "three\n"


def test_the_command_fails_with_what_moves_and_the_fix(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    root = project(tmp_path)
    assert main(["migrate"], root=root) == 1
    out = capsys.readouterr().out
    assert f"{LABELS}: the labels good first issue and help wanted move" in out
    # This folder has no .github/blueprint.py, as the blueprint itself.
    assert "python3 blueprint.py migrate --fix moves" in out
    assert "::error" not in out


def test_the_command_annotates_the_file_in_the_ci(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    root = project(tmp_path)
    (root / ".github/blueprint.py").touch()
    assert main(["migrate"], root=root) == 1
    out = capsys.readouterr().out
    assert f"::error file={LABELS},title=Files of the project::the labels" in out
    assert "python3 .github/blueprint.py migrate --fix moves" in out


def test_the_command_with_fix_moves_and_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = project(tmp_path)
    assert main(["migrate", "--fix"], root=root) == 0
    assert "1 move(s) of a release done" in capsys.readouterr().out
    assert (root / LABELS).read_text(encoding="utf-8") == NEW


def test_the_command_passes_with_nothing_left(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["migrate"], root=project(tmp_path, NEW)) == 0
    assert "have what the releases of the blueprint moved" in capsys.readouterr().out


def test_a_file_that_cant_be_read_names_the_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path
    path = root / LABELS
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff\xfe")
    assert main(["migrate"], root=root) == 2
    assert "blueprint.py:" in capsys.readouterr().err
