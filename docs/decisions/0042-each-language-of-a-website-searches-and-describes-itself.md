# Each language of a website searches and describes itself

- Status: accepted
- Date: 2026-10-18

## Context

The websites in English and German, such as those of the blueprint, ha-autodarts and paperless-sync, had one search index for both languages. An English search for "checkout" on ha-autodarts' website found a German page first, a German search found the English version of a page that has a German one, and 18 German sections of ha-autodarts' roadmap led to `…/undefined`, because the i18n plugin had taken their page out of the index: its title and empty text looked like those of the English page. 67 entries of the blueprint's index were the Mermaid sources of the live diagrams, so a search for "token" showed `flowchart LR admin([…` as its text.

A German page without a translation, such as `de/roadmap.html`, is the English page under a German menu, but it said it was German, named itself as its canonical address and was a German version for search engines: duplicate content in the wrong language for search engines and screen readers. The links to the versions of a page were relative, which search engines ignore, and had no `x-default`. Every page had the description of the website, the switch between light and dark spoke English on the German pages, the changelog showed the date of its own file of one line, not that of `CHANGELOG.md`, which it includes, the sitemap the date of the build for every page, and the badges of the README showed the release and the checks of the day of the build. The template of the decision records was in the search and the sitemap.

## Options

1. A second build for each language, each with its own search: the language switch of Material between the two builds needs addresses that the i18n plugin doesn't give, and every repository would build its website twice.
2. One index, and a script that hides the results of the other language: Material renders the results ten at a time as the reader scrolls, and counts them, so hidden results leave a short list that never loads the rest and a count that is wrong.
3. An index for each language beside that of every language, which the hook writes after the build, and a script in the head of each page that gives Material the index of its language in place of that of every language.

## Decision

Option 3, in the hook of every website, `.github/mkdocs_blueprint.py`.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/how-each-language-searches-its-pages.dark.svg">
  <img src="../images/diagrams/how-each-language-searches-its-pages.svg" alt="How each language searches its pages: You write guide.md and guide.de.md, and roadmap.md without a German version. MkDocs builds the English and the German website with the hook of the blueprint. The German roadmap is a copy of the English page, with its text marked as English, the English page as its canonical address and noindex, and stays out of the search and the sitemap. After the build, the hook writes beside the index of every language one index for each: the English pages, and the German pages with the English ones that have no German version, at their address in de/. A German page asks for the German index and an English one for the English index.">
</picture>

- **An index for each language:** `search/search_index.en.json` holds the English pages, `search/search_index.de.json` the German ones and the English pages without a German version, at their address in `de/`, so that a German reader stays in the German menu. A page of a project website in the search of its owner's website, such as `ha-autodarts/de/games.html`, counts as German too. `search/search_index.json` keeps every language, for the search of the owner's website, which adds the index of each project. The i18n plugin no longer takes entries out of it (`reconfigure_search: false`), and a section whose page an index lacks gets one.
- **Untranslated pages are copies:** a page that the German website shows in English has its text marked as English, the English page as its canonical address and `noindex`, and stays out of the search and the sitemap; its date speaks German. The English page names no German version.
- **Full addresses:** every other page names its versions with their full addresses and `x-default`, the version of the default language.
- **A description of each page,** the start of its first paragraph that has words outside its links, at most 160 characters, unless its front matter has one; the home page of each language keeps the description of the website, and its preview card the name of the website as its title. The picture of a preview card may still show the description of the website: the social plugin starts drawing it before the hook knows the description of the page.
- **The date of the newest file** that a page includes with `--8<--`, in the page and in the sitemap.
- **No status badges on the website,** while buttons such as those of My Home Assistant stay, and German names for the switch between light and dark.
- **The template of the decision records,** and any page with `robots: noindex` in its front matter, stay out of the search and the sitemap.

## Consequences

An English page loads 420 KB of index instead of 513 KB on the blueprint's website, a German one 432 KB, and neither finds a page of the other language. The hook depends on two more parts of the plugins that are not documented as their interface: the versions of a page that the i18n plugin lists, and two methods of git-revision-date-localized that format a date. A version of a plugin that changes them stops the strict build, and the update of Renovate shows it.

The script in the head of each page redirects one request of Material, the one for `search/search_index.json`; a Material whose scripts no longer ask for it with an `XMLHttpRequest` would search every language again, so the hook then warns, which stops the strict build of the update of Material until the script follows it.
