"""Tests of the bots in the steps of the workflows: each step that deletes, starts,
merges, publishes or comments runs in bash, as GitHub runs it, with the fake gh of
tests/workflow_steps.py, which answers as the API does and writes down every call. A
census makes sure that every such step of every workflow runs in a test."""

from __future__ import annotations

import ast
import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

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
        run: |
          gh api /repos/o/r/thing --jq .name
          gh api /repos/o/r/thing --jq .name
          printf 'from stdin' | gh api graphql --input -
          printf 'a body' > body.md
          gh pr comment 1 --body-file body.md
          gh issue view 2 || echo "gh failed with $?"
          gh api repos/o/r/raw
          {
            echo "text<<END"
            printf 'two\\nlines\\n'
            echo END
            echo "one=1"
          } >> "$GITHUB_OUTPUT"
          echo "EXPORTED=yes" >> "$GITHUB_ENV"
          echo "### Done" >> "$GITHUB_STEP_SUMMARY"
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
    # starts with /, which Git Bash would make a Windows path of; a call without an
    # answer fails.
    assert done.stdout == 'first\nsecond\ngh failed with 1\n{"a": 1}\n'
    assert "fake gh: no answer for: gh issue view 2" in done.stderr
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
        DEMO.replace(
            "gh api repos/o/r/raw", "gh api repos/o/r/raw --jq '.[] | .name, .id'"
        ),
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
    # as an empty line and anything else as compact JSON.
    assert done.stdout == 'a\n\nb\n{"x":[1,2]}\n'


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
    ("after-checks.yml", "rerun", "Run the failed jobs once more"): "test_template.py",
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
        "Run the checks of the head of the pull request again",
    ): "test_template.py",
    (
        "after-checks.yml",
        "fixes",
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
        "dependabot-automerge.yml",
        "auto-merge",
        "Enable automatic squash merge for patch and minor updates",
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
        "links",
        "Keep the issue of broken links current",
    ): "test_workflow_steps.py",
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


def run_the_branch_clean_up(
    tmp_path: Path, listed: str, used: str, *more: Answer
) -> tuple[list[str], str]:
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
    return done.commands, done.summary


def test_the_clean_up_bot_deletes_only_the_branches_that_main_holds(
    tmp_path: Path,
) -> None:
    calls, summary = run_the_branch_clean_up(
        tmp_path,
        branches(
            "main",
            "gh-pages",
            "release-please--branches--main",
            "renovate/ruff-0.x",
            "dependabot/pip/ruff-1",
            "feat/in-review",
            "fix/merged",
            "feat/old",
            "feat/new",
        ),
        branches("feat/in-review", "other"),
        exact("api repos/o/r/compare/main...fix/merged --jq .ahead_by", "0\n"),
        exact("api repos/o/r/compare/main...feat/old --jq .ahead_by", "2\n"),
        exact("api repos/o/r/compare/main...feat/new --jq .ahead_by", "1\n"),
        exact(
            "api repos/o/r/commits/feat/old --jq .commit.committer.date",
            "2026-01-02T03:04:05Z\n",
        ),
        exact(
            "api repos/o/r/commits/feat/new --jq .commit.committer.date",
            days_ago(2) + "\n",
        ),
    )

    # Only a branch that main holds completely goes, and the bot doesn't even look at
    # main, the website, the branches of the bots and those of open pull requests.
    assert [call for call in calls if "--method DELETE" in call] == [
        "api --method DELETE repos/o/r/git/refs/heads/fix/merged --silent"
    ]
    assert [call for call in calls if call.startswith("api repos/o/r/compare/")] == [
        "api repos/o/r/compare/main...fix/merged --jq .ahead_by",
        "api repos/o/r/compare/main...feat/old --jq .ahead_by",
        "api repos/o/r/compare/main...feat/new --jq .ahead_by",
    ]
    # A branch with commits of its own stays; once it is a month old, the bot lists it
    # for its owner.
    assert summary == (
        "### Branches\n"
        "- deleted `fix/merged`, which main holds\n"
        "- kept `feat/old, 2 commit(s) that main doesn't have, last on 2026-01-02`:"
        " without a pull request for a month\n"
    )


def test_the_clean_up_bot_says_when_there_is_nothing_to_clean_up(
    tmp_path: Path,
) -> None:
    calls, summary = run_the_branch_clean_up(
        tmp_path, branches("main", "renovate/x"), ""
    )

    assert calls == [
        "pr list --state open --limit 500 --json headRefName --jq .[].headRefName",
        "api repos/o/r/branches --paginate --jq .[] | select(.protected | not) | .name",
    ]
    assert summary == "### Branches\nNothing to clean up.\n"


def test_an_error_of_the_api_deletes_no_branch(tmp_path: Path) -> None:
    done = run_step(
        tmp_path,
        "cleanup.yml",
        "cleanup",
        "Delete the branches that main holds",
        answers=[
            Answer(r"pr list .*"),
            Answer(r"api repos/o/r/branches .*", branches("fix/merged")),
            Answer(
                r"api repos/o/r/compare/.*", err="gh: Bad Gateway (HTTP 502)", code=1
            ),
            Answer(r"api --method DELETE .*"),
        ],
        env={"DEFAULT": "main"},
    )

    assert done.returncode == 1
    assert not done.called("api --method DELETE")


