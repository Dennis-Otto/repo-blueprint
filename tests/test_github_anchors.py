"""Tests of .github/github_anchors.py, the anchors of the headings of the website.

The headings are rendered with the Markdown extensions of .github/mkdocs-blueprint.yml,
and GitHub's anchors come from GitHub itself: its renderer, POST /markdown in the mode
markdown, gave these ids (user-content-...) on 2026-11-23, and the tables of
https://github.com/Dennis-Otto/repo-blueprint/issues/1117 have the same.
"""

from __future__ import annotations

import importlib
import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, ClassVar

import markdown
import pytest
import yaml
from hypothesis import given
from hypothesis import strategies as st
from markdown.treeprocessors import Treeprocessor
from shared import YAML_LOADER

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / ".github/mkdocs-blueprint.yml"
HEADING_ID = re.compile(r'<h[1-6] id="([^"]*)"')

NBSP = "\u00a0"
NNBSP = "\u202f"
# Each heading in a document of its own, with the id that GitHub gave it.
GITHUB = [
    # French: a no-break space before ?, !, : and », after «.
    (f"De quoi ai-je besoin{NBSP}?", "de-quoi-ai-je-besoin"),
    (f"Qu'est-ce qui quitte mon réseau{NBSP}?", "quest-ce-qui-quitte-mon-réseau"),
    (
        "Ma cible Autodarts n'a pas encore de caméras. Puis-je compter à la main"
        f"{NBSP}?",
        "ma-cible-autodarts-na-pas-encore-de-caméras-puis-je-compter-à-la-main",
    ),
    (f"Attention{NNBSP}!", "attention"),
    (f"«{NBSP}Citation{NBSP}»", "citation"),
    (f"Note{NBSP}: deux points", "note-deux-points"),
    (f"Trois{NBSP}{NBSP}fois", "troisfois"),
    # A plain space before ? stays a hyphen, there as here.
    ("Puis-je jouer ?", "puis-je-jouer-"),
    # Two spaces, also those around inline HTML, are two hyphens.
    ("Deux  espaces", "deux--espaces"),
    ("A <br> B", "a--b"),
    ("Comment <!-- c --> here", "comment--here"),
    ("Code `a  b` here", "code-a--b-here"),
    # An emoji shortcode counts with its name, an alias with the name written.
    ("Emoji :dart: dart", "emoji-dart-dart"),
    ("Emoji :tada: :dart:", "emoji-tada-dart"),
    ("Snake :snake:", "snake-snake"),
    ("Thumbs :+1: up", "thumbs-1-up"),
    # What agreed before agrees still: escapes, entities, inline code, links, emphasis,
    # accents, apostrophes, typographic quotes, ¿ and a raw emoji.
    ("Un \\_x\\_ fin", "un-_x_-fin"),
    ("R&amp;D", "rd"),
    ("De quoi ai-je besoin&nbsp;?", "de-quoi-ai-je-besoin"),
    ("Encore&#160;?", "encore"),
    ("Run `blueprint.py fix` now", "run-blueprintpy-fix-now"),
    ("See [the guide](guide.md) here", "see-the-guide-here"),
    ("Une *belle* idée", "une-belle-idée"),
    ("Équipe à côté", "équipe-à-côté"),
    ("L'équipe d'été", "léquipe-dété"),
    ("\u201cQuoted\u201d \u2018single\u2019 it\u2019s", "quoted-single-its"),
    ("¿Qué necesito?", "qué-necesito"),
    ("Raw 🎯 dart", "raw--dart"),
]


