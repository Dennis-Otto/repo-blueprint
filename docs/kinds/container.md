---
description: "A template for a container image: Alpine pinned by its digest, Hadolint, a build and a self-test in every pull request, and releases on the GitHub Container Registry for amd64 and arm64 with SBOM and signed provenance."
---

# Container image template: Alpine by digest, Hadolint and multi-arch images on GHCR with SBOM

An image for the GitHub Container Registry, built on a base that Renovate moves by its digest.

## Start one

```sh
uvx --from copier==9.18.2 copier copy --data project_type=container gh:Dennis-Otto/repo-blueprint my-image
cd my-image
python3 .github/blueprint.py create
```

With [uv](https://docs.astral.sh/uv/) and the GitHub CLI, as [the quick start](../guide.md#start-a-repository) shows. Copier asks for the name, the owner and the other answers, and `create` makes the repository on GitHub, applies the settings as code and prints the checklist.

## What you get

- **The example:** `Dockerfile`, which starts from Alpine pinned by its digest, and `app/entrypoint.sh`, which the self-test runs. Replace it with the real code; its tests show how.
- **The steps of `scripts/check.sh` for this kind,** the same on your machine and in the CI: Hadolint for the `Dockerfile`, the build of the image and its self-test.
- **The steps of every kind:** the text files, the diagrams, the pages in one column, the fragments of the changelog, the version, the Git hooks, ShellCheck for the shell scripts and the strict build of the website.
- **Everything that every repository gets:** the PR coach and the fix bot, the release bot, Renovate, the settings as code, the issue assistant, the website in English and German, the security checks and the blueprint bot, as [the guide](../guide.md#what-a-new-repository-gets) lists them.

## The checks that a pull request needs

The ruleset *Protect main* of `.github/repository.toml` lets a pull request merge once these checks pass:

- `check (container)`: `scripts/check.sh` with Hadolint and Docker.
- `lint`, `diagrams`, `docs`, `conventional title`, `codeql`, `dependency-review` and `gitleaks`, which every kind needs: every linter in one job, the pictures of the diagrams, the strict build of the website, the title of the pull request with its entry in the changelog, CodeQL, the review of new dependencies and the secret scan.

## Delivery

Merging the release pull request builds the image for `linux/amd64` and `linux/arm64` and pushes it to the GitHub Container Registry with the tags of the version, such as `1.4.2`, `1.4` and `1`, with its SBOM and the signed provenance of SLSA Build Level 3.

## Once by hand

`python3 .github/blueprint.py checklist` ticks off each step that it can see and names the rest, each with its link: the release app of the owner with its private key, as [your own account](../own-account.md) shows, the token of the issue assistant unless its AI is off, OpenSSF Best Practices, the REUSE API and the social preview.

This kind adds these steps:

- Make the package of the image public after the first release.

## A real repository

No public repository of this kind follows the blueprint yet. The Variants workflow of the blueprint makes one from every change and runs its checks with their real tools, and updates one from the latest release as its blueprint bot would.

How the blueprint compares with other templates: [the comparison](../compare.md).
