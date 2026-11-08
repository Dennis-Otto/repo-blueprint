# Keep draws the difference of every picture, with frames for a phone

- Status: accepted
- Date: 2026-11-08

## Context

The visual checks of the repositories show what changed in a picture: each changed pixel in red over a pale copy of the new picture, as `diff/` of their artifacts, and the pager links to them with the words "each changed pixel in red". On 8 November 2026 the maintainer looked at such a message about paperless-unified-search, whose `dark-poster.webp` had changed in 8.16 % of its pixels and `search-and-open-dark.gif` in 0.11 %, and found no red pixel. There were two causes. The checks of paperless-unified-search and paperless-sync drew a difference only for PNG and skipped every other kind, and paperless-unified-search has only WebP, GIF and MP4 in `docs/images`, so its artifact had never held a red pixel. And where a difference was drawn, a change of 0.1 % of the pixels was a few red dots, which vanish when a phone or Telegram shows the picture scaled down to about 1000 pixels wide.

`blueprint.py screenshots keep` already reads every picture with Pillow, frame by frame, to compare it with the one of `main` ([0037](0037-pictures-renew-themselves-by-their-pixels.md)). It is the one place that can draw the difference of every kind once, for every repository.

## Options

1. Each repository draws its differences: three implementations, in JavaScript and in Python, of which two can read only PNG without a library for each kind.
2. `keep` draws the changed pixels only, in red: every kind, but a single changed pixel still disappears when the picture is scaled down to a third.
3. `keep` draws the changed pixels in red and a red frame around each place of change, whose width and distance grow with the size of the picture, so that a picture scaled to about 1000 pixels at its longer side still shows the frame several pixels wide.

## Decision

Option 3. For each changed picture whose size and number of frames stayed, `keep` writes a PNG at `diff/<path>`, with `.png` appended unless the path ends in it, and names it as `diff` in the entry of the picture in `report.json`; `collect` copies it from the shard that rendered the picture. Each changed pixel is `rgb(220, 38, 38)` over a gray copy of the new picture on white with a quarter of its darkness, as the repositories draw it; for an animation, the pair of frames with the most changed pixels. The changes are grouped in squares of 48 pixels of a picture shown 1000 pixels wide at its longer side, joined where the squares touch, also at a corner; each group gets a frame 4 such pixels wide, 6 away from its changes. A test scales a picture of 3000 pixels, and one of 2400 pixels in height, with a single changed pixel down to 1000 pixels, with three filters, and still finds red there, which the pixel alone doesn't leave. The PNG has a palette of the grays and the red, so a difference stays small.

A picture of another size or with other frames, a new and a deleted one, a video and a picture that Pillow can't read get no difference, and `keep` goes on. `kept()` takes a `diff` only as `keep` names it, for a changed picture, as a PNG and no link, because `collect` copies it; a report without the key, from a `keep` before this change, names none. The commits of the bot still take only `files/`.

## Consequences

The artifact of every run of the screenshot bot and of the Docs pictures workflow holds a picture of each difference, and the description of the pull request and the summary of the run say so. The repositories take these pictures from `keep` in their own visual checks instead of drawing their own, in packages of their own once a release of the blueprint brings this, and the pager can send them as they are. A frame hides the pale copy of the picture around a change for a few pixels, and the changes of a picture that changed everywhere lie in a few large frames; the red of the pixels shows where they are within.
