"""Tests of the hooks of the documentation website, .github/mkdocs_blueprint.py."""

from __future__ import annotations

import gzip
import importlib.util
import io
import json
import logging
import re
import sys
import time
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def hooks() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "mkdocs_blueprint", ROOT / ".github/mkdocs_blueprint.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def config(
    site: Path, *locales: tuple[str, bool, bool], building: str = ""
) -> SimpleNamespace:
    """The parts of a MkDocs configuration that the hooks read: the i18n plugin with
    its languages as (locale, default, build) and the language it builds, the default
    one unless named, or no such plugin."""
    plugins: dict[str, SimpleNamespace] = {}
    if locales:
        languages = [
            SimpleNamespace(locale=locale, default=default, build=build)
            for locale, default, build in locales
        ]
        default = next(language.locale for language in languages if language.default)
        plugins["i18n"] = SimpleNamespace(
            config=SimpleNamespace(languages=languages),
            is_default_language_build=building in ("", default),
            current_language=building or default,
        )
    return SimpleNamespace(site_dir=str(site), plugins=plugins)


def site(root: Path, *pages: str) -> None:
    """A built website: its sitemap at the root and the given pages."""
    (root / "sitemap.xml").write_text("<urlset/>\n", encoding="utf-8")
    for page in pages:
        (root / page).parent.mkdir(parents=True, exist_ok=True)
        (root / page).write_text("<html></html>\n", encoding="utf-8")


def sitemaps(root: Path) -> list[str]:
    """Every sitemap of the website, by its path from the root."""
    return sorted(
        path.relative_to(root).as_posix() for path in root.rglob("sitemap.xml")
    )


def test_every_folder_of_pages_gets_the_sitemap(tmp_path: Path) -> None:
    site(
        tmp_path,
        "index.html",
        "decisions/0006-beta-channel.html",
        "de/index.html",
        "de/decisions/0006-beta-channel.html",
        "assets/images/favicon.png",
    )

    hooks().on_post_build(
        config(tmp_path, ("en", True, True), ("de", False, True), ("fr", False, False))
    )

    assert sitemaps(tmp_path) == [
        "de/decisions/sitemap.xml",
        "de/sitemap.xml",
        "decisions/sitemap.xml",
        "sitemap.xml",
    ]
    copy = tmp_path / "de/decisions/sitemap.xml"
    assert copy.read_text(encoding="utf-8") == "<urlset/>\n"


def test_a_page_in_its_own_folder_gets_the_sitemap(tmp_path: Path) -> None:
    # With use_directory_urls, the switch asks next to decisions/0006-beta-channel/.
    site(tmp_path, "index.html", "decisions/0006-beta-channel/index.html")

    hooks().on_post_build(config(tmp_path, ("en", True, True), ("de", False, True)))

    assert sitemaps(tmp_path) == [
        "decisions/0006-beta-channel/sitemap.xml",
        "sitemap.xml",
    ]


def test_a_website_in_one_language_keeps_its_one_sitemap(tmp_path: Path) -> None:
    site(tmp_path, "index.html", "decisions/0006-beta-channel.html")

    hooks().on_post_build(config(tmp_path))
    hooks().on_post_build(config(tmp_path, ("en", True, True), ("de", False, False)))

    assert sitemaps(tmp_path) == ["sitemap.xml"]


def test_without_a_sitemap_nothing_is_copied(tmp_path: Path) -> None:
    (tmp_path / "de").mkdir()
    (tmp_path / "de/index.html").write_text("<html></html>\n", encoding="utf-8")

    hooks().on_post_build(config(tmp_path, ("en", True, True), ("de", False, True)))

    assert sitemaps(tmp_path) == []


def test_a_further_language_leaves_the_404_page_to_the_default_one(
    tmp_path: Path,
) -> None:
    languages = (("en", True, True), ("de", False, True))
    page = '<html lang="de">'

    further = config(tmp_path, *languages, building="de")
    default = config(tmp_path, *languages, building="en")

    assert hooks().on_post_template(page, "404.html", further) == ""
    assert hooks().on_post_template(page, "404.html", default) == page
    assert hooks().on_post_template(page, "sitemap.xml", further) == page


def test_a_website_in_one_language_keeps_its_404_page(tmp_path: Path) -> None:
    page = '<html lang="en">'

    assert hooks().on_post_template(page, "404.html", config(tmp_path)) == page


class Network:
    """The requests of a plugin, with its errors, and an answer or an error for every
    download in turn: a status code or an exception."""

    class ConnectionError(Exception):
        pass

    class Timeout(Exception):
        pass

    def __init__(self, *outcomes: int | Exception) -> None:
        self.outcomes = list(outcomes)
        self.downloads: list[str] = []

    def get(self, url: str, **kwargs: Any) -> SimpleNamespace:
        assert kwargs == {"timeout": 5}
        self.downloads.append(url)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(status_code=outcome)


