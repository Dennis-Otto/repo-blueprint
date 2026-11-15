# The hosts and files of the issue assistant of a project have a file of their own

- Status: accepted
- Date: 2026-11-15

## Context

`.github/issue-assistant/config.toml` is a file of the blueprint, and its `[links] hosts` and `[transparency] files` are values of the project all the same: the hosts that links in the comments of the issue assistant may lead to, and the files that tell reporters which AI reads their issue. The template sets the hosts by the kind of project, and four repositories that follow the blueprint changed the file of the blueprint to add their own: homedarts-for-autodarts the hosts of Home Assistant and Autodarts and a page of its troubleshooting, paperless-sync and paperless-unified-search the documentation of Paperless-ngx, issue-assistant that of Anthropic ([#848](https://github.com/Dennis-Otto/repo-blueprint/issues/848)). The check of ownership names each such change, and the next change of that line in the template conflicts with it in the pull request of the update, which then waits for a person and stops the Rollout at that repository.

The settings and the notes of a project already have files of their own beside those of the blueprint, `.github/repository.project.toml` and `.github/issue-assistant/project.md`. Since its release 1.12.0, the issue assistant reads `.github/issue-assistant/config.project.toml` as well, whose `[links] hosts` and `[transparency] files` add to those of `config.toml`, and nothing else ([issue-assistant#423](https://github.com/Dennis-Otto/issue-assistant/issues/423)).

## Options

1. **The workflow of the blueprint merges both files before the run.** The reusable workflow of the issue assistant checks out the repository in its own jobs, so the caller has no step where it could merge them.
2. **Each repository keeps changing `config.toml`.** The conflicts stay.
3. **A file of the project, which the issue assistant reads,** with a migration that moves what a repository added to `config.toml` there.

## Decision

Option 3.

- **The file:** every repository gets `.github/issue-assistant/config.project.toml`, with empty lists and a comment for each; `_skip_if_exists` of `copier.yml` and the list of `template/AGENTS.md.jinja` name it, so no update overwrites it and `owned.txt` leaves it out. The update of an existing repository creates it as a new repository gets it. A line at the top of `config.toml` points to it.
- **The defaults stay in `config.toml`,** by the kind of project, as `LINK_HOSTS` of `blueprint/migrate.py` lists them and a test keeps them equal to the template. The file of the project only adds.
- **The migration:** `issue_assistant_project` of `blueprint/migrate.py` moves each host and file of `config.toml` that the template doesn't name for the kind of the repository, from `.copier-answers.yml`, to the end of the lists of the file of the project, each once. `config.toml` keeps the rest in its order, which is that of the template, so the next update changes the lists without a conflict. What the issue assistant reads stays the same: the same hosts and files, the first file of `[transparency]` that its footers link first. A repository without answers, such as the blueprint itself, a `config.toml` that isn't TOML, or a list of another type is left alone, and the check of the issue assistant names the mistake. The tests take the real files of the six repositories that follow the blueprint as cases.
- **The migration waits a release:** the fix bot that commits it onto the pull request of the update is the copy of `main`, from the release before, which only commits a move of a path that its `MOVABLE` and the `writes` of its step *Files of the project* name ([decision 0142](0142-the-fix-bot-commits-nothing-that-runs-with-rights-where-nobody-reads-its-commit.md), [decision 0161](0161-each-fix-names-the-paths-that-it-writes.md)). So this release brings both paths there, and the migration waits in `NEXT` of `blueprint/migrate.py` until the next release adds it to `MIGRATIONS`, once every repository knows its paths. Until then the hosts that a repository added stay in `config.toml`, where the issue assistant still reads them.
- **A Chrome extension and a Cloudflare Worker** got hosts of their own kind before, instead of those of a package of npm ([#875](https://github.com/Dennis-Otto/repo-blueprint/pull/875)). The hosts of one project, such as `autodarts.io` of player-switch-for-autodarts or `core.telegram.org` of repo-pager, go into its own file.

## Consequences

A project adds a host or a file of its issue assistant without touching a file of the blueprint, and the template can change its defaults without a conflict in any repository. The issue assistant must be at least at its release 1.12.0, which a test checks of the workflows of the blueprint: an older one would leave out what a project moved. The move itself comes a release later than the file, and a person who doesn't wait moves the hosts by hand.
