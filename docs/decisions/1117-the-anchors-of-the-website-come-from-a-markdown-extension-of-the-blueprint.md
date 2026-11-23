# The anchors of the website come from a Markdown extension of the blueprint

- Status: accepted, follows up [0146](0146-every-website-moves-to-zensical-before-the-maintenance-of-material-for-mkdocs-ends.md), [0160](0160-a-trial-build-with-zensical-measures-the-move.md) and [0166](0166-the-steps-of-a-website-that-need-no-generator-are-steps-of-blueprint-py.md)
- Date: 2026-11-23

## Context

`.github/mkdocs-blueprint.yml` gives the extension `toc` the slugify of pymdownx with `case: lower`, so that a heading has the anchor that GitHub gives it on the page of the file, and a link to it works in both places. That held for nearly every heading, but `strip_tags()` of `toc` ends with `' '.join(text.split())`: every run of whitespace, a no-break space (U+00A0) and a narrow no-break space (U+202F) among it, reaches the slugify as one plain space ([#1117](https://github.com/Dennis-Otto/repo-blueprint/issues/1117)).

- **A no-break space,** which French puts before `?`, `!`, `:` and `;`: GitHub drops it, the website made it a hyphen. The 21 questions of `docs/faq.fr.md` of homedarts-for-autodarts had `de-quoi-ai-je-besoin-` on the website and `de-quoi-ai-je-besoin` on GitHub, so a link to one of them could pass either its test against GitHub's anchors or the strict build, never both.
- **Two spaces,** also those that inline HTML such as `A <br> B` leaves: GitHub makes two hyphens, the website one.
- **An emoji shortcode:** GitHub takes its name, `Emoji :dart: dart` has `emoji-dart-dart`; the website dropped the emoji that pymdownx.emoji put in its place, `emoji-dart`.

No slugify can tell these apart, since it gets the text after the collapse. Decisions 0146 and 0166 take work out of the hooks of `.github/mkdocs_blueprint.py`, since Zensical runs no hook of MkDocs.

MkDocs imports the Markdown extensions while it reads its configuration, before it loads the hooks, and only by name: neither `mkdocs build`, whose script starts in the folder of the virtual environment, nor Zensical 0.1.1 finds a module beside `mkdocs.yml` or in `.github/` (measured with both on 2026-11-23), and only `python -m mkdocs` has the current folder on the path of Python.

## Options

1. **A slugify of its own:** it still gets the collapsed text, so it can't drop a no-break space that has become a plain space.
2. **`{#id}` on the headings, or another way to write the no-break space:** GitHub shows `{#id}` as text, a plain space lets `?` wrap onto a line of its own, and every author of every page would have to remember it.
3. **A hook that adds the extension in `on_config`:** it works with MkDocs, but it is lost with the move of 0146, and the anchors would quietly fall back to those of `toc` and move a second time.
4. **The extension named in `markdown_extensions`, found through `PYTHONPATH` or `python -m mkdocs`:** every command that builds the website, the preview of a person among them, would have to remember it, and a plain `mkdocs serve` would stop with *Failed to load extension*.
5. **The extension named in `markdown_extensions`, with a tag of YAML as its configuration that puts `.github` on the path of Python:** `github_anchors: !!python/object/apply:site.addsitedir [.github]`. PyYAML runs the tag while MkDocs or Zensical reads the file, before either imports an extension, and the tag gives `None`, which both take as an extension without options.

## Decision

Option 5, since only it keeps the anchors in the place that both generators read, with no step that a build has to remember:

- **`.github/github_anchors.py`** is a Markdown extension of the blueprint beside the hooks, which every repository gets with the template and which `.github/blueprint/owned.txt` lists. Its treeprocessor runs at priority 6: after `attr_list` (8), whose `{#id}` a heading keeps, and before `toc` (5) and the collection of anchors of MkDocs for its strict check at the same priority, so that the permalinks, the table of contents, the search and that check all take its ids.
- **It changes only the text that the slugify of `toc` gets:** the text of the heading as `toc` reads it, with the escapes, entities and HTML resolved and the tags and comments removed, but with its whitespace as it is, and each emoji of pymdownx.emoji as the shortcode in its title. The slugify of the configuration makes the anchor, and a heading that has an id keeps it.
- **A repeated heading keeps `_1`, `_2`,** numbered as `toc` numbers it. GitHub writes `-1`, `-2`, and counts within the file that `pymdownx.snippets` includes, the website within the page; numbering them as GitHub does would move ids that are stable today, so it is a decision of its own.
- **The tag puts the folder `.github` of the current folder on the path,** as `pymdownx.snippets` takes its files from there: every build of the blueprint starts in the root of the repository. `site.addsitedir` adds it at the end of the path, so that no installed module is shadowed, and only once, also in each build of `mkdocs serve`.

## Consequences

- On a website in French, every heading with a no-break space gets a new id, the 21 questions of `fr/faq.html` of homedarts-for-autodarts; their old ids stop working, and the fragment of the changelog says so. Every other id stays: the builds of the website of the blueprint (451 pages, 9,473 ids) and of homedarts-for-autodarts (302 pages, 8,879 ids) before and after differ only in those 21 ids.
- Zensical 0.1.1 loads the extension from the same configuration and gives the same anchors, also for a link to another page that its check of the anchors accepts, so the move of 0146 carries the anchors without a step of its own.
- A website that builds from another folder than the root of its repository, with `mkdocs build -f`, stops with *Failed to load extension 'github_anchors'*, as its snippets would miss their files.
- An icon of Material such as `:material-github:` still counts with nothing, as before: its element carries no shortcode, and GitHub keeps such a name as text.
- The tests render headings with the extensions of `.github/mkdocs-blueprint.yml` and compare them with the anchors that GitHub's renderer gave, so the tools of development have Python-Markdown and pymdown-extensions as well.

## De quoi ai-je besoin ?

This heading is the first question of the French FAQ of homedarts-for-autodarts ("What do I need?"), with the no-break space before its `?`, and the [page of the website](../features/website.md) links to it by the anchor that GitHub gives it, `de-quoi-ai-je-besoin`. Without the extension, the heading has `de-quoi-ai-je-besoin-`: should its ids ever stop reaching the check of the anchors of MkDocs or Zensical, such as when either collects them before priority 6, the strict build of this website fails on that link.
