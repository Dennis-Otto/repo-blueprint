# Every tool of the checks shows its findings at their lines

- Status: accepted
- Date: 2026-10-25

## Context

The PR coach ([decision 0022](0022-every-check-explains-its-failure.md)) lists what a check that failed found from the annotations of its check run, and the files of a pull request show each annotation at its line. Only some tools of `scripts/check.sh` wrote annotations, and two promises of the coach were still open ([issue #200](https://github.com/Dennis-Otto/repo-blueprint/issues/200)):

- **Most findings stayed in the log.** The text files, Ruff and actionlint annotated their findings, and in the CI so did Psalm, Biome and the compiler of TypeScript, the last through the problem matcher of actions/setup-node. ShellCheck, mypy, pytest, PHP CS Fixer, PHPUnit and the tests of Node wrote only to the log, so the coach could say no more than that the step failed, and a reviewer looked for the line in the log.
- **The taint analysis of a Nextcloud app passed in the CI.** Psalm 6 ends a taint analysis that writes a report with 0 in a workflow of GitHub, which it tells by `GITHUB_WORKFLOW`, for the action that uploads the report to code scanning. The step *Psalm taint analysis* writes the report of code scanning, so a path of untrusted input to a sink passed the required check and showed only in code scanning.
- **No step checked the explanations.** `blueprint.py coach verify` listed each required check and each step of `scripts/check.sh` without an explanation, but only a test of the blueprint failed on it: a project could require a check, or add a step, that the coach couldn't explain. Every repository of the blueprint now explains its checks.

## Options

1. A problem matcher of GitHub for each tool, a file of JSON with a regular expression that the runner applies to the log. It needs no code, but a matcher reads one line or a fixed sequence of lines: it can't count the lines of a diff, take the place of an error from the trace of a test, or leave out a file outside the repository, and it applies to every line of the log until it is removed.
2. A reporter of each tool for GitHub, where the tool has one. ShellCheck, mypy, pytest, PHP CS Fixer and PHPUnit have none, and a plugin of pytest or of PHPUnit would be a dependency of every project.
3. One command of the blueprint that reads what each tool writes, or its report of JUnit, and writes the annotations, with a test against the real output of each tool.

## Decision

Option 3. `blueprint.py annotate TOOL` (`blueprint/annotate.py`) runs in the CI only, with the Python and `blueprint.py` of the step *Pages in one column*:

- **What a tool writes passes on as it is.** For ShellCheck (`--format=gcc`), mypy (`--no-pretty --show-error-end`, one line for each finding with where it starts and ends), PHP CS Fixer (its diff, one annotation for each run of lines that it changes, with the lines that it writes) and the tests of Node (the list of the spec reporter at its end), the command reads the output of the tool from a pipe, passes each line on to the log at once, and writes the annotations in a group of the log after it. The exit code of the step stays that of the tool: a line that the command doesn't understand is no finding, and a parser that stumbles leaves the annotations out and passes the rest of the log on.
- **The tests from their report of JUnit.** pytest (`--junitxml` with `junit_family=xunit1`, which names the file and the line of each test) and PHPUnit (`--log-junit build/phpunit.xml`) write a report, which the command reads after a test failed: each failure or error is an annotation at the place of the trace in the repository where it happened, or else where the test starts.
- **Safe with any pull request.** The output of a tool is that of the code of a pull request, also from a fork. A finding names a file only when it is a file of the repository outside the folders of packages, such as `vendor/` and `node_modules/`, and every property and message is escaped as a workflow command needs it, so that no text ends its command or starts another one. Colors of a terminal are left out, and a message is cut at 2,000 characters.
- **Psalm fails on every path.** The step *Psalm taint analysis* runs Psalm without `GITHUB_WORKFLOW`, so that a path fails it in the CI as on a machine; the CI still uploads the report to code scanning.
- **Every check explains itself, or the checks fail.** The new step *Explanations of the checks* of `scripts/check.sh` runs `blueprint.py coach verify`, in the blueprint and in every repository made from it.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/how-the-findings-of-a-tool-reach-their-lines.dark.svg">
  <img src="../images/diagrams/how-the-findings-of-a-tool-reach-their-lines.svg" alt="How the findings of a tool reach their lines: A push to a pull request, also one from a fork, runs scripts/check.sh in the CI. Ruff, Psalm and Biome write their findings as annotations on their own, and the TypeScript compiler through the problem matcher of actions/setup-node. ShellCheck, mypy, PHP CS Fixer and the tests of Node write lines that blueprint.py annotate reads and passes on to the log as they are, and pytest and PHPUnit write a report of JUnit that it reads after a test failed. blueprint.py annotate writes one annotation for each finding, at a file of the repository only and with every text escaped. GitHub keeps the annotations of the check run, the files of the pull request show each finding at its line, and the PR coach lists them in its one comment.">
</picture>

## Consequences

A finding of every tool of `scripts/check.sh` shows at its line in the files of a pull request, and the comment of the PR coach lists the first ten of a check with their files and lines; GitHub keeps ten errors of a step, and the coach writes its own explanation of a step as a notice, which these don't push out. A run on a machine prints what it printed before. The coverage summary and the suggestions of the fix bot for a fork, which issue #200 asked for as well, came with decisions [0030](0030-one-report-on-each-pull-request.md) and [0023](0023-pull-requests-fix-themselves.md).

The command knows the formats of the tools that the blueprint sets up. A project that changes the reporter of its tests, such as the spec reporter of Node in `package.json`, keeps its checks and loses only the annotations of its tests. A taint analysis that finds a path now fails the CI of a Nextcloud app, as it already failed `scripts/check.sh` on a machine. A project that requires a check without an explanation fails its checks until it explains it in `.github/checks.project.toml`.
