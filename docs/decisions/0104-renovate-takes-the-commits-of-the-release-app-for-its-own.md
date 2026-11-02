# Renovate takes the commits of the release app for its own, by a pattern from the name of the app

- Status: accepted
- Date: 2026-11-02

## Context

Renovate rebases a branch and brings it new versions only as long as nobody else committed to it. It compares the author and the committer of every commit between the base branch and its branch with its own address, with the addresses of the rule `gitIgnoredAuthors` and with `noreply@github.com`, the committer of a commit through the API. Any other address makes it take the branch for edited and leave it alone, until a person ticks the box in the pull request. The fix bot ([decision 0023](0023-pull-requests-fix-themselves.md)), the branch bot and the bots of the diagrams and the pictures commit onto its branches, as the release app, whose address looks like `321826887+octo-release[bot]@users.noreply.github.com`. The number belongs to the bot user of the app and differs for every owner, so [#429](https://github.com/Dennis-Otto/repo-blueprint/issues/429) expected a setting or a variable of its own.

We asked the code of Renovate 44.145.1, the one that the workflow pins, with commits of each kind on a real repository:

| Who runs Renovate | Who committed | Renovate takes the branch for |
| --- | --- | --- |
| `hub`, `self`: a Renovate workflow, as the release app | a bot, as the release app | not edited |
| `hub`, `self` | a person, with *Update branch* | edited |
| `mend`: the Mend Renovate app | a bot, as the release app, without a rule | edited |
| `mend` | a bot, as the release app, with the rule below | not edited |
| `mend` | another app, with the rule below | edited |
| `mend` | a bot and a person, with the rule below | edited |

So in a Renovate workflow, which names the address of the app to Renovate with `RENOVATE_GIT_AUTHOR`, the commits of the bots have been Renovate's own all along, and only the Mend Renovate app needs a rule. Since [decision 0051](0051-every-owner-chooses-who-runs-renovate-and-whether-an-ai-reads-the-issues.md), the checklist printed that rule for a person to add, and only until Renovate had opened its first pull request, which the app does in its first run. Whoever missed it found out with the first branch that a commit of a bot left for a person to rescue.

The address can't be known when Copier renders the file, but `gitIgnoredAuthors` takes patterns as well as addresses.

## Options

1. **A setting of its own, with the number,** as an answer of Copier or a variable. A person looks up a number that GitHub knows, and a variable of the repository doesn't reach the Mend Renovate app, which reads files only.
2. **`blueprint.py app register` writes the address into `.github/renovate.json5`,** with the number from GitHub. That file belongs to the project, and a repository that names its app in its answers, without the command, gets no rule.
3. **The rule for every way of running Renovate.** It would change nothing for `hub` and `self`, in the rules of every repository.
4. **A pattern from the name of the app, in the rules of the blueprint, for the Mend Renovate app alone.**

## Decision

Option 4. With the answers `renovate_runner: mend` and a `release_app`, `.github/renovate-blueprint.json5` gets the rule, here for an app named `octo-release`:

```json5
gitIgnoredAuthors: ["/^[0-9]+\\+octo-release\\[bot\\]@users\\.noreply\\.github\\.com$/"],
```

- **No setting:** the name is an answer already, whose validator lets through only letters, digits and hyphens, so it needs no escape. A regular expression, since a glob would read `[bot]` as one of three letters.
- **It arrives by itself:** `blueprint.py app register` names the app with an update of Copier, which writes the rule in the same pull request, and an owner who answers the name gets it with the copy. Without a release app there is neither a rule nor a bot that would need one.
- **Only that app:** any other address stays an edit. Someone with write access could name the app as the author of a commit, as with an exact address too; that only hands their branch back to Renovate.
- **The checklist asks for nothing,** and no longer asks GitHub for the number. A test keeps the address that Renovate takes in a workflow equal to that of the fix bot.

## Consequences

A commit of a bot no longer stops the Mend Renovate app, without a step for the owner, also with a new name of the app, whose update of the blueprint writes the rule anew. The rules of `hub` and `self` stay as they were. A repository with the Mend Renovate app has no Renovate workflow and so no check *renovate rules*, and no variant of the blueprint answers `mend`: the tests of the blueprint check what the pattern matches, and `renovate-config-validator --strict` of the pinned Renovate was run on the rule by hand. The table above was made by hand too, so both need asking again if Renovate changes how it treats a branch.

The rule follows the answer of Copier alone. A project that names its app only in `.github/repository.project.toml` gets no rule for it, so there the checklist says to answer the name with Copier.

A person's commit stays an edit, on purpose, as a rule can't tell a person's merge from their work. That includes *Update branch* and `gh pr update-branch`, which GitHub makes in the name of whoever asks: the section *Renovate leaves a branch alone* of [the troubleshooting](../troubleshooting.md) says how to hand such a branch back to Renovate.
