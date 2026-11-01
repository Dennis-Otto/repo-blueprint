# mutmut collects its stats once for every part, and a pull request tries a sample

- Status: accepted
- Date: 2026-10-25

## Context

Before its first mutant, mutmut runs the whole suite once with trampolines that record which tests reach each function: its stats. Under the trampolines the suite runs about ten times as long as without them. Since the mutation tests run in parts ([0031](0031-mutation-tests-in-parts-with-the-logic-first-and-an-issue-on-a-drop.md)), every part ran these stats again, on the same code:

- **The stats cost more than the mutants:** in issue-assistant, run 40067752188 had six parts of 1,559 to 5,083 seconds, about 16,500 runner-seconds. Each part spent 13 to 21 minutes on the stats of 1,738 tests, which take 70 seconds without mutmut.
- **A failing baseline cost every part:** a test failed in mutmut's copy of the repository at test 1,575, and all six parts found it out on their own, each after its full stats. pytest printed no short summary there, so the summary named no test.
- **A pull request ran every part:** each update of the blueprint that changes `mutation.yml` ran the whole matrix in every Python and Home Assistant repository, which can hold most of the 20 jobs of the account for an hour.

mutmut 3.8 already reuses its stats: `mutmut run` loads `mutants/mutmut-stats.json` when it finds it and runs the stats only for the tests that are new, unless the options of pytest changed.

## Options

1. Keep the stats in each part, and fewer parts. A large project then runs out of the six hours of a job again.
2. One job collects the stats and hands `mutmut-stats.json` to every part; a pull request tries a deterministic sample in one part.
3. Hand over the whole `mutants/` of the stats job, with the generated code. The artifact of a large project holds many megabytes, and every part generates the same code in a minute or two.
4. Keep the stats of the run before in a cache and let mutmut update them. The tests that reach a changed function can change with it, and mutmut keeps their old ones, so the score could drift.

## Decision

Option 2.

- **The job *mutation stats*** runs `mutmut run stats-only`: mutmut has no command for the stats alone, and a run for a mutant that no code has generates the mutants, collects the stats, saves them and then stops, since nothing matches. `blueprint.py mutation stats` reads `mutants/mutmut-stats.json` and writes the summary. The job uploads the file, and each part downloads it into `mutants/` before `mutmut run` with its names.
- **One configuration for both:** `blueprint.py mutation configure` writes the section `[mutmut]` of `setup.cfg` for a project without one, in the stats job and in each part alike, since mutmut collects the stats again when the options of pytest differ.
- **Stats that fail start no part:** the parts and the report wait for the stats, and the job names the tests that failed without any mutant in its summary and in an annotation, which the bot-health bot quotes. Without a short summary of pytest, the frames of the tracebacks of `--tb=native`, which mutmut asks for, name the tests, by their path in the repository.
- **A pull request tries a sample:** `blueprint.py mutation plan --sample` puts about 200 mutants into one part, functions picked in the order of a hash of their names, so that each run of a pull request tries the same ones. The part runs for at most 12 minutes after the stats. The schedule and a run by hand run every part.

## Consequences

A run runs the stats once, in place of once per part: a project of six parts saves five stats of its suite, and a failing baseline costs one job. A part still generates the mutants of all the code, a minute or two of a large project, and runs the tests of its mutants once without one, as mutmut does before the first mutant.

The stats job relies on mutmut collecting its stats before it looks for the mutants to run. A version of mutmut that changes this order saves no stats in that job; the job then fails with the reason in its summary, on the pull request of Renovate that brings that version, since such a pull request runs the Mutation workflow.

A pull request now waits for the stats and the sample, so the check of a project whose stats take longer than about ten minutes still takes more than a quarter of an hour; issue-assistant's stats alone take 13 to 21 minutes.
