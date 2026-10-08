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


def test_every_further_language_gets_the_sitemap(tmp_path: Path) -> None:
    (tmp_path / "sitemap.xml").write_text("<urlset/>\n", encoding="utf-8")

    hooks().on_post_build(
        config(tmp_path, ("en", True, True), ("de", False, True), ("fr", False, False))
    )

    assert (tmp_path / "de/sitemap.xml").read_text(encoding="utf-8") == "<urlset/>\n"
    assert not (tmp_path / "en").exists()
    assert not (tmp_path / "fr").exists()


def test_a_website_in_one_language_keeps_its_one_sitemap(tmp_path: Path) -> None:
    (tmp_path / "sitemap.xml").write_text("<urlset/>\n", encoding="utf-8")

    hooks().on_post_build(config(tmp_path))

    assert sorted(path.name for path in tmp_path.iterdir()) == ["sitemap.xml"]


def test_without_a_sitemap_nothing_is_copied(tmp_path: Path) -> None:
    hooks().on_post_build(config(tmp_path, ("en", True, True), ("de", False, True)))

    assert list(tmp_path.iterdir()) == []
