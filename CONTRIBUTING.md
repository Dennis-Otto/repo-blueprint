# Contributing

Contributions are welcome through issues and pull requests.
Participation follows [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md), and project decision-making is described in [GOVERNANCE.md](GOVERNANCE.md).
Use [SUPPORT.md](SUPPORT.md) to choose the correct public support channel and [SECURITY.md](SECURITY.md) for private vulnerability reports.

All changes reach the protected `main` branch through pull requests that pass every required check.

## Requirements for changes

- Changes need tests, and the checks of `scripts/check.sh` pass.
- Every commit carries a [Developer Certificate of Origin](https://developercertificate.org/) sign-off, `Signed-off-by: Your Name <you@example.com>`, which `git commit -s` adds.
- Name the issue that a pull request fixes with `Fixes #123` in its description. The issue stays open until a release ships the fix and then closes with a link to the release.

## Tests

New functionality comes with tests in the automated test suite, in the same pull request, and so does every change of behavior. A bug fix comes with a test that fails without the fix, so that the bug can't return unnoticed. `scripts/check.sh` fails when a line or a branch of the code runs in no test. A pull request without the tests it needs is not merged.

A change of the template comes with a test in `tests/test_template.py` that renders it, and the Variants workflow runs the checks of every kind of project with its real tools.

## Coding standards

- **Python** follows [PEP 8](https://peps.python.org/pep-0008/) in the format of [Ruff](https://docs.astral.sh/ruff/), which matches Black, with the rules of Ruff that `pyproject.toml` selects. The code has type hints, which mypy checks in its strict mode.
- **Shell scripts** pass [ShellCheck](https://www.shellcheck.net/), **workflows** pass actionlint and zizmor's audit of their security, and **Markdown** follows the rules of markdownlint in `.markdownlint.jsonc`.
- **Every text file** has LF line endings, no trailing whitespace and a line break at its end; `.editorconfig` sets up most editors for it.

`scripts/check.sh` and the Lint workflow check these standards on every pull request, which merges only when they pass. An exception to a rule is rare and is marked at its place in the code, with its reason in a comment.

## Workflow

1. Open an issue first for anything larger than a small fix, so we can agree on the approach.
2. Create a branch from `main`.
3. Describe what changes for users under `## Unreleased` in `CHANGELOG.md`, in the words of a user; the check *changelog* asks for it in every `feat`, `fix` or `perf` pull request.
4. A change that makes or changes a decision that shapes the blueprint records it in [`docs/decisions/`](docs/decisions/README.md).
5. Open a pull request whose title is a [Conventional Commit](https://www.conventionalcommits.org/), such as `feat(settings): add a dark mode` or `fix: keep the token secret`. Mark a breaking change with `!`. Pull requests are squashed into one commit named after the title, and the title decides the next version: `fix` a patch, `feat` a minor, `!` a major version.

## Checks

```sh
python3 -m venv .venv
.venv/bin/pip install --require-hashes -r requirements-dev.txt
. .venv/bin/activate && bash scripts/check.sh
```

To run them before every push on its own, turn on the hook of the repository once:

```sh
git config core.hooksPath .githooks
```

The dev container in `.devcontainer/` has all of this set up, for VS Code and for GitHub Codespaces: open the repository in it, and `bash scripts/check.sh` runs.

## Website

MkDocs builds the website of the blueprint from `mkdocs.yml` and the pages in `docs/`, which include the READMEs and the changelog. The check *docs* builds it strictly in every pull request, and the Dashboard workflow publishes it with the dashboard. To see it while you write, at <http://127.0.0.1:8000>:

```sh
python3 -m venv .venv-docs
.venv-docs/bin/pip install --require-hashes -r stacks/docs/requirements-docs.txt
.venv-docs/bin/mkdocs serve
```

Pictures make the documentation easier to follow:

- **Diagrams** are Mermaid in a `mermaid` block of the Markdown, which GitHub and the website both draw. They run from top to bottom (`flowchart TB`), so that they keep their size in the column of a page, and have `accTitle` and `accDescr` for screen readers. Their colors are tints that read in the light and the dark theme: blue (`#526cfe`) the blueprint and its bots, orange (`#f59e0b`) you and what is yours, green (`#16a34a`) what comes out. A diagram in a README comes in English and in German.
- **Pictures** are files in `docs/images/`. A page of `docs/` names one as `images/…`, a README as `docs/images/…`, and a hook of the website (`.github/mkdocs_project.py`) shows it there too.
- **The recording and the screenshot** of the README, `docs/images/copier-copy.gif` and `docs/images/dashboard.png`, come from `bash scripts/docs-pictures.sh`, with Docker: run it again after the questions of `copier.yml`, the output of Copier or the dashboard change.

## Releases

The release bot keeps a pull request titled `chore: release x.y.z` with the next version, up to date with `main` and decided anew with every merge. Its section of the changelog is the text of Unreleased; without one, it lists the pull requests. Merging it creates the release with its package, SBOM and signed provenance. New repositories copy the blueprint from its release tags, and the blueprint bot brings every repository made from it up to the new release. A release of dependency updates merges and publishes itself.

A line `Release-As: 2.0.0-beta.1` in the description of a pull request sets the version of the next release, for a prerelease for example. A prerelease keeps the text of Unreleased for the release that follows it.

By contributing, you agree that your contribution is licensed under the MIT-0 license of this project.