def load_anchors() -> ModuleType:
    """.github/github_anchors.py under the name that markdown_extensions gives it, as
    MkDocs imports it once the tag of .github/mkdocs-blueprint.yml put .github on the
    path of Python."""
    spec = importlib.util.spec_from_file_location(
        "github_anchors", ROOT / ".github/github_anchors.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["github_anchors"] = module
    spec.loader.exec_module(module)
    return module


anchors = load_anchors()

# Material for MkDocs, which the tools of the tests don't bring, gives these names of
# .github/mkdocs-blueprint.yml: its index of the emoji is that of pymdownx.emoji with
# Material's icons added, and its generator hands every emoji with a code point to
# that of pymdownx.emoji.
MATERIAL = {
    "material.extensions.emoji.twemoji": "pymdownx.emoji.twemoji",
    "material.extensions.emoji.to_svg": "pymdownx.emoji.to_svg",
}


def python_name(name: str) -> Any:
    """The object that a tag !!python/name or !!python/object/apply names."""
    module, _, attribute = MATERIAL.get(name, name).rpartition(".")
    return getattr(importlib.import_module(module), attribute)


class SettingsLoader(YAML_LOADER):  # type: ignore[misc]
    """YAML as MkDocs reads .github/mkdocs-blueprint.yml, with its tags of Python, which
    records the folders that the tags put on the path of Python instead."""

    site_dirs: ClassVar[list[str]] = []


def construct_name(loader: SettingsLoader, suffix: str, node: yaml.Node) -> Any:
    return python_name(suffix)


def construct_apply(loader: SettingsLoader, suffix: str, node: yaml.Node) -> Any:
    if isinstance(node, yaml.SequenceNode):
        args, kwds = loader.construct_sequence(node), {}
    else:
        mapping = loader.construct_mapping(node, deep=True)
        args, kwds = mapping.get("args", []), mapping.get("kwds", {})
    if suffix == "site.addsitedir":
        SettingsLoader.site_dirs.extend(args)
        return None
    return python_name(suffix)(*args, **kwds)


def construct_environment(loader: SettingsLoader, node: yaml.Node) -> Any:
    # A variable of the environment, such as CI, as where it isn't set: the default.
    return loader.construct_sequence(node)[-1]


SettingsLoader.add_constructor("!ENV", construct_environment)
SettingsLoader.add_multi_constructor("tag:yaml.org,2002:python/name:", construct_name)
SettingsLoader.add_multi_constructor(
    "tag:yaml.org,2002:python/object/apply:", construct_apply
)


def settings() -> dict[str, Any]:
    """The configuration of .github/mkdocs-blueprint.yml."""
    loaded: dict[str, Any] = yaml.load(
        SETTINGS.read_text(encoding="utf-8"), Loader=SettingsLoader
    )
    return loaded


def website_markdown(*leave_out: str, **more: dict[str, Any]) -> markdown.Markdown:
    """Python-Markdown with the extensions of the website and their settings, without
    those named in leave_out, and with the settings in more for the extensions."""
    extensions = settings()["markdown_extensions"]
    names = [name for name in extensions if name not in leave_out]
    configs = {name: extensions[name] or {} for name in names}
    for name, config in more.items():
        configs[name] = {**configs[name], **config}
    return markdown.Markdown(extensions=names, extension_configs=configs)


WEBSITE = website_markdown()
TOC_ALONE = website_markdown("github_anchors")


def ids(text: str, md: markdown.Markdown = WEBSITE) -> list[str]:
    """The ids of the headings of the page, as the website makes them."""
    md.reset()
    return HEADING_ID.findall(md.convert(text))


@pytest.mark.parametrize(("heading", "github"), GITHUB)
def test_a_heading_gets_the_anchor_that_github_gives_it(
    heading: str, github: str
) -> None:
    assert ids(f"## {heading}\n") == [github]


def test_without_the_extension_a_no_break_space_was_a_hyphen() -> None:
    # What toc alone makes, and the reason for the extension.
    assert ids(f"## De quoi ai-je besoin{NBSP}?\n", TOC_ALONE) == [
        "de-quoi-ai-je-besoin-"
    ]
    assert ids("## Deux  espaces\n", TOC_ALONE) == ["deux-espaces"]
    assert ids("## Emoji :dart: dart\n", TOC_ALONE) == ["emoji-dart"]


def test_an_id_that_a_page_gives_a_heading_stays() -> None:
    page = (
        "## Propre {#own-id}\n\n"
        f'## <a id="kept"></a>Ancre{NBSP}?\n\n'
        "## Options\n\n## Options {#options_2}\n\n## Options\n"
    )
    html = WEBSITE.reset().convert(page)
    assert HEADING_ID.findall(html) == [
        "own-id",
        "ancre",
        "options",
        "options_2",
        "options_1",
    ]
    assert '<a id="kept"></a>' in html


def test_a_repeated_heading_keeps_its_number_with_an_underscore() -> None:
    # GitHub numbers them -1, -2; changing these ids is a decision of its own.
    page = "## Options\n\n### Options\n\n## Options\n\n## Options 1\n"
    assert ids(page) == ["options", "options_1", "options_2", "options-1"]
    assert ids(page) == ids(page, TOC_ALONE)


def test_a_footnote_counts_with_nothing() -> None:
    page = "## Note[^1] here\n\n[^1]: The note.\n"
    assert ids(page) == ids(page, TOC_ALONE) == ["note-here"]


# Words that GitHub and toc read alike, with one space between them: every such
# heading keeps the id that it has. A colon could make an emoji of a word, such as
# :tada:, which the table above has.
WORDS = st.lists(
    st.text(
        alphabet=st.characters(
            categories=["Lu", "Ll", "Nd"], include_characters="'?!.,-()/¿éàçÉ"
        ),
        min_size=1,
        max_size=8,
    ),
    min_size=1,
    max_size=6,
)


@given(WORDS)
def test_a_heading_that_toc_and_github_read_alike_keeps_its_id(
    words: list[str],
) -> None:
    page = f"## {' '.join(words)}\n"
    assert ids(page) == ids(page, TOC_ALONE)


def test_the_strict_check_of_mkdocs_sees_the_ids_of_the_extension() -> None:
    # MkDocs collects the anchors of a page for its strict check with a
    # treeprocessor at the priority of toc, registered after the extensions.
    seen: list[str] = []

    class Anchors(Treeprocessor):
        def run(self, root: Any) -> None:
            seen.extend(e.get("id") for e in root.iter() if e.get("id"))

    md = website_markdown()
    md.treeprocessors.register(Anchors(md), "mkdocs_extract_anchors", 5)
    ids(f"## De quoi ai-je besoin{NBSP}?\n", md)
    assert seen == ["de-quoi-ai-je-besoin"]
    assert anchors.PRIORITY == 6
    assert md.treeprocessors.get_index_for_name("attr_list") < (
        md.treeprocessors.get_index_for_name("abbr")
    )
    assert md.treeprocessors.get_index_for_name("abbr") < (
        md.treeprocessors.get_index_for_name("github_anchors")
    )
    assert md.treeprocessors.get_index_for_name("github_anchors") < (
        md.treeprocessors.get_index_for_name("toc")
    )


def test_without_toc_no_heading_gets_an_id() -> None:
    md = markdown.Markdown(extensions=["github_anchors"])
    assert md.convert("## Deux  espaces\n") == "<h2>Deux  espaces</h2>"


def test_without_the_emoji_a_shortcode_is_text_as_on_github() -> None:
    md = markdown.Markdown(extensions=["toc", "github_anchors"])
    assert ids("## Emoji :dart: dart\n", md) == ["emoji-dart-dart"]


def test_only_the_title_of_an_emoji_counts() -> None:
    # A picture with a title, and an emoji whose title is its long name, count
    # with nothing, and the spaces around them stay two, as on GitHub.
    picture = '## Pic ![alt](p.png ":x:") end\n'
    assert ids(picture) == ["pic--end"]
    long = website_markdown(**{"pymdownx.emoji": {"title": "long"}})
    assert ids("## Emoji :dart: dart\n", long) == ["emoji--dart"]


def test_the_website_names_the_extension_and_puts_its_folder_on_the_path() -> None:
    SettingsLoader.site_dirs.clear()
    extensions = settings()["markdown_extensions"]
    # No options, and the folder of the extension on the path of Python, from the
    # folder of mkdocs.yml, where MkDocs and Zensical run.
    assert "github_anchors" in extensions
    assert extensions["github_anchors"] is None
    assert SettingsLoader.site_dirs == [".github"]
    text = SETTINGS.read_text(encoding="utf-8")
    assert (
        "\n  github_anchors: !!python/object/apply:site.addsitedir [.github]\n" in text
    )


def test_python_finds_the_extension_by_its_name_from_the_root() -> None:
    # As MkDocs and Zensical find it: by its name, once the tag of the settings put
    # .github on the path, in a Python of its own, with the slugify of the website.
    script = (
        "import site, markdown, pymdownx.slugs; site.addsitedir('.github');"
        " slugify = pymdownx.slugs.slugify(case='lower');"
        " print(markdown.markdown('## Deux  espaces', extensions=['toc', 'github_anchors'],"
        " extension_configs={'toc': {'slugify': slugify}}))"
    )
    shown = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert shown == '<h2 id="deux--espaces">Deux  espaces</h2>\n'


def test_the_strict_build_of_the_website_links_to_a_no_break_space() -> None:
    # The real check of MkDocs and Zensical: without the extension, the heading
    # has de-quoi-ai-je-besoin-, and the strict build fails on these links.
    record = next((ROOT / "docs/decisions").glob("1117-*.md"))
    assert f"\n## De quoi ai-je besoin{NBSP}?\n" in record.read_text(encoding="utf-8")
    link = f"](../decisions/{record.name}#de-quoi-ai-je-besoin)"
    for page in ("website.md", "website.de.md"):
        assert link in (ROOT / "docs/features" / page).read_text(encoding="utf-8")
