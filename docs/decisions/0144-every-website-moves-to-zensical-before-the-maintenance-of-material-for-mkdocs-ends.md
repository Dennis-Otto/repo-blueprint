# Every website moves to Zensical before the maintenance of Material for MkDocs ends

- Status: accepted
- Date: 2026-11-12

## Context

The website of the blueprint and of every repository made from it is built with MkDocs and Material for MkDocs: `stacks/docs/requirements-docs.txt` pins `mkdocs==1.6.1` and `mkdocs-material` 9, every repository gets that lock file as `.github/docs-requirements.txt`, and `.github/mkdocs-blueprint.yml` with the hooks of `.github/mkdocs_blueprint.py` makes the website what [the page of the website](../features/website.md) promises.

The authors of Material ended its development in November 2025 ([Zensical — A modern static site generator built by the creators of Material for MkDocs](https://squidfunk.github.io/mkdocs-material/blog/2025/11/05/zensical/)): Material is in maintenance mode, they fix critical bugs and vulnerabilities through **5 May 2027**, and then its upstream maintenance ends. The same article calls MkDocs a risk of the supply chain, since it has been unmaintained since August 2024. PyPI shows it: 1.6.1 of 30 August 2024 is the latest release of `mkdocs`, and after it come only the pre-releases of 2.0, which the authors of Material call incompatible with Material and its plugins.

After 5 May 2027, a vulnerability or a break in MkDocs 1.6 or in Material, such as one by a new release of Python, Pygments or Python-Markdown, gets no fix upstream, for every website of `.github/fleet.toml` at once. No successor comes as an update of Renovate, and a stable MkDocs 2.0 would come as a routine pull request of a new major version that breaks every build ([#818](https://github.com/Dennis-Otto/repo-blueprint/issues/818)).

## What the websites need

Each hook of `.github/mkdocs_blueprint.py` and each plugin of `.github/mkdocs-blueprint.yml` and of `stacks/docs/requirements-docs.in`, with what each successor offers for it, as of 12 November 2026. Staying on MkDocs 1.6 and Material 9 keeps every line as it is today. Zensical is its release 0.1.1 of 10 November 2026, as its [list of the plugins](https://zensical.org/compatibility/plugins/) and its [page of the languages](https://zensical.org/docs/setup/language/) describe it; *another generator* stands for one such as Docusaurus, Astro Starlight or Sphinx.

| Need | Today | Zensical | Another generator |
| --- | --- | --- | --- |
| A stack of every thread when a build nearly reaches the limit of its step | hook `on_startup` | No MkDocs hook runs; its module API, in development without a date, is the place | A hook of its own, written anew |
| Downloads that try again, the stylesheet and the script of the blueprint, the links to the owner in the footer, the version of the latest release in the header, the page *Automation* in the menu | hook `on_config` | Its own privacy and social plugins, written anew, don't need the retry of Material's; the stylesheet, the script and the footer through `extra_css`, `extra_javascript` and `extra`; the version and the menu need the module API | Its configuration and a plugin of its own |
| The stylesheet and the script served, Mermaid pinned, the page *Automation* in English and German | hook `on_files` | The page can be written into `docs/` by a step before the build; the pin of Mermaid needs the module API | A step before the build |
| Pages that nobody looks for left out of the search, a page dated by the newest of its files, the preview card of a home page named after the website | hook `on_page_markdown` | The module API; the date waits for `git-revision-date-localized` | Its own date from Git, the rest a plugin |
| The pictures of the diagrams, pictures from `main` served from the checkout, a picture for each theme, videos in place of GIFs, pictures that load late, no badges, a description of each page, the language of an untranslated page | hook `on_page_content` | The module API, or a step after the build over the HTML of `site/` | A plugin of its own, or a step after the build |
| The addresses of the versions of a page in other languages, an untranslated page kept from search engines, the search in the language of the page, the version of the latest release in the link to the repository | hook `on_post_page` | A step after the build, once the languages are built | Native in Docusaurus and Starlight, the rest a step after the build |
| The sitemap without the unlisted pages and in every folder of pages, `llms.txt`, the search index of each language | hook `on_post_build` | A step after the build; it needs no hook | A step after the build |
| The 404 page of the default language at the root | hook `on_post_template` | Not needed with one build for each language | Native |
| The workflows of the page *Automation* in folds | hook `on_page_context` | Written folded by the step before the build | Written folded by the step before the build |
| The text of the pages that the hooks write, the menu for `llms.txt` | hook `on_nav` | The step before the build, and the menu from `mkdocs.yml` | The step before the build |
| The search | plugin `search` of Material | Its own search, on by default; one language for each build | Its own, or Pagefind |
| Fonts and scripts served from the website itself, without Google | plugin `privacy` of Material | Supported since 0.0.72; it doesn't reuse the cache of Material | A plugin or a step of its own |
| A preview card of each page for social media | plugin `social` of Material, with `mkdocs-material[imaging]` | Supported since 0.0.67, without the imaging libraries | A plugin of its own, or none |
| Pictures that open enlarged | plugin `glightbox`, `mkdocs-glightbox` | Supported since 0.0.35; some of its settings are ignored | A plugin of its own |
| The date of the last change of a page | plugin `git-revision-date-localized`, with `tzdata` on Windows | Planned, without a date | Native in Docusaurus and Starlight |
| A website in more than one language from `page.de.md` beside `page.md` | plugin `i18n`, `mkdocs-static-i18n` | Not on its list: one language for each project, and a switch through `extra.alternate` to the build of another; one build for each language would need a configuration for each | Native, with a folder for each language instead of a suffix |
| The Markdown: admonitions, tabs, details, tasks, emoji, snippets, footnotes and the anchors of `toc` | `markdown_extensions` | Python Markdown and its extensions, as today; the YAML tags `!ENV` and `!!python/name` of `.github/mkdocs-blueprint.yml` need a check | A Markdown of its own: every page that uses one of them is rewritten |
| The theme: a light and a dark scheme, tabs, sections, the path, the button to the top, the copy of code, the pencil to edit a page, and the fixes of contrast and underlines for WCAG 2.2 AA in `.github/mkdocs-blueprint.css` | Material 9 | Its theme takes the settings of Material, with a variant in its classic look | A theme of its own, and the fixes for WCAG 2.2 AA anew |

## Options

1. **Stay on MkDocs 1.6 and Material 9** and accept the risk: nothing changes, and from 5 May 2027 no fix comes upstream for anything in the table.
2. **Move to Zensical,** the successor that the authors of Material name and build to take an existing `mkdocs.yml`: the theme, the search, `privacy`, `social`, `glightbox` and the Markdown stay; the hooks become steps before and after the build or modules of its API; the languages wait for it.
3. **Move to another generator,** such as Docusaurus, Astro Starlight or Sphinx: every line of the table is written anew, the pages of every repository too, wherever they use the Markdown of Material, and the checks of the website learn another build.
4. **Move to MkDocs 2.0:** it has no stable release, and its pre-releases leave out the plugins and the themes that every line of the table relies on.

## Decision

Option 2, with option 1 for a stated time until it is carried out.

- **Until the move,** a rule of `.github/renovate-blueprint.json5` and `template/.github/renovate-blueprint.json5.jinja` holds `mkdocs` below 2, with its reason in a comment. Material 9 and the plugins keep their updates, since the authors of Material fix it until 5 May 2027.
- **First,** the hooks that need no generator, those that read the files before the build or `site/` after it, such as the page *Automation*, the sitemaps and `llms.txt`, become steps of `blueprint.py`, so that they move with any generator.
- **By 1 February 2027,** a look at Zensical's module API, its languages and the dates of a page decides how each remaining hook moves.
- **Before 5 May 2027,** every website is built with Zensical, as a breaking release with a migration of `mkdocs.yml`, and the rule of Renovate goes with it.
- **If Zensical can't carry the websites by then,** they stay on the last releases of MkDocs 1.6 and Material 9 until **5 November 2027** at the latest. An advisory against either without a fix ends that time at once: the blueprint then decides again, between options 2 and 3, in a new record.

[#872](https://github.com/Dennis-Otto/repo-blueprint/issues/872) tracks the move, with these dates.

## Consequences

A stable MkDocs 2.0 doesn't come as a routine pull request of Renovate, and no website breaks for it. Every update of Material 9 still comes, and so does each fix of a vulnerability. The move becomes smaller with each hook that turns into a step before or after the build, which the checks of the website (`blueprint.py site-check`, lychee and the accessibility check) keep honest, since they read `site/` and not the generator. The risk that remains is the half year after 5 May 2027, at most, and it ends with an advisory.
