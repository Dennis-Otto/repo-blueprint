# Every website is accessible and quick on a phone, and a check proves it

- Status: accepted, amended by [0097](0097-a-pull-request-checks-the-accessibility-of-the-pages-that-it-changes-and-a-new-violation-fails.md), by which a pull request opens only the pages that it changes and a new violation fails the check
- Date: 2026-10-18

## Context

All six websites take their theme from `.github/mkdocs-blueprint.yml`, Material's indigo, and none of them met WCAG 2.2 AA. axe-core 4.10 on their pages found the tabs of the header at 4.3:1 to the header, links in the text that only their color set apart, at 2.3:1 to the text around them in the light theme and 1.9:1 in the dark one, buttons with a border at 2.3:1 in the dark theme, colors of code below 4.5:1, and a link around every picture of the other theme that the keyboard reached although the page didn't show it. A `<picture>` followed the theme of the system rather than the switch of the website, so a reader who switched to dark got white screenshots, and the lightbox showed every light picture next to its dark copy.

The pages were also heavy. The home page of the blueprint loaded 3.5 MB on a phone with 1.6 Mbit/s and 150 ms, and its largest picture appeared after 7.5 seconds: the recording of `copier copy`, a GIF of 1.8 MB far below the fold, and the social preview, a PNG of 340 KB, loaded first, with every other picture of the page. Material loads the newest Mermaid 11 from unpkg.com, which the privacy plugin downloads in every build, so two builds of the same commit could draw the diagrams differently. Nothing checked any of this.

## Options

1. Each project fixes its own website, as dennis-otto.github.io and issue-assistant began to with stylesheets of their own. The same rules in six copies drift apart, and a new repository starts with none.
2. The blueprint brings a stylesheet, a script and the pictures to every website through its hook, and the check *docs* runs axe-core on every page that it built.
3. As 2, with Lighthouse CI as the check. It scores performance as well, but its numbers vary from run to run, it needs a browser of its own, and its accessibility audits are those of axe-core.

## Decision

Option 2.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/how-a-website-stays-accessible-and-quick.dark.svg">
  <img src="../images/diagrams/how-a-website-stays-accessible-and-quick.svg" alt="How a website stays accessible and quick: You write the pages in docs/. MkDocs builds the website with the hook and the stylesheet of the blueprint, which underline the links in the text, give the theme the contrast of WCAG 2.2 AA, load each picture as the reader comes to it and only in its theme, play a GIF with an MP4 beside it as that video, and pin the release of Mermaid. After the build, the check docs opens every page in Chrome, in the light and the dark theme, and runs axe-core on it; each serious or critical violation shows in the summary and as an annotation at its page. Without one, the website is published.">
</picture>

- **A stylesheet of the blueprint:** `.github/mkdocs-blueprint.css`, which the hook serves before the stylesheets of the project, so that a project's rules win. It underlines the links in the text, gives the tabs the full color of the header and the current one bold, the links of the dark theme 6.5:1, buttons with a border in the dark theme the color of the links, and code at least 5:1. A picture for one theme hides with its link.
- **The theme of the system, also after it changes:** the palette starts with the theme of the system, and its switch goes on to light, dark and back.
- **Pictures that load as the reader comes to them:** the hook gives the first picture of a page the priority, every other one `loading="lazy"`, and a PNG, a GIF or a WebP its width and height. A `<picture>` with a dark `<source>` becomes a picture for each theme with `#only-light` and `#only-dark`, which Material shows in that theme alone, and the lightbox shows only the pictures of the reader's theme.
- **A video in place of a GIF:** a GIF with `NAME.mp4` beside it plays as that video on the website, while it is in view, muted and in a loop, with `NAME.webp` until it plays; a reader who paused it, or whose system asks for less motion, starts it. GitHub keeps the GIF. `scripts/docs-pictures.sh` makes the video, its picture and a GIF of 64 colors, and the picture bot takes MP4s, which change when their bytes do; one beside a GIF changes only together with that GIF, since each recording encodes the video anew while its GIF looks the same, as [decision 0037](0037-pictures-renew-themselves-by-their-pixels.md) keeps a picture whose pixels stay.
- **A Mermaid of a fixed release:** the hook gives Material a copy of its script that loads `MERMAID` of the hook, which Renovate keeps current within the major version that Material loads. A Material that loads another one fails the strict build, so that both move together. The pages load Mermaid only where they draw a diagram, as before.
- **A check of every page in both themes:** `.github/a11y/check.mjs` runs axe-core with the rules of WCAG 2.2 A and AA on every page that the build wrote, in the Google Chrome of the runner, with `playwright-core` and `@axe-core/playwright` locked in `.github/a11y/package-lock.json`, so that it downloads no browser. Each theme has a browser of its own whose system shows that theme, and each page loads in it as for a new reader, without a theme that an earlier page saved; a website whose palette doesn't follow the system switches with its toggle, and a page that shows the theme of its toggle neither way is a violation too. A page of another language without a translation, whose text is that of its page in the default language, is checked through that page. It answers every request from the built website and refuses every other, so it needs no network. Each serious or critical violation goes into the summary of the check and becomes an annotation at the Markdown of its page, with a link that explains the fix. For one release it only reports, so that every repository can fix its pages after the update; then it fails the check *docs*. The Dashboard workflow runs it on the website with the dashboard.

## Consequences

On the slow phone, the home page of the blueprint loads 1.6 MB instead of 3.5 MB, and its largest picture appears after 1.7 seconds instead of 7.5; the guide 1.7 MB instead of 3.8 MB, after 2.8 seconds instead of 8.9. axe-core finds no serious or critical violation on the 91 pages of the blueprint's website in either theme, and on ha-autodarts' website only its own demo page, whose colors are the project's.

Mermaid is now the largest part of a page with a diagram, almost 1 MB. Drawing the diagrams live is [decision 0016](0016-diagrams-as-pictures-of-their-sources.md); the pictures that the Markdown shows are a few kilobytes, so showing those on the website as well would make such a page small too, at the cost of text to search and select. [Decision 0058](0058-every-website-shows-the-pictures-of-its-diagrams.md) does that, and the check weighs every page.

The check adds about a minute and a half to the check *docs* of the blueprint, whose 95 pages it checks through 50. A project whose own pages, colors or stylesheets fail it has one release to fix them; the summary of the check names each one. Once that release reached every repository, the check fails on what it finds.
