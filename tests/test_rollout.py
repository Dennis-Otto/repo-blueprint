"""Tests of the Rollout workflow, which brings every release of the blueprint to the
repositories of the release app: the steps of .github/workflows/rollout.yml in bash,
as tests/workflow_steps.py runs them, with the fake gh answering as GitHub does after
the filters of jq, and a sleep that only counts."""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from pathlib import Path

import pytest
import workflow_steps
from shell import BASH
from workflow_steps import Answer, StepResult, exact

pytestmark = pytest.mark.skipif(
    BASH is None, reason="the steps run in bash, Git Bash on Windows"
)

# The repositories that the tests start the blueprint bot of.
REPOSITORIES = ("a", "b", "c")


def failing_or(pattern: str, failed: bool, out: str) -> Answer:
    """The answer of gh to the calls that match: out, or a moment in which GitHub
    fails."""
    if failed:
        return Answer(pattern, err="gh: Bad Gateway (HTTP 502)\n", code=1)
    return Answer(pattern, out)


def answer(kind: str, outcome: str, values: dict[str, str]) -> Answer:
    """How gh answers a kind of call with an outcome that the test planned: the
    release, the jobs of the run, the listing of the repositories, the look for
    the blueprint bot of a repository, its start, its run and its pull request."""
    if kind == "release":
        return failing_or(r"release view .*", outcome == "fail", values["latest"])
    if kind == "jobs":
        return failing_or(
            r"api repos/o/r/actions/runs/7/jobs\?per_page=100 .*",
            outcome == "fail",
            values["publish"],
        )
    if kind == "listing":
        return failing_or(r"api --paginate .*", outcome == "fail", values["listing"])
    if kind.startswith("lookup-"):
        call = (
            f"api --include --silent repos/o/{kind.removeprefix('lookup-')}"
            "/contents/.github/workflows/blueprint-update.yml"
        )
        if outcome == "nothing":
            return exact(call, err="error connecting to api.github.com\n", code=1)
        headers = f"HTTP/2.0 {outcome} Status\nContent-Type: application/json\n"
        if outcome == "200":
            return exact(call, headers)
        return exact(call, headers, err=f"gh: Status (HTTP {outcome})\n", code=1)
    if kind.startswith("dispatch-"):
        repository = f"o/{kind.removeprefix('dispatch-')}"
        call = f"workflow run blueprint-update.yml --repo {repository}"
        if outcome == "ok":
            return exact(call, f"https://github.com/{repository}/actions/runs/123\n")
        # GitHub didn't name the run.
        if outcome == "quiet":
            return exact(call)
        return exact(
            call, err="could not create workflow dispatch event: HTTP 500\n", code=1
        )
    if kind == "bot":
        return failing_or(r"run view .*", outcome == "error", f"{outcome}\n")
    assert kind == "pull-request", kind
    if outcome == "none":
        return Answer(
            r"pr view .*",
            err='no pull requests found for branch "blueprint/update"\n',
            code=1,
        )
    return failing_or(
        r"pr view .*",
        outcome == "error",
        f"{outcome} https://github.com/o/b/pull/9\n",
    )


# The usual outcome of each kind of call, once the test planned no more.
USUAL = {
    "release": "ok",
    "jobs": "ok",
    "listing": "ok",
    **{f"lookup-{name}": "200" for name in REPOSITORIES},
    **{f"dispatch-{name}": "ok" for name in REPOSITORIES},
    "bot": "completed success",
    "pull-request": "passed",
}


@dataclasses.dataclass
class Rollout:
    """The runner of the steps of the rollout, with the fake gh and a sleep that
    only notes its seconds."""

    folder: Path
    planned: dict[str, list[str]] = dataclasses.field(default_factory=dict)

    def plan(self, kind: str, *outcomes: str) -> None:
        """The next outcomes of a kind of call, one call each, before the usual."""
        self.planned[kind] = list(outcomes)

    def answers(self, values: dict[str, str]) -> Iterator[Answer]:
        for kind, outcomes in self.planned.items():
            for outcome in outcomes:
                yield dataclasses.replace(answer(kind, outcome, values), once=True)
        for kind, outcome in USUAL.items():
            yield answer(kind, outcome, values)

    def run(
        self,
        step: str,
        *,
        latest: str = "",
        publish: str = "",
        listing: str = "",
        **variables: str,
    ) -> StepResult:
        """Runs the step whose name starts with step as GitHub does: gh answers
        the release with latest, the jobs of the run with publish and the
        repositories of the release app with listing, one name after the other."""
        jobs = workflow_steps.workflow("rollout.yml")["jobs"]
        [(job, name)] = [
            (job_id, found["name"])
            for job_id, settings in jobs.items()
            for found in settings["steps"]
            if found.get("name", "").startswith(step)
        ]
        values = {
            "latest": f"{latest}\n",
            "publish": f"{publish}\n",
            "listing": "".join(f"{each}\n" for each in listing.split()),
        }
        return workflow_steps.run_step(
            self.folder,
            "rollout.yml",
            job,
            name,
            answers=list(self.answers(values)),
            env={"TAG": "v1.2.0", **variables},
            stubs={"sleep": workflow_steps.recording("sleep")},
        )


