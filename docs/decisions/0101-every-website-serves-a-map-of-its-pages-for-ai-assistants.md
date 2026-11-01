# Every website serves a map of its pages for AI assistants

- Status: accepted
- Date: 2026-11-01

## Context

AI assistants look for `/llms.txt` ([llmstxt.org](https://llmstxt.org/)), a Markdown map of a website. Since Dennis-Otto/dennis-otto.github.io#99, the root of the address has one that lists every project; a project website answered 404, and a website made from the blueprint outside that address had no map at all (#437).

## Options

1. A file that each project writes in `docs/`. It goes stale with the first new page, and the blueprint can't check what it should say.
2. A plugin for MkDocs. It would be one more dependency of every website, for what a hook does in a few lines with the menu that it already sees.
3. The hooks of the blueprint write it from the menu at every build, and the check *docs* checks it.

## Decision

Option 3.

- **The menu decides what the map lists.** Its parts become the sections, as a reader sees them; the pages at the top of the menu come first, under *Pages*. A link to another site is no page of the website, and a page that search engines leave out or a decision record, in a folder `decisions` at any depth, stays out, as on the map of the address: those are for maintainers.
- **Full addresses,** as a reader of the file gets it alone, with no address to resolve a relative link against. A website without `site_url` has none and gets no map.
- **A language has a link only where it has a page.** A further language that shows a page untranslated has no link for it, and the map stays in the default language otherwise.
- **The last build writes it.** The i18n plugin builds every further language within the build of the default one, so `on_nav` keeps the menu of each, and `on_post_build` writes the map once all are there, when the pages have their titles and descriptions.
- **A file that is there stays,** from `docs/llms.txt` or from a hook of the project that runs earlier, as on the website at the root of an address, which lists every website there.
- **lychee reads the file with a rule of its own.** With `--offline`, which keeps the check of the website away from the network, lychee leaves out every full address, so reading `**/*.txt` alone, as #437 proposed, would have checked nothing: 0 of 6 links in a trial with lychee 0.24.2. A second step gives it `--remap` with the rule that `blueprint.py site-check` writes, which leads the addresses of the website to the files of `site/`. The rule stays out of the step of the pages, whose full addresses may lead outside the build, such as the dashboard. A website at the root of an address has no rule, as other websites have addresses below it.
- **`site-check` checks what lychee can't:** the file starts with a title, its sections hold lists of links alone, no link leads to a decision record or to a page that search engines leave out, and a further language with a home page of its own has links. At the root of an address, a folder that the website lacks belongs to another website.

## Consequences

- Every website answers `/llms.txt`, also one made from the blueprint outside the address of its owner, and the file follows the menu without anyone touching it.
- The job *docs* has one more step of lychee, of a second or two.
- `llms-full.txt`, with the text of the pages, stays out for now: nothing asks for it yet, and the search index has the text for those who do.
