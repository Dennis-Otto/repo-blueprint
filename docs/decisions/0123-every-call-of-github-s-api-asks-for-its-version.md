# Every call of GitHub's API asks for its version

- Status: accepted
- Date: 2026-11-08

## Context

GitHub versions its REST API by date. A request names its version in the header `X-GitHub-Api-Version`, and one without it gets the version that GitHub serves by default, which is `2022-11-28` today. On the day that GitHub makes a newer version its default, such a request gets other answers, with no change in the repository that sends it, and a bot finds out in a failed run.

The issue assistant asks for `2022-11-28` on every call ([Dennis-Otto/issue-assistant#239](https://github.com/Dennis-Otto/issue-assistant/issues/239)). The blueprint didn't: its workflows, which every repository gets, called `gh api` 110 times in 18 files without the header, and so did the Python of the blueprint, at the runners of `Api` in `blueprint/github.py`, which most of it calls, and at three places that start `gh api` themselves ([#690](https://github.com/Dennis-Otto/repo-blueprint/issues/690)).

## Options

1. **The header in the `env:` of each step** that runs `gh api`, as the issue assistant does for the two workflows of its own: 40 steps, and a new step that calls the API lacks it until someone adds it.
2. **The header in the `env:` of each workflow** that calls `gh api`, beside `GH_TELEMETRY`, which every workflow that runs the GitHub CLI already sets there ([decision 0080](0080-jobs-with-secrets-or-tokens-that-write-block-every-host-they-dont-need.md)): one line in each of the 18 files, and every step of the workflow has it.
3. **A wrapper** of `gh`, such as a function or an alias of `gh alias set` in each step, which adds the header: the GitHub CLI has no setting for a header of every call, and a wrapper hides what a step sends from someone who reads it.
4. **Nothing:** the default stays `2022-11-28` until GitHub changes it.

## Decision

Option 2.

- **Workflows.** Each workflow that calls `gh api` sets `API_VERSION_HEADER: "X-GitHub-Api-Version: 2022-11-28"` in its `env:`, and each call asks right after `gh api`: `gh api --header "$API_VERSION_HEADER" …`, GraphQL as well, so that one rule holds for every call. The value is no secret, and an action of a step that reads it learns nothing.
- **Python.** `blueprint/github.py` holds `API_VERSION` and `API_VERSION_HEADER`. `gh_command()` puts the header at the end of each call of `gh api`, and both runners of `Api` start gh through it; `blueprint/bootstrap.py`, `blueprint/app.py` and `dashboard.py` end their own calls of `gh api` with it.
- **Tests.** `tests/test_template.py` fails on a call of `gh api` without the header, or in a workflow whose environment doesn't set it to `API_VERSION_HEADER` of `blueprint/github.py`, in the blueprint and in each kind of project. `tests/test_api_version.py` reads the Python of the blueprint with `ast` and fails on a call of `gh api` that doesn't end with the header, and on a second place that starts gh with any arguments. The gh of the tests of the steps, and the simulated shells of `blueprint.py create` and of the release app, refuse a call of `gh api` without the version.
- **The copies of the issue assistant's workflows** stay as the issue assistant makes them: it keeps them, and its own tests check its calls.

## Consequences

A newer default of GitHub changes no answer of a bot. The move to a newer version is one change: `API_VERSION` in `blueprint/github.py` and the line in each workflow, which the test keeps equal, after a read of the breaking changes of that version. The calls are longer by the header. The workflows that a project adds of its own aren't the blueprint's to check: such a workflow asks for the version the same way.
