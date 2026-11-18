# A bot notices a stale entry on bestpractices.dev and gives the links that take in the answers

- Status: accepted, amends [0047](0047-every-repository-proposes-the-best-practices-answers-that-the-blueprint-guarantees.md)
- Date: 2026-11-18

## Context

[Decision 0047](0047-every-repository-proposes-the-best-practices-answers-that-the-blueprint-guarantees.md) said that an update of the blueprint brings each changed answer of `.bestpractices.json` to every repository, as *Save (and continue) 🤖* on a level takes it in. It doesn't. bestpractices.dev reads the file with a confidence of 3.5 and replaces an answer that a project already has only at 4 or more, and a justification stays as it is while its status doesn't change. Its [documentation of automation proposals](https://github.com/coreinfrastructure/best-practices-badge/blob/main/docs/automation-proposals.md) says the same: a proposal fills only an unknown answer, unless the address of the edit page forces it with `overrides=`.

Release 1.22.0 joined the workflows *Secret scan* and *Dependency review* into *Quick checks*, and the answers of the file link `quick-checks.yml` since. On 2026-11-18 the public entries of all eight repositories still linked `secret-scan.yml`, which was gone, and 10 to 96 justifications of each entry differed from the file; nothing noticed, as no workflow and no part of `blueprint.py` read the entries ([#1046](https://github.com/Dennis-Otto/repo-blueprint/issues/1046)). The site has no way to write an entry with a token: a change needs a maintainer who is signed in. It asks for about one request per second at most and refuses a long address: one of about 9,500 characters got `414`, one of 7,000 did not.

## Options

1. **Correct the words only:** the template, the guide and 0047 say that *Save* fills only unknown answers. Nothing tells a maintainer when an answer of the file changes.
2. **A bot that writes the entry:** the site's API takes no token for it, and a login of a person in a workflow would be a secret of a person in every repository.
3. **A workflow of its own that reads the entry:** a new workflow, its runs and the bot-health bot's runs after them, every week in every repository, for one request.
4. **A job of the weekly run of *Links* that reads the entry and keeps one issue with the links of the edit pages,** which a maintainer opens while signed in.

## Decision

Option 4, with the words of option 1:

- **Read once a week:** the job *best practices entry* of `links.yml`, on its schedule and by hand, runs `blueprint.py best-practices`. The number of the project comes from the badge of the README, of either series, as the checklist reads it; a repository without the badge asks nothing. It reads `https://www.bestpractices.dev/projects/<number>.json` once, without a login, through Harden-Runner, which allows only GitHub and `www.bestpractices.dev`.
- **Compare the answers of the file only:** each field of `.bestpractices.json` with the field of the entry, `osps_br_07_01_justification` of the file being `OSPS-BR-07.01_justification` of the entry; a status by its value whatever its case, a justification by its text without the spaces at its ends, as the site strips both. Each link of a differing justification of the entry into the repository, on any branch, is checked against the files of the checkout, without a request. What a maintainer answers on the site and the file leaves out is never reported.
- **One issue:** *The answers on bestpractices.dev differ from .bestpractices.json*, found by a mark in its text, as the issue of the acceptances that end soon is. It lists each answer that differs or links a file that is gone, with the text to enter, and closes once the entry gives every answer. A site that doesn't answer is a warning, and the issue stays as it is. An issue that would pass the 65,536 characters of GitHub leaves out the texts, which its links carry anyway.
- **One link per level:** `https://www.bestpractices.dev/en/projects/<number>/<level>/edit?<field>=<answer>&…&overrides=<fields>`, for passing, silver, gold and baseline-1 to 3, each with the criteria of its own level from `blueprint/bestpractices-criteria.json`, as the site ignores a proposal for another level. `overrides=` names exactly the fields that the entry answers otherwise; an empty one takes the proposal without it. A status and its justification stay in one link, since the site couples them. A link stays at 8,000 characters or below, and the criteria of a level that need more are split into parts, each of which the site takes on its own, since it leaves the fields that a link doesn't name as they are.
- **The list of the criteria** moves from `tests/data/` to `blueprint/bestpractices-criteria.json`, which every repository gets as `.github/blueprint/bestpractices-criteria.json`, so that the bot knows the level of each criterion; the tests of 0047 read it from there.
- **The words:** the comment of `template/.bestpractices.json.jinja`, the guide, the page of the bots and the checklist say that *Save (and continue) 🤖* fills only the questions still open, and that a changed answer comes through the links of the bot's issue. The consequence of 0047 that an update brings a changed answer by itself no longer holds.

## Consequences

- A stale entry shows within a week of the update that changed the file, and putting it right takes a few clicks per level: the maintainer opens each link while signed in, checks the fields that the form highlights and saves.
- The bot never writes the entry and needs no secret; the issue is the only thing that it changes.
- Each repository with the badge sends one request a week to bestpractices.dev.
- What only a signed-in maintainer can see, that the site takes a forced justification whose status doesn't change, rests on the site's code (`apply_url_proposals` of `projects_controller.rb`) until a maintainer has saved one such link.
