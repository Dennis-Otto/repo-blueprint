# The steps of a website that need no generator are steps of blueprint.py

- Status: accepted, follows up [0146](0146-every-website-moves-to-zensical-before-the-maintenance-of-material-for-mkdocs-ends.md) and [0160](0160-a-trial-build-with-zensical-measures-the-move.md)
- Date: 2026-11-15

## Context

Decision 0146 moves every website to Zensical before 5 May 2027, and its first step is that the hooks that need no generator become steps of `blueprint.py`, so that they move with any generator. The trial build of decision 0160 showed exactly these as missing in Zensical, which runs no hooks of MkDocs: the page *Automation*, which `on_files` and `on_nav` wrote from `.github/workflows/`, and the sitemaps and `llms.txt`, which `on_post_build` finished. All of that code was in `.github/mkdocs_blueprint.py` and read the objects of MkDocs: its configuration, its files and its menu ([#872](https://github.com/Dennis-Otto/repo-blueprint/issues/872)).

## Options

1. **Leave the code in the hooks until the module API of Zensical is there.** For: no change before the move. Against: the move then rewrites these steps and their tests together with everything else, and they stay tied to MkDocs.
2. **Steps of `blueprint.py` that read only `site/` after the build,** with the menu of `llms.txt` from the HTML of the pages. For: no input but the website itself. Against: the menu of a page is the markup of the theme, which changes with the generator, so the map would follow Material, not the website.
3. **Steps in `blueprint/website.py` that take plain values,** the files before the build, `site/` after it and the menu as data, which the hooks call with what MkDocs knows, and the command `blueprint.py website`, which takes them for another generator. For: one copy of each step, tested once, the same website from MkDocs, and a generator with a menu of its own only hands it over. Against: the hooks still turn the objects of MkDocs into those values.

Option 3, since only it keeps the website the same today and takes the steps out of MkDocs for the move.

## Decision

- **`blueprint/website.py` holds the steps:** the page *Automation* in each language from the workflows, the settings and the pictures of the diagrams; the pages that no search engine lists taken out of both sitemaps; the sitemap of a website in several languages copied into every folder of pages; and `llms.txt` from the menu of each language. It needs nothing of MkDocs and only Python, and PyYAML for the workflows.
- **The hooks call them** with what the build knows: the configuration, the menu of each language and the pages that it left out of the search. Every repository gets the file as `.github/blueprint/website.py` beside the hooks, which fail at once without it.
- **`blueprint.py website automation DIR` and `blueprint.py website finish SITE`** take the same steps for a build with another generator: the first into a copy of `docs/` before the build, the second over `site/` after it, with the pages whose head says `noindex` and the menu from a file of JSON.
- **The website stays the same:** the build of the blueprint's website before and after this change is the same, file for file.

## Consequences

The move to Zensical keeps the page *Automation*, the sitemaps and `llms.txt` without writing them anew: a build runs the two commands around it, and the module API of Zensical, once it is there, only hands them the menu. The hooks that remain, those that change the pages while MkDocs builds them, still wait for that API, as decision 0146 says. A change of the page *Automation* or of `llms.txt` is now a change of `blueprint/website.py`, with its tests in `tests/test_website.py` and those of the hooks.
