"""Tests of what a built website promises: blueprint/site_check.py, which reads the
files that MkDocs and the hooks of .github/mkdocs_blueprint.py wrote, and the command
site-check of blueprint.py, which the check docs runs after the build."""

from __future__ import annotations

from pathlib import Path

import pytest
from shell import BASH
from workflow_steps import SHA, run_step

from blueprint.cli import main
from blueprint.site_check import Finding, Page, annotation, check

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
