# Changelog

All notable changes, by release. Each pull request that changes something for
users describes it under Unreleased. The release bot makes that text the section of
the next release, or lists the pull requests when there is none.

## Unreleased

### Changes

- **Every job runs on `ubuntu-24.04`, named with its version:** GitHub moves `ubuntu-latest` to Ubuntu 26.04 from 19 October 2026, one job at a time over a month, so that the runs of one workflow would have landed on either image at random, with Python 3.14 instead of 3.12, ShellCheck 0.11 and Docker 29, and failed like flaky tests. The workflows of the blueprint now name `ubuntu-24.04` and keep it until the checks of every kind of project pass on Ubuntu 26.04, which the blueprint tries every week; then one release moves every job. The workflows of the issue assistant follow with its next release. A workflow of your own, such as one of end-to-end tests, and the action test `.github/workflows/action-test.yml` of a GitHub Action, which the update leaves alone, keep `ubuntu-latest` until you change their `runs-on:` to `ubuntu-24.04` as well.

### Bug fixes

- **The blueprint bot keeps its pull request open, and your commits on it:** with every new release, the bot put its branch back on `main` before it committed the update, so GitHub closed the open update pull request and the bot opened a new one, as with Dennis-Otto/ha-autodarts#225 and Dennis-Otto/ha-autodarts#226; commits with which a maintainer had resolved conflicts on the branch were lost. The bot now moves its branch straight from the update before to the new one: the pull request stays open with its number and its auto-merge, and an auto-merge that you switched off stays off. Once someone else has committed to the branch, other than with a plain merge of `main` such as the button *Update branch* makes, the bot leaves it alone and says in one comment that a newer release is out; merge or close the pull request, and its next run brings the rest.
- **Conflicts no longer merge on their own:** an update with conflict markers now turns off the auto-merge that an earlier update without conflicts switched on, before it moves the pull request on, and adds the label `merge-conflict`, which the next update without conflicts takes off again. Only the files that the update touched count, so lines like markers that a project has on purpose no longer hold an update up.
- **The bot updates to the latest published release,** not to the newest tag, whose release may still be a draft or have failed; a repository made from a fork of the blueprint takes the fork's. `BLUEPRINT_AUTOMERGE` set to `off` now holds an open update pull request too, when a newer release moves it on.
- **An update that changes only `.copier-answers.yml` comes as a pull request too,** so that a repository no longer stays at the release before and the dashboard no longer counts it as behind.
- **New modes of files reach existing repositories:** the bot commits through the Git Data API, which carries the mode of every file, such as a script that becomes executable; GitHub still signs the commit. Where GitHub doesn't, the bot commits as before and lists the modes to set in the pull request.
- The bot's code moved from the workflow into `blueprint.py update-commit`, with tests, and runs from `main`, not from the update it brings. The update that brings this release still runs the bot before it, which may close an open update pull request one last time.
- **The preview of the website works on Windows, and `scripts/check.sh` builds the website:** the preview that CONTRIBUTING.md shows failed on Windows twice. pip refused all of `.github/docs-requirements.txt`, because the plugin for the dates needs the time zones of `tzdata` there, which the lock left out, and the strict build stopped at the preview cards for social media, which need the Cairo library. The lock now pins `tzdata` for every system, and only the CI draws the cards: GitHub's runners set `CI` to `true`, so the check *docs* still builds them. `bash scripts/check.sh` now builds the website strictly as well, with the tools of the preview in `.venv-docs` or those of an activated virtual environment, so that a link or an anchor that leads nowhere fails before the push, and a failure names the MkDocs that ran; without them it says so and leaves the website to the CI, which doesn't slow down. A MkDocs from elsewhere on the PATH, which lacks the theme and the plugins, doesn't count. The dev container sets these tools up. The first lines of your `mkdocs.yml`, which belongs to the project, still show the old preview; CONTRIBUTING.md has the new one.
- **The checks of the blueprint pass on Windows:** `bash scripts/check.sh` failed in Git Bash on Windows in four tests of the bot for cancelled checks, because Windows started their bare `bash` from System32, where it is the launcher of WSL, which ran the step in Linux without its variables. The tests now run Git Bash, in Git Bash as well as from PowerShell or the test runner of an IDE, and the new Windows workflow runs the checks on Windows every week and for each pull request that changes the code, the template or the tests. The repositories made from the blueprint don't change.
- **The weekly mutation tests measure again:** they had not reported a score since they came. For Python, the Mutation workflow gave mutmut the code to change as one line with commas, which mutmut 3 takes for a single path that doesn't exist, so it changed nothing and the run failed; it now gets one path on each line. For a Nextcloud app, Infection needs PHP 8.3 and got 8.2, and the run still ended green, because its error was lost in the pipe to `tail`; it now runs on PHP 8.3 with the bootstrap of the tests, which loads the classes of Nextcloud, and an error of Infection fails the run. A low score still fails nothing, not even below a minimum in the project's own configuration of Infection, but a run that measures nothing now fails, with the end of the output of the tool in its summary. A pull request that changes how the mutants run tries them and shows a defect as a red check; the check isn't required, so a pull request that merges itself doesn't wait for it. The dashboard shows the share of the mutants caught again, for both tools that of the code that the tests run. It also no longer takes the coverage, the mutation score or the time of the CI from a pull request whose branch in a fork is called main. A test that can't run in the copy of the repository in which mutmut tests the mutants, because it reads the code as text or asks Git, gets the marker `@pytest.mark.mutation_unsafe` and stays out of the mutation tests. New projects register the marker; an existing Python project that needs it adds the line of the blueprint's `pyproject.toml` to `markers` under `[tool.pytest.ini_options]` in its own.
- **Every release gets its signed tag, even when the run of its merge is lost:** the release workflow signed the tag of a release only in the run that the merge of the release pull request started. When that run was cancelled or failed before it got there, the next run could create the release on a tag without a signature, which the immutable release then kept for good. Every run of the Release workflow, the hourly one and one started by hand too, now signs the tag of a merged release pull request before the release is created on it, and creates a release only on a tag that it signed: a release pull request merged in the seconds after a run looked, or in a repository without the release app, waits for the next run instead of getting a tag without a signature. Signing and pushing the tag, and every question to GitHub on the way, try three times each, because GitHub fails for a moment now and then, as with the `fatal error in commit_refs` that held up 0.10.0 until someone ran it again; a tag that GitHub took although the push failed counts as pushed.
- **A release is built only on its own signed tag:** a token that may push could create the tag of the coming version first, at a commit of its own, and the release was then built, signed and published from it. A tag that exists already must now be the one that the release workflow signed, at the commit of the release; any other stops the release before release-please creates it, and the isolated build checks the tag again before it builds or signs anything.
- **The release check is strict with every new release:** called by an hourly run of the Release workflow, it took the event of that run for its own weekly run: it only noted a tag without a signature, and it skipped a release without the bundle of its provenance altogether. It now checks every new release in full; only its own weekly run of the latest release accepts what older releases lack.
- **Findings no longer fails when hassfest or HACS move on:** the CI of a Home Assistant integration pinned the actions of hassfest and HACS to a commit of their branches, and zizmor reports such a pin as soon as the branch moves on, as `home-assistant/actions` did twice on 2026-10-12. From then on, the Findings workflow failed every run, and Renovate, which waits a week after each commit, couldn't catch up. The CI now runs their images with `docker run`, as the actions did, without a pin that falls behind; hassfest still shows its errors as annotations. Renovate follows an action that a project pins to a branch in its next run and merges the update once every check passes.
- **Every release reaches every repository, one after the other, and the Rollout names each repository that it misses:** the Rollout started the blueprint bots in one loop, which ended at the first repository whose bot GitHub didn't start, so the repositories after it got nothing; an error of GitHub in the look for a repository's bot, such as an exhausted rate limit, left that repository out without a word. Each repository now has a job of its own: only GitHub's answer that a repository has no blueprint bot leaves it out, the look and the start are tried three times, and a repository whose bot can't be started, or fails, fails the run by its name while the others still get the release. The repositories go one at a time, the quickest checks first and ha-autodarts last, each with up to 15 minutes for its bot and the checks of its update pull request, so that the update pull requests no longer all wait for the 20 runners of the account at once, and other pull requests keep runners free. A release that the hourly run of the Release workflow or a run started by hand finished now rolls out as well, and the merges of other pull requests no longer start a runner of the Rollout. The repositories made from the blueprint don't change.
- **A passing error of a download no longer fails the checks or a release:** the checks of a Nextcloud app failed on `main` because GitHub's download of krankerl answered with a 504 for a moment, which the flaky-test bot then reported as a flaky test (Dennis-Otto/paperless-unified-search#94); the same error in the build of a release leaves it a draft to finish by hand. Every download of the workflows now tries again after an error of the network or of the server, with pauses that grow, and a connection that hangs fails and tries again instead of holding the job until its time limit: krankerl, the certificate of the app and the server of Nextcloud for signing it, Infection, gitsign, and what the release check reads from PyPI and the App Store. Each one writes into a file, which curl empties before it tries again. The checks of a Nextcloud app take krankerl from the cache of the CI after their first run, checked against its checksum as before, so that most runs don't download it at all; a release still downloads it. A test holds every download of the workflows and scripts to this.
- **The CI checks `appinfo/info.xml` in any case:** when the schema of the App Store was out of reach, `scripts/check.sh` passed with "the CI checks it", in the CI as well, so a broken `info.xml` could merge while apps.nextcloud.com was down. The download of the schema now tries again, and in the CI a schema that stays out of reach fails the check and says to run it again later; locally, the check still passes without it.
- **The Upstream bot of a Nextcloud app can be tried:** it runs only when Nextcloud has a new major version, so its first real run would come unobserved. Started by hand with *dry run*, it now shows the change and the pull request that it would make, and writes nothing to GitHub.
- **Renovate keeps every lock file current again:** it skipped the test tools of the Home Assistant integrations (`requirements-test.txt`) since 0.8.8 and the lock file of mutmut since it came, with no more than a warning in its log, because it couldn't read the command in their headers: `--python-version 3.14.8` lacked the `=` before its value, and `--unsafe-package` is an option of `pip-compile` that Renovate doesn't know. Neither file got an update, not even one that fixes a vulnerability. Both are compiled again with `uv pip compile` and an `=` before every value; mutmut's leaves out the pytest of the project with `--no-emit-package=` and now holds for every Python from 3.12 on. A Home Assistant integration made before this release has the old header in its own `requirements-test.txt`: compile it once with `uv pip compile --generate-hashes --python-version=3.14.8 --output-file=requirements-test.txt requirements-test.in`. A test now reads the header of every lock file as Renovate does, and in the blueprint, Renovate itself reads every file of a pull request that changes its rules or a lock file.
- **The weekly refresh of the lock files waits for you:** it moves every indirect dependency to its newest version, also one released minutes ago, and so skipped the week that Renovate waits after a release, as when pydantic 2.14.1 reached every repository 17 hours after its upload. The refresh now waits for the maintainer instead of merging on its own, and it covers every package manager, also `composer.lock` and `package-lock.json`, which moved only with their direct dependencies before. Renovate builds it anew only in its weekly window, so the changes you reviewed are the ones that merge. Decision 0012 says why a cooldown of the package managers isn't possible for the refresh alone.