@pytest.fixture
def rollout(tmp_path: Path) -> Rollout:
    return Rollout(tmp_path)


def slept(result: StepResult) -> list[str]:
    return [call for call in result.stubbed if call.startswith("sleep ")]


# The latest release went public at 10:00:30.
LATEST = "v1.2.0 2026-10-13T10:00:30Z"


@pytest.mark.parametrize(
    ("publish", "tag"),
    [
        # The run published it, whatever started it: the merge of the release pull
        # request, the daily schedule after the run of the merge failed, or a start by
        # hand that took up a draft; and however far main moved on meanwhile.
        ("success 2026-10-13T10:00:10Z", "v1.2.0"),
        ("success 2026-10-13T10:00:30Z", "v1.2.0"),
        # The run published a beta, which leaves the latest release as it was.
        ("success 2026-10-13T11:00:10Z", ""),
        # The run made no release.
        ("skipped 2026-10-13T11:00:10Z", ""),
        ("", ""),
    ],
)
def test_the_rollout_takes_the_release_that_the_run_published(
    rollout: Rollout, publish: str, tag: str
) -> None:
    result = rollout.run("Find the release", RUN_ID="7", latest=LATEST, publish=publish)

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.outputs == ({"tag": tag} if tag else {})
    made_none = "The run made no release; the latest one, v1.2.0, went out before."
    assert (made_none in result.summary) == (not tag)


def test_started_by_hand_the_rollout_takes_the_latest_release(
    rollout: Rollout,
) -> None:
    result = rollout.run("Find the release", RUN_ID="", latest=LATEST)

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.outputs == {"tag": "v1.2.0"}
    assert result.called("api") == []


@pytest.mark.parametrize(
    ("release", "jobs", "tag"),
    [
        # GitHub fails for a moment.
        (["fail"], ["fail"], "v1.2.0"),
        (["fail", "fail", "fail"], [], ""),
        ([], ["fail", "fail", "fail"], ""),
    ],
)
def test_github_is_asked_again_for_the_release(
    rollout: Rollout, release: list[str], jobs: list[str], tag: str
) -> None:
    rollout.plan("release", *release)
    rollout.plan("jobs", *jobs)

    result = rollout.run(
        "Find the release",
        RUN_ID="7",
        latest=LATEST,
        publish="success 2026-10-13T10:00:10Z",
    )

    # Three times at most, 15 seconds apart.
    assert slept(result) == ["sleep 15", "sleep 15"]
    assert result.outputs == ({"tag": tag} if tag else {})
    assert result.returncode == (0 if tag else 1), result.stdout + result.stderr
    error = (
        "::error::The latest release, or the jobs of the run of the Release "
        "workflow, could not be read."
    )
    assert (error in result.stdout) == (not tag)


def test_the_repositories_go_one_after_the_other_the_quickest_checks_first(
    rollout: Rollout,
) -> None:
    listing = (
        "o/homedarts-for-autodarts o/paperless-sync o/r o/zeta o/issue-assistant "
        "o/paperless-unified-search o/dennis-otto.github.io o/alpha"
    )

    # In the order of the workflow, which names the repositories by their checks.
    result = rollout.run("List the repositories", listing=listing)

    assert result.returncode == 0, result.stdout + result.stderr
    # The blueprint itself is no repository to update; one that the order doesn't
    # name goes first.
    planned = [
        "o/alpha",
        "o/zeta",
        "o/dennis-otto.github.io",
        "o/issue-assistant",
        "o/paperless-unified-search",
        "o/paperless-sync",
        "o/homedarts-for-autodarts",
    ]
    assert result.outputs == {
        "repositories": "[" + ",".join(f'"{name}"' for name in planned) + "]",
        "last": "o/homedarts-for-autodarts",
    }
    assert "The blueprint bots bring v1.2.0 to these repositories" in result.summary
    assert "".join(f"1. {name}\n" for name in planned) in result.summary
    assert slept(result) == []


