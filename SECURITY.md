# Security policy

## Supported versions

Security fixes are provided for the latest release. A repository made from the blueprint receives a fix with the pull request of its blueprint bot, which updates it to the latest release once it has verified that release, as [Verify a release](#verify-a-release) shows; merge that pull request. To update by hand, verify the release the same way first and then run `copier update --vcs-ref vX.Y.Z` with its tag.

## Reporting a vulnerability

Please do not open a public issue, discussion or pull request for a suspected vulnerability. Use GitHub's private vulnerability reporting for this repository:

<https://github.com/Dennis-Otto/repo-blueprint/security/advisories/new>

Include the affected release, the set-up, reproduction steps and the potential impact. Reports in English or German are welcome.

## What happens next

| Step | Target |
| --- | --- |
| Acknowledgement of the report | within 7 days |
| First assessment, including whether the report is accepted | within 14 days |
| Fix released for a confirmed vulnerability | as fast as possible, at the latest within 90 days |
| Public disclosure | when the fixed release is available, in a GitHub security advisory and the release notes |

If a fix needs longer, for example because the cause lies in an upstream project, you receive an update at least every 14 days. Reporters are credited in the advisory and the release notes unless they prefer to stay anonymous.

## How the project keeps itself secure

- Every pull request runs CodeQL, a Gitleaks secret scan of its commits and, for changed dependencies, a review against known vulnerabilities, and one that adds an alert of CodeQL of high or critical severity can't merge. zizmor audits the workflows of every pull request, and one that adds an alert of zizmor can't merge either. CodeQL and zizmor run after every change of `main` as well, Gitleaks every week over the whole history, and GitHub's secret scanning with push protection stops a known kind of secret before it lands and reports generic ones, such as private keys, connection strings and passwords. OpenSSF Scorecard checks the practices of the repository every week.
- Actions are pinned to commit hashes, only those of GitHub and of a list in the settings as code may run, tokens get the least permissions they need, and Renovate keeps actions, dependencies and images current, with the updates that fix a vulnerability at once.
- OSV-Scanner checks every lock file against the OSV database of known vulnerabilities: in every pull request that changes a lock file, after every change of `main` and every week.
- Harden-Runner records the network traffic of every job of the workflows, so that a connection that doesn't belong there shows, and blocks it in every job that holds a secret, an OIDC token or a token that may write, such as those with the private key of the release app or the signing key of a Nextcloud app: such a job reaches only the hosts that it needs, each named in the job, and runs without `sudo` and Docker where it needs neither. Such a job first waits until Harden-Runner lets its hosts through, because of [a bug on some of GitHub's runners](https://github.com/step-security/harden-runner/issues/708), and one that hangs until its time limit runs once more; the block stays on. The GitHub CLI of the workflows sends no telemetry.
- Releases carry SBOMs of what they ship, under their name and version, as SPDX and as CycloneDX, the licenses of their third-party components (`THIRD_PARTY_NOTICES.md`), an OpenVEX document of the advisories that the project accepts with their reasons, and the signed provenance of an isolated build (SLSA Build Level 3); their tags are signed without a key by the release workflow (gitsign), which builds no release on a tag that it didn't sign; they are immutable once published and are verified as their users can after every release, every week and at once when anybody but the release workflow publishes one.

## Findings of code scanning

CodeQL and OpenSSF Scorecard report their findings in the repository's Security tab. A new alert of CodeQL of high or critical severity, or a new error, stops the merge of the pull request that adds it, which shows the alert at its lines, and so does every new alert of zizmor, the audit of the workflows. The Findings workflow of the [issue assistant](https://github.com/Dennis-Otto/issue-assistant#findings) dismisses the findings that `.github/findings.toml` accepts, each with its reason, and fails while any other finding is open. It names an open finding only by the number and link of its alert, which only maintainers can open; nothing about a possible vulnerability becomes a public issue.

## Verify a release

A release is immutable once it is published, and GitHub signs an attestation of it that ties its tag to its commit and to every file it carries. The release workflow also signs the build provenance of every file with [Sigstore](https://www.sigstore.dev/), using a certificate for the workflow of this repository that is valid for ten minutes. No long-lived signing key exists, so none can leak, and none is stored where the releases are downloaded. The [GitHub CLI](https://cli.github.com/) checks both signatures with the public keys of GitHub and Sigstore, which it fetches itself:

```sh
gh release verify vX.Y.Z --repo Dennis-Otto/repo-blueprint
gh release download vX.Y.Z --repo Dennis-Otto/repo-blueprint --pattern '<asset>'
gh attestation verify <asset> --repo Dennis-Otto/repo-blueprint --signer-workflow Dennis-Otto/repo-blueprint/.github/workflows/build-release.yml --source-ref refs/heads/main --deny-self-hosted-runners
```

`--signer-workflow` accepts only the provenance of the workflow that builds the release, `--source-ref` only that of a run for `main`, the only branch whose runs make releases, and `--deny-self-hosted-runners` only that of a runner of GitHub: an attestation that another workflow, another branch or a machine of someone else made for this repository fails.

Every asset of a release carries this provenance, those that the project builds itself with `scripts/release-assets.sh`, such as the zip of a browser extension, too.

Copier renders a repository from the tag of a release, so the tag must be the one the release workflow made. Only the release app may create a release tag, and the release workflow signs every tag without a key ([gitsign](https://github.com/sigstore/gitsign)). Before every update, the blueprint bot of each repository checks that the release is immutable, that its tag points at a commit of `main` no older than the version the repository has, and that the release workflow of the blueprint signed the tag under the name of that release; it refuses any other release. You check a tag the same way with git and gitsign, where `vA.B.C` is the version your repository has, the `_commit` of its `.copier-answers.yml`; `gh release verify` above holds only for an immutable release:

```sh
git clone --quiet --no-checkout --filter=blob:none https://github.com/Dennis-Otto/repo-blueprint.git blueprint
cd blueprint
# The name inside the tag, which the signature covers: it must print vX.Y.Z.
git cat-file tag vX.Y.Z | sed -n '/^$/q; s/^tag //p'
git merge-base --is-ancestor vX.Y.Z origin/main && echo "on main"
git merge-base --is-ancestor vA.B.C vX.Y.Z && echo "no older than vA.B.C"
gitsign verify-tag vX.Y.Z \
  --certificate-identity https://github.com/Dennis-Otto/repo-blueprint/.github/workflows/release.yml@refs/heads/main \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

Every release describes what it ships in an SBOM, as SPDX in `repo-blueprint.spdx.json` and as CycloneDX in `repo-blueprint.cdx.json`: the files of its tag, without those that only check, test and document the project, or, where the project builds assets of its own with `scripts/release-assets.sh`, the zips and tarballs of that script, under the name `repo-blueprint` and the version of the release. A scanner such as [Grype](https://github.com/anchore/grype) checks it against the advisories it knows. When the project accepts an advisory in `osv-scanner.toml`, with its reason, the release carries the OpenVEX document `repo-blueprint.openvex.json` too, which tells the scanner that the advisory doesn't affect the release; without that document, leave out `--vex`:

```sh
gh release download vX.Y.Z --repo Dennis-Otto/repo-blueprint --pattern 'repo-blueprint.*.json'
grype sbom:repo-blueprint.spdx.json --vex repo-blueprint.openvex.json
```

## Verify the website

The Dashboard workflow publishes the website on GitHub Pages and signs the build provenance of what it publishes with Sigstore, as the release workflow signs a release: `artifact.tar` of the artifact `github-pages` of its run, which GitHub keeps for a day. It then asks the published website for the home page of each of its languages, and for an address that leads nowhere, which must answer with 404, and fails when one doesn't. Take the artifact of the run that published the website, and check it with the GitHub CLI:

```sh
gh run download RUN_ID --repo Dennis-Otto/repo-blueprint --name github-pages
gh attestation verify artifact.tar --repo Dennis-Otto/repo-blueprint --signer-workflow Dennis-Otto/repo-blueprint/.github/workflows/dashboard.yml
```

## Assurance case

This section argues why the way the project is changed, built and delivered meets the requirements of this policy. The software itself, what it protects, where its trust boundaries lie when it runs and which risks remain, is the subject of [docs/security.md](docs/security.md).

### Threat model

An attacker would most likely try to bring malicious code into `main`, through a pull request or through a dependency, an action or an image; to make a workflow run code that it shouldn't run, or leak a secret; to replace a release on its way to the users; or to keep a known vulnerability in a release. A report of a vulnerability is itself sensitive until its fix is released.

### Trust boundaries

1. **Outside contributors → pull requests.** Their code is untrusted. The workflows of their pull requests run only after the maintainer approves them, with a read-only token and without secrets.
2. **Pull requests → `main`.** A change reaches `main` only through a pull request that passes every required check, squashed into one signed commit; nobody can push to `main` directly, force-push it or delete it. The rules of `main` and of the release tags have no exceptions, not even for administrators, but one: only the release app may create a release tag, which the release workflow signs.
3. **`main` → secrets.** Every secret lives in an environment that only workflows on `main` can use, and the jobs that use one run no code of a pull request.
4. **Third-party code → the build.** Dependencies are pinned by version and hash, actions by commit hash and images by digest. An update waits a week after its release, unless it fixes a vulnerability, and passes the same checks as every other change. Updates of the [blueprint](https://github.com/Dennis-Otto/repo-blueprint) come only from a release that is immutable, on the blueprint's `main` and signed by its release workflow, which the blueprint bot verifies first; the workflows of the [issue assistant](https://github.com/Dennis-Otto/issue-assistant) come with them, from a release of the issue assistant that the blueprint verified the same way.
5. **The release → its users.** The release workflow builds every release from its tagged commit, once it has checked that it signed the tag itself, at the commit of the release; GitHub keeps it immutable, and its signatures let users check it, as [Verify a release](#verify-a-release) shows.
6. **Issues → the issue assistant.** Anyone can write an issue, so its text is data for an AI that only reads; a job without the AI checks the answer before anything is posted.

### Secure design principles

- **Least privilege:** tokens are read-only unless a job needs more, and then get only what it needs; each secret is in the one environment that needs it.
- **Fail-safe defaults:** a failed check, a missing secret or an open finding stops a merge or a release instead of being skipped; workflows of outside contributors wait for approval.
- **Complete mediation:** every change of `main` passes the same required checks, nobody can bypass the rules of `main`, and nobody can move or delete a release tag; only the release app creates one.
- **Separation of privilege:** the job in which the AI reads untrusted text, such as an issue, holds no token that writes, and the job that writes runs no AI; only the release workflow on `main` publishes releases.
- **Least common mechanism:** the secrets of the releases and those of the issue assistant are in separate environments, so a job that needs one never holds the other.
- **Economy of mechanism:** one script, `scripts/check.sh`, runs the checks locally and in the CI; one workflow builds, signs and publishes every release.
- **Open design:** the workflows, the settings as code and this policy are public; the protection relies on no secret about how it works.
- **Psychological acceptability:** the dev container has every tool of the checks, and the hook before every push runs the same checks as the CI, so the secure way is the easy one.

### Common weaknesses

How the [OWASP Top 10 CI/CD security risks](https://owasp.org/www-project-top-10-ci-cd-security-risks/) are countered:

| Risk | Countermeasure |
| --- | --- |
| Insufficient flow control mechanisms | pull requests only, every required check, no new alert of CodeQL of high severity and none of zizmor, a linear history, release tags that never move and that only the release app creates |
| Inadequate identity and access management | administrator access only for the maintainers; bots act as GitHub Apps or with the token of their workflow |
| Dependency chain abuse | lock files with hashes, pins by commit hash and digest, updates only a week after their release, a weekly refresh of the lock files that waits for the maintainer, the dependency review and OSV-Scanner |
| Poisoned pipeline execution | no code of a pull request runs with a secret; actionlint and zizmor audit every workflow |
| Insufficient pipeline-based access controls | permissions per job, environments that only `main` can use, actions pinned to commit hashes and only listed actions, as settings of the repository |
| Insufficient credential hygiene | the secret scan with push protection and generic patterns, tokens of the release app that expire after an hour, no secret printed or committed |
| Insecure system configuration | the settings as code, which the settings bot applies after every change and every week, and OpenSSF Scorecard every week |
| Ungoverned usage of third-party services | only the services of the workflows in this repository, each in the jobs that need it, with the least permissions |
| Improper artifact integrity validation | immutable releases with signed provenance, verified after every release and every week; updates only to a verified release of the blueprint |
| Insufficient logging and visibility | the logs of every run, and Harden-Runner, which records the network traffic of every job and blocks every host that a job with a secret or a token that may write doesn't need |

In the code, CodeQL looks for the weaknesses of the [CWE Top 25](https://cwe.mitre.org/top25/) with its extended security queries, on every pull request and every push to `main`. How the code counters the weaknesses that matter for it is part of [docs/security.md](docs/security.md).
