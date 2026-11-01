# Contributing

Contributions are welcome through issues and pull requests.
Participation follows [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md), and project decision-making is described in [GOVERNANCE.md](GOVERNANCE.md).
Use [SUPPORT.md](SUPPORT.md) to choose the correct public support channel and [SECURITY.md](SECURITY.md) for private vulnerability reports.

All changes reach the protected `main` branch through pull requests that pass every required check.
Coding agents find these rules in short in [AGENTS.md](AGENTS.md), with what a change of the template reaches; a change of a rule here changes it there as well.

## Requirements for changes

- Changes need tests, and the checks of `scripts/check.sh` pass.
- Every commit carries a [Developer Certificate of Origin](https://developercertificate.org/) sign-off, `Signed-off-by: Your Name <you@example.com>`, which `git commit -s` adds.
- Name the issue that a pull request fixes with `Fixes #123` in its description. The issue stays open until a release ships the fix and then closes with a link to the release.

## Tests

New functionality comes with tests in the automated test suite, in the same pull request, and so does every change of behavior. A bug fix comes with a test that fails without the fix, so that the bug can't return unnoticed. `scripts/check.sh` fails when a line or a branch of the code runs in no test. A pull request without the tests it needs is not merged.

`scripts/check.sh` runs the tests on every logical core with pytest-xdist, in at most eight processes unless `PYTEST_XDIST_AUTO_NUM_WORKERS` sets another number, so each test stands on its own, without the state or the order of another one. A folder that many tests read and that takes long to make, such as the project of each kind that the tests of the template render, is made once for the whole run with `once` of `tests/shared.py`, and a test that changes such a folder works on a copy of it. `render()` of `tests/test_template.py` compiles each template of Jinja once in each process, so that a project of a test takes a third of a second to render, as [decision 0070](docs/decisions/0070-the-tests-run-on-every-logical-core-at-most-eight.md) describes. pytest-timeout fails a test that hangs after five minutes. No test sees the variables that point Git at a repository, such as `GIT_DIR`, which Git sets for the hook before a push in a worktree and an agent sets for a worktree in a container: `tests/conftest.py` takes them away, so that `git init` and the commits of a test's own repository can't land in the blueprint's, and git in the blueprint's own checkout gets them back from `git_environment` of `tests/shared.py`.

A change of the template comes with a test in `tests/test_template.py` that renders it, and the Variants workflow runs the checks of every kind of project with its real tools, for a new repository and for one that the update brings from the latest release. Its legs *pictures* run the starter `scripts/screenshots.sh` of a new Home Assistant integration, Nextcloud app and generic repository with Docker, in a pull request that changes what the pictures depend on, such as an update of an image or of Playwright, and every week. It updates one with the answers of each repository that takes the blueprint as well, the files of `tests/answers/`, and the Downstream workflow updates those repositories themselves, cloned read-only, as their blueprint bots will after the release: its summary names the files of each repository whose update the pull request changes and each conflict, and a conflict that the pull request brings into a file that is not a page, such as a workflow, a script or a configuration, fails it, as [decision 0039](docs/decisions/0039-try-every-change-on-the-repositories-that-take-the-blueprint.md) describes. `python3 downstream.py --base origin/main` runs the same on your machine, with the changes that you haven't committed yet, and `python3 downstream.py --answers` writes `tests/answers/` anew when a repository changed its answers, of which Downstream warns. A change that the files of a project must follow, which an update never touches, says in the changelog how an existing project makes it.

A bot in the `run:` of a step of a workflow, such as the clean-up bot that deletes branches or the release bot that merges a release, runs in its tests as GitHub runs it: `run_step()` of `tests/workflow_steps.py` takes its script from the parsed workflow and runs it in bash, Git Bash on Windows, with the variables of the step and a fake gh, `tests/fake_gh.py`, which answers each call as the test plans it, fails a call that the test didn't plan and writes every call down. A step that deletes, starts, merges, publishes or comments needs such a test: the census in `tests/test_workflow_steps.py` finds each one and fails until a test runs it, as [decision 0040](docs/decisions/0040-every-step-of-a-bot-that-changes-github-runs-in-a-test.md) describes. A test that gives gh the JSON of the API, for a step whose filter of `--jq` decides what the bot touches, needs jq, which the runners of GitHub have; without it, the test is skipped. `tests/fake_gh.py` is the only fake gh of the tests: a test of a step never writes a gh of its own. A test reads the jobs of a workflow, their permissions and the conditions of jobs and steps from the parsed workflow, with `parse()`, `job_in()`, `step_in()` and `condition_of()` of `tests/workflow_steps.py`, never from a slice of its text, which can hold a line of another job or of a comment. A guard in `tests/test_workflow_steps.py` fails, with the file and the line, on a test that slices the text of a workflow or writes a gh of its own.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/diagrams/how-a-test-runs-a-step-of-a-bot.dark.svg">
  <img src="docs/images/diagrams/how-a-test-runs-a-step-of-a-bot.svg" alt="How a test runs a step of a bot: A test names a step of a workflow and plans the answers of gh. run_step reads the step from the parsed workflow, with the variables of the step, its job and its workflow, and runs its script in bash with the options of GitHub, in Git Bash on Windows. gh is the fake gh, which answers each call as planned, fails a call without an answer and writes every call down with what it read. The test checks the calls, the summary, the outputs and the exit code. A census finds every step that deletes, starts, merges, publishes or comments, and fails while one of them runs in no test.">
</picture>

A new check runs only where it can change a result, as [decision 0009](docs/decisions/0009-run-a-check-only-where-it-can-change-a-result.md) describes: a required check in every pull request and without a path filter, a scanner in the pull requests that change what it reads, and on `main` only what keeps a baseline or publishes.

## Coding standards

- **Python** follows [PEP 8](https://peps.python.org/pep-0008/) in the format of [Ruff](https://docs.astral.sh/ruff/), which matches Black, with the rules of Ruff that `pyproject.toml` selects. The code has type hints, which mypy checks in its strict mode.
- **Shell scripts** pass [ShellCheck](https://www.shellcheck.net/), which the CI never skips, **workflows** pass actionlint and zizmor's audit of their security, and **Markdown** follows the rules of markdownlint in `.markdownlint.jsonc`.
- **A new action or reusable workflow** needs its pattern `owner/repo@*` in `[actions.selected]` of `.github/repository.toml` and `template/.github/repository.toml.jinja`, also for what it runs in turn: GitHub starts only the listed ones. The step *Check that the allowed actions let every action start* of the check *lint* fails while the list lacks one, in the blueprint and in each kind of project of the Variants, and `python3 blueprint.py settings actions` runs it on your machine, with the GitHub CLI. Its jobs start once a maintainer has run `python3 blueprint.py settings apply`. A step with `uses: docker://…` is an action as well, which GitHub refuses whatever the list names, and `settings check` names it too: run the image in a `run:` step instead, pinned by its digest, as `docker run --rm --volume "$PWD:/github/workspace" --workdir /github/workspace <image>` with the step's `with: args` after it and its `entrypoint` as `--entrypoint`, which is what GitHub does for such a step.
- **Every text file** has LF line endings, no trailing whitespace, a line break at its end and no conflict markers that a merge left; `.editorconfig` sets up most editors for it.

`scripts/check.sh` and the Lint workflow check these standards on every pull request, which merges only when they pass. An exception to a rule is rare and is marked at its place in the code, with its reason in a comment.

## Workflow

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/diagrams/the-way-of-a-contribution.dark.svg">
  <img src="docs/images/diagrams/the-way-of-a-contribution.svg" alt="The way of a contribution: An issue first for anything larger, a branch from main, the change with its tests and an entry in a new file of changelog.d, every commit signed off, and a pull request with a Conventional Commit title. Once every required check passes, it is squashed into main, and its title decides the next version.">
</picture>

1. Open an issue first for anything larger than a small fix, so we can agree on the approach.
2. Create a branch from `main`.
3. Describe what changes for users, in the words of a user, in a new file in `changelog.d/` named after your branch without its type, such as `changelog.d/dark-mode.md` for the branch `feat/dark-mode`, below the heading of its kind of change, such as `### Features` or `### Bug fixes`. The check of the title, *conventional title*, asks for it in every `feat`, `fix` or `perf` pull request, and checks it as the release takes it in. A file of its own conflicts with no other pull request; a line under `## Unreleased` in `CHANGELOG.md` works as well, but conflicts with each pull request that adds one at the same place.
4. A change that makes or changes a decision that shapes the blueprint records it in [`docs/decisions/`](docs/decisions/README.md).
5. Open a pull request whose title is a [Conventional Commit](https://www.conventionalcommits.org/), such as `feat(settings): add a dark mode` or `fix: keep the token secret`. Mark a breaking change with `!`. Pull requests are squashed into one commit named after the title, and the title decides the next version: `fix` a patch, `feat` a minor, `!` a major version, or a minor one while the version is below 1.0.0.

### The changelog

A fragment holds the entries of one pull request, each below the heading of its kind of change:

```markdown
### Features

- **Dark mode:** the settings follow the theme of the system.
```

The headings are those of the blueprint, `Breaking changes`, `Features`, `Changes`, `Bug fixes` and `Performance`, those of [Keep a Changelog](https://keepachangelog.com/), `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed` and `Security`, and every other one that `CHANGELOG.md` has already. The release bot moves the entries of every fragment and of Unreleased into the section of the next release, each kind of change below one heading, and deletes the fragments in the same commit of the release pull request. `bash scripts/check.sh` checks every fragment as the release takes it in, those that wait on `main` for the next release too, with `python3 blueprint.py fragments`. A heading that surely means a kind of change, such as `### Fixes` for `### Fixed` or `## Features` for `### Features`, `python3 blueprint.py fragments --fix` renames, as the fix bot does on the branch of a pull request and suggests on one from a fork; a heading as close to one kind as to another, such as `### Change`, stays for you. The check of the title, *conventional title*, takes only a new fragment as the entry of a pull request: one that `main` has already is the entry of another pull request that waits for its release, so a pull request that changes it gets a warning, and one that needs an entry adds a fragment of its own under a new name. A page of the website that includes `CHANGELOG.md` with a line `--8<-- "CHANGELOG.md"` shows the entries of the fragments under Unreleased until the release takes them in, grouped as the release groups them.

## Checks

```sh
python3 -m venv .venv
.venv/bin/pip install --require-hashes -r requirements-dev.txt
. .venv/bin/activate && bash scripts/check.sh
```

On Windows, run them in Git Bash, which comes with [Git for Windows](https://gitforwindows.org/), with `py -3` in place of `python3` and `.venv/Scripts/` in place of `.venv/bin/`. The Windows workflow runs them there as well: every week, and for each pull request that changes the code or the tests.

To run them before every push on its own, turn on the hook of the repository once:

```sh
git config core.hooksPath .githooks
```

Git runs the hook only when its file is executable. Windows has no such mode and adds the file as a plain one, which `scripts/check.sh` reports; `git update-index --chmod=+x .githooks/pre-push` and a commit make it executable.

The dev container in `.devcontainer/` has all of this set up, for VS Code and for GitHub Codespaces: open the repository in it, and `bash scripts/check.sh` runs.

## When a check fails

A check that fails explains itself. The PR coach writes what the check found, why that matters and how to fix it, with the commands to run, into the summary of the check and as its annotation; the pull request also shows each finding of a tool at the line that it names, as an annotation, and the comment lists them: those of the text files, Ruff, ShellCheck, mypy and pytest, of PHP CS Fixer, Psalm and PHPUnit, and of Biome, the TypeScript compiler and the tests of Node. After the checks, the coach keeps one comment on the pull request up to date with a section for each check that failed, also on a pull request from a fork, and a title that is no Conventional Commit gets one that passes. The comment follows every push and says so once every check passes. On a pull request of a person, the same comment also says what the merge makes: the next version, from the title and a `BREAKING CHANGE:` or `Release-As:` line of the description; the entry that it adds to the changelog; the coverage of the tests against that of `main`, file by file; and, when it changes the website, a link to the website that the check *docs* built, with the address of each page that it changes. While the checks pass, it comments only when it has something of this to say. On your machine, `scripts/check.sh` explains the step that stopped it in the same words.

The explanations are in [`.github/checks.toml`](.github/checks.toml). A new check, or a new step of `scripts/check.sh`, comes with its explanation there, in the same pull request: what it found, why that matters and how to fix it, with the commands and a link to read more. The step *Explanations of the checks* of `scripts/check.sh` fails for a required check or a step without one, and so does a test; `python3 blueprint.py coach verify` lists them. The coach runs no code of a pull request and shows the text of its checks only as code, as [decision 0022](docs/decisions/0022-every-check-explains-its-failure.md) describes.

## Pull requests fix themselves

What a command can fix, a pull request fixes by itself. When a check fails, its job runs the commands of `autofix` from `.github/checks.toml` on the head of the pull request, such as `ruff format .` or the fix of the text files, and keeps the files that they changed. After the checks, the fix bot commits them as one commit onto a branch of this repository, also one of Renovate, and the checks run again: pull the branch before you push again. On a pull request from a fork, it suggests the fixes at their lines, and **Commit suggestion** takes each. A pull request with the label `no-bot-fixes` gets no commit of the bot. On your machine, `python3 blueprint.py fix run` runs the same commands, `python3 blueprint.py fix text` fixes the text files alone, and `python3 blueprint.py fix version` writes the version of the release bot back into each file where a hand changed it.

Every explanation in `.github/checks.toml` says in `autofix` how its check fixes itself: the commands, a list in which `{blueprint}` stands for `python3` and the `blueprint.py` of the repository, or a sentence with the reason why no command can. A new check, or a new step of `scripts/check.sh`, comes with its `autofix` as well; a test fails without one, and `python3 blueprint.py coach verify` lists the gaps. The bot runs nothing of a pull request with a token that can write, and commits only text files that the commit has already, outside `.git` and the workflows, as [decision 0023](docs/decisions/0023-pull-requests-fix-themselves.md) describes. When the tests fail because a pinned download, such as gitsign, disagrees with its sha256 in `.github/pins.toml`, the fix bot runs `python3 pins.py` too, by the autofix of `.github/checks.project.toml`, and commits what it writes outside `.github/workflows/`; a sha256 in a workflow still needs a person.

## Website

MkDocs builds the website of the blueprint from `mkdocs.yml` and the pages in `docs/`, which include the READMEs and the changelog. The check *docs* builds it strictly in every pull request; after the build, lychee checks every link and anchor of the built pages, also those written in HTML, without asking a server, `python3 blueprint.py site-check site` what the hooks of the website promise, such as a sitemap in every folder of pages and the 404 page in the default language, that no page loads more than 1,200 KB at once on a phone (its stylesheets, scripts, search, first pictures and, for a `mermaid` block, Mermaid, compressed as GitHub Pages sends them), and that every page shows each picture of its Markdown, the parts of the README included, with no empty paragraph where a plugin took one out, and `scripts/check-site.sh`, where it exists, the website as this project alone does. The Dashboard workflow publishes it with the dashboard, signs its provenance and asks the published website for its pages. To see it while you write, at <http://127.0.0.1:8000>:

```sh
python3 -m venv .venv-docs
.venv-docs/bin/pip install --require-hashes -r stacks/docs/requirements-docs.txt
.venv-docs/bin/mkdocs serve
```

On Windows, use `py -3` in place of `python3` and `.venv-docs/Scripts/` in place of `.venv-docs/bin/`; the dev container sets these tools up on its own. With them, `bash scripts/check.sh` builds the website strictly as well and checks what its hooks promise, as the check *docs* does, and without them it leaves that to the CI. The preview cards for social media come from the CI alone, because they need the Cairo library, which Windows doesn't have; where it is installed, `CI=true` before the command draws them too.

Pictures make the documentation easier to follow, and so do [diagrams](#diagrams):

- **Pictures** are files in `docs/images/`. A page of `docs/` names one as `images/…`, a README as `docs/images/…`, and a hook of the website (`.github/mkdocs_project.py`) shows it there too.
- **On the website**, the hook of every website (`.github/mkdocs_blueprint.py`) makes the pictures quick to load: the first one of a page loads first, every other one as the reader comes to it, and a PNG, a GIF or a WebP gets its width and height, so that the page doesn't shift. A `<picture>` with a `<source media="(prefers-color-scheme: dark)">` becomes a picture for each theme, which follows the switch of the website and loads only in its theme, and opens enlarged among the pictures of that theme. A GIF with `NAME.mp4` beside it plays as that video, a third of its size, while it is in view, with `NAME.webp` or `NAME.png` until it plays; a reader who asks the system for less motion starts it.
- **The recording and the screenshot** of the README, `docs/images/copier-copy.gif` with its video `copier-copy.mp4` and its last screen `copier-copy.webp`, and `docs/images/dashboard.png`, come from `bash scripts/docs-pictures.sh`, with Docker, which also makes `docs/images/social-preview.webp`, the social preview of the home page at a seventh of its size, and the pictures of the pages of GitHub, such as `docs/images/github-release.png` and its `.dark.png`, which `.github/docs-pictures/github_pages.py` takes from pages that no longer change, with a clock that stands still. The Docs pictures workflow runs it after every release that changed a file of `.github/docs-pictures/paths.txt`, and on demand, and keeps one pull request from `bot/pictures` with the pictures whose pixels changed, which merges itself. A new question of `copier.yml` needs its key in `.github/docs-pictures/copier-copy.tape`, or the recording waits for ever; a test of the blueprint says so, as the run after a release would. To see what a change of yours changes, run it, then `python3 blueprint.py screenshots restore`, which gives every picture that looks the same its committed file back.

### Languages, search and search engines

The hook of every website, `.github/mkdocs_blueprint.py`, keeps each page in its language for readers, the search and search engines ([decision 0042](docs/decisions/0042-each-language-of-a-website-searches-and-describes-itself.md)):

- **The search** of a page looks only through the pages of its language: the hook writes `search/search_index.en.json` and `search/search_index.de.json` beside the index of every language, and a German page searches the German pages and the English ones that have no German version, at their address in `de/`. The sources of a diagram that a page still draws live, from a `mermaid` block, stay out of it, and so do the template of the decision records and a page with `robots: noindex` in its front matter.
- **A page that the German website shows untranslated,** such as `de/roadmap.html` without a `roadmap.de.md`, is a copy of the English page: its text says it is English, its canonical address is that of the English page, no search engine lists it, and the English page names no German version.
- **Every other page** names its versions in the other languages with their full addresses and `x-default`, and gets a description of its own from its first paragraph with words of its own, so not from a line of links such as the one to the other language, unless its front matter has `description:`; the home page of each language keeps the `site_description` of `mkdocs.yml`, and its preview card names the website, where it said *Home*. A canonical address that a hook of the project set, such as that of a page that moved, stays.
- **The date of a page** is that of the newest file it is made of: the guide, which includes `README.md` with a line `--8<--`, changes with the README. The sitemap gives search engines the same date.
- **The badges** of a README stay on GitHub: the website would show them as the build downloaded them. Buttons such as those of My Home Assistant, `…/badges/hacs_repository.svg`, show no status and stay.
- **The switch between light and dark** names itself in German on the German pages.

### Accessibility

Every website meets WCAG 2.2 AA: the stylesheet of the blueprint, `.github/mkdocs-blueprint.css`, gives the theme the contrast that it asks for and underlines the links in the text, which a color alone doesn't set apart for every reader. The check *docs* proves it after each build: `.github/a11y/check.mjs` opens every page in Chrome, in the light and the dark theme, and runs [axe-core](https://github.com/dequelabs/axe-core) on it; each serious or critical violation shows in the summary of the check and as an annotation at its page, with a link that explains the fix. For one release it only reports, so that every repository can fix its pages first; then it fails the check. To run it on your machine after a build, with Google Chrome, or another Chrome or Chromium named in `CHROME`:

```sh
npm ci --prefix .github/a11y --ignore-scripts
node .github/a11y/check.mjs site
```

### The page of the automation

The page *Automation* of every website has no file in `docs/`: at every build, the hooks write it from `.github/workflows/` and the required checks of `.github/repository.toml` and `.github/repository.project.toml`, in English and, on a website in German, in German too. Each workflow shows with the comment at its top, which is why every workflow starts with one that says what it does, with what starts it, each schedule in words, the checks of it that `main` requires and the environments and secrets that it uses. A word of the name of its file, by `KEYWORDS` of `.github/mkdocs_blueprint.py`, puts it into a group: checks, releases, bots, security or maintenance. The page shows the pictures of two diagrams of the README, `how-a-repository-looks-after-itself` and `from-a-change-to-a-release`, in English and German: every repository gets them in `.github/mkdocs-blueprint-diagrams/`, which the template takes from `docs/images/diagrams/`, and the blueprint itself shows those of `docs/images/diagrams/`. A project's own `docs/automation.md` takes the place of the page, and `docs/automation.de.md` that of the German one.

### The reference

The pages of the reference, `docs/reference/questions.md` and `docs/reference/variables.md`, come from `reference.py`, which writes them from `copier.yml`, the workflows and `template/.github/repository.toml.jinja`, so that every question of Copier and every variable and secret is described and none drifts from its source. After a change of a question, of a variable or secret that a workflow reads, or of what the settings as code set, run `python3 reference.py` and commit the pages with it; `tests/test_reference.py` fails while a page differs from its sources. A new variable or secret needs its description, in the words of a user, in `ABOUT` of `reference.py`, and the test names each one that lacks it. The fix bot runs `python3 reference.py` when the tests fail, by the autofix of `.github/checks.project.toml`, and the Issue assistant sync writes the pages anew for each release of the assistant that it takes over.

The repositories that follow the blueprint are listed once, in [`.github/fleet.toml`](.github/fleet.toml): the name, the kind and the place in the Rollout of each, whether the Variants try every pull request on its answers (a canary), and its name, what it is and what it does, in English and in German. `reference.py` writes from it the showcase *Made with the blueprint* of both READMEs, the section *A real repository* of each page of `docs/kinds/`, the order of the Rollout in `.github/workflows/rollout.yml` and the legs of the canaries in `.github/workflows/variants.yml`, between the marks of each part; `tests/test_reference.py` fails while one of them differs. A new repository takes one entry there and `python3 reference.py`; a canary takes its answers in `tests/answers/<name>.yml` too, from its `.copier-answers.yml` without `_commit` and `_src_path`, which the Downstream workflow then keeps equal to those of the repository. The fix bot writes the READMEs and the pages anew, but a person commits the change of the two workflows.

### Pages in one column

Pages have one column, so that they read well in the GitHub app and on a phone, which keep columns side by side and squeeze them until the text is a few words wide and the pictures tiny. A table holds tabular data, never a layout: no `<table>` that sets a picture beside text, and no `<td width="…">`. A picture or a GIF comes at full width below the text that it illustrates, and a long list goes into `<details>` with a `<summary>` that names it. A cell of a Markdown table holds a value, a name or a short sentence: one of more than 30 words is a paragraph, which goes into a list, or onto a page of its own that the table links, as the README links the pages of `docs/features/`. `scripts/check.sh` fails on such a table and such a cell in a README, a CONTRIBUTING file or a page of `docs/`, with its file and line, and warns of a cell of more than 30 words, which fails nothing yet; `python3 blueprint.py pages --fix` puts the cells of a layout table one below the other, the text before its picture, and leaves out the widths. Each README stays below 3,000 words, which a test of the blueprint keeps.

## Diagrams

Diagrams are pictures of Mermaid sources, because the GitHub app and other renderers of Markdown show a `mermaid` block as code ([decision 0016](docs/decisions/0016-diagrams-as-pictures-of-their-sources.md)). A source is `docs/diagrams/<name>.mmd`, and `bash scripts/diagrams.sh` draws it, with Docker, as `docs/images/diagrams/<name>.svg` and `<name>.dark.svg`, which the Markdown shows with a `<picture>` and the website as well, the picture of the reader's theme, so that no page loads Mermaid for it ([decision 0058](docs/decisions/0058-every-website-shows-the-pictures-of-its-diagrams.md)); `bash scripts/diagrams.sh --extract` turns a `mermaid` block into a source and its picture. The check *diagrams* draws the pictures anew in a pull request that changes a diagram or adds a `mermaid` block, and on a branch of this repository the diagram bot commits the sources and pictures that it made; on `main`, the Diagrams workflow keeps one pull request from `bot/diagrams` that fixes what is left and merges itself. You need no Docker for a diagram: change its source, push, and let the bot draw it. Diagrams run from top to bottom (`flowchart TB`), so that they keep their size in the column of a page and on a phone, and have `accTitle` and `accDescr` for screen readers, which the `alt` of the picture repeats: `--extract` writes it from the source, and `scripts/check.sh` fails on an `alt` that the source doesn't say. Labels are text in the pictures: `<br>` breaks a line, and a label in `` "`…`" `` takes `**bold**` and `*italic*`. Their colors are tints that read in the light and the dark theme: blue (`#526cfe`) the blueprint and its bots, orange (`#f59e0b`) you and what is yours, green (`#16a34a`) what comes out. A diagram in a README comes in English and in German, the German one as `<name>.de.mmd`.

## Releases

The release bot keeps a pull request titled `chore: release x.y.z` with the next version, up to date with `main` and decided anew with every merge. Its section of the changelog is the text of the fragments in `changelog.d/` and of Unreleased, and it deletes the fragments; without such text, it lists the pull requests. Merging it creates the release with its package, SBOM and signed provenance. New repositories copy the blueprint from its release tags, and the blueprint bot brings every repository made from it up to the new release. A release of dependency updates merges and publishes itself, once a day, or at once when it fixes a vulnerability.

A line `Release-As: 2.0.0-beta.1` in the description of a pull request sets the version of the next release, for a prerelease for example. After the merge, the release bot writes the title and such a line, or one of `BREAKING CHANGE:`, into the end of the description as an override in an HTML comment, which release-please reads instead of the squash commit, whose parser could fail on another line of the description. A prerelease leaves the fragments and the text of Unreleased to the release that follows it.

By contributing, you agree that your contribution is licensed under the MIT-0 license of this project.
