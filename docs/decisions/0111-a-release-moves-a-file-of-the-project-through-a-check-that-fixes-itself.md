# A release moves a file of the project through a check that fixes itself

- Status: accepted
- Date: 2026-11-02

## Context

The issue assistant 1.9.0 names good first issue candidates in its morning digest, for the labels of a new group, `contribution`. `check` of an older release refuses that group, so the labels can move only together with the pin of the assistant.

`.github/labels.toml` belongs to the project: it is in `_skip_if_exists` of `copier.yml`, and `copier update` excludes such a file from what it applies. Moving the two labels in the template reaches a new repository and no other. All six repositories made from the blueprint have them in `decision`, and for them the feature would stay off without a word.

On 8 October 2026, we decided against migrations until the first change needs one. This is the first.

## Options

- **Say in the changelog how a project changes the file,** as until now: nobody has to read it, and each repository takes a person.
- **`_migrations` of Copier:** they run code of the template during the update and need `--trust`, which breaks the promise of `docs/security.md` that copying and updating run no code of the blueprint.
- **A step of the blueprint bot after `copier update`:** the bot that runs is the copy of `main`, from the release before, on purpose: an update runs no code of the blueprint before the checks have passed it. So it doesn't know a migration that the update brings, and every move would come one release late.
- **Take the file out of `_skip_if_exists`:** an update would overwrite the areas of each project.
- **A pull request for each repository:** it reaches the repositories of the owner and nobody else's.
- **A step of `scripts/check.sh` with an autofix:** the pull request of the update brings the code and runs it in its checks, where a mistake fails a check and changes nothing on `main`.

## Decision

`blueprint/migrate.py` holds what the releases move, each as a function from the text of a file to its new text. The step *Files of the project* of `scripts/check.sh` runs `blueprint.py migrate`, which fails while something is left to move and names it. Its explanation in `.github/checks.toml` has `blueprint.py migrate --fix` as its autofix, so the fix bot commits the move onto the pull request of the update, and the update merges itself as ever.

A migration stays in the module, so a repository that updates later, from any version, gets it too, and it finds nothing once the text has moved. Nothing records that it ran: the text of the file is the only state.

A project can decline a move in the file itself, so the check doesn't force a feature on it. For the labels, a comment behind the line `group = "decision"` keeps the label there, and a label that the file doesn't have moves nowhere.

The first migration moves `good first issue` and `help wanted` to `contribution`, in that order, as the first label of the group is the one that the digest tells the maintainer to add. The same pull request brings the pin of the assistant to 1.9.0, in the way of the sync bot, because an older `check` refuses the group.

## Consequences

- An update with a new migration fails its check once and fixes itself, which costs a second run of the checks of that pull request. That happens only for a release with a new migration.
- A repository without the release app, or a pull request with the label `no-bot-fixes`, keeps the failed check, with its explanation and the command.
- The job `update (kind)` of *Variants* runs the same command after `copier update`, as the fix bot would, and so tests each migration on the files of the latest release.
- A project that moves a label back without the comment gets it moved again.
- The way back from a migration is to delete it from `MIGRATIONS`; the files it moved stay as they are.
