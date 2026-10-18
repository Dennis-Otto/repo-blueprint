---
description: "A template for a GitHub repository without a build, such as documentation, configuration or scripts: the checks of the text files and shell scripts, a website, signed releases, the settings as code and the bots of every repository."
---

# GitHub repository template for documentation, configuration and scripts, with releases and settings as code

A repository of documentation, configuration or scripts, which needs no build and gets the same care as every other kind.

## Start one

```sh
uvx copier copy --data project_type=generic gh:Dennis-Otto/repo-blueprint my-repository
cd my-repository
python3 .github/blueprint.py create
```

With [uv](https://docs.astral.sh/uv/) and the GitHub CLI, as [the quick start](../guide.md#start-a-repository) shows. Copier asks for the name, the owner and the other answers, and `create` makes the repository on GitHub, applies the settings as code and prints the checklist.

## What you get

- **The example:** none, only the community files, the website in `docs/` and the workflows.
- **The steps of every kind:** the text files, the diagrams, the pages in one column, the fragments of the changelog, the version, the Git hooks, ShellCheck for the shell scripts and the strict build of the website.
- **Everything that every repository gets:** the PR coach and the fix bot, the release bot, Renovate, the settings as code, the issue assistant, the website in English and German, the security checks and the blueprint bot, as [the guide](../guide.md#what-a-new-repository-gets) lists them.

## The checks that a pull request needs

The ruleset *Protect main* of `.github/repository.toml` lets a pull request merge once these checks pass:

- `check (generic)`: `scripts/check.sh` with the text files and the shell scripts.
- `lint`, `diagrams`, `docs`, `conventional title`, `codeql`, `dependency-review` and `gitleaks`, which every kind needs: every linter in one job, the pictures of the diagrams, the strict build of the website, the title of the pull request with its entry in the changelog, CodeQL, the review of new dependencies and the secret scan.

## Delivery

Merging the release pull request publishes a release with its notes from the changelog and a signed tag, without a package.

## Once by hand

`python3 .github/blueprint.py checklist` ticks off each step that it can see and names the rest, each with its link: the release app of the owner with its private key, as [your own account](../own-account.md) shows, the token of the issue assistant unless its AI is off, OpenSSF Best Practices, the REUSE API and the social preview.

This kind adds no step of its own.

## A real repository

[dennis-otto.github.io](https://github.com/Dennis-Otto/dennis-otto.github.io) is made from the blueprint: the website with every project of its owner.

How the blueprint compares with other templates: [the comparison](../compare.md).
