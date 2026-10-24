# The website shows the pictures of its repository from the checkout, so that a pull request shows a new screenshot on its website too

- Status: accepted
- Date: 2026-10-24

## Context

A README shows its pictures from `main` of its own repository, such as `https://github.com/OWNER/NAME/raw/main/screenshots/settings.png`, so that they show wherever the README does: on GitHub, on PyPI, in the store of a Nextcloud app and in HACS, where a relative path leads nowhere. The website includes the README, and the privacy plugin of Material downloads every picture from another server while it builds, so that reading a page asks no other server. A pull request that adds a screenshot can't show it on the website: `main` doesn't have it before the merge, the download answers 404, and the strict build fails. So every new screenshot needed a second pull request after the first one was merged, to show it on the website, and paperless-unified-search forgot that follow-up four times ([#367](https://github.com/Dennis-Otto/repo-blueprint/issues/367)); a check of the project there only named the follow-up. A pull request that deletes or moves a picture that the README still shows passed the other way round: `main` still had it.

## Options

1. Keep downloading from `main`, and let a check name the follow-up. Every new screenshot still needs a second pull request, and a person who forgets it leaves the website without the screenshot.
2. Let the README name its pictures by relative paths, such as `screenshots/settings.png`. GitHub and the website show them, but PyPI, the stores and HACS show a broken picture.
3. Let the hook of the website serve such a picture from the checkout: the file that the pull request has, the same that `main` will have once it is merged.

## Decision

Option 3. `.github/mkdocs_blueprint.py` takes every picture of a page, in `<img>` and in each candidate of the `srcset` of a `<source>`, that the page shows from `main` of the repository that `repo_url` of `mkdocs.yml` names: on `github.com/OWNER/NAME/raw/main/`, its `blob/main/…?raw=true` and `raw.githubusercontent.com/OWNER/NAME/main/`, also from `HEAD` or `refs/heads/main`, with the owner and the name in any case.

- **A picture of `docs/`** is the one that the website has already, at its path there.
- **Any other picture** is served from the checkout in `assets/images/repository/`, at its path in the repository, once git tracks it, with the video and the posters that git tracks beside a GIF, so that the GIF plays as its video as one in `docs/` does. The website names each such file by its path there, so that it takes the place of no file of `docs/`.
- **A picture that git doesn't track,** such as a new screenshot that isn't committed, one that the pull request deletes, a folder or a link out of the repository, warns, which fails the strict build, as `main` would lack it once the change is merged. A path out of the repository, such as `../`, stays an address of GitHub.
- **Without git,** or outside a repository, nothing can tell what `main` will have, and the privacy plugin downloads the picture from `main` as before.

Any other address stays as it is: another repository, another branch or a tag, such as a picture of a release, and another server.

## Consequences

The pull request that adds a screenshot shows it on the website that the check *docs* builds, and the website of `main` shows it with the merge: no second pull request, and no check of a project that names one; the exemption of paperless-unified-search for pictures that `main` doesn't have yet can go. A build downloads no picture of its own repository from GitHub any longer, and one that fails on a picture that git doesn't track says which page shows it and how to fix it, also for a pull request that deletes a picture that the README still shows. A README that shows its pictures from another branch, or from the old name of a renamed repository, still downloads them.
