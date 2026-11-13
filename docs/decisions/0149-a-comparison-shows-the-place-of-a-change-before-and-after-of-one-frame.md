# A comparison shows the place of a change before and after, of one frame

- Status: accepted
- Date: 2026-11-13

## Context

[0131](0131-keep-draws-the-difference-of-every-picture-with-frames-for-a-phone.md) gave every changed picture a picture of its difference: each changed pixel in red over a gray copy of the new picture with a quarter of its darkness, for an animation of the pair of frames with the most changed pixels. On 13 November 2026 the maintainer looked at the album that the pager sent him about homedarts-for-autodarts#716, whose `de/setup.webp`, an animation of the steps of the quick start, had changed in 0.66 % of its pixels. The picture of the difference showed step 4, the pictures before and after beside it showed step 1: the artifact holds the whole animation for both sides, and Telegram shows the first frame of an animated WebP. So the changed picture looked like another picture than the two beside it, nothing said which frame it was of, and the gray copy of a dark page left hardly anything to recognize, so one couldn't tell to which part of the page the red pixels belonged. A change of 0.66 % can't be found by eye in two whole pictures on a phone either.

## Options

1. Keep the difference and send the frame of the difference before and after as well: three pictures of one frame, but each whole, so the change still can't be found on a phone.
2. One comparison picture: the place of the change before and after, cut to the changes, of the frame with the most changes, in the colors of the pictures, with the same red frame around each change on both sides; the report names it with the frame and the number of frames.
3. Draw the changes over the picture before and the picture after, each whole.

## Decision

Option 2, and the difference stays beside it for the exact pixels. For each changed picture whose size and number of frames stayed, `keep` writes a PNG at `comparison/<path>`, named like `diff/`, and names it in the entry of the picture in `report.json` as `comparison`, with `frame`, the number of the compared frame from 1, and `frames`, how many frames the picture has, as `keep` counts them: a frame that repeats the one before counts once. These names are the contract with the pager and with the visual checks of the repositories, which call `comparison()` of `blueprint/screenshots.py`.

The comparison cuts both frames to the box around every change, with 60 pixels of room around it and at least 360 of each side, in pixels of the picture shown 1000 pixels wide at its longer side, moved inside the picture at its edges. It keeps the pixels at their size, so that a text in it stays as readable as in the picture. The two places stand side by side or one above the other, whichever a phone held upright (9 to 16) shows larger, so a wide place, such as a line of text, stands above the other; the one before comes first, and a gray strip with a white arrow lies between them. Each group of changes gets the same red frame on both sides, as wide and as far from its changes as in the difference, measured in the comparison.

The difference shows the new picture in its own colors behind a veil of a fifth of white instead of a gray copy, so that a dark page stays dark, its text readable, and the red of the changes still stands out. Its PNG is in RGB now, no longer a palette of the grays.

`kept()` takes a comparison only as `keep` names it, a PNG at `comparison/<path>` of a changed picture and no link, together with a whole `frame` from 1 up to `frames`, and neither without the other; a report of a `keep` before this change names none. The table of the pull request of the screenshot bot names the frame of an animation, and the bot commits nothing of `comparison/`.

## Consequences

The pager sends the comparison instead of three pictures that don't fit together, and says which frame it shows (repo-pager#207). homedarts-for-autodarts draws its visual check with its own `tests/e2e/compare.py`, which takes `difference()` from the blueprint: it gets the new look of the difference with the next update of the blueprint, and writes the comparison into its report in a change of its own. A comparison of changes far from each other, or of a page that moved as a whole, is as large as the picture, two of them above each other; its frames then lie at the edges.
