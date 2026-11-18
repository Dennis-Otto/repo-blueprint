# Instructions for coding agents

Repo Blueprint: Copier template for self-maintaining GitHub repos (Home Assistant/HACS, Nextcloud apps, GitHub Actions, Python, Node/TypeScript, Chrome extensions, Cloudflare Workers, containers): CI, signed SLSA L3 releases, Renovate, OpenSSF Scorecard, settings as code, and a bot that rolls out every template update.

These are the rules for coding agents, such as Claude Code, Codex, GitHub Copilot and Cursor, that change the blueprint; people find the same rules in [CONTRIBUTING.md](CONTRIBUTING.md). Every repository made from the blueprint gets an `AGENTS.md` of its own from [`template/AGENTS.md.jinja`](template/AGENTS.md.jinja). The notes on how the blueprint works are in [.github/agents.project.md](.github/agents.project.md): read them as well.

## Commands

Set up the tools once, then run every check before every push, the same ones the CI runs:

```sh
python3 -m venv .venv
.venv/bin/pip install --require-hashes -r requirements-dev.txt
. .venv/bin/activate && bash scripts/check.sh
```

On Windows, run them in Git Bash, with `py -3` in place of `python3` and `.venv/Scripts/` in place of `.venv/bin/`. While you work, the quicker steps of the checks:

- `pytest -n logical --maxprocesses=8 --cov`: the tests on every core, with every line and branch covered, as `scripts/check.sh` runs them.
- `pytest tests/test_template.py -k name`: one test; the tests of the template render every kind of project, which takes a while.
- `ruff format . && ruff check --fix .`: the format of the code, and the fixes that Ruff can make.
- `bash scripts/markdownlint.sh --fix`: the Markdown of every document, with the version and the rules of the check *lint*, and the fixes that markdownlint can make, with Node 22 or newer or with Docker.
- `python3 blueprint.py fix run`: every fix that a command makes for a step of `scripts/check.sh`, such as those of the text files, the pages and Ruff, as the fix bot makes them in a pull request.
- `python3 blueprint.py locks --compile --fix`: compiles each lock file of pip-compile again after a change of its source, with uv, for its Python and on the versions that it pins.
- `mypy`: the types, in the strict mode of mypy.
- `npm ci --prefix .github/a11y --ignore-scripts && node .github/a11y/check.mjs site`: the accessibility of the website after a build, as the check *docs* checks it on `main`, with Google Chrome or the Chrome named in `CHROME`; `node --test .github/a11y/check.test.mjs` tests the check itself, as `scripts/check.sh` does with every line and branch covered, when Node 24 and a Chrome are there.

With the tools of the website in `.venv-docs`, as CONTRIBUTING.md sets them up, `scripts/check.sh` builds the website strictly as well. Turn on the hook of the repository once with `git config core.hooksPath .githooks`, and it runs the checks before every push.

## Changes