@pytest.fixture
def waits(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """The seconds that the hook waits, without waiting them."""
    waits: list[float] = []
    monkeypatch.setattr(time, "sleep", waits.append)
    return waits


def plugin(monkeypatch: pytest.MonkeyPatch, name: str, network: Network) -> Any:
    """A plugin whose module downloads with the given requests, as those of Material."""
    module: Any = ModuleType(f"material.plugins.{name}.plugin")
    module.requests = network
    monkeypatch.setitem(sys.modules, module.__name__, module)
    return type("Plugin", (), {"__module__": module.__name__})()


def requests_of(plugin: Any) -> Any:
    """What the module of the plugin downloads with."""
    return sys.modules[type(plugin).__module__].requests


def downloading(monkeypatch: pytest.MonkeyPatch, network: Network) -> Any:
    """The requests of the privacy plugin, after the hook has set it up."""
    privacy = plugin(monkeypatch, "privacy", network)
    hooks().on_config(
        SimpleNamespace(
            plugins={"material/privacy": privacy},
            extra_css=[],
            extra_javascript=[],
            nav=None,
        )
    )
    return requests_of(privacy)


URL = "https://fonts.gstatic.com/s/robotomono/v31/L0x7DF4xlVMF.woff2"


def test_a_download_that_times_out_is_tried_again(
    monkeypatch: pytest.MonkeyPatch, waits: list[float]
) -> None:
    network = Network(
        Network.Timeout("Read timed out."), Network.ConnectionError(), 200
    )

    response = downloading(monkeypatch, network).get(URL, timeout=5)

    assert response.status_code == 200
    assert network.downloads == [URL, URL, URL]
    assert waits == [1, 2]


def test_a_download_is_tried_again_after_an_error_of_the_server(
    monkeypatch: pytest.MonkeyPatch, waits: list[float]
) -> None:
    network = Network(503, 200)

    assert downloading(monkeypatch, network).get(URL, timeout=5).status_code == 200
    assert waits == [1]


def test_the_plugin_gets_the_error_of_the_third_attempt(
    monkeypatch: pytest.MonkeyPatch, waits: list[float]
) -> None:
    timeouts = Network(*(Network.Timeout(f"attempt {n}") for n in (1, 2, 3)))
    errors = Network(500, 502, 503)

    with pytest.raises(Network.Timeout, match="attempt 3"):
        downloading(monkeypatch, timeouts).get(URL, timeout=5)
    assert downloading(monkeypatch, errors).get(URL, timeout=5).status_code == 503
    assert waits == [1, 2, 1, 2]


def test_a_missing_file_or_a_wrong_address_is_not_tried_again(
    monkeypatch: pytest.MonkeyPatch, waits: list[float]
) -> None:
    missing = Network(404)
    wrong = Network(ValueError("Invalid URL"))

    assert downloading(monkeypatch, missing).get(URL, timeout=5).status_code == 404
    with pytest.raises(ValueError, match="Invalid URL"):
        downloading(monkeypatch, wrong).get("htp:/fonts", timeout=5)
    assert missing.downloads == [URL]
    assert waits == []


def test_both_plugins_that_download_try_again_and_nothing_else_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    names = ("privacy", "social", "search")
    privacy, social, search = (plugin(monkeypatch, n, Network()) for n in names)
    module = hooks()
    config = SimpleNamespace(
        plugins={
            "material/privacy": privacy,
            "material/social": social,
            "material/search": search,
        },
        extra_css=[],
        extra_javascript=[],
        nav=None,
    )

    module.on_config(config)
    retrying = requests_of(privacy)
    # Every build of mkdocs serve sets it up again, and once is enough.
    module.on_config(config)

    assert isinstance(retrying, module.Retrying)
    assert requests_of(privacy) is retrying
    assert isinstance(requests_of(social), module.Retrying)
    assert isinstance(requests_of(search), Network)
    # The rest of requests is the same.
    assert retrying.Timeout is Network.Timeout


SOURCE = 'flowchart TB\n    a["one<br>two"] --> b["A & B"]\n'


def picture(src: str, dark: str = "") -> str:
    """A <picture> of a diagram, as scripts/diagrams.sh --extract writes it."""
    dark = dark or src.replace(".svg", ".dark.svg")
    return (
        "<picture>\n"
        f'  <source media="(prefers-color-scheme: dark)" srcset="{dark}">\n'
        f'  <img src="{src}" alt="Steps: one and two">\n'
        "</picture>"
    )


def live(source: str = SOURCE) -> str:
    escaped = source.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f'<pre class="mermaid"><code>{escaped}</code></pre>'


def draw(tmp_path: Path, html: str) -> str:
    docs = tmp_path / "docs"
    (docs / "diagrams").mkdir(parents=True, exist_ok=True)
    (docs / "diagrams/steps.mmd").write_text(SOURCE, encoding="utf-8")
    (docs / "diagrams/steps.de.mmd").write_text(
        "flowchart TB\n  a --> b\n", encoding="utf-8"
    )
    result: str = hooks().live_diagrams(html, docs / "diagrams")
    return result


def test_the_website_draws_a_diagram_from_its_source(tmp_path: Path) -> None:
    # A README, which names the pictures from the root of the repository, and a page
    # of docs/, which names them from its folder.
    html = (
        "<h1>Demo</h1>\n"
        f"<p>{picture('docs/images/diagrams/steps.svg')}</p>\n"
        "<p>Text.</p>\n"
        f"<p>\n{picture('../images/diagrams/steps.de.svg')}\n</p>\n"
    )

    assert draw(tmp_path, html) == (
        "<h1>Demo</h1>\n"
        f"{live()}\n"
        "<p>Text.</p>\n"
        f"{live('flowchart TB' + chr(10) + '  a --> b' + chr(10))}\n"
    )


def test_a_picture_in_a_paragraph_with_text_keeps_the_paragraph(tmp_path: Path) -> None:
    html = f"<p>Before\n{picture('images/diagrams/steps.svg')}\nafter.</p>"

    assert draw(tmp_path, html) == f"<p>Before\n{live()}\nafter.</p>"


def test_other_pictures_stay_as_they_are(tmp_path: Path) -> None:
    html = (
        f"<p>{picture('images/diagrams/missing.svg')}</p>\n"
        f"<p>{picture('images/card.png', 'images/card-dark.png')}</p>\n"
        '<p><img src="images/diagrams/steps.svg" alt="Steps"></p>\n'
    )

    assert draw(tmp_path, html) == html


# The stylesheet and the script of the blueprint


class Script:
    """An entry of extra_javascript, which MkDocs keeps as an ExtraScriptValue."""

    def __init__(self, path: str) -> None:
        self.path = path

    def __str__(self) -> str:
        return self.path


def test_every_page_gets_the_stylesheet_and_the_script_before_the_project_s() -> None:
    module = hooks()
    project = Script("javascripts/extra.js")
    config = SimpleNamespace(
        plugins={},
        extra_css=["stylesheets/extra.css"],
        extra_javascript=[project],
        nav=None,
    )

    module.on_config(config)
    # Every build of mkdocs serve sets it up again, and once is enough.
    module.on_config(config)

    assert config.extra_css == [module.STYLESHEET, "stylesheets/extra.css"]
    assert config.extra_javascript == [module.SCRIPT, project]
    assert module.STYLESHEET == "assets/stylesheets/blueprint.css"
    assert module.SCRIPT == "assets/javascripts/blueprint.js"


class File:
    """A file of MkDocs, by the arguments of mkdocs.structure.files.File."""

    def __init__(
        self,
        path: str,
        src_dir: str | None,
        dest_dir: str,
        use_directory_urls: bool,
        *,
        dest_uri: str | None = None,
    ) -> None:
        self.src_uri = path
        self.dest_uri = dest_uri or path
        self.abs_src_path = str(Path(src_dir) / path) if src_dir else None
        self.site = (dest_dir, use_directory_urls)


def theme(tmp_path: Path, script: str) -> File:
    """The script of Material in the folder of its theme."""
    folder = tmp_path / "material"
    name = "assets/javascripts/bundle.d7400e89.min.js"
    (folder / name).parent.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(script, encoding="utf-8")
    return File(name, str(folder), str(tmp_path / "site"), False)


def build(tmp_path: Path, *files: File) -> list[File]:
    config = SimpleNamespace(
        config_file_path=str(tmp_path / "mkdocs.yml"),
        docs_dir=str(tmp_path / "docs"),
        site_dir=str(tmp_path / "site"),
        use_directory_urls=False,
    )
    result: list[File] = hooks().on_files(list(files), config)
    return result


LOADER = 'let m="https://unpkg.com/mermaid@11/dist/mermaid.min.js";'


def test_the_website_serves_the_stylesheet_and_the_script_beside_the_hook(
    tmp_path: Path,
) -> None:
    page = File("index.md", str(tmp_path / "docs"), str(tmp_path / "site"), False)

    files = {file.dest_uri: file for file in build(tmp_path, page)}

    assert files["index.md"] is page
    stylesheet = files["assets/stylesheets/blueprint.css"]
    script = files["assets/javascripts/blueprint.js"]
    assert stylesheet.abs_src_path == str(ROOT / ".github/mkdocs-blueprint.css")
    assert script.abs_src_path == str(ROOT / ".github/mkdocs-blueprint.js")
    assert stylesheet.site == (str(tmp_path / "site"), False)


def test_the_script_of_material_loads_the_pinned_mermaid(tmp_path: Path) -> None:
    module = hooks()
    bundle = theme(tmp_path, LOADER + LOADER)
    original = bundle.abs_src_path
    assert original is not None

    build(tmp_path, bundle)

    copy = tmp_path / ".cache/plugin/blueprint" / bundle.src_uri
    assert bundle.abs_src_path == str(copy)
    pinned = f'let m="{module.MERMAID}";'
    assert copy.read_text(encoding="utf-8") == pinned + pinned
    assert Path(original).read_text(encoding="utf-8") == LOADER + LOADER
    assert re.fullmatch(
        r"https://unpkg\.com/mermaid@11\.\d+\.\d+/dist/mermaid\.min\.js", module.MERMAID
    )


@pytest.mark.parametrize(
    ("script", "warning"),
    [
        (LOADER.replace("@11/", "@12/"), "Material loads Mermaid 12"),
        ('let m="https://cdn.example/mermaid.js";', "no longer loads Mermaid"),
    ],
)
def test_a_material_that_loads_mermaid_otherwise_fails_a_strict_build(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, script: str, warning: str
) -> None:
    bundle = theme(tmp_path, script)
    original = bundle.abs_src_path

    with caplog.at_level(logging.WARNING, logger="mkdocs.hooks.blueprint"):
        build(tmp_path, bundle)

    assert bundle.abs_src_path == original
    assert [record.levelno for record in caplog.records] == [logging.WARNING]
    assert warning in caplog.text
    # A strict build of MkDocs fails on every warning of a logger below mkdocs.
    assert caplog.records[0].name.startswith("mkdocs.")


def test_other_scripts_stay_as_they_are(tmp_path: Path) -> None:
    other = File("assets/javascripts/glightbox.min.js", str(tmp_path), "site", False)
    generated = File("assets/javascripts/bundle.0000.min.js", None, "site", False)

    build(tmp_path, other, generated)

    assert other.abs_src_path == str(tmp_path / "assets/javascripts/glightbox.min.js")
    assert generated.abs_src_path is None
    assert not (tmp_path / ".cache").exists()


def test_renovate_keeps_the_pinned_mermaid_current() -> None:
    renovate = (ROOT / ".github/renovate.json5").read_text(encoding="utf-8")
    assert '"/^\\\\.github/mkdocs_blueprint\\\\.py$/"' in renovate
    # The pattern of the manager, as JSON reads its string, in the syntax of Python.
    written = re.search(r'\n {8}("https://unpkg[^\n]+"),\n', renovate)
    assert written is not None
    pattern = json.loads(written[1]).replace("(?<", "(?P<")
    hook = (ROOT / ".github/mkdocs_blueprint.py").read_text(encoding="utf-8")
    found = [match.groupdict() for match in re.finditer(pattern, hook)]
    version = hooks().MERMAID.split("@")[1].split("/")[0]
    assert found == [{"depName": "mermaid", "currentValue": version}]


def test_the_stylesheet_fixes_what_the_accessibility_check_found() -> None:
    css = (ROOT / ".github/mkdocs-blueprint.css").read_text(encoding="utf-8")
    rules = {
        "link-in-text-block": "text-decoration: underline;",
        "the tabs, 4.3:1": ".md-tabs__link {\n  opacity: 1;\n}",
        "outlined buttons in the dark, 2.3:1": "color: var(--md-typeset-a-color);",
        "links in the dark, 4.2:1 on code": "--md-typeset-a-color: #7aa2f7;",
        "comments of code, 4.5:1": "--md-code-hl-comment-color: rgb(0 0 0 / 60%);",
        "links that the keyboard reaches unseen": 'img[src$="#only-dark"])',
    }
    for problem, rule in rules.items():
        assert rule in css, problem


# The pictures of a page


def png(width: int = 4, height: int = 2) -> bytes:
    data = io.BytesIO()
    Image.new("RGB", (width, height), (82, 108, 254)).save(data, "PNG")
    return data.getvalue()


def gif(width: int = 6, height: int = 3) -> bytes:
    data = io.BytesIO()
    Image.new("P", (width, height)).save(data, "GIF")
    return data.getvalue()


def webp(width: int, height: int, **options: Any) -> bytes:
    data = io.BytesIO()
    frames = [Image.new("RGB", (width, height), color) for color in ("red", "blue")]
    frames[0].save(data, "WEBP", **options)
    return data.getvalue()


def pictures(
    tmp_path: Path,
    html: str,
    media: dict[str, bytes],
    page: str = "guide.html",
    source: str = "",
) -> str:
    """The content of a page after the hook, with the files of the website; the
    page comes from source, from the same path as Markdown when it is empty."""
    docs = tmp_path / "docs"
    files = []
    for name, data in media.items():
        (docs / name).parent.mkdir(parents=True, exist_ok=True)
        (docs / name).write_bytes(data)
        files.append(File(name, str(docs), str(tmp_path / "site"), False))
    files.append(File(source or page.replace(".html", ".md"), str(docs), "site", False))
    files[-1].dest_uri = page
    result: str = hooks().on_page_content(
        html,
        page=SimpleNamespace(file=files[-1], meta={}),
        config=SimpleNamespace(docs_dir=str(docs), plugins={}),
        files=files,
    )
    return result


def themed_picture(light: str, dark: str, alt: str = "The settings") -> str:
    return (
        "<picture>\n"
        f'  <source media="(prefers-color-scheme: dark)" srcset="{dark}">\n'
        f'  <img src="{light}" alt="{alt}">\n'
        "</picture>"
    )


def test_the_first_picture_loads_first_and_the_others_as_the_reader_comes(
    tmp_path: Path,
) -> None:
    html = (
        '<p><img alt="Hero" src="images/hero.png"></p>\n'
        '<p><img alt="Elsewhere" src="https://example.org/picture.svg"></p>\n'
        "<p><img src='images/card.png' width=\"40\" alt=Card></p>\n"
        '<p><img src="images/steps.svg" alt="Steps"/></p>\n'
    )

    media = {
        "images/hero.png": png(1280, 640),
        "images/card.png": png(),
        "images/steps.svg": b"<svg/>",
    }
    assert pictures(tmp_path, html, media) == (
        '<p><img alt="Hero" src="images/hero.png" width="1280" height="640"'
        ' fetchpriority="high"></p>\n'
        '<p><img alt="Elsewhere" src="https://example.org/picture.svg"'
        ' loading="lazy" decoding="async"></p>\n'
        '<p><img src="images/card.png" width="40" alt="Card" loading="lazy"'
        ' decoding="async"></p>\n'
        '<p><img src="images/steps.svg" alt="Steps" loading="lazy"'
        ' decoding="async"></p>\n'
    )


def test_a_picture_that_says_how_it_loads_stays_as_it_is(tmp_path: Path) -> None:
    html = (
        '<img src="images/hero.png" loading="eager" alt="Hero">'
        '<img src="data:image/png;base64,iVBOR" alt="Dot">'
        '<img src="/images/hero.png" alt="Root">'
        '<img alt="Empty">'
    )

    assert pictures(tmp_path, html, {"images/hero.png": png()}) == (
        '<img src="images/hero.png" loading="eager" alt="Hero">'
        '<img src="data:image/png;base64,iVBOR" alt="Dot" loading="lazy"'
        ' decoding="async">'
        '<img src="/images/hero.png" alt="Root" loading="lazy" decoding="async">'
        '<img alt="Empty" loading="lazy" decoding="async">'
    )


def test_a_picture_for_each_scheme_follows_the_switch_of_the_website(
    tmp_path: Path,
) -> None:
    media = {"images/settings.png": png(), "images/settings.dark.png": png()}
    html = f"<p>{themed_picture('../images/settings.png', '../images/settings.dark.png')}</p>"

    assert pictures(tmp_path, html, media, page="de/guide.html") == (
        '<p><img src="../images/settings.png#only-light" alt="The settings"'
        ' width="4" height="2" loading="lazy" decoding="async">'
        '<img src="../images/settings.dark.png#only-dark" alt="The settings"'
        ' width="4" height="2" loading="lazy" decoding="async"></p>'
    )


def test_a_translated_page_leads_its_html_pictures_from_its_source(
    tmp_path: Path,
) -> None:
    media = {
        "images/a.png": png(),
        "images/a.dark.png": png(),
        "images/b.png": png(),
        "images/c.gif": gif(),
        "images/c.mp4": b"",
    }
    # MkDocs leaves the paths of HTML as guide.de.md names them, from docs/.
    html = (
        f"{themed_picture('images/a.png', 'images/a.dark.png', alt='A')}"
        '<img src="images/b.png?v=2#top" alt="B"><img src="images/c.gif" alt="C">'
    )

    assert pictures(tmp_path, html, media, "de/guide.html", "guide.de.md") == (
        '<img src="../images/a.png#only-light" alt="A" width="4" height="2"'
        ' loading="lazy" decoding="async">'
        '<img src="../images/a.dark.png#only-dark" alt="A" width="4" height="2"'
        ' loading="lazy" decoding="async">'
        '<img src="../images/b.png?v=2#top" alt="B" width="4" height="2"'
        ' loading="lazy" decoding="async">'
        '<video class="blueprint-video" src="../images/c.mp4" width="6" height="3"'
        ' controls muted loop playsinline preload="none" aria-label="C"></video>'
    )


def test_a_readme_names_the_pictures_of_both_schemes_from_the_root(
    tmp_path: Path,
) -> None:
    media = {"images/a.png": png(), "images/a.dark.png": png()}
    # Both sources, as GitHub documents it, and a <picture> without a source.
    html = (
        "<picture>"
        '<source type="image/avif" srcset="docs/images/a.avif">'
        '<source media="(prefers-color-scheme: light)" srcset="docs/images/a.png 1x">'
        '<source media="(prefers-color-scheme:dark)" srcset="docs/images/a.dark.png">'
        '<img src="docs/images/fallback.png" alt="A">'
        "</picture>"
        '<picture><img src="https://example.com/b.png" alt="B"></picture>'
        "<picture></picture>"
    )

    assert pictures(tmp_path, html, media, page="decisions/0001.html") == (
        '<img src="../images/a.png#only-light" alt="A" width="4" height="2"'
        ' loading="lazy" decoding="async">'
        '<img src="../images/a.dark.png#only-dark" alt="A" width="4" height="2"'
        ' loading="lazy" decoding="async">'
        '<picture><img src="https://example.com/b.png" alt="B" loading="lazy"'
        ' decoding="async"></picture><picture></picture>'
    )


def test_a_picture_of_a_scheme_that_the_website_lacks_keeps_its_path(
    tmp_path: Path,
) -> None:
    html = themed_picture(
        "docs/images/gone.png", "https://example.com/dark.png", alt="Gone"
    )

    assert pictures(tmp_path, html, {}) == (
        '<img src="docs/images/gone.png#only-light" alt="Gone" loading="lazy"'
        ' decoding="async">'
        '<img src="https://example.com/dark.png#only-dark" alt="Gone"'
        ' loading="lazy" decoding="async">'
    )


def test_a_gif_with_a_video_beside_it_plays_as_the_video(tmp_path: Path) -> None:
    media = {
        "images/copy.gif": gif(1320, 720),
        "images/copy.mp4": b"\0\0\0\x20ftypisom",
        "images/copy.webp": webp(4, 2),
        "images/copy.png": png(),
    }
    html = '<p><img alt="copier copy in the terminal" title="A copy" src="../images/copy.gif"></p>'

    assert pictures(tmp_path, html, media, page="de/index.html") == (
        '<p><video class="blueprint-video" src="../images/copy.mp4"'
        ' poster="../images/copy.webp" width="1320" height="720" controls muted'
        ' loop playsinline preload="none" aria-label="copier copy in the terminal"'
        ' title="A copy"></video></p>'
    )


def test_a_video_takes_a_png_until_it_plays_or_shows_nothing(tmp_path: Path) -> None:
    media = {
        "a.gif": b"no GIF after all",
        "a.mp4": b"",
        "a.png": png(),
        "b.gif": gif(),
        "b.mp4": b"",
    }
    html = '<img src="a.gif" alt="A"><img src="b.gif">'

    assert pictures(tmp_path, html, media, page="index.html") == (
        '<video class="blueprint-video" src="a.mp4" poster="a.png" controls muted'
        ' loop playsinline preload="none" aria-label="A"></video>'
        '<video class="blueprint-video" src="b.mp4" width="6" height="3" controls'
        ' muted loop playsinline preload="none"></video>'
    )


def test_a_gif_without_a_video_stays_a_gif(tmp_path: Path) -> None:
    html = '<img src="images/a.gif" alt="A"><img src="images/b.png" alt="B">'
    media = {"images/a.gif": gif(), "images/b.png": png(), "images/b.mp4": b""}

    assert pictures(tmp_path, html, media) == (
        '<img src="images/a.gif" alt="A" width="6" height="3" fetchpriority="high">'
        '<img src="images/b.png" alt="B" width="4" height="2" loading="lazy"'
        ' decoding="async">'
    )


def test_the_size_of_a_picture_comes_from_its_first_bytes(tmp_path: Path) -> None:
    module = hooks()
    kinds = {
        "a.png": png(7, 3),
        "a.gif": gif(5, 9),
        "lossy.webp": webp(33, 17, quality=50),
        "lossless.webp": webp(31, 19, lossless=True),
        "moving.webp": webp(
            30, 20, save_all=True, append_images=[Image.new("RGB", (30, 20))]
        ),
        "a.svg": b"<svg width='3' height='4'/>",
        "short.webp": b"RIFF\0\0\0\0WEBPVP8 ",
        "sound.wav": b"RIFF\0\0\0\0WAVEfmt " + bytes(20),
        "other.webp": b"RIFF\0\0\0\0WEBPALPH" + bytes(20),
    }
    for name, data in kinds.items():
        (tmp_path / name).write_bytes(data)

    found = {name: module.size(str(tmp_path / name)) for name in kinds}

    assert found == {
        "a.png": (7, 3),
        "a.gif": (5, 9),
        "lossy.webp": (33, 17),
        "lossless.webp": (31, 19),
        "moving.webp": (30, 20),
        "a.svg": None,
        "short.webp": None,
        "sound.wav": None,
        "other.webp": None,
    }


def test_the_lightbox_shows_the_pictures_of_the_reader_s_scheme() -> None:
    settings = (ROOT / ".github/mkdocs-blueprint.yml").read_text(encoding="utf-8")
    assert "\n  glightbox:\n    auto_themed: true\n" in settings
    # The scheme of the system first, so that a change of it shows on the next page.
    palette = settings.split("\n  palette:\n", 1)[1]
    assert palette.startswith('    - media: "(prefers-color-scheme)"\n')


# The search, the metadata and the dates of a page in its language

SITE = "https://example.org/demo/"


def bilingual(current: str = "en", *, search: bool = True, **more: Any) -> Any:
    """The parts of the configuration of a website in English and German that the
    hooks read, while the i18n plugin builds the language current."""
    languages = [
        SimpleNamespace(locale="en", default=True, build=True),
        SimpleNamespace(locale="de", default=False, build=True),
    ]
    plugins: dict[str, Any] = {
        "i18n": SimpleNamespace(
            config=SimpleNamespace(languages=languages), current_language=current
        )
    }
    if search:
        plugins["material/search"] = object()
    return SimpleNamespace(site_url=SITE, plugins=plugins, **more)


def version(locale: str, url: str) -> Any:
    """A file of a version of a page, as the i18n plugin lists it."""
    return SimpleNamespace(locale=locale, url=url)


def page_of(
    url: str,
    *,
    locale: str = "en",
    meta: dict[str, Any] | None = None,
    **alternates: Any,
) -> Any:
    """A page of MkDocs at url, from a file in locale, with its versions."""
    src_uri = re.sub(r"^de/", "", url).replace(".html", ".md")
    file = SimpleNamespace(
        src_uri=src_uri,
        dest_uri=url,
        url=url,
        locale=locale,
        alternates=alternates,
        abs_src_path=f"docs/{src_uri}",
    )
    return SimpleNamespace(
        file=file,
        url=url,
        canonical_url=SITE + url,
        meta={} if meta is None else meta,
        update_date="2026-10-18",
    )


def test_the_search_leaves_out_the_sources_of_diagrams(tmp_path: Path) -> None:
    html = f"<h1>Steps</h1>\n{live()}"

    assert pictures(tmp_path, html, {}) == html.replace(
        '<pre class="mermaid">', '<pre class="mermaid" data-search-exclude>'
    )


def test_the_website_shows_no_badges() -> None:
    html = (
        "<h1>Demo</h1>\n"
        '<p><a href="https://github.com/o/r/actions">'
        '<img alt="CI" src="https://github.com/o/r/actions/workflows/ci.yml/badge.svg">'
        "</a>\n"
        '<a href="https://scorecard.dev/viewer/">'
        '<img alt="Scorecard" src="https://api.scorecard.dev/projects/o/r/badge"></a>'
        "</p>\n"
        '<p>Text with <img alt="Shield" src="https://img.shields.io/badge/a-b"> in it.'
        "</p>\n"
        '<p><a href="https://example.org/"><img alt="Logo" src="https://example.org/'
        'logo.png"></a> <img alt="Card" src="images/card.png"></p>\n'
        '<p><img alt="REUSE" src="https://api.reuse.software/badge/github.com/o/r">'
        '<img alt="Coverage" src="https://codecov.io/gh/o/r/graph/badge.svg?t=1">'
        "</p>\n"
    )
    # A button of My Home Assistant shows no status: it stays, with its link.
    button = (
        '<p><a href="https://my.home-assistant.io/redirect/hacs_repository/">'
        '<img alt="Open in HACS" '
        'src="https://my.home-assistant.io/badges/hacs_repository.svg"></a></p>\n'
    )

    assert hooks().without_badges(html + button) == (
        "<h1>Demo</h1>\n"
        "<p>Text with  in it.</p>\n"
        '<p><a href="https://example.org/"><img alt="Logo" src="https://example.org/'
        'logo.png"></a> <img alt="Card" src="images/card.png"></p>\n' + button
    )


def test_a_page_describes_itself_with_its_first_paragraph() -> None:
    module = hooks()
    html = (
        '<div class="admonition"><p class="admonition-title">Note</p></div>\n'
        '<p><a href="ci.html"><img alt="CI" src="ci.png"></a></p>\n'
        "<p>The <strong>guide</strong> says &quot;why&quot; &amp;\n how.</p>\n"
        "<p>More.</p>"
    )
    guide = page_of("guide.html")
    own = page_of("security.html", meta={"description": "Its own."})
    homes = [page_of("index.html"), page_of("de/index.html", locale="de")]
    empty = page_of("empty.html")

    for page in (guide, own, homes[0]):
        module.describe(page, html, SimpleNamespace(plugins={}))
    module.describe(homes[1], html, bilingual("de"))
    module.describe(empty, "<p><img alt='Only' src='a.png'></p>", bilingual())

    assert guide.meta == {"description": "The guide says 'why' & how."}
    # The line that leads to the version in another language describes nothing.
    switch = page_of("de/guide.html", locale="de")
    module.describe(
        switch,
        '<p><a href="README.md">English version</a> · <a href="x">Demo</a></p>\n'
        "<p>Die <a href='guide.html'>Anleitung</a>.</p>",
        bilingual("de"),
    )
    assert switch.meta == {"description": "Die Anleitung."}
    assert own.meta == {"description": "Its own."}
    assert [home.meta for home in homes] == [{}, {}]
    assert empty.meta == {}


def test_a_long_description_ends_after_a_word() -> None:
    module = hooks()
    text = "word " * 40

    assert module.shorten("one two", 7) == "one two"
    assert module.shorten("one two three", 9) == "one two…"
    assert module.shorten("one, two three", 6) == "one…"
    assert len(module.shorten(text, module.DESCRIPTION)) <= module.DESCRIPTION
    assert module.DESCRIPTION == 160


def test_the_language_of_a_page_comes_from_its_path() -> None:
    found = hooks().Languages("en", ("de",), "en")

    assert [
        found.of(location)
        for location in (
            "guide.html",
            "de/guide.html",
            "de/",
            "de.html",
            # The pages of a project website in the search of its owner's website.
            "ha-autodarts/games.html",
            "ha-autodarts/de/games.html",
            "ha-autodarts/de.html",
        )
    ] == ["en", "de", "de", "en", "en", "de", "en"]
    assert found.versions("guide.html", "de") == ("de/guide.html",)
    assert found.versions("ha-autodarts/games.html", "de") == (
        "de/ha-autodarts/games.html",
        "ha-autodarts/de/games.html",
    )


def test_the_languages_of_a_website(tmp_path: Path) -> None:
    module = hooks()
    one = config(tmp_path, ("en", True, True), ("de", False, False))
    first = bilingual()
    first.plugins["i18n"].current_language = None

    assert module.languages(SimpleNamespace(plugins={})) is None
    assert module.languages(one) is None
    assert module.languages(bilingual("de")) == module.Languages("en", ("de",), "de")
    # The plugin names the language only once its on_config ran, after this hook's.
    assert module.languages(first) == module.Languages("en", ("de",), "en")


def test_the_switch_of_the_scheme_speaks_the_language_of_the_page() -> None:
    module = hooks()
    palette: list[dict[str, Any]] = [
        {"media": "(prefers-color-scheme)", "toggle": {"name": "Switch to light mode"}},
        {"scheme": "default", "toggle": {"name": "Switch to dark mode"}},
        {"scheme": "slate", "toggle": {"name": "Switch to the scheme of the system"}},
        {"scheme": "own", "toggle": {"name": "A name of the project", "icon": "x"}},
        {"scheme": "bare", "toggle": {"icon": "x"}},
        {"scheme": "none"},
    ]

    def names() -> list[str | None]:
        return [option.get("toggle", {}).get("name") for option in palette]

    def build(language: str, theme: dict[str, Any]) -> None:
        module.on_config(
            bilingual(
                language, theme=theme, extra_css=[], extra_javascript=[], nav=None
            )
        )

    build("de", {"palette": palette})
    assert names() == [
        "Zum hellen Farbschema wechseln",
        "Zum dunklen Farbschema wechseln",
        "Zum Farbschema des Systems wechseln",
        "A name of the project",
        None,
        None,
    ]
    build("en", {"palette": palette})
    assert names() == [
        "Switch to light mode",
        "Switch to dark mode",
        "Switch to the scheme of the system",
        "A name of the project",
        None,
        None,
    ]
    # A palette of a single scheme names no switch.
    single = {"palette": {"scheme": "slate"}}
    build("de", single)
    assert single == {"palette": {"scheme": "slate"}}


def test_the_search_and_search_engines_leave_out_copies_and_templates() -> None:
    module = hooks()
    one = SimpleNamespace(plugins={})
    template = page_of("decisions/0000-template.html", meta={"search": {"boost": 2}})
    hidden = page_of("draft.html", meta={"robots": "NOINDEX, follow"})
    copy = page_of("de/roadmap.html")
    translated = page_of("de/guide.html", locale="de")

    for page, settings in (
        (template, one),
        (hidden, one),
        (copy, bilingual("de")),
        (translated, bilingual("de")),
    ):
        assert module.on_page_markdown("# Page", page, settings, []) == "# Page"

    assert template.meta["search"] == {"boost": 2, "exclude": True}
    assert hidden.meta["search"] == {"exclude": True}
    assert copy.meta["search"] == {"exclude": True}
    assert "search" not in translated.meta
    assert module.BUILT.unlisted == {
        SITE + "decisions/0000-template.html",
        SITE + "draft.html",
        SITE + "de/roadmap.html",
    }
    assert module.BUILT.untranslated == {"de/roadmap.html"}
    # After the plugin of the dates, before the search plugin.
    assert module.on_page_markdown.mkdocs_priority == -10


def test_the_sitemap_dates_a_page_by_its_last_change() -> None:
    module = hooks()
    changed = page_of("guide.html")
    changed.meta["git_revision_date_localized_raw_iso_date"] = "2026-10-12"
    new = page_of("new.html")

    for page in (changed, new):
        module.on_page_markdown("", page, SimpleNamespace(plugins={}), [])

    assert changed.update_date == "2026-10-12"
    # Without the history of git, the date of the build stays.
    assert new.update_date == "2026-10-18"


class Dates:
    """The plugin git-revision-date-localized, with a time for each file."""

    def __init__(self, times: dict[str, int]) -> None:
        self.times = times
        self.util = SimpleNamespace(get_git_commit_timestamp=self.commit)
        self.rendered: list[tuple[Any, ...]] = []

    def commit(self, path: str, is_first_commit: bool) -> tuple[str, int]:
        assert not is_first_commit
        name = Path(path).name
        return f"hash of {name}", self.times[name]

    def _get_locale(self, page: Any) -> str:
        return str(page.file.locale)

    def _render_date(
        self, markdown: str, page: Any, locale: str, variable: str, *commit: Any
    ) -> str:
        self.rendered.append((locale, variable, *commit))
        return markdown


def dated(
    tmp_path: Path,
    markdown: str,
    page: Any,
    language: str = "en",
    **snippets: Any,
) -> list[tuple[Any, ...]]:
    """The dates that the hook renders for page, with the files of a repository."""
    files = {
        "README.md": 'Intro\n--8<-- "NESTED.md"\n--8<-- "README.md"\n',
        "NESTED.md": "Nested\n",
        "CHANGELOG.md": "# Changelog\n",
        "includes/PART.md": "Part\n",
    }
    for name, text in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text, encoding="utf-8")
    plugin = Dates(
        {"guide.md": 100, "README.md": 300, "CHANGELOG.md": 200, "PART.md": 500}
        | {"NESTED.md": 400, "roadmap.md": 50}
    )
    settings = bilingual(
        language,
        config_file_path=str(tmp_path / "mkdocs.yml"),
        mdx_configs={"pymdownx.snippets": snippets} if snippets else {},
    )
    settings.plugins["git-revision-date-localized"] = plugin
    page.meta["git_revision_date_localized"] = "a date"
    hooks().redate(markdown, page, settings)
    return plugin.rendered


