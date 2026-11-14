"""The page of the dashboard that the documentation shows: .github/docs-pictures/
dashboard_page.py renders it from the fixed data of .github/docs-pictures/
dashboard.json, so that docs/images/dashboard.png changes only with the layout and the
columns of the page, not with each state, date and version of the live dashboard
(#827)."""

from __future__ import annotations

import importlib.util
import io
import json
import re
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

import dashboard

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / ".github/docs-pictures/dashboard.json"
SCRIPT = ROOT / "scripts/docs-pictures.sh"


def module(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        name, ROOT / f".github/docs-pictures/{name}.py"
    )
    assert spec is not None
    assert spec.loader is not None
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


@pytest.fixture
def shown() -> ModuleType:
    return module("dashboard_page")


def document() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(DATA.read_text(encoding="utf-8"))
    return loaded


def test_the_data_of_the_picture_holds_what_the_dashboard_publishes(
    shown: ModuleType,
) -> None:
    # The rows of dashboard.json give its repos.json back, field for field: a new field
    # of a repository, or one that it drops, fails here until the data has it too.
    data = document()
    week = data.pop("a_week_ago")
    rows = [shown.row(item) for item in data["repos"]]
    assert (
        dashboard.data(
            rows, data["owner"], data["blueprint"], dashboard.when(data["generated"])
        )
        == data
    )
    # The arrows of the table Health compare with the same repositories.
    assert set(week) <= {row.repo for row in rows}
    assert all(
        set(health) == set(dashboard.Health.__dataclass_fields__)
        for health in week.values()
    )


def test_the_page_is_the_dashboard_of_one_day_with_every_column(
    shown: ModuleType,
) -> None:
    data = document()
    page = shown.page(data)
    moment = dashboard.when(data["generated"]).strftime("%Y-%m-%d %H:%M UTC")
    assert f"as of {moment}." in page
    assert f"The blueprint's latest release is {data['blueprint']}." in page
    for item in data["repos"]:
        assert f">{item['name']}</a>" in page
    # The arrows of a week ago, with what the value was then.
    assert 'title="a week ago ' in page
    # The cap of the width is lifted once, in the head, after the style of the page.
    head = page.split("</head>", 1)[0]
    assert head.endswith(shown.UNCAPPED)
    assert page.count(shown.UNCAPPED) == 1
    # The same data gives the same page: nothing of it comes from the clock.
    assert shown.page(document()) == page


def test_the_difference_picture_finds_a_workflow_that_passed(
    shown: ModuleType,
) -> None:
    # scripts/docs-pictures.sh draws screenshots-difference.png of the same page.
    page = shown.page(document())
    changed = module("difference_picture").changed(page)
    assert changed != page
    assert "✘" in changed


def test_a_null_text_of_the_data_is_an_empty_text_again(shown: ModuleType) -> None:
    run = shown.restored(dashboard.Run, {"state": "none", "url": None, "started": None})
    assert run == dashboard.Run("none")
    update = {"target": None, "number": 7, "url": "https://u", "state": "pending"}
    item = {
        **document()["repos"][0],
        "kind": None,
        "update": update,
        "scorecard": None,
    }
    row = shown.row(item)
    assert row.kind == ""
    assert row.update == dashboard.Update("", 7, "https://u", "pending")
    assert row.scorecard is None


def test_data_without_a_field_of_the_dashboard_says_what_it_lacks(
    shown: ModuleType,
) -> None:
    item = dict(document()["repos"][0])
    del item["conflicts"]
    with pytest.raises(ValueError, match="holds no conflicts of Row") as raised:
        shown.row(item)
    assert "save the repos.json of the published dashboard anew" in str(raised.value)


def test_data_of_another_schema_is_refused(shown: ModuleType) -> None:
    data = {**document(), "schema": dashboard.SCHEMA + 1}
    with pytest.raises(ValueError, match="holds schema 2, the dashboard writes 1"):
        shown.page(data)


def test_main_writes_the_page(
    shown: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", SimpleNamespace(buffer=out))
    shown.main([str(DATA)])
    assert out.getvalue().decode() == shown.page(document())


@pytest.mark.parametrize(
    ("arguments", "said"),
    [
        ([], "dashboard_page.py .github/docs-pictures/dashboard.json"),
        (["bad"], "holds schema"),
    ],
)
def test_main_stops_with_what_went_wrong(
    shown: ModuleType, tmp_path: Path, arguments: list[str], said: str
) -> None:
    if arguments:
        bad = tmp_path / "dashboard.json"
        bad.write_text(json.dumps({**document(), "schema": 0}), encoding="utf-8")
        arguments = [str(bad)]
    with pytest.raises(SystemExit) as stopped:
        shown.main(arguments)
    assert said in str(stopped.value.code)


def test_the_picture_of_the_dashboard_comes_from_the_fixed_data() -> None:
    # The live dashboard shows another time, other states and other versions with each
    # run, so its picture changed with every run of the Docs pictures workflow (#827).
    script = SCRIPT.read_text(encoding="utf-8")
    assert "github.io/repo-blueprint/dashboard" not in script
    assert 'dashboard=".github/docs-pictures/dashboard.json"\n' in script
    rendering = re.search(
        r"--env PYTHONPATH=/work \\\n.*\"\$browser\" \\\n\s+python3 "
        r"/work/\.github/docs-pictures/dashboard_page\.py \"/work/\$dashboard\" "
        r">\"\$shown\"",
        script,
    )
    assert rendering, "docs-pictures.sh renders the page of the fixed data"
    # The browser photographs that page, and the difference is drawn of it too.
    photograph = script.index("--screenshot=/tmp/dashboard.png")
    assert rendering.start() < photograph
    assert script.count('<"$shown"') == 2
    # The Docs pictures workflow is due after a change of the data or of its page.
    listed = (ROOT / ".github/docs-pictures/paths.txt").read_text(encoding="utf-8")
    assert "\n.github/docs-pictures/**\n" in listed
    assert "\ndashboard.py\n" in listed
