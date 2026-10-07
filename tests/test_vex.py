"""Tests of the OpenVEX document of a release, from the advisories that osv-scanner.toml accepts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import blueprint

ACCEPTED = """\
# Advisories that OSV-Scanner should not report.

[[IgnoredVulns]]
id = "GHSA-g6cj-pr64-35w5"
reason = "cryptography 48.0.1: test-only dependency; not shipped."

[[IgnoredVulns]]
id = "GHSA-2gx3-rcp4-g85q"
"""


def document() -> Any:
    text = blueprint.openvex(
        "Dennis-Otto/demo", "v1.3.0", "2026-10-08T03:00:00Z", ACCEPTED
    )
    assert text is not None
    assert text.endswith("\n")
    return json.loads(text)


def test_every_accepted_advisory_does_not_affect_the_release() -> None:
    vex = document()

    assert vex["@context"] == blueprint.OPENVEX
    assert vex["timestamp"] == "2026-10-08T03:00:00Z"
    assert vex["@id"] == (
        "https://github.com/Dennis-Otto/demo/releases/download/v1.3.0/demo.openvex.json"
    )
    statements = vex["statements"]
    assert [s["vulnerability"]["name"] for s in statements] == [
        "GHSA-g6cj-pr64-35w5",
        "GHSA-2gx3-rcp4-g85q",
    ]
    for statement in statements:
        assert statement["status"] == "not_affected"
        assert statement["products"] == [{"@id": "pkg:github/Dennis-Otto/demo@v1.3.0"}]


def test_the_reason_becomes_the_statement_of_its_impact() -> None:
    first, second = document()["statements"]

    assert (
        first["impact_statement"]
        == "cryptography 48.0.1: test-only dependency; not shipped."
    )
    # An entry without a reason still says why it is there.
    assert "osv-scanner.toml" in second["impact_statement"]


@pytest.mark.parametrize("accepted", ["", "# Nothing accepted.\n"])
def test_without_accepted_advisories_there_is_no_document(accepted: str) -> None:
    assert blueprint.openvex("o/r", "v1.0.0", "2026-10-08T03:00:00Z", accepted) is None


def test_the_command_line_writes_the_document(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    accepted = tmp_path / "osv-scanner.toml"
    accepted.write_text(ACCEPTED, encoding="utf-8")
    arguments = ["vex", "Dennis-Otto/demo", "v1.3.0", "2026-10-08T03:00:00Z"]

    assert blueprint.main([*arguments, "--file", str(accepted)]) == 0
    assert json.loads(capsys.readouterr().out) == document()

    # Without the file, nothing is written.
    assert blueprint.main([*arguments, "--file", str(tmp_path / "missing.toml")]) == 0
    assert capsys.readouterr().out == ""
