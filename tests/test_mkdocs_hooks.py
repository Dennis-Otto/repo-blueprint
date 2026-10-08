"""Tests of the hooks of the documentation website, .github/mkdocs_blueprint.py."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace

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


def config(site: Path, *locales: tuple[str, bool, bool]) -> SimpleNamespace:
    """The parts of a MkDocs configuration that the hook reads: the i18n plugin with
    its languages as (locale, default, build), or no such plugin."""
    plugins: dict[str, SimpleNamespace] = {}
    if locales:
        languages = [
            SimpleNamespace(locale=locale, default=default, build=build)
            for locale, default, build in locales
        ]
        plugins["i18n"] = SimpleNamespace(config=SimpleNamespace(languages=languages))
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
