# A container image is built in an isolated workflow of its own

- Status: accepted
- Date: 2026-11-07

## Context

Every asset of a release is built and attested in `build-release.yml`, a reusable workflow that the release workflow calls with the tag, its commit and the version alone, so that the provenance names that build as its signer and no other job of the release can change it: SLSA Build Level 3. The container image was the exception. The job `ghcr` of `release.yml` built it, pushed it to GHCR and attested it in the same job, so its provenance named `release.yml`, the workflow that also signs the tags, publishes the release and holds the private key of the release app in other jobs. An image therefore reached SLSA Build Level 2 only, which [decision 0091](0091-the-build-of-a-release-holds-no-secret-and-its-provenance-must-come-from-main-on-github.md) wrote into `SECURITY.md`, the READMEs and the pages ([#531](https://github.com/Dennis-Otto/repo-blueprint/issues/531)).

The image is delivered after the release is public, not with the other assets into the draft: a release that fails before it is public leaves no image with its version in the registry, and `:1` and `:1.4` move only once the release is out.

## Options

1. Build the image in `build-release.yml`, in a job of its own. Its provenance would name the same workflow as the other assets, but the image would go to GHCR while the release is still a draft, and the job `assets` of every kind of project would need `packages: write`, which only a container uses.
2. A reusable workflow of its own, `build-image.yml`, which the job `ghcr` of the release workflow calls after `publish`, with the same three inputs as the build of the other assets, and which only that job grants `packages: write`.
3. Keep the build in `release.yml` and leave the image at Level 2.

## Decision

Option 2.

- **`build-image.yml`** checks with `.github/sign-tag.sh` of the commit that runs it that the tag is the one that the release workflow signed, at the commit of the release, before it checks the tag out, as `build-release.yml` does. It builds the image for `linux/amd64` and `linux/arm64` with its SBOM, pushes it with the tags of the version and attests its provenance in GHCR. It holds no secret but the token of its job, and the caller passes no secret. Harden-Runner records its traffic, as it did for the job `ghcr`: Docker reaches the registries of the base images that the Dockerfile names.
- **Every repository gets the file,** not only a container: `release.yml` is the same file in each repository, and GitHub refuses a run of a workflow whose job calls a workflow that isn't there, also when the job doesn't run.
- **The verification and the users' command demand `build-image.yml`** in `--signer-workflow`, with `--source-ref refs/heads/main --deny-self-hosted-runners`: `verify-release.yml`, `SECURITY.md` and the README of a container. As for the other assets, the weekly run also accepts the provenance of `release.yml` for an image made before this change, until the next release, and a run for a tag accepts only `build-image.yml`.
- **No page claims Level 2 any longer:** `README.md`, `README.de.md`, `docs/compare.md`, `docs/compare.de.md`, the pages of the releases, the home page and those of the kind say Level 3 for every asset.

## Consequences

An image reaches SLSA Build Level 3 like every other asset: its provenance names a build that no other job of the release can change, and an attestation of `release.yml` or any other workflow fails the verification of a new release. The job `ghcr` is now a call, so its steps show as *deliver to GHCR / image* in the run. No repository of the owner delivers an image yet: the proof is a real release of a container in a test repository, whose `gh attestation verify oci://ghcr.io/<owner>/<repository>:<version> --repo <owner>/<repository> --signer-workflow <owner>/<repository>/.github/workflows/build-image.yml --source-ref refs/heads/main --deny-self-hosted-runners` passes, whose provenance has the build type of GitHub Actions with `build-image.yml` as the workflow of its build signer, and whose run of `verify-release.yml` passes.

`README.md` belongs to the project, so only a new container repository gets the new command in its README; an existing one changes its line `gh attestation verify oci://…` by hand to the one of its `SECURITY.md`, as the changelog says.
