# Roadmap

Where the blueprint is heading in the next twelve months, until October 2027, and what it will not do. It is a direction, not a promise: the needs of the repositories made from it set the order. Ideas are welcome as [feature requests](https://github.com/Dennis-Otto/repo-blueprint/issues/new?template=feature_request.yml) or in the [discussions](https://github.com/Dennis-Otto/repo-blueprint/discussions).

## Done

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="images/diagrams/the-larger-steps-of-the-blueprint.dark.svg">
  <img src="images/diagrams/the-larger-steps-of-the-blueprint.svg" alt="The larger steps of the blueprint: 0.1 to 0.3 brought seven kinds of projects, the settings as code and the release bot; 0.4 and 0.5 the settings bot, Renovate and the beta channel; 0.6 to 0.8 the websites, SLSA Build Level 3 and signed tags; 0.9 and 0.10 the Rollout of every release, the branch bot and checks that get going again; 0.11 and 0.12 the diagrams that every app shows, the PR coach and the bot-health bot. The next release brings the blueprint for any owner, the screenshot bot and one report on every pull request; next come pages for every question, visual changes in pull requests and more kinds of projects.">
</picture>

The [changelog](https://github.com/Dennis-Otto/repo-blueprint/blob/main/CHANGELOG.md) names every change of every release. The larger steps so far:

- **0.1 to 0.3:** seven kinds of projects, the settings as code, the security checks of the workflows, fuzzing and property tests, the release bot with the changelog that the pull requests write, the verification of every release, prereleases, the dev container, the dashboard and Harden-Runner.
- **0.4:** the settings bot that applies the settings as code itself, OSV-Scanner, area labels, the changelog check and the licenses of the third-party components in every release.
- **0.5:** Renovate instead of Dependabot, a beta channel, the records of decisions, the coverage of every pull request, the flaky-test bot, the SBOM as CycloneDX with an OpenVEX document, the Markdown lint and the announcement of every release.
- **0.6:** a documentation website for every repository, the build of every release in an isolated workflow (SLSA Build Level 3), release tags signed without a key, mutation tests every week, the taint analysis of Psalm for a Nextcloud app, hints at the spelling and the style of the documents, the clean-up bot, the weekly report, the health of every repository on the dashboard and the documents that the Silver level of the OpenSSF Best Practices badge asks for.
- **0.7:** the settings that every website shares, from the blueprint, and a successor that the owner designated on GitHub, who can carry the project on.
- **0.8:** websites in more than one language, issue forms that point to the documentation, and the website of the owner itself made from the blueprint.
- **0.9 and 0.10:** the Rollout, which brings every release to every repository within minutes, one repository after the other, where the weekly run of the blueprint bots took up to a week ([decision 0052](decisions/0052-roll-out-every-release-at-once.md)), with one update pull request that each release moves on; the branch bot, which brings the pull requests of Renovate up to date with `main` too, so that an update whose checks passed merges without waiting for the next run of Renovate; checks that run only where they can change a result; and checks and releases that stall get going again without a person.
- **0.11 and 0.12:** the diagrams as pictures that every reader sees, also in the GitHub app and the stores, the PR coach, which explains every check that fails, the bot-health bot, which keeps an issue open while a bot fails, an `AGENTS.md` for the coding agents, the fragments of the changelog in `changelog.d/`, over which pull requests no longer conflict, and release tags that only the release app creates.
- **OpenSSF Best Practices:** the blueprint holds [the Silver level](https://www.bestpractices.dev/projects/15284) of the badge.
- **The next release:** the blueprint for any owner, with a release app of their own, Renovate of their own and an AI that reads the issues if they want one, and `blueprint.py create`, which makes a new copy its repository with one command; the screenshot bot, whose pictures change only when their pixels change, in every repository and for the blueprint's own documentation; pull requests that fix what a command can fix by themselves, and one report on each that says what it makes; a page of the automation and a website that is accessible and quick in every repository; the answers of OpenSSF Best Practices and of the OSPS Baseline, proposed in every repository; the data of the dashboard as JSON and a feed of the releases; and what else the fragments in `changelog.d/` and the section *Unreleased* of the changelog list.

## Next

| Topic | What it brings |
| --- | --- |
| **Documentation for every question** | A page for every question of Copier and every variable, an FAQ, help when something fails, a page on how the blueprint works, a comparison with other templates, and a page for each kind of project, with the repositories made from it |
| **Visual changes in pull requests** | A pull request that changes what a picture of the screenshot bot shows shows the picture before and after the change in its report, rendered by the same script, and one that changes the website shows its changed pages, before and after |
| **More pictures for the screenshot bot** | Starter scripts for each kind of project, screenshots of the public GitHub pages for the blueprint's own documentation, and ha-autodarts on the shared workflow ([#271](https://github.com/Dennis-Otto/repo-blueprint/issues/271)) |
| **A website that shows the blueprint** | A logo and colors of its own, a home page that shows what a repository gets, and a page that builds the command of `copier copy` from your answers |
| **Commands in pull requests** | `/update`, `/retest` and `/automerge` in a comment of a pull request |
| **More kinds of projects** | Cards for the dashboards of Home Assistant, apps of Home Assistant (add-ons), and actions in JavaScript and TypeScript |
| **Version 1.0.0** | A policy of versions and support that says what 1.0.0 promises, and then the release 1.0.0 |

## Always

- New versions of the dependencies and the actions, and every new major version of Nextcloud, reach the repositories through the update bots.
- Every new release of the blueprint reaches every repository made from it as a pull request of the blueprint bot: within minutes for the repositories of the release app, which the Rollout takes one after the other, and with the weekly run of the bot for every other one.
- What GitHub adds for the security of repositories and releases is taken up when it fits, as immutable releases and their attestations were.

## Not planned

- **Forges other than GitHub.** The blueprint builds on the rulesets, environments, attestations, immutable releases and the API of GitHub.
- **Releases by hand.** Versions follow the titles of the pull requests, and the notes are the text that they write in their fragments of the changelog or under *Unreleased*.
- **Bots that merge what nobody approved.** Only updates that pass every check merge on their own; every other change waits for a person.
- **Secrets in files.** `blueprint.py` never reads or sets the value of a secret, and no file of the blueprint holds one.
