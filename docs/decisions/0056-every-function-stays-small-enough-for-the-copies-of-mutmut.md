# Every function stays small enough for the copies of mutmut

- Status: accepted
- Date: 2026-10-19

## Context

mutmut 3 writes each function into its copy of the repository, `mutants/`, once as it is and once more, whole, for each of its mutants, and Python compiles every copy when a test imports the module. `main()` of `blueprint/cli.py` built the parser of every command and then ran the command: 640 lines with about 1,800 mutants, which made `mutants/blueprint/cli.py` 1.25 million lines and 51 MB, two thirds of the whole copy. Each part of the Mutation workflow spent minutes writing that module and more compiling it, and every test that starts `blueprint.py` in a rendered project compiled its own copy again: `test_the_tests_of_a_python_project_run_on_every_core[True]` ran past its 300 seconds, the first run of the tests in the copy failed, no mutant ran, and the Mutation workflow failed on `main` and on every pull request that changed how the mutants run ([issue 219](https://github.com/Dennis-Otto/repo-blueprint/issues/219)).

## Options

1. Mark the test `mutation_unsafe` and raise the time limits: the test passes everywhere else, every part of every run still pays for the module, and the next test that starts the tool fails the same way.
2. Leave the parser out of the mutation tests with `# pragma: no mutate function`: the copy shrinks, but the names, choices and defaults of the options, which the tests check, lose their mutants, and so does the code that runs each command.
3. Split the function: the parser adds each group of commands in a function of its own, and the commands that need neither the settings nor the repository run in a function of their own. A test fails when a function of the blueprint would make more than 50,000 lines of copies, about 2 MB.

## Decision

Option 3. `parser()` builds the command line from ten functions, one for each group of commands, such as `add_mutation_parsers`, and `standalone_command()` runs the commands that need no repository before `main()` makes its client of the API. `tests/test_mutation.py` estimates the copies of each function, its lines times its mutants, with the estimate that splits the run into parts, and names every function above the limit. The limit leaves room for the largest functions of today, about 20,000 lines each, and stops the next one that grows the way `main()` did.

## Consequences

The copy of the blueprint shrinks from about 1.8 to 0.8 million lines, and `mutants/blueprint/cli.py` from 51 to 8 MB. mutmut writes its mutants in seconds instead of minutes, the tests that start the tool in the copy pass within their time, and the parts have their time for the mutants again. A new command goes into the function of its group, or into a new one; a function that grows past the limit fails the test with its name and gets split. The `CONTRIBUTING.md` of every Python project explains why a long function with many mutants is split, and the explanation of a part that measured nothing points to it.
