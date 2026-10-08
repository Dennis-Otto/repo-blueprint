# Changelog

All notable changes, by release. Each pull request that changes something for
users describes it under Unreleased. The release bot makes that text the section of
the next release, or lists the pull requests when there is none.

## Unreleased

### Bug fixes

- **The language switch finds its sitemap on every page:** on a page in a folder, such as a decision record in `docs/decisions/`, the switch of Material asked for the sitemap in the folder of the page in each language, such as `decisions/sitemap.xml` and `de/decisions/sitemap.xml`, and the browser logged two errors. The hook of the blueprint now copies the sitemap into every folder that holds a page. The switch already led to the same page in the other language.

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
