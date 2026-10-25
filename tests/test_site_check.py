"""Tests of what a built website promises: blueprint/site_check.py, which reads the
files that MkDocs and the hooks of .github/mkdocs_blueprint.py wrote, and the command
site-check of blueprint.py, which the check docs runs after the build."""

from __future__ import annotations

import importlib.util
import random
import re
from pathlib import Path
from types import ModuleType

import pytest
from shell import BASH
from workflow_steps import SHA, run_step

from blueprint.cli import main
from blueprint.site_check import (
    BADGE,
    SNIPPET,
    Finding,
    Page,
    Picture,
    annotation,
    built_from,
    check,
    name_of,
    pictures_in,
    resolved,
    sources,
)

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://owner.github.io/demo/"
GENERATOR = '<meta name="generator" content="mkdocs-1.6.1, mkdocs-material-9.7.7">'
NOINDEX = '<meta name="robots" content="noindex, follow">'


def page(
    lang: str,
    *,
    canonical: str | None = None,
    alternates: dict[str, str] | None = None,
    head: str = GENERATOR,
    body: str = "<h1>Demo</h1>",
) -> str:
    """A page as Material writes it, with the head that the hooks leave."""
    links = f'<link rel="canonical" href="{canonical}">' if canonical else ""
    links += "".join(
        f'<link rel="alternate" href="{href}" hreflang="{language}">'
        for language, href in (alternates or {}).items()
    )
    return (
        f'<!doctype html>\n<html lang="{lang}" class="no-js">\n<head>{head}{links}'
        f"<title>Demo</title></head>\n<body>{body}</body>\n</html>\n"
    )


def versions(name: str) -> dict[str, str]:
    """The full addresses of the versions of a translated page."""
    return {
        "en": BASE + name,
        "de": BASE + "de/" + name,
        "x-default": BASE + name,
    }


