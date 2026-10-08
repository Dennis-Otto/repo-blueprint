"""Tests of the hooks of the blueprint's own website, .github/mkdocs_project.py."""

from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType, SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def hooks() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "mkdocs_project", ROOT / ".github/mkdocs_project.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@dataclass
class File:
    """The parts of a file of MkDocs that the hook reads, with its constructor."""

    src_uri: str
    src_dir: str | None
    dest_dir: str
    use_directory_urls: bool
    dest_uri: str = ""
    abs_dest_path: str = ""

    def __post_init__(self) -> None:
        self.dest_uri = self.dest_uri or self.src_uri
        self.abs_dest_path = self.abs_dest_path or os.path.join(
            self.dest_dir, self.dest_uri
        )

    def is_media_file(self) -> bool:
        return not self.src_uri.endswith((".md", ".css", ".js", ".html"))


def config(root: Path) -> SimpleNamespace:
    return SimpleNamespace(docs_dir=str(root / "docs"), site_dir=str(root / "site"))


def test_a_picture_of_docs_has_the_name_that_the_readme_gives_it(
    tmp_path: Path,
) -> None:
    picture = File(
        "images/dashboard.png", str(tmp_path / "docs"), str(tmp_path / "site"), False
    )

    files = hooks().on_files([picture], config(tmp_path))

    assert files == [
        picture,
        File(
            "docs/images/dashboard.png",
            str(tmp_path),
            str(tmp_path / "site"),
            False,
            dest_uri="images/dashboard.png",
            abs_dest_path=picture.abs_dest_path,
        ),
    ]


def test_the_second_name_leads_where_the_i18n_plugin_puts_the_picture(
    tmp_path: Path,
) -> None:
    # The i18n plugin passes the place of a file as its folder and then sets where
    # it goes; the folder alone would lead out of the website.
    site = str(tmp_path / "site" / "images" / "dashboard.png")
    picture = File(
        "images/dashboard.png",
        str(tmp_path / "docs"),
        "images/dashboard.png",
        False,
        abs_dest_path=site,
    )

    alias = hooks().on_files([picture], config(tmp_path))[1]

    assert alias.src_uri == "docs/images/dashboard.png"
    assert alias.abs_dest_path == site


def test_pages_and_the_files_of_the_theme_keep_their_one_name(tmp_path: Path) -> None:
    files = [
        File("guide.md", str(tmp_path / "docs"), "site", False),
        File("assets/logo.png", str(tmp_path / "theme"), "site", False),
        File("sitemap.xml", None, "site", False),
    ]

    assert hooks().on_files(list(files), config(tmp_path)) == files


def test_the_names_come_after_the_files_of_every_language() -> None:
    # The i18n plugin makes them anew at -100, as the last of the plugins.
    assert hooks().on_files.mkdocs_priority < -100
