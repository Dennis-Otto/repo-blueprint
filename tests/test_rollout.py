"""Tests of the Rollout workflow, which brings every release of the blueprint to the
repositories of the release app: the steps of .github/workflows/rollout.yml in bash,
with a gh that answers as GitHub does, after the filters of jq, and a sleep that only
counts."""

from __future__ import annotations

import os
import re
import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path

import pytest
from shell import BASH, in_bash

ROOT = Path(__file__).parents[1]
ROLLOUT = ROOT / ".github/workflows/rollout.yml"
pytestmark = pytest.mark.skipif(
    BASH is None, reason="the steps run in bash, Git Bash on Windows"
)

GH = """#!/usr/bin/env bash
echo "gh $*" >> "$CALLS"
# The next outcome that the test planned for a kind of call, one per line, or the
# usual one once it planned no more.
next() {
  outcome=""
  if [[ -s "$STUBS/$1" ]]; then
    outcome="$(head -n 1 "$STUBS/$1")"
    tail -n +2 "$STUBS/$1" > "$STUBS/$1.next" && mv "$STUBS/$1.next" "$STUBS/$1"
  fi
  outcome="${outcome:-$2}"
}
case "$1 $2" in
  "release view")
    next release ok
    if [[ "$outcome" == fail ]]; then
      echo "gh: Bad Gateway (HTTP 502)" >&2
      exit 1
    fi
    echo "$LATEST"
    ;;
  "api repos/o/r/actions/runs/7/jobs?per_page=100")
    next jobs ok
    if [[ "$outcome" == fail ]]; then
      echo "gh: Bad Gateway (HTTP 502)" >&2
      exit 1
    fi
    printf '%s\\n' "$PUBLISH"
    ;;
  "api --paginate")
    next listing ok
    if [[ "$outcome" == fail ]]; then
      echo "gh: Bad Gateway (HTTP 502)" >&2
      exit 1
    fi
    printf '%s\\n' $LISTING
    ;;
  # The look for the blueprint bot: gh api --include --silent repos/o/<name>/contents/...
  "api --include")
    name="${4#repos/o/}"
    next "lookup-${name%%/*}" 200
    if [[ "$outcome" == nothing ]]; then
      echo "error connecting to api.github.com" >&2
      exit 1
    fi
    printf 'HTTP/2.0 %s Status\\nContent-Type: application/json\\n' "$outcome"
    if [[ "$outcome" != 200 ]]; then
      echo "gh: Status (HTTP $outcome)" >&2
      exit 1
    fi
    ;;
  "workflow run")
    next "dispatch-${5#o/}" ok
    case "$outcome" in
      ok) echo "https://github.com/$5/actions/runs/123" ;;
      # GitHub didn't name the run.
      quiet) ;;
      *)
        echo "could not create workflow dispatch event: HTTP 500" >&2
        exit 1
        ;;
    esac
    ;;
  "run view")
    next bot "completed success"
    if [[ "$outcome" == error ]]; then
      echo "gh: Bad Gateway (HTTP 502)" >&2
      exit 1
    fi
    echo "$outcome"
    ;;
  "pr view")
    next pull-request passed
    case "$outcome" in
      none)
        echo 'no pull requests found for branch "blueprint/update"' >&2
        exit 1
        ;;
      error)
        echo "gh: Bad Gateway (HTTP 502)" >&2
        exit 1
        ;;
      *) echo "$outcome https://github.com/o/b/pull/9" ;;
    esac
    ;;
  *)
    echo "unexpected: gh $*" >&2
    exit 1
    ;;
esac
"""
SLEEP = '#!/usr/bin/env bash\necho "sleep $*" >> "$CALLS"\n'


def script_of(step: str) -> str:
    """The script of the step of the Rollout workflow whose name starts with step."""
    lines = ROLLOUT.read_text(encoding="utf-8").splitlines(keepends=True)
    start = next(
        index
        for index, line in enumerate(lines)
        if line.startswith(f"      - name: {step}")
    )
    run = lines.index("        run: |\n", start)
    script = []
    for line in lines[run + 1 :]:
        if line.strip() and not line.startswith(" " * 10):
            break
        script.append(line)
    return textwrap.dedent("".join(script))


def order() -> str:
    found = re.search(
        r"^          ORDER: (.+)$", ROLLOUT.read_text(encoding="utf-8"), re.M
    )
    assert found
    return found[1]