SITEMAP = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>{BASE}</loc></url>
<url><loc>{BASE}guide.html</loc></url>
<url><loc>{BASE}de/</loc></url>
<url><loc> https://elsewhere.example/page.html </loc></url>
<url><loc>{BASE}gone.html</loc></url>
</urlset>
"""


def two_languages() -> dict[str, str]:
    """A website in English and German as the hooks leave it: guide.html translated,
    record.html shown untranslated in German, the 404 page of the default language
    at the root, with the relative versions that Material writes into it, and a page
    of HTML of the project that MkDocs only copied."""
    return {
        "index.html": page(
            "en", canonical=BASE + "index.html", alternates=versions("index.html")
        ),
        "guide.html": page(
            "en", canonical=BASE + "guide.html", alternates=versions("guide.html")
        ),
        "record.html": page("en", canonical=BASE + "record.html"),
        "de/index.html": page(
            "de", canonical=BASE + "de/index.html", alternates=versions("index.html")
        ),
        "de/guide.html": page(
            "de", canonical=BASE + "de/guide.html", alternates=versions("guide.html")
        ),
        "de/record.html": page(
            "de",
            canonical=BASE + "record.html",
            head=GENERATOR + NOINDEX,
            body='<div lang="en"><h1>Record</h1></div>',
        ),
        # Only in German, with no page of the default language beside it.
        "de/only.html": page("de", canonical=BASE + "de/only.html"),
        "404.html": page(
            "en", alternates={"en": "/demo/index.html", "de": "/demo/de/index.html"}
        ),
        "dashboard/index.html": (
            '<meta http-equiv="refresh" content="0; url=https://example.org/">'
        ),
        "sitemap.xml": SITEMAP,
        "de/sitemap.xml": SITEMAP,
        "dashboard/sitemap.xml": SITEMAP,
    }


def hooks() -> ModuleType:
    """The hooks of the website, .github/mkdocs_blueprint.py."""
    spec = importlib.util.spec_from_file_location(
        "mkdocs_blueprint", ROOT / ".github/mkdocs_blueprint.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def built(tmp_path: Path, files: dict[str, str]) -> Path:
    site = tmp_path / "site"
    for name, text in files.items():
        (site / name).parent.mkdir(parents=True, exist_ok=True)
        (site / name).write_text(text, encoding="utf-8", newline="\n")
    return site


def messages(site: Path) -> list[str]:
    return [f"{finding.path}: {finding.message}" for finding in check(site).findings]


def test_a_website_in_two_languages_keeps_every_promise(tmp_path: Path) -> None:
    site = check(built(tmp_path, two_languages()))

    assert site.findings == ()
    assert site.default == "en"
    assert site.further == ("de",)
    # The path of the address of a project website, from which its 404 page links.
    assert site.root == "/demo/"


def test_a_folder_of_pages_without_its_sitemap_fails(tmp_path: Path) -> None:
    files = two_languages()
    del files["de/sitemap.xml"]

    assert messages(built(tmp_path, files)) == [
        "de/sitemap.xml: the sitemap is missing, which the language switch of the "
        "pages of this folder reads"
    ]


def test_a_sitemap_that_differs_from_the_one_at_the_root_fails(
    tmp_path: Path,
) -> None:
    files = two_languages()
    files["dashboard/sitemap.xml"] = "<urlset></urlset>\n"

    assert messages(built(tmp_path, files)) == [
        "dashboard/sitemap.xml: differs from the sitemap.xml at the root"
    ]


def test_a_website_in_two_languages_needs_its_sitemap(tmp_path: Path) -> None:
    files = two_languages()
    for name in ("sitemap.xml", "de/sitemap.xml", "dashboard/sitemap.xml"):
        del files[name]

    assert messages(built(tmp_path, files)) == ["sitemap.xml: the sitemap is missing"]


def test_the_sitemap_lists_no_page_that_search_engines_leave_out(
    tmp_path: Path,
) -> None:
    files = two_languages()
    listed = SITEMAP.replace(
        "</urlset>", f"<url><loc>{BASE}de/record.html</loc></url></urlset>"
    )
    for name in ("sitemap.xml", "de/sitemap.xml", "dashboard/sitemap.xml"):
        files[name] = listed

    assert messages(built(tmp_path, files)) == [
        f"sitemap.xml: lists {BASE}de/record.html, which no search engine may list"
    ]


@pytest.mark.parametrize(
    ("lang", "found"),
    [
        ("de", '404.html: is in the language "de", not in the default one, "en"'),
        (None, "404.html: the 404 page is missing"),
    ],
)
def test_the_404_page_at_the_root_is_in_the_default_language(
    tmp_path: Path, lang: str | None, found: str
) -> None:
    files = two_languages()
    if lang:
        files["404.html"] = page(lang)
    else:
        del files["404.html"]

    assert messages(built(tmp_path, files)) == [found]


def test_every_page_that_mkdocs_built_names_one_canonical_address(
    tmp_path: Path,
) -> None:
    files = two_languages()
    files["guide.html"] = files["guide.html"].replace(
        "<title>", f'<link rel="canonical" href="{BASE}other.html"><title>'
    )
    files["de/only.html"] = page("de")

    assert messages(built(tmp_path, files)) == [
        "de/only.html: no canonical address",
        "guide.html: 2 canonical addresses; a page names one",
    ]


def test_a_website_without_an_address_needs_no_canonical_one(
    tmp_path: Path,
) -> None:
    # A website without site_url in mkdocs.yml, in one language: no page names a
    # canonical address, and no sitemap or 404 page is needed.
    site = check(
        built(tmp_path, {"index.html": page("en"), "guide/index.html": page("en")})
    )

    assert site == type(site)("en", (), "/", ())


def test_the_versions_in_other_languages_have_full_addresses(
    tmp_path: Path,
) -> None:
    files = two_languages()
    files["guide.html"] = page(
        "en",
        canonical=BASE + "guide.html",
        alternates={"en": "guide.html", "de": "de/guide.html"},
    )

    assert messages(built(tmp_path, files)) == [
        "guide.html: the versions in other languages need full addresses, which "
        "search engines take, not de/guide.html, guide.html",
        "guide.html: x-default names nothing, not the version of the default "
        "language, guide.html",
    ]


def test_x_default_names_the_version_of_the_default_language(
    tmp_path: Path,
) -> None:
    files = two_languages()
    files["de/guide.html"] = page(
        "de",
        canonical=BASE + "de/guide.html",
        alternates={"de": BASE + "de/guide.html", "x-default": BASE + "de/guide.html"},
    )

    assert messages(built(tmp_path, files)) == [
        f"de/guide.html: x-default names {BASE}de/guide.html, not the version of the "
        "default language, which names no en"
    ]


def test_an_untranslated_page_reads_in_the_default_language_and_stays_unlisted(
    tmp_path: Path,
) -> None:
    files = two_languages()
    files["de/record.html"] = page(
        "de", canonical=BASE + "record.html", alternates=versions("record.html")
    )

    assert messages(built(tmp_path, files)) == [
        'de/record.html: is untranslated, so its text needs <div lang="en">, in '
        "whose language a screen reader reads it",
        "de/record.html: is untranslated, a copy of the page of the default "
        "language, and names no versions of its own",
        "de/record.html: is untranslated, a copy that no search engine may list, "
        'and needs <meta name="robots" content="noindex, follow">',
    ]


def test_only_pages_that_mkdocs_built_count(tmp_path: Path) -> None:
    files = two_languages()
    # A page of HTML of the project in a folder of a further language, beside a page
    # of the default language, and a folder whose home page MkDocs didn't build.
    files["de/copied.html"] = f'<link rel="canonical" href="{BASE}copied.html">'
    files["copied.html"] = page("en", canonical=BASE + "copied.html")
    files["fr/index.html"] = '<html lang="fr"><h1>Bonjour</h1></html>'
    files["fr/sitemap.xml"] = SITEMAP

    site = check(built(tmp_path, files))

    assert site.findings == ()
    assert site.further == ("de",)


def test_no_page_has_the_browser_of_its_reader_ask_github(tmp_path: Path) -> None:
    files = two_languages()
    link = (
        '<a href="https://github.com/owner/demo" title="Go to repository" '
        'class="md-source" data-md-component="source">owner/demo</a>'
    )
    files["guide.html"] = page(
        "en",
        canonical=BASE + "guide.html",
        alternates=versions("guide.html"),
        body=link + link,
    )
    files["404.html"] = page("en", body=link)
    # A page of HTML of the project, which MkDocs only copied, is the project's.
    files["copied.html"] = link
    asks = (
        "has the browser of every reader ask the API of GitHub for the numbers of "
        'the repository: data-md-component="source" on its link to the repository, '
        "which the hooks of the website take away"
    )

    assert messages(built(tmp_path, files)) == [
        f"404.html: {asks}",
        f"guide.html: {asks}",
    ]


def test_a_website_without_a_home_page_fails(tmp_path: Path) -> None:
    site = check(tmp_path / "nothing")

    assert site.findings == (Finding("index.html", "the home page is missing"),)


def test_a_home_page_without_a_language_names_no_default(tmp_path: Path) -> None:
    files = {
        "index.html": "<p>Demo</p>",
        "guide.html": page("en", alternates={"en": BASE + "guide.html"}),
    }

    site = check(built(tmp_path, files))

    assert site.default == ""
    assert site.findings == ()


def test_the_address_of_a_website_of_the_owner_is_the_root(tmp_path: Path) -> None:
    site = check(
        built(
            tmp_path,
            {"index.html": page("en", canonical="https://owner.github.io/")},
        )
    )

    assert site.root == "/"
    assert site.findings == ()


def test_a_page_says_what_it_is() -> None:
    found = Page()
    found.feed(
        '<html lang="en"><head><meta name="viewport" content="width=device-width">'
        '<meta name="ROBOTS" content="NOINDEX">'
        '<link rel="alternate" type="application/rss+xml" href="feed.xml">'
        '<link rel="canonical alternate" hreflang="en" href="a.html"></head>'
        '<body><html lang="de"><span lang="fr">Bonjour</span><br/></body></html>'
    )

    assert found.lang == "en"
    assert found.unlisted
    assert not found.built
    assert found.canonical == ["a.html"]
    assert found.alternates == [("en", "a.html")]
    assert found.parts == {"fr"}
    assert not found.asks_github


# What a page loads at once, as Material and the hooks write it: its stylesheets,
# among them the fonts of another server, its scripts, the configuration of the
# search and the script that has it load the index of the page's language.
HEAD = (
    GENERATOR
    + '<link rel="stylesheet" href="../assets/main.css">'
    + '<link rel="stylesheet" href="https://fonts.example/css">'
    + '<link rel="icon" href="../assets/icon.png">'
    + '<script>(function(){var a=new URL("../search/search_index.json",location.href)'
    + '.href,b=new URL("../search/search_index.de.json",location.href).href})()'
    + "</script>"
)
SCRIPTS = (
    '<script id="__config" type="application/json">{"base": "..", "search": '
    '"../assets/worker.js"}</script>'
    '<script src="../assets/bundle.js"></script>'
    '<script src="../assets/bundle.js?v=1#again"></script>'
)


def noise(size: int, seed: int = 1) -> bytes:
    """Bytes that no compression makes smaller."""
    return random.Random(seed).randbytes(size)


def heavy_site(tmp_path: Path) -> Path:
    files = two_languages()
    files["de/guide.html"] = page(
        "de",
        canonical=BASE + "de/guide.html",
        alternates=versions("guide.html"),
        head=HEAD,
        body=(
            '<img src="../images/hero.webp#only-light" alt="Hero">'
            '<img src="../images/far.png" loading="lazy" alt="Far">'
            '<video class="blueprint-video" src="../images/a.mp4" '
            'poster="../images/a.webp" preload="none"></video>'
            '<img src="/demo/images/rooted.png" alt="From the root">'
            '<img src="../../outside.png" alt="Outside">'
            '<img src="../images/missing.png" alt="Missing">'
            '<img alt="Nothing">'
            '<pre class="mermaid"><code>flowchart TB</code></pre>' + SCRIPTS
        ),
    )
    # A diagram drawn live, and a large picture.
    files["record.html"] = page(
        "en",
        canonical=BASE + "record.html",
        body='<div class="mermaid"></div><img src="images/big.png" alt="Big">',
    )
    site = built(tmp_path, files)
    for name, size in (
        ("assets/main.css", 30_000),
        ("assets/icon.png", 900_000),
        ("assets/worker.js", 12_000),
        ("assets/bundle.js", 40_000),
        ("search/search_index.de.json", 200_000),
        ("search/search_index.json", 900_000),
        ("images/hero.webp", 60_000),
        ("images/far.png", 2_000_000),
        ("images/a.webp", 50_000),
        ("images/rooted.png", 900_000),
        ("images/big.png", 1_300_000),
        ("assets/external/unpkg.com/mermaid@11.17.2/dist/mermaid.min.js", 0),
    ):
        (site / name).parent.mkdir(parents=True, exist_ok=True)
        (site / name).write_bytes(noise(size))
    (tmp_path / "outside.png").write_bytes(noise(900_000))
    return site


def test_no_page_loads_more_than_its_budget_at_once(tmp_path: Path) -> None:
    site = heavy_site(tmp_path)
    mermaid = site / "assets/external/unpkg.com/mermaid@11.17.2/dist/mermaid.min.js"
    mermaid.write_bytes(noise(850_000))

    found = messages(site)

    # The page, its stylesheet, its scripts once, the search with the German index,
    # the first picture and the poster of the video, and Mermaid: 1,242 KB and the
    # page itself, without the icon, the picture that waits for the
    # reader and every address that leads to no file of the website.
    assert len(found) == 2
    assert re.fullmatch(
        r"de/guide\.html: loads 1,24\d KB at once, more than the 1,200 KB that a "
        r"page may on a slow phone; the most: assets/external/unpkg\.com/mermaid@"
        r"11\.17\.2/dist/mermaid\.min\.js \(850 KB\), search/search_index\.de\.json "
        r"\(200 KB\), images/hero\.webp \(60 KB\); it draws a diagram live from a "
        r"```mermaid block, which loads Mermaid: show the pictures of "
        r"scripts/diagrams\.sh in its place",
        found[0],
    ), found[0]
    assert found[1] == (
        "record.html: loads 2,151 KB at once, more than the 1,200 KB that a page may "
        "on a slow phone; the most: images/big.png (1,300 KB), assets/external/"
        "unpkg.com/mermaid@11.17.2/dist/mermaid.min.js (850 KB), record.html (0 KB); "
        "it draws a diagram live from a ```mermaid block, which loads Mermaid: show "
        "the pictures of scripts/diagrams.sh in its place"
    )


def test_a_page_within_its_budget_passes(tmp_path: Path) -> None:
    site = heavy_site(tmp_path)
    (site / "images/big.png").write_bytes(noise(100))
    # A website without the script of Mermaid, which its diagrams would load.
    next(site.glob("assets/external/unpkg.com/mermaid@*/dist/mermaid.min.js")).unlink()

    # The German guide loads 392 KB.
    assert messages(site) == []


def test_the_search_of_a_page_loads_its_worker_and_its_index() -> None:
    def search(config: str, scripts: str = "") -> list[str]:
        found = Page()
        found.feed(
            f'<script id="__config" type="application/json">{config}</script>'
            f"<script>{scripts}</script>"
        )
        return found.search

    assert search('{"base": "..", "search": "w.js"}') == [
        "w.js",
        "../search/search_index.json",
    ]
    assert search('{"search": "w.js"}', HEAD.split("<script>")[1]) == [
        "w.js",
        "../search/search_index.de.json",
    ]
    assert search('{"base": "."}') == []
    assert search("[1]") == []
    assert search("{not json") == []


def test_an_annotation_names_the_file_on_one_line() -> None:
    finding = Finding("de/100%.html", "first\r\nsecond")

    assert annotation(finding, "site") == (
        "::error title=What the website promises::site/de/100%25.html: "
        "first%0D%0Asecond"
    )


def test_the_command_passes_a_website_that_keeps_its_promises(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    built(tmp_path, two_languages())
    output = tmp_path / "output"
    output.write_text("before=1\n", encoding="utf-8")

    assert main(["site-check", "site/", "--output", str(output)], root=tmp_path) == 0

    assert capsys.readouterr().out == (
        "The website in site keeps what its hooks promise (en de).\n"
    )
    # The further languages and the path of the address, for the steps that follow.
    assert output.read_text(encoding="utf-8") == (
        "before=1\nlanguages=de\nroot=/demo/\n"
    )


def test_the_command_names_a_website_in_one_language(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    built(tmp_path, {"index.html": "<p>Demo</p>"})

    assert main(["site-check", "site"], root=tmp_path) == 0

    assert "keeps what its hooks promise (one language)" in capsys.readouterr().out


@pytest.mark.parametrize("actions", [False, True])
def test_the_command_names_every_broken_promise(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    actions: bool,
) -> None:
    files = two_languages()
    del files["de/sitemap.xml"]
    built(tmp_path, files)
    if actions:
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
    else:
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)

    assert main(["site-check", "site"], root=tmp_path) == 1

    out = capsys.readouterr().out
    assert out.startswith(
        "site/de/sitemap.xml: the sitemap is missing, which the language switch of "
        "the pages of this folder reads\n"
    )
    assert ("::error title=What the website promises::site/de/sitemap.xml" in out) is (
        actions
    )
    assert "1 file(s) of the website break what the hooks of" in out
    assert "report it to the blueprint" in out


def test_the_command_fails_when_it_cant_write_its_outputs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    built(tmp_path, two_languages())

    assert main(["site-check", "site", "--output", str(tmp_path)], root=tmp_path) == 2

    assert capsys.readouterr().err.startswith("blueprint.py: ")


# The published website, as the job that publishes it asks for it: a fake curl answers
# every address with a page, but those that end with BROKEN, and an address that leads
# nowhere with the status in MISSING.
CURL = r"""url="${@: -1}"
printf '%s\n' "curl $url" >> "$STUB_CALLS"
if [[ "$*" == *--write-out* ]]; then
  printf '%s' "${MISSING:-404}"
  exit 0
