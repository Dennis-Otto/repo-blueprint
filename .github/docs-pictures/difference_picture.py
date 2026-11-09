"""The picture of a difference for the documentation of the screenshot bot: what
`blueprint.py screenshots keep` draws when the pixels of a picture change.

scripts/docs-pictures.sh runs it in the image of .github/social-preview/Dockerfile,
with Pillow from stacks/screenshots/requirements.txt and the root of the blueprint on
PYTHONPATH, in two steps around the browser that photographs the dashboard:

    python3 difference_picture.py change < dashboard.html > changed.html
    python3 difference_picture.py draw dashboard.png changed.png > difference.png

change turns the page of the dashboard into the page as it could be an hour later:
its time an hour on, and the first workflow that passed now failed. draw draws the
difference of the pictures of both pages with the code of keep, so that the picture
changes when that code does.
https://github.com/Dennis-Otto/repo-blueprint
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

from blueprint.screenshots import difference
from dashboard import SYMBOLS

# The time of the dashboard, as dashboard.py writes it.
MOMENT = re.compile(r"as of (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) UTC")
FORMAT = "%Y-%m-%d %H:%M"
LATER = timedelta(hours=1)
# The state of a workflow that passed, as dashboard.py writes it: a cell with its
# symbol, which links to the run.
PASSED, FAILED = SYMBOLS["success"], SYMBOLS["failure"]
STATE = re.compile(
    rf'<td class="state {re.escape(PASSED[1])}" title="(?P<name>[^"<]+): '
    rf'{re.escape(PASSED[2])}">(?P<link><a href="[^"<]*">)?{re.escape(PASSED[0])}'
    r"(?P<end></a>)?</td>"
)


def changed(page: str) -> str:
    """The page of the dashboard an hour later, after the first workflow that passed
    failed."""
    if not MOMENT.search(page) or not STATE.search(page):
        raise ValueError(
            "The page shows no time of the dashboard or no workflow that passed."
        )

    def later(moment: re.Match[str]) -> str:
        shown = datetime.strptime(moment[1], FORMAT) + LATER
        return f"as of {shown.strftime(FORMAT)} UTC"

    def failed(state: re.Match[str]) -> str:
        symbol, css, words = FAILED
        link, end = state["link"] or "", state["end"] or ""
        return (
            f'<td class="state {css}" title="{state["name"]}: {words}">'
            f"{link}{symbol}{end}</td>"
        )

    return STATE.sub(failed, MOMENT.sub(later, page, count=1), count=1)


def drawn(before: bytes, after: bytes) -> bytes:
    """The picture of the difference of two pictures, as keep draws it."""
    picture = difference(before, after)
    if picture is None:
        raise ValueError(
            "The pictures differ in their size or frames, or no pixel changed."
        )
    return picture


def main(arguments: list[str]) -> None:
    try:
        match arguments:
            case ["change"]:
                page = changed(sys.stdin.buffer.read().decode())
                sys.stdout.buffer.write(page.encode())
            case ["draw", before, after]:
                picture = drawn(Path(before).read_bytes(), Path(after).read_bytes())
                sys.stdout.buffer.write(picture)
            case _:
                raise ValueError(__doc__)
    except ValueError as error:
        raise SystemExit(str(error)) from None


if __name__ == "__main__":
    main(sys.argv[1:])