@dataclass
class Rollout:
    """The runner of a job of the rollout, with the stubs of gh and sleep."""

    folder: Path
    environment: dict[str, str]

    def plan(self, kind: str, *outcomes: str) -> None:
        (self.folder / "stubs" / kind).write_text(
            "".join(f"{outcome}\n" for outcome in outcomes),
            encoding="utf-8",
            newline="\n",
        )

    def run(self, step: str, **variables: str) -> subprocess.CompletedProcess[str]:
        """Runs the step as GitHub does, with bash -e."""
        (self.folder / "step.sh").write_text(
            script_of(step), encoding="utf-8", newline="\n"
        )
        return subprocess.run(
            in_bash("-e", "step.sh"),
            cwd=self.folder,
            env={**self.environment, **variables},
            capture_output=True,
            encoding="utf-8",
            check=False,
        )

    def read(self, name: str) -> str:
        return (self.folder / name).read_text(encoding="utf-8")

    def calls(self, *kinds: str) -> list[str]:
        return [
            call
            for call in self.read("calls").splitlines()
            if call.startswith(tuple(kinds))
        ]


@pytest.fixture
def rollout(tmp_path: Path) -> Rollout:
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    for name, text in {"gh": GH, "sleep": SLEEP}.items():
        (stubs / name).write_text(text, encoding="utf-8", newline="\n")
        (stubs / name).chmod(0o755)
    (tmp_path / "runner").mkdir()
    for name in ("calls", "summary", "output"):
        (tmp_path / name).touch()
    environment = {
        **os.environ,
        "STUBS": stubs.as_posix(),
        "CALLS": (tmp_path / "calls").as_posix(),
        "GITHUB_REPOSITORY": "o/r",
        "GITHUB_STEP_SUMMARY": (tmp_path / "summary").as_posix(),
        "GITHUB_OUTPUT": (tmp_path / "output").as_posix(),
        "RUNNER_TEMP": (tmp_path / "runner").as_posix(),
        "TAG": "v1.2.0",
    }
    return Rollout(tmp_path, environment)


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
    result = rollout.run("Find the release", RUN_ID="7", LATEST=LATEST, PUBLISH=publish)

    assert result.returncode == 0, result.stdout + result.stderr
    assert rollout.read("output") == (f"tag={tag}\n" if tag else "")
    made_none = "The run made no release; the latest one, v1.2.0, went out before."
    assert (made_none in rollout.read("summary")) == (not tag)


def test_started_by_hand_the_rollout_takes_the_latest_release(
    rollout: Rollout,
) -> None:
    result = rollout.run("Find the release", RUN_ID="", LATEST=LATEST, PUBLISH="")

    assert result.returncode == 0, result.stdout + result.stderr
    assert rollout.read("output") == "tag=v1.2.0\n"
    assert rollout.calls("gh api") == []


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
        LATEST=LATEST,
        PUBLISH="success 2026-10-13T10:00:10Z",
    )

    # Three times at most, 15 seconds apart.
    assert rollout.calls("sleep") == ["sleep 15", "sleep 15"]
    assert rollout.read("output") == (f"tag={tag}\n" if tag else "")
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

    result = rollout.run("List the repositories", LISTING=listing, ORDER=order())

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
    assert rollout.read("output") == (
        "repositories=[" + ",".join(f'"{name}"' for name in planned) + "]\n"
        "last=o/homedarts-for-autodarts\n"
    )
    summary = rollout.read("summary")
    assert "The blueprint bots bring v1.2.0 to these repositories" in summary
    assert "".join(f"1. {name}\n" for name in planned) in summary
    assert rollout.calls("sleep") == []


def test_the_repositories_are_listed_again_when_github_fails_for_a_moment(
    rollout: Rollout,
) -> None:
    rollout.plan("listing", "fail", "fail")

    result = rollout.run("List the repositories", LISTING="o/b", ORDER=order())

    assert result.returncode == 0, result.stdout + result.stderr
    assert rollout.read("output") == 'repositories=["o/b"]\nlast=o/b\n'
    assert rollout.calls("sleep") == ["sleep 15", "sleep 15"]


def test_repositories_that_cannot_be_listed_fail_the_rollout(
    rollout: Rollout,
) -> None:
    rollout.plan("listing", "fail", "fail", "fail")

    result = rollout.run("List the repositories", LISTING="o/b", ORDER=order())

    assert result.returncode == 1
    assert "::error::The repositories of the release app could not be listed." in (
        result.stdout
    )
    assert rollout.read("output") == ""


