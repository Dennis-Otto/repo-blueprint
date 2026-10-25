# The issue of flaky tests counts in its body, and a marker names other tests

- Status: accepted
- Date: 2026-10-25

## Context

The flaky-test bot reports each run that passed when it ran again in the one issue of flaky tests, with a table of the jobs that failed at first: the step that broke, the tests that pytest names in the log, and the first error. Two things were missing.

- **No running count.** Each run added a comment, and the body of the issue stayed as the first run left it, so seeing which job or test flakes most meant reading every comment.
- **No test for logs that are not from pytest.** The Docker E2E of ha-autodarts runs browser tests, whose log names each step as it starts with `Browser step: …`. When Safari timed out in `Page.goto` (Dennis-Otto/ha-autodarts#223), the Test column stayed empty and the error was only the exit code of the job.

The bot runs after the checks, without a checkout and with no right to read the contents of the repository, and the names and logs of a pull request reach what it writes.

## Options

For the count:

1. Count anew from every comment of the issue on each report. The bot would parse its own tables back, in which a test can hold the comma that separates the tests, and anybody who comments on the issue writes into what it parses.
2. Keep the table of the counts in the body of the issue, between two comments of the bot, and rewrite it on each report from what it holds and the jobs of the run.

For the tests of other logs:

1. A key in `.github/repository.project.toml`, read when the bot runs. The job would need the right to read the contents of the repository, and one more request on each report.
2. An answer of Copier, `test_marker`, which the template writes into the workflow, as `test_workflows` names the other workflows of tests.

## Decision

Option 2 for both.

- **The count:** the body of the issue holds a table "Job | Test | Times | Last run", one row for each job, with the name of its workflow, and each test that the run names, the latest first, and each run gets a comment of its own with its table, as before. The bot rewrites only the lines between its two comments, adds them to an issue that has none, and keeps the 100 latest rows, well within the 65,536 characters of a body. The cells are code, as in the table of a run, so a pull request can't end the table with a name or a line of its log, and the bot reads back only the rows that it wrote. Two reports at the same moment may miss a count; neither misses its comment, which comes first.
- **The marker:** the answer `test_marker`, such as `Browser step:`, is the text that the log writes before the name of each test or step as it starts. When pytest names no test, the bot takes the line that names the marker last before the first error of the log, wherever in the line the marker stands, as the name of a container that Docker Compose puts first, and the name after it as the test, without the seconds that a step adds when it names itself again as it passed. Only the lines of the step of the job that failed count, from its `##[group]Run` line on, so a marker of an earlier step that passed names no test. Workers that run side by side, such as the two of each job of browser tests of homedarts-for-autodarts, put a prefix of their own before each line, such as `[1/4]` and a space: the first exception before the error belongs to the worker whose prefix it starts with, and the bot takes the last marker of that worker, not of one that went on and passed. Without an exception, the last marker of any of them counts. The first exception after that line, such as `playwright._impl._errors.TimeoutError: …`, is the error when no annotation names one. The validator keeps the answer to letters, digits, spaces and `: ( ) . _ / # > = -`, since it goes into a string of YAML in the workflow.

## Consequences

The body of the issue shows at a glance how often each job and test flaked and when it last did; the comments keep the details of every run. An issue that the bot opened before keeps its text and starts to count with the next run.

A repository whose tests are not pytest names its failed test with one answer, `copier update --data "test_marker=Browser step:"`, and its tests write the marker before each test or step. A log that names a step in another way, or writes no line before a test, gives no test, as before. The test of such a log is the step that started last in the worker that failed, also when the failure came after it had passed, before the next one started.
