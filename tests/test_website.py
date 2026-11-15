"""Tests of the steps of a website that need no generator, blueprint/website.py, and
of blueprint.py website, which takes them for a build with another generator."""

from __future__ import annotations

import gzip
import importlib.util
import json
import shutil
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from blueprint import website
from blueprint.cli import main

ROOT = Path(__file__).resolve().parents[1]
ADDRESS = "https://owner.github.io/demo/"
CHECK = """name: CI

# The checks of every change.
# https://github.com/Dennis-Otto/repo-blueprint

on:
  pull_request:
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - run: echo
"""
NOINDEX = '<meta name="robots" content="noindex, follow">'


def hooks(at: Path | None = None) -> ModuleType:
    """The hooks of the website, as MkDocs loads them, from beside the blueprint's
    code; with at, as if they were the file at, beside the pictures there."""
    spec = importlib.util.spec_from_file_location(
        "mkdocs_blueprint_of_the_steps", ROOT / ".github/mkdocs_blueprint.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if at is not None:
        module.__file__ = str(at)
    return module


def draw(folder: Path, *languages: str) -> None:
    """The pictures of the diagrams of the page in folder, in each of languages."""
    folder.mkdir(parents=True, exist_ok=True)
    for diagram in website.DIAGRAMS:
        for language in languages:
            suffix = "" if language == "en" else f".{language}"
            for scheme in ("", ".dark"):
                (folder / f"{diagram}{suffix}{scheme}.svg").write_text(
                    f"<svg><title>{diagram}</title><desc>About it</desc></svg>",
                    encoding="utf-8",
                )


def repository(root: Path, *languages: str) -> Path:
    """A repository with a workflow, its settings as code, the pages in docs/ and the
    pictures of the diagrams in each of languages beside the hooks."""
    folder = root / ".github/workflows"
    folder.mkdir(parents=True)
    (folder / "ci.yml").write_text(CHECK, encoding="utf-8")
    (root / ".github/repository.toml").write_text(
        '[branch]\nrequired_checks = ["check"]\n', encoding="utf-8"
    )
    (root / "docs").mkdir()
    draw(root / ".github" / website.PICTURES, *languages)
    return folder


def run(root: Path, *argv: str) -> int:
    """blueprint.py website with argv, in the repository at root."""
    return main(["website", *argv], root=root)


def test_the_page_of_the_automation_is_written_without_a_generator(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = repository(tmp_path, "en", "de")
    shutil.copytree(tmp_path / "docs", tmp_path / "build")
    argv = ["automation", "build", "--site-name", "Demo", "--language", "en"]

    code = run(
        tmp_path,
        *argv,
        "--language",
        "de",
        "--repository",
        "https://github.com/owner/demo",
    )

    assert code == 0
    assert capsys.readouterr().out.splitlines() == [
        "build/automation.md",
        "build/automation.de.md",
    ]
    page = (tmp_path / "build/automation.md").read_text(encoding="utf-8")
    assert (
        "[`.github/workflows/ci.yml`](https://github.com/owner/demo/blob/HEAD/" in page
    )
    assert "- **Required checks:** <code>check</code>" in page
    served = sorted(
        path.name for path in (tmp_path / "build/assets/images/automation").iterdir()
    )
    assert served == sorted(
        path.name for path in (tmp_path / ".github" / website.PICTURES).iterdir()
    )
    # The same pages as the hooks of MkDocs write for this repository.
    config = SimpleNamespace(
        config_file_path=str(tmp_path / "mkdocs.yml"),
        docs_dir=str(tmp_path / "docs"),
        site_name="Demo",
        repo_url="https://github.com/owner/demo",
        edit_uri=None,
        theme={"language": "en"},
        plugins={
            "i18n": SimpleNamespace(
                config=SimpleNamespace(
                    languages=[
                        SimpleNamespace(locale="en", default=True, build=True),
                        SimpleNamespace(locale="de", default=False, build=True),
                    ]
                ),
                current_language="en",
            )
        },
    )
    built = hooks(tmp_path / ".github/mkdocs_blueprint.py").automation_pages(
        folder, config
    )
    assert built == {
        name: (tmp_path / "build" / name).read_text(encoding="utf-8")
        for name in ("automation.md", "automation.de.md")
    }


def test_a_page_of_the_project_in_a_further_language_takes_its_place(
    tmp_path: Path,
) -> None:
    repository(tmp_path, "en")
    (tmp_path / "docs/automation.de.md").write_text(
        "# Eigene Seite\n", encoding="utf-8"
    )
    argv = ("--site-name", "Demo", "--language", "en", "--language", "de")

    assert run(tmp_path, "automation", "build", *argv) == 0

    assert sorted(path.name for path in (tmp_path / "build").iterdir()) == [
        "assets",
        "automation.md",
    ]


def test_a_missing_picture_fails_the_step_after_the_page(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repository(tmp_path, "en")
    shutil.rmtree(tmp_path / ".github" / website.PICTURES)
    (tmp_path / ".github/repository.toml").unlink()

    assert run(tmp_path, "automation", "build", "--site-name", "Demo") == 1

    assert (tmp_path / "build/automation.md").is_file()
    assert (
        "lacks the pictures from-a-change-to-a-release.svg, "
        "from-a-change-to-a-release.dark.svg"
    ) in capsys.readouterr().err


@pytest.mark.parametrize("own", [True, False])
def test_no_page_of_the_automation_without_workflows_or_with_the_projects_own(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], own: bool
) -> None:
    folder = repository(tmp_path, "en")
    if own:
        (tmp_path / "docs/automation.md").write_text("# Ours\n", encoding="utf-8")
    else:
        (folder / "ci.yml").unlink()

    assert run(tmp_path, "automation", "build", "--site-name", "Demo") == 0

    assert not (tmp_path / "build").exists()
    assert "no page of the automation to write" in capsys.readouterr().out


def test_the_page_of_the_automation_never_goes_into_docs_itself(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repository(tmp_path, "en")

    assert run(tmp_path, "automation", "docs/", "--site-name", "Demo") == 2

    assert not (tmp_path / "docs/automation.md").exists()
    assert "into a copy of docs/" in capsys.readouterr().err


def site(root: Path, *, languages: bool) -> Path:
    """A built website at root/site in English, and with languages in German too: a
    home page, a guide, and a page that no search engine lists."""
    folder = root / "site"
    pages = {
        "index.html": "",
        "guide/index.html": "",
        "hidden.html": NOINDEX,
        **({"de/index.html": "", "de/hidden.html": NOINDEX} if languages else {}),
    }
    entries = []
    for path, head in pages.items():
        (folder / path).parent.mkdir(parents=True, exist_ok=True)
        # A page that names the tag in its text, not in its head, is listed.
        (folder / path).write_text(
            f"<html><head>{head}</head><body>{NOINDEX}</body></html>", encoding="utf-8"
        )
        address = ADDRESS + path.removesuffix("index.html")
        other = (
            f'<xhtml:link rel="alternate" hreflang="de" href="{ADDRESS}de/{path}"/>'
            if languages and not path.startswith("de/")
            else ""
        )
        entries.append(f"<url><loc>{address}</loc>{other}</url>")
    text = f'<urlset xmlns="x">{"".join(entries)}\n</urlset>\n'
    (folder / "sitemap.xml").write_text(text, encoding="utf-8")
    with gzip.GzipFile(folder / "sitemap.xml.gz", "wb", mtime=0) as packed:
        packed.write(text.encode("utf-8"))
    return folder


def menu(path: Path) -> Path:
    """A file of the menus of the website in English and German."""
    path.write_text(
        json.dumps(
            {
                "default": "en",
                "languages": {
                    "en": {
                        "name": "Demo",
                        "summary": "A [demo] project",
                        "items": [
                            {
                                "title": "Home",
                                "url": "index.html",
                                "address": ADDRESS,
                                "description": "Where it starts",
                            },
                            {
                                "title": "Hidden",
                                "url": "hidden.html",
                                "address": f"{ADDRESS}hidden.html",
                            },
                            {
                                "title": "Guides",
                                "children": [
                                    {
                                        "title": "Guide (one)",
                                        "url": "guide/",
                                        "address": f"{ADDRESS}guide/",
                                        "description": "How.",
                                    },
                                    {
                                        "title": "Decision",
                                        "url": "decisions/0001.html",
                                        "address": f"{ADDRESS}decisions/0001.html",
                                    },
                                ],
                            },
                        ],
                    },
                    "de": {
                        "name": "Demo",
                        "label": "Deutsch",
                        "items": [
                            {
                                "title": "Start",
                                "url": "de/index.html",
                                "address": f"{ADDRESS}de/",
                            }
                        ],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_the_website_is_finished_without_a_generator(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = site(tmp_path, languages=True)
    menu(tmp_path / "menu.json")

    code = run(
        tmp_path,
        "finish",
        "site",
        "--site-url",
        ADDRESS.rstrip("/"),
        "--menu",
        "menu.json",
    )

    assert code == 0
    assert capsys.readouterr().out.splitlines() == [
        "2 address(es) that no search engine lists left the sitemaps.",
        "the sitemap of a website in several languages is in every folder.",
        "llms.txt maps the menu of en, de.",
    ]
    sitemap = (folder / "sitemap.xml").read_text(encoding="utf-8")
    assert "hidden.html" not in sitemap
    assert f"<loc>{ADDRESS}guide/</loc>" in sitemap
    with gzip.GzipFile(folder / "sitemap.xml.gz") as packed:
        assert packed.read().decode("utf-8") == sitemap
    for copy in ("guide", "de"):
        assert (folder / copy / "sitemap.xml").read_text(encoding="utf-8") == sitemap
    assert (folder / "llms.txt").read_text(encoding="utf-8") == (
        "# Demo\n\n> A (demo) project\n\n"
        "The pages of this website, in the order of its menu, each with its page in "
        "Deutsch where there is one.\n\n"
        "## Pages\n\n"
        f"- [Home]({ADDRESS}): Where it starts. Deutsch: [Start]({ADDRESS}de/)\n\n"
        "## Guides\n\n"
        f"- [Guide (one)]({ADDRESS}guide/): How.\n"
    )


def test_a_website_in_one_language_keeps_its_sitemap_and_its_own_map(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = site(tmp_path, languages=False)
    (folder / "llms.txt").write_text("# Our own\n", encoding="utf-8")
    menu(tmp_path / "menu.json")

    code = run(tmp_path, "finish", "site", "--site-url", ADDRESS, "--menu", "menu.json")

    assert code == 0
    assert capsys.readouterr().out.splitlines() == [
        "1 address(es) that no search engine lists left the sitemaps.",
    ]
    assert not (folder / "guide/sitemap.xml").exists()
    assert (folder / "llms.txt").read_text(encoding="utf-8") == "# Our own\n"


def test_a_website_without_a_sitemap_is_finished_too(tmp_path: Path) -> None:
    (tmp_path / "site/guide").mkdir(parents=True)
    (tmp_path / "site/guide/index.html").write_text(
        f"<head>{NOINDEX}</head>", encoding="utf-8"
    )

    assert run(tmp_path, "finish", "site", "--site-url", ADDRESS) == 0

    assert website.noindexed(tmp_path / "site", ADDRESS) == {
        f"{ADDRESS}guide/index.html",
        f"{ADDRESS}guide/",
    }
    assert sorted(path.name for path in (tmp_path / "site").rglob("*")) == [
        "guide",
        "index.html",
    ]
    website.copy_sitemap(tmp_path / "site")
    assert not (tmp_path / "site/guide/sitemap.xml").exists()


def test_a_menu_that_is_no_menu_fails_the_step(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    site(tmp_path, languages=False)
    (tmp_path / "menu.json").write_text('{"languages": {}}', encoding="utf-8")

    code = run(tmp_path, "finish", "site", "--site-url", ADDRESS, "--menu", "menu.json")

    assert code == 2
    assert capsys.readouterr().err == (
        "blueprint.py: menu.json holds no menus of the website, as read_menus of "
        "blueprint/website.py reads them (KeyError: 'default').\n"
    )


def test_the_menus_of_a_website_read_from_json(tmp_path: Path) -> None:
    menus, default, further = website.read_menus(menu(tmp_path / "menu.json"))

    assert default == "en"
    assert further == {"de": "Deutsch"}
    assert menus["de"].summary is None
    assert menus["en"].items[2] == website.Section(
        "Guides",
        (
            website.Entry("Guide (one)", "guide/", f"{ADDRESS}guide/", "How."),
            website.Entry(
                "Decision", "decisions/0001.html", f"{ADDRESS}decisions/0001.html"
            ),
        ),
    )


def test_a_further_language_without_a_label_is_named_by_its_code(
    tmp_path: Path,
) -> None:
    path = tmp_path / "menu.json"
    path.write_text(
        json.dumps(
            {
                "default": "en",
                "languages": {
                    "en": {"name": "Demo", "items": []},
                    "fr": {"name": "Démo"},
                },
            }
        ),
        encoding="utf-8",
    )

    menus, _, further = website.read_menus(path)

    assert further == {"fr": "fr"}
    assert menus["fr"].items == ()


def test_the_hooks_need_the_steps_beside_them(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hooks without blueprint/website.py beside them fail at once, with what brings
    it, rather than a website that lacks its steps."""
    is_file = Path.is_file
    monkeypatch.setattr(
        Path, "is_file", lambda path: path.name != "website.py" and is_file(path)
    )
    spec = importlib.util.spec_from_file_location(
        "mkdocs_blueprint", ROOT / ".github/mkdocs_blueprint.py"
    )
    assert spec is not None
    assert spec.loader is not None

    with pytest.raises(ImportError, match=r"need blueprint/website\.py beside"):
        spec.loader.exec_module(importlib.util.module_from_spec(spec))


def test_the_template_brings_the_steps_beside_the_hooks() -> None:
    included = (ROOT / "template/.github/blueprint/website.py.jinja").read_text(
        encoding="utf-8"
    )

    assert included == '[% include "blueprint/website.py" -%]\n'


EVERY_KIND = {
    "ci.yml": """# SPDX-License-Identifier: MIT
name: CI

# The checks of every change, with `ruff` and https://docs.astral.sh/ruff/.
#
# A second paragraph.
# https://github.com/Dennis-Otto/repo-blueprint

on:
  push:
    branches: [main]
  pull_request:
  pull_request_target:
jobs:
  check:
    environment:
      name: tests
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ secrets.TOKEN }}
""",
    "release.yml": "name: Release\non: push\njobs:\n  release:\n    environment: pypi\n",
    "labels.yml": "on: [issues, pull_request]\njobs:\n  sort:\n    runs-on: x\n",
    "after.yml": (
        "name: After\non:\n  workflow_run:\n    workflows: [CI, Release]\n"
        "jobs:\n  go:\n    runs-on: x\n"
    ),
    "elsewhere.yml": (
        "on: push\njobs:\n  first:\n    if: github.repository != 'owner/demo'\n"
        "  second:\n    needs: first\n"
    ),
    "broken.yml": "on: [\n",
    "comment.yml": "# Only a comment.\n",
}


def test_the_page_of_the_automation_shows_every_kind_of_workflow(
    tmp_path: Path,
) -> None:
    folder = tmp_path / ".github/workflows"
    folder.mkdir(parents=True)
    for name, text in EVERY_KIND.items():
        (folder / name).write_text(text, encoding="utf-8")
    (tmp_path / ".github/repository.toml").write_text(
        '[branch]\nrequired_checks = ["check", "elsewhere"]\n', encoding="utf-8"
    )
    draw(tmp_path / "docs/images/diagrams", "en")

    made = website.automation(
        folder,
        tmp_path / "docs",
        tmp_path / ".github" / website.PICTURES,
        site_name="Demo",
        repository="https://github.com/owner/demo",
        default="en",
    )

    page = made.pages[website.AUTOMATION]
    assert made.pictures == []
    assert made.missing == []
    assert made.sources == [folder, tmp_path / ".github/repository.toml"]
    assert '<img src="images/diagrams/how-a-repository-looks-after-itself.svg"' in page
    assert "its 6 workflows of GitHub Actions" in page
    assert "[Elsewhere]" not in page
    assert (
        "<p>The checks of every change, with <code>ruff</code> and "
        '<a href="https://docs.astral.sh/ruff/">https://docs.astral.sh/ruff/</a>.</p>'
    ) in page
    assert "<p>A second paragraph.</p>" in page
    # A pull request and one of a fork read alike, and the page says it once.
    assert "- **When:** every push to <code>main</code>, every pull request\n" in page
    assert "after 2 workflows" in page
    assert "after a run of [CI](#ci) or [Release](#release)" in page
    assert "- **Environments:** <code>tests</code>" in page
    assert "- **Environments:** <code>pypi</code>" in page
    assert "- **Secrets:** <code>TOKEN</code>" in page
    assert (
        "from the [Repo Blueprint](https://github.com/Dennis-Otto/repo-blueprint)"
        in page
    )
    assert "- <code>elsewhere</code>\n" in page
    assert "| [broken](#broken) |" in page
    assert "| [comment](#comment) |" in page
    assert "<p>Only a comment.</p>" in page


def test_the_map_of_the_website_lists_the_pages_of_every_section() -> None:
    page = website.Entry("Deep", "a/b/deep.html", f"{ADDRESS}a/b/deep.html")
    menus = {
        "en": website.Menu(
            "Demo",
            None,
            (
                website.Section("Empty"),
                website.Section("Guides", (website.Section("Inner", (page,)),)),
            ),
        )
    }

    assert website.map_of_website(menus, "en", {}, set()) == (
        "# Demo\n\nThe pages of this website, in the order of its menu.\n\n"
        f"## Guides\n\n- [Deep]({ADDRESS}a/b/deep.html)\n"
    )
