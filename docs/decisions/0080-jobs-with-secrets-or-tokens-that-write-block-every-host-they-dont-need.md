# Jobs with secrets or tokens that write block every host they don't need

- Status: accepted
- Date: 2026-10-25

## Context

Harden-Runner ran in audit mode in all 89 of its steps: it recorded the network traffic of every job and prevented nothing, and nobody was alerted. A compromised action or tool in a job with the private key of the release app, which can ask for tokens in every repository of the installation, the signing key of a Nextcloud app, an OIDC token for the keyless signatures or a token that may write could have sent them to any host. The logs of the post step of Harden-Runner show that these jobs reach only one to ten hosts, the same in every repository ([#450](https://github.com/Dennis-Otto/repo-blueprint/issues/450)). `SECURITY.md` named Harden-Runner as a control all the same.

## Options

1. Keep audit mode everywhere, and look at the recorded traffic after an incident.
2. Block mode in every job, the checks too.
3. Block mode in every job that holds a secret, an OIDC token or a token that may write, with the hosts that its runs reached; audit mode, with its reason, where the hosts can't be named.

## Decision

Option 3. The checks run the tools and the dependencies of each kind of project, whose hosts change with every update, and hold only tokens that read: blocking them would fail pull requests for hosts that do no harm.

- **What blocks.** Each job that has an environment, a secret other than `GITHUB_TOKEN`, or a permission with `write`, `id-token` too, starts with the step *Block every host that the job doesn't need*: `egress-policy: block` and `allowed-endpoints` with each host as `host:443`. The hosts are those that the post steps of Harden-Runner logged in the runs of the blueprint and of every repository made from it: `api.github.com` for the bots that only use the API, `github.com` where a job checks out or fetches, Sigstore and `*.actions.githubusercontent.com` (the OIDC token comes from a host of the region of the runner) where a job signs, `release-assets.githubusercontent.com` where it downloads a pinned tool.
- **The hosts of a delivery.** The build of a release and its verification add the hosts of the one place where `PUBLISH_TO` delivers, with an expression per place, such as `download.nextcloud.com` for a Nextcloud app or `pypi.org` for a package of PyPI: one workflow serves every kind, and no kind reaches the hosts of another.
- **No sudo, no Docker.** `disable-sudo-and-containers: true` in every such job but the build of a Nextcloud app, which installs krankerl with `dpkg`. Harden-Runner removes Docker with `apt-get` in the background, and a short job that ends before it finishes hangs in *Cleaning up orphan processes* until its timeout, so each such job ends with the step *Wait until Harden-Runner has removed Docker* (`if: always()`, only steps for a failure after it), which waits at most two minutes for `apt-get` and `dpkg` and then warns.
- **What records.** The jobs whose hosts can't be named or weren't measured keep audit mode, each with its reason in `AUDITED_PRIVILEGED_JOBS` of `tests/test_template.py`: the deliveries to PyPI, npm and GHCR, which no repository uses yet; Renovate, which reaches the registry of every package manager; the deployments of the website, which ask the website on its own domain; the link check; CodeQL, zizmor, Scorecard and Psalm's taint analysis, which only upload findings. The workflows of the issue assistant are its templates, which its check keeps equal to its own; they change there.
- **The signing key of a Nextcloud app** is only in the step *Sign the Nextcloud app*, which runs nothing of the project, downloads nothing and removes the key with a `trap` also when it fails. The build with krankerl, the downloads and the project's `scripts/check-package.sh` run in steps of their own, before and after it.
- **No telemetry.** Every workflow that runs the GitHub CLI sets `GH_TELEMETRY: "false"`, so gh doesn't call `cafe.github.com`.
- **Tests keep it so.** `test_every_privileged_job_blocks_the_hosts_that_it_doesnt_need` fails for a new job that holds a secret or may write and records instead of blocking, for a host in the wrong form, and for a host that a `curl` of the job reaches but the job doesn't allow, for the `PUBLISH_TO` that its step runs for; it fails too when a reason stays for a job that blocks or is gone. Other tests check the hosts of each delivery, the step that holds the signing key and the variable of gh.

## Consequences

A compromised action in a job with the release app's key reaches GitHub and the hosts of its job, no host of its own. A new host that a job needs, such as the mirror of a pinned tool, fails that job with the blocked call in the summary of Harden-Runner: add the host to the job, as the run names it.

Harden-Runner allows the hosts of GitHub's Actions service and its storage in every job, and every job that blocks still reaches the API of GitHub, so a compromised step could still put a secret into an artifact of the run or send it to a repository of its own with a token of its own. Blocking narrows what a compromised step can do; the pins of the actions, the list of the allowed actions and the review of their updates stay the guard.

The build of a Nextcloud app keeps `sudo` for setup-php and `dpkg`, so a step with root in that job, krankerl or the project's `scripts/check-package.sh` too, could lift the block or leave a process behind that reads the signing key in the step that signs. Splitting the step narrows that, but doesn't take the key away from the project's code in the same job.

What remains for later: a job of its own without `sudo` that signs the unsigned package of a Nextcloud app, the hosts of the deliveries to PyPI, npm and GHCR once a repository delivers there, the deployments of the website once the domain of each repository is known to the job, and Harden-Runner in the jobs of the issue assistant's templates, in [Dennis-Otto/issue-assistant](https://github.com/Dennis-Otto/issue-assistant).
