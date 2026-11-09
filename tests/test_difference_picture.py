"""The picture of a difference for the documentation of the screenshot bot:
.github/docs-pictures/difference_picture.py, which turns the dashboard into the
dashboard an hour later and draws the difference of their pictures as keep does."""

from __future__ import annotations

import importlib.util
import io
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from PIL import Image

import dashboard
from blueprint.screenshots import RED, difference

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 9, 7, 0, tzinfo=UTC)


@pytest.fixture
def picture() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "difference_picture", ROOT / ".github/docs-pictures/difference_picture.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def page_of(*rows: dashboard.Row, now: datetime = NOW) -> str:
    return dashboard.render(list(rows), "Dennis-Otto", "v1.15.0", now)


def png(size: tuple[int, int], dots: list[tuple[int, int]]) -> bytes:
    image = Image.new("RGB", size, "white")
    for dot in dots:
        image.putpixel(dot, (0, 0, 0))
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def test_the_dashboard_an_hour_later_shows_its_first_passed_workflow_failed(
    picture: ModuleType,
) -> None:
    # The page as dashboard.py renders it: the time, and a cell of each workflow
    # with its symbol, whose first that passed fails an hour later.
    runs = {
        "CI": dashboard.Run("failure", "https://ci"),
        "CodeQL": dashboard.Run("success", "https://codeql"),
        "Release": dashboard.Run("success", "https://release"),
    }
    page = page_of(
        dashboard.Row("Dennis-Otto/first", runs=runs),
        dashboard.Row("Dennis-Otto/second", runs=runs),
    )
    link = '<a href="https://codeql">'
    passed = f'<td class="state ok" title="CodeQL: passed">{link}✔</a></td>'
    failed = f'<td class="state bad" title="CodeQL: failed">{link}✘</a></td>'
    assert page.count(passed) == 2
    assert "as of 2026-11-09 07:00 UTC" in page

    later = picture.changed(page)

    assert "as of 2026-11-09 08:00 UTC" in later
    assert "07:00" not in later
    assert later.count(passed) == 1
    assert later.count(failed) == 1
    assert later.index(failed) < later.index(passed)
    # Nothing else changes: the release passed and the CI failed as before.
    assert later.replace(failed, passed).replace("08:00", "07:00") == page


def test_an_hour_later_can_be_the_next_day(picture: ModuleType) -> None:
    runs = {"CI": dashboard.Run("success", "https://ci")}
    page = page_of(
        dashboard.Row("Dennis-Otto/demo", runs=runs),
        now=datetime(2026, 12, 31, 23, 30, tzinfo=UTC),
    )

    later = picture.changed(page)

    assert "as of 2027-01-01 00:30 UTC" in later
    assert (
        '<td class="state bad" title="CI: failed"><a href="https://ci">✘</a>' in later
    )


def test_a_passed_workflow_without_a_link_fails_without_one(
    picture: ModuleType,
) -> None:
    page = 'as of 2026-11-09 07:00 UTC <td class="state ok" title="CI: passed">✔</td>'

    assert picture.changed(page) == (
        'as of 2026-11-09 08:00 UTC <td class="state bad" title="CI: failed">✘</td>'
    )


@pytest.mark.parametrize(
    "page",
    [
        # No workflow passed.
        page_of(
            dashboard.Row(
                "Dennis-Otto/demo", runs={"CI": dashboard.Run("failure", "https://ci")}
            )
        ),
        # No time of the dashboard.
        '<td class="state ok" title="CI: passed"><a href="https://ci">✔</a></td>',
    ],
)
def test_a_page_without_a_time_or_a_passed_workflow_is_no_dashboard_to_change(
    picture: ModuleType, page: str
) -> None:
    with pytest.raises(ValueError, match="no time of the dashboard or no workflow"):
        picture.changed(page)


def test_the_picture_is_the_difference_that_keep_draws(picture: ModuleType) -> None:
    before = png((40, 30), [(3, 4)])
    after = png((40, 30), [(3, 4), (30, 20)])

    drawn = picture.drawn(before, after)

    assert drawn == difference(before, after)
    with Image.open(io.BytesIO(drawn)) as image:
        assert image.size == (40, 30)


@pytest.mark.parametrize(
    "after",
    [png((40, 30), [(3, 4)]), png((41, 30), [(3, 4)])],
    ids=["no pixel changed", "another size"],
)
def test_pictures_without_a_difference_to_draw_fail(
    picture: ModuleType, after: bytes
) -> None:
    with pytest.raises(ValueError, match="no pixel changed"):
        picture.drawn(png((40, 30), [(3, 4)]), after)


def test_the_script_changes_the_page_and_draws_the_pictures(
    picture: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runs = {"CI": dashboard.Run("success", "https://ci")}
    page = page_of(dashboard.Row("Dennis-Otto/demo", runs=runs))
    out = io.BytesIO()
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(page.encode())))
    monkeypatch.setattr(sys, "stdout", SimpleNamespace(buffer=out))

    picture.main(["change"])

    assert out.getvalue().decode() == picture.changed(page)

    before, after = tmp_path / "dashboard.png", tmp_path / "changed.png"
    before.write_bytes(png((40, 30), []))
    after.write_bytes(png((40, 30), [(10, 10)]))
    out.seek(0)
    out.truncate()

    picture.main(["draw", str(before), str(after)])

    assert out.getvalue() == difference(before.read_bytes(), after.read_bytes())


@pytest.mark.parametrize(
    ("arguments", "said"),
    [
        ([], "python3 difference_picture.py change"),
        (["draw", "one.png"], "python3 difference_picture.py change"),
        (["change"], "no time of the dashboard"),
    ],
)
def test_the_script_says_what_is_wrong_without_a_traceback(
    picture: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    arguments: list[str],
    said: str,
) -> None:
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(b"<html>")))

    with pytest.raises(SystemExit) as stopped:
        picture.main(arguments)

    assert said in str(stopped.value.code)


def test_the_pages_of_the_screenshot_bot_show_the_picture_that_renews_itself() -> None:
    # scripts/docs-pictures.sh draws the picture with the code and the Pillow of keep,
    # and a release that changes either renders it anew.
    script = (ROOT / "scripts/docs-pictures.sh").read_text(encoding="utf-8")
    for part in (
        "-r /work/stacks/screenshots/requirements.txt",
        "--env PYTHONPATH=/work",
        "python3 /work/.github/docs-pictures/difference_picture.py change",
        "python3 /work/.github/docs-pictures/difference_picture.py draw",
        'cp "$difference" docs/images/screenshots-difference.png\n',
    ):
        assert part in script, part
    listed = (ROOT / ".github/docs-pictures/paths.txt").read_text(encoding="utf-8")
    for pattern in ("blueprint/screenshots.py", "stacks/screenshots/requirements.txt"):
        assert f"\n{pattern}\n" in listed, pattern
    drawn = (ROOT / "docs/images/screenshots-difference.png").read_bytes()
    with Image.open(io.BytesIO(drawn)) as image:
        assert image.format == "PNG"
        # The palette of keep: the red of the changes first, then the grays.
        assert image.mode == "P"
        palette = image.getpalette()
        assert palette is not None
        assert palette[:3] == list(RED)
    # The pages about the screenshot bot show it, in English and in German, with
    # what it shows in words.
    for name, words in (
        ("website.md", "The picture of the difference that keep draws"),
        ("website.de.md", "Das Bild des Unterschieds, das keep"),
    ):
        text = (ROOT / "docs/features" / name).read_text(encoding="utf-8")
        assert f"![{words}" in text, name
        assert "](../images/screenshots-difference.png)\n" in text, name
