"""Tests of the bots in the steps of the workflows: each step that deletes, starts,
merges, publishes or comments runs in bash, as GitHub runs it, with the fake gh of
tests/workflow_steps.py, which answers as the API does and writes down every call. A
census makes sure that every such step of every workflow runs in a test."""

from __future__ import annotations

import ast
import base64
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest
from shell import BASH
from workflow_steps import (
    ROOT,
    RUN_URL,
    SHA,
    Answer,
    StepResult,
    acting_steps,
    acts_of,
    condition_of,
    exact,
    job,
    job_in,
    parse,
    recording,
    run_step,
    step,
    step_in,
    workflow,
)

pytestmark = pytest.mark.skipif(
    BASH is None, reason="the steps run in bash, Git Bash on Windows"
)
# gh filters the answers of the API with its own jq, which the fake gh and some steps
# take from the machine; the runners of GitHub have it, Git for Windows doesn't.
WITH_JQ = pytest.mark.skipif(shutil.which("jq") is None, reason="needs jq")


# The harness itself.

DEMO = """\
name: Demo
on: push
env:
  LITERAL: as it is
jobs:
  demo:
    runs-on: ubuntu-24.04
    env:
      FROM_JOB: ${{ github.repository }}
      UNREAD: ${{ inputs.unread }}
    steps:
      - name: Variables
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GIVEN: ${{ inputs.given }}
          URL: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
        run: |
          echo "literal=$LITERAL job=$FROM_JOB given=$GIVEN token=$GH_TOKEN url=$URL"
          env | grep '^UNREAD='
      - name: Calls
        env:
          API_VERSION_HEADER: "X-GitHub-Api-Version: 2022-11-28"
        run: |
          gh api --header "$API_VERSION_HEADER" /repos/o/r/thing --jq .name
          gh api --header "$API_VERSION_HEADER" /repos/o/r/thing --jq .name
          printf 'from stdin' | gh api --header "$API_VERSION_HEADER" graphql --input -
          printf 'a body' > body.md
          gh pr comment 1 --body-file body.md
          gh issue view 2 || echo "gh failed with $?"
          gh api repos/o/r/unversioned || echo "gh failed with $?"
          gh api --header "$API_VERSION_HEADER" repos/o/r/raw
          {
            echo "text<<END"
            printf 'two\\nlines\\n'
            echo END
            echo "one=1"
          } >> "$GITHUB_OUTPUT"
          echo "EXPORTED=yes" >> "$GITHUB_ENV"
          echo "### Done" >> "$GITHUB_STEP_SUMMARY"
      - name: Escape sequences
        env:
          API_VERSION_HEADER: "X-GitHub-Api-Version: 2022-11-28"
        run: |
          gh help api | grep -c -e --allow-escape-sequences || true
          gh api --header "$API_VERSION_HEADER" repos/o/r/log || echo "gh failed with $?"
          gh api --header "$API_VERSION_HEADER" --allow-escape-sequences repos/o/r/log || echo "gh failed with $?"
          gh api --header "$API_VERSION_HEADER" repos/o/r/log --jq . || echo "gh failed with $?"
      - name: Default shell
        run: |
          false | true
          echo after
      - name: Bash shell
        shell: bash
        run: |
          false | true
          echo after
      - name: Workspace
        run: |
          cat brought.txt given.txt
          echo "$GITHUB_WORKSPACE"
      - name: Lines of jq
        run: |
          mapfile -t names < <(jq -r 'keys[]' <<<'{"a": 1, "b": 2}')
          printf '%q\\n' "${names[@]}"
"""


@pytest.fixture
def demo(tmp_path: Path) -> Path:
    root = tmp_path / "root"
    (root / ".github/workflows").mkdir(parents=True)
    (root / ".github/workflows/demo.yml").write_text(DEMO, encoding="utf-8")
    return root


def test_a_step_gets_its_variables_as_the_runner_sets_them(
    tmp_path: Path, demo: Path
) -> None:
    done = run_step(
        tmp_path, "demo.yml", "demo", "Variables", env={"GIVEN": "yes"}, root=demo
    )

    assert done.returncode == 0, done.stderr
    assert done.stdout == (
        f"literal=as it is job=o/r given=yes token=the-token url={RUN_URL}\nUNREAD=\n"
    )
    # A variable that the script reads and whose expression the test doesn't know
    # comes from the test.
    with pytest.raises(AssertionError, match="no value for GIVEN"):
        run_step(tmp_path, "demo.yml", "demo", "Variables", root=demo)


def test_the_fake_gh_answers_as_planned_and_writes_down_every_call(
    tmp_path: Path, demo: Path
) -> None:
    done = run_step(
        tmp_path,
        "demo.yml",
        "demo",
        "Calls",
        answers=[
            Answer(r"api /repos/o/r/thing --jq \.name", "first\n", once=True),
            exact("api /repos/o/r/thing --jq .name", "second\n"),
            exact("api graphql --input -"),
            exact("pr comment 1 --body-file body.md"),
            Answer("api repos/o/r/raw", json={"a": 1}),
        ],
        root=demo,
    )

    assert done.returncode == 0, done.stderr
    # Each answer once, then the next; the arguments as bash passed them, also one that
    # starts with /, which Git Bash would make a Windows path of, and without the
    # version of the API that a call of gh api asks for. A call without an answer
    # fails, and so does a call of gh api that asks for no version.
    assert (
        done.stdout == 'first\nsecond\ngh failed with 1\ngh failed with 1\n{"a": 1}\n'
    )
    assert "fake gh: no answer for: gh issue view 2" in done.stderr
    no_version = "fake gh: gh api asks for no version: gh api repos/o/r/unversioned"
    assert no_version in done.stderr
    assert done.commands == [
        "api /repos/o/r/thing --jq .name",
        "api /repos/o/r/thing --jq .name",
        "api graphql --input -",
        "pr comment 1 --body-file body.md",
        "issue view 2",
        "api repos/o/r/raw",
    ]
    assert done.read_by("api graphql", "--input") == ["from stdin"]
    assert done.read_by("pr comment", "--body-file") == ["a body"]
    assert done.called("api /repos") == done.commands[:2]
    assert done.outputs == {"text": "two\nlines", "one": "1"}
    assert done.exported == {"EXPORTED": "yes"}
    assert done.summary == "### Done\n"


@WITH_JQ
def test_the_fake_gh_filters_json_with_jq_as_gh_does(
    tmp_path: Path, demo: Path
) -> None:
    (demo / ".github/workflows/demo.yml").write_text(
        DEMO.replace(" repos/o/r/raw\n", " repos/o/r/raw --jq '.[] | .name, .id'\n"),
        encoding="utf-8",
    )
    done = run_step(
        tmp_path,
        "demo.yml",
        "demo",
        "Calls",
        answers=[
            Answer(
                r"api repos/o/r/raw --jq .*",
                json=[{"name": "a", "id": None}, {"name": "b", "id": {"x": [1, 2]}}],
            ),
            Answer(r".*"),
        ],
        root=demo,
    )

    assert done.returncode == 0, done.stderr
    # As gh prints what the filter makes, one result on each line: a string raw, null
    # as an empty line and anything else as compact JSON. The call that asks for no
    # version of the API fails before any answer.
    assert done.stdout == 'gh failed with 1\na\n\nb\n{"x":[1,2]}\n'


@pytest.mark.parametrize(
    ("gh", "guarded"),
    [("", True), ("2.97.0", True), ("2.96.0", False)],
    ids=["runner", "first-guarded", "older"],
)
def test_the_fake_gh_guards_against_escape_sequences_as_its_version_does(
    tmp_path: Path, demo: Path, gh: str, guarded: bool
) -> None:
    red = "\x1b[31mred\x1b[0m\n"
    done = run_step(
        tmp_path,
        "demo.yml",
        "demo",
        "Escape sequences",
        answers=[Answer(r"api .*repos/o/r/log.*", red)],
        env={"FAKE_GH_CLI": gh},
        root=demo,
    )

    assert done.returncode == 0, done.stderr
    # The gh of the runners, as every gh since v2.97.0, lists the option, refuses a raw
    # answer with escape sequences without it, and prints one with it or through a
    # filter; an older gh knows no such option and prints every answer as it is.
    if guarded:
        assert done.stdout == f"1\ngh failed with 1\n{red}{red}"
        assert (
            "the response contains terminal escape sequences;"
            " pass --allow-escape-sequences to output it anyway\n"
        ) in done.stderr
    else:
        assert done.stdout == f"0\n{red}gh failed with 1\n{red}"
        assert "unknown flag: --allow-escape-sequences\n" in done.stderr
    assert done.commands[0] == "help api"


def test_a_step_runs_with_the_options_of_its_shell(tmp_path: Path, demo: Path) -> None:
    # bash -e by default, so a pipe fails only by its last command; shell: bash adds
    # pipefail.
    default = run_step(tmp_path / "1", "demo.yml", "demo", "Default shell", root=demo)
    assert (default.returncode, default.stdout) == (0, "after\n")
    strict = run_step(tmp_path / "2", "demo.yml", "demo", "Bash shell", root=demo)
    assert (strict.returncode, strict.stdout) == (1, "")


def test_a_step_runs_in_the_checkout_that_the_test_made(
    tmp_path: Path, demo: Path
) -> None:
    # A repository of the test, such as one with the history of a pull request, as
    # the checkout of the job, with the files that the test gives it.
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / "brought.txt").write_text("from the checkout\n", encoding="utf-8")

    done = run_step(
        tmp_path,
        "demo.yml",
        "demo",
        "Workspace",
        files={"given.txt": "from the test\n"},
        root=demo,
        workspace=checkout,
    )

    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines() == [
        "from the checkout",
        "from the test",
        checkout.as_posix(),
    ]
    assert done.workspace == checkout
    assert not (tmp_path / "workspace").exists()


@WITH_JQ
def test_a_step_reads_the_lines_of_jq_as_on_the_runners_of_github(
    tmp_path: Path, demo: Path
) -> None:
    # Each line without the CR that jq.exe of Windows writes before its LF, which
    # mapfile kept: the update leg of the Variants updated symfony/filesystem with a CR
    # at its end, a package that Composer doesn't know (#676).
    done = run_step(tmp_path, "demo.yml", "demo", "Lines of jq", root=demo)

    assert done.returncode == 0, done.stderr
    assert done.stdout == "a\nb\n"


# Text that a slice of the workflow takes for a job, a permission or a condition: the
# comment above a job and the script of a step.
SLICED = """\
on: push
permissions: {}
jobs:
  first:
    # Not a job of its own, nor its condition or its permissions:
    #   second:
    #     if: always()
    #     permissions:
    #       contents: write
    if: >-
      github.event_name == 'push' &&
      !cancelled()
    permissions:
      contents: read
    steps:
      - name: One
        id: one
        if: failure()
        run: |
          cat <<'EOF'
            if: always()
          second:
          EOF
  second:
    steps:
      - uses: actions/checkout@v6
"""


def test_a_job_its_permissions_and_conditions_come_from_the_parsed_workflow(
    demo: Path,
) -> None:
    parsed = parse(SLICED)

    # The same object for the same text, and the key on as YAML 1.1 reads it.
    assert parse(SLICED) is parsed
    assert parsed["on"] == "push"
    assert parsed["permissions"] == {}
    first = job_in(SLICED, "first")
    assert condition_of(first) == "github.event_name == 'push' && !cancelled()"
    assert first["permissions"] == {"contents": "read"}
    one = step_in(first, "One")
    assert step_in(first, "one") == one
    assert condition_of(one) == "failure()"
    second = job_in(parsed, "second")
    assert condition_of(second) == ""
    assert "permissions" not in second
    with pytest.raises(AssertionError, match="no job third, but"):
        job_in(parsed, "third")
    with pytest.raises(AssertionError, match="no step 'Two', but"):
        step_in(first, "Two")
    with pytest.raises(AssertionError, match=r"demo.yml/demo: the job has no step"):
        step("demo.yml", "demo", "Two", demo)


# A call of gh api as the steps write it, with the version of the API.
VERSIONED = 'gh api --header "$API_VERSION_HEADER"'


@pytest.mark.parametrize(
    ("script", "acts"),
    [
        ('gh pr merge "$number" --auto --squash', ["merges"]),
        ('gh issue close "$n" \\\n  --comment "Fixed."', ["closes", "comments"]),
        ('gh api --method DELETE "repos/$GH_REPO/git/refs/heads/$b"', ["deletes"]),
        ('gh workflow run blueprint-update.yml --repo "$repo"', ["dispatches"]),
        ('gh api "repos/$GH_REPO/issues" -f title="$title"', ["writes"]),
        ("gh api graphql --input - --jq .data", ["writes"]),
        ("git push origin refs/tags/v1", ["pushes"]),
        # The other ways to write the same commands.
        ("gh api --method=DELETE repos/o/r/git/refs/heads/x", ["deletes"]),
        ("gh api -X put repos/o/r/topics -f names[]=a", ["writes"]),
        ("gh api -XPATCH repos/o/r", ["writes"]),
        ("gh api --method=post repos/o/r/labels", ["writes"]),
        ("git -C repo push origin HEAD", ["pushes"]),
        ("git -c user.name=bot push origin :old", ["deletes", "pushes"]),
        ('gh issue reopen "$n"', ["opens"]),
        ('gh pr reopen "$n"', ["opens"]),
        ('gh issue delete "$n" --yes', ["deletes"]),
        ('gh issue lock "$n"', ["edits"]),
        ('gh pr unlock "$n"', ["edits"]),
        ('gh issue transfer "$n" o/other', ["edits"]),
        ("gh secret set TOKEN < token", ["edits"]),
        ("gh variable delete NAME", ["deletes"]),
        ('gh run cancel "$run"', ["cancels"]),
        ("gh workflow disable mutation.yml", ["edits"]),
        ("gh repo edit --enable-wiki=false", ["edits"]),
        # Reading only, or a comment.
        ('# gh api "repos/$GH_REPO/issues" -f title=x', []),
        ("gh api --method=GET search/issues -f q=x", []),
        ("gh api graphql -f query='query { viewer { login } }'", []),
        # With the version of the API, as the steps call it.
        (f"{VERSIONED} graphql -f query='query {{ viewer {{ login }} }}'", []),
        (f"{VERSIONED} graphql -F owner=o -f query='query {{ x }}'", []),
        (f'{VERSIONED} graphql --input "$RUNNER_TEMP/commit.json"', ["writes"]),
        (f'{VERSIONED} "repos/$GH_REPO/issues" -f title="$title"', ["writes"]),
        ('gh api -X GET search/issues -f q="$query"', []),
        ('gh pr list --json number\n# gh pr merge "$number"', []),
    ],
)
def test_the_census_finds_what_a_step_changes(script: str, acts: list[str]) -> None:
    assert acts_of(script) == acts


