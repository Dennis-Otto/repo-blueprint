# Changelog

All notable changes, by release. Each pull request that changes something for
users describes it under Unreleased. The release bot makes that text the section of
the next release, or lists the pull requests when there is none.

## Unreleased

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

## [0.3.0](https://github.com/Dennis-Otto/repo-blueprint/compare/v0.2.0...v0.3.0) (2026-10-07)


### Features

* attach the provenance of a release as in-toto JSON lines too ([#28](https://github.com/Dennis-Otto/repo-blueprint/issues/28)) ([fb73981](https://github.com/Dennis-Otto/repo-blueprint/commit/fb7398127309095aa47bc98dd881b225dd9a2718))
* give every project a dev container for VS Code and Codespaces ([#19](https://github.com/Dennis-Otto/repo-blueprint/issues/19)) ([25abe0a](https://github.com/Dennis-Otto/repo-blueprint/commit/25abe0af955971e23c6dbaa9bb664e3d6309a2a7))
* leave the issue forms to the project and start them richer ([#17](https://github.com/Dennis-Otto/repo-blueprint/issues/17)) ([1d0ab5c](https://github.com/Dennis-Otto/repo-blueprint/commit/1d0ab5cab167d98be93c2c7e1db61c08819f7882))
* raise max-version of a Nextcloud app with every new major version of Nextcloud ([#27](https://github.com/Dennis-Otto/repo-blueprint/issues/27)) ([e38bd79](https://github.com/Dennis-Otto/repo-blueprint/commit/e38bd79a52db501710dd2280dedead1f2716f223))
* record the network traffic of every job with Harden-Runner ([#20](https://github.com/Dennis-Otto/repo-blueprint/issues/20)) ([ebc7d85](https://github.com/Dennis-Otto/repo-blueprint/commit/ebc7d85d83a77b7f2fbe1ff49ab378b6cf903097))
* register a Nextcloud app in the App Store with a workflow of the app ([#30](https://github.com/Dennis-Otto/repo-blueprint/issues/30)) ([dce379a](https://github.com/Dennis-Otto/repo-blueprint/commit/dce379ab53a7be539f2339aa98c1c1558ee0a445))
* show every repository on a dashboard ([#26](https://github.com/Dennis-Otto/repo-blueprint/issues/26)) ([1c7e86f](https://github.com/Dennis-Otto/repo-blueprint/commit/1c7e86f56d08d9018590e44746f58d6c1acf7093))
* verify every release as its users can ([#21](https://github.com/Dennis-Otto/repo-blueprint/issues/21)) ([612e634](https://github.com/Dennis-Otto/repo-blueprint/commit/612e63420683205fcf16b1a08149d7d58b1cf71b))
* write the release changelog from Unreleased and keep the release pull request current ([#15](https://github.com/Dennis-Otto/repo-blueprint/issues/15)) ([b20402f](https://github.com/Dennis-Otto/repo-blueprint/commit/b20402f3a263bde2f2ecef0f8f7760e714c45c8f))


### Bug fixes

* **deps:** Bump the dev-container-features group across 2 directories with 2 updates ([#32](https://github.com/Dennis-Otto/repo-blueprint/issues/32)) ([6ccda81](https://github.com/Dennis-Otto/repo-blueprint/commit/6ccda81c2cecd3b8feb054ac07f607ef81cf2e54))
* **deps:** keep the version of each dev container and move only its digest ([#25](https://github.com/Dennis-Otto/repo-blueprint/issues/25)) ([028a4db](https://github.com/Dennis-Otto/repo-blueprint/commit/028a4db5b3112021943545c144a9282ff306760a))
* give Nextcloud apps the checks and package rules that the existing apps have ([#29](https://github.com/Dennis-Otto/repo-blueprint/issues/29)) ([d9b0e60](https://github.com/Dennis-Otto/repo-blueprint/commit/d9b0e602746adad79cb0c821884b7837d81ad15c))
* let updates reach every file of the blueprint, and give dev containers Docker and Node ([#31](https://github.com/Dennis-Otto/repo-blueprint/issues/31)) ([1674ee0](https://github.com/Dennis-Otto/repo-blueprint/commit/1674ee01bfa52dd35906bf5909f104cfca45de82))
* **settings:** accept rulesets whose bypass list the release app can't see ([#24](https://github.com/Dennis-Otto/repo-blueprint/issues/24)) ([e91116b](https://github.com/Dennis-Otto/repo-blueprint/commit/e91116bb5d0ad85602ba84cc2349a459994fb1c0))
* write the changelog into a release pull request that was just created ([#18](https://github.com/Dennis-Otto/repo-blueprint/issues/18)) ([d45caad](https://github.com/Dennis-Otto/repo-blueprint/commit/d45caadb5d55b4ac8b57c2caeb2b2c3d78d4d93b))

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
