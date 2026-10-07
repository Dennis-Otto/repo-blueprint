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

### Bug fixes

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

## Changelog

All notable changes, by release. The release bot writes each section from the
titles of the merged pull requests.
