# The dashboard lists other owners' repositories made with the blueprint, with an opt-out topic

- Status: accepted
- Date: 2026-11-07

## Context

The showcase of the README and the Rollout know the owner's own repositories from `.github/fleet.toml` ([#457](https://github.com/Dennis-Otto/repo-blueprint/issues/457)). A repository of another owner that `copier copy` made from the blueprint is known nowhere: nobody sees that the blueprint is used beyond its owner, and nobody sees how far behind such a copy is. [#460](https://github.com/Dennis-Otto/repo-blueprint/issues/460) asked for a weekly code search, a list on the website and an opt-out topic, and left open whether the token of a job may search the code of all of GitHub. The owner chose a public list with an opt-out topic on 2026-11-07.

Real requests answered that question. With the owner's token, the search of the REST API for `"Dennis-Otto/repo-blueprint" filename:.copier-answers.yml` finds two repositories, one of them of another owner, on v0.8.1 of the blueprint; it doesn't find every repository of the owner either, because the legacy code search of the REST API indexes only a part of GitHub. With the token of a run of the Dashboard workflow, a probe of five searches a minute apart was answered 200 twice, with the same two repositories, and 429 three times, with `Retry-After` of 7 to 56 seconds and the message `try again in 56.9s`, while `X-RateLimit-Remaining` still said 10 of 10: the job's token may search, under a limit of its own that GitHub doesn't name. The Api of the bots waited only for an answer that says *rate limit*, so the first run's only search failed.

## Options

1. A list that the owner keeps by hand, as `.github/fleet.toml`: no search, but a repository of another owner reaches it only when someone tells the owner.
2. Repositories that opt in with a topic, found by the search of repositories: reliable, but a list of the few who know of the topic.
3. A weekly code search for the answers of Copier, with a topic that opts out, checked again in every run.

## Decision

Option 3, in `dashboard.py`:

- **The search:** once a week, the first run after seven days asks the code search for `.copier-answers.yml` that names the blueprint, one page of 100. A repository joins the list only where its answers at the root name the blueprint as `_src_path` (`gh:`, HTTPS or SSH, with or without `.git`) and GitHub shows it as public, no fork, not archived and without the topic `repo-blueprint-unlisted`, and not as one of the owner's, which the dashboard shows anyway.
- **The checks in between:** every run checks each repository on the list again, a request each, so that one that takes the topic, goes private, is archived, is blocked or is gone leaves the list within two hours.
- **What the list shows:** the full name, the kind and the release of the blueprint, from the answers, each only where it is a plain value, and escaped on the page. Nothing else of another owner, such as a description, reaches the page.
- **What stays:** the list is published as `dashboard/made-with.json` beside the page, which the next run reads, as it reads `history.json`. When GitHub refuses the search or a check, the list stays as it was, the page says so and the run warns; a published list that can't be read fails the run, so that a failed search never publishes an empty list.
- **429 with a time to wait:** the Api of the bots now waits the seconds of `Retry-After`, up to 90, after a 429 without the words *rate limit*, and tries once more, as it does after a secondary rate limit.

## Consequences

The website shows who uses the blueprint and how far behind each copy is, without a token or a secret beyond the job's own. The list misses a repository that the legacy code search doesn't index, as it misses some of the owner's own: it can show only what the search finds. A repository of another owner appears on a public page without asking; the topic takes it off within two hours, and README.md and README.de.md name the topic. A change of the shape of `made-with.json` raises its `schema`, as one of `repos.json` does.