# The steps that change something on GitHub, each with the file of its tests, which
# runs the step. A new step that deletes, starts, merges, publishes or comments needs a
# test that runs it, here with run_step() or in the tests of its bot.
TESTED = {
    (
        "publish-store.yml",
        "status",
        "Check the set-up of the environment",
    ): "test_template.py",
    ("publish-store.yml", "store", "Submit the release for review"): "test_template.py",
    ("after-checks.yml", "rerun", "Run the failed jobs once more"): "test_template.py",
    ("after-checks.yml", "branches", "Start the branch bot"): "test_workflow_steps.py",
    (
        "after-checks.yml",
        "stopped",
        "Run the jobs again that Harden-Runner stopped",
    ): "test_template.py",
    (
        "after-checks.yml",
        "report",
        "Add the jobs that failed at first to the issue of flaky tests",
    ): "test_template.py",
    (
        "after-checks.yml",
        "release",
        "Run the failed jobs of the release once more",
    ): "test_workflow_steps.py",
    (
        "after-checks.yml",
        "cancelled",
        "Run the checks of the head of a pull request or of main again",
    ): "test_template.py",
    (
        "after-checks.yml",
        "fixes",
        "Say on the pull request that the fix bot failed",
    ): "test_fixes.py",
    (
        "after-checks.yml",
        "own-branch",
        "Say on the pull request that the fix bot failed",
    ): "test_fixes.py",
    (
        "after-checks.yml",
        "fixes",
        "Keep the issue of the fix bot of main current",
    ): "test_fixes.py",
    (
        "after-checks.yml",
        "diagrams",
        "Commit the diagrams onto the branch of the pull request",
    ): "test_diagrams.py",
    (
        "after-checks.yml",
        "diagrams",
        "Say on the pull request that the bot failed",
    ): "test_diagrams.py",
    (
        "build-release.yml",
        "assets",
        "Attach the assets and their signed provenance to the draft",
    ): "test_workflow_steps.py",
    (
        "build-release.yml",
        "assets",
        "Write the notes, the section of the changelog with every pull request",
    ): "test_workflow_steps.py",
    (
        "cleanup.yml",
        "cleanup",
        "Delete the branches that main holds",
    ): "test_workflow_steps.py",
    (
        "cleanup.yml",
        "cleanup",
        "Delete the caches of closed pull requests",
    ): "test_workflow_steps.py",
    (
        "commands.yml",
        "fix",
        "Answer the command on the pull request",
    ): "test_fixes.py",
    (
        "dependabot-automerge.yml",
        "auto-merge",
        "Enable automatic squash merge",
    ): "test_workflow_steps.py",
    (
        "diagrams.yml",
        "pull-request",
        "Open, update or close the pull request of the diagrams",
    ): "test_diagrams.py",
    (
        "diagrams.yml",
        "report",
        "Keep the issue of the diagram bot current",
    ): "test_diagrams.py",
    (
        "docs-pictures.yml",
        "pull-request",
        "Open, update or close the pull request of the pictures",
    ): "test_workflow_steps.py",
    (
        "links.yml",
        "issue",
        "Keep the issue of broken links current",
    ): "test_workflow_steps.py",
    (
        "newest-node.yml",
        "report",
        "Keep the issue of the newest Node current",
    ): "test_template.py",
    (
        "newest-python.yml",
        "report",
        "Keep the issue of the newest Python current",
    ): "test_template.py",
    (
        "next-runner.yml",
        "report",
        "Keep the issue of the next runner current",
    ): "test_template.py",
    (
        "pull-request-title.yml",
        "title",
        "Check the title and set the label",
    ): "test_workflow_steps.py",
    (
        "release.yml",
        "release-please",
        "Have the release pull request rebuilt on the current main",
    ): "test_workflow_steps.py",
    (
        "release.yml",
        "release-please",
        "Write the text of Unreleased and of the fragments into the release pull request",
    ): "test_template.py",
    (
        "release.yml",
        "release-please",
        "Merge a release of dependency updates once its checks pass",
    ): "test_workflow_steps.py",
    (
        "release.yml",
        "release-please",
        "Publish a beta of the next release",
    ): "test_workflow_steps.py",
    (
        "release.yml",
        "publish",
        "Make the complete release public",
    ): "test_workflow_steps.py",
    (
        "release.yml",
        "github-action",
        "Point the major tag at the release, as users of v1 and the like expect",
    ): "test_workflow_steps.py",
    (
        "rollout.yml",
        "rollout",
        "Start the blueprint bot of the repository",
    ): "test_rollout.py",
    (
        "screenshot-bot.yml",
        "plan",
        "Start the run that renders the pictures",
    ): "test_workflow_steps.py",
    (
        "screenshot-bot.yml",
        "pull-request",
        "Open, update or close the pull request of the screenshots",
    ): "test_workflow_steps.py",
    (
        "sync-issue-assistant.yml",
        "pull-request",
        "Open, update or close the pull request of the release",
    ): "test_sync_issue_assistant.py",
    (
        "upstream.yml",
        "nextcloud",
        "Raise max-version to the newest major version of Nextcloud",
    ): "test_template.py",
    (
        "weekly-report.yml",
        "report",
        "Post it in the discussions",
    ): "test_workflow_steps.py",
    (
        "welcome.yml",
        "welcome",
        "Welcome the first pull request",
    ): "test_workflow_steps.py",
}


def names_in(module: Path) -> set[str]:
    """The strings of a file of tests, other than those of TESTED."""
    tree = ast.parse(module.read_text(encoding="utf-8"))
    skipped = {
        id(node)
        for assignment in ast.walk(tree)
        if isinstance(assignment, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "TESTED"
            for target in assignment.targets
        )
        for node in ast.walk(assignment)
    }
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in skipped
    }


def test_every_step_that_changes_something_on_github_runs_in_a_test() -> None:
    found = acting_steps()
    # Each with a test, and no test listed for a step that is gone or changes nothing.
    assert sorted(set(found) - set(TESTED)) == [], "a step without a test that runs it"
    assert sorted(set(TESTED) - set(found)) == [], "a step that changes nothing"
    for (name, job_id, step_name), module in TESTED.items():
        # The tests run it by its name, or by the start of it.
        strings = names_in(ROOT / "tests" / module)
        assert any(
            text == step_name or (len(text) >= 20 and step_name.startswith(text))
            for text in strings
        ), f"{module} runs no step {step_name!r} of {name}/{job_id}"


# The clean-up bot.


def branches(*names: str) -> str:
    return "".join(f"{name}\n" for name in names)


