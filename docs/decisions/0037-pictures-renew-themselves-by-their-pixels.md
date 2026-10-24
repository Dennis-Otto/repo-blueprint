# Pictures renew themselves by their pixels, through one pull request of a bot

- Status: accepted, amended by [0065](0065-every-kind-photographs-itself-in-docker-with-the-playwright-of-the-browser.md), with which a new repository photographs its website and, by its kind, its integration or app, and the job *render* checks out the whole history
- Date: 2026-10-18

## Context

The pictures of a project, in its README, on its website and in the stores, are the first thing a visitor sees, and they show the project as it was when someone last took them. ha-autodarts has a screenshot bot of its own: a frozen demo, a comparison by pixels and one pull request of the release app that merges itself. The other repositories have none, and the pictures of the blueprint's own README, the recording of `copier copy` and the dashboard, were renewed only by hand and lagged behind the questions and the workflows.

Two things make a naive bot useless. A new version of Chromium, of an encoder or of the runner writes other bytes for the same pixels, so a bot that compares files opens a pull request every week that changes nothing a person can see. And the script that renders the pictures is code of the project, which must not run where a token that writes is at hand.

## Options

1. Leave the pictures to each project, as ha-autodarts does. Each repository builds its own bot, or has none.
2. One workflow of the blueprint in every repository that runs a script of the project without secrets, keeps every picture whose pixels stayed the same, and keeps one pull request with the others, as the release app, which merges itself.
3. As 2, but the bot pushes the pictures onto `main`. The rulesets require a pull request with passing checks, and a bypass for a bot would also let a broken picture or a file that is no picture through.
4. Render the pictures in every pull request and show what changed. It needs the script on code of forks and is a step of its own; the roadmap names it next.

## Decision

Option 2.

- **A script turns it on:** the Screenshots workflow (`screenshot-bot.yml`) is in every repository, and its job *plan* ends the run while the project has no `scripts/screenshots.sh`. The script and `.github/screenshots-paths.txt`, the files whose change can change the pictures, belong to the project (`_skip_if_exists`); a new repository with the sample code starts with a script that renders the social preview, and an adopted one keeps its own. The workflow has a name of its own so that it never overwrites a project's `screenshots.yml`, such as that of ha-autodarts.
- **When it renders:** after a change of `main` that touches a file of the list, which the job *plan* checks with `blueprint.py screenshots due`, because a workflow of the blueprint can't take its `paths:` from a file of the project; after every release; every Friday; and on demand.
- **Only pixels count:** `blueprint.py screenshots keep` compares each picture that the script changed with the one of `main` with Pillow, hash-pinned in `stacks/screenshots/requirements.txt`: every frame by its colors weighted by their transparency, a frame that repeats the one before once, the time of each frame not at all. A picture that looks the same gets its committed file back.
- **Two jobs, two tokens:** the job *render* runs the script with a token that only reads and without secrets, and hands the pictures over as an artifact. The job *pull-request* runs nothing of the script: `blueprint.py` of `main` takes only PNG, JPEG, GIF and WebP files whose content starts as their kind does, by plain paths outside `.git` and the workflows, no link, and only those that the report names.
- **One pull request that merges itself:** the commits go through `createCommitOnBranch` as the release app, so GitHub signs them and the checks run, in parts below 8 MB, onto a branch of their own that starts at the rendered commit; then `bot/screenshots` moves there in one step. The pull request merges itself once every check passes, and the bot closes it when `main` looks as rendered without it. Without the release app, the run warns and keeps the pictures as an artifact.
- **The blueprint's pictures:** the Docs pictures workflow (`docs-pictures.yml`), in the blueprint alone, runs `scripts/docs-pictures.sh` in the same way after a release that changed a file of `.github/docs-pictures/paths.txt`, and keeps one pull request from `bot/pictures`.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/how-the-screenshots-renew-themselves.dark.svg">
  <img src="../images/diagrams/how-the-screenshots-renew-themselves.svg" alt="How the screenshots renew themselves: After a change of main that touches a file of .github/screenshots-paths.txt, after every release, every week and on demand, the screenshot bot looks for scripts/screenshots.sh; without it, the bot renders nothing. The script renders the pictures without secrets, and each picture whose pixels stayed the same keeps its committed file. When pixels changed, one pull request from bot/screenshots holds the new pictures and merges itself once every check passes; when main looks as rendered, the bot closes it. So every picture shows the project as it is.">
</picture>

## Consequences

The pictures of every repository with a script stay current without a person, and a run whose pixels stayed the same changes nothing. paperless-unified-search and dennis-otto.github.io have a `scripts/screenshots.sh` already, so their bot starts with the update of the blueprint; the job *render* sets up the tools of the website in `.venv-docs`, as `CONTRIBUTING.md` does, for a script that photographs its pages. ha-autodarts keeps its own bot until it moves to this one. A script that renders other pixels each time, because of a clock, random data or an animation that isn't waited for, opens a pull request every week: the fix belongs in the script, and the table of the pull request shows the share of the pixels that changed. Each run that renders costs one job of up to an hour, and those that don't a job of seconds.
