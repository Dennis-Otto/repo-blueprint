# Harden-Runner v2.22.4 everywhere, and a job with sudo takes GitHub's DNS experiment away

- Status: accepted, amends [0088](0088-jobs-that-block-wait-for-their-hosts-and-try-again-when-they-hang.md)
- Date: 2026-11-08

## Context

[Decision 0088](0088-jobs-that-block-wait-for-their-hosts-and-try-again-when-they-hang.md) pinned Harden-Runner v2.22.3 in every workflow, because it takes GitHub's DNS experiment on the runners of `westus2` (`egress-dns-resolver.service`, `90-egress-proxy.conf`) out of its way, which otherwise makes a job that blocks fail on a host that it may reach and hang until its time limit. v2.22.3 does so only when a feature flag, fetched once within 3 seconds, tells it to; when that request fails, the experiment stays.

That happened on 7 November 2026 in [homedarts-for-autodarts#586](https://github.com/Dennis-Otto/homedarts-for-autodarts/issues/586): the job *changes* of the end-to-end tests ran on `westus2`, StepSecurity's API answered the request with `429`, the log of the agent says `RevertGithubDNSExperiment:false`, it dropped `168.63.129.16`, and the job hung in *Cleaning up orphan processes* until its limit of 5 minutes. The job runs without sudo, so it couldn't take the experiment away itself. HomeDarts' own jobs with containers have done so since [homedarts-for-autodarts#525](https://github.com/Dennis-Otto/homedarts-for-autodarts/pull/525), with a step right after Harden-Runner, because the experiment caused at least 33 of the 46 flaky jobs of [homedarts-for-autodarts#463](https://github.com/Dennis-Otto/homedarts-for-autodarts/issues/463).

[Harden-Runner v2.22.4](https://github.com/step-security/harden-runner/releases/tag/v2.22.4), of 6 November 2026, takes the experiment away also when its feature flags can't be fetched, tries a failed request of its API again and fixes a leak of memory of its agent.

Two jobs of the blueprint block and keep sudo: the job *render* of the shared screenshot bot, once `.github/screenshots.toml` names hosts ([decision 0120](0120-the-screenshot-bot-renders-in-shards-takes-named-files-and-blocks-other-hosts.md)), because the script of a project may start its demo in containers, and the build of the release assets of a Nextcloud app, which builds in Docker. HomeDarts renders its screenshots with the shared bot since [homedarts-for-autodarts#618](https://github.com/Dennis-Otto/homedarts-for-autodarts/pull/618), whose job *render* has no such step.

## Options

1. Only Harden-Runner v2.22.4, and rely on it.
2. Harden-Runner v2.22.4, and every job that blocks and keeps sudo takes the experiment away itself as well, as HomeDarts' jobs do.
3. Audit mode everywhere, the fallback of decision 0088.

## Decision

Option 2. The block stays in force, as decision 0088 wants.

- **v2.22.4 everywhere.** Every workflow of the blueprint, which the template includes, pins it, in 98 places, ahead of the seven days that Renovate waits for a release, as decision 0088 did for v2.22.3, because it carries the fix. It joins `FIXED_RELEASES` of `tests/test_template.py`, the releases that fix an advisory or a bug which a pin once fell under: `test_no_workflow_pins_an_action_below_the_release_that_fixes_its_advisory` fails for an older version, in the blueprint and in every kind of project, so that no workflow falls back, and the tests of every pin keep its commit and its version. Renovate takes every later release as before.
- **A job with sudo makes sure.** The feature flags can still say no, and a job that keeps sudo can take the experiment away for itself at no cost. Right after Harden-Runner, such a job runs *Let Harden-Runner see the DNS lookups*: when a drop-in `90-egress-proxy.conf` of systemd-resolved is there, or `/etc/resolv.conf` names the resolver of the experiment, `127.0.0.100`, it removes the drop-ins, restarts systemd-resolved, points `/etc/resolv.conf` at its stub again, stops the two services of the experiment and empties the cache, and says so in a notice; otherwise it does nothing. It is HomeDarts' step word for word, which has run in its end-to-end tests since 1 November 2026. Then the warm-up of decision 0088 follows, which asks the hosts of the job. The step runs where the job keeps sudo: in *render* when the settings of the project block, in the build when `PUBLISH_TO` is `nextcloud-appstore`. A job without sudo can't run it, since its sudo is off so that no step can lift the block, and relies on v2.22.4; a job that only records its traffic drops nothing.
- **A failure shows at once.** When systemd-resolved doesn't come back, the step fails and the job with it, at once and with the step's name, instead of hanging until its limit. Stopping the services of the experiment and emptying the cache fail nothing, because they may be gone already.
- **Tests keep it so.** `test_every_job_that_blocks_and_keeps_sudo_lets_harden_runner_see_its_dns_lookups` fails for a job that blocks and keeps sudo without the step right after Harden-Runner, with another condition or another script, and for the step in a job without sudo or one that only records. Three tests run the script with a stand-in for sudo and the files of a runner in a folder of their own: without the experiment, with each of its two drop-ins or its resolver, and with a systemd-resolved that doesn't restart.

## Consequences

A job without sudo still depends on Harden-Runner: should its feature flags say no on a runner with the experiment, it can still hang, and the bots of decision 0088 run it once more.

The step costs two looks at a file and one `grep` when the experiment is not there, and a restart of systemd-resolved when it is.

*The way to audit and back* of decision 0088 removes this step together with the warm-up, and brings it back with it. The step can go on its own, with its tests, once GitHub ends the experiment, or once the jobs of a release have run a month without its notice.

The workflows of a project change in the project. One that pins Harden-Runner takes v2.22.4 from Renovate, or at once by hand; one that blocks and keeps sudo copies the step from `.github/workflows/screenshot-bot.yml`, right after Harden-Runner.