### Performance

- **Pull requests wait less for a runner:** a check now runs only where it can change a result, since an account runs about 20 jobs at once. The scanners run in the pull requests that change what they read: zizmor for a workflow, an action or the settings of Dependabot, OSV-Scanner for a lock file, the fuzzing for Python code, and the link check for a document, but not for the changelog alone. The SBOM comes every week and with every release, no longer with every pull request. The release pull request, which changes only the changelog and the version, runs no scanner. After a merge, `main` runs only what keeps a baseline or publishes: Lint, the secret scan, the SBOM and the fuzzing no longer run there, and the secret scan runs every week over the whole history instead. The checks with the newest Python move into a workflow of their own, Newest Python, which runs after every change of `main` and every week instead of in every pull request, so that a new Python no longer turns the CI of `main` red; a failure there keeps an issue open until the checks pass again. In the blueprint itself, a merge now starts 11 to 14 jobs instead of 36, the release pull request 17 instead of 37, and one required check, `variants`, stands for the 14 variants and updates, which the release pull request skips.

## [0.10.1](https://github.com/Dennis-Otto/repo-blueprint/compare/v0.10.0...v0.10.1) (2026-10-12)

### Bug fixes

- **A cancelled check no longer blocks a pull request:** a newer run of a workflow cancels the one still running for the same pull request, but GitHub doesn't always create the runs in the order of the commits. A late run for an older commit could cancel the run for the latest commit, whose required checks then stayed cancelled until someone ran them again by hand, as with the release pull requests of 0.8.8 and 0.10.0. The bots after the checks now start such a run again: when the concurrency of its workflow cancelled it, it is for the latest commit of an open pull request and no newer run of its workflow for that commit exists. A run that a person cancelled stays cancelled. For this they watch the workflows of every required check, CodeQL, Dependency review, Docs, Lint, Pull request title and Secret scan as well as the tests; the flaky-test bot still looks at the tests only.

