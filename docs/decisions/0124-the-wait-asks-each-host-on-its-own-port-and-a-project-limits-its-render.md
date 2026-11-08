# The wait asks each host on its own port, and a project limits its render and keeps its failure

- Status: accepted, amends [0088](0088-jobs-that-block-wait-for-their-hosts-and-try-again-when-they-hang.md) and [0120](0120-the-screenshot-bot-renders-in-shards-takes-named-files-and-blocks-other-hosts.md)
- Date: 2026-11-08

## Context

Every job that blocks waits right after Harden-Runner until it may reach its hosts, for two minutes at most ([decision 0088](0088-jobs-that-block-wait-for-their-hosts-and-try-again-when-they-hang.md)). The step *Wait until Harden-Runner lets the hosts through* asked each host by `https://host/`, on port 443, whatever port the job allows it on, and took every failure of curl for a block. A host that a job allows only on port 80, such as a mirror of apt, is blocked on 443: the job waited two minutes for it and warned on every run, and a port that speaks no HTTP would have done the same.

HomeDarts for Autodarts renders its screenshots with the shared bot since [homedarts-for-autodarts#618](https://github.com/Dennis-Otto/homedarts-for-autodarts/pull/618) ([decision 0120](0120-the-screenshot-bot-renders-in-shards-takes-named-files-and-blocks-other-hosts.md)), and keeps three work-arounds for what the bot lacks:

- `launchpad.net`, from which its script installs pngquant, often keeps a runner waiting: the wait costs up to two minutes for each of its nine shards, although the script needs the host only later and tries again by itself.
- The step *Render the pictures* has no time limit of its own, so a hung render ran into the hour of the job, which then ended without any step after it. Its script limits each group itself, with `SCREENSHOTS_LIMIT` of 21 minutes and GNU `timeout`.
- A failed shard kept nothing: the screenshots and the logs of a section that failed, which its own workflow uploaded from `tests/e2e/artifacts`, were gone with the runner.

## Decision

**The wait asks each host on its own port.** It takes the port from the endpoint, `host:port` as Harden-Runner allows it, and asks `http://host:80/` on port 80 and `https://host:port/` on any other. Only a host that curl can't resolve (6), can't reach (7) or doesn't hear from in time (28) counts as blocked. A host that answers at all is through, even when it answers in another protocol, such as an error of TLS on a port of SSH, because the wait is there for the connection, not for the answer. The script stays the same in every workflow, and a test keeps it so.

**`.github/screenshots.toml` can set three more keys**, besides `shards`, `files` and `hosts`:

```toml
# Hosts of `hosts` that the jobs don't wait for before the script runs, because they
# keep a runner waiting and the script asks for them only later. They stay allowed.
skip_wait = ["launchpad.net:443"]
# The time limit of the script, in whole minutes from 1 to 45; without it, the hour
# of the job.
timeout_minutes = 21
# The folder that a failed render keeps as an artifact for a person to see.
failure_folder = "tests/e2e/artifacts"
```

- **`skip_wait`** names hosts of `hosts`, by the same words; the jobs still allow them. Its hosts reach the step in `SKIP_WAIT`, which every other job leaves empty, so that `HOSTS` stays the very words of `allowed-endpoints`.
- **`timeout_minutes`** becomes the `timeout-minutes` of the step *Render the pictures*; without it, the step has the 60 minutes of the job. At most 45 leaves a quarter of an hour for the steps before and after the script. The step runs the script with `exec`, so that the script itself gets the SIGINT with which GitHub ends a step that runs out of time, can stop its demo and say where it waited.
- **`failure_folder`** is a path of plain names in the repository outside `.git`. When a step of the render fails, also one that ran out of time, the job uploads that folder as `failed-render-<shard>-attempt-<attempt>`, for seven days. That name never matches `screenshots-*`, which the job *collect* takes, so a failure of an earlier attempt never reaches the pull request.

The settings stay strict: a host of `skip_wait` that `hosts` doesn't name, a time limit that is no whole number from 1 to 45, or a folder that isn't plain fails the run that starts the render, with what is wrong.

## Consequences

- A job that allows a host on another port than 443 no longer waits two minutes and warns for it on every run.
- The boundary of [decision 0118](0118-a-bot-whose-pull-request-conflicts-builds-it-anew-at-once.md) stays: the artifact of a failure comes from the job *render*, which has no secrets and a token that only reads, and the job with the release app never downloads it.
- A host of `skip_wait` may still be blocked for up to a minute when the script first asks for it, so the script must try it again by itself.
- HomeDarts for Autodarts can set `skip_wait`, `timeout_minutes` and `failure_folder` and drop the limit of its script for each group in the bot.
