---
description: "A template for a GitHub Action: a composite action in Python with Ruff, mypy, full coverage, fuzzing, mutation and property tests, a run of the action in every pull request, and signed release tags with a moving major tag."
---

# GitHub Action template: a composite action with tests, fuzzing and signed release tags

A composite action whose code is Python, on the Python 3.12 of the runner, so that it starts without a container or a build, tested as its users run it.

## Start one

```sh
uvx --from copier==9.18.2 copier copy --data project_type=github-action gh:Dennis-Otto/repo-blueprint my-action
cd my-action
python3 .github/blueprint.py create
```

With [uv](https://docs.astral.sh/uv/) and the GitHub CLI, as [the quick start](../guide.md#start-a-repository) shows. Copier asks for the name, the owner and the other answers, and `create` makes the repository on GitHub, applies the settings as code and prints the checklist.

## What you get

- **The example:** `action.yml`, the module of the action beside it, its tests in `tests/` and the targets of the fuzzing in `fuzz/`. Replace it with the real code; its tests show how.
- **The steps of `scripts/check.sh` for this kind,** the same on your machine and in the CI: Ruff, mypy and the tests with every line and branch covered, on every core.
- **The steps of every kind:** the text files, the diagrams, the pages in one column, the fragments of the changelog, the version, the Git hooks, ShellCheck for the shell scripts and the strict build of the website.
- **Workflows of this kind:** a run of the action as its users run it, in every pull request (`action-test.yml`), fuzzing with Atheris (`fuzz.yml`), the newest Python on `main` (`newest-python.yml`), the property tests every night (`properties.yml`) and the mutation tests with mutmut every week (`mutation.yml`).
- **Everything that every repository gets:** the PR coach and the fix bot, the release bot, Renovate, the settings as code, the issue assistant, the website in English and German, the security checks and the blueprint bot, as [the guide](../guide.md#what-a-new-repository-gets) lists them.

## The checks that a pull request needs

The ruleset *Protect main* of `.github/repository.toml` lets a pull request merge once these checks pass:

- `check (github-action)`: `scripts/check.sh` with the tools of Python.
- `action`: the action itself, as `action-test.yml` runs it.
- `lint`, `diagrams`, `docs`, `conventional title`, `codeql`, `dependency-review` and `gitleaks`, which every kind needs: every linter in one job, the pictures of the diagrams, the strict build of the website, the title of the pull request with its entry in the changelog, CodeQL, the review of new dependencies and the secret scan.

## Delivery

Merging the release pull request creates the signed release tag, such as `v1.4.2`, and moves the major tag, such as `v1`, to it, so that the users of `@v1` get every compatible release. The release has its SBOM and the signed provenance of SLSA Build Level 3.

## Once by hand

`python3 .github/blueprint.py checklist` ticks off each step that it can see and names the rest, each with its link: the release app of the owner with its private key, as [your own account](../own-account.md) shows, the token of the issue assistant unless its AI is off, OpenSSF Best Practices, the REUSE API and the social preview.

This kind adds no step of its own.

## A real repository

The [issue assistant](https://github.com/Dennis-Otto/issue-assistant) is made from the blueprint: a first analysis of every new issue by an AI that only reads, which every repository of the blueprint runs.

How the blueprint compares with other templates: [the comparison](../compare.md).
