"""The pictures of GitHub's pages for the README: .github/docs-pictures/github_pages.py,
with a Playwright of its own that records what the script asks of the browser."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]


class Element:
    """A part of a page, where it is, and the parts inside it."""

    def __init__(
        self, box: dict[str, float] | None, inside: dict[str, Element] | None = None
    ) -> None:
        self.box = box
        self.inside = inside or {}
        self.first = self
        self.calls: list[str] = []

    def bounding_box(self) -> dict[str, float] | None:
        return self.box

    def locator(self, selector: str) -> Element:
        return self.inside[selector]

    def scroll_into_view_if_needed(self) -> None:
        self.calls.append("scroll")

    def get_by_text(self, text: str) -> Element:
        self.calls.append(f"text {text}")
        return self

    def wait_for(self) -> None:
        self.calls.append("wait")


class Tab:
    """A page of the browser that shows the same element at every address."""

    def __init__(self, part: Element, scrolled: float = 0) -> None:
        self.part = part
        self.scrolled = scrolled
        self.url = "https://github.com/example"
        self.clock = SimpleNamespace(set_fixed_time=self.calls_back("clock"))
        self.calls: list[Any] = []

    def calls_back(self, name: str) -> Any:
        return lambda *args, **kwargs: self.calls.append((name, args, kwargs))

    def evaluate(self, expression: str) -> float | None:
        return self.scrolled if expression == "window.scrollY" else None

    def goto(self, url: str, **kwargs: Any) -> None:
        self.url = url

    def locator(self, selector: str) -> Element:
        return self.part

    def wait_for_load_state(self, state: str) -> None:
        self.calls.append(("load", state))

    def screenshot(self, path: Path, **kwargs: Any) -> None:
        path.write_bytes(b"png")
        self.calls.append(("screenshot", path.name, kwargs["clip"]))


class Browser:
    """A browser whose every context has one tab."""

    def __init__(self, tab: Tab) -> None:
        self.tab = tab
        self.contexts: list[dict[str, Any]] = []
        self.closed = False

    def new_context(self, **options: Any) -> SimpleNamespace:
        self.contexts.append(options)
        return SimpleNamespace(new_page=lambda: self.tab, close=lambda: None)

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def pages(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """The script, with a Playwright that only this test has."""
    sync_api = ModuleType("playwright.sync_api")
    for name in ("Browser", "Locator", "Page", "sync_playwright"):
        setattr(sync_api, name, object)
    package = ModuleType("playwright")
    package.sync_api = sync_api  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "playwright", package)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api)
    spec = importlib.util.spec_from_file_location(
        "github_pages", ROOT / ".github/docs-pictures/github_pages.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Its dataclass looks itself up by the name of its module.
    monkeypatch.setitem(sys.modules, "github_pages", module)
    spec.loader.exec_module(module)
    return module


def test_a_part_is_found_on_the_page_not_in_the_window(pages: ModuleType) -> None:
    tab = Tab(Element(None), scrolled=300)
    found = pages.box_of(tab, Element({"x": 5, "y": 40, "width": 10, "height": 20}))
    assert found == {"x": 5, "y": 340, "width": 10, "height": 20}
    with pytest.raises(RuntimeError, match=r"^https://github.com/example shows no "):
        pages.box_of(tab, Element(None))


def test_a_picture_shows_the_part_with_a_margin(pages: ModuleType) -> None:
    # The whole part, with the margin around it; never left of the page or wider
    # than the window.
    whole = pages.Shot("whole", "https://example", "main", "Text")
    part = Element({"x": 100, "y": 200, "width": 600, "height": 300})
    assert pages.region(Tab(part), whole, part) == {
        "x": 84,
        "y": 184,
        "width": 632,
        "height": 332,
    }
    wide = Element({"x": 4, "y": 8, "width": 1280, "height": 50})
    assert pages.region(Tab(wide), whole, wide) == {
        "x": 0,
        "y": 0,
        "width": 1280,
        "height": 82,
    }
    # From its heading down, as far as the height of the shot.
    heading = Element({"x": 100, "y": 250, "width": 600, "height": 30})
    part = Element({"x": 100, "y": 200, "width": 600, "height": 300}, {"h1": heading})
    start = pages.Shot("start", "https://example", "main", "Text", "h1", 100)
    assert pages.region(Tab(part), start, part)["y"] == 234
    assert pages.region(Tab(part), start, part)["height"] == 132
    # A height beyond the part shows only the rest of it.
    rest = pages.Shot("rest", "https://example", "main", "Text", "h1", 1000)
    assert pages.region(Tab(part), rest, part)["height"] == 282


def test_every_shot_is_taken_in_both_themes_at_the_still_clock(
    pages: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    part = Element(
        {"x": 100, "y": 200, "width": 600, "height": 300},
        {"h1": Element({"x": 100, "y": 250, "width": 600, "height": 30})},
    )
    tab = Tab(part)
    browser = Browser(tab)
    launched: list[dict[str, Any]] = []

    def launch(**options: Any) -> Browser:
        launched.append(options)
        return browser

    class Playwright:
        chromium = SimpleNamespace(launch=launch)

        def __enter__(self) -> Playwright:
            return self

        def __exit__(self, *_: object) -> None:
            return None

    monkeypatch.setattr(pages, "sync_playwright", Playwright)
    monkeypatch.setattr(pages, "BROWSERS", tmp_path / "none")
    folder = tmp_path / "pictures"
    monkeypatch.setattr(sys, "argv", ["github_pages.py", str(folder)])
    pages.main()
    names = [shot.name for shot in pages.SHOTS]
    assert sorted(path.name for path in folder.iterdir()) == sorted(
        f"{name}{suffix}.png" for name in names for suffix in ("", ".dark")
    )
    assert [options["color_scheme"] for options in browser.contexts] == [
        "light",
        "dark",
    ] * len(names)
    assert {options["timezone_id"] for options in browser.contexts} == {"UTC"}
    assert ("clock", (pages.CLOCK,), {}) in tab.calls
    assert part.calls[:3] == ["scroll", f"text {pages.SHOTS[0].shows}", "wait"]
    assert browser.closed
    # Without the browsers of the image, Playwright finds its own.
    assert launched[0]["executable_path"] is None
    assert "--disable-lcd-text" in launched[0]["args"]
    # With them, it starts the Chromium of the newest.
    for version in ("1100", "1200"):
        chrome = tmp_path / f"browsers/chromium-{version}/chrome-linux/chrome"
        chrome.parent.mkdir(parents=True)
        chrome.write_bytes(b"")
    monkeypatch.setattr(pages, "BROWSERS", tmp_path / "browsers")
    pages.main()
    assert launched[1]["executable_path"] == str(chrome)