def test_without_another_repository_nothing_rolls_out(rollout: Rollout) -> None:
    result = rollout.run("List the repositories", LISTING="o/r", ORDER=order())

    assert result.returncode == 0, result.stdout + result.stderr
    assert rollout.read("output") == ""
    assert "no other repository to bring v1.2.0 to" in rollout.read("summary")


LOOKUP = "gh api --include --silent repos/o/b/contents/.github/workflows/blueprint-update.yml"
DISPATCH = "gh workflow run blueprint-update.yml --repo o/b"


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
    assert rollout.read("output") == f"started=true\nrun={run}\n"
    link = f": https://github.com/o/b/actions/runs/{run}" if run else ""
    assert f"The blueprint bot of o/b brings v1.2.0{link}.\n" in rollout.read("summary")
    assert rollout.calls("gh api") == [LOOKUP] * len(lookups)
    assert rollout.calls("gh workflow") == [DISPATCH] * len(dispatches)
    # 15 seconds apart.
    pauses = len(lookups) + len(dispatches) - 2
    assert rollout.calls("sleep") == ["sleep 15"] * pauses


@pytest.mark.parametrize("lookups", [["404"], ["500", "404"]])
def test_a_repository_without_a_blueprint_bot_is_left_out(
    rollout: Rollout, lookups: list[str]
) -> None:
    rollout.plan("lookup-b", *lookups)

    result = rollout.run("Start the blueprint bot", REPOSITORY="o/b")

    assert result.returncode == 0, result.stdout + result.stderr
    assert rollout.read("output") == ""
    assert "o/b has no blueprint bot." in rollout.read("summary")
    assert rollout.calls("gh workflow") == []


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
    assert f"✘ Not started in o/b: {problem}." in rollout.read("summary")
    assert rollout.read("output") == ""
    assert rollout.calls("gh workflow") == [DISPATCH] * len(dispatches)


def test_a_repository_that_fails_holds_up_none_after_it(rollout: Rollout) -> None:
    # The job of the rollout runs the step for every repository of the plan, one
    # after the other and also after one that failed, as its matrix does.
    rollout.plan("dispatch-b", "fail", "fail", "fail")

    results = {
        name: rollout.run("Start the blueprint bot", REPOSITORY=f"o/{name}")
        for name in ("a", "b", "c")
    }

    assert {name: result.returncode for name, result in results.items()} == {
        "a": 0,
        "b": 1,
        "c": 0,
    }
    assert "::error::Not started in o/b:" in results["b"].stdout
    started = [call.split()[-1] for call in rollout.calls("gh workflow")]
    assert started == ["o/a", "o/b", "o/b", "o/b", "o/c"]


def wait(
    rollout: Rollout, run: str = "123", last: str = "false"
) -> subprocess.CompletedProcess[str]:
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
    assert summary in rollout.read("summary")
    # A look a minute.
    assert rollout.calls("sleep") == ["sleep 60"] * looks
    failed = "::warning::The checks of the update pull request of o/b failed:"
    assert (f"{failed} https://github.com/o/b/pull/9" in result.stdout) == (
        checks == ["failed"]
    )
    # The bot first: no look at the checks before it is done.
    calls = rollout.calls("gh run", "gh pr")
    if "gh pr view" in "".join(calls):
        bot_looks = [call for call in calls if call.startswith("gh run")]
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
    assert "✘ The blueprint bot failed in o/b." in rollout.read("summary")
    assert rollout.calls("gh pr") == []


def test_no_repository_waits_for_the_last_one(rollout: Rollout) -> None:
    rollout.plan("bot", "in_progress ", "completed success")

    result = wait(rollout, last="true")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "The blueprint bot is done" in rollout.read("summary")
    assert rollout.calls("gh pr") == []
    assert rollout.calls("sleep") == ["sleep 60"]


def test_without_the_name_of_its_run_only_the_checks_are_waited_for(
    rollout: Rollout,
) -> None:
    rollout.plan("pull-request", "pending", "passed")

    result = wait(rollout, run="")

    assert result.returncode == 0, result.stdout + result.stderr
    assert rollout.calls("gh run") == []
    assert (
        rollout.calls("gh pr")
        == [
            "gh pr view blueprint/update --repo o/b --json state,statusCheckRollup,url "
            "--jq the filter of jq"
        ]
        * 2
    )