def days_ago(days: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_the_clean_up_bot_runs_every_week_with_the_rights_it_needs() -> None:
    cleanup = workflow("cleanup.yml")
    assert set(cleanup["on"]) == {"schedule", "workflow_dispatch"}
    assert cleanup["permissions"] == {}
    settings = job("cleanup.yml", "cleanup")
    assert settings["if"] == "${{ !github.event.repository.fork }}"
    assert settings["permissions"] == {
        "actions": "write",
        "contents": "write",
        "pull-requests": "read",
    }


def listing(*names: str) -> str:
    """The branches as the clean-up bot lists them: each name as it is, a tab and the
    name for the path of a request, encoded as jq's @uri does, but with its slashes."""
    return "".join(f"{name}\t{quote(name, safe='/')}\n" for name in names)


def run_the_branch_clean_up(
    tmp_path: Path, listed: str, used: str, *more: Answer
) -> StepResult:
    done = run_step(
        tmp_path,
        "cleanup.yml",
        "cleanup",
        "Delete the branches that main holds",
        # The answers of the test first, then the lists.
        answers=[
            *more,
            Answer(
                r"pr list --state open --limit 500 --json headRefName --jq .*", used
            ),
            Answer(r"api repos/o/r/branches --paginate --jq .*", listed),
            Answer(r"api --method DELETE repos/o/r/git/refs/heads/\S+ --silent"),
        ],
        env={"DEFAULT": "main"},
    )
    assert done.returncode == 0, done.stderr
    return done


COUNTED = "[.ahead_by, .behind_by] | @tsv"
FIRST_OF_MAIN = ".commits[0].commit.committer.date"


def counted(branch: str, ahead: int, behind: int) -> Answer:
    """How many commits a branch has that main doesn't, and main that it doesn't."""
    return exact(
        f"api repos/o/r/compare/main...{branch} --jq {COUNTED}", f"{ahead}\t{behind}\n"
    )


def moved_past(branch: str, date: str) -> Answer:
    """The date of the first commit that main has and the branch doesn't."""
    return exact(f"api repos/o/r/compare/{branch}...main --jq {FIRST_OF_MAIN}", date)


def last_commit(branch: str, date: str) -> Answer:
    """The date of the last commit of a branch, named as in the path of a request."""
    return exact(f"api repos/o/r/commits/{branch} --jq .commit.committer.date", date)


def test_the_clean_up_bot_deletes_only_the_branches_that_main_holds(
    tmp_path: Path,
) -> None:
    done = run_the_branch_clean_up(
        tmp_path,
        listing(
            "main",
            "gh-pages",
            "release-please--branches--main",
            "renovate/ruff-0.x",
            "dependabot/pip/ruff-1",
            "feat/in-review",
            "fix/merged",
            "fix/issue#12",
            "feat/fresh",
            "feat/at-main",
            "feat/old",
            "feat/new",
        ),
        branches("feat/in-review", "other"),
        counted("fix/merged", 0, 3),
        counted("fix/issue%2312", 0, 1),
        counted("feat/fresh", 0, 1),
        counted("feat/at-main", 0, 0),
        counted("feat/old", 2, 5),
        counted("feat/new", 1, 0),
        moved_past("fix/merged", days_ago(2) + "\n"),
        moved_past("fix/issue%2312", days_ago(2) + "\n"),
        moved_past("feat/fresh", days_ago(0) + "\n"),
        last_commit("feat/old", "2026-01-02T03:04:05Z\n"),
        last_commit("feat/new", days_ago(2) + "\n"),
    )

    # Only a branch that main holds completely, and that main moved past a day ago,
    # goes: one made from main stays while it sits on main's last commit, however
    # old that is, and for a day after main moved on. The bot doesn't even look at
    # main, the website, the branches of the bots and those of open pull requests,
    # and it names a branch with a # encoded, so that the # is no fragment of the path.
    assert done.called("api --method DELETE") == [
        "api --method DELETE repos/o/r/git/refs/heads/fix/merged --silent",
        "api --method DELETE repos/o/r/git/refs/heads/fix/issue%2312 --silent",
    ]
    assert done.called("api repos/o/r/(compare|commits)/") == [
        f"api repos/o/r/compare/main...fix/merged --jq {COUNTED}",
        f"api repos/o/r/compare/fix/merged...main --jq {FIRST_OF_MAIN}",
        f"api repos/o/r/compare/main...fix/issue%2312 --jq {COUNTED}",
        f"api repos/o/r/compare/fix/issue%2312...main --jq {FIRST_OF_MAIN}",
        f"api repos/o/r/compare/main...feat/fresh --jq {COUNTED}",
        f"api repos/o/r/compare/feat/fresh...main --jq {FIRST_OF_MAIN}",
        f"api repos/o/r/compare/main...feat/at-main --jq {COUNTED}",
        f"api repos/o/r/compare/main...feat/old --jq {COUNTED}",
        "api repos/o/r/commits/feat/old --jq .commit.committer.date",
        f"api repos/o/r/compare/main...feat/new --jq {COUNTED}",
        "api repos/o/r/commits/feat/new --jq .commit.committer.date",
    ]
    # A branch with commits of its own stays; once it is a month old, the bot lists it
    # for its owner, by its name as it is.
    assert done.summary == (
        "### Branches\n"
        "- deleted `fix/merged`, which main holds\n"
        "- deleted `fix/issue#12`, which main holds\n"
        "- kept `feat/old, 2 commit(s) that main doesn't have, last on 2026-01-02`:"
        " without a pull request for a month\n"
    )
    assert "::warning::" not in done.stdout


def test_the_clean_up_bot_says_when_there_is_nothing_to_clean_up(
    tmp_path: Path,
) -> None:
    done = run_the_branch_clean_up(tmp_path, listing("main", "renovate/x"), "")

    assert done.commands == [
        "pr list --state open --limit 500 --json headRefName --jq .[].headRefName",
        "api repos/o/r/branches --paginate --jq .[] | select(.protected | not)"
        ' | [.name, (.name | @uri | gsub("%2F"; "/"))] | @tsv',
    ]
    assert done.summary == "### Branches\nNothing to clean up.\n"


def test_a_branch_that_github_refuses_is_a_warning_and_the_bot_goes_on(
    tmp_path: Path,
) -> None:
    done = run_the_branch_clean_up(
        tmp_path,
        listing("fix/compare", "fix/moved", "fix/date", "fix/delete", "fix/merged"),
        "",
        Answer(
            r"api repos/o/r/compare/main\.\.\.fix/compare .*",
            err="gh: Bad Gateway (HTTP 502)",
            code=1,
        ),
        counted("fix/date", 1, 0),
        Answer(r"api repos/o/r/compare/main\.\.\..*", "0\t1\n"),
        Answer(
            r"api repos/o/r/compare/fix/moved\.\.\.main .*",
            err="gh: Not Found (HTTP 404)",
            code=1,
        ),
        Answer(r"api repos/o/r/compare/.*\.\.\.main .*", days_ago(2) + "\n"),
        Answer(
            r"api repos/o/r/commits/fix/date .*", err="gh: Not Found (HTTP 404)", code=1
        ),
        Answer(
            r"api --method DELETE repos/o/r/git/refs/heads/fix/delete --silent",
            err="gh: Reference does not exist (HTTP 422)",
            code=1,
        ),
    )

    # No branch whose state the bot doesn't know goes, the one after them does, and
    # the run stays green with a warning for each that it looks at again next week.
    assert done.called("api --method DELETE") == [
        "api --method DELETE repos/o/r/git/refs/heads/fix/delete --silent",
        "api --method DELETE repos/o/r/git/refs/heads/fix/merged --silent",
    ]
    assert done.stdout.splitlines() == [
        f"::warning::GitHub refused a request for the branch {name};"
        " the clean-up looks at it again next week."
        for name in ("fix/compare", "fix/moved", "fix/date", "fix/delete")
    ]
    assert done.summary == (
        "### Branches\n"
        "- deleted `fix/merged`, which main holds\n"
        "- left `fix/compare` for next week: GitHub refused a request for it\n"
        "- left `fix/moved` for next week: GitHub refused a request for it\n"
        "- left `fix/date` for next week: GitHub refused a request for it\n"
        "- left `fix/delete` for next week: GitHub refused a request for it\n"
    )


def test_a_warning_keeps_the_percent_of_a_branch(tmp_path: Path) -> None:
    done = run_the_branch_clean_up(
        tmp_path,
        listing("fix/100%0Adone"),
        "",
        Answer(r"api repos/o/r/compare/.*", code=1),
    )

    # The runner reads %0A of a workflow command as a new line; %25 is the percent.
    assert done.stdout == (
        "::warning::GitHub refused a request for the branch fix/100%250Adone;"
        " the clean-up looks at it again next week.\n"
    )
    assert done.summary == (
        "### Branches\n"
        "- left `fix/100%0Adone` for next week: GitHub refused a request for it\n"
    )


@WITH_JQ
def test_the_clean_up_bot_never_looks_at_a_protected_branch_and_encodes_a_name(
    tmp_path: Path,
) -> None:
    done = run_the_branch_clean_up(
        tmp_path,
        "",
        "",
        Answer(
            r"api repos/o/r/branches --paginate --jq .*",
            json=[
                {"name": "main", "protected": True},
                {"name": "stable", "protected": True},
                {"name": "fix/merged", "protected": False},
                {"name": "fix/issue#12 100%", "protected": False},
            ],
        ),
        Answer(r"api repos/o/r/compare/main\.\.\..*", "0\t1\n"),
        Answer(r"api repos/o/r/compare/.*\.\.\.main .*", days_ago(2) + "\n"),
    )

    # jq of gh encodes the name for the paths, and the summary keeps it as it is.
    assert done.called("api repos/o/r/compare/|api --method DELETE") == [
        f"api repos/o/r/compare/main...fix/merged --jq {COUNTED}",
        f"api repos/o/r/compare/fix/merged...main --jq {FIRST_OF_MAIN}",
        "api --method DELETE repos/o/r/git/refs/heads/fix/merged --silent",
        f"api repos/o/r/compare/main...fix/issue%2312%20100%25 --jq {COUNTED}",
        f"api repos/o/r/compare/fix/issue%2312%20100%25...main --jq {FIRST_OF_MAIN}",
        "api --method DELETE repos/o/r/git/refs/heads/fix/issue%2312%20100%25 --silent",
    ]
    assert "- deleted `fix/issue#12 100%`, which main holds\n" in done.summary


def test_the_clean_up_bot_deletes_the_caches_of_closed_pull_requests_only(
    tmp_path: Path,
) -> None:
    done = run_step(
        tmp_path,
        "cleanup.yml",
        "cleanup",
        "Delete the caches of closed pull requests",
        answers=[
            Answer(
                r"pr list --state open --limit 500 --json number --jq .*", "112\n7\n"
            ),
            Answer(
                r"cache list --limit 1000 --json id,ref --jq .*",
                "1 refs/pull/112/merge\n2 refs/pull/11/merge\n3 refs/heads/main\n"
                "4 refs/pull/12/merge\n5 refs/pull/1/head\n",
            ),
            Answer(r"cache delete \d+"),
        ],
    )

    assert done.returncode == 0, done.stderr
    # Those of the merge commits of closed pull requests; #12 is not #112, and the
    # caches of main and of a head stay.
    assert done.called("cache delete") == ["cache delete 2", "cache delete 4"]
    assert done.summary == "### Caches\nDeleted 2 cache(s) of closed pull requests.\n"


# The start of the branch bot after a check that failed for good.

START_THE_BRANCH_BOT = (
    "workflow run update-branches.yml --field after=77 --field attempt=2"
)


def start_the_branch_bot(tmp_path: Path, *answers: Answer) -> StepResult:
    return run_step(
        tmp_path,
        "after-checks.yml",
        "branches",
        "Start the branch bot",
        answers=answers,
        env={"RUN": "77", "ATTEMPT": "2", "NAME": "CI (python)"},
        stubs={"sleep": recording("sleep")},
    )


def test_a_check_that_failed_for_good_starts_the_branch_bot_with_its_run(
    tmp_path: Path,
) -> None:
    done = start_the_branch_bot(tmp_path, exact(START_THE_BRANCH_BOT))

    assert done.returncode == 0, done.stderr
    assert done.commands == [START_THE_BRANCH_BOT]
    assert done.summary == (
        "CI (python) failed for good, so the branch bot moves its line on.\n"
    )
    assert done.stubbed == []


def test_the_start_of_the_branch_bot_tries_again_when_github_fails(
    tmp_path: Path,
) -> None:
    done = start_the_branch_bot(
        tmp_path,
        Answer(re.escape(START_THE_BRANCH_BOT), err="HTTP 502", code=1, once=True),
        exact(START_THE_BRANCH_BOT),
    )

    assert done.returncode == 0, done.stderr
    assert done.commands == [START_THE_BRANCH_BOT] * 2
    assert done.stubbed == ["sleep 10"]


def test_a_branch_bot_that_github_never_starts_fails_with_what_follows(
    tmp_path: Path,
) -> None:
    done = start_the_branch_bot(
        tmp_path, Answer(re.escape(START_THE_BRANCH_BOT), err="HTTP 502", code=1)
    )

    assert done.returncode == 1
    assert done.commands == [START_THE_BRANCH_BOT] * 3
    assert done.stubbed == ["sleep 10", "sleep 20"]
    assert (
        "::error title=The branch bot didn't start::GitHub didn't start Update "
        "branches after CI (python) failed; its next run, after a merge or on its "
        "schedule, moves the line on."
    ) in done.stdout
    assert done.summary == ""


# The bots that merge.


def test_every_dependabot_update_merges_itself_a_major_one_too() -> None:
    settings = job("dependabot-automerge.yml", "auto-merge")
    # Only Dependabot's own pull requests, from a branch of the repository.
    for part in (
        "!github.event.repository.fork",
        "github.event.pull_request.user.login == 'dependabot[bot]'",
        "github.event.pull_request.head.repo.full_name == github.repository",
    ):
        assert part in settings["if"]
    # The checks are the gate, not the kind of the update: a major one, and one whose
    # metadata names no kind, merges once every required check passes (decision 0150).
    for name in (
        "Check that the release app is set up",
        "Enable automatic squash merge",
    ):
        assert "if" not in step("dependabot-automerge.yml", "auto-merge", name), name
    text = (ROOT / ".github/workflows/dependabot-automerge.yml").read_text("utf-8")
    assert "update-type" not in text
    assert "waits for the maintainer" not in text


def test_a_dependabot_update_merges_only_the_commit_that_was_checked(
    tmp_path: Path,
) -> None:
    url = "https://github.com/o/r/pull/3"
    done = run_step(
        tmp_path,
        "dependabot-automerge.yml",
        "auto-merge",
        "Enable automatic squash merge",
        answers=[exact(f"pr merge --auto --squash --match-head-commit fed987 {url}")],
        env={"GH_TOKEN": "app-token", "PR_URL": url, "PR_HEAD_SHA": "fed987"},
    )

    assert done.returncode == 0, done.stderr
    assert len(done.calls) == 1


MERGE_STEP = "Merge a release of dependency updates once its checks pass"
RELEASE_PR = json.dumps({"number": 21, "headBranchName": "release-please--x"})


def decides(verdict: str) -> str:
    """A stub of python3 that writes its call down and decides as blueprint.py does:
    merge=true or merge=false into the file after --output, and its reason."""
    return recording(
        "python3",
        'while [[ "$1" != --output ]]; do shift; done\n'
        f'printf "merge=%s\\n" {verdict} > "$2"\necho "The reason."',
    )


def run_the_merge_of_dependency_updates(
    tmp_path: Path,
    *answers: Answer,
    verdict: str = "true",
    event: str = "schedule",
    pr: str = RELEASE_PR,
    script: str = ".github/blueprint.py",
) -> StepResult:
    done = run_step(
        tmp_path,
        "release.yml",
        "release-please",
        MERGE_STEP,
        answers=[*answers, Answer(r"pr merge --repo o/r --auto --squash 21")],
        env={"GH_TOKEN": "app-token", "PR": pr, "GITHUB_EVENT_NAME": event},
        stubs={"python3": decides(verdict)},
        files={script: ""},
    )
    assert done.returncode == 0, done.stderr
    return done


def test_the_merge_runs_in_every_run_without_a_new_release() -> None:
    merge = step("release.yml", "release-please", MERGE_STEP)

    # Also in the run of the schedule, where release-please changed nothing.
    assert merge["if"] == (
        "steps.app.outputs.token != '' && "
        "steps.release.outputs.release_created != 'true'"
    )


@WITH_JQ
@pytest.mark.parametrize("script", [".github/blueprint.py", "blueprint.py"])
@pytest.mark.parametrize("event", ["schedule", "push"])
@pytest.mark.parametrize("verdict", ["true", "false"])
def test_blueprint_py_decides_whether_the_release_merges_itself(
    tmp_path: Path, script: str, event: str, verdict: str
) -> None:
    # tests/test_dependency_release.py tests the decision, by the commits since the
    # last release and the event of the run.
    done = run_the_merge_of_dependency_updates(
        tmp_path, verdict=verdict, event=event, script=script
    )

    assert done.stubbed == [
        f"python3 {script} --repo o/r release dependency-only --event {event} "
        f"--output {(tmp_path / 'runner' / 'dependency-only').as_posix()}"
    ]
    assert done.called("pr merge") == (
        ["pr merge --repo o/r --auto --squash 21"] if verdict == "true" else []
    )
    # The reason stays in the log and in the summary of the run.
    assert done.stdout.startswith("The reason.\n")
    assert done.summary == "The reason.\n"


@WITH_JQ
def test_the_daily_run_finds_the_release_pull_request_that_stayed_the_same(
    tmp_path: Path,
) -> None:
    done = run_the_merge_of_dependency_updates(
        tmp_path,
        Answer(
            r"pr list --repo o/r --state open --label autorelease: pending "
            r"--json number --jq .*",
            json=[{"number": 21}],
        ),
        pr="",
    )

    assert done.called("pr merge") == ["pr merge --repo o/r --auto --squash 21"]


@WITH_JQ
def test_without_a_release_pull_request_nothing_merges(tmp_path: Path) -> None:
    done = run_the_merge_of_dependency_updates(
        tmp_path,
        Answer(r"pr list --repo o/r --state open .*", json=[]),
        pr="",
    )

    assert done.called("pr merge") == []
    assert done.stubbed == []
    assert done.stdout == "No release pull request is open.\n"


@WITH_JQ
@pytest.mark.parametrize("passes", [True, False])
def test_a_release_whose_checks_passed_already_merges_at_once(
    tmp_path: Path, passes: bool
) -> None:
    done = run_step(
        tmp_path,
        "release.yml",
        "release-please",
        MERGE_STEP,
        answers=[
            exact(
                "pr merge --repo o/r --auto --squash 21",
                err="Pull request Pull request is in clean status",
                code=1,
            ),
            exact(
                "pr merge --repo o/r --squash 21",
                code=0 if passes else 1,
                err="" if passes else "the base branch policy prohibits the merge",
            ),
        ],
        env={
            "GH_TOKEN": "app-token",
            "PR": RELEASE_PR,
            "GITHUB_EVENT_NAME": "schedule",
        },
        stubs={"python3": decides("true")},
        files={".github/blueprint.py": ""},
    )

    # Without --auto, the rules of main still decide, and a refusal fails the run.
    assert (done.returncode == 0) == passes
    assert done.called("pr merge") == [
        "pr merge --repo o/r --auto --squash 21",
        "pr merge --repo o/r --squash 21",
    ]


# The release bot.


@pytest.mark.parametrize(
    ("state", "behind", "rebuilt"),
    [("OPEN", "3", True), ("OPEN", "0", False), ("MERGED", None, False)],
)
def test_the_release_pull_request_is_rebuilt_only_when_it_is_behind_main(
    tmp_path: Path, state: str, behind: str | None, rebuilt: bool
) -> None:
    branch = "release-please--branches--main"
    done = run_step(
        tmp_path,
        "release.yml",
        "release-please",
        "Have the release pull request rebuilt on the current main",
        answers=[
            Answer(
                r"pr list --state open --label autorelease: pending .*",
                f"21 {branch}\n",
            ),
            exact("pr view 21 --json state --jq .state", f"{state}\n"),
            exact(
                f"api repos/o/r/compare/main...{branch} --jq .behind_by", f"{behind}\n"
            ),
            exact("pr view 21 --json body --jq .body", "The notes\n"),
            Answer(r"pr edit 21 --body .*"),
        ],
        env={"GH_TOKEN": "app-token"},
    )

    assert done.returncode == 0, done.stderr
    # A pull request that the list shows, but which is merged already, is left alone.
    assert bool(done.called("api repos/o/r/compare")) == (state == "OPEN")
    assert done.called("pr edit") == (
        [
            "pr edit 21 --body The notes\n\n"
            "<!-- The release bot rebuilds this pull request on the current main. -->"
        ]
        if rebuilt
        else []
    )


OVERRIDES = "Give release-please the title of each merged pull request"


@pytest.mark.parametrize("script", [".github/blueprint.py", "blueprint.py"])
def test_release_please_reads_the_overrides_that_the_step_before_writes(
    tmp_path: Path, script: str
) -> None:
    # blueprint.py writes the overrides, which tests/test_overrides.py tests, with the
    # token of the job, whose edit of a merged pull request starts no workflow.
    names = [each.get("name") for each in job("release.yml", "release-please")["steps"]]
    assert names.index(OVERRIDES) == (
        names.index("Update the release pull request, or create the release") - 1
    )
    assert step("release.yml", "release-please", OVERRIDES)["env"] == {
        "GH_TOKEN": "${{ secrets.GITHUB_TOKEN }}"
    }
    done = run_step(
        tmp_path,
        "release.yml",
        "release-please",
        OVERRIDES,
        stubs={"python3": recording("python3", 'echo "- #383: the title"')},
        files={script: ""},
    )

    assert done.returncode == 0, done.stderr
    assert done.stubbed == [f"python3 {script} --repo o/r commit-overrides"]
    assert done.summary == "- #383: the title\n"


BETA = "Publish a beta of the next release"
SIGN_TAG = 'printf "%s\\n" "sign-tag $*" >> "$STUB_CALLS"\n'


@pytest.mark.parametrize(
    "message", ["docs: a typo", "fix(deps): update ruff", "chore: tidy up\n\nfeat: x"]
)
def test_no_beta_without_a_change_for_users(tmp_path: Path, message: str) -> None:
    done = run_step(
        tmp_path,
        "release.yml",
        "release-please",
        BETA,
        env={"GH_TOKEN": "app-token", "MESSAGE": message},
    )

    assert done.returncode == 0, done.stderr
    assert done.calls == []
    assert done.summary == "No change for users, so no beta.\n"


def run_the_beta(tmp_path: Path, *answers: Answer) -> tuple[int, list[str], str]:
    done = run_step(
        tmp_path,
        "release.yml",
        "release-please",
        BETA,
        answers=answers,
        env={"GH_TOKEN": "app-token", "MESSAGE": "feat: a dark mode\n\nThe body."},
        stubs={"python3": recording("python3", 'echo "The notes of the beta"')},
        files={".github/sign-tag.sh": SIGN_TAG},
    )
    assert done.returncode == 0, done.stderr
    return len(done.called("release create")), done.stubbed, done.summary


RELEASE_PULL_REQUEST = r"pr list --state open --label autorelease: pending .*"
MANIFEST = (
    r"api -H Accept: application/vnd\.github\.raw\+json "
    r"repos/o/r/contents/\.release-please-manifest\.json\?ref=release-please--x"
)


def test_no_beta_without_a_release_pull_request(tmp_path: Path) -> None:
    created, stubbed, summary = run_the_beta(
        tmp_path, Answer(RELEASE_PULL_REQUEST, "\n")
    )

    assert (created, stubbed) == (0, [])
    assert summary == "No release pull request, so no beta.\n"


@WITH_JQ
def test_no_beta_of_a_prerelease(tmp_path: Path) -> None:
    created, stubbed, summary = run_the_beta(
        tmp_path,
        Answer(RELEASE_PULL_REQUEST, "release-please--x\n"),
        Answer(MANIFEST, json={".": "2.0.0-rc.1"}),
    )

    assert (created, stubbed) == (0, [])
    assert (
        summary == "The next release, 2.0.0-rc.1, is a prerelease itself, so no beta.\n"
    )


@WITH_JQ
def test_a_beta_is_signed_and_numbered_after_the_last_one(tmp_path: Path) -> None:
    done = run_step(
        tmp_path,
        "release.yml",
        "release-please",
        BETA,
        answers=[
            Answer(RELEASE_PULL_REQUEST, "release-please--x\n"),
            Answer(MANIFEST, json={".": "1.3.0"}),
            Answer(
                r"release list --limit 100 --json tagName --jq .*",
                "v1.3.0-beta.9\nv1.3.0-beta.10\nv1.2.0-beta.12\nv1.2.0\n",
            ),
            Answer(
                r"release create v1\.3\.0-beta\.11 --draft --prerelease --verify-tag"
                r" --title v1\.3\.0-beta\.11 --notes-file \S+/beta\.md"
            ),
        ],
        env={"GH_TOKEN": "app-token", "MESSAGE": "feat: a dark mode\n\nThe body."},
        stubs={"python3": recording("python3", 'echo "The notes of the beta"')},
        files={".github/sign-tag.sh": SIGN_TAG},
    )

    assert done.returncode == 0, done.stderr
    # The notes, then the signed tag, then the draft that names it.
    assert done.stubbed == [
        "python3 blueprint.py beta 1.3.0-beta.11",
        "sign-tag v1.3.0-beta.11",
    ]
    assert done.read_by("release create", "--notes-file") == ["The notes of the beta\n"]
    assert done.outputs == {
        "tag": "v1.3.0-beta.11",
        "sha": SHA,
        "version": "1.3.0-beta.11",
    }
    assert done.summary == "The beta v1.3.0-beta.11 of 1.3.0 is on its way.\n"


@pytest.mark.parametrize(
    ("tag", "categories", "edit"),
    [
        # A prerelease is never the latest release and is not announced.
        ("v2.0.0-beta.1", None, "--draft=false --prerelease --latest=false"),
        (
            "v2.0.0",
            "General\nAnnouncements\n",
            "--draft=false --latest --discussion-category Announcements",
        ),
        ("v2.0.0", "General\nIdeas\n", "--draft=false --latest"),
    ],
)
def test_a_release_is_made_public_and_announced_where_it_can_be(
    tmp_path: Path, tag: str, categories: str | None, edit: str
) -> None:
    done = run_step(
        tmp_path,
        "release.yml",
        "publish",
        "Make the complete release public",
        answers=[
            Answer(
                r"api graphql -F owner=o -F name=r -f query=query.* --jq .*",
                categories or "",
            ),
            Answer(rf"release edit {tag} .*"),
        ],
        env={"TAG": tag},
    )

    assert done.returncode == 0, done.stderr
    assert done.called("api graphql") == (
        [] if categories is None else done.commands[:1]
    )
    assert done.called("release edit") == [f"release edit {tag} {edit} --repo o/r"]
    assert ("announced" in done.summary) == ("Announcements" in edit)


# How gh answers when GitHub fails for a moment, as it answered the call that made
# v1.11.1 public, which it made public all the same (#661).
BAD_GATEWAY = "HTTP 502: Bad Gateway (https://api.github.com/repos/o/r/releases/1)\n"
MADE_PUBLIC_ANYWAY = "made it public all the same"


def release_state(tag: str, state: str = "", code: int = 0) -> Answer:
    """The answer of gh to the look at the release of the tag: whether it is a draft
    and whether it is a prerelease, such as "false false"."""
    pattern = (
        rf"release view {re.escape(tag)} --repo o/r --json isDraft,isPrerelease .*"
    )
    if code:
        return Answer(pattern, err=BAD_GATEWAY, code=code, once=True)
    return Answer(pattern, f"{state}\n", once=True)


def latest_release(tag: str) -> Answer:
    """The answer of gh to the look at the latest release of the repository."""
    return exact("release view --repo o/r --json tagName --jq .tagName", f"{tag}\n")


def failed_edit(tag: str) -> Answer:
    """The call that makes the release public, which GitHub fails once."""
    return Answer(
        rf"release edit {re.escape(tag)} .*", err=BAD_GATEWAY, code=1, once=True
    )


def publishing(tmp_path: Path, tag: str, answers: list[Answer]) -> StepResult:
    """Runs *Make the complete release public* for the tag, with the answers of gh
    before those of a repository without the category Announcements, and a sleep
    that only counts."""
    return run_step(
        tmp_path,
        "release.yml",
        "publish",
        "Make the complete release public",
        answers=[*answers, Answer(r"api graphql .*", "General\n")],
        env={"TAG": tag},
        stubs={"sleep": recording("sleep")},
    )


@pytest.mark.parametrize(
    ("tag", "state"), [("v2.0.0", "false false"), ("v2.0.0-beta.1", "false true")]
)
def test_a_release_that_github_made_public_despite_an_error_is_public(
    tmp_path: Path, tag: str, state: str
) -> None:
    done = publishing(
        tmp_path,
        tag,
        [failed_edit(tag), release_state(tag, state), latest_release("v2.0.0")],
    )

    assert done.returncode == 0, done.stdout + done.stderr
    # One call, which GitHub answered with an error after it had done what was asked.
    assert len(done.called("release edit")) == 1
    assert [call for call in done.stubbed if call.startswith("sleep")] == []
    assert MADE_PUBLIC_ANYWAY in done.summary
    # Only a release for everybody is the latest one.
    assert bool(done.called("release view --repo")) == ("-" not in tag)


@pytest.mark.parametrize(
    "state",
    [
        # Still a draft.
        release_state("v2.0.0", "true false"),
        # Public, but not the latest release.
        release_state("v2.0.0", "false false"),
        # GitHub fails the look at the release as well.
        release_state("v2.0.0", code=1),
    ],
)
def test_a_release_that_github_did_not_make_public_is_made_public_again(
    tmp_path: Path, state: Answer
) -> None:
    done = publishing(
        tmp_path,
        "v2.0.0",
        [
            failed_edit("v2.0.0"),
            state,
            latest_release("v1.9.0"),
            Answer(r"release edit v2\.0\.0 .*"),
        ],
    )

    assert done.returncode == 0, done.stdout + done.stderr
    assert (
        done.called("release edit")
        == ["release edit v2.0.0 --draft=false --latest --repo o/r"] * 2
    )
    assert done.stubbed == ["sleep 15"]
    assert MADE_PUBLIC_ANYWAY not in done.summary


def test_a_release_that_github_never_makes_public_fails_its_job(
    tmp_path: Path,
) -> None:
    tag = "v2.0.0-beta.1"
    done = publishing(
        tmp_path,
        tag,
        [
            Answer(r"release edit .*", err=BAD_GATEWAY, code=1),
            Answer(r"release view .*", "true true\n"),
        ],
    )

    # Three times at most, 15 seconds apart.
    assert done.returncode == 1
    assert len(done.called("release edit")) == 3
    assert done.stubbed == ["sleep 15", "sleep 15"]
    assert (
        f"::error::GitHub failed three times to make {tag} public, which stays a "
        "draft until the job runs again." in done.stdout
    )


@pytest.mark.parametrize(
    ("discussion", "edits"),
    [
        # Public and the latest release, but GitHub linked no discussion yet, as
        # with v1.11.1: the call is made again, and GitHub creates it then.
        ("", 2),
        ("https://github.com/o/r/discussions/659", 1),
    ],
)
def test_a_public_release_without_its_announcement_is_announced_again(
    tmp_path: Path, discussion: str, edits: int
) -> None:
    done = publishing(
        tmp_path,
        "v2.0.0",
        [
            Answer(r"api graphql .*", "General\nAnnouncements\n"),
            failed_edit("v2.0.0"),
            release_state("v2.0.0", "false false"),
            latest_release("v2.0.0"),
            exact(
                "api repos/o/r/releases/tags/v2.0.0 --jq .discussion_url // empty",
                f"{discussion}\n" if discussion else "",
            ),
            Answer(r"release edit v2\.0\.0 .*"),
        ],
    )

    assert done.returncode == 0, done.stdout + done.stderr
    assert (
        done.called("release edit")
        == [
            "release edit v2.0.0 --draft=false --latest "
            "--discussion-category Announcements --repo o/r"
        ]
        * edits
    )
    assert done.stubbed == ["sleep 15"] * (edits - 1)
    assert (MADE_PUBLIC_ANYWAY in done.summary) == (edits == 1)
    assert "announced in the discussions" in done.summary


@pytest.mark.parametrize("failures", [1, 3])
def test_github_is_asked_again_for_the_categories_of_the_discussions(
    tmp_path: Path, failures: int
) -> None:
    done = publishing(
        tmp_path,
        "v2.0.0",
        [
            *[
                Answer(r"api graphql .*", err=BAD_GATEWAY, code=1, once=True)
                for _ in range(failures)
            ],
            Answer(r"api graphql .*", "Announcements\n"),
            Answer(r"release edit v2\.0\.0 .*"),
        ],
    )

    assert done.stubbed == ["sleep 15"] * min(failures, 2)
    if failures == 3:
        assert done.returncode == 1
        assert done.called("release edit") == []
        assert (
            "::error::GitHub failed three times to name the categories of the "
            "discussions; v2.0.0 stays a draft until the job runs again."
        ) in done.stdout
        return
    assert done.returncode == 0, done.stdout + done.stderr
    assert done.called("release edit") == [
        "release edit v2.0.0 --draft=false --latest "
        "--discussion-category Announcements --repo o/r"
    ]


def test_the_major_tag_of_an_action_follows_each_release() -> None:
    settings = job("release.yml", "github-action")
    assert settings["if"] == (
        "vars.PUBLISH_TO == 'github-action' && "
        "!contains(needs.release-please.outputs.tag, '-')"
    )
    assert settings["permissions"] == {"contents": "write"}


def test_the_major_tag_points_at_the_release(tmp_path: Path) -> None:
    done = run_step(
        tmp_path,
        "release.yml",
        "github-action",
        "Point the major tag at the release, as users of v1 and the like expect",
        env={"TAG": "v2.3.0", "MAJOR": "v2"},
        stubs={"git": recording("git")},
    )

    assert done.returncode == 0, done.stderr
    assert done.stubbed == [
        "git config user.name github-actions[bot]",
        "git config user.email 41898282+github-actions[bot]@users.noreply.github.com",
        "git tag -fa v2 -m v2.3.0 v2.3.0^{commit}",
        "git push --force https://x-access-token:the-token@github.com/o/r.git refs/tags/v2",
    ]


@WITH_JQ
def test_the_failed_jobs_of_a_release_run_once_more(tmp_path: Path) -> None:
    settings = job("after-checks.yml", "release")
    for part in (
        "github.event.workflow_run.name == 'Release'",
        "github.event.workflow_run.conclusion == 'failure'",
        "github.event.workflow_run.run_attempt == 1",
    ):
        assert part in settings["if"]
    assert settings["permissions"] == {"actions": "write"}

    confirmed = "Requested rerun (failed jobs) of run 77\n"
    done = rerun_the_release(
        tmp_path, "completed", 1, exact("run rerun 77 --failed", confirmed)
    )

    assert done.returncode == 0, done.stderr
    # The log shows that GitHub took the rerun.
    assert confirmed in done.stdout
    assert done.commands[0].startswith(
        "api repos/o/r/actions/runs/77/attempts/1/jobs --paginate --jq "
    )
    assert done.commands[1:] == [
        'api repos/o/r/actions/runs/77 --jq "\\(.status) \\(.run_attempt)"',
        "run rerun 77 --failed",
    ]
    assert done.summary == (
        "The failed jobs of the release of abc1234 run once more, where they stopped.\n"
    )


# A job of the release that failed in a step: GitHub started it.
FAILED_IN_A_STEP = {
    "id": 771,
    "name": "release",
    "conclusion": "failure",
    "steps": [{"name": "Push the tag", "conclusion": "failure"}],
}


def rerun_the_release(
    tmp_path: Path,
    status: str,
    attempt: int,
    rerun: Answer,
    jobs: Sequence[Mapping[str, Any]] = (FAILED_IN_A_STEP,),
    first: Sequence[Answer] = (),
) -> StepResult:
    """The bot for failed releases after the first attempt of run 77 failed in jobs,
    with the run as GitHub shows it now and the answer of its rerun, after the answers
    first."""
    return run_step(
        tmp_path,
        "after-checks.yml",
        "release",
        "Run the failed jobs of the release once more",
        answers=[
            *first,
            Answer(
                r"api repos/o/r/actions/runs/77/attempts/1/jobs --paginate --jq .*",
                json={"jobs": list(jobs)},
            ),
            Answer(
                r"api repos/o/r/actions/runs/77 --jq .*",
                json={"id": 77, "status": status, "run_attempt": attempt},
            ),
            rerun,
        ],
        env={"RUN": "77", "SHA": "abc1234def"},
        stubs={"sleep": recording("sleep")},
    )


@WITH_JQ
@pytest.mark.parametrize(
    "jobs",
    [[], [{**FAILED_IN_A_STEP, "steps": []}]],
    ids=["no job", "a job without a step"],
)
def test_the_bot_leaves_a_release_alone_that_github_could_not_start(
    tmp_path: Path, jobs: list[dict[str, Any]]
) -> None:
    # As in GitHub's outage of 9 November 2026: another try while GitHub fails would
    # fail too, and the scheduled run of the release takes it up (decision 0136).
    # The job without a step has no annotation either.
    done = rerun_the_release(
        tmp_path,
        "completed",
        1,
        exact("run rerun 77 --failed", code=1),
        jobs,
        first=[Answer(r"api repos/o/r/check-runs/771/annotations .*", json=[])],
    )

    assert done.returncode == 0, done.stderr
    assert not done.called("run rerun")
    assert done.stdout.startswith(
        "::notice title=GitHub is unavailable::GitHub couldn't start the release of "
        "abc1234"
    )
    assert done.summary == (
        "GitHub couldn't start the release of abc1234, so the bot leaves it alone; "
        "the scheduled run of the release takes it up.\n"
    )


@WITH_JQ
def test_the_bot_runs_a_release_again_whose_job_no_runner_took(
    tmp_path: Path,
) -> None:
    # A job without a step that has an annotation broke: GitHub started the run.
    done = rerun_the_release(
        tmp_path,
        "completed",
        1,
        exact("run rerun 77 --failed"),
        [{**FAILED_IN_A_STEP, "steps": []}],
        first=[
            Answer(
                r"api repos/o/r/check-runs/771/annotations .*",
                json=[{"message": "The job was not acquired by Runner of type hosted"}],
            )
        ],
    )

    assert done.returncode == 0, done.stderr
    assert done.called("run rerun 77 --failed")
    assert "::notice" not in done.stdout


@WITH_JQ
def test_the_bot_for_failed_releases_ends_with_a_notice_when_github_keeps_failing(
    tmp_path: Path,
) -> None:
    failing = Answer(
        r"api repos/o/r/actions/runs/77/attempts/1/jobs .*",
        err="HTTP 503: Service Unavailable\n",
        code=1,
    )
    done = rerun_the_release(
        tmp_path, "completed", 1, exact("run rerun 77 --failed"), first=[failing]
    )

    assert done.returncode == 0, done.stderr
    assert done.stubbed == ["sleep 10", "sleep 20", "sleep 40"]
    assert not done.called("run rerun")
    assert "::notice title=GitHub is unavailable::GitHub kept failing (HTTP 503" in (
        done.stdout
    )


@WITH_JQ
@pytest.mark.parametrize(
    ("status", "attempt", "now"),
    [
        # A person ran it again before the bot started, as in run 39648756239.
        ("in_progress", 2, "running"),
        ("queued", 2, "waiting"),
        # Its second attempt ended already, passed or failed: a third is a person's.
        ("completed", 2, "done"),
    ],
)
def test_the_bot_leaves_a_release_alone_that_ran_again_already(
    tmp_path: Path, status: str, attempt: int, now: str
) -> None:
    done = rerun_the_release(
        tmp_path, status, attempt, exact("run rerun 77 --failed", code=1)
    )

    assert done.returncode == 0, done.stderr
    assert not done.called("run rerun")
    assert done.summary == (
        f"The release of abc1234 ran again already: its attempt {attempt} is"
        f" {now}. The bot leaves it alone.\n"
    )


@WITH_JQ
def test_the_bot_leaves_a_release_alone_that_started_again_in_the_meantime(
    tmp_path: Path,
) -> None:
    # It started again between the look at the run and the rerun.
    refused = "run 77 cannot be rerun; This workflow is already running\n"
    done = rerun_the_release(
        tmp_path, "completed", 1, exact("run rerun 77 --failed", code=1, err=refused)
    )

    assert done.returncode == 0, done.stderr
    assert done.summary == (
        "The release of abc1234 runs again already; the bot leaves it alone.\n"
    )


@WITH_JQ
def test_the_bot_for_failed_releases_fails_when_github_refuses_otherwise(
    tmp_path: Path,
) -> None:
    refused = "HTTP 403: Resource not accessible by integration\n"
    done = rerun_the_release(
        tmp_path, "completed", 1, exact("run rerun 77 --failed", code=1, err=refused)
    )

    assert done.returncode == 1
    assert refused in done.stderr
    assert done.summary == ""


# The assets of a release.


@WITH_JQ
def test_the_assets_go_to_the_draft_with_their_provenance(tmp_path: Path) -> None:
    envelope = {"payload": "e30=", "payloadType": "application/vnd.in-toto+json"}
    runner = (tmp_path / "runner").as_posix()
    done = run_step(
        tmp_path,
        "build-release.yml",
        "assets",
        "Attach the assets and their signed provenance to the draft",
        answers=[Answer(r"release upload v1\.2\.0 .* --clobber --repo o/r")],
        env={
            "TAG": "v1.2.0",
            "BUNDLE_PATH": f"{runner}/bundle.json",
            "ASSETS": f"{runner}/assets",
        },
        files={
            "$RUNNER_TEMP/bundle.json": json.dumps({"dsseEnvelope": envelope}),
            "$RUNNER_TEMP/assets/app-1.2.0.tar.gz": "the package",
        },
    )

    assert done.returncode == 0, done.stderr
    assets = f"{runner}/assets"
    assert done.commands == [
        f"release upload v1.2.0 {assets}/app-1.2.0.tar.gz"
        f" {assets}/provenance.intoto.jsonl {assets}/provenance.sigstore.json"
        " --clobber --repo o/r"
    ]
    statement = (tmp_path / "runner/assets/provenance.intoto.jsonl").read_text()
    assert json.loads(statement) == envelope


# The key and the token of a Nextcloud app, each in an environment of its own (#530).

OPENSSL = shutil.which("openssl")
WITH_OPENSSL = pytest.mark.skipif(OPENSSL is None, reason="needs openssl")
APP_ID = "demoapp"
PYTHON3 = {"python3": f'exec "{Path(sys.executable).as_posix()}" "$@"\n'}
SIGN_THE_APP_ID = "Check the certificate and sign the app id"
REGISTER_THE_APP_ID = "Register the app id with its certificate"
NOT_HANDED_OVER = (
    "::error::The job sign the app id handed over no app id, certificate or signature."
)


def test_the_build_signs_no_nextcloud_app_without_the_key_of_its_environment(
    tmp_path: Path,
) -> None:
    # Without the key of the environment signing, which takes the place of the empty
    # value that release.yml passes, the release stops here, before anything signs.
    done = run_step(
        tmp_path,
        "build-release.yml",
        "assets",
        "Sign the Nextcloud app",
        env={"APP_ID": APP_ID, "APP_PRIVATE_KEY": ""},
        stubs={"php": recording("php"), "openssl": recording("openssl")},
    )

    assert done.returncode == 1
    assert (
        "::error::The build got no APP_PRIVATE_KEY: set it as a secret of the"
        " environment signing, and let the job assets of release.yml pass it"
        " under secrets:"
    ) in done.stdout
    # A release has shown that GitHub takes the key of signing, and release holds no
    # copy of it any more (#530), so the error advises no revert to it.
    assert (
        " The secret of the environment takes the place of the empty value passed"
        " (decision 0114, #530)."
    ) in done.stdout
    assert "revert" not in done.stdout
    assert done.stubbed == []
    assert list(done.runner_temp.iterdir()) == []


@pytest.fixture(scope="module")
def app_keys(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    """The key of the app with the certificate that Nextcloud issued for its id, and
    those of another app, by the names of their files."""
    assert OPENSSL
    folder = tmp_path_factory.mktemp("keys")
    for name, app_id in (("app", APP_ID), ("other", "otherapp")):
        subprocess.run(
            [
                OPENSSL,
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                str(folder / f"{name}.key"),
                "-out",
                str(folder / f"{name}.crt"),
                "-subj",
                f"/CN={app_id}",
                "-days",
                "2",
            ],
            check=True,
            capture_output=True,
        )
    return {path.name: path.read_text(encoding="utf-8") for path in folder.iterdir()}


def sign_the_app_id(
    tmp_path: Path, certificate: str, *, key: str, confirmation: str = APP_ID
) -> StepResult:
    """Runs the step of the job sign of register-app.yml, whose curl downloads the
    certificate."""
    issued = tmp_path / "issued.crt"
    issued.write_text(certificate, encoding="utf-8", newline="\n")
    download = (
        'while (($#)); do [[ "$1" == --output ]] && out="$2"; shift; done\n'
        f'cp "{issued.as_posix()}" "$out"'
    )
    return run_step(
        tmp_path,
        "register-app.yml",
        "sign",
        SIGN_THE_APP_ID,
        env={"APP_PRIVATE_KEY": key, "CONFIRMATION": confirmation},
        stubs={**PYTHON3, "curl": recording("curl", download)},
        files={"appinfo/info.xml": f"<info>\n  <id>{APP_ID}</id>\n</info>\n"},
    )


@WITH_OPENSSL
def test_the_app_id_is_signed_in_the_environment_of_the_key_alone(
    tmp_path: Path, app_keys: dict[str, str]
) -> None:
    # A job enters one environment: the key signs in signing, and the token posts in
    # appstore, so that neither job holds both, nor the key of the release app.
    sign, register = (
        job("register-app.yml", "sign"),
        job("register-app.yml", "register"),
    )
    assert sign["environment"] == {"name": "signing", "deployment": False}
    assert register["environment"] == {"name": "appstore", "deployment": False}
    assert register["needs"] == "sign"
    handed_over = ("app-id", "certificate", "signature")
    assert sign["outputs"] == {
        name: f"${{{{ steps.sign.outputs.{name} }}}}" for name in handed_over
    }
    assert {
        name: step_in(register, REGISTER_THE_APP_ID)["env"][name]
        for name in ("APP_ID", "CERTIFICATE", "SIGNATURE")
    } == {
        "APP_ID": "${{ needs.sign.outputs.app-id }}",
        "CERTIFICATE": "${{ needs.sign.outputs.certificate }}",
        "SIGNATURE": "${{ needs.sign.outputs.signature }}",
    }

    done = sign_the_app_id(tmp_path, app_keys["app.crt"], key=app_keys["app.key"])

    assert done.returncode == 0, done.stdout + done.stderr
    assert len(done.stubbed) == 1
    assert done.stubbed[0].endswith(
        f"https://raw.githubusercontent.com/nextcloud/app-certificate-requests/master/{APP_ID}/{APP_ID}.crt"
    )
    assert done.outputs["app-id"] == APP_ID
    # The certificate as it came, and the app id signed by the key that it names.
    certificate = base64.b64decode(done.outputs["certificate"]).decode()
    assert certificate == app_keys["app.crt"]
    (tmp_path / "app.crt").write_text(certificate, encoding="utf-8", newline="\n")
    (tmp_path / "app-id").write_bytes(APP_ID.encode())
    (tmp_path / "signature").write_bytes(base64.b64decode(done.outputs["signature"]))
    assert OPENSSL
    public = subprocess.run(
        [OPENSSL, "x509", "-in", str(tmp_path / "app.crt"), "-pubkey", "-noout"],
        check=True,
        capture_output=True,
    ).stdout
    (tmp_path / "app.pub").write_bytes(public)
    verified = subprocess.run(
        [
            OPENSSL,
            "dgst",
            "-sha512",
            "-verify",
            str(tmp_path / "app.pub"),
            "-signature",
            str(tmp_path / "signature"),
            str(tmp_path / "app-id"),
        ],
        capture_output=True,
        check=False,
    )
    assert verified.returncode == 0, verified.stderr
    # Neither the key nor the certificate stays on the runner.
    assert list(done.runner_temp.iterdir()) == []


@WITH_OPENSSL
def test_a_key_that_the_certificate_doesnt_name_signs_nothing(
    tmp_path: Path, app_keys: dict[str, str]
) -> None:
    done = sign_the_app_id(tmp_path, app_keys["app.crt"], key=app_keys["other.key"])

    assert done.returncode == 1
    assert (
        f"::error::APP_PRIVATE_KEY is not the key of the certificate of {APP_ID}."
        in done.stdout
    )
    assert done.outputs == {}
    assert list(done.runner_temp.iterdir()) == []


@WITH_OPENSSL
def test_a_certificate_of_another_app_signs_nothing(
    tmp_path: Path, app_keys: dict[str, str]
) -> None:
    done = sign_the_app_id(tmp_path, app_keys["other.crt"], key=app_keys["other.key"])

    assert done.returncode == 1
    assert done.outputs == {}
    assert list(done.runner_temp.iterdir()) == []


@pytest.mark.parametrize(
    ("key", "confirmation", "error"),
    [
        (
            "",
            APP_ID,
            "::error::The environment signing needs the secret APP_PRIVATE_KEY.",
        ),
        ("a key", "otherapp", f"::error::Confirm with the id of the app, {APP_ID}."),
    ],
)
def test_no_app_id_is_signed_without_the_key_or_the_confirmation(
    tmp_path: Path, key: str, confirmation: str, error: str
) -> None:
    done = sign_the_app_id(tmp_path, "", key=key, confirmation=confirmation)

    assert done.returncode == 1
    assert error in done.stdout
    assert done.stubbed == []
    assert done.outputs == {}


def register_the_app_id(tmp_path: Path, **env: str) -> tuple[StepResult, Path]:
    """Runs the step of the job register of register-app.yml, whose curl keeps the
    request that it posts."""
    request = tmp_path / "request.json"
    post = (
        'while (($#)); do [[ "$1" == --data-binary ]] && body="${2#@}"; shift; done\n'
        f'cp "$body" "{request.as_posix()}"'
    )
    done = run_step(
        tmp_path,
        "register-app.yml",
        "register",
        REGISTER_THE_APP_ID,
        env=env,
        stubs={"curl": recording("curl", post)},
    )
    return done, request


@WITH_JQ
@WITH_OPENSSL
def test_the_app_store_gets_the_certificate_with_the_signed_app_id(
    tmp_path: Path,
) -> None:
    certificate = "-----BEGIN CERTIFICATE-----\nMIIBdemo\n-----END CERTIFICATE-----\n"
    done, request = register_the_app_id(
        tmp_path,
        APPSTORE_TOKEN="the token",
        APP_ID=APP_ID,
        CERTIFICATE=base64.b64encode(certificate.encode()).decode(),
        SIGNATURE="c2lnbmVk",
    )

    assert done.returncode == 0, done.stdout + done.stderr
    runner = done.runner_temp.as_posix()
    assert done.stubbed == [
        "curl --fail-with-body --silent --show-error --request POST"
        " --header Authorization: Token the token"
        " --header Content-Type: application/json"
        f" --data-binary @{runner}/request.json https://apps.nextcloud.com/api/v1/apps"
    ]
    assert json.loads(request.read_text(encoding="utf-8")) == {
        "certificate": certificate,
        "signature": "c2lnbmVk",
    }
    assert f"Registered {APP_ID} in the Nextcloud App Store." in done.summary
    assert list(done.runner_temp.iterdir()) == []


@pytest.mark.parametrize(
    ("missing", "error"),
    [
        (
            "APPSTORE_TOKEN",
            "::error::The environment appstore needs the secret APPSTORE_TOKEN.",
        ),
        ("APP_ID", NOT_HANDED_OVER),
        ("CERTIFICATE", NOT_HANDED_OVER),
        ("SIGNATURE", NOT_HANDED_OVER),
    ],
)
def test_nothing_is_registered_without_the_token_or_all_that_the_key_signed(
    tmp_path: Path, missing: str, error: str
) -> None:
    # GitHub hands on no output of a job that it takes for a secret: it arrives empty.
    env = {
        "APPSTORE_TOKEN": "the token",
        "APP_ID": APP_ID,
        "CERTIFICATE": "Y2VydGlmaWNhdGU=",
        "SIGNATURE": "c2lnbmVk",
    }
    done, request = register_the_app_id(tmp_path, **{**env, missing: ""})

    assert done.returncode == 1
    assert error in done.stdout
    assert done.stubbed == []
    assert not request.exists()


# A beta of a Nextcloud app reaches the App Store with its own version, never in the
# place of the last release (#635): the App Store takes the version of a release from
# the appinfo/info.xml in its package and updates a release of that version.

INFO_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<info xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
\t<id>demoapp</id>
\t<name>Démo</name>
\t<!-- The version that release-please writes. -->
\t<version>1.4.0</version>
\t<dependencies>
\t\t<php min-version="8.2"/>
\t\t<nextcloud min-version="31" max-version="33"/>
\t</dependencies>
</info>
"""
# The info.xml of the package, which the build unpacks to sign it.
UNPACKED_INFO_XML = f"$RUNNER_TEMP/signing/{APP_ID}/appinfo/info.xml"
WRITE_THE_VERSION = "Write the version of the release into the Nextcloud app"
CHECK_THE_VERSION = "Check the version of the signed Nextcloud app"
SUBMIT_THE_PACKAGE = "Submit the signed package of the public release"
APP_BETA = "1.5.0-beta.1"


def info_xml(version: str) -> str:
    """The info.xml of the app at the version."""
    return INFO_XML.replace("<version>1.4.0</version>", f"<version>{version}</version>")


def app_package(info: str | None) -> bytes:
    """The package of the app, as krankerl and the signing pack it: a tar.gz with the
    folder of its id, and the info.xml unless it is None."""
    data = io.BytesIO()
    files = {f"{APP_ID}/lib/Application.php": "<?php\n"}
    if info is not None:
        files[f"{APP_ID}/appinfo/info.xml"] = info
    with tarfile.open(fileobj=data, mode="w:gz") as archive:
        for name, text in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(text.encode())
            archive.addfile(member, io.BytesIO(text.encode()))
    return data.getvalue()


def write_the_version(tmp_path: Path, version: str, info: str = INFO_XML) -> StepResult:
    """Runs the step of the build that writes the version of the release into the
    unpacked package and the checkout, which both have the info.xml of the tag."""
    return run_step(
        tmp_path,
        "build-release.yml",
        "assets",
        WRITE_THE_VERSION,
        env={"APP_ID": APP_ID, "VERSION": version},
        stubs=PYTHON3,
        files={"appinfo/info.xml": info, UNPACKED_INFO_XML: info},
    )


@pytest.mark.parametrize(
    "version",
    [
        # A beta of main, whose info.xml still has the version of the last release.
        APP_BETA,
        # A release, whose version release-please has written into the info.xml.
        "1.4.0",
    ],
)
def test_the_package_of_a_nextcloud_app_has_the_version_of_its_release(
    tmp_path: Path, version: str
) -> None:
    done = write_the_version(tmp_path, version)

    assert done.returncode == 0, done.stdout + done.stderr
    # Only the version changes, before the signature covers it, and in the checkout
    # too, which the project's own check of its signed package may compare with it.
    for written in (
        done.workspace / "appinfo/info.xml",
        done.runner_temp / f"signing/{APP_ID}/appinfo/info.xml",
    ):
        assert written.read_bytes() == info_xml(version).encode()


@pytest.mark.parametrize(
    "info",
    [
        INFO_XML.replace("\t<version>1.4.0</version>\n", ""),
        INFO_XML.replace("</info>", "\t<version>1.4.0</version>\n</info>"),
        INFO_XML.replace("<version>1.4.0</version>", "<version>1.4.0"),
    ],
    ids=["without a version", "with two versions", "not XML"],
)
def test_no_nextcloud_app_is_signed_whose_version_cant_be_written(
    tmp_path: Path, info: str
) -> None:
    done = write_the_version(tmp_path, APP_BETA, info)

    assert done.returncode == 1
    assert (
        f"::error::The appinfo/info.xml of {APP_ID} has no single version that the"
        f" build can set to {APP_BETA}, so the App Store would take its package for"
        " another release (#635)."
    ) in done.stdout
    assert (done.workspace / "appinfo/info.xml").read_text(encoding="utf-8") == info


def check_the_version(tmp_path: Path, info: str | None) -> StepResult:
    """Runs the check of the build after the signing, of the package with the info.xml,
    for the beta."""
    assets = tmp_path / "runner/assets"
    assets.mkdir(parents=True)
    (assets / f"{APP_ID}.tar.gz").write_bytes(app_package(info))
    return run_step(
        tmp_path,
        "build-release.yml",
        "assets",
        CHECK_THE_VERSION,
        env={"APP_ID": APP_ID, "VERSION": APP_BETA, "ASSETS": assets.as_posix()},
        stubs=PYTHON3,
    )


def test_the_signed_package_of_a_nextcloud_app_has_the_version_of_its_release(
    tmp_path: Path,
) -> None:
    done = check_the_version(tmp_path, info_xml(APP_BETA))

    assert done.returncode == 0, done.stdout + done.stderr
    assert "::error::" not in done.stdout


@pytest.mark.parametrize(
    ("info", "found"),
    [(INFO_XML, "1.4.0"), (None, "none"), ("<info>", "none")],
    ids=["of the last release", "without an info.xml", "not XML"],
)
def test_no_signed_package_of_another_version_becomes_a_release(
    tmp_path: Path, info: str | None, found: str
) -> None:
    done = check_the_version(tmp_path, info)

    assert done.returncode == 1
    assert (
        f"::error::The appinfo/info.xml in {APP_ID}.tar.gz has the version {found},"
        f" not {APP_BETA}, so the App Store would take the package for another release"
        " (#635)."
    ) in done.stdout


def submit_the_package(
    tmp_path: Path, tag: str, info: str | None
) -> tuple[StepResult, Path]:
    """Runs the delivery to the App Store of the release of the tag, in the checkout of
    the tag, whose info.xml still says 1.4.0 for a beta, with the package that the
    release attaches, and returns its result and the request that curl posts."""
    checkout = tmp_path / "checkout"
    (checkout / "appinfo").mkdir(parents=True)
    (checkout / "appinfo/info.xml").write_text(INFO_XML, encoding="utf-8", newline="\n")
    # What gh release download brings.
    (checkout / f"{APP_ID}.tar.gz").write_bytes(app_package(info))
    (checkout / f"{APP_ID}.tar.gz.sig").write_bytes(b"signed")
    request = tmp_path / "request.json"
    post = (
        'while (($#)); do [[ "$1" == --data-binary ]] && body="${2#@}"; shift; done\n'
        f'cp "$body" "{request.as_posix()}"'
    )
    done = run_step(
        tmp_path,
        "release.yml",
        "nextcloud-appstore",
        SUBMIT_THE_PACKAGE,
        answers=[
            exact(
                f"release download {tag} --repo o/r --pattern {APP_ID}.tar.gz"
                f" --pattern {APP_ID}.tar.gz.sig"
            )
        ],
        env={"APPSTORE_TOKEN": "the token", "GH_TOKEN": "a token", "TAG": tag},
        stubs={
            **PYTHON3,
            "curl": recording("curl", post),
            "openssl": recording("openssl", "printf c2lnbmVk"),
        },
        workspace=checkout,
    )
    return done, request


@WITH_JQ
@pytest.mark.parametrize(
    ("version", "offered"),
    [
        (
            APP_BETA,
            f"The App Store offers {APP_ID} {APP_BETA} only to servers on the beta"
            " channel of Nextcloud.",
        ),
        ("1.4.0", f"The App Store offers {APP_ID} 1.4.0 to every server it fits."),
    ],
)
def test_the_app_store_gets_a_package_of_the_version_of_its_tag(
    tmp_path: Path, version: str, offered: str
) -> None:
    tag = f"v{version}"
    done, request = submit_the_package(tmp_path, tag, info_xml(version))

    assert done.returncode == 0, done.stdout + done.stderr
    # A beta is no nightly: the pre-release identifier of its version marks it.
    assert json.loads(request.read_text(encoding="utf-8")) == {
        "download": f"https://github.com/o/r/releases/download/{tag}/{APP_ID}.tar.gz",
        "signature": "c2lnbmVk",
        "nightly": False,
    }
    assert offered in done.summary


@pytest.mark.parametrize(
    ("info", "found"),
    [(INFO_XML, "1.4.0"), (None, "none")],
    ids=["of the last release", "without an info.xml"],
)
def test_the_app_store_gets_no_package_of_another_version_than_its_tag(
    tmp_path: Path, info: str | None, found: str
) -> None:
    # A beta whose package still says the last release would replace that release
    # for every user, as the App Store updates the release of the same version.
    done, request = submit_the_package(tmp_path, f"v{APP_BETA}", info)

    assert done.returncode == 1
    assert (
        f"::error::The appinfo/info.xml in {APP_ID}.tar.gz has the version {found},"
        f" not {APP_BETA}, so the App Store would take the package for another release"
        " (#635)."
    ) in done.stdout
    assert not [call for call in done.stubbed if call.startswith("curl ")]
    assert not request.exists()


@pytest.mark.parametrize("tool", ["blueprint.py", ".github/blueprint.py"])
def test_the_notes_of_a_release_are_its_section_of_the_changelog(
    tmp_path: Path, tool: str
) -> None:
    done = run_step(
        tmp_path,
        "build-release.yml",
        "assets",
        "Write the notes, the section of the changelog with every pull request",
        answers=[
            exact("release view v1.2.0 --repo o/r --json body --jq .body", "* #12\n"),
            Answer(r"release edit v1\.2\.0 --repo o/r --notes-file \S+/notes\.md"),
        ],
        env={"TAG": "v1.2.0", "VERSION": "1.2.0"},
        stubs={"python3": recording("python3", 'echo "The section of 1.2.0"')},
        files={".github/blueprint.py": ""} if tool.startswith(".github") else {},
    )

    assert done.returncode == 0, done.stderr
    runner = done.runner_temp.as_posix()
    assert done.stubbed == [
        f"python3 {tool} changelog notes 1.2.0 CHANGELOG.md {runner}/pull-requests.md"
    ]
    assert (done.runner_temp / "pull-requests.md").read_text() == "* #12\n"
    assert done.read_by("release edit", "--notes-file") == ["The section of 1.2.0\n"]


# The bots of pictures, which keep one pull request of their own.

PICTURE_BOTS = [
    pytest.param(
        "docs-pictures.yml",
        "Open, update or close the pull request of the pictures",
        "bot/pictures",
        "docs: renew the pictures",
        id="docs-pictures",
    ),
    pytest.param(
        "screenshot-bot.yml",
        "Open, update or close the pull request of the screenshots",
        "bot/screenshots",
        "docs: update the screenshots",
        id="screenshots",
    ),
]
# How the bots ask GitHub what main changed since the commit that was rendered, and
# two answers: no change, and one of a picture of the pull request.
COMPARED = "{behind_by, files: [.files[]? | {filename, previous_filename}]}"
NO_CHANGE = '{"behind_by":0,"files":[]}\n'
MERGED = '{"behind_by":0,"files":[{"filename":"docs/images/a.gif"}]}\n'
# The tool of the bots: whether main changed a file of the pull request meanwhile, two
# commits for the pictures, the JSON of each part's commit, and the report.
PICTURE_TOOL = recording(
    "python3",
    """case "$*" in
  *"screenshots overtaken"*) echo "main changed none of them."; exit 3 ;;
  *"screenshots parts"*) echo 2 ;;
  *"screenshots commit"*) echo "{\\"part\\": \\"${!#}\\"}" ;;
  *"screenshots report"*) echo "The report" ;;
