# The mutation tests run in parts, list the logic first and open an issue when the score drops

- Status: accepted
- Date: 2026-10-18

## Context

The weekly mutation tests ran every mutant of a project in one job and reported the score and the first 30 surviving mutants by name, and a low score failed nothing:

- **One job is too short for a large project:** mutmut runs about half a mutant a second on the four cores of a runner when each mutant starts slow tests, as in the integration of ha-autodarts. Its 9,000 mutants would take five hours and more, beyond the 320 minutes that the workflow gives mutmut, so the project limited `only_mutate` to a third of its code.
- **The survivors that matter hid:** in issue-assistant, 476 of 909 survivors changed only a text, 26 the help of an option and 233 passed None or left out an argument; 174 changed the logic. The summary listed the first 30 by name, all from one function, and none with its change, which only `mutmut show` prints, in the copy of mutmut that the job throws away.
- **Nobody saw a run that measured nothing, or a drop:** when the tests fail in mutmut's copy of the repository, `mutants/`, no mutant runs, and the summary showed the last words of mutmut, not the test. A score that fell from one week to the next showed only on the dashboard.

## Options

1. One job, as before, with a longer time for mutmut. A job of GitHub ends after six hours, so a large project still can't finish, and a run of five hours holds a runner of the account all morning.
2. Parts by module or by function, each a job of a matrix, the plan by an estimate of the mutants of each function, and a report that puts the parts together; the kind of each survivor from its change; one issue when the score of the default branch drops.
3. Mutation tests only of the code that a pull request changes. They find a gap where it is made, but each pull request would wait for minutes of mutmut, and the weekly run is still needed for the score.

## Decision

Option 2.

- **The plan** (`blueprint.py mutation plan`) estimates the mutants that mutmut 3 makes of each function, from the syntax tree: three of a text, one or two of a number, an operator, a comparison, an assignment or a condition, one of each argument of a call and one for leaving it out. It splits the code into parts of about 3,000 mutants, at most eight, whole modules first and the functions of a module that is larger than a part, and names the mutants of each part as `mutmut run` takes them. The estimate lies within about a fifth of what mutmut makes; the variable `MUTATION_PARTS` of a repository sets the number of parts when it misjudges. Each part runs mutmut on all the tests, as before; its stats and its copy of the code cost each part a few minutes.
- **Each part** keeps the status of its mutants and the change of each survivor, which `mutmut show` prints only in the job, and names the tests that failed without any mutant when none ran: pytest reports them, and mutmut stops before the first mutant. Such a part fails its job, so that the bot-health bot opens its issue.
- **The kind of a survivor** comes from its change, token by token: only a text, unless a comparison reads it; a value that becomes None, or an argument left out of a call; otherwise the logic. The summary lists the survivors of the logic first, by function, each with its change, and tables of the functions of the others; the *score of the logic* counts only the survivors of the logic.
- **A drop opens one issue:** a complete run of the default branch, every part reported and none at its time limit, is compared with `mutation.json` of the run before, from its artifact, which now stays for 90 days. When the score or the score of the logic falls by more than half a point, the issue *Mutation score dropped* opens, with the label `maintenance` and the run before the drop in its marker; it closes once a run is back at that score. A small tolerance keeps a mutant that hits its time limit in one run from opening it.
- **No mutation tests in pull requests** that change only the code: option 3 stays for later, as the same parts with the names of the changed functions.

## Consequences

A large project finishes its weekly run within the limits of GitHub, in about an hour with four parts at a time, and the summary starts with what a test should catch. A run that measures nothing names its tests, and a drop of the score reaches the maintainer as an issue instead of a line on the dashboard. Each part repeats the stats of mutmut, so a run of several parts takes more runner minutes than one job would, and up to four runners at a time on Saturday morning. The estimate follows mutmut 3.8; a later mutmut that makes other mutants changes only the size of the parts, not their results.
