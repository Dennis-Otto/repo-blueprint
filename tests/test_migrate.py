"""What a release moves in a file of the project: blueprint/migrate.py and the command
migrate, which the step *Files of the project* of scripts/check.sh runs."""

from __future__ import annotations

import json
import tomllib
from functools import partial
from pathlib import Path

import pytest
from shared import ROOT

from blueprint.cli import main
from blueprint.fixes import OPT_OUT
from blueprint.migrate import (
    ISSUE_ASSISTANT,
    ISSUE_ASSISTANT_PROJECT,
    ISSUE_ASSISTANT_PROJECT_TEXT,
    LABELS,
    LINK_HOSTS,
    NEXT,
    NO_BOT_FIXES_LABEL,
    Migration,
    contribution_labels,
    issue_assistant_project,
    label_name,
    migrate,
    no_bot_fixes_label,
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


# As the repositories that took release 1.1.0 by an update have it: without the label
# no-bot-fixes, which that release gave only to a new repository.
WITHOUT_NO_BOT_FIXES = NEW.replace(
    '[[label]]\nname = "no-bot-fixes"\ncolor = "c5def5"\n'
    'description = "The fix bot leaves this pull request alone"\n'
    'group = "decision"\n\n',
    "",
)
WITH_NO_BOT_FIXES = WITHOUT_NO_BOT_FIXES.replace(
    "# Contribution: ", f"{NO_BOT_FIXES_LABEL}\n\n# Contribution: "
)


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


def test_the_label_no_bot_fixes_is_the_one_the_fix_bot_reads() -> None:
    (label,) = tomllib.loads(NO_BOT_FIXES_LABEL)["label"]
    assert label_name(NO_BOT_FIXES_LABEL) == label["name"] == OPT_OUT
    assert label["group"] == "decision"


def test_the_label_no_bot_fixes_comes_after_the_last_decision() -> None:
    assert "no-bot-fixes" not in WITHOUT_NO_BOT_FIXES
    assert no_bot_fixes_label(WITHOUT_NO_BOT_FIXES) == WITH_NO_BOT_FIXES
    assert no_bot_fixes_label(WITH_NO_BOT_FIXES) == WITH_NO_BOT_FIXES


def test_a_decision_with_a_comment_behind_its_group_is_one_too() -> None:
    text = (
        '[[label]]\nname = "wontfix"\ngroup = "decision" # ours\n\n'
        '[[label]]\nname = "release"\ngroup = "release"\n'
    )
    assert no_bot_fixes_label(text) == (
        '[[label]]\nname = "wontfix"\ngroup = "decision" # ours\n\n'
        f"{NO_BOT_FIXES_LABEL}\n\n"
        '[[label]]\nname = "release"\ngroup = "release"\n'
    )


def test_a_group_whose_name_only_starts_with_decision_is_another() -> None:
    text = '[[label]]\nname = "a"\ngroup = "decisions"\n\n# Last\n'
    assert no_bot_fixes_label(text) == f"{text}\n{NO_BOT_FIXES_LABEL}\n"


def test_without_a_decision_the_label_no_bot_fixes_comes_at_the_end() -> None:
    text = '[[label]]\nname = "bug"\ngroup = "type"'
    assert no_bot_fixes_label(text) == f"{text}\n\n{NO_BOT_FIXES_LABEL}\n"
    assert no_bot_fixes_label("") == f"{NO_BOT_FIXES_LABEL}\n"


def test_a_file_that_names_no_bot_fixes_declines_or_has_the_label() -> None:
    declined = f"# no-bot-fixes: this project wants every fix\n{WITHOUT_NO_BOT_FIXES}"
    assert no_bot_fixes_label(declined) == declined
    # A label of that name stays as the project wrote it.
    assert no_bot_fixes_label(NEW) == NEW


def test_a_label_that_only_mentions_no_bot_fixes_still_gets_it() -> None:
    # Another label whose name begins with it, or a description that names it, is
    # neither the label nor a decline.
    other = (
        '[[label]]\nname = "no-bot-fixes-docs"\ncolor = "c5def5"\n'
        'description = "Like no-bot-fixes, for the documents"\ngroup = "decision"\n'
    )
    assert no_bot_fixes_label(other) == f"{other}\n{NO_BOT_FIXES_LABEL}\n"
    # A comment that names only that other label declines nothing either.
    commented = f"# no-bot-fixes-docs: for the documents\n{other}"
    assert no_bot_fixes_label(commented) == f"{commented}\n{NO_BOT_FIXES_LABEL}\n"


def test_an_update_after_1_1_0_adds_the_label(tmp_path: Path) -> None:
    root = project(tmp_path, WITHOUT_NO_BOT_FIXES)
    found = migrate(root, fix=False)
    assert len(found) == 1
    assert isinstance(found[0], Migration)
    assert found[0].moved is no_bot_fixes_label
    assert migrate(root, fix=True) == found
    assert (root / LABELS).read_text(encoding="utf-8") == WITH_NO_BOT_FIXES
    assert not migrate(root, fix=False)
    labels = tomllib.loads(WITH_NO_BOT_FIXES)["label"]
    assert [label["name"] for label in labels if label["group"] == "decision"] == [
        "wontfix",
        "no-bot-fixes",
    ]


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


# ------------------------------------------- the hosts and files of the issue assistant

# The config.toml of the issue assistant of the repositories that follow the blueprint,
# as each had it at release 1.18.3, with the kind of each: four added hosts or files.
REAL = ROOT / "tests/data/issue-assistant"
KIND_OF = {
    "homedarts-for-autodarts": "home-assistant",
    "paperless-sync": "nextcloud-app",
    "paperless-unified-search": "nextcloud-app",
    "issue-assistant": "github-action",
    "player-switch-for-autodarts": "chrome-extension",
    "repo-pager": "cloudflare-worker",
}
# What each of them added, which moves to config.project.toml.
ADDED = {
    "homedarts-for-autodarts": (
        ["home-assistant.io", "autodarts.io", "docs.autodarts.io"],
        ["docs/troubleshooting.de.md"],
    ),
    "paperless-sync": (["docs.paperless-ngx.com"], []),
    "paperless-unified-search": (["docs.paperless-ngx.com"], []),
    "issue-assistant": (["docs.anthropic.com"], []),
    "player-switch-for-autodarts": ([], []),
    "repo-pager": ([], []),
}


def assistant_repository(
    root: Path, config: str, kind: str = "home-assistant", ai: bool = True
) -> Path:
    """A repository of the kind with config.toml of the issue assistant, and without
    config.project.toml."""
    path = root / ISSUE_ASSISTANT
    path.parent.mkdir(parents=True)
    path.write_text(config, encoding="utf-8", newline="\n")
    (root / ".copier-answers.yml").write_text(
        f"_commit: v1.18.3\nissue_assistant_ai: {str(ai).lower()}\n"
        f"project_type: {kind}\n",
        encoding="utf-8",
    )
    return root


def read_lists(root: Path) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """[links] hosts and [transparency] files of config.toml and of
    config.project.toml in root, empty for a file that isn't there."""
    lists = []
    for name in (ISSUE_ASSISTANT, ISSUE_ASSISTANT_PROJECT):
        path = root / name
        table = tomllib.loads(path.read_text("utf-8")) if path.is_file() else {}
        lists.append(
            {
                "hosts": table.get("links", {}).get("hosts", []),
                "files": table.get("transparency", {}).get("files", []),
            }
        )
    return lists[0], lists[1]


def as_the_assistant_reads(root: Path) -> dict[str, list[str]]:
    """The lists as the issue assistant 1.12.0 reads them: those of config.toml followed
    by what config.project.toml adds, each value once."""
    config, project = read_lists(root)
    return {key: list(dict.fromkeys((*config[key], *project[key]))) for key in config}


def without_lists(text: str) -> dict[str, object]:
    """The TOML of text without the lists that the move changes."""
    table = tomllib.loads(text)
    table["links"].pop("hosts")
    table["transparency"].pop("files")
    return table


@pytest.mark.parametrize("name", sorted(KIND_OF))
def test_the_hosts_and_files_of_a_real_repository_move_to_its_own_file(
    tmp_path: Path, name: str
) -> None:
    text = (REAL / f"{name}.toml").read_text(encoding="utf-8")
    root = assistant_repository(tmp_path, text, KIND_OF[name])
    before = as_the_assistant_reads(root)
    hosts, files = ADDED[name]
    found = migrate(root, True, NEXT)
    assert bool(found) == bool(hosts or files)
    # The issue assistant reads every host and file that it read before, none more,
    # and the file that its footers link stays the first.
    after = as_the_assistant_reads(root)
    assert {key: set(value) for key, value in after.items()} == {
        key: set(value) for key, value in before.items()
    }
    assert after["files"][0] == "SUPPORT.md"
    config, project = read_lists(root)
    # config.toml has the lists of the template again, and nothing else changed.
    assert config == {"hosts": list(LINK_HOSTS[KIND_OF[name]]), "files": ["SUPPORT.md"]}
    moved = (root / ISSUE_ASSISTANT).read_text(encoding="utf-8")
    assert without_lists(moved) == without_lists(text)
    if found:
        assert project == {"hosts": hosts, "files": files}
        # Everything else of the new file is as a new repository gets it.
        assert (root / ISSUE_ASSISTANT_PROJECT).read_text(encoding="utf-8") == (
            ISSUE_ASSISTANT_PROJECT_TEXT.replace(
                "hosts = []", f"hosts = {json.dumps(hosts)}"
            ).replace("files = []", f"files = {json.dumps(files)}")
        )
    else:
        assert moved == text
        assert not (root / ISSUE_ASSISTANT_PROJECT).exists()
    assert not migrate(root, False, NEXT)


def test_a_repository_without_the_kind_or_the_file_has_nothing_to_move(
    tmp_path: Path,
) -> None:
    text = (REAL / "issue-assistant.toml").read_text(encoding="utf-8")
    # The blueprint itself has no answers of Copier.
    path = tmp_path / ISSUE_ASSISTANT
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")
    assert not issue_assistant_project(tmp_path)
    assert not issue_assistant_project(assistant_repository(tmp_path / "x", text, "?"))
    root = assistant_repository(tmp_path / "y", text, "github-action")
    (root / ISSUE_ASSISTANT).unlink()
    assert not issue_assistant_project(root)


@pytest.mark.parametrize(
    "text",
    [
        'hosts = ["a.example"\n',
        '[links]\nhosts = "a.example"\n',
        "[links]\nhosts = [1]\n",
        'links = "a.example"\n',
    ],
)
def test_a_config_that_isnt_toml_or_has_lists_of_another_type_stays(
    tmp_path: Path, text: str
) -> None:
    # The check of the issue assistant names the mistake; nothing moves out of it.
    assert not issue_assistant_project(assistant_repository(tmp_path, text))


def test_a_list_that_the_move_cant_follow_stays_as_it_is(tmp_path: Path) -> None:
    # The `]` in the comment ends the search for the list early: the move would leave
    # a config.toml that isn't TOML, so neither file changes.
    root = assistant_repository(
        tmp_path,
        '[links]\nhosts = [\n  "a.example",  # see [docs]\n  "b.example",\n]\n',
    )
    assert not issue_assistant_project(root)
    assert not migrate(root, True, NEXT)
    assert not (root / ISSUE_ASSISTANT_PROJECT).exists()


def test_the_project_file_keeps_what_it_has_and_names_each_host_once(
    tmp_path: Path,
) -> None:
    root = assistant_repository(
        tmp_path,
        '[links] # the hosts\nhosts = [\n  "hacs.xyz",\n  "b.example",  # B\n'
        '  "a.example",\n]\n\n[transparency]\nfiles = ["SUPPORT.md", "c.md"]\n',
    )
    (root / ISSUE_ASSISTANT_PROJECT).write_text(
        '[links]\nhosts = ["a.example", "d.example"]\n', encoding="utf-8"
    )
    changes = issue_assistant_project(root)
    assert changes[ISSUE_ASSISTANT] == (
        '[links] # the hosts\nhosts = ["hacs.xyz"]\n\n'
        '[transparency]\nfiles = ["SUPPORT.md"]\n'
    )
    # A list that the file lacks comes into its section, or with a section of its own.
    assert changes[ISSUE_ASSISTANT_PROJECT] == (
        '[links]\nhosts = ["a.example", "d.example", "b.example"]\n\n'
        '[transparency]\nfiles = ["c.md"]\n'
    )
    (root / ISSUE_ASSISTANT_PROJECT).write_text(
        "[transparency]\n# Ours.\n\n[links]\n", encoding="utf-8"
    )
    assert issue_assistant_project(root)[ISSUE_ASSISTANT_PROJECT] == (
        '[transparency]\nfiles = ["c.md"]\n# Ours.\n\n'
        '[links]\nhosts = ["b.example", "a.example"]\n'
    )


def test_without_the_ai_no_file_names_it_by_default(tmp_path: Path) -> None:
    root = assistant_repository(
        tmp_path, '[transparency]\nfiles = ["SUPPORT.md"]\n', "generic", ai=False
    )
    assert migrate(root, True, NEXT)
    config, project = read_lists(root)
    assert config == {"hosts": [], "files": []}
    assert project == {"hosts": [], "files": ["SUPPORT.md"]}


def test_the_command_names_the_move_of_the_issue_assistant(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setattr("blueprint.cli.migrate", partial(migrate, migrations=NEXT))
    text = (REAL / "paperless-sync.toml").read_text(encoding="utf-8")
    root = assistant_repository(tmp_path, text, "nextcloud-app")
    assert main(["migrate"], root=root) == 1
    out = capsys.readouterr().out
    assert (
        f"::error file={ISSUE_ASSISTANT},title=Files of the project::the hosts" in out
    )
    assert main(["migrate", "--fix"], root=root) == 0
    assert read_lists(root)[1]["hosts"] == ["docs.paperless-ngx.com"]