@WITH_JQ
def test_the_clean_up_bot_never_looks_at_a_protected_branch(tmp_path: Path) -> None:
    calls, _ = run_the_branch_clean_up(
        tmp_path,
        "",
        "",
        Answer(
            r"api repos/o/r/branches --paginate --jq .*",
            json=[
                {"name": "main", "protected": True},
                {"name": "stable", "protected": True},
                {"name": "fix/merged", "protected": False},
            ],
        ),
        Answer(r"api repos/o/r/compare/main\.\.\.fix/merged --jq \.ahead_by", "0\n"),
    )

    assert [call for call in calls if "compare" in call or "DELETE" in call] == [
        "api repos/o/r/compare/main...fix/merged --jq .ahead_by",
        "api --method DELETE repos/o/r/git/refs/heads/fix/merged --silent",
    ]


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


# The bots that merge.


def test_dependabot_updates_merge_themselves_only_as_patch_and_minor() -> None:
    settings = job("dependabot-automerge.yml", "auto-merge")
    # Only Dependabot's own pull requests, from a branch of the repository.
    for part in (
        "!github.event.repository.fork",
        "github.event.pull_request.user.login == 'dependabot[bot]'",
        "github.event.pull_request.head.repo.full_name == github.repository",
    ):
        assert part in settings["if"]
    merge = step(
        "dependabot-automerge.yml",
        "auto-merge",
        "Enable automatic squash merge for patch and minor updates",
    )
    assert merge["if"] == (
        "steps.metadata.outputs.update-type == 'version-update:semver-patch' || "
        "steps.metadata.outputs.update-type == 'version-update:semver-minor'"
    )


def test_a_dependabot_update_merges_only_the_commit_that_was_checked(
    tmp_path: Path,
) -> None:
    url = "https://github.com/o/r/pull/3"
    done = run_step(
        tmp_path,
        "dependabot-automerge.yml",
        "auto-merge",
        "Enable automatic squash merge for patch and minor updates",
        answers=[exact(f"pr merge --auto --squash --match-head-commit fed987 {url}")],
        env={"GH_TOKEN": "app-token", "PR_URL": url, "PR_HEAD_SHA": "fed987"},
    )

    assert done.returncode == 0, done.stderr
    assert len(done.calls) == 1


def run_the_merge_of_dependency_updates(
    tmp_path: Path, *answers: Answer
) -> tuple[list[str], str]:
    done = run_step(
        tmp_path,
        "release.yml",
        "release-please",
        "Merge a release of dependency updates once its checks pass",
        answers=[*answers, Answer(r"pr merge --repo o/r --auto --squash 21")],
        env={
            "GH_TOKEN": "app-token",
            "PR": json.dumps({"number": 21, "headBranchName": "release-please--x"}),
        },
    )
    assert done.returncode == 0, done.stderr
    return done.called("pr merge"), done.stdout


@WITH_JQ
def test_the_first_release_waits_for_the_maintainer(tmp_path: Path) -> None:
    merged, said = run_the_merge_of_dependency_updates(
        tmp_path,
        Answer(r"release view .*", err="release not found", code=1),
    )

    assert merged == []
    assert said == "The first release waits for the maintainer.\n"


@WITH_JQ
@pytest.mark.parametrize(
    ("subjects", "merges"),
    [
        (
            "fix(deps): update ruff\nchore(deps-dev): update mypy\nbuild(deps): pin",
            True,
        ),
        ("fix(deps): update ruff\nfeat: a dark mode", False),
        ("fix(depsy): no update\n", False),
        ("chore: release 1.2.0\n", False),
    ],
)
def test_a_release_merges_itself_only_with_dependency_updates_alone(
    tmp_path: Path, subjects: str, merges: bool
) -> None:
    merged, said = run_the_merge_of_dependency_updates(
        tmp_path,
        exact("release view --repo o/r --json tagName --jq .tagName", "v1.2.0\n"),
        Answer(rf"api repos/o/r/compare/v1\.2\.0\.\.\.{SHA} --jq .*", subjects),
    )

    assert merged == (["pr merge --repo o/r --auto --squash 21"] if merges else [])
    assert ("the maintainer merges it" in said) == (not merges)


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
    assert done.commands == [
        'api repos/o/r/actions/runs/77 --jq "\\(.status) \\(.run_attempt)"',
        "run rerun 77 --failed",
    ]
    assert done.summary == (
        "The failed jobs of the release of abc1234 run once more, where they stopped.\n"
    )


def rerun_the_release(
    tmp_path: Path, status: str, attempt: int, rerun: Answer
) -> StepResult:
    """The bot for failed releases after the first attempt of run 77 failed, with the
    run as GitHub shows it now and the answer of its rerun."""
    return run_step(
        tmp_path,
        "after-checks.yml",
        "release",
        "Run the failed jobs of the release once more",
        answers=[
            Answer(
                r"api repos/o/r/actions/runs/77 --jq .*",
                json={"id": 77, "status": status, "run_attempt": attempt},
            ),
            rerun,
        ],
        env={"RUN": "77", "SHA": "abc1234def"},
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
# The tool of the bots: two commits for the pictures, the JSON of each part's commit,
# and the report.
PICTURE_TOOL = recording(
    "python3",
    """case "$*" in
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
        env={"GH_TOKEN": "app-token", "APP_SLUG": "the-app", "STALE": "false"},
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
        env={"GH_TOKEN": "app-token", "APP_SLUG": "the-app", "STALE": "true"},
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
    assert "python3 blueprint.py screenshots parts" in commits


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
        env={"GH_TOKEN": "app-token", "APP_SLUG": "the-app", "STALE": "false"},
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
    report = step("links.yml", "links", "Keep the issue of broken links current")
    assert report["if"] == "github.event_name == 'schedule'"
    assert job("links.yml", "links")["permissions"] == {
        "contents": "read",
        "issues": "write",
    }

    done = run_step(
        tmp_path,
        "links.yml",
        "links",
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
                r"api graphql -F owner=o -F name=r -f query=query.* --jq .*",
                "R_1 DIC_2\n",
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