- **Tests come with every change of behavior,** in the same pull request, and a bug fix comes with a test that fails without the fix. `scripts/check.sh` fails when a line or a branch of the code runs in no test. A change of the template comes with a test in `tests/test_template.py` that renders it, for every kind of project that it touches.
- **No test sees the variables that point Git at a repository,** such as `GIT_DIR`, which Git sets for the hook before a push in a worktree and an agent sets for a worktree in a container: `tests/conftest.py` takes them away, so that `git init` and the commits of a test's own repository can't land in the blueprint's, and git in the blueprint's own checkout gets them back from `git_environment` of `tests/shared.py`. A shell script that makes a repository of its own clears them with `unset $(git rev-parse --local-env-vars)`.
- **A test reads YAML with `load_yaml()` of `tests/shared.py`,** which takes the parser of libyaml; a test fails on a `yaml.safe_load` in the tests.
- **A test loads a file of the blueprint by its path under the name of its module** of `source_pkgs` in `pyproject.toml`, such as `mkdocs_blueprint` for `.github/mkdocs_blueprint.py`: coverage decides by that name, the first time that a process runs the file, whether it measures it there, and `tests/test_shared.py` fails on another name.
- **The coding standards** of [CONTRIBUTING.md](CONTRIBUTING.md#coding-standards) apply; an exception to a rule is rare and has its reason in a comment at its place.
- **The documentation changes with the code:** `README.md` and `README.de.md` together, and the pages of the website in `docs/`, the German ones such as `docs/index.de.md` with the English ones.
- **Diagrams** are Mermaid sources in `docs/diagrams/<name>.mmd`, from top to bottom (`flowchart TB`), with `accTitle` and `accDescr`, in the tints of [CONTRIBUTING.md](CONTRIBUTING.md#website). `bash scripts/diagrams.sh` draws each, with Docker, as `docs/images/diagrams/<name>.svg` and `<name>.dark.svg`, and the Markdown shows them with a `<picture>`, whose `alt` repeats the title and the description. Never write a `mermaid` block: the GitHub app shows it as code, and `scripts/check.sh` fails on it once a page shows a picture of a diagram. Wherever Docker runs, draw the pictures before the push: `scripts/check.sh` warns of a source that the branch changed without its pictures, which would fail the check *diagrams* once and start a second round of checks. Without Docker, change the source and push, and the diagram bot draws the pictures on the branch; a German page takes `<name>.de.mmd`.
- **A change for users** (`feat`, `fix`, `perf`) gets an entry in the words of a user, in a new file `changelog.d/<branch>.md` named after the branch without its type, such as `changelog.d/dark-mode.md` for the branch `feat/dark-mode`, below the heading of its kind of change, such as `### Features` or `### Bug fixes`. On a branch of the repository, a pull request without one gets a draft from its title by the fix bot, once: replace its words with what changes for users. The check of the title, *conventional title*, asks for it, and `python3 blueprint.py fragments` checks it as the release takes it in; with `--fix`, it renames a heading that surely means a kind of change, such as `### Fixes` to `### Fixed`. A file of its own conflicts with no other pull request, an entry under `## Unreleased` in `CHANGELOG.md` with every one that adds one at the same place, so write the fragment. The release bot moves the fragments into the section of the next release and writes the version, so leave the released sections alone.
- **A new check, or a new step of `scripts/check.sh`,** comes with its explanation in [`.github/checks.toml`](.github/checks.toml), which the PR coach shows when it fails: what it found, why that matters and how to fix it, and in `autofix` the commands that fix it, which the fix bot runs, or the reason why no command can. The step *Explanations of the checks* of `scripts/check.sh` and a test fail without them, and `python3 blueprint.py coach verify` lists the gaps.
- **A decision that shapes the blueprint** gets a record in [`docs/decisions/`](docs/decisions/README.md), named after the number of its pull request, or of the issue that the pull request fixes, such as `1040-the-oldest-supported-release.md`, and cited by it; open the pull request first, as a draft if needed, or take the number of its issue. Leave the rows of the index to the release, which writes them. The step *Records of decisions* of `scripts/check.sh` fails when two records share a number, a file of the folder is no record, or the index lists a record twice, names a file that doesn't exist or lists the records out of order, and in the CI of a pull request when a new record carries neither number, with the number to take in its log; `python3 blueprint.py decisions --fix` fixes the rows of the index. `tests/test_decisions.py` checks the records of `template/docs/decisions/` the same way.

## Commits and pull requests

- Sign off every commit with `git commit -s`, for the [Developer Certificate of Origin](https://developercertificate.org/); the check *lint* fails without it.
- Sign every commit as well, with `git commit -S` or `commit.gpgsign` set: `-S` signs, `-s` only adds the sign-off. Where the rules of `main` require a verified signature, GitHub blocks the merge of a pull request with an unsigned commit; the check *signed commits* and the PR coach name the commit and how to sign it again.
- The title of a pull request is a [Conventional Commit](https://www.conventionalcommits.org/), such as `feat(settings): add a dark mode`. Pull requests are squashed into one commit named after the title, and the title decides the next version: `fix` and `perf` a patch, `feat` a minor, `!` after the type, such as `feat!:`, a major version (a minor one before 1.0.0). `docs`, `test`, `refactor`, `ci`, `build` and `chore` make no release by themselves.
- The description follows the pull request template and names the issue that it fixes with `Fixes #123`. The issue stays open until a release ships the fix, and a bot closes it then.
- Every change reaches `main` through a pull request that passes every required check.
- **Run `scripts/check.sh`, then push once.** Every push starts every check again and cancels the runs that are still going. Push a second time before the first round of checks has answered only to fix a check that failed.
- **Turn on auto-merge and leave the update to the branch bot.** `main` takes only a pull request that is up to date with it, and the branch bot, the workflow *Update branches*, brings the pull requests that wait for auto-merge up to date one after the other, in the order in which it was turned on, so that each runs its checks once, on the head that merges, as [decision 0028 of the blueprint](https://github.com/Dennis-Otto/repo-blueprint/blob/main/docs/decisions/0028-bring-one-pull-request-at-a-time-up-to-date.md) describes. A pull request that is only behind `main` waits for its turn, which can take hours while others are in front of it, and one without auto-merge is not in the bot's line; on a pull request from a fork, a maintainer turns it on. Never bring a branch that is only behind up to date yourself, neither with *Update branch* on GitHub nor with a merge of `main`.
- **Merge `main` into the branch yourself only in two cases,** in the same push as your fix, with a signed merge commit, and never by a rebase through GitHub:
  - GitHub reports a conflict, which the bot marks with the label `merge-conflict`. A conflict can also be why GitHub starts no run of the pull request at all.
  - A required check fails and `main` holds its fix. The bot's line leaves out a pull request with a failed required check until it is fixed.

## Never

- Never weaken, skip or switch off a check, a test or a security control to get a pull request green: no lower coverage, no deleted or skipped test, no `--no-verify`, no exception to a rule without its reason. Fix the cause.
- Never commit tokens, keys, passwords or personal data, not even in a test or an example.
- Never fix a file of the blueprint only in a repository made from it: the fix belongs here, and the next release brings it to every repository.

## What reaches the other repositories

Every file here is the blueprint's own. A change of `template/`, or of a file of the blueprint that the template includes, such as a workflow, `blueprint/` or a lock file in `stacks/`, reaches every repository made from the blueprint with its next release: the blueprint bot of each repository brings it as a pull request that runs `copier update`, and the Rollout starts the bots one repository after the other.

- **The files of the blueprint** in such a repository are all that the template renders, other than those that `_skip_if_exists` in [`copier.yml`](copier.yml) lists: an update brings their changes, so they change here, never there.
- **The files of the project** are those that `_skip_if_exists` lists: an update never overwrites them, and a change of their template reaches only new repositories. Such a change says in the changelog how an existing repository makes it, and comes with a migration of `blueprint/migrate.py`, for a file of its `MOVABLE`, or a step of `blueprint/checklist.py` that finds what is left, unless no command can make it, which the entry then says.
- **The list of the files of a project** is in `_skip_if_exists` and, for coding agents, in `template/AGENTS.md.jinja`; a test keeps both equal, so a new pattern goes into both.
- **The list of the files of the blueprint,** from which a pull request of such a repository hears that it changes one, is `template/.github/blueprint/owned.txt.jinja`: after a new file of the template or a new pattern, `python3 reference.py` writes it anew, and a test fails until it has.
- **A file of the blueprint that a release removes or renames** gets an entry in `MOVED` of `blueprint/migrate.py`, with the file that takes its place or `None`: the update deletes it, and `migrate` then finds the lines of a project that still name it, such as the badge of a workflow, and points a page of Markdown at the successor. The job `update (kind)` of the Variants workflow fails a pull request whose update removes a file of `owned.txt` without its entry ([decision 1051](docs/decisions/1051-a-release-that-removes-a-file-of-the-blueprint-names-it-in-moved.md)).

## Project notes

See [.github/agents.project.md](.github/agents.project.md).
