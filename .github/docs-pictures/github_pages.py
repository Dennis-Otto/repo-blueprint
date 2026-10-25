"""Photographs public pages of GitHub for the documentation of the blueprint, each in
the light and the dark theme, as a reader without an account sees them.

scripts/docs-pictures.sh runs it in the image of .github/social-preview/Dockerfile,
whose Python has Playwright from stacks/screenshots/requirements-browser.txt, and
takes the pictures from the folder that it names. Each page is one that no longer
changes, such as a merged pull request or a published release, and the clock of the
browser stands still at CLOCK, long after them, so that GitHub writes their dates in
full instead of "3 hours ago". A picture changes only when GitHub changes its pages.
https://github.com/Dennis-Otto/repo-blueprint
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import Browser, Locator, Page, sync_playwright

CLOCK = datetime(2027, 1, 1, 12, 0, tzinfo=UTC)
SIZE = {"width": 1280, "height": 900}
# The space around the part of the page that a picture shows.
MARGIN = 16
# Where the image keeps the browsers of its Playwright.
BROWSERS = Path("/ms-playwright")


@dataclass(frozen=True)
class Shot:
    """A picture of a part of a page: name.png and name.dark.png."""

    name: str
    url: str
    # The part of the page, and the text that it shows once it has loaded.
    part: str
    shows: str
    # Where the picture starts within the part, if not at its top, and how many
    # pixels of it it shows from there, if not all.
    start: str = ""
    height: int = 0


SHOTS = (
    # An update of the blueprint, as the Rollout brought it to a repository, with
    # the checks that passed before it merged itself.
    Shot(
        "github-update-pull-request",
        "https://github.com/Dennis-Otto/paperless-sync/pull/248/checks",
        "main",
        "Area labels",
        start="h1",
        height=560,
    ),
    # A release with its package, its signature, its SBOMs and its provenance.
    Shot(
        "github-release",
        "https://github.com/Dennis-Otto/paperless-sync/releases/tag/v1.2.0",
        "details:has(summary:has-text('Assets'))",
        "provenance.intoto.jsonl",
    ),
    # The comment of the PR coach, with the coverage of the tests.
    Shot(
        "github-pr-coach",
        "https://github.com/Dennis-Otto/issue-assistant/pull/177",
        "#issuecomment-6371170200",
        "This pull request",
    ),
)


def box_of(page: Page, element: Locator) -> dict[str, float]:
    """Where element is on the page, not in the window."""
    box = element.bounding_box()
    if box is None:
        message = f"{page.url} shows no {element}."
        raise RuntimeError(message)
    return {**box, "y": box["y"] + page.evaluate("window.scrollY")}


def region(page: Page, shot: Shot, part: Locator) -> dict[str, float]:
    """The box of the part with a margin around it, from where the picture starts
    down to its height."""
    box = box_of(page, part)
    top = box_of(page, part.locator(shot.start).first)["y"] if shot.start else box["y"]
    rest = box["y"] + box["height"] - top
    tall = min(rest, shot.height) if shot.height else rest
    return {
        "x": max(box["x"] - MARGIN, 0),
        "y": max(top - MARGIN, 0),
        "width": min(box["width"] + 2 * MARGIN, SIZE["width"]),
        "height": tall + 2 * MARGIN,
    }


def photograph(browser: Browser, shot: Shot, folder: Path) -> None:
    """Takes shot in both themes."""
    for scheme, suffix in (("light", ""), ("dark", ".dark")):
        context = browser.new_context(
            viewport=SIZE,
            device_scale_factor=1,
            color_scheme=scheme,
            locale="en-US",
            timezone_id="UTC",
            reduced_motion="reduce",
        )
        page = context.new_page()
        page.clock.set_fixed_time(CLOCK)
        page.goto(shot.url, wait_until="domcontentloaded")
        part = page.locator(shot.part).first
        # GitHub loads some parts, such as the assets of a release, once they come
        # into view.
        part.scroll_into_view_if_needed()
        part.get_by_text(shot.shows).first.wait_for()
        page.wait_for_load_state("networkidle")
        page.evaluate("document.fonts.ready")
        page.screenshot(
            path=folder / f"{shot.name}{suffix}.png",
            clip=region(page, shot, part),
            full_page=True,
            animations="disabled",
            caret="hide",
        )
        context.close()
        print(f"Took {shot.name}{suffix}.png of {shot.url}.", file=sys.stderr)


def main() -> None:
    folder = Path(sys.argv[1])
    folder.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        # The Chromium of the image, with letters whose edges are gray: the colored
        # ones of LCD text come out differently from run to run.
        found = sorted(BROWSERS.glob("chromium-*/chrome-linux*/chrome"))
        browser = playwright.chromium.launch(
            executable_path=str(found[-1]) if found else None,
            args=["--disable-lcd-text", "--force-color-profile=srgb"],
        )
        for shot in SHOTS:
            photograph(browser, shot, folder)
        browser.close()


if __name__ == "__main__":
    main()
