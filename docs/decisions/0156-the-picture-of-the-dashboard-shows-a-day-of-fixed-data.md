# The picture of the dashboard shows a day of fixed data

- Status: accepted, follows up [0145](0145-the-recording-of-copier-copy-renews-itself-only-when-a-screen-changes.md)
- Date: 2026-11-14

## Context

`scripts/docs-pictures.sh` photographed the live dashboard for `docs/images/dashboard.png`, which the page of the bots and the social card of the dashboard show. The live dashboard shows the time of its last run, the release of the blueprint that each repository is on, the state of each workflow and the health of each repository, which change with nearly every run. So `blueprint.py screenshots keep` found other pixels in each run of the Docs pictures workflow, which runs after nearly every release, and the bot renewed the picture each time: 3.4 MiB of history in 23 versions after five weeks ([#827](https://github.com/Dennis-Otto/repo-blueprint/issues/827)). `docs/images/screenshots-difference.png`, which the code of `keep` draws of the same page, changed with it.

## Options

1. **Keep photographing the live page,** and accept a new picture with nearly every release.
2. **Pin the time and the versions of the live page** before the browser draws it. The states of the workflows, the pull requests, the Scorecard and the health still change.
3. **Render the page from fixed data.** `dashboard.py` writes everything that its page shows into `repos.json` too; the same code renders the page of one day from that data, at the time of that day.

## Decision

Option 3. `.github/docs-pictures/dashboard.json` holds the `repos.json` of the published dashboard of one day and, under `a_week_ago`, the health of each repository a week before, from its `history.json`, for the arrows of the table *Health*. `.github/docs-pictures/dashboard_page.py` turns it back into the rows of `dashboard.py` and renders the page with `render` of `dashboard.py`, at the time of `generated`, with the cap of its width lifted so that every column is in the picture; the browser photographs that page, and `difference_picture.py` draws its difference from the same page.

A test reads the data back into what `dashboard.py` would publish of it, field for field: a field of a repository that the dashboard adds or drops fails it until the data has it too, so the picture can't fall behind the page.

## Consequences

- The picture changes when the code of the page changes its layout, its columns or its words, or when the browser draws them another way, not with each run of the dashboard. So does the picture of a difference.
- The picture shows the repositories of one day: a new repository of the owner, or another name, shows only once someone saves the published data anew, with `curl` of `repos.json` and the entry of `history.json` a week before. The list *Also made with the blueprint* is below the part of the page that the picture shows and stays empty.
- Rendering needs no network: the page is the same on every machine with the same image of the browser.