def test_a_page_that_includes_files_takes_the_date_of_the_newest(
    tmp_path: Path,
) -> None:
    markdown = (
        '--8<-- "README.md:loop"\n'
        ';--8<-- "includes/PART.md"\n'
        "--8<-- 'missing.md'\n"
        '--8<-- "https://example.org/remote.md"\n'
        "--8<--\n"
        "CHANGELOG.md\n"
        "; includes/PART.md\n"
        "\n"
        "README.md\n"
        "--8<--\n"
    )

    assert dated(tmp_path, markdown, page_of("guide.html")) == [
        ("en", "git_revision_date_localized", "hash of NESTED.md", 400)
    ]
    # In the folders of base_path, the first that has the file.
    assert dated(
        tmp_path, '--8<-- "PART.md"', page_of("guide.html"), base_path=["includes", "."]
    ) == [("en", "git_revision_date_localized", "hash of PART.md", 500)]
    assert hooks().included(markdown, [tmp_path]) == [
        tmp_path / "README.md",
        tmp_path / "NESTED.md",
        tmp_path / "CHANGELOG.md",
    ]


def test_an_untranslated_page_is_dated_in_the_language_of_its_menu(
    tmp_path: Path,
) -> None:
    roadmap = page_of("de/roadmap.html")

    assert dated(tmp_path, "# Roadmap", roadmap, "de") == [
        ("de", "git_revision_date_localized", "hash of roadmap.md", 50)
    ]