def test_the_repositories_are_listed_again_when_github_fails_for_a_moment(
    rollout: Rollout,
) -> None:
    rollout.plan("listing", "fail", "fail")

    result = rollout.run("List the repositories", listing="o/b")

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.outputs == {"repositories": '["o/b"]', "last": "o/b"}
    assert slept(result) == ["sleep 15", "sleep 15"]


def test_repositories_that_cannot_be_listed_fail_the_rollout(
    rollout: Rollout,
) -> None:
    rollout.plan("listing", "fail", "fail", "fail")

    result = rollout.run("List the repositories", listing="o/b")

    assert result.returncode == 1
    assert "::error::The repositories of the release app could not be listed." in (
        result.stdout
    )
    assert result.outputs == {}


def test_without_another_repository_nothing_rolls_out(rollout: Rollout) -> None:
    result = rollout.run("List the repositories", listing="o/r")

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.outputs == {}
    assert "no other repository to bring v1.2.0 to" in result.summary


LOOKUP = (
    "api --include --silent repos/o/b/contents/.github/workflows/blueprint-update.yml"
)
DISPATCH = "workflow run blueprint-update.yml --repo o/b"


@pytest.mark.parametrize(
    ("lookups", "dispatches", "run"),
    [
        (["200"], ["ok"], "123"),
        # GitHub fails for a moment, or is out of requests for a while.
        (["502", "nothing", "200"], ["ok"], "123"),
        (["403", "200"], ["fail", "fail", "ok"], "123"),
        # GitHub started the bot without naming its run.
        (["200"], ["quiet"], ""),
    ],
)
def test_the_blueprint_bot_of_a_repository_is_started(
    rollout: Rollout, lookups: list[str], dispatches: list[str], run: str
) -> None:
    rollout.plan("lookup-b", *lookups)
    rollout.plan("dispatch-b", *dispatches)

    result = rollout.run("Start the blueprint bot", REPOSITORY="o/b")

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.outputs == {"started": "true", "run": run}
    link = f": https://github.com/o/b/actions/runs/{run}" if run else ""
    assert f"The blueprint bot of o/b brings v1.2.0{link}.\n" in result.summary
    assert result.called("api") == [LOOKUP] * len(lookups)
    assert result.called("workflow") == [DISPATCH] * len(dispatches)
    # 15 seconds apart.
    pauses = len(lookups) + len(dispatches) - 2
    assert slept(result) == ["sleep 15"] * pauses


@pytest.mark.parametrize("lookups", [["404"], ["500", "404"]])
def test_a_repository_without_a_blueprint_bot_is_left_out(
    rollout: Rollout, lookups: list[str]
) -> None:
    rollout.plan("lookup-b", *lookups)

    result = rollout.run("Start the blueprint bot", REPOSITORY="o/b")

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.outputs == {}
    assert "o/b has no blueprint bot." in result.summary
    assert result.called("workflow") == []


@pytest.mark.parametrize(
    ("lookups", "dispatches", "problem"),
    [
        # An error of GitHub is no answer that the repository has no bot.
        (
            ["500", "500", "500"],
            [],
            "GitHub answered the look for its blueprint bot with 500",
        ),
        (
            ["nothing", "nothing", "nothing"],
            [],
            "GitHub answered the look for its blueprint bot with nothing",
        ),
        # A bot that GitHub doesn't start: disabled, for example.
        (["200"], ["fail", "fail", "fail"], "its blueprint bot could not be started"),
    ],
)
def test_a_repository_whose_bot_cannot_be_started_fails_by_its_name(
    rollout: Rollout, lookups: list[str], dispatches: list[str], problem: str
) -> None:
    rollout.plan("lookup-b", *lookups)
    rollout.plan("dispatch-b", *dispatches)

    result = rollout.run("Start the blueprint bot", REPOSITORY="o/b")

    assert result.returncode == 1
    assert f"::error::Not started in o/b: {problem}." in result.stdout
    assert f"✘ Not started in o/b: {problem}." in result.summary
    assert result.outputs == {}
    assert result.called("workflow") == [DISPATCH] * len(dispatches)


