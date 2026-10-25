# Mutation tests, fuzzing and property tests

The tests beyond the checks of a pull request: whether the tests notice a change of the code, and inputs that nobody wrote down.

## Mutation tests

Every week, thousands of small changes of the code run against the tests, a large project in parts of one job each, and the summary shows the share they notice and first the survivors that change the logic, with their changes; a low score is a report, never a failure, but a drop of the score of main opens one issue, and a run that measures nothing fails with the tests that fail without any mutant; a pull request that changes how they run tries them.

**How:** `mutation.yml`: mutmut, Infection.

The mutation tests show the lines that the tests run but don't check: every Saturday they change the code in thousands of small ways, the mutants, and run the tests that cover each one. A mutant that no test notices survives.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/how-the-mutation-tests-run.dark.svg">
  <img src="../images/diagrams/how-the-mutation-tests-run.svg" alt="How the mutation tests run: Every Saturday, on demand, and for a pull request that changes how they run, the Mutation workflow runs the mutants. For Python, the plan splits the code into parts of about the same number of mutants, and mutmut runs each part in a job of its own, in a copy of the repository and without the tests marked mutation_unsafe; Infection changes the PHP of a Nextcloud app, with the bootstrap of its tests. The summary shows one score and first the survivors that change the logic, with their changes, the artifact keeps them and the dashboard shows the score. When the score of the default branch drops below that of the run before, one issue opens, which closes once a run is back. A run that measured nothing fails and names the tests that failed without any mutant.">
</picture>

- **The score is the share of the mutants that a test noticed,** among those of the code that the tests run: for mutmut the killed among the killed and the survived, for Infection its *Covered Code MSI*. The dashboard shows it as *mutants caught*.
- **The survivors that change the logic come first:** the summary sorts each survivor of mutmut by its change, as `mutmut show` prints it. First come those that change the logic, an operator, a comparison, a number or a condition, which a test should notice, by function, the most first, each with its change; then a table of the functions whose survivors pass None or leave out an argument, and one of those that change only a text, such as a message, a help or a log line. The *score of the logic* counts only the survivors of the logic, and `survivors.md` of the artifact *mutation* has the change of every survivor. A line whose text no test needs to check gets `# pragma: no mutate`, and mutmut leaves it alone.
- **A large project runs in parts:** the job *plan* estimates the mutants of each function and splits the code into parts of about 3,000 mutants, at most eight: whole modules, and the functions of a module larger than a part. Each part is a job of its own that runs only its mutants, so that a project of 10,000 mutants finishes within the six hours of a job of GitHub, and the job *report* puts the parts together into one score. The variable `MUTATION_PARTS` of the repository sets the number of parts in place of the estimate.
- **A drop of the score opens one issue:** the report compares a complete run of the default branch with the run before it, from `mutation.json` of its artifact. When the score or the score of the logic falls by more than half a point, it opens the issue *Mutation score dropped*, with both scores and the functions that gained survivors of the logic, keeps it current while the score stays below, and closes it once a run is back at the score before the drop. A run that stopped at its time limit or lost a part is compared with no other.
- **A low score fails nothing,** not even below a minimum that the project's own configuration sets, but a run in which no mutant ran does: mutmut runs every test once without a mutant first, and when one fails there, the summary names it under *The tests fail without any mutant*, with the end of the output of mutmut or Infection, and an annotation of the job names the first one, which the bot-health bot quotes in its issue. A broken configuration or a test that can't run in the copy shows up in the week it breaks, and the bot-health bot opens its issue.
- **A pull request that changes how the mutants run,** `mutation.yml` or the pinned mutmut, tries them, each part for 25 minutes, and shows a defect as a red check before the weekly run. The check isn't required, so a pull request that merges itself, such as an update of mutmut, doesn't wait for it: its red check is a warning to read.
- **mutmut runs the tests in a copy of the repository,** `mutants/`, with the changed code and without Git. A test that can't work there, because it reads the code as text, asks Git or starts the tool, which in the copy is the code with the mutants, gets the marker `@pytest.mark.mutation_unsafe`, and the mutation tests leave it out. So does a test that copies a module of the code into a repository of its own and runs it there, such as `pins.py` for the fix bot: outside of `mutants/`, the code with the mutants finds no configuration of mutmut, and a test of the blueprint fails when such a test of the blueprint lacks the marker. The `pyproject.toml` of a new Python project registers the marker, and `MUTANT_UNDER_TEST`, which mutmut sets, tells a test that it runs there. mutmut learns which tests cover a function by running them all in one process: a test of a function with a cache of `functools`, such as `@functools.cache`, clears it with `cache_clear()`, so that it runs the code and not the result that another test left.
- **mutmut copies a whole function for each of its mutants,** so a long function with many of them, such as a parser with the options of every command, makes a module of many megabytes, which each part and every test that starts the tool in the copy compile for minutes, past their time limits. Such a function is split into smaller ones: the parser of `blueprint.py` adds each group of its commands in a function of its own, and a test of the blueprint fails when a function of its code would make more than 50,000 lines of copies.
- **A configuration of the project wins:** a `[tool.mutmut]` table in `pyproject.toml` or a `[mutmut]` section in `setup.cfg` for mutmut, an `infection.json5` for Infection. Without one, mutmut mutates `custom_components/`, `src/` or the modules and packages of the root, and Infection mutates `lib/` on PHP 8.3, with `tests/bootstrap.php`, which loads the classes of Nextcloud. The plan follows `source_paths`, `only_mutate` and `do_not_mutate` of mutmut.

## Fuzzing

For a Python package or a GitHub Action: coverage-guided fuzzing of every target in `fuzz/`, a minute each in every pull request that changes the code, the targets or the tools, and every week 25 minutes shared by all targets; a finding fails the run, with the input that caused it in the log.

**How:** `fuzz.yml`: Atheris.

## Property tests

In Python and Home Assistant projects: the property tests with new random inputs every night, beyond the fixed inputs of the CI; a failure shows its seed in the summary, and a run by hand with that seed replays it.

**How:** `properties.yml`: Hypothesis.
