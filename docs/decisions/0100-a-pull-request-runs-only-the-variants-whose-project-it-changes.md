# A pull request runs only the Variants whose project it changes

- Status: accepted
- Date: 2026-11-01

## Context

The Variants workflow makes a project from the pull request for each leg and runs its checks with their real tools: a new repository and an update of each kind, and an update with the answers of each repository that takes the blueprint. That is more jobs than the account can run at once, about 20, and every pull request but the release pull request started all of them.

- **Pull requests that no project sees:** #407 changed four pictures under `docs/images/` and ran all 20 legs of that time, 2,078 runner-seconds of jobs.
- **Pull requests of one stack:** #324 changed the lock file of Home Assistant, which only that kind and the answers of homedarts-for-autodarts render, and ran all 20 as well. So did #377, #379 and #383.
- **The critical path:** the Variants are what a pull request waits for longest. In #404 their legs queued for up to 149 seconds for a runner, and 1,484 of the 4,212 seconds of its 37 jobs went to queueing.

The workflow can't tell by the paths of a pull request. The template includes many files from outside `template/`, such as `lychee.toml` and the whole of `blueprint/`, some only for one stack, and a filter of paths that names them all would drift from them unnoticed, and would then skip a leg that a change needs.

## Options

1. Keep running every leg in every pull request.
2. Filters of paths for each kind. They are cheap, but they drift from what the template includes, and a filter that is too narrow skips a check without anyone seeing it.
3. Render the project of each leg from the pull request and from the `main` it merges into, and run the legs whose project differs. Each render takes about a second and runs no code, and it can't drift from the template, since it is the template.
4. Sign the rendered tree of each kind on `main` and look the result up. It needs a store of results, which GitHub's checks don't offer, and saves only the seconds of the renders.

## Decision

Option 3, in a job *variants plan* that the legs wait for.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/how-a-pull-request-picks-the-legs-of-the-variants.dark.svg">
  <img src="../images/diagrams/how-a-pull-request-picks-the-legs-of-the-variants.svg" alt="How a pull request picks the legs of the Variants: A pull request starts the job variants plan, and a run on a schedule, by hand or of the Next runner workflow runs every leg. A change of what every leg runs with, the workflow, Copier, its Python, copier.yml or the plan itself, runs every leg. Otherwise the plan renders the project of each leg from the merge commit and from main; a render that fails runs every leg. A project that differs, or an adopted leg whose answers change, runs its leg; a project that stays the same to the byte skips it, and its reason goes into the summary. The required check variants passes when each leg that ran passed and the plan passed.">
</picture>

- **What a leg can show:** a leg depends on what its project contains and on what it runs with. When the project is the same to the byte and the workflow, Copier and its Python are too, a new run shows only what the tools did since `main` last passed, and the weekly run tries that for every leg anyway.
- **Every leg runs** when a pull request changes `.github/workflows/variants.yml`, `requirements-dev.txt`, `.python-version`, `copier.yml`, or `variants.py` and the `downstream.py` it imports, the plan itself, which must not decide on a change of itself; when a project fails to render, since nothing then shows which legs a change concerns; on the schedule, by hand and in the Next runner workflow, whose run names a runner.
- **An adopted leg runs** when its file of `tests/answers/` changes, whatever the answers render.
- **A plain copy of each commit:** `git archive` gives Copier a folder without a history, which it renders as it is, in about a second, where `--vcs-ref` clones the checkout first and writes a version into the answers. Only the line `_src_path` of the answers differs then, which the comparison leaves out, and the executable bit of each file counts as well.
- **A script of the blueprint alone:** `variants.py` sits next to `downstream.py` and `reference.py`, not in `blueprint/`, whose modules every repository gets, and which has no template to render there.
- **One list of the legs:** `variants.py` makes them from `project_type` in `copier.yml` and from `tests/answers/`, so `reference.py` no longer writes the canaries into the workflow, which holds no list of legs of its own.
- **The required check** stays `variants`. It requires the plan as well, since a plan that fails skips the legs, which would otherwise look like none had to run. The summary of the plan names each leg that doesn't run and why.
- **The pictures** stay as they are: their legs find in their first step whether they are due.

## Consequences

A pull request of documents or tests starts no leg, and a Renovate pull request of one stack starts only the legs of that stack, which leaves the runners of the account to the other checks. A plan adds a job of about half a minute to every pull request, which also installs Copier. GitHub lists a job that its condition skips under the unresolved expression of its name, as it already did in the release pull request; only the required check `variants` counts.

A change that the render doesn't show and that a leg still depends on would skip that leg. The list of such files is short and written down in `EVERY_LEG` of `variants.py`, and the weekly run of every leg finds what slips through it within a week. The update legs also depend on the latest release, which a pull request doesn't change: a new release shows its effect in the next pull request that changes a project, and in the weekly run.

The way back is one step: a plan without `--base` names every leg.
