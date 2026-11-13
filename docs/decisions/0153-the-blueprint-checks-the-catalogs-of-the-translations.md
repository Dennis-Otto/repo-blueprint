# The blueprint checks the catalogs of the translations

- Status: accepted
- Date: 2026-11-13

## Context

Three kinds of projects ship catalogs of translations: a Home Assistant integration (`strings.json` and `translations/*.json`), a Nextcloud app (`l10n/<language>.json` and `l10n/<language>.js`) and a Chrome extension (`_locales/<language>/messages.json`). No check of the blueprint compared them with their source, so each repository of the fleet with a translated interface wrote its own checker, about 1,500 lines with the same rules in four places, as files of the project that no update of the blueprint reaches. A new repository of one of these kinds had none of it: a language that lacks a text, keeps a stale one or loses a placeholder went unnoticed until a user reported it.

## Options

1. Leave the check to each project, in `scripts/check-project.sh`. Every repository keeps writing and fixing the same rules, and a new one starts without them.
2. A step of `scripts/check.sh` for these three kinds, with a command `blueprint.py translations [--fix]` that knows their layouts and checks what holds for every project: every language with the texts of its source and no other, each text with its words and the placeholders of the source, as many forms of a plural as its rule names, and the two files of a catalog of Nextcloud saying the same.
3. The same, and also which texts the code uses. Where a project calls its translations, such as `t()`, `->t()`, `data-i18n` or `__MSG_x__`, differs from project to project, and a scan that guesses wrong fails good pull requests.

## Decision

Option 2. The rules come from the four checkers of the fleet, and the step runs with the Python and `blueprint.py` of the other steps that the CI never skips. `translations --fix` fixes what needs no words: the order of the texts, the stale ones, `en.json` as the copy of `strings.json` and each `l10n/<language>.js` from its `.json`; the fix bot runs it. A text that a language lacks, or whose placeholders differ, needs a person who writes it, so the step names it with its file and line, also as an annotation. What only a project knows, such as the scan of its code for the texts that it uses, stays a step of `scripts/check-project.sh`.

## Consequences

Every new integration, Nextcloud app and extension checks its translations from its first commit, and an update brings the step to the existing ones. Their own checkers can drop the rules that the step now has and keep only what the project alone knows. A catalog that broke a rule before the update fails the step once; the log and `translations --fix` say what to do.