fi
if [[ -n "${BROKEN:-}" && "$url" == *"$BROKEN" ]]; then
  echo "curl: (22) The requested URL returned error: 404" >&2
  exit 22
fi
while [[ "$1" != --output ]]; do
  shift
done
printf '<!doctype html>\n<html lang="en"><title>Demo</title></html>\n' > "$2"
"""
PAGE_URL = "https://owner.github.io/demo"
MISSING_PAGE = f"{PAGE_URL}/no-such-page-{SHA}"


@pytest.mark.skipif(BASH is None, reason="the steps run in bash, Git Bash on Windows")
@pytest.mark.parametrize("workflow", ["docs.yml", "dashboard.yml"])
@pytest.mark.parametrize(
    ("broken", "missing", "failed"),
    [
        ("", "404", ""),
        ("/de/", "404", f"{PAGE_URL}/de/ answers with no page"),
        ("", "200", f"{MISSING_PAGE} answers with the status 200, not 404"),
    ],
)
def test_the_job_that_publishes_asks_the_website_for_its_pages(
    tmp_path: Path, workflow: str, broken: str, missing: str, failed: str
) -> None:
    result = run_step(
        tmp_path,
        workflow,
        "deploy",
        "Ask the published website for its pages",
        env={
            "PAGE_URL": PAGE_URL,
            # A language that no folder of a website can have is left out.
            "LANGUAGES": "de $(touch x)",
            "BROKEN": broken,
            "MISSING": missing,
        },
        stubs={"curl": CURL},
    )

    assert result.stubbed == [
        f"curl {PAGE_URL}/",
        f"curl {PAGE_URL}/de/",
        f"curl {MISSING_PAGE}",
    ]
    assert result.returncode == (1 if failed else 0), result.stdout + result.stderr
    if failed:
        assert f"::error title=The published website::{failed}" in result.stdout
    else:
        assert result.summary == (
            f"- {PAGE_URL}/ answers with its page.\n"
            f"- {PAGE_URL}/de/ answers with its page.\n"
            f"- {MISSING_PAGE} answers with 404, as an address that leads nowhere"
            " does.\n"
        )


@pytest.mark.skipif(BASH is None, reason="the steps run in bash, Git Bash on Windows")
@pytest.mark.parametrize(("root", "inside"), [("/demo/", "demo/"), ("/", "")])
def test_the_address_of_the_website_leads_to_its_files(
    tmp_path: Path, root: str, inside: str
) -> None:
    # The 404 page links /demo/assets/... for the website at /demo/.
    result = run_step(
        tmp_path,
        "docs.yml",
        "docs",
        "Lay out the address of the website",
        env={"ROOT": root},
        files={"site/assets/style.css": "body {}\n"},
    )

    assert result.returncode == 0, result.stderr
    style = result.runner_temp / "address" / inside / "assets/style.css"
    assert style.read_text(encoding="utf-8") == "body {}\n"


# The pictures of a page: its Markdown, the parts of the README that it includes, and
# what the plugins and the hooks of the website make of them.

# The README of a project, with a part that a page of the website includes: a hero, a
# picture for each scheme from main of the repository, one in an item of a list and
# one of Markdown, and what shows no picture: a badge, a comment and code.
README = """# Demo

