# The recording of copier copy renews itself only when a screen changes

- Status: accepted, follows up [0037](0037-pictures-renew-themselves-by-their-pixels.md)
- Date: 2026-11-12

## Context

The Docs pictures workflow records `copier copy` with VHS after each release that changes the template or the workflows, which is nearly every release. `blueprint.py screenshots keep` keeps a picture whose pixels stayed the same, and since [decision 0037](0037-pictures-renew-themselves-by-their-pixels.md) it counts a frame that repeats the one before once and ignores the time that each frame shows. Yet `docs/images/copier-copy.gif` and `copier-copy.mp4` came out new with nearly every run, 20 times between 1 and 10 November 2026, and their old versions were 54 of the 68 MiB of the repository after five weeks ([#827](https://github.com/Dennis-Otto/repo-blueprint/issues/827)), which every full clone downloads.

Comparing the frames of 22 committed versions showed why:

- VHS records the terminal in real time, so each run catches the typing and the output of Copier at other moments: 139 to 156 distinct frames for the same recording.
- The GIF's 64 colors and its lossy compression depend on every frame, so the pixels of every frame differ between two runs, also those of the first screen, which is the same: of two GIFs that show the same screens, no frame was equal.
- A comparison with a tolerance doesn't tell the noise apart from a change: the noise moves pixels along the edges of every letter by up to 250 of 255, and in blocks of pixels as much as an `m` that turns into an `n`.

## Options

1. **Compare the distinct frames of the GIF in order** in `keep`, as #827 proposed. `frames` already drops repeated frames, and no frame stays equal.
2. **Compare with a tolerance,** by blocks, by the ink of the letters or by the screens on which the GIF rests. Each separated the 22 versions only with thresholds that a change of one letter falls under.
3. **Record deterministically.** VHS has no clock of its own to play a tape against; its frames follow the time of the run.
4. **Fingerprint what the recording shows.** VHS draws a picture of a screen the same way whenever the terminal shows the same: `copier-copy.webp`, made from the picture of the last screen, changed in only 6 of the 23 versions of the recording, while the GIF changed in each. The tape takes such a picture of each screen on which it waits, and the recording keeps its committed files while those pictures stay the same.

## Decision

Option 4. Before each key on which the tape waits for Copier, and after the copy and the listing of its files, `copier-copy.tape` takes a picture into `screens/`, 300 ms after the screen it waits for appeared and at least 200 ms before the next key, so that the picture shows the screen that the key answers; the times between the keys stay as they were. With the last screen, `docs/images/copier-copy.png`, these are the screens of the recording.

`.github/docs-pictures/recording.py` writes their fingerprint, their number and the sha256 of their sha256s in order, into a comment of the new GIF, after gifsicle made it smaller. When the committed GIF carries the same fingerprint, it puts the committed GIF and video in place of the new ones, so `keep` finds no change. A changed screen, another number of screens, or a committed GIF without a fingerprint, renews both, with the new fingerprint.

## Consequences

- A release that changes nothing on the screens of the recording no longer renews the GIF and the video, about 2.5 MB of history each time. The first run after this change renews them once, to add the fingerprint.
- A change that only shows between two screens, such as a line of Copier that scrolls by while it writes the files, renews the recording only with the next change of a screen.
- A new version of VHS, of its fonts or of ffmpeg may draw the screens another way, which renews the recording once, as it should.
- The history that exists stays as it is. `dashboard.png`, which shows the date and the versions of the live dashboard, still changes with each run.
