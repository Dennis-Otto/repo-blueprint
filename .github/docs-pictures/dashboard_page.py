"""The page of the dashboard that the documentation shows, from fixed data.

scripts/docs-pictures.sh runs it in the image of .github/social-preview/Dockerfile,
with the root of the blueprint on PYTHONPATH, before the browser photographs the page
as docs/images/dashboard.png:

    python3 dashboard_page.py .github/docs-pictures/dashboard.json > dashboard.html

dashboard.json holds what the published dashboard showed on one day, as its repos.json
holds it, and under "a_week_ago" the health of each repository a week before, from its
history.json, for the arrows of the table Health. dashboard.py renders the page from
it, at the time of "generated", so the picture changes only when the code of the page
changes its layout or its columns, not with each state, date or version of the live
dashboard (#827). A change of what the data holds, such as a new field of a
repository, fails a test until dashboard.json has it too.

The page lifts the cap of the width of the page, below that of the main table, so that
every column is in the picture.
https://github.com/Dennis-Otto/repo-blueprint
"""

from __future__ import annotations

import json
import sys
from dataclasses import fields
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dashboard import SCHEMA, Health, Row, Run, Update, render, when

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

# The style that lifts the cap of the width of the page, in the head of the page.
UNCAPPED = "<style>main { max-width: none; }</style>"


def restored[T: DataclassInstance](kind: type[T], item: dict[str, Any]) -> T:
    """The dataclass kind of an item of repos.json, which holds null for every empty
    text: the fields of kind, with each such null a text again."""
    missing = [each.name for each in fields(kind) if each.name not in item]
    if missing:
        raise ValueError(
            f"The data holds no {', '.join(missing)} of {kind.__name__}, which the "
            "dashboard shows: save the repos.json of the published dashboard anew."
        )
    return kind(
        **{
            each.name: ""
            if item[each.name] is None and each.type == "str"
            else item[each.name]
            for each in fields(kind)
        }
    )


def row(item: dict[str, Any]) -> Row:
    """The row of one repository, as repos.json holds it."""
    update = item["update"]
    return restored(
        Row,
        {
            **item,
            "update": None if update is None else restored(Update, update),
            "runs": {name: restored(Run, run) for name, run in item["runs"].items()},
            "health": restored(Health, item["health"]),
        },
    )


def page(document: dict[str, Any]) -> str:
    """The page of the dashboard of document, with every column in sight."""
    if document.get("schema") != SCHEMA:
        raise ValueError(
            f"The data holds schema {document.get('schema')!r}, the dashboard writes "
            f"{SCHEMA}: save the repos.json of the published dashboard anew."
        )
    shown = render(
        [row(item) for item in document["repos"]],
        document["owner"],
        document["blueprint"] or "",
        when(document["generated"]),
        document.get("a_week_ago") or {},
    )
    return shown.replace("</head>", f"{UNCAPPED}</head>", 1)


def main(arguments: list[str]) -> None:
    match arguments:
        case [path]:
            document = json.loads(Path(path).read_text(encoding="utf-8"))
            try:
                shown = page(document)
            except ValueError as error:
                raise SystemExit(str(error)) from None
            sys.stdout.buffer.write(shown.encode())
        case _:
            raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
