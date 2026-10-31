# Jobs that block wait for their hosts, and try again when they hang

- Status: accepted
- Date: 2026-10-31

## Context

[Decision 80](0080-jobs-with-secrets-or-tokens-that-write-block-every-host-they-dont-need.md) turned on Harden-Runner's block mode in every job that holds a secret or may write. Since it reached the other repositories, such jobs failed and hung at random, the short bots and the check of the title too.

GitHub tries a DNS resolver and an outbound proxy of its own on the hosted runners of the region `westus2` (`egress-dns-resolver.service`, `90-egress-proxy.conf`), which keeps the questions of the runner from reaching Harden-Runner. So Harden-Runner knows one address of a host and the runner connects to another, which Harden-Runner drops ([step-security/harden-runner#708](https://github.com/step-security/harden-runner/issues/708)):

- A step fails on a host that it may reach, such as a `gh` with `ECONNREFUSED`, or `actions/checkout` after its three tries.
- The questions of systemd-resolved to the DNS of Azure, `168.63.129.16`, are dropped as well, so the runner can't reach its own hosts at the end of the job. It hangs in *Cleaning up orphan processes* until the time limit of the job, and GitHub takes five minutes more to cancel it: a job of 15 seconds with a limit of 5 minutes takes 10, and ends as cancelled, even when every step passed. A required check that ends so blocks its pull request.

From 29 to 31 October 2026, on Harden-Runner v2.22.2, 50 jobs in the seven repositories hung like that, in 1,478 runs: all 50 ran on `westus2`, dropped `168.63.129.16` and end in *Cleaning up orphan processes*; [issue-assistant#181](https://github.com/Dennis-Otto/issue-assistant/issues/181) and [homedarts-for-autodarts#488](https://github.com/Dennis-Otto/homedarts-for-autodarts/issues/488) describe the same. Harden-Runner v2.22.3, of 27 October, removes GitHub's experiment before it starts, when a feature flag that it fetches once, within 3 seconds, tells it to; when that request fails, the experiment stays, as a report on the issue shows.

## Options

1. Audit mode everywhere until Harden-Runner is fixed. Nothing fails, and nothing is blocked either.
2. Only Harden-Runner v2.22.3, and rely on the request for the feature flag.
3. Harden-Runner v2.22.3, a job that waits until it may reach its hosts, and one more try for a job that ran out of time.

## Decision

Option 3, with option 1 as the fallback, as Dennis decided on 31 October 2026: when jobs still fail or hang through this cause, audit mode goes everywhere until the fix is upstream, as *The way to audit and back* says.

- **The fix of Harden-Runner.** Every workflow pins v2.22.3 ahead of the seven days that Renovate waits for a release, because it carries the fix.
- **The warm-up.** Right after Harden-Runner, every job that blocks runs the step *Wait until Harden-Runner lets the hosts through*. It asks each host of the job with `curl --head` every 3 seconds, for two minutes at most, so that an address that passed Harden-Runner by has left the cache of systemd-resolved before the first step needs it. Its `HOSTS` are the very words of `allowed-endpoints`, those of a delivery too; a wildcard names no host to ask. After two minutes it warns and goes on, because a host that doesn't answer may be one that this run doesn't need. It sends nothing but the question, no token. It is the same step in each job, not an action of its own, because most of these jobs check out nothing, and an action of the blueprint would have to pin the commit that adds it.
- **One more try.** A job that hangs can't save itself: every step has ended, and only GitHub can end it, with the annotation `The job has exceeded the maximum execution time`. The bots look for it. The bot for cancelled checks runs the cancelled jobs of the first attempt of a run for the head of a pull request or of `main` once more, where the flaky-test bot, which already does so for the tests, doesn't run; the bot-health bot now also looks at the runs that ended as cancelled, and treats such a run as one that timed out: a second try, and an issue when that hangs too. A run that a person or a newer run cancelled says nothing of the kind, and stays cancelled.
- **The time limits stay.** A hang costs its limit and five minutes, but the limits of the short jobs are 5 minutes already, the warm-up and the wait for Docker can take two minutes each, and with the fix a hang is rare.
- **Tests keep it so.** `test_every_job_that_blocks_waits_until_harden_runner_lets_its_hosts_through` fails for a job that blocks without the warm-up right after Harden-Runner, with other hosts than it allows or with another script, and for a warm-up in a job that only records. Other tests run the script and the two bots with stand-ins.

## What was measured

Before the change, from 29 to 31 October 2026: 50 hung jobs in 1,478 runs of the seven repositories, on v2.22.2, all on `westus2`.

With the change, on 31 October 2026: 79 jobs with the steps of a real bot (the warm-up, a checkout, a call of the API and the wait for Docker), 6 of them on `westus2`. None failed, hung, waited in the warm-up or dropped an address, and each of the 6 says `[github-dns-experiment] reverted` in the log of the agent. The warm-up took about 0.4 seconds: 16.8 seconds on average, against 16.4 of 36 jobs on v2.22.2 without it. None of those 36 ran on `westus2`, so they show what the warm-up costs, not what it cures. The pull request that fixes [#518](https://github.com/Dennis-Otto/repo-blueprint/issues/518) has the numbers of the real workflows that can run from a branch; those that run only from `main`, such as the check of the title, can't be measured before the merge.

## Consequences

The block stays in force, so a compromised step in a job with the key of the release app still reaches only the hosts of its job.

A job that blocks takes a moment longer, less than a second when nothing is wrong, as measured above, and up to two minutes when something is. When the request for the feature flag fails on `westus2`, the warm-up gets the steps through, and the job may still hang at its end, until the bots try it again. Such a hang costs a runner up to the limit of the job and five minutes more; and it reaches only the workflows that the bots watch, a bot of the project's own stays cancelled until its next run. The workflows of a project change in the project: [homedarts-for-autodarts#488](https://github.com/Dennis-Otto/homedarts-for-autodarts/issues/488) takes the warm-up into the workflows that it owns.

### The way to audit and back

To audit: set `egress-policy: audit` and name the step *Record the network traffic of the job* in every job that blocks, without its `allowed-endpoints` and `disable-sudo-and-containers`, remove the warm-up and the wait for Docker of those jobs, add each job to `AUDITED_PRIVILEGED_JOBS` of `tests/test_template.py` with a link to this decision as its reason, and say so in `SECURITY.md`, `template/SECURITY.md.jinja` and `docs/security.md`. The hosts stay in the history of the files.

Back to block, once [#708](https://github.com/step-security/harden-runner/issues/708) is closed and a run on `westus2` shows no dropped address: revert that pull request. The warm-up can go on its own, with its test, once the jobs of a release have passed a month without a warning of it.