[![CI](https://github.com/owner/demo/actions/workflows/ci.yml/badge.svg)](https://github.com/owner/demo/actions)

<!-- --8<-- [start:how] -->
<p align="center"><img src="docs/assets/logo.png" alt="Logo"></p>

A first analysis looks like this:

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/owner/demo/main/docs/images/analysis-dark.webp">
  <img src="https://raw.githubusercontent.com/owner/demo/main/docs/images/analysis-light.webp" alt="A first analysis">
</picture>

1. Run it once:

   <img src="docs/images/dry-run.png" alt="The dry run">

![The settings](docs/images/settings.png "Settings")

<!-- <img src="docs/images/old.png" alt="Old"> -->

```html
<img src="docs/images/example.png" alt="Example">
```

Write `![text](docs/images/inline.png)` for a picture.
<!-- --8<-- [end:how] -->

![Outside the part](docs/images/outside.png)
"""


def article(content: str) -> str:
    """A page of Material with its content in its article, and the logo of the theme
    in the header."""
    return page(
        "en",
        body='<header><img src="assets/logo.png" alt="Logo"></header>'
        f'<article class="md-content__inner md-typeset">{content}</article>',
    )


# The page that includes the part of the README, as the plugins and the hooks leave
# it: the picture for each scheme from the checkout, each in the link of the
# lightbox.
HEADING = (
    '<h1 id="how">How it works<a class="headerlink" href="#how">'
    "\N{PILCROW SIGN}</a></h1>"
)
KEPT = (
    HEADING
    + '<p align="center"><img src="assets/logo.png" alt="Logo" fetchpriority="high">'
    "</p><p>A first analysis looks like this:</p>\n"
    '<p><a class="glightbox" data-gallery="light"><img src="images/analysis-light.webp'
    '#only-light" alt="A first analysis"></a><a class="glightbox" data-gallery="dark">'
    '<img src="images/analysis-dark.webp#only-dark" alt="A first analysis"></a></p>\n'
    '<ol><li><p>Run it once:</p><p><a class="glightbox"><img src="images/dry-run.png"'
    ' alt="The dry run" loading="lazy"></a></p></li></ol>\n'
    '<p><img src="images/settings.png" alt="The settings" title="Settings"></p>'
)
# The same page from a lightbox that took every picture out with its link, as
# mkdocs-glightbox did with selectolax 1.0.0 and 1.0.1.
EMPTIED = (
    HEADING + "<p></p>"
    "<p>A first analysis looks like this:</p>\n<p></p>\n"
    "<ol><li><p>Run it once:</p><p> </p></li></ol>\n"
    '<p><img src="images/settings.png" alt="The settings" title="Settings"></p>'
)


def project(tmp_path: Path, content: str) -> Path:
    """A repository whose page how.md includes the part how of its README, and the
    website that MkDocs built of it, with content in the article of the page."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "README.md").write_text(README, encoding="utf-8")
    (tmp_path / "docs/how.md").write_text(
        '# How it works\n\n--8<-- "README.md:how"\n', encoding="utf-8"
    )
    return built(tmp_path, {"index.html": page("en"), "how.html": article(content)})


def test_a_page_that_keeps_every_picture_of_its_markdown_passes(
    tmp_path: Path,
) -> None:
    site = project(tmp_path, KEPT)

    assert check(site, tmp_path).findings == ()


def test_a_page_that_lost_pictures_of_its_markdown_names_each(tmp_path: Path) -> None:
    # The live websites of issue-assistant and homedarts-for-autodarts showed an
    # empty paragraph in place of each screenshot of the README, and the check of
    # the website passed.
    site = project(tmp_path, EMPTIED)

    assert check(site).findings == tuple(
        Finding("how.html", message)
        for message in (
            'has an empty paragraph after "How it works": a plugin or a hook took out '
            "what it held, such as a picture",
            'has an empty paragraph after "A first analysis looks like this:": a '
            "plugin or a hook took out what it held, such as a picture",
            'has an empty paragraph after "Run it once:": a plugin or a hook took out '
            "what it held, such as a picture",
        )
    )
    lost = [
        f"{finding.path}: {finding.message}"
        for finding in check(site, tmp_path).findings
        if "lacks" in finding.message
    ]
    # The logo of the theme in the header makes up for no picture of the content.
    assert lost == [
        f"how.html: lacks the picture {address} that README.md shows: a plugin or a "
        "hook took it out of the page, as mkdocs-glightbox did with selectolax 1.0.0 "
        "and 1.0.1"
        for address in (
            "docs/assets/logo.png",
            "https://raw.githubusercontent.com/owner/demo/main/docs/images/"
            "analysis-light.webp",
            "docs/images/dry-run.png",
        )
    ]


def test_a_picture_may_show_as_the_website_has_it(tmp_path: Path) -> None:
    # A GIF as its video, a picture of another server as the privacy plugin
    # downloads it, one in a further language, one by its text alone, and the picture
    # of a diagram on a page that a hook of the project has draw it live.
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/shown.md").write_text(
        "![The recording](images/copier-copy.gif)\n"
        '<img src="https://example.org/shot.png?size=2" alt="">\n'
        "![The screen](images/screen.png)\n"
        '<img src="https://example.org/chart" alt="A   chart">\n'
        '<img src="images/diagrams/flow.svg" alt="Flow">\n'
        '<img src="data:image/png;base64,AAAA" alt="">\n'
        "![CI](https://img.shields.io/badge/ci-passing-green)\n"
        "<picture><source srcset=''></picture>\n",
        encoding="utf-8",
    )
    (tmp_path / "docs/drawn.md").write_text(
        '<img src="images/diagrams/flow.svg" alt="Flow">\n', encoding="utf-8"
    )
    shown = (
        '<video class="blueprint-video" src="images/copier-copy.mp4" '
        'poster="images/copier-copy.webp" aria-label="The recording"></video>'
        '<p><img src="assets/external/example.org/shot.3f2a9c1b.png"></p>'
        '<p><img src="images/screen.de.png" alt="Der Bildschirm"></p>'
        '<p><img src="assets/external/example.org/other.png" alt="A chart"></p>'
        '<pre class="mermaid"><code>flowchart TB</code></pre>'
    )
    site = built(
        tmp_path,
        {
            "index.html": page("en"),
            "shown.html": article(shown),
            "drawn.html": article("<p>The flow:</p>"),
        },
    )

    assert messages(site) == []
    assert [finding.message for finding in check(site, tmp_path).findings] == [
        "lacks the picture images/diagrams/flow.svg that docs/drawn.md shows: a "
        "plugin or a hook took it out of the page, as mkdocs-glightbox did with "
        "selectolax 1.0.0 and 1.0.1"
    ]


@pytest.mark.parametrize(
    ("source", "languages", "page_of"),
    [
        ("guide.md", ("en",), "guide.html"),
        ("guide.md", ("en",), "guide/index.html"),
        ("index.md", ("en",), "index.html"),
        ("sub/README.md", ("en",), "sub/index.html"),
        ("guide.de.md", ("en", "de"), "de/guide.html"),
        ("sub/guide.de.md", ("en", "de"), "de/sub/guide.html"),
        ("guide.en.md", ("en", "de"), "guide.html"),
        ("guide.de.md", ("en",), "guide.de.html"),
    ],
)
def test_each_file_of_markdown_leads_to_the_page_built_from_it(
    source: str, languages: tuple[str, ...], page_of: str
) -> None:
    built_page = Page()
    built_page.feed(page("en"))
    copied = Page()
    copied.feed("<p>Copied</p>")
    pages = {page_of: built_page, "other.html": built_page, "copy.html": copied}

    assert built_from(source, languages, pages) == page_of
    # A file of which MkDocs built no page, and a page of HTML that it only copied.
    assert built_from("missing.md", languages, pages) is None
    assert built_from("copy.md", languages, pages) is None


def test_a_folder_with_an_index_builds_its_page_from_it(tmp_path: Path) -> None:
    # MkDocs leaves README.md out of a folder with index.md, in every language.
    docs = tmp_path / "docs"
    (docs / "sub").mkdir(parents=True)
    names = ("README.md", "index.md", "README.de.md", "index.de.md", "zz.md")
    for name in (*names, "sub/README.md", "unbuilt.md"):
        (docs / name).write_text(name, encoding="utf-8")
    built_page = Page()
    built_page.feed(page("en"))
    built_pages = ("index.html", "de/index.html", "sub/index.html", "zz.html")
    pages = dict.fromkeys(built_pages, built_page)

    found = sources(docs, ("en", "de"), pages)

    assert {
        name: path.relative_to(docs).as_posix() for name, path in found.items()
    } == {
        "de/index.html": "index.de.md",
        "index.html": "index.md",
        "sub/index.html": "sub/README.md",
        "zz.html": "zz.md",
    }


def test_a_page_includes_the_files_of_its_lines_as_the_snippets_do(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    files = {
        "README.md": (
            "Top\n<!-- --8<-- [start:part] -->\nIn part\n<!-- --8<-- [start:other] -->"
            "\nIn other\n<!-- --8<-- [end:other] -->\n<!-- --8<-- [end:part] -->\n"
            "<!-- --8<-- [end:late] -->\n<!-- --8<-- [start:late] -->\nLate\n"
            "<!-- --8<-- [start:open] -->\nBottom\n"
        ),
        "LICENSE.md": "License\n",
        "lines.md": "one\ntwo\nthree\nfour\n",
        "docs/page.md": (
            "Intro\n"
            '--8<-- "README.md:part"\n'
            ';--8<-- "README.md"\n'
            "--8<--\n"
            "LICENSE.md\n"
            ";README.md\n"
            "\n"
            "lines.md:2:3\n"
            '--8<-- "README.md"\n'
            "--8<--\n"
            '--8<-- "missing.md"\n'
            '--8<-- "../outside.md"\n'
            '--8<-- "docs/page.md"\n'
            '--8<-- "lines.md:3"\n'
            '--8<-- "lines.md::1"\n'
            '--8<-- "README.md:late"\n'
            '--8<-- "README.md:open"\n'
            '--8<-- "https://example.org/remote.md"\n'
            '--8<-- "README.md"\n'
        ),
    }
    for name, text in files.items():
        (root / name).write_text(text, encoding="utf-8")
    (tmp_path / "outside.md").write_text("Outside\n", encoding="utf-8")
    page_md = (root / "docs/page.md").resolve()
    readme = (root / "README.md").resolve()
    license_md = (root / "LICENSE.md").resolve()
    lines_md = (root / "lines.md").resolve()

    assert resolved(root / "docs/page.md", root) == [
        ("Intro", page_md),
        ("In part", readme),
        ("In other", readme),
        (';--8<-- "README.md"', page_md),
        ("License", license_md),
        ("two", lines_md),
        ("three", lines_md),
        ("three", lines_md),
        ("four", lines_md),
        ("one", lines_md),
        # A part without its end goes on to the end of the file.
        ("Bottom", readme),
        ("Top", readme),
        ("In part", readme),
        ("In other", readme),
        ("Late", readme),
        ("Bottom", readme),
    ]


def test_the_pictures_of_markdown_are_those_outside_of_comments_and_code(
    tmp_path: Path,
) -> None:
    page_md, readme = tmp_path / "page.md", tmp_path / "README.md"
    lines = [
        ("~~~", page_md),
        ("```", page_md),
        ("![In code](images/code.png)", page_md),
        ("~~~~", page_md),
        ("![After the code](images/after.png)", page_md),
        ("```python", page_md),
        ("```python", page_md),
        ("<img src='images/still-code.png'>", page_md),
        ("```", page_md),
        # The video of a page is no picture of it.
        ('<video><source src="images/clip.mp4"></video>', page_md),
        ("Use ``![a `b`](images/span.png)`` to show one.", readme),
        (r"![A \[draft\]](<images/draft.png> 'The draft')", readme),
        ("<picture><source srcset='images/a.dark.png 1x, images/b.png 2x'>", readme),
        ('<img src="images/a.png" alt="A &amp; B"></picture>', readme),
    ]

    assert pictures_in(lines) == [
        Picture("images/after.png", "After the code", frozenset({"after"}), page_md),
        Picture("images/draft.png", "A [draft]", frozenset({"draft"}), readme),
        Picture("images/a.png", "A & B", frozenset({"a", "a.dark", "b"}), readme),
    ]


@pytest.mark.parametrize(
    ("address", "name"),
    [
        ("images/guide.png", "guide"),
        ("images/guide.de.png#only-dark", "guide"),
        ("https://example.org/Guide.PNG?raw=true", "guide"),
        ("assets/external/example.org/guide.1a2b3c4d.png", "guide"),
        ("assets/external/example.org/guide.de.1a2b3c4d.png", "guide"),
        ("images/diagram.dark.svg", "diagram.dark"),
        ("images/a%20b.webp", "a b"),
        ("https://github.com/user-attachments/assets/0f1e", "0f1e"),
        ("images/.de.png", ".de"),
    ],
)
def test_a_picture_has_one_name_in_the_markdown_and_on_the_website(
    address: str, name: str
) -> None:
    assert name_of(address) == name


def test_the_content_of_a_page_is_its_article() -> None:
    found = Page()
    found.feed(
        '<html><body><header><img src="logo.png" alt="Logo"></header><p></p>'
        '<article class="md-content__inner md-typeset"><p>Before</p><p>\n</p>'
        "<article><p>Nested</p></article><p><br></p>"
        '<script>var a = "<p></p>";</script><p></p>'
        "<p><video><source src='clip.mp4'></video>"
        "<img srcset='a.png 1x, , b.png 2x' alt='Two'></p></article>"
        '<img src="footer.png"></body></html>'
    )

    assert found.content.names == {"clip", "a", "b"}
    assert found.content.texts == {"Two"}
    assert found.content.empty == ["Before", "Nested"]
    # The whole page, for one without an article of Material.
    assert found.whole.names == {"logo", "clip", "a", "b", "footer"}
    assert found.whole.empty == ["the start of the page", "Before", "Nested"]
    plain = Page()
    plain.feed('<p><img src="a.png"></p>')
    assert plain.content is plain.whole


def test_the_check_reads_the_markdown_as_the_hooks_do() -> None:
    # The badges that the hooks take out, and the lines that include files.
    module = hooks()

    assert BADGE.pattern == module.BADGE.pattern
    assert BADGE.flags == module.BADGE.flags
    assert SNIPPET.pattern == module.SNIPPET.pattern


def test_the_command_names_a_picture_that_a_page_lost(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project(tmp_path, EMPTIED)
    # The Markdown of the pages in a folder of another name.
    (tmp_path / "docs").rename(tmp_path / "pages")

    assert main(["site-check", "site", "--docs", "pages"], root=tmp_path) == 1

    out = capsys.readouterr().out
    assert (
        "site/how.html: lacks the picture docs/images/dry-run.png that README.md shows"
        in out
    )
    assert "A page that lacks a picture of its Markdown, or has an empty" in out


def test_an_empty_paragraph_quotes_the_start_of_the_block_before_it(
    tmp_path: Path,
) -> None:
    text = "Every comment keeps the questions for the reporter in view and says what"
    site = built(tmp_path, {"index.html": article(f"<p>{text} it is:</p><p></p>")})

    assert messages(site) == [
        'index.html: has an empty paragraph after "Every comment keeps the questions '
        'for the reporter in view…": a plugin or a hook took out what it held, '
        "such as a picture"
    ]
