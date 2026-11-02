# The screenshot bot corrects the sizes that pages name for a picture of another size

- Status: accepted
- Date: 2026-11-02

## Context

A page that shows a picture can name its width and height, so that it doesn't shift while the picture loads. In paperless-unified-search#274 the bot rendered `screenshots/10-try-a-search*.png` taller, from 660 x 788 to 660 x 878. `docs/index.md` and `docs/index.de.md` still named the old size, so the check of the project, `tests/js/website-pictures.test.mjs`, failed `check (php)` until an agent edited the pages by hand, and it fails again at the next change of shape: the bot opened a pull request that could not pass, and the bot that should save the work made it. dennis-otto.github.io and player-switch-for-autodarts name such sizes on their pages too, and homedarts-for-autodarts does in its README.

The job that commits holds the token of the release app, and it trusts nothing from the job that ran the script of the project ([decision 0037](0037-pictures-renew-themselves-by-their-pixels.md)).

## Options

1. A `--write` mode of the check of each project as its autofix. The check is a project's own, in another language in each project, so each project would write the same fix again, and the pull request would fail first.
2. Let the script of the project rewrite the pages in the job *render*, and let the bot take them from the artifact. A file of the artifact would then reach a page, as the release app, and checking that it differs from `main` only by numbers needs the same parser as computing those numbers.
3. Let `blueprint.py` compute the correction in the job *pull-request*, from its own checkout of `main` and the numbers in the headers of the pictures, and commit it with them.

## Decision

Option 3, for the Screenshots and the Docs pictures workflow alike.

- **Which sizes:** those of the pictures that came out at another size, wherever a page at the top of the repository or in `docs/` names both the width and the height, in `![Text](address){ width="660" height="788" }` of Markdown or in `<img>` of HTML, at an address relative to the page or from `main` of the repository, read as the hooks of the website read it ([decision 0062](0062-the-website-shows-the-pictures-of-its-repository-from-the-checkout.md)).
- **Which numbers:** a page that named the whole picture of another shape names the whole new one. Any other keeps its width, such as a phone in a gallery at the width of 120, and gets the height of the new shape; a height one pixel off stays, as rounding makes it, and so does the size of a sharper file of the same shape, which looks the same on the page.
- **Only numbers:** the Markdown comes from the checkout of `main` and no other text changes: the quotes of the numbers, every other attribute, the line endings. The header of a picture is read without Pillow, which the job doesn't have, and a file that names no size that makes sense corrects nothing. The size of the committed file comes from `report.json`, and a false one decides at most whether a page keeps its width; the height follows the file.
- **Fail closed:** a width alone, a size in percent, an address of another repository, a link, a page by a path that isn't plain or not in UTF-8 stay as they are, and the check that names the size explains them. A code block that shows the same picture at the same size changes with the page, as it shows what the page shows.
- **Without pictures in the checkout:** the job checks out its tool and `*.md` by the patterns of a sparse checkout that isn't in cone mode, so that it fetches no picture of `main` for a few lines of text.
- **On your machine:** `blueprint.py screenshots restore` makes the same correction in the work tree, for a repository without the release app, whose run names that command. Without `--repo`, it takes the repository from the remote *origin*.

## Consequences

The pull request of the bot passes a check that compares the sizes on a page with its files, and its description has a table of what changed, so a person sees it. The bot now commits text of the repository as well as pictures, by the fixed rule above; the threat in [the security page](../security.md) names it. A project needs no check and no code of its own for this. homedarts-for-autodarts keeps its own bot until it moves to this one (issue #421), and only then gets the correction. Sizes in another place, such as a `<source>` or a stylesheet, stay with the check of the project.
