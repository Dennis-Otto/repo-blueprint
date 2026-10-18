# A website leads to its owner and asks GitHub for nothing

- Status: accepted
- Date: 2026-10-18

## Context

The websites of the repositories made from the blueprint showed only their copyright in the footer: a reader of the ha-autodarts documentation, the largest of them with about 500 pages, found no way to the owner's other projects or to the owner's own website, which lists them all. The header showed the stars, forks and latest release of the repository, which the script of Material fetched from the API of GitHub in the browser of every reader, once in each session, although the settings of every website promised that reading a page asks no other server. On the owner's own website, which had no release, the request for the latest release failed with a 404 and an error in the console on every visit, and on a network that many people share the API refused with a 403.

## Options

1. Keep the script of Material and write the links of the footer into the `mkdocs.yml` of each repository: every repository keeps its own copy, which falls behind, and every reader still asks GitHub.
2. Turn the link to the repository off, with `repo_url` unset: the header loses the link to the code, and the pencil on every page needs `repo_url` too.
3. Let the hooks of every website write both at the build: the links of the footer from what the repository already says, and the version of the latest release in the header, from git, with the attribute that has the script of Material ask GitHub taken away.

## Decision

Option 3, in the hook of every website, `.github/mkdocs_blueprint.py`.

- **The footer:** a link to the owner's profile on GitHub, from `repo_url` or an absolute `edit_uri`; to the owner's website, `https://owner.github.io/`, for a website under it, which the owner's own website is not; and to GitHub Sponsors, for the first account that `github:` of `.github/FUNDING.yml` names, as the sponsor button of the repository does. Their names, which a screen reader reads and a pointer shows, are in the language of the page, English or German. A list `extra.social` of `mkdocs.yml` takes their place, and an empty one shows none, since INHERIT replaces every list.
- **The header:** the newest stable tag before the commit of the build, `git describe --tags --abbrev=0 --match 'v[0-9]*' --exclude '*-*'`, as Material would show the latest release; the Docs workflow checks out the whole history. Without a release, without the history or without git, the link names only the repository, and a link to the owner's profile, as on the owner's own website, shows no version. Stars and forks are left out: they would be as old as the build.
- **The proof:** `blueprint.py site-check` fails a built page whose link to the repository still has `data-md-component="source"`, so that a new release of Material that writes it otherwise stops the check *docs* before the website is published.

## Consequences

No page of any website asks another server while it is read, as its settings promise, and the browser console stays free of errors on a website without a release. Every website leads to every other project of the owner with the next update, without a change of its `mkdocs.yml`. The version in the header changes with the next build after a release, which the Docs workflow runs for the commit of the release. The links of the owner's website assume that the owner has one at `https://owner.github.io/`; a website under that address of an owner without one sets `extra.social` in its `mkdocs.yml`.