def test_a_page_of_its_own_keeps_the_date_of_the_plugin(tmp_path: Path) -> None:
    excluded = page_of("guide.html")
    plugin = Dates({})
    settings = bilingual(config_file_path="mkdocs.yml", mdx_configs={})
    settings.plugins["git-revision-date-localized"] = plugin

    assert dated(tmp_path, "# Guide", page_of("guide.html")) == []
    # A page that the plugin leaves out, by its option exclude.
    hooks().redate('--8<-- "README.md"', excluded, settings)
    assert plugin.rendered == []


def test_an_untranslated_page_says_its_language(tmp_path: Path) -> None:
    roadmap = page_of("de/roadmap.html")
    guide = page_of("de/guide.html", locale="de")
    settings = bilingual("de", docs_dir=str(tmp_path / "docs"))

    copy = hooks().on_page_content("<p>Text.</p>", roadmap, settings, [roadmap.file])
    own = hooks().on_page_content("<p>Text.</p>", guide, settings, [guide.file])

    assert copy == '<div lang="en">\n<p>Text.</p>\n</div>'
    assert own == "<p>Text.</p>"


HEAD = (
    "<head>\n"
    '<link rel="canonical" href="{canonical}">\n'
    '<link rel="alternate" href="{en}" hreflang="en">\n'
    '<link rel="alternate" href="{de}" hreflang="de">\n'
    '<link rel="stylesheet" href="assets/main.css">\n'
    "</head><body></body>"
)