## [0.10.0](https://github.com/Dennis-Otto/repo-blueprint/compare/v0.9.1...v0.10.0) (2026-10-12)

### Features

- **Renovate's updates merge without waiting for its next run:** `main` only takes pull requests that are up to date with it, and Renovate brought its own up to date only when it ran, every two hours and often later. An update whose checks had passed waited behind every other merge. The branch bot now brings Renovate's pull requests up to date as well, as the release app that Renovate commits as, so that Renovate still takes the branch for its own; one that conflicts with `main` Renovate builds anew itself, without a label or a comment of the bot.

## [0.9.1](https://github.com/Dennis-Otto/repo-blueprint/compare/v0.9.0...v0.9.1) (2026-10-12)

### Bug fixes

* **deps:** refresh pip-compile outputs ([#124](https://github.com/Dennis-Otto/repo-blueprint/issues/124)) ([6b4dd2d](https://github.com/Dennis-Otto/repo-blueprint/commit/6b4dd2d15d59b9de490d006eebd2fc6bcfaaff97))

## [0.9.0](https://github.com/Dennis-Otto/repo-blueprint/compare/v0.8.8...v0.9.0) (2026-10-12)

### Features

- **Every release of the blueprint goes out at once:** the new Rollout workflow starts the blueprint bot in every repository of the release app as soon as the Release workflow has published and verified a release, so that the update pull requests come within minutes instead of with the bot's weekly run. The release app needs the permission *Actions* to read and write for it: change it in the settings of the app, then accept the new permissions on its installation.

## [0.8.8](https://github.com/Dennis-Otto/repo-blueprint/compare/v0.8.7...v0.8.8) (2026-10-12)

### Bug fixes

- **Renovate compiles every lock file for its own Python:** Renovate installs pip-tools once per repository and run, for the Python of the first lock file it compiles, so it compiled a lock file for another Python with the wrong one. The lock file of the Home Assistant stack, for Python 3.14, came out for Python 3.12 with Home Assistant 2025.1. It is now compiled with `uv pip compile --python-version 3.14.8`, which doesn't depend on the Python it runs on, and its `requirements-test.in` pins the test plugin, so that a Home Assistant that needs a newer Python fails its update instead of an older Home Assistant being chosen. A project with lock files for two Pythons compiles the one for the other Python with `uv pip compile --python-version` as well.
- **Ruff and its pre-commit hook move together:** Renovate now keeps the hooks of `.pre-commit-config.yaml` current as well, in the group of the Python tools, where Ruff and its hook also move to a new major version together.
- **The test plugin of Home Assistant moves on its own:** it pins a new Home Assistant, now and then a beta, and when its lock file didn't resolve, it held up the other Python tools of the integration.
- **The weekly refresh of the lock files merges itself:** it has no release date, so its age check stayed pending for good and it waited for the maintainer. It now merges once every check passes, like a routine update.
- **The Nextcloud apps get only the releases that run on their PHP:** Renovate offered phpunit 13 and nextcloud/ocp 35, which need PHP 8.4 and 8.3, to apps that run on PHP 8.2, and Composer couldn't update their lock file. Renovate now leaves out the releases that don't run on the platform PHP of `composer.json`. A project on a newer PHP sets `constraints: { php: "8.3.*" }` for Composer in its `.github/renovate.json5`.
- **Renovate updates mutmut again:** the lock file of the mutation tests recorded `--no-index`, which pip-tools 7.6.1 added by mistake with click 8.5, and Renovate skipped a file with it.
- **The dependency review accepts regex,** which Home Assistant's test base brings in and whose license reads `Apache-2.0 AND CNRI-Python` since 2026.9.29. An existing Home Assistant integration adds `pkg:pypi/regex` to `allow-dependencies-licenses` in its `.github/dependency-review.yml`, which updates leave alone.

## [0.8.7](https://github.com/Dennis-Otto/repo-blueprint/compare/v0.8.6...v0.8.7) (2026-10-12)

### Bug fixes

* **deps:** update davidanson/markdownlint-cli2 docker tag to v0.23.3 ([#120](https://github.com/Dennis-Otto/repo-blueprint/issues/120)) ([84d2d85](https://github.com/Dennis-Otto/repo-blueprint/commit/84d2d85e68b7395dccdf8fa34bc1972c537ad5c7))

## [0.8.6](https://github.com/Dennis-Otto/repo-blueprint/compare/v0.8.5...v0.8.6) (2026-10-11)

### Bug fixes

- **The blueprint bot no longer fails now and then:** since version 2.47, Git starts its maintenance in the background after a commit, and `copier update` deletes the repositories it commits to right away, so an update failed at times with `Directory not empty: '/tmp/copier._main.new_copy…/.git'`. The bot now runs Copier with `maintenance.auto` off.

## [0.8.5](https://github.com/Dennis-Otto/repo-blueprint/compare/v0.8.4...v0.8.5) (2026-10-10)

### Bug fixes

- **The link check passes while GitHub refuses the page of a file:** github.com answers the page of a file, such as `https://github.com/<owner>/<repo>/blob/main/LICENSE`, with 503 Service Unavailable at times while its other pages work, and the Links workflow failed for every such link. It now asks `raw.githubusercontent.com` for the same file, which answers 404 for a missing one as well.

## [0.8.4](https://github.com/Dennis-Otto/repo-blueprint/compare/v0.8.3...v0.8.4) (2026-10-10)

### Bug fixes

- **The website builds when a download is slow:** while the website is built, the privacy plugin of Material downloads the fonts and scripts that the pages use, such as those of Google Fonts, and the social plugin the fonts of the preview cards. They tried every file once, so a single font that didn't come within 5 seconds failed the strict build of the Docs workflow. The hook of the blueprint now has them try a download up to three times, after a second and then two, when the network or the server fails.

## [0.8.3](https://github.com/Dennis-Otto/repo-blueprint/compare/v0.8.2...v0.8.3) (2026-10-08)

### Bug fixes

- **No labels and no merge step for the updates that Dependabot no longer makes:** Renovate keeps the actions, the dependencies and the images current, so Dependabot updates only the Features of the dev container and sets just the label `dependencies`, and Renovate sets none. New projects no longer get the labels `github_actions`, `python`, `php`, `javascript` and `docker`, and the workflow *Dependabot maintenance* loses its step for updates of the HACS and hassfest actions to a new commit, which Renovate brings and merges itself. An existing project removes the group *Dependabot* from its `.github/labels.toml`, which updates leave alone. The Labels workflow never deletes a label, so the project deletes them on GitHub as well, each with `gh label delete github_actions --yes`, and with them those that Dependabot created itself, such as `devcontainers_package_manager`.
- **The social preview names Renovate** instead of Dependabot. An existing project changes it in its `.github/social-preview.html`, renders it again with `bash scripts/social-preview.sh` and uploads it.
- **The language switch finds its sitemap on every page:** on a page in a folder, such as a decision record in `docs/decisions/`, the switch of Material asked for the sitemap in the folder of the page in each language, such as `decisions/sitemap.xml` and `de/decisions/sitemap.xml`, and the browser logged two errors. The hook of the blueprint now copies the sitemap into every folder that holds a page. The switch already led to the same page in the other language.
- **The 404 page stays in the default language:** on a website in more than one language, the build of each further language wrote `404.html` at the root again, so a missing page showed the header of the German website, and its language switch led to the page built last, such as a decision record. The hook of the blueprint now keeps the 404 page of the default language, whose switch leads to the start page of each language.

## [0.8.2](https://github.com/Dennis-Otto/repo-blueprint/compare/v0.8.1...v0.8.2) (2026-10-08)

### Changes

- **The code of `.github/blueprint.py` is in modules:** the tool keeps its commands, and its code is now in `.github/blueprint/`, one module for each task. The folder brings its own Ruff settings, so that those of a project don't apply to it.

### Bug fixes

- **The coverage comment names every file by its path from the root of the repository,** such as `lib/AppInfo/Application.php` instead of `AppInfo/Application.php`, where the report has one source folder, as the report of PHPUnit and of a project that measures one folder with coverage.py have. A project that measures several folders names its packages under `source_pkgs` instead of `source` in `[tool.coverage.run]`, as the blueprint does now, since such a report doesn't say which folder holds a file.
- `blueprint.py settings check` and `settings apply` name the settings as `.github/repository.toml` on Windows too, as the documentation does, instead of `.github\repository.toml`.
- **One run after the checks, not two:** the coverage bot and the flaky-test bot share the new workflow *After the checks*, `after-checks.yml`, which replaces `coverage.yml` and `flaky.yml`. A run of the checks starts one run after it instead of two that mostly had nothing to do, the coverage bot no longer starts for checks that were skipped or cancelled, and the workflow watches only the checks of the repository. A project that added a workflow of its own to the list of `flaky.yml` adds it to `after-checks.yml`.

## [0.8.1](https://github.com/Dennis-Otto/repo-blueprint/compare/v0.8.0...v0.8.1) (2026-10-08)

### Bug fixes

- **The language switch finds its sitemap:** on a website in more than one language, the switch of Material asked for a sitemap next to the pages of each further language, such as `de/sitemap.xml`, and got nothing. A hook of the blueprint now copies the sitemap there. A project with hooks of its own adds `.github/mkdocs_blueprint.py` to its `hooks` in `mkdocs.yml`.

## [0.8.0](https://github.com/Dennis-Otto/repo-blueprint/compare/v0.7.0...v0.8.0) (2026-10-08)

### Bug fixes

- **Websites in more than one language build:** the dates of the pages no longer stop the build of a website that turns on its German pages, and the language switch leads to the same page in the other language. A website turns them on with `enabled: true` under `i18n` in `mkdocs.yml`; pages load with a full reload now.
- **One heading for each kind of change:** when two pull requests each start a heading such as *Features* under *Unreleased*, the release puts their entries under one heading, in the changelog and in the notes.

### Features

- **The issue forms point to the documentation:** with a `homepage`, the first link of the forms leads to it, so that a question finds its answer before it becomes an issue. The blueprint's own homepage is its website now.
- **The website of the owner itself:** a repository named like `dennis-otto.github.io` may use the blueprint, and its documentation website lives at the root of the owner's address, such as `https://dennis-otto.github.io/`.

## [0.7.0](https://github.com/Dennis-Otto/repo-blueprint/compare/v0.6.2...v0.7.0) (2026-10-08)

### Bug fixes

- GitHub no longer asks the maintainer to review every pull request of a bot: the blueprint brings no `.github/CODEOWNERS`, which named the owner of every file and so requested their review on every pull request of someone else, although no rule asks for one. A repository whose update keeps the file can delete it.

### Features

- **The settings that every website shares come from the blueprint.** `.github/mkdocs-blueprint.yml` holds the theme, the plugins and the Markdown of the documentation website, and the `mkdocs.yml` of a project inherits it (`INHERIT`), so that the updates of the blueprint bring the website new features. It adds tabs for the sections of the menu and the path above a page, fonts and pictures served with the website instead of from other servers (privacy plugin), a preview card of every page for where a link to it is shared (social plugin), pictures that open enlarged (glightbox), the date of the last change of a page, tabs on a page, tooltips, and the plugin for a website in more than one language with a switch in the header (mkdocs-static-i18n). An existing project puts `INHERIT: .github/mkdocs-blueprint.yml` at the top of its `mkdocs.yml` and removes what the file now holds; its dependency review allows the license MIT-CMU of Pillow.
- **A designated successor:** the new answer `successor` says that the owner has designated a successor through GitHub's account successor setting. GOVERNANCE.md then says how the successor can carry the project on, with a bus factor of 2, and what doesn't pass with the repository, such as an app in the Nextcloud App Store. An existing repository turns it on with `copier update --data successor=true`.

## [0.6.2](https://github.com/Dennis-Otto/repo-blueprint/compare/v0.6.1...v0.6.2) (2026-10-08)

### Bug fixes

- The isolated build of a release gets the secrets of the environment *release* again, so a Nextcloud app is signed: since 0.6.0 its release stopped at the build for want of the signing key.
- A release that a failed run left as a draft, with its signed tag, is built and published by starting the Release workflow by hand.

## [0.6.1](https://github.com/Dennis-Otto/repo-blueprint/compare/v0.6.0...v0.6.1) (2026-10-08)

### Bug fixes

- The settings bot applies every part of the settings even when GitHub refuses one, and names the permission of the release app that a refusal points to. Before, a missing permission for the repository variables kept GitHub Pages and the labels from being set.

## [0.6.0](https://github.com/Dennis-Otto/repo-blueprint/compare/v0.5.0...v0.6.0) (2026-10-08)

### Bug fixes

- The package of a Nextcloud app leaves out the files of the Markdown lint, `.markdownlint-cli2.jsonc` and `.markdownlint.jsonc`, which its package check rejected, and the style rules `.vale.ini`. A test checks every file of the repository against the package now.
- Renovate updates an image of a script also where a variable holds it in quotes, such as `IMAGE="name:tag@sha256:…"`; it found only an image after a space before.

### Features

- **SLSA Build Level 3:** a release is built in a reusable workflow of its own, `build-release.yml`, isolated from the rest of the release workflow, and the signed provenance of every asset names it as the build. The release check verifies that; releases from before are accepted by its weekly run only.
- **Every repository gets a documentation website:** MkDocs with the Material theme makes the pages of `docs/` a website with search and a light and a dark theme, German pages under `docs/de/` included, and the new Docs workflow publishes it on GitHub Pages with every change of `main`. Every pull request builds it strictly, as the new required check `docs`, so that a link or an anchor that leads nowhere fails; a repository without a website passes it. The settings bot turns GitHub Pages on from the new table `[pages]` of the settings as code. `mkdocs.yml` belongs to the project, and a page can include a file of the repository, such as the README, with `--8<--`, so that nothing is written twice.
- **The weekly report:** every Monday, the blueprint posts in its discussions what the public repositories of the owner released, merged and fixed in the week, from public data alone (`weekly.py`, Weekly report workflow).
- **The blueprint's own website** is its documentation now, and [the dashboard](https://dennis-otto.github.io/repo-blueprint/dashboard/) moved to `dashboard/` of it.
- **The dashboard shows the health of every repository:** the line coverage and the share of mutants that the tests catch, from the reports of the last runs on `main`, the stable releases and the median time to the first answer to a new issue over 90 days, and the median time of the CI, each with an arrow when it moved since a week ago. The history of one entry a day lives in the published dashboard itself, in `history.json`.
- **Signed release tags:** the tag of every release and beta is an annotated tag, signed without a key by the release workflow with gitsign: Sigstore certifies the identity of the workflow, and the release check verifies it. There is no key to keep secret.
- **Mutation tests every week:** mutmut for Python and Infection for the PHP of a Nextcloud app change the code in thousands of small ways and run the tests against each change. The summary shows the share of mutants that a test notices and the first that survive; a low score fails nothing.
- **The clean-up bot** deletes every week the branches that `main` holds completely and that no open pull request uses, and the caches of closed pull requests. A branch with commits that `main` doesn't have stays and is listed in its summary after a month without a pull request.
- **A Nextcloud app runs the taint analysis of Psalm** in `scripts/check.sh`: input from a request or a user that reaches HTML, SQL, a shell, a file or a header without escaping fails the check, as CodeQL does for the other languages, which has no PHP.
- **Every repository documents what the Silver level of the OpenSSF Best Practices badge asks for.** SECURITY.md says how to verify a release with the GitHub CLI and gives the assurance case of the repository and its releases: the threat model, the trust boundaries, the secure design principles and how the OWASP Top 10 CI/CD security risks are countered. A new repository starts with `docs/security.md`, the security design of its software, which belongs to the project from then on. GOVERNANCE.md names the roles and their responsibilities and says honestly how the project continues with one maintainer, and CONTRIBUTING.md the coding standards of each kind of project and the rule that new functionality and every fix come with tests.
- **Hints at the prose** of the documents that a pull request changes: the spelling in English and German (cspell, with the words of the project in `.github/cspell-words.txt`) and the style of the English (Vale, with write-good and proselint), as warnings next to the lines, never as a failure. The dependency review allows the two dictionaries of cspell whose licenses it would reject, since only the checks use them; an existing repository adds them to its own `.github/dependency-review.yml`, which the update doesn't change.

## [0.5.0](https://github.com/Dennis-Otto/repo-blueprint/compare/v0.4.0...v0.5.0) (2026-10-07)

### Features

- **The coverage bot** keeps one comment on every pull request: the coverage of its tests against that of `main`, and every file whose coverage changes, from the reports that the checks keep. It never runs the code of a pull request. A Nextcloud app keeps its report now too.
- **Every repository records the decisions that shape it** in `docs/decisions/`, from a template, with an index and a first record; they belong to the project. The blueprint records its own there, such as Copier with an update bot, the curated changelog, the settings as code, Renovate and the beta channel.
- **The settings bot keeps the community profile at 100 %:** when GitHub's community standards miss a file of a repository, its run fails and names what to add, with the link to the profile.
- **Every release carries its SBOM as CycloneDX too,** the format that many tools of companies read, beside SPDX, and **an OpenVEX document** that states every advisory that `osv-scanner.toml` accepts, with its reason, as one that doesn't affect the release, so that the scanners of the users stop reporting it. The release check verifies both.
- **The flaky-test bot:** when the tests or end-to-end tests fail for the first time, their failed jobs run once more. A job that passes then is flaky; the bot lists it in one issue, *Flaky tests*, so that its test gets fixed, and the pull request is no longer blocked by chance. A job that fails again stays red.
- **A Nextcloud app covers every line of `lib/` with its tests:** `scripts/check.sh` measures the coverage with pcov in the CI and Xdebug in the dev container, and fails below 100 %, as the other kinds of projects do.
- **Renovate keeps every repository current, instead of Dependabot.** The blueprint runs it every two hours for each repository with a `.github/renovate.json5`, as the release app, with a token that can't change any setting. It updates what Dependabot did and also the images that the workflows and scripts start by digest, the end-to-end tests and the Renovate of the bot itself. An update waits a week after its release, one that fixes a vulnerability comes at once; routine updates merge on their own once every check passes, major ones wait, and the release bot ships them as before: `fix(deps)` for what the users run, `chore(deps)` for the tools. The rules of the blueprint are in `.github/renovate-blueprint.json5`; `.github/renovate.json5` extends them and belongs to the project, whose own rules come last. Dependabot keeps only the Features of the dev container, whose lock file Renovate can't update; Renovate also takes over the security updates.
- **A beta channel:** where the repository variable `BETA_CHANNEL` is true, every `feat`, `fix` or `perf` that reaches `main` becomes a beta of the next release, such as `1.3.0-beta.2`, with the text of Unreleased as its notes. It is built, signed and verified like a release and published as a prerelease, which HACS, npm and PyPI offer only to those who ask for betas, and it announces nothing.
- **The Markdown of every document is linted** by markdownlint, as the new required check `markdown` of the Lint workflow. The rules of the blueprint are in `.github/markdownlint.jsonc`; a project changes them in its own `.markdownlint.jsonc`.
- **Every release is announced in the discussions,** in their category Announcements, with its notes; prereleases are not. New repositories have discussions, with forms for questions and ideas that belong to the project; an existing repository turns them on with `copier update --data discussions=true`.

### Bug fixes

- The release check of a Nextcloud app looks for the release on the page of the app in the App Store, which links its signed package at once; the list of all apps, which it read before, shows a new release only hours later, so the check failed after every release.

## [0.4.0](https://github.com/Dennis-Otto/repo-blueprint/compare/v0.3.2...v0.4.0) (2026-10-07)

### Features

- **The settings bot applies the settings as code itself,** after every change of `repository.toml`, `repository.project.toml` or `labels.toml` on `main` and every week, as the release app, which may now write the administration of the repositories. So a new required check of a blueprint update is in place without anyone running `settings apply`; only a missing secret still waits for the maintainer, with the command that sets it.
- **OSV-Scanner** checks every lock file against the OSV database of known vulnerabilities: on every pull request the ones it brings in, on `main` and every week all of them. Its findings go to code scanning, where the Findings workflow keeps them fixed or accepted.
- **Area labels:** a bot labels every pull request with the areas whose files it changes, by the paths in `.github/labeler.yml`, which each repository fills with its own areas.
- **The changelog check** asks every `feat`, `fix` or `perf` pull request for its entry under Unreleased, so that the notes of a release are always written; bots and dependency updates are exempt. It is a new required check, `changelog`.
- **Every release carries the licenses of its third-party components** as `THIRD_PARTY_NOTICES.md`, from the dependency graph of GitHub, grouped by license.

### Bug fixes

- The release pull request shows its introduction as text above a line, not as a large heading: Markdown read the line under it as the underline of a heading.
- The pin of `shivammathur/setup-php` names its tag as it is, `2.37.2`, so that zizmor no longer reports the comment as a mismatch and the Findings workflow passes.

## [0.3.2](https://github.com/Dennis-Otto/repo-blueprint/compare/v0.3.1...v0.3.2) (2026-10-07)

### Bug fixes

- The tools of the blueprint bot pass the dependency review of every project: Copier's Jinja filters (GPL-3.0-only) and typing-extensions, whose license the review reads wrongly, are no part of any release.
- `blueprint.py` writes UTF-8, so that its checklist shows its marks in a console of Windows too.

## [0.3.1](https://github.com/Dennis-Otto/repo-blueprint/compare/v0.3.0...v0.3.1) (2026-10-07)

### Bug fixes

- **The release bot no longer loses a release:** its step that has the release pull request rebuilt on `main` could replace the description of a pull request that had just been merged, and without its notes release-please made no release of it. The step now checks that the pull request is still open and only adds a marker at the end of the description.
- **An existing repository keeps out the samples of the template:** `copier update` brought back the sample code and tests that an adopted repository had deleted. The new question `sample_code`, which an existing repository answers with no, leaves them out.
- The link check leaves out the badges of workflows, which GitHub serves only once a workflow is on `main`.

## [0.3.0](https://github.com/Dennis-Otto/repo-blueprint/compare/v0.2.0...v0.3.0) (2026-10-07)

### Features

- **The release bot writes the changelog that the pull requests write.** What they describe under `## Unreleased` of `CHANGELOG.md` becomes the section of the next release, and its notes show that text followed by every pull request. Without a text, the section lists the pull requests as before. The version still follows from their titles (`fix` a patch, `feat` a minor, `!` a major version), decided anew with every merge, and the release pull request says so.
- **The release pull request stays up to date with `main`**, also after merges that change none of its notes, such as `docs:` or `chore:` pull requests.
- **The upstream bot** of a Nextcloud app raises `max-version` in `appinfo/info.xml` when Nextcloud has a new major version, with an entry under Unreleased, in a pull request that merges itself once every check passes against it. `blueprint.py unreleased` lets every bot write such an entry.
- **The registration of a Nextcloud app** in the App Store is a workflow of every app (`register-app.yml`): it checks the key of the environment against the certificate of the app id and registers it, confirmed with the app id.
- **The release verification bot** checks every release after its delivery and the latest one every week, as its users can: the signed provenance of every asset in GitHub and in the attached bundle, the SBOM, an immutable release with a signed commit, and the same release on PyPI, npm, GHCR, the Nextcloud App Store or the major tag of an action.
- **Prereleases:** a version such as `2.0.0-beta.1`, set with a line `Release-As: 2.0.0-beta.1` in a pull request, becomes a prerelease. It keeps the text of Unreleased for the release that follows, leaves the major tag of an action where it is, and goes to the tag `next` on npm.
- **The dashboard** of every public repository of the owner on GitHub Pages: the release of the blueprint it is on, its releases, its open pull requests and conflicts, the last runs of its main workflows and its Scorecard, every six hours.
- **Harden-Runner** records the network traffic of every job of the workflows, so that a connection that doesn't belong there shows; SECURITY.md says so.
- **The issue forms belong to the project** after the first copy, like its labels, because their areas and fields are its own. They start richer: an introduction with what happens with an issue and where vulnerabilities go, steps to reproduce, an area for feature requests too, and a checklist.
- Releases attach their signed provenance also as in-toto JSON lines (`provenance.intoto.jsonl`), the format of SLSA that OpenSSF Scorecard and other tools look for.
- **A dev container** for VS Code and GitHub Codespaces in every project: the image of its kind by digest, which Dependabot keeps current, the tools of the checks and the pre-push hook set up once it is created.
- Every project gets the `docker` label, for the Dependabot updates of the image of its social preview.
- **Nextcloud apps** check more on every change: `composer validate` and `composer audit`, `appinfo/info.xml` against the schema of the App Store, the PHP of `templates/`, and the package that krankerl builds, with the project's `scripts/check-package.sh`, which the release runs before and after signing as well. Lines of `info.xml` marked `x-release-please-version`, such as screenshot URLs at a tag, follow each release.
- The dev container has Docker for every project, for the end-to-end tests and the social preview, and Node for a Home Assistant integration or a Nextcloud app with a frontend; its Features are locked and kept current by Dependabot. The CI of a Home Assistant integration with a `package.json` sets up Node for the tests of its frontend.
- The README describes how an existing repository takes the blueprint.
- Every `.gitignore` leaves out the local settings of Claude Code, and `.gitattributes` marks the lock files as generated, so that GitHub folds them in diffs.

### Bug fixes

- **Updates reach every file of the blueprint again:** the patterns of the files that belong to a project matched at any depth, so that `.github/blueprint.py`, the Dockerfile of the dev container and that of the social preview never changed with an update.
- A release follows only from changes for users: pull requests of the type `docs` no longer make one on their own; what they wrote under Unreleased comes with the next release.
- A Nextcloud app keeps its icons in `img/`, and its package leaves out the dev container, the hooks, the link check, `screenshots/` and `LICENSES/`, whose text `LICENSE` carries. psalm's JSON mapper (OSL-3.0) passes the dependency review as a tool of the checks. Dependabot leaves the major version of `nextcloud/ocp`, which follows the min-version of the app, to the maintainer and groups the major updates of composer.
- Every `.gitignore` keeps secrets out: `.env`, keys, certificates and credential files.
- The weekly release verification waits for the next release when the latest one is older than the release workflow of the blueprint.
- The first release no longer drops the introduction of the changelog.
- The settings bot no longer fails on the bypass list of the rulesets: the token of the release app gets the rulesets without it.
- `LICENSE` ends with one line break, also for the SPDX texts that end with a blank line, such as MIT.

## [0.2.0](https://github.com/Dennis-Otto/repo-blueprint/compare/v0.1.0...v0.2.0) (2026-10-07)


### Features

* leave the action test to the project, check the newest Python and sign every commit ([#13](https://github.com/Dennis-Otto/repo-blueprint/issues/13)) ([a0118dd](https://github.com/Dennis-Otto/repo-blueprint/commit/a0118dd4330673cae950e7a2f244f94b1394e7f5))

## 0.1.0 (2026-10-07)


### Features

* catch the merges of workflows, report conflicts, welcome and guard pushes ([#9](https://github.com/Dennis-Otto/repo-blueprint/issues/9)) ([e5b8b03](https://github.com/Dennis-Otto/repo-blueprint/commit/e5b8b0356724058af231ede805eeb8fde3466c6a))
* check workflow security, links, licenses and settings ([#10](https://github.com/Dennis-Otto/repo-blueprint/issues/10)) ([2066a37](https://github.com/Dennis-Otto/repo-blueprint/commit/2066a374ea8a671a681632464b7a6e56b86663e8))
* fuzz the Python projects with Atheris and the Node packages with fast-check ([#3](https://github.com/Dennis-Otto/repo-blueprint/issues/3)) ([81c1359](https://github.com/Dennis-Otto/repo-blueprint/commit/81c1359be5591d9289902d892c5b8e30e6184f57))
* keep pull requests that wait for auto-merge up to date ([#6](https://github.com/Dennis-Otto/repo-blueprint/issues/6)) ([a7ad6a3](https://github.com/Dennis-Otto/repo-blueprint/commit/a7ad6a34f6941ab6543804216bce2bfe692ee0f1))
* let a project add its own settings and copyright holders ([#12](https://github.com/Dennis-Otto/repo-blueprint/issues/12)) ([b05400d](https://github.com/Dennis-Otto/repo-blueprint/commit/b05400d0886a700549f01e9dba9e44b716c468a1))
* **settings:** create the labels of labels.toml with the settings ([#5](https://github.com/Dennis-Otto/repo-blueprint/issues/5)) ([5f76ffb](https://github.com/Dennis-Otto/repo-blueprint/commit/5f76ffbf3184297048995751fd1a247c7e191d18))
* start the blueprint ([d6bad3b](https://github.com/Dennis-Otto/repo-blueprint/commit/d6bad3b0663a89975c0e5334d939cb87dd67dd08))
* test properties every night, show the coverage and suit HACS ([#11](https://github.com/Dennis-Otto/repo-blueprint/issues/11)) ([b53ec72](https://github.com/Dennis-Otto/repo-blueprint/commit/b53ec72929909b0ca97d2186218732f98119ecf1))


### Bug fixes

* **deps-dev:** Bump typescript from 5.9.3 to 7.0.2 in /stacks/node in the node-stack group ([#8](https://github.com/Dennis-Otto/repo-blueprint/issues/8)) ([c55cc32](https://github.com/Dennis-Otto/repo-blueprint/commit/c55cc32967df8f4a456e7a27d6de06fc33f69808))
* **deps:** Bump alpine from 3.22 to 3.24 in /stacks/container ([#1](https://github.com/Dennis-Otto/repo-blueprint/issues/1)) ([3d44918](https://github.com/Dennis-Otto/repo-blueprint/commit/3d44918eaafa8f7a98e0f53af210c065fc40ad12))
* leave the fuzz targets and their requirements to the project ([#7](https://github.com/Dennis-Otto/repo-blueprint/issues/7)) ([82455ec](https://github.com/Dennis-Otto/repo-blueprint/commit/82455ecb75ce267848a99e4813e8538a24f3fce3))
* tag the license choice for REUSE and quote a path in the variants ([9385ca5](https://github.com/Dennis-Otto/repo-blueprint/commit/9385ca5a5b8e41ec27d095a2c59fd3e04ca014c2))
