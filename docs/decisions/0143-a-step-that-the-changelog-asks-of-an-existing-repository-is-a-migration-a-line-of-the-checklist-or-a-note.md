# A step that the changelog asks of an existing repository is a migration, a line of the checklist or a note

- Status: accepted, amends [0111](0111-a-release-moves-a-file-of-the-project-through-a-check-that-fixes-itself.md)
- Date: 2026-11-12

## Context

An update never overwrites a file of the project, one that `_skip_if_exists` of `copier.yml` lists. So a release that needs such a file changed said so in the changelog, in an entry of the form "An existing repository …" or "An existing project …", and left the step to whoever reads it. Nothing checked whether they did. The audit of 2026-11-11 found two steps that six of the seven repositories that follow the blueprint never made ([#847](https://github.com/Dennis-Otto/repo-blueprint/issues/847)):

- the label `no-bot-fixes` of release 1.1.0, in `.github/labels.toml`, which `CONTRIBUTING.md`, `after-checks.yml` and `commands.yml` of every repository name as the way to keep the fix bot away from a pull request, and which a contributor there could not set, because it did not exist;
- `pkg:pypi/wcwidth` of release 1.3.0, under `allow-dependencies-licenses` in `.github/dependency-review.yml`, a tool of the blueprint bot whose license the review didn't know.

[Decision 0111](0111-a-release-moves-a-file-of-the-project-through-a-check-that-fixes-itself.md) gave such a step a home, a migration of `blueprint/migrate.py`, which the step *Files of the project* checks and the fix bot commits onto the pull request of the update. [Decision 0142](0142-the-fix-bot-commits-nothing-that-runs-with-rights-where-nobody-reads-its-commit.md) then limited that commit to the files of `MOVABLE`: data that the settings bot applies and no job runs as code, since nobody reads the update before it merges, and whatever runs in its checks could write the file.

## Options

1. **Everything a migration:** `.github/dependency-review.yml` joins `MOVABLE`. That file decides which licenses and which advisories pass the dependency review, a security control: on the update, whatever runs in a check could loosen it, and the bot would commit that unread.
2. **A migration only for `MOVABLE`, without a way for the rest:** the step *Files of the project* would fail the update of every repository on a file that the bot doesn't commit, until a person does; the updates, which merge by themselves, would wait.
3. **Each step where it fits:** a migration where the file is in `MOVABLE`; a line of the checklist, `python3 .github/blueprint.py checklist`, where a command could make the step but no bot may commit it unread; a note where the step is a choice or a step on GitHub that no file shows.

## Decision

Option 3.

- **A migration:** the label `no-bot-fixes` comes to the group `decision` of `.github/labels.toml`, after its last label; a file that names the label anywhere, also in a comment such as `# no-bot-fixes: not here`, declines it. The Labels workflow then creates the label on GitHub.
- **A line of the checklist:** *The dependency review allows the licenses of the blueprint bot's tools* names each tool of `BOT_TOOLS` in `blueprint/checklist.py` that `.github/dependency-review.yml` doesn't allow, and how to add it. A test keeps `BOT_TOOLS` equal to what the template allows.
- **The other steps of the changelog** stay notes, as every repository of `.github/fleet.toml` has made them, or as no file shows them:

| Release | Step for an existing repository | Kept as |
| --- | --- | --- |
| 1.4.0 | Run `copier update` with `--data publish_package=false` and remove `PUBLISH_TO` from `.github/repository.project.toml` | a note: an answer that only a package that publishes nowhere chooses |
| 1.4.0 | Register the release app with `app register` | a note: nothing to do |
| 1.3.0 | Allow `pkg:pypi/wcwidth` in `.github/dependency-review.yml` | a line of the checklist |
| 1.1.0 | Add the label `no-bot-fixes` to `.github/labels.toml` | a migration |
| 0.13.0 | Set `config.platform.php` in `composer.json` to move the tools of a Nextcloud app to PHP 8.3 | a note: `composer.lock` changes with it, and both apps have made it |
| 0.13.0 | The answers of the owner and of the release app, and answers that Copier now refuses | a note: the update makes it |
| 0.10.3 | `tests/bootstrap.php` and `tests/stubs/` of an app without the sample code | a note: the update adds the files |
| 0.8.3 | Remove the group *Dependabot* from `.github/labels.toml` and delete its labels on GitHub | a note: every repository has made it, and the deletion on GitHub is a person's |
| 0.8.3 | Name Renovate in `.github/social-preview.html` and upload the picture | a note: every repository has made it, and the checklist asks for the upload |
| 0.7.0 | `INHERIT: .github/mkdocs-blueprint.yml` in `mkdocs.yml`, and the license MIT-CMU of Pillow | a note: every repository has made it |
| 0.7.0 | `copier update --data successor=true` | a note: a choice of the owner |
| 0.3.1 | `sample_code=false` | a note: a choice of the owner |

- **From now on,** an entry of `changelog.d/` that asks a step of an existing repository comes with its migration or its line of the checklist, or says why no command can make the step, as `CONTRIBUTING.md` and `AGENTS.md` ask.

## Consequences

The next update of each repository adds the label `no-bot-fixes`: its step *Files of the project* fails, and the fix bot commits the move, as with the labels of the group `contribution`. The six repositories without `pkg:pypi/wcwidth` see it as an open step of their checklist; a person adds the line, in a pull request of the repository. The dependency review keeps its rules out of reach of every bot that commits unread.

A step that a release asks of an existing repository can't be lost silently any more as long as its entry follows this record. A new path for a migration still comes to `MOVABLE` one release before its first migration, as decision 0142 says.