def script(every: str, own: str) -> str:
    template: str = hooks().SEARCH_SCRIPT
    return template.format(every=json.dumps(every), own=json.dumps(own))


def test_a_page_names_its_versions_with_their_full_addresses() -> None:
    guide = page_of(
        "guide.html",
        en=version("en", "guide.html"),
        de=version("de", "de/guide.html"),
    )
    head = HEAD.format(
        canonical=SITE + "guide.html", en="guide.html", de="de/guide.html"
    )

    output = hooks().on_post_page(head, guide, bilingual())

    assert output == (
        "<head>\n"
        f'<link rel="canonical" href="{SITE}guide.html">\n'
        f'<link rel="alternate" href="{SITE}guide.html" hreflang="en">'
        f'<link rel="alternate" href="{SITE}de/guide.html" hreflang="de">'
        f'<link rel="alternate" href="{SITE}guide.html" hreflang="x-default">\n'
        "\n"
        '<link rel="stylesheet" href="assets/main.css">\n'
        + script("search/search_index.json", "search/search_index.en.json")
        + "</head><body></body>"
    )
    # After the hooks of a project and the privacy plugin.
    assert hooks().on_post_page.mkdocs_priority == -60


def test_an_untranslated_page_is_a_copy_that_search_engines_leave_out() -> None:
    copy = page_of(
        "de/roadmap.html",
        de=version("en", "de/roadmap.html"),
        en=version("en", "roadmap.html"),
    )
    original = page_of(
        "roadmap.html",
        en=version("en", "roadmap.html"),
        de=version("en", "de/roadmap.html"),
    )
    head = HEAD.format(
        canonical=SITE + "de/roadmap.html", en="../roadmap.html", de="roadmap.html"
    )

    output = hooks().on_post_page(head, copy, bilingual("de"))
    english = hooks().on_post_page(
        HEAD.format(canonical=SITE + "roadmap.html", en="roadmap.html", de="de/x"),
        original,
        bilingual(),
    )

    assert output == (
        "<head>\n"
        f'<link rel="canonical" href="{SITE}roadmap.html">\n'
        "\n"
        "\n"
        '<link rel="stylesheet" href="assets/main.css">\n'
        + script("../search/search_index.json", "../search/search_index.de.json")
        + '<meta name="robots" content="noindex, follow"></head><body></body>'
    )
    # The page of the default language names no version either.
    assert 'rel="alternate"' not in english
    assert f'<link rel="canonical" href="{SITE}roadmap.html">' in english
    assert "noindex" not in english


def test_an_untranslated_page_keeps_the_canonical_page_of_its_project() -> None:
    # The page moved: a hook of the project names the page that replaced it.
    moved = page_of(
        "de/SETUP.html",
        de=version("en", "de/SETUP.html"),
        en=version("en", "SETUP.html"),
    )
    head = HEAD.format(canonical=SITE + "setup.html", en="../SETUP.html", de="x")

    output = hooks().on_post_page(head, moved, bilingual("de"))

    assert f'<link rel="canonical" href="{SITE}setup.html">' in output
    assert "noindex" in output


def test_the_preview_card_of_a_home_page_names_the_website() -> None:
    module = hooks()
    social = SimpleNamespace(plugins={"material/social": object()}, site_name="Demo")
    german = bilingual("de", site_name="Demo")
    german.plugins["material/social"] = object()
    home = page_of("index.html")
    own = page_of("index.html", meta={"social": {"cards_layout_options": {}}})
    own.meta["social"]["cards_layout_options"]["title"] = "Own"
    de_home = page_of("de/index.html", locale="de")
    guide = page_of("guide.html")
    without = page_of("index.html")

    for page in (home, own, guide):
        module.on_page_markdown("", page, social, [])
    module.on_page_markdown("", de_home, german, [])
    module.on_page_markdown("", without, SimpleNamespace(plugins={}), [])

    card = {"social": {"cards_layout_options": {"title": "Demo"}}}
    assert home.meta == card
    assert de_home.meta == card
    assert own.meta["social"]["cards_layout_options"] == {"title": "Own"}
    assert guide.meta == {}
    # Without the social plugin, no page has a card.
    assert without.meta == {}


def test_a_website_in_one_language_only_keeps_templates_from_search_engines() -> None:
    template = page_of("decisions/0000-template.html")
    page = page_of("guide.html")
    one = SimpleNamespace(site_url=SITE, plugins={"material/search": object()})
    head = "<head></head>"

    assert hooks().on_post_page(head, template, one) == (
        '<head><meta name="robots" content="noindex, follow"></head>'
    )
    assert hooks().on_post_page(head, page, one) == head
    # Without the search, no script asks for an index.
    assert hooks().on_post_page(head, page, bilingual(search=False)) == head


