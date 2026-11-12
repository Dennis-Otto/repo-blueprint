# The fix bot commits nothing that runs with rights where nobody reads its commit

- Status: accepted, amends [0023](0023-pull-requests-fix-themselves.md)
- Date: 2026-11-12

## Context

The jobs of the checks hold a token that only reads, and the jobs that hold the key of the release app check out `main` alone ([decision 0130](0130-jobs-that-reach-any-host-hold-no-token-that-writes.md)). The fix bot bridges the two: a check that fails keeps the files that its commands of `autofix` changed as an artifact `fixes-<job>`, and the bot after the checks commits them as the release app ([decision 0023](0023-pull-requests-fix-themselves.md)). It lets through only text files that the commit has, outside `.git` and `.github/workflows/`, and nothing ties a file to the command that was meant to fix it: whatever runs in the job of a check, a dependency of the branch or one of its tools, can change any tracked file before the upload.

Decision 0023 accepted that, as "each such commit shows in the pull request". That holds where a person reads the pull request before the merge, not for the two kinds that merge without anyone ([#837](https://github.com/Dennis-Otto/repo-blueprint/issues/837)):

- a pull request of Renovate or Dependabot, which merges by itself once green, with no required review, and on which Renovate takes the release app's commit for its own ([decision 0104](0104-renovate-takes-the-commits-of-the-release-app-for-its-own.md));
- the pull request from `bot/self-heal`, which merges itself.

There a new version of a dependency that runs in a check could reach `main` with a change of `blueprint/`, `.github/blueprint.py`, `scripts/` or a composite action, which the jobs of *After the checks*, *Update branches* and *Release* later run with the key of the release app, here and in every repository made from the blueprint. A pull request of a person whose auto-merge is on merges without another look at the bot's commit too.

## Options

1. **Keep it,** as decision 0023 did. The split between the jobs without rights and those with them has a gap exactly where no person looks.
2. **The guard of a fork everywhere:** no fix of a file that decides what a workflow runs, on every path. A person's own pull request would lose the fixes of Ruff for `blueprint/` and of the text files of `.github/`, the most common fixes of the blueprint itself, for a risk that the person reads.
3. **The guard where nobody reads the commit:** on the pull request of a bot, on one whose auto-merge is on, and on that of `main`, no fix of a file that decides what a workflow runs or that runs later with the rights of one. A person's own pull request keeps every fix.
4. **Each check names the globs that its `autofix` may write,** in `.github/checks.toml` and `.github/checks.project.toml`, and the bot keeps a file only when a check of its workflow allows it. It ties a fix to its fixer, but the text files and Ruff may write nearly anything, `blueprint/` included, so it doesn't close the gap by itself, and every project would have to name the globs of its own checks.

## Decision

Option 3, with option 4 left as a follow-up that narrows the rest ([#864](https://github.com/Dennis-Otto/repo-blueprint/issues/864)).

- **Who reads the commit:** `fix collect` reads the pull request as it decides, as before, and says in the output `unread` why nobody reads the bot's commit before the merge: `bot` for a pull request of a bot, by the type of its author, which covers Renovate as the release app, Mend's Renovate and Dependabot, and `auto-merge` for one whose auto-merge is on. `fix commit` takes it as `--unread`; without the option, the bot counts the commit as unread, so that a step that forgets it fails closed. `fix main` always counts as unread.
- **What stays with a person:** each file for which `decides_what_runs()` of `blueprint/branches.py` is true, the guard of the runs of a fork and of `/fix` on a fork, such as `.github/`, `scripts/`, `pyproject.toml` and the lock files; and what runs later with rights or reaches every repository: `blueprint/`, the scripts at the root that the workflows run, such as `blueprint.py` and `downstream.py`, and the `template/` of the blueprint. A test keeps the scripts equal to those that the workflows name.
- **The move of a migration:** the update of the blueprint, a pull request of the release app from the branch `blueprint/update`, merges by itself, and its check *Files of the project* fails until the bot commits what `migrate --fix` moved in a file of the project ([decision 0111](0111-a-release-moves-a-file-of-the-project-through-a-check-that-fixes-itself.md)). `unread` says `update` there, and the bot still commits a fix of a file of `MOVABLE` in `blueprint/migrate.py`, such as `.github/labels.toml`, but of no other guarded file. These are data that the settings bot applies and no job runs as code. The bot that decides is the copy of `main`, from the release before, which can't know a migration that the update brings, so it trusts the path, not the text: a new path comes to `MOVABLE` one release before its first migration, and a test keeps the path of each migration in it.
- **What a person sees:** the bot commits the other fixes as before and names each file that it left, with the reason, in the summary of its job, and on `main` in the description of the pull request. The check stays red, so a pull request of a bot doesn't merge, and a person commits the fix, by hand or with `/fix`, whose answer lists every file. A pull request of `main` with nothing but such fixes doesn't open, and one that is open closes.
- **What doesn't change:** a person's own pull request without auto-merge, a `/fix` of a person on a branch of the repository, the suggestions on a fork and the guard of `/fix` on a fork.

## Consequences

What runs in a check of a pull request that nobody reads can no longer bring code to `main` that a job with rights runs, through the bot. Renovate writes its lock files and `.github/pins.toml` itself, with `postUpgradeTasks`, so its pull requests rarely needed such a fix of the bot; one that does stays red until a person commits it, as the refresh under the Mend Renovate app already waits for the maintainer ([decision 0137](0137-the-refresh-of-the-lock-files-merges-by-itself-from-versions-a-week-old.md)). A weekly run of `main` that a new rule of Ruff fails heals `main` only outside `blueprint/` and the scripts, and leaves those files to a person. A person's pull request with auto-merge on gets these fixes no longer by itself either; `/fix` brings them.

The other files, such as the documentation, the tests and the code of a project outside these folders, still come from the artifact of a check as data that nobody reads before a bot's pull request merges. They run with no rights, but they reach `main`, so option 4 would narrow them to what each fixer writes.

One case stays open: the bot decides whether a person reads its commit when it plans the commit. A person's pull request that turns auto-merge on after the bot's commit, or that is merged right after it turns green without another look, takes a fix of a guarded file unread. The follow-up [#864](https://github.com/Dennis-Otto/repo-blueprint/issues/864) names this case too.
