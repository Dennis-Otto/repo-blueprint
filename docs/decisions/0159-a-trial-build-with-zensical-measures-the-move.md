# A trial build with Zensical measures the move, and front matter reads alike in both

- Status: accepted, follows up [0146](0146-every-website-moves-to-zensical-before-the-maintenance-of-material-for-mkdocs-ends.md)
- Date: 2026-11-15

## Context

Decision 0146 moves every website to Zensical before the upstream maintenance of Material for MkDocs ends on 5 May 2027, and it judged from the compatibility pages of Zensical what the move can carry today. [#872](https://github.com/Dennis-Otto/repo-blueprint/issues/872) asks for the move now, as far as the blueprint's own website and the tests of the template can prove it.

So the website of the blueprint was built with Zensical 0.1.1 of 10 November 2026, the latest release on PyPI on 15 November 2026, unchanged, from its `mkdocs.yml` and `.github/mkdocs-blueprint.yml`, in a virtual environment of its own:

```sh
python3 -m venv .venv-zensical
.venv-zensical/bin/pip install zensical==0.1.1
.venv-zensical/bin/zensical build -f mkdocs.yml
```

| What the build showed | What it means |
| --- | --- |
| It stopped at once: `error reading page metadata 'reference/variables.md': mapping values are not allowed in this context` | The description in the front matter of the page, which `reference.py` writes, held a colon and a space, so it was no mapping of YAML. MkDocs gives no warning for that and keeps the front matter as Markdown: the [published page](https://dennis-otto.github.io/repo-blueprint/reference/variables.html) showed a line and a heading *description: Every variable…* above its title, and its description was lost. A bug of today's website, which only Zensical named. |
| With the description in quotes, it built the website in about 4 seconds, with no warning on an English page | It reads the YAML tags `!ENV` and `!!python/name` of `.github/mkdocs-blueprint.yml`, and the Markdown of the pages with its extensions builds without a complaint. |
| 55 warnings *anchor does not exist*, every one in a German page | It builds `guide.de.md` as `guide.de.html` beside `guide.html`, without a folder `de/`, and a link of a German page to `guide.md#ein-repository-anlegen` reaches the English page, whose headings are English. The website in several languages of 0146 is still missing. |
| No page *Automation*, no `llms.txt`, no stylesheet and script of the blueprint, the pictures of the README with the paths of the repository | No MkDocs hook runs, as 0146 says: each of them is a hook of `.github/mkdocs_blueprint.py`. |
| Its plugin `privacy` downloaded the scripts of its own bundle, such as Pyodide, Ace and Plyr, and warned that it couldn't download one of Google | The strict build of the check *docs* would fail on that warning alone, before the move takes the plugin. |

## Decision

- **No website moves yet.** Without the hooks and the languages, a website built with Zensical would lose most of what [the page of the website](../features/website.md) promises, and every German page would link to English headings; decision 0146 stays as it is, with its dates.
- **Front matter reads alike in both:** the hooks of every website warn about a page whose front matter MkDocs couldn't read as a mapping of YAML, which stops the strict build of the check *docs*, and `reference.py` writes the front matter of its pages with PyYAML, which puts a value in quotes where plain YAML would read it otherwise.
- **Each look at Zensical starts with this trial build,** by 1 February 2027 at the latest, as 0146 asks: a finding that is wrong for MkDocs as well, as the front matter was, is fixed at once, and the others are written down here, against the table of 0146.

## Consequences

The page of the variables shows its title first again, with its own description, and no page of a website can lose its front matter that way unnoticed. The move to Zensical stays where 0146 put it: it waits for the module API of Zensical, the place of the hooks, and for a website in several languages. The trial build needs no change of a website, so it can be repeated with every release of Zensical.
