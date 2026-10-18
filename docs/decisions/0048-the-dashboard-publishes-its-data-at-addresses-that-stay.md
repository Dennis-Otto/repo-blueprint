# The dashboard publishes its data as JSON and a feed, at addresses that stay

- Status: accepted
- Date: 2026-10-18

## Context

Every two hours, `dashboard.py` collects the state of each public repository of the owner: the release of the blueprint it is on, its latest release and its date, the last runs of its main workflows, its Scorecard and its health. It published all of it only as a page of HTML, beside a `history.json` of the health of each day without a release or a Scorecard. The owner's website, which lists every project, wants to show the version and the numbers of each one on its cards, and the only other source is GitHub's API, which every reader's browser would ask, with a limit of 60 requests an hour for each address on the internet. The portfolio had no feed of its releases, which most hubs of open source offer, and the dashboard had no column for the website, although the website is what one of the six repositories makes and a key output of the others.

## Options

1. Let the owner's website ask GitHub's API in the browser: no change here, but a request to another server on every visit, which the settings of every website promise not to make (decision 0046), and a limit that a shared network reaches.
2. Let the owner's website collect the data itself, in a workflow of its own: a second copy of what `dashboard.py` already collects, with its own errors and its own token.
3. Publish what the dashboard collects as data beside the page, on the same GitHub Pages host, at addresses that stay, with a feed of the releases from the same requests.

## Decision

Option 3. Beside `dashboard/index.html` and `dashboard/history.json`, the Dashboard workflow publishes:

- **`dashboard/repos.json`:** every value that the page shows, with the description, website and stars that the list of the owner's repositories already holds. `null` stands for a value that isn't known, never an empty text. A field `schema`, now 1, rises with a change that takes a field away or changes its meaning; a new field doesn't raise it.
- **`dashboard/releases.atom`:** an Atom 1.0 feed of the 30 newest releases of every repository, without prereleases and drafts, each with the first 500 characters of its notes as plain text, from the list of releases that the health already fetches. ElementTree writes it, so every text and attribute is escaped, and the control characters that XML 1.0 has no place for are left out. The head of the page names it and `repos.json`, so a feed reader finds the feed from the address of the page.
- **A column *Website*:** the last run of the Docs workflow on `main`, which builds the website of each repository and publishes it everywhere but in the blueprint, where the Dashboard workflow publishes it and the time at the top of the page shows its last run.

The four addresses stay: a page that moves the dashboard, such as one that makes it a page of the website, keeps `dashboard/index.html`, at least as a redirect, and the three files of data where they are. The job that publishes the dashboard asks for each of the four after every deployment and fails when one is missing or holds something else.

## Consequences

The owner's website reads one file from its own host, without a token, a limit or a request to another server, and shows what the dashboard showed at its last run, at most about two hours old. Anyone can follow every release of the owner's projects in one feed. A change of `dashboard.py` that takes a field of `repos.json` away or changes its meaning raises `schema` and is a change for its readers: the owner's website changes with it. The README names the four addresses and the fields of `repos.json`.
