# The bot-health bot asks for the upload of a new social preview

- Status: accepted, amended by [0140](0140-a-step-that-waits-for-a-person-has-a-label-of-its-own.md)
- Date: 2026-11-09

## Context

GitHub takes the social preview of a repository only from an upload under *Settings → General → Social preview*, which no API offers. `scripts/social-preview.sh` renders `.github/social-preview.png`, and the screenshot bot renders it anew wherever a project's `scripts/screenshots.sh` takes it, but GitHub keeps showing the old upload until a person uploads the new picture. On 8 November 2026 the uploaded previews of repo-blueprint (still *Seven kinds of projects* and *Dependabot*), paperless-unified-search and the website were out of date, and that of dennis-otto-pager had never been uploaded ([#721](https://github.com/Dennis-Otto/repo-blueprint/issues/721)). Nobody had noticed: the checklist's step *Social preview uploaded* read only `usesCustomOpenGraphImage`, which says that someone uploaded a picture once, and the only hint, a sentence in the pull request of the screenshot bot, sits in a pull request that merges itself.

GitHub serves the uploaded file byte for byte at the `openGraphImageUrl` of the repository, which GraphQL names, from `repository-images.githubusercontent.com`: right after an upload, the sha256 of that download is the sha256 of the committed picture. Without an upload, GitHub draws a card of its own on another host.

A private repository is different. GitHub [shares the image only from a public repository](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/customizing-your-repositorys-social-media-preview), and takes an upload in a private one only where someone uploaded one before, such as while the repository was public. Whether the host of uploads serves the upload of a private repository to an anonymous download, as the look makes it, is not documented, and no private repository of the blueprint's owner holds an upload to try it with ([#760](https://github.com/Dennis-Otto/repo-blueprint/issues/760)).

## Options

1. **The checklist alone:** it compares the upload with the picture, but only whoever runs it hears of it.
2. **The screenshot bot, after the merge of its pull request:** it knows when it changed the picture, but not when a person changed it by hand, as most projects do with `bash scripts/social-preview.sh`, and nothing would run again to close its issue once someone uploads the picture, since an upload starts no workflow.
3. **The nightly look of the bot-health bot:** it runs in every repository each night, sees the picture on the default branch whoever changed it, and can open an issue and close it again. Its issues carry the label `bot-failure`, which the pager pages ([`src/rules.ts`](https://github.com/Dennis-Otto/repo-pager/blob/main/src/rules.ts) ignores the issues of a bot except those), and GitHub notifies whoever watches the repository of a new one.

## Decision

Options 1 and 3.

- **The checklist compares.** Once the repository holds `.github/social-preview.png`, the step is *Social preview uploaded and current*: done when the uploaded picture is the committed one, byte for byte, with the link to the settings when GitHub shows a card of its own or an older picture, and neutral, with the reason, when the upload can't be read. A repository without the picture keeps the step *Social preview uploaded*, done with any upload.
- **The bot-health bot asks.** Its nightly look compares the two in the same way and keeps one issue, *Upload the new social preview*, with the labels `bot-failure` and `maintenance`, open while they differ: with the picture of the commit that last changed it, the link to the settings and the steps of the upload. Its state, in the marker of the bot, holds the sha256 of the picture: the next night leaves the issue alone while the picture stays the same, so the pager pages once; a picture that changes again updates the issue, and the night after the upload closes it. A page that still shows the default panel of its kind ([decision 0127](0127-a-new-social-preview-draws-its-kind-of-project.md)) has no picture to upload yet, because the checklist asks first to replace the panel: the bot opens nothing for it, and closes its issue, as it does when the picture is gone.
- **One more host.** The job *look after every workflow* reaches `repository-images.githubusercontent.com:443` besides GitHub's API and waits for it, as [decision 0088](0088-jobs-that-block-wait-for-their-hosts-and-try-again-when-they-hang.md) asks. The download takes only an address on that host and reads at most a byte more than the 1 MB that GitHub takes. The job keeps blocking every other host and holds no token that writes more than before ([decision 0130](0130-jobs-that-reach-any-host-hold-no-token-that-writes.md)): it already writes issues.
- **A picture too large to upload says so.** GitHub takes an upload of at most 1 MB: for a larger `.github/social-preview.png`, the issue and the checklist ask first for a smaller render, with fewer colors or a simpler screenshot, since that picture can never be uploaded.
- **A private repository compares nothing.** The query that names the upload names the visibility too, `isPrivate`. In a private repository nobody sees the social preview, and an issue would ask for an upload that GitHub may not even take, so the look downloads nothing, opens no issue and passes, with a line of its summary that says why. It closes an issue that the repository kept when it turned private, as not planned, and asks again once the repository is public. The checklist's step stays neutral there, with the reason. Neither sends a token to the host of uploads instead: the picture would still show to nobody.
- **A failure shows.** A download that times out, or that the host answers with an error of its own side, gets one more try after a pause, as the requests to GitHub's API do. When the upload still can't be read, the look names the reason in its summary and fails, as it does when it can't look at a workflow, so that a host that Harden-Runner blocks or a change of GitHub doesn't hide the issue.
- **The screenshot bot points to it.** Its pull request, when it changed the picture, says that the issue stays open until GitHub shows it.

## Consequences

A maintainer hears of a new social preview within a night, in the issue and through the pager, and the issue shows the picture to upload.

The nightly look makes one more query of GraphQL in a repository with the picture and one download of at most 1 MB when someone uploaded a picture.

Until the pager gives this issue a text of its own, its alarm reads *A bot fails: Upload the new social preview*, as for every issue with the label `bot-failure`, although nothing fails: a step waits for a person.

Should GitHub stop serving the upload byte for byte, every repository would get the issue although its upload is current; the look would then need to compare the pictures by their pixels, as the screenshot bot does. A private repository hears of its social preview only once it is public: the first night after that compares the pictures and opens the issue when they differ.
