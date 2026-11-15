# Every website serves its fonts and Mermaid only by their sha256

- Status: accepted
- Date: 2026-11-15

## Context

The privacy plugin of Material downloads the files of other servers that the pages name and serves them with the website, so that reading a page asks no other server. Without `theme.font`, Material names the stylesheet of Google Fonts for Roboto and Roboto Mono, and the plugin downloads it from `fonts.googleapis.com` and its 30 fonts from `fonts.gstatic.com`; it also finds the address of Mermaid in the script of Material and downloads `mermaid.min.js` from unpkg.com, on every website, whether a page draws a diagram or not. The hooks pinned only the version of Mermaid, and nothing checked a hash of any of these files. The Docs workflow keeps them in its cache for an ISO week, so the first build of a week took whatever the servers sent then and served it to every reader ([issue 935](https://github.com/Dennis-Otto/repo-blueprint/issues/935)). Every diagram of the blueprint is a picture since [decision 0016](0016-diagrams-as-pictures-of-their-sources.md) and [decision 0058](0058-every-website-shows-the-pictures-of-its-diagrams.md), so Mermaid is needed only where a page still has a `mermaid` block.

The stylesheet of Google Fonts names no version: Google changes it whenever a font gets a new version, and a pin of its hash would fail the build of every website at a time that nobody chose, with no update that Renovate could make. The address of each font names its version, and the file under it stays as it is.

## Options

1. A sha256 of every file that the plugin downloads, the stylesheet of Google Fonts included: the builds fail whenever Google changes the stylesheet, until someone writes the new hashes.
2. The fonts and Mermaid from a hash-pinned package, such as `@fontsource/roboto` and `mermaid` of npm: every build of a website needs Node and a lock file of npm beside the hash-pinned tools of Python, for three files.
3. The fonts and Mermaid in the repository: about 4.3 MB of binary files in every repository, 0.8 MB of fonts and 3.6 MB of Mermaid, which every update of a font or of Mermaid brings again.
4. A copy of the stylesheet of Google Fonts in the blueprint, `.github/mkdocs-blueprint-fonts.css`, with `theme.font: false` in `.github/mkdocs-blueprint.yml`, and the sha256 of each font and of the release of Mermaid in `.github/mkdocs-blueprint-pins.toml`, which the hooks check; Mermaid downloaded by the hooks once a page has a `mermaid` block.

## Decision

Option 4. The hooks serve the stylesheet of the fonts before that of the blueprint, and the privacy plugin downloads the fonts that it names, through the requests of the hooks, which already try a download again: a file that the pins name and whose sha256 differs raises an error, which the plugin takes for a download that failed, so it never reaches the cache or the website, and a strict build, as every build of the CI and of `scripts/check.sh` is, fails. Before the plugin starts, the hooks remove every copy in its cache that differs from its pin, such as one from a cache of the time before this record, so that the plugin downloads it again and the check sees it.

The script of Material names the copy of Mermaid at the address of the website instead of unpkg.com, so the plugin leaves it alone, and after the pages, once one of any language had a `mermaid` block, the hooks download the pinned release, check it, keep it in the cache of the plugin and serve it where the plugin served it before. A website without an address, whose script can't name the full address of the copy, loads it on every page, as the plugin does, and a website without the downloads of the plugin loads the pinned release from unpkg.com. The release of Mermaid has its line `# renovate:` in the pins, which Renovate moves within the major version that Material loads, and `pins.py` writes the sha256 of the new release beside it and into `.github/pins.toml`.

## Consequences

A website serves no font or Mermaid that differs from the files that the blueprint pins, and a website whose pages have no `mermaid` block, as every website of the blueprint and of its repositories today, downloads no Mermaid and serves none: the builds ask unpkg.com and `fonts.googleapis.com` nothing, so an outage of either no longer breaks them. The fonts look the same, since the copy is the stylesheet that Google Fonts sent to the privacy plugin. A check needs no network: a cache of the week still serves a build while a server is out, as before.

The pins hold only what the blueprint brings. A picture that a page of the project shows from another server is downloaded as before and isn't checked, since no pin could know it; a project that names fonts of its own in `theme.font` gets them from Google Fonts, as Material loads them, without the stylesheet of the blueprint. The fonts of the preview cards, which the social plugin downloads to draw the cards and which the website doesn't serve, stay as they are. A new version of Roboto at Google Fonts doesn't reach the websites by itself: the copy keeps the fonts of `roboto/v51` and `robotomono/v31` until someone takes the stylesheet again with the User-Agent of the privacy plugin and writes the sha256 of its fonts.
