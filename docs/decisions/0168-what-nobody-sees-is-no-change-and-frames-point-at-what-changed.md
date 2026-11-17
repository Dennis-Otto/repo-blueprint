# What nobody sees is no change, and frames point at what changed

- Status: accepted
- Date: 2026-11-17

## Context

`blueprint.py screenshots keep` counted a pixel as changed when any of its bytes differed ([0037](0037-pictures-renew-themselves-by-their-pixels.md)), and framed the changes in squares of 48 pixels of a picture shown 1000 pixels wide that joined when they touched, also at a corner ([0131](0131-keep-draws-the-difference-of-every-picture-with-frames-for-a-phone.md)). On 17 November 2026 the maintainer reported that the pager flooded him with comparisons whose red frames held nearly everything ([#985](https://github.com/Dennis-Otto/repo-blueprint/issues/985)): the menu at the left, the whole column of dates, the upper half of a picture.

The pictures of the visual check of paperless-sync#511 ("update the images", run 43930199217), which hold the pairs that the pager sent, show what differed, pixel by pixel:

- **A real change in every picture:** the new images of Nextcloud draw another icon on the button that shows and hides the navigation, 18 by 14 pixels at (324, 68) of a picture 1280 pixels wide. It is the only difference of every still picture, 210 pixels.
- **A real change in two animations:** in the last frames of `archive.gif` and `archive-dark.gif`, the new viewer of PDF files lays out its toolbar anew, with a button more.
- **Noise everywhere else:** each frame of the animations differs in up to 11,500 more pixels, because the GIF picks other colors of its palette for the same page: by 1 to 13 of 255, and by up to 38 in single pixels at the edges of letters. These pixels lay all over the picture, so the squares of 48 pixels touched each other across it and their frames held everything. They also made a frame with the icon alone, such as frame 6 of 57 of `archive-dark.gif`, the one with the most changed pixels: 1.12 % instead of 0.02 %.

So the frames were large because noise filled the space between the real changes, and every picture was reported because each had a real change: the noise decided which frame was shown and how large the frames were.

## Options

1. **A threshold on the share of changed pixels of a picture:** hides a real change of a small icon, 0.02 % of the picture, together with the noise.
2. **A threshold on the difference of each pixel alone:** takes the shades of the palette away, but not the edges of letters, which differ by up to 38 in the same pictures, and a higher threshold misses a change of color that one sees.
3. **A threshold of sight, as an eye compares:** a pixel changed only when its color lies beyond the colors around the same place in the other picture, and the average of the pixels around it beyond the averages around it.

## Decision

Option 3. A pixel changed only when both hold, either way between the pictures:

- one of its colors, or its opacity, lies more than `TOLERANCE`, 24 of 255, below the least or above the greatest value of that color at the same place and its eight neighbors in the other picture. Every shade between the colors of the neighbors lies within, and the edge of a letter is made of such shades, so an edge drawn in another shade or a pixel further is no change;
- and the average of the square of three by three pixels around it lies more than `AVERAGE`, 10 of 255, beyond those averages at the same place and its neighbors in the other picture. A letter drawn half a pixel further keeps its averages nearby; another letter doesn't.

The numbers come from the pictures: the shades of the palette reach 13, so 24 leaves room, and 10 is the middle of the averages that took the letters drawn half a pixel further away, from 6 up, and still found a 6 for a 5 and a single white pixel on blue, up to 12. Tests take real pairs of paperless-sync#511, cut to the place that tells, in `tests/data/sight/`: the shades of the palette and the edges of letters come out as the same, the new icon and the toolbar as changes. Synthetic changes of a real picture test the other side: a button moved by two or four pixels, another word, a 6 for a 5, an o for a c, a color lighter by 25 and a single white pixel are changes; a button moved by one pixel, a color lighter by 24 and letters drawn a quarter, a half or a whole pixel further are not. There is no threshold of the number of pixels: a real change can be few pixels, and the noise of the pictures was gone without it.

A picture whose pixels differ only below this threshold gets its committed file back, like one whose pixels stayed the same, so neither the screenshot bot nor a visual check reports it. The report names it apart, under `unseen`, with the `share`, `pixels` and `box` of every pixel that differs and `seen` false. Each changed picture names, besides what it named before, `pixels`, how many pixels changed in all its frames, `box`, where they changed in the frame that its comparison shows, `seen` true and `all_over`. No field is renamed, so the pager of today reads the report as before, and its `share` is the share of the pixels that one sees.

The frames point: changes join in squares of 16 pixels of a picture shown 1000 pixels wide, as before with 48, and frames that would touch become one, so a frame is no larger than its changes and their air. When the frames together would cover more than a fifth of the picture, or be more than 12, the picture changed all over: neither the difference nor the comparison draws a frame, the difference shows the changed pixels in red, and the table says *changed all over*.

A pointer or a caret that sits a pixel further, or blinks beside a letter, falls under the edges; one that sits clearly elsewhere stays a change, because no comparison of pixels can tell it from a small icon, and the threshold must not hide that. A script that records hides its pointer and caret, or keeps them still.

## Consequences

The pictures of paperless-sync#511 would still have been reported, because each had the new icon, but with a frame around the icon alone and, in the two animations, around the parts of the toolbar; the shares fall from up to 0.65 % to between 0.01 % and 0.04 %. A dependency update that only changes the shades of a GIF or the edges of letters changes no picture and sends nothing. A change of one pixel in a shade close to its neighbors, or a whole element moved by a single pixel, is no change any more; the pages say so. The comparison looks only at the box around the pixels that differ by more than the tolerance and takes the neighbors with a few steps of Pillow: a frame of 1280 by 800 pixels with a small change costs less than a tenth of a second, and one that changed all over about half a second, so an animation of 57 such frames, as in the update to Nextcloud 35 of paperless-sync#512, takes about 25 seconds instead of 3.
