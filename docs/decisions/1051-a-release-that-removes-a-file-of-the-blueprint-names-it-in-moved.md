# A release that removes a file of the blueprint names it in MOVED, and the update points the project's pages at its successor

- Status: accepted, amends [0143](0143-a-step-that-the-changelog-asks-of-an-existing-repository-is-a-migration-a-line-of-the-checklist-or-a-note.md)
- Date: 2026-11-18

## Context

When a release removes or renames a file of the blueprint, the update deletes it, but the files of the project can keep naming it, and an update never changes a file of the project. Release 1.22.0 joined *Secret scan* and *Dependency review* into *Quick checks* ([#1026](https://github.com/Dennis-Otto/repo-blueprint/pull/1026)) and removed `.github/workflows/secret-scan.yml` and `.github/workflows/dependency-review.yml`. Its update merged by itself in all seven repositories that follow the blueprint, and afterwards 18 lines of theirs still named the old files ([#1050](https://github.com/Dennis-Otto/repo-blueprint/issues/1050)): the badge *Secret scan* of nine READMEs, whose picture and link answered 404, two links of a page, and the first line of each `.github/dependency-review.yml`.

Nothing noticed. The entry of the changelog said it in its last sentence, which nobody reads at night. The link check passed on the update and on `main`, from its cache, and leaves every badge picture out. Downstream listed the files that the update changes, not the lines that name a file that it deletes. [Decision 0143](0143-a-step-that-the-changelog-asks-of-an-existing-repository-is-a-migration-a-line-of-the-checklist-or-a-note.md) already asked for a migration or a line of the checklist, but no test held a pull request to it, and #1026 brought neither.

## Options

1. **Only a report in the body of the update.** The bot of `main` could list the lines from the files that the update deletes, but nobody reads the body before the update merges, and it fixes nothing.
2. **Only the changelog and the rule, as before.** Both were there in 1.22.0, and nothing happened.
3. **Only the link check.** Its weekly run reports the link of a badge within a week, after the broken badge is public, never its picture or a comment, and each repository still needs a pull request by hand.
4. **A list of the removed files in the release, a guard that keeps it complete, and a fix of the project's pages by the existing migrations.**

## Decision

Option 4.

- **The list:** `MOVED` of `blueprint/migrate.py` maps each file of the blueprint that a release removed to the file that took its place, or to `None` when nothing did. An entry stays, so a repository that updates later, from any version, gets the fix too.
- **The guard:** the job `update (kind)` of the Variants workflow, a required check, keeps the `owned.txt` of the latest release of each kind before it runs `copier update`, and `migrate --since` then fails for each file that it lists, that the update removed and that has no entry. That is the check that would have stopped #1026. It runs where the release is checked out with every tag, on the real rendering of each kind, so the conditions of `owned.txt.jinja` need no rule of their own. A file that leaves `owned.txt` but stays in the project has become one of the project and needs no entry.
- **The search:** `migrate` reads the files of the project that Git tracks, without those of `owned.txt`, which the update writes, and without `CHANGELOG.md`, `changelog.d/` and `docs/decisions/`, whose history rightly names an old file. It runs only where `.github/blueprint/owned.txt` exists, so not in the blueprint, whose tests name the old paths on purpose. It finds the path itself, also in the address of this repository at `main` (`blob/`, `raw/`, `tree/`, `edit/` and `raw.githubusercontent.com`), and for a workflow the address of its page and of its badge, `actions/workflows/<name>`, which a badge needs because its line never holds the path. A link to a tag, a commit, another branch or another repository stays, and so does a path whose file the project has.
- **The fix:** a page of Markdown outside `.github/` fails the step *Files of the project* and names each line; `migrate --fix` changes only the path, or the name of the workflow, so the words of the project stay, such as the label *Secret scan* of a badge that now shows *Quick checks*. The fix bot commits it onto the update: such a page decides nothing that a workflow runs, so [decision 0142](0142-the-fix-bot-commits-nothing-that-runs-with-rights-where-nobody-reads-its-commit.md) allows the commit, and the writes of the step name `**/*.md`.
- **What it only reports:** a line that the bot may not or cannot change, under `.github/`, in a workflow, in a file that isn't Markdown, or without a successor, is a warning in the log and an open step of `blueprint.py checklist`. It fails nothing, so no update waits for a person over a comment, as option 2 of decision 0143 has it.
- **Declining:** a line that keeps the old name on purpose, such as on a page about the history of the project, says `blueprint: keep` in a comment and is neither changed nor reported.
- **Downstream** runs the search on each repository that it updates, with the entries of the next release too, and lists the lines below each repository, so the author of the pull request sees them before the release.
- **No `--trust`, no `_migrations` of Copier:** the code runs in the checks of the update, as every migration does.

## Two releases

The fix bot of a repository reads what it may write from the catalog of its own `main`, the release before ([decision 0142](0142-the-fix-bot-commits-nothing-that-runs-with-rights-where-nobody-reads-its-commit.md)). So the release that brings this mechanism brings `**/*.md` to the writes of the step and keeps the first entries, the two workflows of 1.22.0, in `MOVED_NEXT`, which the search leaves alone and which the guard and Downstream count. The next release moves them to `MOVED`; from then on a new entry goes to `MOVED` at once, since every repository knows the writes. Without that order, the first update would fail the step on a README that the bot of `main` may not commit, and wait for a person.

## Consequences

- A pull request that removes a file of the blueprint adds its entry, or the job `update (kind)` fails with the path and what to do.
- The lines that #1026 left behind in the projects' pages are fixed by the update to the release after the one that brings this mechanism, if they are still there, and the comment of `.github/dependency-review.yml` stays a step of the checklist until a person changes it.
- The weekly link check stays as it is: it still finds a link that no entry covers.
