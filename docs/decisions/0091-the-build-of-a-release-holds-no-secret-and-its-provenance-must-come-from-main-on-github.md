# The build of a release holds no secret, and its provenance must come from a run for main on a runner of GitHub

- Status: accepted
- Date: 2026-11-01

## Context

Every release is built in the isolated workflow `build-release.yml`, so that its provenance names that build alone, as SLSA Build Level 3 asks. Three gaps remained, tracked in [#444](https://github.com/Dennis-Otto/repo-blueprint/issues/444):

- **The build held every secret of the release.** Its job entered the environment `release` in every repository, and the release workflow called it with `secrets: inherit`, so that a Nextcloud app could be signed with the key of that environment. The build runs actions of others, such as the one that writes the SBOMs and those that set up PHP, Node and Python, and the same environment holds `RELEASE_AUTOMATION_PRIVATE_KEY`, the key of the release app, which can change the settings and the workflows of every repository it is installed on. Only a Nextcloud app needs a secret in its build, every other kind none. zizmor's audit `secrets-inherit` was ignored for every `release.yml`.
- **The provenance was checked for its workflow only.** `verify-release.yml` and the commands of `SECURITY.md` asked `gh attestation verify` for the workflow that signed the provenance, but not for the branch its run was for nor the machine it ran on, and for the image in GHCR not even for the workflow. An attestation of the same workflow, run for another branch or on a self-hosted runner, passed.
- **A release published outside the release workflow went unchecked for up to a week.** The verification ran after each run of the release workflow and every week.

The container image is built and attested by the release workflow itself, in the job that pushes it, not by the isolated build, so it reaches SLSA Build Level 2 only, while the pages claimed Level 3.

## Options

1. Keep the environment for every build, and accept the risk in `docs/security.md`.
2. Render the environment and `secrets: inherit` only for a Nextcloud app, whose build signs it; every other build holds no secret but the token of its job.
3. As 2, and split the environment `release` of a Nextcloud app at once into `release` (the key of the release app), `signing` (`APP_PRIVATE_KEY`, for the build) and `appstore` (`APPSTORE_TOKEN`).

## Decision

Option 2, with the stricter verification.

- **No environment for the build, but that of a Nextcloud app.** The blueprint's own `build-release.yml` and `release.yml` have no environment and pass no secrets; their templates add both for `publish_to` `nextcloud-appstore` only, through `includes/replace.jinja`, which fails the render when the text it replaces is gone. zizmor accepts the passed secrets only at that one line of a Nextcloud app, with `# zizmor: ignore[secrets-inherit]`, no longer in `.github/zizmor.yml` for every `release.yml`.
- **The provenance of a run for `main` on a runner of GitHub.** Every `gh attestation verify` of `verify-release.yml`, and that of `publish-store.yml` before a zip goes to the Chrome Web Store, demands `--source-ref refs/heads/main --deny-self-hosted-runners`, the check of the image in GHCR also `--signer-workflow` of `release.yml`, and so do the commands of `SECURITY.md` and the README of a container image. The latest releases of the repositories of the owner passed these flags before the change, and each failed for `--source-ref refs/heads/other`.
- **A release published by anybody else is verified at once.** `verify-release.yml` starts on `release: published` too. The release workflow publishes with the token of its job, whose events start no workflow, so only a release that it didn't publish starts it, and none of its own is verified twice. GitHub mails the failure of that run only to whoever published the release, so the bot-health bot, which otherwise acts on runs of the default branch alone, takes this one run of a tag too and opens an issue of its own that names the tag, and only a run for that tag closes it: the weekly run checks the latest release alone, so it says nothing about a prerelease.
- **SLSA Build Level 2 for the image,** in `SECURITY.md` and the pages, until the image is built in an isolated workflow too ([#531](https://github.com/Dennis-Otto/repo-blueprint/issues/531)).

Option 3 waits until the maintainer has set the secrets of the two Nextcloud apps in the new environments: switching first would stop their releases. Until then the build of a Nextcloud app still enters the whole environment `release`, which `docs/security.md` names as a remaining risk. [#530](https://github.com/Dennis-Otto/repo-blueprint/issues/530) tracks the split and its order: the settings declare the two environments, the settings bot creates them and prints the commands for the secrets, the maintainer sets them, and only then the workflows switch.

## Consequences

The builds of every kind of project but a Nextcloud app, the blueprint's own too, hold no secret but the token of their job, and none of the actions they run can take the private key of the release app or of the settings app, which lie in the same environment. A Nextcloud app keeps building and signing as before. An attestation of another branch, of a self-hosted runner or, for the image, of another workflow fails the verification and the users' command; a release that someone publishes by hand or with a token fails its verification within minutes when it doesn't hold up. The run that `release: published` starts takes the workflow of the commit of its tag, so the weekly run checks it again with the workflow of `main` when it is the latest release.
