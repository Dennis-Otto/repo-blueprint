# Every repository checks the numbers of its records of decisions

- Status: accepted
- Date: 2026-11-09

## Context

Two pull requests that each take the next free number for a record of a decision merge without a conflict of Git, since their files have different names. In one night run of November 2026, three pull requests of the blueprint took the same numbers (0127, 0129, 0130 and 0132 clashed), and each one that landed later had to be renumbered by hand. Since [#750](https://github.com/Dennis-Otto/repo-blueprint/issues/750), `tests/test_decisions.py` fails in the blueprint when two records share a number, the numbers skip one, a file of the folder is no record, or the index lists a record twice, misses one, names a file that doesn't exist or lists the records out of order.

Every repository made from the blueprint has a `docs/decisions/` with its own records and index too, and the repositories of the run add records as quickly as the blueprint does: paperless-sync has 37, homedarts 29. They had no such check. The folder belongs to the project (`_skip_if_exists`), so the check has to accept what a project made of it.

## Options

1. **A test in each repository:** a repository of Node, PHP or a container has no Python tests to add it to, and a test of a project would be the project's own file, which no update brings.
2. **A step of `scripts/check.sh`,** which runs a command of `blueprint.py`, as the steps *Changelog fragments* and *Binary files* do: the blueprint keeps it current in every repository, and the CI runs it on every pull request and on `main`.
3. **A check of the fix bot that renumbers the record of the pull request:** which record keeps its number and which one moves is a choice of the authors, a new name of a file is no fix that the bot commits (it changes only files that the commit has), and each link to the record would have to change as well.

## Decision

Option 2. The step *Records of decisions* runs `blueprint.py decisions` with the Python of the step *Pages in one column*, and the code of `tests/test_decisions.py` moved to `blueprint/decisions.py`, so the blueprint checks its own records with the same step.

- **What fails** is what the test of #750 found: a number of two records, a number that the numbers skip, 0000 for another record than the template, a file of the folder that is no record named `NNNN-its-title.md`, and in the index a record twice, a missing one, a file that the folder doesn't have, a row with another number than its file and rows out of order. The log names each number and file and the next free number.
- **What `--fix` fixes** is what only the index gets wrong, and the fix bot commits it onto a pull request: the number of a row, the row of a record whose file was renamed (the one record of the same title that no row names), a second copy of a row, the row of a record that the index misses, from the title and the status of the record, and the order of the rows. A number that two records share stays for the author of the record that moves.
- **What a project keeps:** a repository without records passes, and a folder without an index has only its numbers checked. A folder below `docs/decisions/`, such as one of pictures, is not checked. The records of the seven repositories that follow the blueprint passed the check when it was made.
- **The records of the template,** `template/docs/decisions/`, which no step of the blueprint reads, keep their test in `tests/test_decisions.py`.

## Consequences

The second of two pull requests with the same number fails once the branch bot merges `main` into it, in every repository, before the clash reaches `main`. A missing row or rows out of order fix themselves. A project that wants other names for its records, or files of another kind in the folder, has to follow the names of the template or keep them in a folder of their own.
