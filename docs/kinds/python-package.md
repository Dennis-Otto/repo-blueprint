---
description: "A template for a Python package: Hatchling, Ruff, mypy in its strict mode, tests with every line and branch covered on every core, fuzzing, mutation and property tests, and releases on PyPI by trusted publishing with signed provenance."
---

# Python package template with Hatchling, full coverage and trusted publishing to PyPI

A library or a command for PyPI, built with Hatchling and published without a token.

## Start one

```sh
uvx --from copier==9.19.0 copier copy --data project_type=python-package gh:Dennis-Otto/repo-blueprint my-package
cd my-package
python3 .github/blueprint.py create
```

With [uv](https://docs.astral.sh/uv/) and the GitHub CLI, as [the quick start](../guide.md#start-a-repository) shows. Copier asks for the name, the owner and the other answers, and `create` makes the repository on GitHub, applies the settings as code and prints the checklist.

## What you get

- **The example:** `src/<package>/` with its `py.typed`, the tests in `tests/`, the targets of the fuzzing in `fuzz/`, and `pyproject.toml`, for Python 3.12 and newer. Replace it with the real code; its tests show how.
- **The steps of `scripts/check.sh` for this kind,** the same on your machine and in the CI: Ruff, mypy, the tests with every line and branch covered, on every core, and the build of the package.
- **The steps of every kind:** the text files, the diagrams, the pages in one column, the fragments of the changelog, the accepted advisories, the version, the Git hooks, ShellCheck for the shell scripts and the strict build of the website.
- **Workflows of this kind:** fuzzing with Atheris (`fuzz.yml`), the newest Python on `main` (`newest-python.yml`), the property tests every night (`properties.yml`) and the mutation tests with mutmut every week (`mutation.yml`).
- **Everything that every repository gets:** the PR coach and the fix bot, the release bot, Renovate, the settings as code, the issue assistant, the website in English and German, the security checks and the blueprint bot, as [the guide](../guide.md#what-a-new-repository-gets) lists them.

## The checks that a pull request needs

The ruleset *Protect main* of `.github/repository.toml` lets a pull request merge once these checks pass:

- `check (python)`: `scripts/check.sh` with the tools of Python.
- `lint`, `diagrams`, `docs`, `conventional title`, `codeql`, `dependency-review` and `gitleaks`, which every kind needs: every linter in one job, the pictures of the diagrams, the strict build of the website, the title of the pull request with its entry in the changelog, CodeQL, the review of new dependencies and the secret scan.

## Delivery

Merging the release pull request builds the package once, publishes it on PyPI by trusted publishing from the environment `pypi`, without a token, and attaches it to the release with its SBOM and the signed provenance of SLSA Build Level 3.

## Once by hand

`python3 .github/blueprint.py checklist` ticks off each step that it can see and names the rest, each with its link: the release app of the owner with its private key, as [your own account](../own-account.md) shows, the token of the issue assistant unless its AI is off, OpenSSF Best Practices, the REUSE API and the social preview.

This kind adds these steps:

- Add the trusted publisher on PyPI, with the workflow `release.yml` and the environment `pypi`: <https://pypi.org/manage/account/publishing/>.

## A real repository

No public repository of this kind follows the blueprint yet. The Variants workflow of the blueprint makes one from every change and runs its checks with their real tools, and updates one from the latest release as its blueprint bot would.

How the blueprint compares with other templates: [the comparison](../compare.md).
