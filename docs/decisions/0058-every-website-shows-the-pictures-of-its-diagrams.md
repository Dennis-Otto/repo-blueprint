# Every website shows the pictures of its diagrams, so that a page with a diagram stays within 1.2 MB

- Status: accepted; replaces the part of [0016](0016-diagrams-as-pictures-of-their-sources.md) in which the website draws the source
- Date: 2026-10-23

## Context

[Decision 0016](0016-diagrams-as-pictures-of-their-sources.md) shows every diagram as the pictures that `scripts/diagrams.sh` draws from its Mermaid source, and had the hook of the website put the live Mermaid of the source in place of each picture, in the colors of the theme, with text to select and search. Mermaid weighs about 980 KB compressed, and every page with a diagram loaded it: the architecture, the security design and the decision records of the blueprint, and on every website the page of the automation, which drew two diagrams of the blueprint's README from copies of their sources in the hook. Such a page loaded about 1.3 MB at once, more than the 1.2 MB of a page on a phone with 1.6 Mbit/s that [decision 0041](0041-every-website-is-accessible-and-quick-and-a-check-proves-it.md) aims at, and Mermaid was its largest part ([#289](https://github.com/Dennis-Otto/repo-blueprint/issues/289)). Nothing checked the weight of a page.

While showing the pictures, the build showed none at all: since selectolax 1.0, mkdocs-glightbox 0.5.2, which wraps each picture in the link that opens it enlarged, moved the picture into the link and then replaced the picture with the link, which took both out of the page. Every picture of every website was gone, such as the social preview on the blueprint's home page; selectolax 1.0.2 fixes it.

## Options

1. Keep drawing the diagrams live. The text of a diagram stays selectable and searchable, and its colors are those of the theme, but every page with one loads about 1 MB more than the budget allows.
2. Load Mermaid only once the reader scrolls to a diagram. The first view of the page is light, but the reader who comes to the diagram still loads 1 MB, and the page needs a script of its own that Material doesn't have.
3. Show the pictures, which every repository has already, as GitHub, the app and the stores show them: a few dozen kilobytes for each, loaded only in the reader's theme and as the reader comes to them. Their text is no longer selectable or searchable, and their colors are those of the pictures.

## Decision

Option 3, as Dennis decided on #289.

- **The pictures of a page:** the hook leaves the `<picture>` of a diagram in place and shows it as every other `<picture>` with a dark `<source>`: a picture for each theme, with `#only-light` and `#only-dark`, that loads as the reader comes to it, with the width and the height that the root of the SVG names, so that the page doesn't shift. Its `alt` repeats the title and the description of the diagram, as before. A German page shows `NAME.de.svg`, which the i18n plugin serves for the German pages in their folder `de/`, without `.de` in its name; the hook leads its path there.
- **The page of the automation:** it shows the pictures of the two diagrams of the blueprint's README. Every repository gets them, light and dark, in English and German, in `.github/mkdocs-blueprint-diagrams/`, which the template takes from `docs/images/diagrams/`, so the update brings them anew whenever the blueprint draws them anew; the website serves them in `assets/images/automation/`. The blueprint itself shows those of `docs/images/diagrams/`. The text of each picture is the title and the description in the SVG, and a strict build fails when the pictures are missing. The copies of the sources in the hook are gone.
- **Mermaid for a `mermaid` block:** a page that still has one, such as one of a project, which `scripts/check.sh` warns about until its diagrams moved, is still drawn live with the pinned release of Mermaid, and its source stays out of the search.
- **A check of the weight:** `blueprint.py site-check`, which the check *docs* runs after the build, weighs every page that MkDocs built: the page, its stylesheets and scripts, the pictures and posters that load before the reader scrolls, the worker of the search with the index of the page's language, and Mermaid on a page that draws a diagram live, each as GitHub Pages sends it, compressed where it is text. A page above 1,200 KB fails the check, with the three files that it loads the most and, for a page that draws a diagram live, the hint to show its pictures. The fonts, a few of them for the whole website, come on top.
- **Pictures that stay:** the docs lock takes selectolax 1.0.2, so that glightbox wraps each picture again instead of taking it out, and the hook counts the pictures of each page after its own step and once more after every plugin: a page that lost one warns, which fails the strict build, so that a release of a plugin that takes pictures out never reaches a website again.

## Consequences

On the blueprint's website, a page with a diagram loads about 310 KB at once instead of about 1.3 MB, and the page of the automation 322 KB instead of 1,302 KB; the heaviest page is the German home page with 441 KB. The pictures of the pages show again, and the lightbox opens each one. The text of a diagram can no longer be selected, and the search no longer finds it: the title and the description of each diagram are the text of its picture, which screen readers read. The dark pictures keep the background of GitHub's dark theme, a little darker than that of the website.

Every repository has eight SVG pictures more in `.github/`, about 500 KB, which the update keeps equal to the blueprint's. A page of a project that loads more than 1,200 KB, such as one with a large first picture or a `mermaid` block, fails the check *docs* after the update; its summary names what to make smaller.
