"""Tests of the hooks of the documentation website, .github/mkdocs_blueprint.py."""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

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
    hooks().on_config(SimpleNamespace(plugins={"material/privacy": privacy}))
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
        }
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
