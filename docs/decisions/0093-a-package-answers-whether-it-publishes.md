# A package answers whether it publishes, and its documents follow that answer

- Status: accepted
- Date: 2026-11-01

## Context

`publish_to` followed the kind of project alone, and nobody could answer it. A package that delivers nowhere, such as player-switch-for-autodarts, a `node-package` with `private: true`, could only set `PUBLISH_TO = "none"` in `.github/repository.project.toml`. That changes the release, but the template renders the documents from `publish_to`: `SECURITY.md` told its users to download and verify a `*.tgz` that no release has and to run `npm audit signatures`, which fails the criterion `documentation_current` of OpenSSF Best Practices.

## Options

1. An answer `publish_to` with a list of targets. Its sensible values depend on the kind, so it would let a Nextcloud app answer `npm`, and a validator would have to forbid that for every kind.
2. Read `.github/repository.project.toml` while rendering. Copier gives a question and a template no file of the destination, and the blueprint bot updates without `--trust`, so no extension can do it.
3. A kind of project for each target, as `chrome-extension` is for an extension in the Chrome Web Store. A private package has the tools, the checks and the workflows of its kind; only its delivery differs.
4. A question `publish_package`, yes or no, asked of the two kinds that deliver to a registry of their own, from which `publish_to` follows.

## Decision

Option 4, because it can't name a target that doesn't fit the kind and leaves `publish_to` as the one value that every condition of the template and the variable `PUBLISH_TO` read.

- **Only `node-package` and `python-package` are asked.** The delivery of the other kinds is what they are: an integration on HACS, an app in the App Store, an action by its tags, an image in the registry, an extension in the store. A generic project delivers nowhere already.
- **With no, `publish_to` is `none`,** as for a generic project: the release builds no package, `SECURITY.md` shows the commands for any asset, `GOVERNANCE.md`, `CONTRIBUTING.md` and `.bestpractices.json` name no registry, `.github/repository.toml` has no environment for it, the checklist asks for no trusted publisher, and the default topics leave out `npm` or `pypi`.
- **A new repository is safe from a slip:** `"private": true` in `package.json`, the classifier `Private :: Do Not Upload` in `pyproject.toml`, and a `README.md` without an install command that can't work.

## Consequences

An existing repository gets the default yes with its next update, and nothing changes for it. One that set `PUBLISH_TO = "none"` itself answers no once, on the branch of that update, with `copier update --defaults --vcs-ref=:current: --data publish_package=false`, and removes that line. Before that update the command changes nothing and reports nothing, because `:current:` is a release without the question. The topics are a stored answer too, so a repository with the default ones also passes the new topics in a `--data`.

`README.md`, `package.json` and `pyproject.toml` belong to the project, so an update doesn't change them; the changelog says so.

A value of `PUBLISH_TO` in `.github/repository.project.toml` stays possible, as for every variable, and still changes only the delivery; the page of the variables says that the documents follow the answer. The targets that `build-release.yml` and the other workflows know don't change.