def written(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def test_the_search_of_each_language_finds_its_pages(tmp_path: Path) -> None:
    def entry(location: str, title: str = "Title") -> dict[str, str]:
        return {"location": location, "title": title, "text": ""}

    docs = [
        entry("index.html"),
        entry("index.html#start", "Start"),
        entry("de/index.html"),
        entry("de/index.html#start", "Start"),
        entry("roadmap.html"),
        entry("roadmap.html#done", "Done"),
        # A section whose page an older build left out.
        entry("guide.html#install", "Install"),
        entry("ha-autodarts/games.html"),
        entry("ha-autodarts/de/games.html"),
        entry("ha-autodarts/coming-from.html"),
    ]
    index = tmp_path / "search/search_index.json"
    index.parent.mkdir()
    settings = {"lang": ["en", "de"], "separator": "[\\s\\-]+"}
    index.write_text(json.dumps({"config": settings, "docs": docs}), encoding="utf-8")
    module = hooks()
    module.BUILT.untranslated.add("de/roadmap.html")

    module.on_post_build(config(tmp_path, ("en", True, True), ("de", False, True)))

    every = written(index)
    english = written(tmp_path / "search/search_index.en.json")
    german = written(tmp_path / "search/search_index.de.json")
    assert every["config"] == english["config"] == german["config"] == settings
    assert every["docs"] == [*docs[:6], entry("guide.html", "Install"), *docs[6:]]
    assert [doc["location"] for doc in english["docs"]] == [
        "index.html",
        "index.html#start",
        "roadmap.html",
        "roadmap.html#done",
        "guide.html",
        "guide.html#install",
        "ha-autodarts/games.html",
        "ha-autodarts/coming-from.html",
    ]
    assert [doc["location"] for doc in german["docs"]] == [
        "de/index.html",
        "de/index.html#start",
        "de/roadmap.html",
        "de/roadmap.html#done",
        "guide.html",
        "guide.html#install",
        "ha-autodarts/de/games.html",
        "ha-autodarts/coming-from.html",
    ]
    assert german["docs"][3] == entry("de/roadmap.html#done", "Done")
    # After the i18n plugin and the hooks of a project that add to the index.
    assert module.on_post_build.mkdocs_priority == -120


@pytest.mark.parametrize(
    ("bundle", "warnings"),
    [
        ('var r=new XMLHttpRequest;r.open("GET","search/search_index.json")', 0),
        ('fetch(new URL("search/search_index.json",base))', 1),
    ],
)
def test_a_material_that_asks_for_its_index_otherwise_stops_the_build(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, bundle: str, warnings: int
) -> None:
    index = tmp_path / "search/search_index.json"
    index.parent.mkdir()
    index.write_text(json.dumps({"config": {}, "docs": []}), encoding="utf-8")
    scripts = tmp_path / "assets/javascripts"
    scripts.mkdir(parents=True)
    (scripts / "bundle.d7400e89.min.js").write_text(bundle, encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="mkdocs.hooks.blueprint"):
        hooks().on_post_build(config(tmp_path, ("en", True, True), ("de", False, True)))

    assert len(caplog.records) == warnings
    # A warning of a logger of MkDocs stops the strict build.
    assert all(record.name.startswith("mkdocs.") for record in caplog.records)
    assert all("SEARCH_SCRIPT" in record.getMessage() for record in caplog.records)


SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url>
        <loc>{site}roadmap.html</loc>
        <lastmod>2026-10-18</lastmod>
        <xhtml:link rel="alternate" hreflang="en" href="{site}roadmap.html"/>
        <xhtml:link rel="alternate" hreflang="de" href="{site}de/roadmap.html"/>
    </url>
    <url>
        <loc>{site}de/roadmap.html</loc>
        <xhtml:link rel="alternate" hreflang="de" href="{site}de/roadmap.html"/>
    </url>
    <url>
         <loc>{site}decisions/0000-template.html</loc>
    </url>
</urlset>"""
LISTED = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url>
        <loc>{site}roadmap.html</loc>
        <lastmod>2026-10-18</lastmod>
        <xhtml:link rel="alternate" hreflang="en" href="{site}roadmap.html"/>
    </url>
</urlset>"""


def unlisting(tmp_path: Path, *locales: tuple[str, bool, bool]) -> None:
    """Build a website whose sitemaps list two pages that no search engine should."""
    (tmp_path / "sitemap.xml").write_text(SITEMAP.format(site=SITE), encoding="utf-8")
    with gzip.GzipFile(
        tmp_path / "sitemap.xml.gz", "wb", mtime=1_700_000_000
    ) as zipped:
        zipped.write(SITEMAP.format(site=SITE).encode("utf-8"))
    module = hooks()
    module.BUILT.unlisted |= {
        SITE + "de/roadmap.html",
        SITE + "decisions/0000-template.html",
    }
    module.on_post_build(config(tmp_path, *locales))


def test_the_sitemaps_leave_out_what_search_engines_should_not_list(
    tmp_path: Path,
) -> None:
    site(tmp_path, "index.html", "de/index.html")

    unlisting(tmp_path, ("en", True, True), ("de", False, True))

    for path in ("sitemap.xml", "de/sitemap.xml"):
        assert (tmp_path / path).read_text(encoding="utf-8") == LISTED.format(site=SITE)
    with gzip.GzipFile(tmp_path / "sitemap.xml.gz") as zipped:
        assert zipped.read().decode("utf-8") == LISTED.format(site=SITE)
        assert zipped.mtime == 1_700_000_000


def test_a_website_in_one_language_leaves_templates_out_of_its_sitemap(
    tmp_path: Path,
) -> None:
    site(tmp_path, "index.html")

    unlisting(tmp_path)

    sitemap = (tmp_path / "sitemap.xml").read_text(encoding="utf-8")
    assert sitemap == LISTED.format(site=SITE)
    assert not (tmp_path / "search").exists()


def test_the_i18n_plugin_keeps_every_entry_of_the_search() -> None:
    settings = (ROOT / ".github/mkdocs-blueprint.yml").read_text(encoding="utf-8")
    # Its removal of the entries that look like the default language's took pages
    # out of the index and left their sections under .../undefined.
    assert "\n  i18n:\n    enabled: false\n    docs_structure: suffix\n" in settings
    assert "\n    reconfigure_search: false\n" in settings


# ---------------------------------------------------------- the page of the automation

BLUEPRINT = "https://github.com/Dennis-Otto/repo-blueprint"
WORKFLOWS = {
    "ci.yml": f"""name: CI

# The checks of every change, as scripts/check.sh runs them.
# {BLUEPRINT}

on:
  push:
    branches: [main]
  pull_request:
  workflow_dispatch:

jobs:
  check:
    name: check (python)
    runs-on: ubuntu-24.04
""",
    "release.yml": """# SPDX-FileCopyrightText: 2026 Dennis Otto
# SPDX-License-Identifier: MIT

name: Release

# The release bot: `release-please` keeps a pull request for the next release,
# as the docs say (https://example.org/docs).
#
# ```mermaid at the start of a line, <b>bold</b> & co
# stay text.

on:
  push:
    branches: [main]
    paths: ["src/**"]
  schedule:
    - cron: "25 5 * * *"
  workflow_dispatch:

jobs:
  release-please:
    name: release pull request
    environment:
      name: release
      deployment: false
    steps:
      - env:
          KEY: ${{ secrets.RELEASE_APP_KEY }}
          TOKEN: ${{ secrets.GITHUB_TOKEN }}
  pypi:
    name: deliver to PyPI
    needs: release-please
    environment: pypi
""",
    "after-checks.yml": """name: After the checks

# The bots that act on the end of a run.

on:
  workflow_run:
    workflows: [CI, Release, Gone]
    types: [completed]

jobs:
  rerun:
    runs-on: ubuntu-24.04
""",
    "rollout.yml": """name: Rollout

# Only in the blueprint.

on: workflow_dispatch

jobs:
  plan:
    if: github.repository != 'Owner/Demo'
  rollout:
    needs: [plan]
  report:
    needs: rollout
""",
    "nightly.yaml": """name: Nightly

on:
  schedule:
    - cron: "0 3 * * 1-5"
    - cron: "0 3 * * 1-5"

jobs:
  sweep:
    if: ${{ github.repository != 'Someone/Else' }}
""",
    "greet.yml": """on: [issues, issue_comment, discussion]
jobs:
  hello:
    runs-on: ubuntu-24.04
""",
    "security.yml": """name: Security
on:
  pull_request_target:
  pull_request:
    paths-ignore: ["docs/**"]
jobs: {}
""",
    "broken.yml": "name: [unclosed\n",
}


def repository(root: Path, *, settings: bool = True) -> Path:
    """A repository with the workflows of WORKFLOWS and the required checks of its
    settings as code, both files of them."""
    folder = root / ".github/workflows"
    folder.mkdir(parents=True)
    for name, text in WORKFLOWS.items():
        (folder / name).write_text(text, encoding="utf-8")
    (root / "docs").mkdir()
    if settings:
        (root / ".github/repository.toml").write_text(
            '[branch]\nrequired_checks = ["check (python)", "conventional title"]\n',
            encoding="utf-8",
        )
        (root / ".github/repository.project.toml").write_text(
            '[branch]\nrequired_checks = ["release pull request", "check (python)"]\n',
            encoding="utf-8",
        )
    return folder


def website(root: Path, *locales: str, **more: Any) -> Any:
    """The parts of the configuration of the website of the repository at root that
    the page of the automation reads, in the languages locales, the first the
    default one, or in one language."""
    plugins: dict[str, Any] = {}
    if locales:
        plugins["i18n"] = SimpleNamespace(
            config=SimpleNamespace(
                languages=[
                    SimpleNamespace(locale=locale, default=not index, build=True)
                    for index, locale in enumerate(locales)
                ]
            ),
            current_language=locales[0],
        )
    return SimpleNamespace(
        **{
            "config_file_path": str(root / "mkdocs.yml"),
            "docs_dir": str(root / "docs"),
            "site_dir": str(root / "site"),
            "use_directory_urls": False,
            "site_name": 'Demo "Project"',
            "repo_url": "https://github.com/owner/demo/",
            "edit_uri": None,
            "theme": {"language": "en"},
            "plugins": plugins,
            **more,
        }
    )


def automation(tmp_path: Path, *locales: str, **more: Any) -> dict[str, str]:
    """The pages of the automation that the hooks write for the repository of
    WORKFLOWS, by their paths in docs/."""
    folder = repository(tmp_path)
    pages: dict[str, str] = hooks().automation_pages(
        folder, website(tmp_path, *locales, **more)
    )
    return pages


def test_the_automation_page_shows_every_workflow_with_its_comment(
    tmp_path: Path,
) -> None:
    page = automation(tmp_path)["automation.md"]

    assert page.startswith(
        "---\n"
        'description: "How Demo \\"Project\\" looks after itself: its 7 workflows'
        " of GitHub Actions, what starts each one, which checks a pull request needs"
        ' and which workflows hold secrets."\n'
        "---\n\n# Automation\n\nHow this repository looks after itself: its 7"
        " workflows of GitHub Actions"
    )
    # Every workflow that runs here, in its group and by the name of its file; the
    # rollout runs elsewhere alone, and its other jobs wait for that one.
    headings = re.findall(r"^#{2,3} .*$", page, re.M)
    assert headings == [
        "## What a pull request needs {#required-checks}",
        "## At a glance {#at-a-glance}",
        "## Checks {#checks}",
        "### CI {#ci}",
        "## Releases {#releases}",
        "### Release {#release}",
        "## Bots {#bots}",
        "### After the checks {#after-checks}",
        "### broken {#broken}",
        "### greet {#greet}",
        "## Security {#security}",
        "### Security {#security-workflow}",
        "## Maintenance {#maintenance}",
        "### Nightly {#nightly}",
    ]
    # The comment at the top, without the lines of the license; code and addresses
    # as such, and nothing of it as Markdown or HTML.
    assert (
        "<p>The release bot: <code>release-please</code> keeps a pull request for the"
        " next release, as the docs say"
        ' (<a href="https://example.org/docs">https://example.org/docs</a>).</p>\n\n'
        "<p>```mermaid at the start of a line, &lt;b&gt;bold&lt;/b&gt; &amp; co stay"
        " text.</p>\n"
    ) in page
    assert "SPDX" not in page
    # The address of the blueprint names where a workflow comes from.
    assert "<p>The checks of every change, as scripts/check.sh runs them.</p>\n" in page
    assert (
        "- **Source:** [`.github/workflows/ci.yml`]"
        "(https://github.com/owner/demo/blob/HEAD/.github/workflows/ci.yml),"
        f" from the [Repo Blueprint]({BLUEPRINT})\n"
    ) in page
    assert (
        "- **Source:** [`.github/workflows/release.yml`]"
        "(https://github.com/owner/demo/blob/HEAD/.github/workflows/release.yml)\n"
    ) in page
    assert "Rollout" not in page


def test_the_automation_page_says_what_starts_each_workflow(tmp_path: Path) -> None:
    page = automation(tmp_path)["automation.md"]

    assert (
        "- **When:** every push to <code>main</code> that changes certain files,"
        " every day at 05:25 UTC, by hand\n"
    ) in page
    assert (
        "- **When:** after a run of [CI](#ci), [Release](#release) or Gone\n"
    ) in page
    # Two schedules alike are one.
    assert (
        "- **When:** every Monday, Tuesday, Wednesday, Thursday and Friday at"
        " 03:00 UTC\n"
    ) in page
    assert "- **When:** new and changed issues, comments, the event" in page
    assert "<code>discussion</code>\n" in page
    # A pull request with the workflow of main is a pull request as well.
    assert "- **When:** every pull request, every pull request that changes" in page
    # The table at a glance counts the workflows after whose run one runs.
    assert "| [After the checks](#after-checks) | after 3 workflows |\n" in page
    assert (
        "| [CI](#ci) | every push to <code>main</code>, every pull request, by hand |\n"
    ) in page
    assert "| [broken](#broken) |  |\n" in page


def test_the_automation_page_names_the_checks_that_main_requires(
    tmp_path: Path,
) -> None:
    page = automation(tmp_path)["automation.md"]

    # Of both files of the settings, each check once.
    assert (
        "\n- <code>check (python)</code> of [CI](#ci)\n"
        "- <code>conventional title</code>\n"
        "- <code>release pull request</code> of [Release](#release)\n\n"
    ) in page
    assert "- **Required checks:** <code>check (python)</code>\n" in page
    assert "- **Required checks:** <code>release pull request</code>\n" in page
    assert "- **Environments:** <code>pypi</code>, <code>release</code>\n" in page
    assert "- **Secrets:** <code>RELEASE_APP_KEY</code>\n" in page
    assert "GITHUB_TOKEN" not in page


def test_the_automation_page_without_settings_or_an_address(tmp_path: Path) -> None:
    folder = repository(tmp_path, settings=False)
    module = hooks()

    page = module.automation_pages(folder, website(tmp_path, repo_url=None))[
        "automation.md"
    ]

    assert "{#required-checks}" not in page
    assert "Required checks" not in page
    assert "- **Source:** `.github/workflows/release.yml`\n" in page
    assert module.BUILT.sources == [folder]


def test_the_automation_page_speaks_the_languages_of_the_website(
    tmp_path: Path,
) -> None:
    pages = automation(tmp_path, "en", "de", "fr")

    # German has words of its own; French shows the English page.
    assert sorted(pages) == ["automation.de.md", "automation.md"]
    german = pages["automation.de.md"]
    assert "\n# Automatisierung\n" in german
    assert "## Was ein Pull Request braucht {#required-checks}" in german
    assert "- <code>check (python)</code> aus [CI](#ci)\n" in german
    assert (
        "- **Wann:** jeder Push auf <code>main</code>, der bestimmte Dateien ändert,"
        " jeden Tag um 05:25 UTC, von Hand\n"
    ) in german
    assert "aus dem [Repo Blueprint]" in german
    # The comments of the workflows are English, and say so to a screen reader.
    assert '<p lang="en">The release bot: ' in german
    assert "## Prüfungen {#checks}" in german


def test_a_page_of_the_project_takes_the_place_of_a_language(tmp_path: Path) -> None:
    folder = repository(tmp_path)
    (tmp_path / "docs/automation.de.md").write_text("# Eigene\n", encoding="utf-8")

    pages = hooks().automation_pages(folder, website(tmp_path, "en", "de"))

    assert sorted(pages) == ["automation.md"]


@pytest.mark.parametrize(
    ("language", "title"), [("de", "Automatisierung"), ("fr", "Automation")]
)
def test_the_page_of_a_website_in_one_language_speaks_it(
    tmp_path: Path, language: str, title: str
) -> None:
    pages = automation(tmp_path, theme={"language": language})

    assert list(pages) == ["automation.md"]
    assert f"\n# {title}\n" in pages["automation.md"]


def test_a_german_website_writes_the_default_page_in_german(tmp_path: Path) -> None:
    pages = automation(tmp_path, "de", "en")

    assert list(pages) == ["automation.md", "automation.en.md"]
    assert "\n# Automatisierung\n" in pages["automation.md"]
    assert "\n# Automation\n" in pages["automation.en.md"]


def test_the_blueprint_s_own_page_names_no_origin(tmp_path: Path) -> None:
    page = automation(tmp_path, repo_url=BLUEPRINT)["automation.md"]

    assert (
        f"- **Source:** [`.github/workflows/ci.yml`]({BLUEPRINT}/blob/HEAD/"
        ".github/workflows/ci.yml)\n"
    ) in page
    assert "from the [Repo Blueprint]" not in page


def test_a_profile_address_takes_the_repository_from_edit_uri(
    tmp_path: Path,
) -> None:
    site = "https://github.com/Dennis-Otto/dennis-otto.github.io"
    page = automation(
        tmp_path,
        repo_url="https://github.com/Dennis-Otto",
        edit_uri=f"{site}/edit/main/docs/",
    )["automation.md"]

    assert (
        f"- **Source:** [`.github/workflows/ci.yml`]({site}/blob/HEAD/"
        ".github/workflows/ci.yml), from the [Repo Blueprint]"
    ) in page
    assert "https://github.com/Dennis-Otto/blob/" not in page


@pytest.mark.parametrize(
    ("repo_url", "edit_uri"),
    [
        ("https://github.com/Dennis-Otto", "edit/main/docs/"),
        ("https://github.com/Dennis-Otto", None),
        ("https://github.com/Dennis-Otto", "https://github.com/Dennis-Otto/"),
        (None, None),
    ],
)
def test_without_the_address_of_a_repository_sources_are_plain(
    tmp_path: Path, repo_url: str | None, edit_uri: str | None
) -> None:
    page = automation(tmp_path, repo_url=repo_url, edit_uri=edit_uri)["automation.md"]

    assert "- **Source:** `.github/workflows/ci.yml`" in page
    assert "/blob/HEAD/" not in page


def test_the_required_checks_name_each_file_of_settings(tmp_path: Path) -> None:
    pages = automation(tmp_path, "en", "de")

    assert (
        "the settings in `.github/repository.toml` and "
        "`.github/repository.project.toml` require:"
    ) in pages["automation.md"]
    assert (
        "die Einstellungen in `.github/repository.toml` und "
        "`.github/repository.project.toml` verlangen:"
    ) in pages["automation.de.md"]


@pytest.mark.parametrize(
    ("expression", "english", "german"),
    [
        ("25 * * * *", "every hour at :25", "jede Stunde um :25"),
        ("5 */2 * * *", "every 2 hours at :05", "alle 2 Stunden um :05"),
        ("40 4 * * *", "every day at 04:40 UTC", "jeden Tag um 04:40 UTC"),
        ("40 4 * * 2", "every Tuesday at 04:40 UTC", "jeden Dienstag um 04:40 UTC"),
        (
            "0 6 * * 0,7",
            "every Sunday and Sunday at 06:00 UTC",
            "jeden Sonntag und Sonntag um 06:00 UTC",
        ),
        (
            "0 6 * * 1,3-4",
            "every Monday, Wednesday and Thursday at 06:00 UTC",
            "jeden Montag, Mittwoch und Donnerstag um 06:00 UTC",
        ),
        (
            "15 1 1 * *",
            "on day 1 of every month at 01:15 UTC",
            "am 1. jedes Monats um 01:15 UTC",
        ),
        # What says more, or otherwise, stays as it is.
        (
            "0 6 * * MON",
            "on the schedule <code>0 6 * * MON</code>",
            "nach dem Zeitplan <code>0 6 * * MON</code>",
        ),
        ("0 6 * * 5-1", "on the schedule <code>0 6 * * 5-1</code>", ""),
        ("0 6 * * 1-2-3", "on the schedule <code>0 6 * * 1-2-3</code>", ""),
        ("0 6 * * 8", "on the schedule <code>0 6 * * 8</code>", ""),
        ("0 6 1 * 1", "on the schedule <code>0 6 1 * 1</code>", ""),
        ("0 6 * 1 *", "on the schedule <code>0 6 * 1 *</code>", ""),
        ("0 6,18 * * *", "on the schedule <code>0 6,18 * * *</code>", ""),
        ("0 */2 1 * *", "on the schedule <code>0 */2 1 * *</code>", ""),
        ("*/5 * * * *", "on the schedule <code>*/5 * * * *</code>", ""),
        ("@daily", "on the schedule <code>@daily</code>", ""),
    ],
)
def test_a_schedule_reads_as_words(expression: str, english: str, german: str) -> None:
    module = hooks()

    assert module.cron(expression, "en") == english
    if german:
        assert module.cron(expression, "de") == german


@pytest.mark.parametrize(
    ("file", "events", "group"),
    [
        ("ci-python.yml", {}, "checks"),
        ("pull-request-title.yml", {}, "checks"),
        ("e2e.yml", {}, "checks"),
        ("build-release.yml", {}, "releases"),
        ("verify-release.yml", {}, "releases"),
        ("dependency-review.yml", {}, "security"),
        ("dependabot-automerge.yml", {}, "bots"),
        ("blueprint-update.yml", {}, "bots"),
        ("docs-pictures.yml", {}, "bots"),
        ("area-labels.yml", {}, "bots"),
        ("labels.yml", {}, "maintenance"),
        ("bot-health.yml", {}, "maintenance"),
        # A workflow of a project, by what starts it.
        ("translate.yml", {"pull_request": None}, "checks"),
        ("nightly.yml", {"schedule": []}, "maintenance"),
        ("greet.yml", {"issues": None}, "bots"),
    ],
)
def test_each_workflow_has_its_group(
    file: str, events: dict[str, Any], group: str
) -> None:
    workflow = hooks().Workflow(file, "A workflow", (), events, (), (), ())

    assert workflow.group == group


def test_a_workflow_without_a_name_of_letters_has_an_anchor_still() -> None:
    workflow = hooks().Workflow("---.yml", "Dashes", (), {}, (), (), ())

    assert workflow.anchor == "-workflow"


def test_the_events_of_a_workflow_read_as_words() -> None:
    module = hooks()
    events = {
        "push": {"tags": ["v*"]},
        "schedule": "not a list",
        "workflow_run": {"types": ["completed"]},
        "workflow_call": None,
        "merge_group": None,
        "release": {"types": ["published"]},
    }

    workflow = module.Workflow("x.yml", "X", (), events, (), (), ())

    assert workflow.when("en", {}) == [
        "every new tag",
        "the event <code>workflow_run</code>",
        "when another workflow calls it",
        "the merge queue",
        "a release",
    ]
    assert module.Workflow("x.yml", "X", (), {"push": None}, (), (), ()).when(
        "de", {}
    ) == ["jeder Push"]
    after = module.Workflow(
        "x.yml", "X", (), {"workflow_run": {"workflows": ["CI"]}}, (), (), ()
    )
    assert after.when("en", {}, brief=True) == ["after a run of CI"]


def test_the_menu_gets_the_page_after_the_security_design(tmp_path: Path) -> None:
    repository(tmp_path)
    module = hooks()

    def menu(nav: Any) -> Any:
        config = website(tmp_path, nav=nav, extra_css=[], extra_javascript=[])
        module.on_config(config)
        return config.nav

    assert menu([{"Home": "index.md"}, {"Security design": "security.md"}, "x.md"]) == [
        {"Home": "index.md"},
        {"Security design": "security.md"},
        "automation.md",
        "x.md",
    ]
    assert menu(
        [
            {"Home": "index.md"},
            {"Guide": [{"Overview": "guide.md"}, "faq.md"]},
            {"Project": ["roadmap.md", "security.md", "changelog.md"]},
        ]
    ) == [
        {"Home": "index.md"},
        {"Guide": [{"Overview": "guide.md"}, "faq.md"]},
        {"Project": ["roadmap.md", "security.md", "automation.md", "changelog.md"]},
    ]
    # Without a security design, at the end; a menu that names it keeps it where it
    # is, and a website without a menu lists every page.
    assert menu(["index.md"]) == ["index.md", "automation.md"]
    assert menu([{"Bots": [{"Automation": "automation.md"}]}, "security.md"]) == [
        {"Bots": [{"Automation": "automation.md"}]},
        "security.md",
    ]
    assert menu(None) is None


def test_a_page_of_the_project_or_no_workflows_leave_the_menu_alone(
    tmp_path: Path,
) -> None:
    module = hooks()
    nav = ["index.md", "security.md"]
    config = website(tmp_path, nav=nav, extra_css=[], extra_javascript=[])
    (tmp_path / "docs").mkdir()

    module.on_config(config)
    assert nav == ["index.md", "security.md"]

    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / ".github/workflows/ci.yml").write_text("name: CI\n", encoding="utf-8")
    (tmp_path / "docs/automation.md").write_text("# Ours\n", encoding="utf-8")
    module.on_config(config)
    assert nav == ["index.md", "security.md"]


