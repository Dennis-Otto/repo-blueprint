---
description: "A template for a Node package in TypeScript: Biome for the lint and the format, tsc, node:test with every line, branch and function covered, npm without the scripts of packages, and releases on npm with provenance by trusted publishing."
---

# TypeScript npm package template with Biome, node:test and npm provenance

A package for npm in TypeScript on Node 24, with the tools that Node brings itself where they are enough.

## Start one

```sh
uvx --from copier==9.19.1 copier copy --data project_type=node-package gh:Dennis-Otto/repo-blueprint my-package
cd my-package
python3 .github/blueprint.py create
```

With [uv](https://docs.astral.sh/uv/) and the GitHub CLI, as [the quick start](../guide.md#start-a-repository) shows. Copier asks for the name, the owner and the other answers, and `create` makes the repository on GitHub, applies the settings as code and prints the checklist.

## What you get

- **The example:** `src/index.ts`, built into `dist/`, the tests in `test/`, `tsconfig.json` and `tsconfig.build.json`, `biome.jsonc`, and `package.json` with its lock file. Replace it with the real code; its tests show how.
- **The steps of `scripts/check.sh` for this kind,** the same on your machine and in the CI: the lock file, which must agree with `package.json`, Biome for the lint and the format, tsc for the types, node:test with every line, branch and function covered and its report in the PR coach, and `npm pack`; npm installs without the scripts of the packages.
- **Workflows of this kind:** the newest Node on `main` (`newest-node.yml`), after every change and every week, while the CI checks the Node of `.nvmrc`.
- **The steps of every kind:** the text files, the diagrams, the pages in one column, the fragments of the changelog, the accepted advisories, the lock files, the version, the Git hooks, ShellCheck for the shell scripts and the strict build of the website.
- **Everything that every repository gets:** the PR coach and the fix bot, the release bot, Renovate, the settings as code, the issue assistant, the website in English and German, the security checks and the blueprint bot, as [the guide](../guide.md#what-a-new-repository-gets) lists them.

## The checks that a pull request needs

The ruleset *Protect main* of `.github/repository.toml` lets a pull request merge once these checks pass:

- `check (node)`: `scripts/check.sh` with the tools of Node.
- `lint`, `diagrams`, `docs`, `conventional title`, `codeql`, `dependency-review` and `gitleaks`, which every kind needs: every linter in one job, the pictures of the diagrams, the strict build of the website, the title of the pull request with its entry in the changelog, CodeQL, the review of new dependencies and the secret scan.

## Delivery

Merging the release pull request publishes the package on npm with provenance, by trusted publishing from the environment `npm`, without a token, and attaches it to the release with its SBOM and the signed provenance of SLSA Build Level 3.

## Once by hand

`python3 .github/blueprint.py checklist` ticks off each step that it can see and names the rest, each with its link: the release app of the owner with its private key, as [your own account](../own-account.md) shows, the token of the issue assistant unless its AI is off, OpenSSF Best Practices, the REUSE API and the social preview.

This kind adds these steps:

- Add the trusted publisher on npm, with the workflow `release.yml` and the environment `npm`: <https://www.npmjs.com/settings/~/packages>.

## A real repository

<!-- --8<-- [start:real-repository] -->

[Player Switch for Autodarts](https://github.com/Dennis-Otto/player-switch-for-autodarts) is made from the blueprint: a shared Autodarts display where everyone plays under their own account and a tap on a tile switches players, without signing in again.

The Variants workflow tries every pull request of the blueprint on the answers of Player Switch for Autodarts, before it merges.

<!-- --8<-- [end:real-repository] -->

How the blueprint compares with other templates: [the comparison](../compare.md).
