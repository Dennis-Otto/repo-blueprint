# Every step of a bot that changes something on GitHub runs in a test

- Status: accepted
- Date: 2026-10-18

## Context

Most bots of the blueprint are bash in the `run:` of a step: at commit d4dd981, 2,530 lines in 31 workflows. They delete branches, start workflows, merge pull requests, publish releases, move tags and comment, with the rights of the release app or of the token of the run, in every repository that takes the blueprint. 32 steps change something on GitHub, and 17 of them ran in no test: the clean-up bot that deletes the branches that `main` holds, the release bot that merges a release of dependency updates, publishes a beta and the release and moves the major tag of an action, the picture bots that delete and move their branches and merge their pull requests, the merge of Dependabot's updates, the labels of a title, the issue of broken links, the post of the weekly report and the welcome of a first pull request. Their tests asserted parts of the text of the workflows, so a guard that changed, such as the one that deletes a branch only when `main` holds all its commits, stayed green. The steps that did run in a test each had a fake gh of their own, six by then.

## Options

1. Move every bot into `blueprint.py`, in Python with every line and branch covered. That is right for a large bot, and several have moved, but the steps that glue them to GitHub stay bash, and a move is a change of its own for each bot.
2. Run the steps as they are, in bash, with one harness and one fake gh for every test, and a census that finds each step that changes something and fails while it runs in no test.
3. Run the workflows with act in Docker. It needs Docker and a runner image for each test, takes seconds for each step and talks to a real API, which the tests would have to fake at the network.

## Decision

Option 2, and option 1 still for a bot that grows.

- **`run_step()` of `tests/workflow_steps.py` runs a step as GitHub does:** its script from the parsed workflow, in bash with the options of its shell (`-e`, and `pipefail` for `shell: bash`), in Git Bash on Windows, in folders of the test for the workspace, or a checkout that the test made, and `$RUNNER_TEMP`, and with the files of the summary, the outputs and the environment, which it reads back. The variables of the step, its job and its workflow come from `env:`: a value without an expression as it is, a known context such as `${{ github.repository }}` as the runner sets it, and every other one from the test, which fails when the script reads one that it doesn't give. A script with an expression of its own fails, since the bots hand every value over as a variable.
- **`tests/fake_gh.py` is the gh of every such test.** It answers a call whose arguments match an answer of the test in full, with its output and exit code, or with JSON through the filter of `--jq`, as gh prints it; an answer can answer one call, so that the next one answers the next. A call without an answer fails, as an unexpected call of the real gh would do harm, and every call is written down with what gh read for it, such as the file of `--body-file`.
- **A census in `tests/test_workflow_steps.py`** finds every step whose script deletes, starts, merges, publishes, pushes, comments or writes through the API, and lists each with the file of the tests that runs it. A new such step fails the census until a test runs it, a step that is gone or changes nothing any more fails it as well, and the test file has to name the step.
- **The structure of a bot,** such as its rights and its condition, is read from the parsed workflow in these tests, not from slices of its text: `parse()`, `job_in()`, `step_in()` and `condition_of()` of `tests/workflow_steps.py` give a job, a step and the condition of either. A slice of the text can hold a line of another job or of a comment, and a check of it passes on a wrong workflow.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/how-a-test-runs-a-step-of-a-bot.dark.svg">
  <img src="../images/diagrams/how-a-test-runs-a-step-of-a-bot.svg" alt="How a test runs a step of a bot: A test names a step of a workflow and plans the answers of gh. run_step reads the step from the parsed workflow, with the variables of the step, its job and its workflow, and runs its script in bash with the options of GitHub, in Git Bash on Windows. gh is the fake gh, which answers each call as planned, fails a call without an answer and writes every call down with what it read. The test checks the calls, the summary, the outputs and the exit code. A census finds every step that deletes, starts, merges, publishes or comments, and fails while one of them runs in no test.">
</picture>

## Consequences

Every step that changes something on GitHub runs in a test, and a changed guard fails one: a clean-up bot that deleted a branch with commits of its own, or a merge bot that merged a release with a feature in it. A new bot step comes with its test in the same pull request. A step whose filter of `--jq` decides what the bot touches, such as the one that leaves out protected branches, has a test that gives the JSON of the API; such a test needs jq, which the runners of GitHub have, on Linux and on Windows, and skips on a machine without it, such as one with Git for Windows alone. Each call of the fake gh starts Python, about 20 milliseconds on Linux and 300 on Windows, and the tests of the steps take a few seconds on every core. The older tests of the diagram bot, the fix bot, the Rollout, the issue assistant's sync, the signing of the release tags, the bots after the checks, the check of the changelog and the blueprint bot have moved onto `run_step()` as well (#288): `tests/fake_gh.py` is the only fake gh of the tests, and no test finds a job, a permission or a condition in a slice of the text of a workflow. A guard in `tests/test_workflow_steps.py` keeps it so: it fails, with the file and the line, on a helper or a slice that cuts a job or a step out of the text of a workflow, and on a test that writes a gh of its own.