class Generated(File):
    """A file of MkDocs, which takes its text in place of the file in docs/, and the
    page that MkDocs makes of it."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.generated_by: str | None = None
        self.page: Any = SimpleNamespace(edit_url="edit/main/docs/" + self.src_uri)

    @property
    def content_string(self) -> str:
        raise AssertionError("read only by MkDocs")

    @content_string.setter
    def content_string(self, text: str) -> None:
        self.text = text
        self.abs_src_path = None


def test_the_website_gets_the_page_of_the_automation_in_each_language(
    tmp_path: Path,
) -> None:
    repository(tmp_path)
    module = hooks()
    config = website(tmp_path, "en", "de")
    stylesheet = Generated("extra.css", str(tmp_path / "docs"), config.site_dir, False)

    files = module.on_files([stylesheet], config)

    # Files of docs/ that the folder lacks, which the i18n plugin takes as pages.
    pages = [file for file in files if file.src_uri.startswith("automation")]
    assert [file.src_uri for file in pages] == ["automation.md", "automation.de.md"]
    assert pages[0].abs_src_path == str(tmp_path / "docs/automation.md")
    # After the i18n plugin, each gets its text, no pencil and no date of its own.
    pages[1].page = None
    assert module.on_nav("the menu", config, files) == "the menu"
    assert pages[0].text == module.BUILT.pages["automation.md"]
    assert "\n# Automatisierung\n" in pages[1].text
    assert pages[0].abs_src_path is None
    assert pages[0].generated_by == module.__name__
    assert pages[0].page.edit_url is None
    assert stylesheet.page.edit_url == "edit/main/docs/extra.css"
    assert stylesheet.generated_by is None


def test_a_website_without_workflows_gets_no_page_of_them(tmp_path: Path) -> None:
    module = hooks()
    module.BUILT.pages = {"automation.md": "# Stale"}
    (tmp_path / "docs").mkdir()
    config = website(tmp_path)
    index = Generated("index.md", config.docs_dir, config.site_dir, False)

    files = module.on_files([index], config)

    assert [file.dest_uri for file in files] == [
        "index.md",
        "assets/stylesheets/blueprint.css",
        "assets/javascripts/blueprint.js",
    ]
    assert module.BUILT.pages == {}


def test_the_page_of_the_automation_is_dated_by_its_workflows(
    tmp_path: Path,
) -> None:
    folder = repository(tmp_path)
    module = hooks()
    plugin = Dates(
        {"workflows": 300, "repository.toml": 400, "repository.project.toml": 200}
    )
    settings = website(tmp_path, "en", "de", mdx_configs={})
    settings.plugins["git-revision-date-localized"] = plugin
    module.BUILT.pages = module.automation_pages(folder, settings)
    page = page_of("automation.html")
    page.file.abs_src_path = None
    page.meta["git_revision_date_localized"] = "the date of the build"

    module.redate("# Automation", page, settings)

    assert plugin.rendered == [
        ("en", "git_revision_date_localized", "hash of repository.toml", 400)
    ]


def test_a_page_of_another_plugin_keeps_the_date_of_the_build(
    tmp_path: Path,
) -> None:
    module = hooks()
    plugin = Dates({})
    settings = bilingual(
        "de", config_file_path=str(tmp_path / "mkdocs.yml"), mdx_configs={}
    )
    settings.plugins["git-revision-date-localized"] = plugin
    # A page that another plugin writes, which German shows untranslated.
    page = page_of("de/generated.html")
    page.file.abs_src_path = None
    page.meta["git_revision_date_localized"] = "the date of the build"

    module.redate("# Generated", page, settings)

    assert plugin.rendered == []


@pytest.mark.parametrize(("language", "suffix"), [("en", ""), ("de", ".de")])
def test_the_automation_page_draws_the_diagrams_of_the_readme(
    language: str, suffix: str
) -> None:
    overview, release = hooks().DIAGRAMS[language]
    sources = ROOT / "docs/diagrams"

    assert overview == (
        sources / f"how-a-repository-looks-after-itself{suffix}.mmd"
    ).read_text(encoding="utf-8")
    assert release == (sources / f"from-a-change-to-a-release{suffix}.mmd").read_text(
        encoding="utf-8"
    )


def test_the_page_of_the_automation_draws_its_diagrams_live(tmp_path: Path) -> None:
    page = automation(tmp_path)["automation.md"]
    overview, release = hooks().DIAGRAMS["en"]

    assert f"\n```mermaid\n{overview}```\n" in page
    assert "## Releases {#releases}\n\nThey make a signed release" in page
    assert f"\n```mermaid\n{release}```\n\n### Release {{#release}}\n" in page


def test_the_blueprint_and_every_repository_list_the_page_in_the_menu() -> None:
    # The blueprint names it and translates the name; the template lists the page
    # alone, so that each language shows the title of its page.
    for path, entry in (
        ("mkdocs.yml", "Automation: automation.md"),
        ("template/mkdocs.yml.jinja", "automation.md"),
    ):
        config = (ROOT / path).read_text(encoding="utf-8")
        assert f"\n  - Security design: security.md\n  - {entry}\n" in config, path
    assert "\n          Automation: Automatisierung\n" in (
        ROOT / "mkdocs.yml"
    ).read_text(encoding="utf-8")


def test_a_group_without_workflows_has_no_heading(tmp_path: Path) -> None:
    folder = tmp_path / ".github/workflows"
    folder.mkdir(parents=True)
    (tmp_path / "docs").mkdir()
    # A file of comments alone, which is no workflow yet.
    (folder / "draft.yml").write_text("# A draft,\n# of a bot.\n", encoding="utf-8")

    page = hooks().automation_pages(folder, website(tmp_path))["automation.md"]

    assert re.findall(r"^#{2,3} .*$", page, re.M) == [
        "## At a glance {#at-a-glance}",
        "## Bots {#bots}",
        "### draft {#draft}",
    ]
    assert "\n<p>A draft, of a bot.</p>\n" in page
