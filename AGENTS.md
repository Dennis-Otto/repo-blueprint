# Instructions for coding agents

Repo Blueprint: a Copier template for GitHub repositories, with tests, releases, security checks and bots built in, for seven kinds of projects.

These are the rules for coding agents, such as Claude Code, Codex, GitHub Copilot and Cursor, that change the blueprint; people find the same rules in [CONTRIBUTING.md](CONTRIBUTING.md). Every repository made from the blueprint gets an `AGENTS.md` of its own from [`template/AGENTS.md.jinja`](template/AGENTS.md.jinja). The notes on how the blueprint works are in [.github/agents.project.md](.github/agents.project.md): read them as well.

## Commands

Set up the tools once, then run every check before every push, the same ones the CI runs:

```sh
python3 -m venv .venv
.venv/bin/pip install --require-hashes -r requirements-dev.txt
. .venv/bin/activate && bash scripts/check.sh
```

On Windows, run them in Git Bash, with `py -3` in place of `python3` and `.venv/Scripts/` in place of `.venv/bin/`. While you work, the quicker steps of the checks:

- `pytest -n auto --cov`: the tests on every core, with every line and branch covered, as `scripts/check.sh` runs them.
- `pytest tests/test_template.py -k name`: one test; the tests of the template render every kind of project, which takes a while.
- `ruff format . && ruff check --fix .`: the format of the code, and the fixes that Ruff can make.
- `python3 blueprint.py fix run`: every fix that a command makes for a step of `scripts/check.sh`, such as those of the text files, the pages and Ruff, as the fix bot makes them in a pull request.
- `mypy`: the types, in the strict mode of mypy.
- `npm ci --prefix .github/a11y --ignore-scripts && node .github/a11y/check.mjs site`: the accessibility of the website after a build, as the check *docs* checks it, with Google Chrome or the Chrome named in `CHROME`.

With the tools of the website in `.venv-docs`, as CONTRIBUTING.md sets them up, `scripts/check.sh` builds the website strictly as well. Turn on the hook of the repository once with `git config core.hooksPath .githooks`, and it runs the checks before every push.

## Changes

- **Tests come with every change of behavior,** in the same pull request, and a bug fix comes with a test that fails without the fix. `scripts/check.sh` fails when a line or a branch of the code runs in no test. A change of the template comes with a test in `tests/test_template.py` that renders it, for every kind of project that it touches.
- **No test sees the variables that point Git at a repository,** such as `GIT_DIR`, which Git sets for the hook before a push in a worktree and an agent sets for a worktree in a container: `tests/conftest.py` takes them away, so that `git init` and the commits of a test's own repository can't land in the blueprint's, and git in the blueprint's own checkout gets them back from `git_environment` of `tests/shared.py`. A shell script that makes a repository of its own clears them with `unset $(git rev-parse --local-env-vars)`.
- **The coding standards** of [CONTRIBUTING.md](CONTRIBUTING.md#coding-standards) apply; an exception to a rule is rare and has its reason in a comment at its place.
- **The documentation changes with the code:** `README.md` and `README.de.md` together, and the pages of the website in `docs/`, the German ones such as `docs/index.de.md` with the English ones.
- **Diagrams** are Mermaid sources in `docs/diagrams/<name>.mmd`, from top to bottom (`flowchart TB`), with `accTitle` and `accDescr`, in the tints of [CONTRIBUTING.md](CONTRIBUTING.md#website). `bash scripts/diagrams.sh` draws each, with Docker, as `docs/images/diagrams/<name>.svg` and `<name>.dark.svg`, and the Markdown shows them with a `<picture>`, whose `alt` repeats the title and the description. Never write a `mermaid` block: the GitHub app shows it as code, and `scripts/check.sh` fails on it once a page shows a picture of a diagram. Without Docker, change the source and push, and the diagram bot draws the pictures on the branch; a German page takes `<name>.de.mmd`.
- **A change for users** (`feat`, `fix`, `perf`) gets an entry in the words of a user, in a new file `changelog.d/<branch>.md` named after the branch without its type, such as `changelog.d/dark-mode.md` for the branch `feat/dark-mode`, below the heading of its kind of change, such as `### Features` or `### Bug fixes`. The check of the title, *conventional title*, asks for it, and `python3 blueprint.py fragments` checks it as the release takes it in. A file of its own conflicts with no other pull request, an entry under `## Unreleased` in `CHANGELOG.md` with every one that adds one at the same place, so write the fragment. The release bot moves the fragments into the section of the next release and writes the version, so leave the released sections alone.
- **A new check, or a new step of `scripts/check.sh`,** comes with its explanation in [`.github/checks.toml`](.github/checks.toml), which the PR coach shows when it fails: what it found, why that matters and how to fix it, and in `autofix` the commands that fix it, which the fix bot runs, or the reason why no command can. A test fails without them, and `python3 blueprint.py coach verify` lists the gaps.
- **A decision that shapes the blueprint** gets a record in [`docs/decisions/`](docs/decisions/README.md), with the next free number.

## Commits and pull requests

- Sign off every commit with `git commit -s`, for the [Developer Certificate of Origin](https://developercertificate.org/); the check *lint* fails without it.
- The title of a pull request is a [Conventional Commit](https://www.conventionalcommits.org/), such as `feat(settings): add a dark mode`. Pull requests are squashed into one commit named after the title, and the title decides the next version: `fix` and `perf` a patch, `feat` a minor, `!` after the type, such as `feat!:`, a major version (a minor one before 1.0.0). `docs`, `test`, `refactor`, `ci`, `build` and `chore` make no release by themselves.
- The description follows the pull request template and names the issue that it fixes with `Fixes #123`. The issue stays open until a release ships the fix, and a bot closes it then.
- Every change reaches `main` through a pull request that passes every required check.

## Never

- Never weaken, skip or switch off a check, a test or a security control to get a pull request green: no lower coverage, no deleted or skipped test, no `--no-verify`, no exception to a rule without its reason. Fix the cause.
- Never commit tokens, keys, passwords or personal data, not even in a test or an example.
- Never fix a file of the blueprint only in a repository made from it: the fix belongs here, and the next release brings it to every repository.

## What reaches the other repositories

Every file here is the blueprint's own. A change of `template/`, or of a file of the blueprint that the template includes, such as a workflow, `blueprint/` or a lock file in `stacks/`, reaches every repository made from the blueprint with its next release: the blueprint bot of each repository brings it as a pull request that runs `copier update`, and the Rollout starts the bots one repository after the other.

- **The files of the blueprint** in such a repository are all that the template renders, other than those that `_skip_if_exists` in [`copier.yml`](copier.yml) lists: an update brings their changes, so they change here, never there.
- **The files of the project** are those that `_skip_if_exists` lists: an update never overwrites them, and a change of their template reaches only new repositories. Such a change says in the changelog how an existing repository makes it.
- **The list of the files of a project** is in `_skip_if_exists` and, for coding agents, in `template/AGENTS.md.jinja`; a test keeps both equal, so a new pattern goes into both.

## Project notes

See [.github/agents.project.md](.github/agents.project.md).
