# Jobs that reach any host hold no token that writes

- Status: accepted, amends [0080](0080-jobs-with-secrets-or-tokens-that-write-block-every-host-they-dont-need.md)
- Date: 2026-11-08

## Context

Decision 0080 made every job that holds a secret, an OIDC token or a token that may write block every host that it doesn't need, and left twelve such jobs in audit mode, each with its reason in a list of the tests. `SECURITY.md`, which every repository gets, said all the same that Harden-Runner blocks in every such job ([#719](https://github.com/Dennis-Otto/repo-blueprint/issues/719)): a reader, or the answers for OpenSSF Best Practices, couldn't tell that CodeQL, zizmor, Scorecard, the taint report of a Nextcloud app, the link check, which may write issues, and the publication of the website with its OIDC token only recorded their traffic.

The post steps of Harden-Runner log every host that a job reached, with the process that called it. Over the last four successful runs on `main` of the blueprint and of the seven repositories made from it, on 2026-11-08, the jobs of CodeQL, zizmor, Scorecard and the taint report reached the same few hosts every time: GitHub's, the index of PyPI for zizmor, and the dozen services that Scorecard asks, from its container, where Harden-Runner sees the calls as well. Besides, the runner itself and the actions for artifacts and caches reached the storage of GitHub's results (`productionresultssa*.blob.core.windows.net`) and `*.githubapp.com`, which Harden-Runner allows by itself from GitHub's list of its own domains, so no job names them. Those repositories analyze Python, JavaScript or TypeScript and their workflows; CodeQL may fetch the dependencies of Go, Java or Kotlin, and Rust from their registries, which no run has shown yet. The publication of the website reached GitHub and Sigstore, and only the step that asks the published website reached its domain, which can be the repository's own. The link check reaches every host that the documents link to, and only its last step writes, the issue of broken links of the weekly run.

## Options

1. Keep the twelve jobs in audit mode, and say so in `SECURITY.md`.
2. Block in each of them with the hosts that its runs reached, also in the link check and the publication of the website, with the hosts of the links and of the website's domain.
3. Block where the hosts are known, and give the part of a job that reaches hosts that nobody can name a job of its own without a token that writes; say in `SECURITY.md` which jobs still only record, and why.

## Decision

Option 3.

- **They block.** CodeQL, zizmor and the taint report of a Nextcloud app start with the step *Block every host that the job doesn't need*, with the hosts that their runs reached, and wait until Harden-Runner lets them through, as decision 0088 asks. In a repository with Go, Java or Kotlin, or Rust, the template turns the job of CodeQL back to recording, which `SECURITY.md` says there.
- **Jobs of their own.** The weekly issue of broken links is the job `issue` of `links.yml`, which holds the only token that writes and reaches only GitHub; the check, which reaches every host that the documents link to, only reads. The publication of the website, in `docs.yml` and the blueprint's `dashboard.yml`, reaches only GitHub and Sigstore; the job `website`, which has no token at all, then asks the published website on its domain.
- **What still records.** Scorecard: the Scorecard API takes published results only from a job whose steps are all actions on its list (`ossf/scorecard-infra`, `verify_workflow.go`), so its job can't wait for its hosts or take GitHub's DNS experiment out of the way, as decisions 0088 and 0123 ask of a job that blocks, and blocking without them would bring back the hangs that those decisions fixed. The deliveries to PyPI and npm, which no repository makes yet, so that no run has shown their hosts; CodeQL for Go, Java or Kotlin, and Rust, for the same reason; the build of an image, whose `Dockerfile` reaches the registries of its base images and of what it installs; and Renovate, which reaches the registry of every package manager and the release notes of each dependency.
- **`SECURITY.md` names them.** The `SECURITY.md` of each repository names each of these jobs that runs there with its reason: a delivery only where `PUBLISH_TO` delivers there, CodeQL only where the repository has one of those languages, and Renovate where a workflow of the repository runs it or where it is the blueprint's (hub). That list replaces the one in the tests: `test_every_privileged_job_blocks_the_hosts_that_it_doesnt_need` fails for a job that holds such a token and only records but that `SECURITY.md` doesn't name, and for one that it names but that blocks, is gone or runs for another delivery.

## Consequences

A compromised action in CodeQL, zizmor, the taint report or the publication of the website reaches GitHub and the hosts of its job, no host of its own. A new host that one of them needs fails that job with the blocked call in the summary of Harden-Runner: add the host to the job, as the run names it.

The weekly run of the links and a publication of the website take one more runner each, for a few seconds.

What remains for later: the hosts of the deliveries to PyPI and npm once a repository delivers there, those of CodeQL once a repository analyzes Go, Java or Kotlin, or Rust, and a build of an image whose hosts the project names.
