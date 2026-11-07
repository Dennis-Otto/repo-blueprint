# The screenshot bot renders in shards, takes the files that a project names and blocks the hosts that it doesn't

- Status: accepted
- Date: 2026-11-07

## Context

The shared screenshot bot (`screenshot-bot.yml`, [decision 0037](0037-pictures-renew-themselves-by-their-pixels.md)) runs `scripts/screenshots.sh` in one job of up to an hour, commits only pictures, and lets Harden-Runner only record the traffic of that job. HomeDarts for Autodarts keeps a workflow of its own, `screenshots.yml`, because it needs three things that the shared one lacks ([#421](https://github.com/Dennis-Otto/repo-blueprint/issues/421)):

- It renders its images in eight jobs side by side, two languages times four groups, each from a fresh demo, and puts them together in a job of each language. One job would take most of an hour.
- The same pull request brings `docs/demo/timeline.json`, the recording that the live demo of its website plays.
- Its jobs that render block every host that they don't need (`egress-policy: block`). Moving to a job that only audits would weaken that control.

The boundary of [decision 0118](0118-a-bot-whose-pull-request-conflicts-builds-it-anew-at-once.md) stays: the jobs that run the script have no secrets and a token that only reads, and the job with the token of the release app runs only `blueprint.py` of a commit that `main` has, and takes what the script made as data that it checks. A render that waited renders `main` as it is then.

## Options

1. **A matrix of shards in the one run, with a group of concurrency for each shard.** A group of the job would hold all shards of a run as one, which runs them one after the other and cancels the waiting ones; a group for each shard lets the shards of two runs interleave, and the shards of a run that waited would start at different times and render different commits of `main`.
2. **A reusable workflow for the render, behind a job with one group of concurrency.** It holds the shards together, but every repository gets a further workflow, and how GitHub holds such a group across the jobs of the called workflow is not written down.
3. **A run by hand renders, one at a time.** The plan of a push, a release or the weekly run only decides, and when the change is due, it starts a run of the workflow by hand, as the branch bot and a person do already. Only those runs share one group of concurrency, in which the newest waiting run replaces an older one, so a run that waited renders the newest `main`; every other run is in a group of its own. In the run, the job *start* names the newest commit and the shards, every shard renders that commit, and the job *collect* puts them together.

For the files besides pictures: any file that the script changes (too wide: a script or a tool that went wrong would commit code that merges itself), files by their endings (a `package.json` or a `requirements.txt` is data by its ending and runs code all the same), or the exact paths that the project names.

For the hosts: a list in the workflow (a workflow of the blueprint can't name the hosts of each project), or a list of the project that the job *start* reads from the commit of `main`.

## Decision

Option 3, with `.github/screenshots.toml`, a file of the project, which can name three lists; without it, everything stays as before, one job, only pictures, Harden-Runner records:

```toml
# The shards that render side by side, each on a runner of its own, with
# SCREENSHOTS_SHARD set to its name; each renders and deletes only its own pictures.
shards = ["en-1", "en-2", "de-1", "de-2"]
# Files besides pictures that the script renders, by their exact paths.
files = ["docs/demo/timeline.json"]
# The hosts that the jobs that render may reach, besides those of their own steps.
hosts = ["ghcr.io:443", "pkg-containers.githubusercontent.com:443"]
```

- **Shards:** `blueprint.py screenshots plan` turns the list into the matrix of the job *render*, of up to 256 plain names, and the script gets the name of its shard in `SCREENSHOTS_SHARD`; without shards, one job renders every picture and the script gets no name, as on a machine. Each shard compares its pictures with those of `main` as before and keeps what changed in an artifact of its own. Once every shard passed, the job *collect* checks the folder of each shard as the job with the release app does, and puts them together, with `blueprint.py screenshots collect`; a path that two shards changed fails the run, since each picture belongs to one shard. The pull request takes every shard or none: a pull request of only some shards would drop the pictures that another shard put into it before. A shard that fails leaves the others running, so that a rerun of the failed jobs renders only that one.
- **Files besides pictures:** a path of plain names, outside `.git` and `.github`, which hold the history, the workflows and the settings, and no picture, which the bot takes anyway. The job with the release app reads the list from its own checkout of `main` and takes a file only when it is in that list and is text in UTF-8, so that its pull request shows it line by line; the kind of each change comes from its path, never from what the run says. A file counts as changed when its bytes change. The project names only data that nothing runs, such as a recording that a page plays: never code, a manifest or a configuration.
- **Hosts:** each one as Harden-Runner takes it, `host:port` in small letters, a wildcard as `*.host`. With hosts, the jobs *render* block every other one, besides those that their own steps need, for the code, uv, the packages of Python and the artifacts, and wait until Harden-Runner lets them through; without them, they only record the traffic. The job *plan*, whose token may now start a run, blocks every host but those of GitHub.
- **Strict settings:** a key that the bot doesn't know, a name that isn't plain, a host without its port, a list that names one twice or a file that it may not take fails the run that starts the render, with what is wrong, so that a typo never drops a host or a shard without a word. A change of the settings counts as a change of the list, so the next render tries it out.

## Consequences

- A due push costs a second, short run: the plan, and the run by hand that renders. The runs by hand wait for each other, the plans never.
- HomeDarts for Autodarts can move to the shared workflow: its script renders the group that `SCREENSHOTS_SHARD` names, `.github/screenshots.toml` names its shards, `docs/demo/timeline.json` and its hosts, and its sources go into `.github/screenshots-paths.txt`. It gives up two things of its own workflow: the reuse of images that an earlier run rendered from the same files, and the pull request of the language that rendered while the other failed.
- `blueprint.py screenshots keep`, `restore`, `commit` and `report` read the settings too, on a machine as in the bot, and the description of the pull request lists the files in a table of their own.