esac""",
)


@pytest.mark.parametrize(("name", "title", "branch", "headline"), PICTURE_BOTS)
@pytest.mark.parametrize("open_number", ["4", ""])
def test_a_picture_bot_closes_its_pull_request_once_main_looks_as_rendered(
    tmp_path: Path,
    name: str,
    title: str,
    branch: str,
    headline: str,
    open_number: str,
) -> None:
    done = run_step(
        tmp_path,
        name,
        "pull-request",
        title,
        answers=[
            Answer(rf"pr list --head {branch} --state open .*", f"{open_number}\n"),
            Answer(r"pr close 4 --delete-branch --comment .*"),
        ],
        env={
            "GH_TOKEN": "app-token",
            "APP_SLUG": "the-app",
            "STALE": "false",
            "SHA": SHA,
        },
    )

    assert done.returncode == 0, done.stderr
    assert done.called("pr close") == (
        [
            "pr close 4 --delete-branch --comment"
            f" `main` looks as rendered without this pull request: {RUN_URL}"
        ]
        if open_number
        else []
    )
    assert ("closed #4" in done.summary) == bool(open_number)
    assert len(done.calls) == 1 + bool(open_number)


@pytest.mark.parametrize(("name", "title", "branch", "headline"), PICTURE_BOTS)
@pytest.mark.parametrize("open_number", ["4", ""])
def test_a_picture_bot_commits_on_a_branch_of_its_own_and_merges_itself(
    tmp_path: Path,
    name: str,
    title: str,
    branch: str,
    headline: str,
    open_number: str,
) -> None:
    scratch = f"{branch}-next"
    done = run_step(
        tmp_path,
        name,
        "pull-request",
        title,
        answers=[
            Answer(rf"pr list --head {branch} --state open .*", f"{open_number}\n"),
            exact(f"api repos/o/r/compare/{SHA}...main --jq {COMPARED}", NO_CHANGE),
            # A scratch branch that a failed run left behind, and the branch of the
            # pull request, which exists while it is open.
            exact(f"api repos/o/r/git/ref/heads/{scratch}", "{}"),
            exact(
                f"api repos/o/r/git/ref/heads/{branch}",
                "{}" if open_number else "",
                code=0 if open_number else 1,
                err="" if open_number else "gh: Not Found (HTTP 404)",
            ),
            Answer(r"api --method (POST|PATCH|DELETE) repos/o/r/git/refs.*"),
            exact("api users/the-app[bot] --jq .id", "123\n"),
            Answer(r"api graphql --input \S+/commit\.json --jq .*", "c1\n", once=True),
            Answer(r"api graphql --input \S+/commit\.json --jq .*", "c2\n"),
            Answer(
                rf"pr create --base main --head {branch} --title {headline}"
                r" --body-file \S+/body\.md",
                "https://github.com/o/r/pull/8\n",
            ),
            Answer(rf"pr edit 4 --title {headline} --body-file \S+/body\.md"),
            Answer(r"pr merge \d+ --auto --squash"),
        ],
        env={
            "GH_TOKEN": "app-token",
            "APP_SLUG": "the-app",
            "STALE": "true",
            "SHA": SHA,
        },
        stubs={"python3": PICTURE_TOOL},
    )

    assert done.returncode == 0, done.stderr
    number = open_number or "8"
    refs = [call for call in done.commands if call.startswith("api --method")]
    moved = (
        f"api --method PATCH repos/o/r/git/refs/heads/{branch} -f sha=c2 -F force=true"
        if open_number
        else f"api --method POST repos/o/r/git/refs -f ref=refs/heads/{branch} -f sha=c2"
    )
    # The scratch branch starts anew from the commit that was rendered, takes the
    # commits, and the branch of the pull request moves to the last one in one step.
    assert refs == [
        f"api --method DELETE repos/o/r/git/refs/heads/{scratch}",
        f"api --method POST repos/o/r/git/refs -f ref=refs/heads/{scratch} -f sha={SHA}",
        moved,
        f"api --method DELETE repos/o/r/git/refs/heads/{scratch}",
    ]
    # One commit for each part, the second on the first.
    assert done.read_by("api graphql", "--input") == [
        '{"part": "1"}\n',
        '{"part": "2"}\n',
    ]
    commits = "\n".join(done.stubbed)
    assert f"--head {SHA} --headline {headline}" in commits
    assert f"--head c1 --headline {headline}" in commits
    assert (
        "Signed-off-by: the-app[bot] <123+the-app[bot]@users.noreply.github.com>"
        in commits
    )
    assert bool(done.called("pr create")) == (not open_number)
    assert bool(done.called("pr edit")) == bool(open_number)
    assert done.read_by("pr (create|edit)", "--body-file") == ["The report\n"]
    assert done.commands[-1] == f"pr merge {number} --auto --squash"
    assert f"#{number} from {branch}, has the commit c2" in done.summary
    assert "python3 blueprint.py --repo o/r screenshots parts" in commits
    # It asked first whether main changed a file of the pull request meanwhile.
    assert done.commands[1] == f"api repos/o/r/compare/{SHA}...main --jq {COMPARED}"
    assert "screenshots overtaken" in done.stubbed[0]
    assert "--compared" in done.stubbed[0]
    assert "main changed none of them." in done.summary


@pytest.mark.parametrize(("name", "title", "branch", "headline"), PICTURE_BOTS)
@pytest.mark.parametrize("open_number", ["4", ""])
def test_a_picture_bot_renders_main_anew_when_main_changed_its_files_meanwhile(
    tmp_path: Path,
    name: str,
    title: str,
    branch: str,
    headline: str,
    open_number: str,
) -> None:
    # paperless-unified-search#316: the render of a release ran while the pull request
    # before it merged with the same pictures, and the bot opened one from the commit
    # of the release, which conflicted. Now the bot starts a run that renders main
    # anew, and leaves the branch and the pull request as they are.
    dispatch = f"api --method POST repos/o/r/actions/workflows/{name}/dispatches"
    done = run_step(
        tmp_path,
        name,
        "pull-request",
        title,
        answers=[
            Answer(rf"pr list --head {branch} --state open .*", f"{open_number}\n"),
            exact(f"api repos/o/r/compare/{SHA}...main --jq {COMPARED}", MERGED),
            exact(f"{dispatch} -f ref=main"),
        ],
        env={
            "GH_TOKEN": "app-token",
            "APP_SLUG": "the-app",
            "STALE": "true",
            "SHA": SHA,
        },
        stubs={
            "python3": recording(
                "python3", 'echo "main changed a.gif since the commit."; exit 0'
            )
        },
    )

    assert done.returncode == 0, done.stderr
    assert done.commands[1:] == [
        f"api repos/o/r/compare/{SHA}...main --jq {COMPARED}",
        f"{dispatch} -f ref=main",
    ]
    assert "main changed a.gif since the commit." in done.summary
    assert "renders main anew" in done.summary


@pytest.mark.parametrize("status", [1, 2])
@pytest.mark.parametrize(("name", "title", "branch", "headline"), PICTURE_BOTS)
def test_a_picture_bot_fails_when_its_tool_cant_tell_whether_main_moved(
    tmp_path: Path, name: str, title: str, branch: str, headline: str, status: int
) -> None:
    done = run_step(
        tmp_path,
        name,
        "pull-request",
        title,
        answers=[
            Answer(rf"pr list --head {branch} --state open .*", "\n"),
            exact(f"api repos/o/r/compare/{SHA}...main --jq {COMPARED}", NO_CHANGE),
        ],
        env={
            "GH_TOKEN": "app-token",
            "APP_SLUG": "the-app",
            "STALE": "true",
            "SHA": SHA,
        },
        # An error that the tool does not catch exits 1, which is no answer either.
        stubs={"python3": recording("python3", f"exit {status}")},
    )

    assert done.returncode == 1
    assert len(done.calls) == 2


@WITH_JQ
@pytest.mark.parametrize(("name", "title", "branch", "headline"), PICTURE_BOTS)
def test_a_picture_bot_takes_only_its_own_pull_request(
    tmp_path: Path, name: str, title: str, branch: str, headline: str
) -> None:
    done = run_step(
        tmp_path,
        name,
        "pull-request",
        title,
        answers=[
            Answer(
                rf"pr list --head {branch} --state open .*",
                json=[
                    # From a fork's branch of the same name, and of a person.
                    {
                        "number": 3,
                        "isCrossRepository": True,
                        "author": {"login": "app/the-app"},
                    },
                    {
                        "number": 4,
                        "isCrossRepository": False,
                        "author": {"login": "someone"},
                    },
                    {
                        "number": 5,
                        "isCrossRepository": False,
                        "author": {"login": "app/the-app"},
                    },
                ],
            ),
            Answer(r"pr close 5 .*"),
        ],
        env={
            "GH_TOKEN": "app-token",
            "APP_SLUG": "the-app",
            "STALE": "false",
            "SHA": SHA,
        },
    )

    assert done.returncode == 0, done.stderr
    assert [call.split(" --")[0] for call in done.called("pr close")] == ["pr close 5"]


# The bots that open, keep and close an issue or comment.


@pytest.mark.parametrize(
    ("exit_code", "open_number", "call"),
    [
        ("0", "", None),
        (
            "0",
            "9",
            "issue close 9 --comment The weekly check finds no broken link any more.",
        ),
        ("2", "9", "issue edit 9 --body "),
        (
            "2",
            "",
            "issue create --title Broken links in the documentation --label documentation --body ",
        ),
    ],
)
def test_the_link_check_keeps_one_issue_of_broken_links(
    tmp_path: Path, exit_code: str, open_number: str, call: str | None
) -> None:
    # The check, which reaches every host that the documents link to, only reads; a
    # job of its own after the weekly run writes the issue, and blocks every host but
    # GitHub's.
    assert job("links.yml", "links")["permissions"] == {"contents": "read"}
    assert job("links.yml", "links")["outputs"] == {
        "exit-code": "${{ steps.lychee.outputs.exit_code }}"
    }
    kept = step("links.yml", "links", "Keep the report of the broken links")
    assert kept["if"] == (
        "github.event_name == 'schedule' && steps.lychee.outputs.exit_code != '0'"
    )
    assert kept["uses"].startswith("actions/upload-artifact@")
    assert kept["with"]["name"] == "links"
    assert kept["with"]["path"] == "${{ runner.temp }}/links.md"
    issue = job("links.yml", "issue")
    assert issue["needs"] == "links"
    assert issue["if"] == "github.event_name == 'schedule'"
    assert issue["permissions"] == {"issues": "write"}
    taken = step("links.yml", "issue", "Take the report of the broken links")
    assert taken["if"] == "needs.links.outputs.exit-code != '0'"
    assert taken["with"] == {"name": "links", "path": "${{ runner.temp }}"}
    report = step("links.yml", "issue", "Keep the issue of broken links current")
    assert "if" not in report
    assert report["env"]["EXIT_CODE"] == "${{ needs.links.outputs.exit-code }}"
    assert report["env"]["REPORT"] == "${{ runner.temp }}/links.md"

    done = run_step(
        tmp_path,
        "links.yml",
        "issue",
        "Keep the issue of broken links current",
        answers=[
            Answer(r"issue list --state open --search .*", f"{open_number}\n"),
            Answer(r"issue (close|edit|create) .*"),
        ],
        env={"EXIT_CODE": exit_code},
        files={"$RUNNER_TEMP/links.md": "- [404] https://example.com/gone\n"},
    )

    assert done.returncode == 0, done.stderr
    changed = done.called("issue (close|edit|create)")
    assert len(changed) == (call is not None)
    if call:
        assert changed[0].startswith(call)
    if exit_code != "0":
        assert changed[0].endswith(
            "list them in .lycheeignore with the reason.\n\n"
            "- [404] https://example.com/gone"
        )


def test_the_weekly_report_is_posted_in_the_general_discussions(
    tmp_path: Path,
) -> None:
    assert job("weekly-report.yml", "report")["if"] == (
        "github.repository == 'Dennis-Otto/repo-blueprint'"
    )
    done = run_step(
        tmp_path,
        "weekly-report.yml",
        "report",
        "Post it in the discussions",
        answers=[
            Answer(
                r"api graphql -F owner=o -F name=r -f query=query.*discussionCategories.*",
                "R_1 DIC_2\n",
            ),
            Answer(
                r"api graphql -F owner=o -F name=r -f query=query.*discussions\(.*",
                "The week before\n",
            ),
            Answer(
                r"api graphql -F repository=R_1 -F category=DIC_2 -F title=The week"
                r" -F body=@\S+/report\.md -f query=mutation.* --jq .*",
                "https://github.com/o/r/discussions/9\n",
            ),
        ],
        env={"TITLE": "The week"},
        files={"$RUNNER_TEMP/report.md": "# The week\n"},
    )

    assert done.returncode == 0, done.stderr
    assert '| select(.name == "General") |' in done.commands[0]
    assert done.read_by("api graphql -F repository", "-F body") == ["# The week\n"]
    assert done.stdout == "https://github.com/o/r/discussions/9\n"


def test_a_second_try_of_the_weekly_report_does_not_post_it_again(
    tmp_path: Path,
) -> None:
    # A job that hung after its last step runs once more.
    done = run_step(
        tmp_path,
        "weekly-report.yml",
        "report",
        "Post it in the discussions",
        answers=[
            Answer(
                r"api graphql -F owner=o -F name=r -f query=query.*discussionCategories.*",
                "R_1 DIC_2\n",
            ),
            Answer(
                r"api graphql -F owner=o -F name=r -f query=query.*discussions\(.*",
                "The week\nThe week before\n",
            ),
        ],
        env={"TITLE": "The week"},
        files={"$RUNNER_TEMP/report.md": "# The week\n"},
    )

    assert done.returncode == 0, done.stderr
    assert done.called("api graphql -F repository") == []
    assert done.stdout == "The report is posted already.\n"


def test_a_first_pull_request_is_welcomed_once(tmp_path: Path) -> None:
    settings = job("welcome.yml", "welcome")
    assert "github.event.pull_request.author_association" in settings["if"]
    assert settings["permissions"] == {"pull-requests": "write"}
    # A name can't run code in the comment.
    author = "octocat$(touch pwned)"

    done = run_step(
        tmp_path,
        "welcome.yml",
        "welcome",
        "Welcome the first pull request",
        answers=[Answer(r"pr comment 7 --body .*")],
        env={"NUMBER": "7", "AUTHOR": author},
    )

    assert done.returncode == 0, done.stderr
    [comment] = done.called("pr comment")
    assert f"Thank you for your first pull request, @{author}!" in comment
    assert "[CONTRIBUTING.md](../blob/main/CONTRIBUTING.md)" in comment
    assert not (done.workspace / "pwned").exists()


# The bot of the titles of pull requests.

MANAGED = [
    "enhancement",
    "bug",
    "documentation",
    "maintenance",
    "dependencies",
    "release",
    "breaking-change",
    "security",
    "translations",
]


@pytest.mark.parametrize(
    ("title", "branch", "current", "wanted"),
    [
        ("feat: add a dark mode", "feat/dark", "", ["enhancement"]),
        ("fix(deps): update ruff", "renovate/ruff", "bug\nquestion", ["dependencies"]),
        (
            "feat(settings)!: drop the old",
            "feat/x",
            "enhancement",
            ["enhancement", "breaking-change"],
        ),
        (
            "chore: release 1.7.0",
            "release-please--branches--main",
            "maintenance",
            ["release"],
        ),
        ("docs(i18n): translate the README", "docs/i18n", "", ["translations"]),
        ("perf(security): compare in constant time", "perf/x", "", ["security"]),
        ("refactor: split the module", "refactor/x", "maintenance", ["maintenance"]),
        # A title is text of the pull request, never code of the step.
        ("fix: $(touch pwned) `touch pwned`", "fix/x", "", ["bug"]),
    ],
)
def test_the_title_sets_the_labels_of_its_kind_of_change(
    tmp_path: Path, title: str, branch: str, current: str, wanted: list[str]
) -> None:
    done = run_step(
        tmp_path,
        "pull-request-title.yml",
        "title",
        "Check the title and set the label",
        answers=[
            exact("pr view 7 --json labels --jq .labels[].name", current),
            Answer(r"pr edit 7 --(add|remove)-label \S+"),
        ],
        env={"NUMBER": "7", "TITLE": title, "BRANCH": branch},
    )

    assert done.returncode == 0, done.stderr
    has = set(current.split())
    assert sorted(done.called("pr edit")) == sorted(
        [f"pr edit 7 --add-label {label}" for label in wanted if label not in has]
        + [
            f"pr edit 7 --remove-label {label}"
            for label in has & set(MANAGED)
            if label not in wanted
        ]
    )
    assert done.summary == f"Labels: {' '.join(wanted)}\n"
    assert not (done.workspace / "pwned").exists()


def test_a_title_that_is_no_conventional_commit_fails_without_a_label(
    tmp_path: Path,
) -> None:
    done = run_step(
        tmp_path,
        "pull-request-title.yml",
        "title",
        "Check the title and set the label",
        env={"NUMBER": "7", "TITLE": "Update stuff", "BRANCH": "patch-1"},
    )

    assert done.returncode == 1
    assert done.stdout.startswith("::error::Use a Conventional Commit title")
    assert done.calls == []


# What brings back a test that reads a workflow as text, or a fake gh of its own (#288):
# a helper that slices out a job, a step or a setting, a slice of the text at a job or
# at a line of a step, and an executable named gh that a test writes.
FORBIDDEN = {
    "a helper that slices workflow text": re.compile(
        r"^def (?:job_of|job_alone|jobs_of|steps_of|step_of|setting_of)\(", re.M
    ),
    "a slice of workflow text": re.compile(
        r"\.r?(?:index|find|split)\(\s*f?\"(?:\n)?  [a-z][\w-]*:\""
        r"|\.r?(?:index|find|split)\(\s*f?\" +(?:run: \||- name: |if: )"
    ),
    "a fake gh of its own": re.compile(r"/ \"gh\"\)|\{\"gh\": "),
}
# The one fake gh and the helpers that parse the workflows.
ALLOWED = {"fake_gh.py", "workflow_steps.py"}


def forbidden_in(text: str) -> list[str]:
    """Each line of the text of a test that reads a workflow as text or fakes gh on its
    own, with what it does."""
    return [
        f"{text.count(chr(10), 0, found.start()) + 1}: {what}"
        for what, pattern in FORBIDDEN.items()
        for found in pattern.finditer(text)
    ]


def test_the_guard_finds_what_slices_workflow_text_or_fakes_gh() -> None:
    # The samples, written so that the guard doesn't find them in this file: % is a
    # dot, ~ a space.
    samples = (
        "def job_of(text: str, job: str) -> str:\n"
        '    return text[text%index("  release:") :]\n'
        'step = job%split("      - name: Sign the tag")[1]\n'
        'run = job[job%rindex("        run: |") :]\n'
        '(bin_dir /~"gh").write_text(FAKE)\n'
        'stubs={"gh":~FAKE}\n'
    )
    assert forbidden_in(samples.replace("%", ".").replace("~", " ")) == [
        "1: a helper that slices workflow text",
        "2: a slice of workflow text",
        "3: a slice of workflow text",
        "4: a slice of workflow text",
        "5: a fake gh of its own",
        "6: a fake gh of its own",
    ]
    # A step that a test runs, and a job of the API, are fine.
    assert (
        forbidden_in(
            'run_step(tmp_path, "release.yml", "publish", "Make it public")\n'
            "def job_of_a_run(number: int) -> dict[str, object]:\n"
        )
        == []
    )


def test_no_test_slices_workflow_text_or_fakes_gh_on_its_own() -> None:
    # Parsed workflows and run_step() with the one fake gh, as CONTRIBUTING.md says.
    found = {
        path.name: forbidden_in(path.read_text(encoding="utf-8"))
        for path in sorted((ROOT / "tests").glob("*.py"))
        if path.name not in ALLOWED
    }
    assert {name: lines for name, lines in found.items() if lines} == {}


# composer audit --locked --format=json, as Composer 2 prints it, with an advisory or
# without one.
AUDIT_FOUND = json.dumps(
    {
        "advisories": {
            "symfony/filesystem": [
                {
                    "advisoryId": "PKSA-g499-cm4q-v35y",
                    "packageName": "symfony/filesystem",
                    "affectedVersions": "<7.4.23",
                }
            ]
        },
        "abandoned": {},
    }
)
AUDIT_CLEAN = json.dumps({"advisories": [], "abandoned": {}})


@pytest.mark.skipif(
    shutil.which("jq") is None, reason="the step reads the audit with jq"
)
@pytest.mark.parametrize(("report", "code"), [(AUDIT_FOUND, 1), (AUDIT_CLEAN, 0)])
def test_the_update_leg_updates_a_locked_package_that_an_advisory_names(
    tmp_path: Path, report: str, code: int
) -> None:
    composer = recording(
        "composer",
        f"if [[ $1 == audit ]]; then printf '%s\n' '{report}'; exit {code}; fi",
    )
    done = run_step(
        tmp_path,
        "variants.yml",
        "variant",
        "Update the locked packages that an advisory names, as Renovate does",
        env={"PROJECT": "variant"},
        stubs={"composer": composer},
        files={"variant/composer.lock": "{}\n"},
    )

    assert done.returncode == 0, done.stdout + done.stderr
    audit = "composer audit --locked --format=json --no-interaction"
    if code:
        # Only the named package, as Renovate's vulnerability alert updates it.
        assert done.stubbed == [
            audit,
            "composer update symfony/filesystem --with-dependencies --no-install "
            "--no-interaction",
        ]
        assert "symfony/filesystem" in done.summary
    else:
        assert done.stubbed == [audit]
        assert "No advisory names a locked package." in done.stdout


# The screenshot bot: the plan starts a run by hand, which names its commit and shards.


def test_a_due_plan_starts_the_run_that_renders(tmp_path: Path) -> None:
    # The runs by hand wait for each other in one group, so the plan of a push starts
    # one instead of rendering in its own run, which waits for nothing.
    dispatch = (
        "api --method POST repos/o/r/actions/workflows/screenshot-bot.yml/dispatches"
    )
    done = run_step(
        tmp_path,
        "screenshot-bot.yml",
        "plan",
        "Start the run that renders the pictures",
        answers=[exact(f"{dispatch} -f ref=main")],
        env={"GH_TOKEN": "job-token", "GH_REPO": "o/r"},
    )

    assert done.returncode == 0, done.stderr
    assert done.commands == [f"{dispatch} -f ref=main"]
    assert "started a run of this workflow by hand" in done.summary


@pytest.mark.parametrize(
    ("due", "code", "outputs"),
    [
        (
            0,
            0,
            {
                "due": "true",
                "sha": SHA,
                "shards": '[{"shard":"","id":"all"}]',
                "policy": "audit",
                "hosts": "",
            },
        ),
        # Without the script, nothing renders, and the run passes.
        (1, 0, {}),
        # An error of the tool fails the run.
        (2, 1, {}),
    ],
)
def test_the_start_names_the_newest_commit_and_the_shards(
    tmp_path: Path, due: int, code: int, outputs: dict[str, str]
) -> None:
    # The tool says whether the script is there, then prints the plan of the settings.
    tool = (
        f'if [[ "$3" == due ]]; then exit {due}; fi\n'
        """echo 'shards=[{"shard":"","id":"all"}]'\n"""
        "echo policy=audit\n"
        "echo hosts=\n"
    )
    done = run_step(
        tmp_path,
        "screenshot-bot.yml",
        "start",
        "Name the commit and the shards that render",
        stubs={
            "python3": recording("python3", tool),
            "git": recording("git", f"echo {SHA}"),
        },
    )

    assert done.returncode == code, done.stderr
    assert done.outputs == outputs
    assert done.stubbed[0] == "python3 blueprint.py screenshots due"
    assert ("python3 blueprint.py screenshots plan" in done.stubbed) == bool(outputs)


# The bots after the checks and the branch bot in an outage of GitHub, as on 9
# November 2026: each step that calls GitHub tries again, ends with a notice when
# GitHub keeps failing, and sends a write that GitHub failed only once (#786,
# decisions 0136 and 0155).
OUTAGE_JOBS = {
    "after-checks.yml": (
        "rerun",
        "report",
        "release",
        "cancelled",
        "stopped",
        "fixes",
        "own-branch",
        "diagrams",
    ),
    "update-branches.yml": ("update",),
}
PROBE = "Tell an outage of GitHub from a refused token"
GH_CALL = re.compile(r"(?<![\w-])gh (?!help\b)\w+")


def test_the_bots_share_one_copy_of_the_helpers_for_an_outage() -> None:
    copies = {name: workflow(name)["env"]["OUTAGE"] for name in OUTAGE_JOBS}
    assert len(set(copies.values())) == 1
    [helpers] = set(copies.values())
    for function in ("unavailable", "calls", "tried", "once", "given_up"):
        assert f"{function}()" in helpers
    assert "trap unavailable EXIT" in helpers


@pytest.mark.parametrize(
    ("name", "job_id"),
    [(name, job_id) for name, jobs in OUTAGE_JOBS.items() for job_id in jobs],
)
def test_every_call_of_github_by_a_bot_sits_out_an_outage(
    name: str, job_id: str
) -> None:
    # A call of gh without tried or once failed the run and mailed the maintainer at
    # the first error of GitHub.
    for each in job(name, job_id)["steps"]:
        script = each.get("run") or ""
        lines = [
            line.strip()
            for line in script.splitlines()
            if not line.lstrip().startswith("#")
        ]
        calls = [line for line in lines if GH_CALL.search(line)]
        if not calls:
            continue
        assert lines[0] == 'eval "$OUTAGE"', each["name"]
        for line in calls:
            for found in GH_CALL.finditer(line):
                assert re.search(r"\b(?:tried|once) $", line[: found.start()]), (
                    each["name"],
                    line,
                )


@pytest.mark.parametrize(
    ("name", "job_id"),
    [(name, job_id) for name, jobs in OUTAGE_JOBS.items() for job_id in jobs],
)
def test_every_token_of_a_bot_sits_out_an_outage(name: str, job_id: str) -> None:
    # GitHub fails the token of the release app in an outage too: the step goes on,
    # and the step after it tells an outage, which ends with a notice, from a token
    # that GitHub refused, which fails the job.
    steps = job(name, job_id)["steps"]
    tokens = [
        index
        for index, each in enumerate(steps)
        if "create-github-app-token" in each.get("uses", "")
    ]
    probes = [index for index, each in enumerate(steps) if each.get("name") == PROBE]
    assert len(probes) == (1 if tokens else 0)
    for index in tokens:
        token = steps[index]
        assert token["continue-on-error"] is True
        [probe] = probes
        assert probe > index
        assert f"steps.{token['id']}.outcome == 'failure'" in condition_of(steps[probe])
        # Before every step that says that the bot failed.
        said = [
            later
            for later, each in enumerate(steps)
            if "failure()" in str(each.get("if", ""))
        ]
        assert all(probe < later for later in said), token["id"]


PROBES = [
    ("after-checks.yml", "fixes"),
    ("after-checks.yml", "own-branch"),
    ("after-checks.yml", "diagrams"),
    ("update-branches.yml", "update"),
]
THE_REPOSITORY = r"api repos/o/r --jq \.full_name"


@pytest.mark.parametrize(("name", "job_id"), PROBES)
def test_a_token_that_github_fails_in_an_outage_ends_with_a_notice(
    tmp_path: Path, name: str, job_id: str
) -> None:
    done = run_step(
        tmp_path,
        name,
        job_id,
        PROBE,
        answers=[Answer(THE_REPOSITORY, err="HTTP 503: Service Unavailable\n", code=1)],
        stubs={"sleep": recording("sleep")},
    )

    assert done.returncode == 0, done.stderr
    assert len(done.called(THE_REPOSITORY)) == 4
    assert done.stubbed == ["sleep 10", "sleep 20", "sleep 40"]
    assert done.stdout.startswith(
        "::notice title=GitHub is unavailable::GitHub kept failing (HTTP 503"
    )


@pytest.mark.parametrize(("name", "job_id"), PROBES)
def test_a_token_that_github_refuses_as_it_answers_fails_the_job(
    tmp_path: Path, name: str, job_id: str
) -> None:
    done = run_step(
        tmp_path,
        name,
        job_id,
        PROBE,
        answers=[exact("api repos/o/r --jq .full_name", "o/r\n")],
        stubs={"sleep": recording("sleep")},
    )

    assert done.returncode == 1
    assert done.stubbed == []
    assert (
        "::error title=The release app gave no token::GitHub answers, but refused the"
        " token of the release app"
    ) in done.stdout
    assert "::notice" not in done.stdout
