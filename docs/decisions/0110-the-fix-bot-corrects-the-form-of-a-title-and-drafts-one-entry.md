# The fix bot corrects the form of a title and drafts one entry of the changelog

- Status: accepted
- Date: 2026-11-02

## Context

Two checks of the workflow *Pull request title* failed for a reason that a machine can often see through. A title in the wrong form, such as `Feat: add a dark mode`, made a person read an explanation to change one letter. A `feat`, `fix` or `perf` without an entry made a person write a file with a heading and a line, often the words of the title once more. The PR coach already suggested a title, and the guide for the changelog already says how a fragment looks, and yet each cost a round trip.

The fix bot of [decision 0023](0023-pull-requests-fix-themselves.md) couldn't take these on, for three reasons. The check of the title runs on `pull_request_target` and nothing of a pull request, so it has no fixer and keeps no artifact. The title of a pull request decides the next version, so a bot that changes it can change what a release promises. And the bot adds no file: it takes files that a check kept as data, which come from the code of a pull request, and lets through only those that the commit has already.

## Options

1. Leave both to the explanation. Nothing to build, and the round trip stays.
2. Let the bot run a fixer inside *Pull request title*. That job holds a token that can write, runs on the event of a pull request, and would need the release app there as well; decision 0023 keeps such a token away from any job of a pull request.
3. Let the check keep an artifact `fixes-*` with a new file, and let the bot accept new files in `changelog.d/`. Every artifact comes from a run that a pull request can influence, so this opens the rule "it never adds a file" to whatever such a run writes.
4. A job of its own after the checks, which reads the pull request from the API and builds the title and the fragment itself. The rule for artifacts stays as it is, and the exception holds only for what `blueprint.py` of `main` wrote in that job.
5. The same, with any title that the PR coach suggests. This is the most help, and it lets a bot choose the type that decides the version.

## Decision

Option 4, on a pull request from a branch of the repository only. A pull request from a fork keeps what it had: the PR coach suggests its title and says what its entry needs.

- **Only the form of a title:** the job `own-branch` of `after-checks.yml` starts after a failed run of *Pull request title*, and `blueprint.py fix own` sets the title that the PR coach suggests only when the title marks its first word as its type, by a colon, a dash with a space before it, brackets that close right after it, a scope or a breaking mark, and that word is the name of a type. So `Feat: add a dark mode`, `[docs] a guide` and `fix(UI)! drop the old look` are corrected. A word for a type, such as `Feature:`, a sentence, such as `Fix the crash` or `test-driven development`, a title with a tag of its own, such as `[Test PR] feat: x`, a title that names a second type, such as `[fix] feat: x`, and a title without words stay suggestions. A first letter stays a capital in a name, such as `GitHub` or `Home Assistant`. The breaking mark stays where it stands, and a corrected title passes the pattern of the check, so the check doesn't fail again for it. The test that says so generates titles.
- **Exactly one new file, built by the bot:** a change for users of a person, without an entry of its own, gets a draft as a new file `changelog.d/<branch without its type>.md`, with the ending `-2` and so on where the commit or its base branch has that fragment already, and with a heading of its kind: `Features`, `Bug fixes`, `Performance`, or `Breaking changes` for a breaking mark. No artifact and no file of the pull request reaches it: its name comes from the branch, reduced to the letters of a fragment, its text from the title. The function that lets fixes of the checks through still refuses a new file, also one in `changelog.d/`.
- **The check and the bot decide alike:** which pull request needs an entry stays in the shell of the check, where it has always been, and `needs_entry` says the same in Python. A test runs both on the same pull requests.
- **Words, not more:** a title with `<`, `@`, `](`, `://` or `www.` gets no draft, because the fragment becomes a page of the website and the notes of a release, where these would be HTML, a mention or a link.
- **Fail closed, and never against a wish:** the bot draws on what the API says at that moment, stops when the commit is no longer the head, leaves a pull request with the label `no-bot-fixes` alone, and commits onto the head that it read, so a push in between wins.
- **One draft for each pull request:** the commit has a headline of its own, *docs: draft the entry of the changelog from the title*. The bot looks for that headline among the commits of the pull request and drafts no second time, so whoever deletes the draft keeps it deleted, and the check explains. The headline also keeps the draft out of the count of the fix bot: that bot makes at most two commits in a row, and a draft is no round of its fixes.
- **The token only when there is work:** the first step decides with the token of the job, and only a fix asks for a token of the release app, with what a title and one commit need. A token of the release app is what makes the check run again, as a token of a job starts no workflow.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/the-title-and-the-entry-fix-themselves.dark.svg">
  <img src="../images/diagrams/the-title-and-the-entry-fix-themselves.svg" alt="The title and the entry fix themselves: The check of the title fails. A pull request from a fork, or one with the label no-bot-fixes, stays as it is, and the PR coach explains. On a branch of the repository, the bot reads the pull request from the API. A title that names its own type and differs only in its form becomes the one that the PR coach suggests; any other stays a suggestion. When that title is a feat, fix or perf of a person with no entry of its own and no draft before, the bot commits one new file of changelog.d that it names and writes itself, and the report asks to read it. A corrected title or a draft starts the check again, which finds it fixed. What is left stays with the PR coach.">
</picture>

## Consequences

A mistake in the form of a title, and a forgotten entry, no longer stop a pull request of a branch of the repository: the check turns green within a minute or two. The entry that it adds is only as good as the title, so a release can carry a line that a person never rewrote: the report of the PR coach asks to read the draft, and the entry shows in the part of the report that names what the pull request adds to the changelog, but nothing forces it. A team that wants every word written by hand adds the label `no-bot-fixes`.

The rule of decision 0023 that the bot adds no file now has this one exception, and only for a file that `blueprint.py` of `main` names and writes. The commit moves the head of the branch, so the checks of the older commit stop and run again, once in the life of a pull request, which also costs a person who hasn't pulled one more pull. A push wins against the bot, and the bot then looks at the new head when its check fails again.

The check of the title and `needs_entry` each say which pull request needs an entry, in shell and in Python, because the shell also writes the annotations of the check and the bot must run with no pull request's code. A failed run for unsigned commits starts the job for a few seconds as well, which then finds nothing to do. The `/fix` of a maintainer on a fork stays open in [#429](https://github.com/Dennis-Otto/repo-blueprint/issues/429).
