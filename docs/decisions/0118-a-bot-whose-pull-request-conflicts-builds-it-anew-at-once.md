# A bot whose pull request conflicts builds it anew at once

- Status: accepted
- Date: 2026-11-04

## Context

The screenshot bot keeps one pull request from `bot/screenshots`, built from the commit that its job *render* rendered. In paperless-unified-search, the push of the release 1.4.0 rendered the pictures, and while it did, the pull request of the run before, [#314](https://github.com/Dennis-Otto/paperless-unified-search/pull/314), merged two of the same pictures into `main`. The bot then opened [#316](https://github.com/Dennis-Otto/paperless-unified-search/pull/316) from the commit of the release, which lacked them: a picture that both sides changed is a conflict that Git can't merge. The run of the Release workflow waited for that render and rendered the same old commit again, since GitHub gives a waiting run the commit of its event. Three updates of the blueprint merged after it, but no push touched a file of `.github/screenshots-paths.txt`, so no run rendered again, and the branch bot gave #316 the label `merge-conflict` and a comment that asked a person to merge `main` into it. The next run due was the weekly one; a start by hand fixed it.

The picture bot of the blueprint (`bot/pictures`) is built the same way and runs only after a release. The sync bot of the issue assistant (`bot/issue-assistant`) runs every day, but leaves a pull request of the same release to the branch bot, which can't update one that conflicts. The diagram bot and the fix bot need nothing: every change of `main` that can conflict with their pull request starts them, and they build their branch anew from it.

## Options

1. The plan of the screenshot bot treats an open pull request of its own that GitHub finds conflicting as due. It needs `pull-requests: read`, a wait for GitHub to compute the state after each push, and the same in every bot; a conflict that comes without a push waits for the next one.
2. The branch bot, which finds every conflict already, starts the workflow of a bot that builds its branch anew, instead of asking a person to merge `main`. Its job has the token that may start a run, `actions: write`, which starts its own next run already.
3. Base the commits on the newest `main` instead of the commit that was rendered. A page whose sizes the bot corrects would then lose the changes of `main` since, and a picture that `main` got meanwhile would be replaced without a look at its pixels.

## Decision

Option 2 heals, and two changes of the picture bots remove the cause.

- **The branch bot starts the bot:** a conflicting pull request from `bot/screenshots`, `bot/pictures` or `bot/issue-assistant` of the repository, not of a fork, starts `screenshot-bot.yml`, `docs-pictures.yml` or `sync-issue-assistant.yml` on `main` with the token of the job. It gets the label `merge-conflict`, which says that the bot started it, and no comment, since nobody has to act. The workflow starts once for each conflict: a pull request with the label starts nothing, and the label goes once GitHub finds the new branch mergeable, so that a later conflict starts it again. Outside of a job, the summary says which workflow to start. A refused start is a warning, and without the label the next run tries again.
- **A waiting render renders `main` as it is then:** the job *render* checks out the newest commit of the branch, not that of its event, and names it for the job that commits; the commits start from it, and the pages come from it.
- **A render that `main` overtook renders anew:** before it touches the branch, the job with the release app asks GitHub for the comparison of the rendered commit with `main`. When `main` changed one of the pictures or pages of the commits since, lacks the rendered commit, or changed more files than GitHub lists, the bot leaves the branch and the pull request as they are, and starts its workflow again with the token of its job (`actions: write`), which renders the newest `main` and compares the pixels with its pictures. `blueprint.py screenshots overtaken` decides it.
- **The sync bot of the issue assistant** builds a pull request of the same release anew when GitHub finds it conflicting, rather than leave it to the branch bot.

## Consequences

- A pull request of these bots no longer waits for a person or for a schedule when it conflicts: the branch bot hears of the conflict at the next merge, the next change of auto-merge or the next check that ends, and the bot builds the branch anew within one run.
- The race of #316, a render while the pull request before it merges, costs one more render instead of a conflict.
- The token of the job of the pull request of both picture bots gets `actions: write`; the release app needs no new right.
- A new bot that keeps a pull request of its own and runs only now and then belongs in `REBUILT_BY` of `blueprint/branches.py`.