def test_a_repository_that_fails_holds_up_none_after_it(rollout: Rollout) -> None:
    # The job of the rollout runs the step for every repository of the plan, one
    # after the other and also after one that failed, as its matrix does.
    rollout.plan("dispatch-b", "fail", "fail", "fail")

    results = {
        name: rollout.run("Start the blueprint bot", REPOSITORY=f"o/{name}")
        for name in REPOSITORIES
    }

    assert {name: result.returncode for name, result in results.items()} == {
        "a": 0,
        "b": 1,
        "c": 0,
    }
    assert "::error::Not started in o/b:" in results["b"].stdout
    started = [
        call.split()[-1]
        for result in results.values()
        for call in result.called("workflow")
    ]
    assert started == ["o/a", "o/b", "o/b", "o/b", "o/c"]


def wait(rollout: Rollout, run: str = "123", last: str = "false") -> StepResult:
    return rollout.run(
        "Wait for the blueprint bot",
        REPOSITORY="o/b",
        RUN=run,
        LAST=last,
        CHECKS="the filter of jq",
    )


@pytest.mark.parametrize(
    ("bot", "checks", "looks", "summary"),
    [
        # The next repository waits for the bot and the checks of its pull request.
        (
            ["queued ", "in_progress ", "completed success"],
            ["pending", "pending", "passed"],
            4,
            "The checks of its update pull request passed.",
        ),
        # GitHub fails for a moment.
        (["error", "completed success"], ["error", "passed"], 2, "passed."),
        # The repository was up to date, or its pull request merged already.
        ([], ["none"], 0, "No update pull request is open"),
        ([], ["closed"], 0, "No update pull request is open"),
        # Checks that fail wait for the maintainer, not the rollout.
        ([], ["failed"], 0, "The checks of its update pull request failed"),
        # 15 minutes at most, for the bot and the checks together.
        (["in_progress "] * 5, ["pending"] * 20, 15, "still ran after 15 minutes"),
        (["in_progress "] * 20, [], 15, "The blueprint bot still ran after 15 minutes"),
    ],
)
def test_the_next_repository_waits_for_the_update_of_this_one(
    rollout: Rollout, bot: list[str], checks: list[str], looks: int, summary: str
) -> None:
    rollout.plan("bot", *bot)
    rollout.plan("pull-request", *checks)

    result = wait(rollout)

    assert result.returncode == 0, result.stdout + result.stderr
    assert summary in result.summary
    # A look a minute.
    assert slept(result) == ["sleep 60"] * looks
    failed = "::warning::The checks of the update pull request of o/b failed:"
    assert (f"{failed} https://github.com/o/b/pull/9" in result.stdout) == (
        checks == ["failed"]
    )
    # The bot first: no look at the checks before it is done.
    calls = result.called("run |pr ")
    if result.called("pr view"):
        bot_looks = [call for call in calls if call.startswith("run ")]
        assert calls[: len(bot_looks)] == bot_looks


def test_a_blueprint_bot_that_fails_fails_the_rollout_by_its_repository(
    rollout: Rollout,
) -> None:
    rollout.plan("bot", "in_progress ", "completed failure")

    result = wait(rollout)

    assert result.returncode == 1
    assert (
        "::error::The blueprint bot failed in o/b: https://github.com/o/b/actions/runs/123"
        in result.stdout
    )
    assert "✘ The blueprint bot failed in o/b." in result.summary
    assert result.called("pr ") == []


def test_no_repository_waits_for_the_last_one(rollout: Rollout) -> None:
    rollout.plan("bot", "in_progress ", "completed success")

    result = wait(rollout, last="true")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "The blueprint bot is done" in result.summary
    assert result.called("pr ") == []
    assert slept(result) == ["sleep 60"]


def test_without_the_name_of_its_run_only_the_checks_are_waited_for(
    rollout: Rollout,
) -> None:
    rollout.plan("pull-request", "pending", "passed")

    result = wait(rollout, run="")

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.called("run ") == []
    assert (
        result.called("pr ")
        == [
            "pr view blueprint/update --repo o/b --json state,statusCheckRollup,url "
            "--jq the filter of jq"
        ]
        * 2
    )
