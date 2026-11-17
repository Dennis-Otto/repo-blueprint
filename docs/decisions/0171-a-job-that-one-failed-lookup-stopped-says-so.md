# A job that one failed lookup stopped says so

- Status: accepted, follows up [0134](0134-a-job-stops-when-harden-runner-doesnt-block.md)
- Date: 2026-11-17

## Context

[Decision 0134](0134-a-job-stops-when-harden-runner-doesnt-block.md) stops every job that blocks when the agent of Harden-Runner doesn't run. From 2026-11-10 to the morning of 2026-11-17 the step *Make sure that Harden-Runner blocks* stopped 13 runs in the repositories that follow the blueprint, and on 2026-11-17, in four hours, at least 15 more in eight repositories ([#1006](https://github.com/Dennis-Otto/repo-blueprint/issues/1006)). Each one sent its maintainer a mail, and six stayed red on `main`.

The annotation said that the agent *didn't start*. It had started, and then taken itself away. The log of the agent, `/home/agent/agent.log`, showed the same two lines in every stop:

```text
Error resolving allowed domain error in response from dns.google unable to resolve domain productionresultssa121.blob.core.windows.net., status 2
Reverted changes
```

In block mode, the agent (`step-security/agent` v0.18.1, which Harden-Runner v2.22.4 installs) looks up every host that it allows before its firewall stands, and when a single lookup fails, it takes back all that it changed and ends (`agent.go`, lines 179 to 187). It asks `dns.google` and tries `cloudflare-dns.com` only when `dns.google` can't be reached at all, not when it answers with an error such as `SERVFAIL` (`dnsproxy.go`, lines 119 to 170). Since the agent also allows the hosts of GitHub's meta list, by name, a job looks up about 150 hosts instead of its handful, so a short phase of failed answers stops many jobs at once. The agent writes no status then, so the step waited half a minute for one that couldn't come.

## Options

1. **A second try inside the job:** Harden-Runner installs its agent once, in its pre step, and has no input to install it again; installing the agent from the workflow is option 3 of decision 0134, which was rejected.
2. **A second job inside the run,** as [decision 0141](0141-the-bot-health-bot-runs-every-bot-again-that-harden-runner-stopped.md) rejected: the run stays red, and the mail has already gone out.
3. **Bot health follows After the checks:** it would start a run of *Bot health* after each of the 8,462 runs of *After the checks* in that week, to heal the 3 that failed; [decision 0151](0151-the-bots-after-the-checks-start-the-branch-bot-when-a-check-failed-for-good.md) removed exactly this kind of mostly skipped run.
4. **Audit mode,** or the custom property `skip-harden-runner`: it takes the block away, which is the control that decision 0134 protects.
5. **The fix where the cause is,** in the agent, which asks once more or asks its second resolver when a lookup of a host that it allows fails, and until then an annotation that tells the truth.

## Decision

Option 5.

- **The annotation names the cause.** When the log of the agent has the line `Error resolving allowed domain`, the step says that the agent took itself away again because one lookup of that host, a host that it allows, failed, that this is no outage; the job's log shows the line of the agent. The annotation links nothing of the blueprint, as the workflows of every project carry it. It finds the host after `resolve domain` when the resolver answered with an error, and after `name=` when no resolver could be reached. The other causes keep their words.
- **No wait for a status that won't come.** Once the log says `Reverted changes`, the step stops at once instead of waiting the half minute.
- **What stays.** The annotation keeps the words that the bots look for, *would reach every host, and it stops here instead*, which `STOPPED` of `blueprint/bot_health.py` and the steps of *After the checks* match, so every second try of decisions 0134 and 0141 still happens. The step stays one script, the same in every job that blocks, in the blueprint and in every kind of project, and it reads the log without `sudo`. No job runs without its block, and none falls back to audit.
- **The fix upstream.** The maintainer reports the cause to `step-security/harden-runner`, with the runs and the lines of `agent.go` and `dnsproxy.go`, and #1006 links that report. The release of Harden-Runner or of its agent that fixes it lands in every workflow and every kind of project at once, without waiting the seven days of Renovate's `minimumReleaseAge`, as [decision 0088](0088-jobs-that-block-wait-for-their-hosts-and-try-again-when-they-hang.md) and [decision 0123](0123-harden-runner-v2-22-4-and-a-job-with-sudo-takes-githubs-dns-experiment-away.md) did for v2.22.3 and v2.22.4. #1006 stays open until then.
- **Tests keep it so.** Besides the seven tests of decision 0134, four run the script with a log of the agent: with a failed answer, with a resolver that couldn't be reached, with a failed lookup whose host the log doesn't name, and with an agent that took its changes back for another cause, which keeps the words of an agent that didn't start. `test_every_job_that_blocks_stops_when_harden_runner_doesnt` still fails when a copy of the script differs.

## Consequences

Until the fix upstream, a single failed lookup still stops a job, and the bots still run it again as before; a person who reads the annotation knows that it was no outage and no problem of the change, and which host failed. A stopped job ends half a minute sooner. The step reads one more file, the log of the agent, which costs nothing when Harden-Runner works.

The workflows of a project change in the project: one with a job that blocks copies the step from `.github/workflows/welcome.yml` again.
