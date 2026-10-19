# The reference of the questions, variables and secrets is written from its sources and committed

- Status: accepted
- Date: 2026-10-19

## Context

The 25 questions of `copier.yml` had their help only in Copier, and the variables and secrets of the workflows, such as `ISSUE_ASSISTANT_AI`, `UPSTREAM_AUTOMERGE` or `ANTHROPIC_API_KEY` as the alternative to `CLAUDE_CODE_OAUTH_TOKEN`, were documented only in the comments of the workflows, many not at all: the README named `RELEASE_AUTOMATION_CLIENT_ID`, which 14 workflows read, but not what it does or what happens without it. A page written by hand would fall behind with the next question or variable, as the hand-written pages about the releases of three repositories did before the page *Automation* ([decision 0045](0045-every-website-shows-its-automation-written-from-its-workflows.md)).

## Options

1. Pages written by hand: they fall behind their sources.
2. Pages that a hook of the website writes at every build, as the page *Automation*: always current, but they exist only on the website, not in the repository, where the GitHub app shows the documentation and where a pull request shows what its change of a question does to the page.
3. Pages that a script writes from their sources into `docs/reference/`, committed, with a test that fails while a page differs from what the script makes of its sources.

## Decision

Option 3: `reference.py` writes `docs/reference/questions.md` from `copier.yml`, with the help, the type, the choices, the default, the condition and the answers that Copier refuses of each question, the values that Copier works out and the files of a project, and `docs/reference/variables.md` from `.github/workflows/` and `template/.github/repository.toml.jinja`, with who sets each variable and secret, its environment, the workflows that read it and which repositories have them, and the sentences of their comments that name it. What a variable or a secret is for comes from `ABOUT` in `reference.py`, in the words of a user, since many have no comment; a name without a description there, and a description of a name that nothing uses any more, stop the script. `tests/test_reference.py` fails while a committed page differs from its sources, as `tests/test_pins.py` does for the checksums of the downloads.

The reference belongs to the blueprint's own website, beside the questions and answers, the troubleshooting and the architecture; the template brings none of it, since the questions and the variables are those of the blueprint.

## Consequences

Every question, variable and secret is described on the website and on GitHub, and can't drift from its source: a pull request that adds a question or a variable runs `python3 reference.py` and shows the change of the page in its diff. A new variable or secret needs a sentence in `ABOUT`, which the test asks for. A failing test is fixed by a command, but the fix bot doesn't run it yet, because its commands belong to the steps of `scripts/check.sh`, which every repository shares, and this check is the blueprint's alone.
