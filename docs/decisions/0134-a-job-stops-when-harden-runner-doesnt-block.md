# A job stops when Harden-Runner doesn't block

- Status: accepted, amends [0088](0088-jobs-that-block-wait-for-their-hosts-and-try-again-when-they-hang.md) and follows up [0133](0133-the-downloads-of-the-workflows-go-through-the-api.md)
- Date: 2026-11-09

## Context

[Decision 0080](0080-jobs-with-secrets-or-tokens-that-write-block-every-host-they-dont-need.md) made every job that holds a secret, an OIDC token or a token that may write block every host that it doesn't need, with Harden-Runner. Harden-Runner blocks with an agent, which its pre step downloads from the page of a release of `step-security/agent` on github.com, starts as the service `agent`, and which writes `Initialized` into `/home/agent/agent.status` once its firewall and its DNS proxy stand.

During GitHub's outage of 8 November 2026, which [decision 0133](0133-the-downloads-of-the-workflows-go-through-the-api.md) describes, that download answered 504 three times in some jobs. The pre step of Harden-Runner v2.22.4 then logs `##[error]Unexpected HTTP response: 504` and still ends with success: it catches every error, calls `core.setFailed`, and then `process.exit(0)`. The job ran on without any block, also without the removal of `sudo` and Docker, which the agent does as well, and nothing failed:

- In paperless-sync, the job *run the failed jobs again* of [run 42469117135](https://github.com/Dennis-Otto/paperless-sync/actions/runs/42469117135) held a token that may run jobs again.
- In the blueprint, the branch bot of *Update branches*, [run 42469810688](https://github.com/Dennis-Otto/repo-blueprint/actions/runs/42469810688), created a token of the release app and brought a pull request up to date, without its block; its run then ended as cancelled, because the run of the next event replaced it, as it does every time.

The same happens when StepSecurity's API answers that Harden-Runner is unavailable (status `409`), when the agent doesn't start within the 9 seconds that the pre step waits, or when it fails later and takes its firewall away. The action has no output that tells a later step whether it blocks.

## Options

1. **A warning:** the step after Harden-Runner warns when the agent doesn't run, as decision 0133 noted as a follow-up. The job still reaches every host with its secrets and tokens, and a warning in a run that passes is easily missed.
2. **The job stops:** a step right after Harden-Runner fails the job when the agent doesn't run, with an annotation that names the cause, so that the job can run again, as a job that hangs behind Harden-Runner does.
3. **The job installs the agent itself,** through the API that kept working: it would copy what the pre step does, the configuration with its key of one run, the service and the checksums of each release, and break with any release of Harden-Runner.
4. **A request to a host that the policy doesn't allow** proves the block, but the agent writes an annotation for every lookup that it blocks, so every job would show a blocked call, and the insights of StepSecurity would list one in every run. The agent's own status says the same without it.

## Decision

Option 2: a security control that turns itself off stops the job, instead of letting it go on unprotected.

- **The step.** Right after Harden-Runner, and after *Let Harden-Runner see the DNS lookups* in a job that keeps sudo, every job that blocks runs *Make sure that Harden-Runner blocks*, before the warm-up of [decision 0088](0088-jobs-that-block-wait-for-their-hosts-and-try-again-when-they-hang.md) and every other step that could need a host. It passes when `/home/agent/agent.status` says `Initialized` and `systemctl is-active` finds the service `agent` running. While the agent is there but hasn't written its status, it waits for it, a second at a time, half a minute at most; when the agent isn't there at all, it fails at once, as nothing will come. It fails with the annotation *Harden-Runner doesn't block*, which says whether the agent couldn't be downloaded, mostly in an outage of GitHub, with the link to githubstatus.com, didn't start or stopped, that the job would reach every host, and that it is no problem of the change; the log shows the status of the agent. It reads two files and asks systemd once, needs neither `sudo` nor a host, and has a time limit of a minute. The screenshot bot's job *render* runs it when the settings of the project block, as it does the warm-up.
- **Who runs it again.** A test of the CI runs once more by the flaky-test bot; a bot of the default branch by the bot-health bot, which gives every failed run of a bot one more try; the release by the bot for failed releases. A check of a pull request, such as its title or CodeQL, runs again with the next push or by hand, and the PR coach shows the annotation in its comment, and in the explanation of a check whose job blocks.
- **Tests keep it so.** `test_every_job_that_blocks_stops_when_harden_runner_doesnt` fails for a job that blocks, in the blueprint and in every kind of project, without the step right before the warm-up, with another condition, another time limit or another script, and for the step in a job that only records. Six tests run the script with the folder of the agent in a folder of their own and stand-ins for `systemctl` and `sleep`: with an agent that blocks, without an agent, with one that starts late, one that doesn't start, one whose status reports an error, and one that stopped.

## Consequences

A job that blocks no longer runs without its block. In an outage of GitHub's downloads, such jobs fail instead of passing unprotected; the bots run most of them again, as above, and the annotation tells a person what to do with the others. It costs one look at two files and one call of `systemctl` when Harden-Runner works.

The update of branches of 8 November 2026 would have stopped before it created the token of the release app. Its next event, or the bot-health bot for a run of `main`, runs the branch bot again; nothing of the change helps the download itself, which stays Harden-Runner's.

A private repository whose plan of StepSecurity doesn't cover it gets an agent that only records, which says so in an annotation of its own; this step still passes there, as the agent runs.

The workflows of a project change in the project: one with a job that blocks copies the step from `.github/workflows/welcome.yml`, right before its warm-up.

*The way to audit and back* of decision 0088 removes this step together with the warm-up, and brings it back with it.
