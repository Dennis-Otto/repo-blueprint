"""Tests of the hooks of the documentation website, .github/mkdocs_blueprint.py."""

from __future__ import annotations

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
            plugins={"material/privacy": privacy}, extra_css=[], extra_javascript=[]
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
        plugins={}, extra_css=["stylesheets/extra.css"], extra_javascript=[project]
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
        page=SimpleNamespace(file=files[-1]),
        config=SimpleNamespace(docs_dir=str(docs)),
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
        '<p><img alt="Badge" src="https://img.shields.io/badge/a-b-blue.svg"></p>\n'
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
        '<p><img alt="Badge" src="https://img.shields.io/badge/a-b-blue.svg"'
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
