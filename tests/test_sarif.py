"""The findings of an analysis where code scanning can't keep them (decision 0081)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from blueprint import cli
from blueprint.sarif import Finding, findings, summary

# What CodeQL writes: the rules of its query packs are those of the extensions, and a
# result names no level of its own.
CODEQL: dict[str, Any] = {
    "runs": [
        {
            "tool": {
                "driver": {"name": "CodeQL", "rules": []},
                "extensions": [
                    {
                        "name": "codeql/python-queries",
                        "rules": [
                            {
                                "id": "py/sql-injection",
                                "defaultConfiguration": {"level": "error"},
                                "properties": {"security-severity": "8.8"},
                            },
                            {
                                "id": "py/weak-hash",
                                "defaultConfiguration": {"level": "warning"},
                                "properties": {"security-severity": "7.5"},
                            },
                            {
                                "id": "py/clear-text-logging",
                                "defaultConfiguration": {"level": "warning"},
                                "properties": {"security-severity": "4.3"},
                            },
                            {"id": "py/unused-import"},
                        ],
                    },
                    {"name": "codeql/actions-queries"},
                ],
            },
            "results": [
                {
                    "ruleId": "py/clear-text-logging",
                    "message": {"text": "Logs a | password\nin clear text."},
                    "locations": [
                        {
                            "physicalLocation": {
                                "artifactLocation": {"uri": "src/log.py"},
                                "region": {"startLine": 3},
                            }
                        }
                    ],
                },
                {
                    "ruleId": "py/sql-injection",
                    "message": {"text": "A query from user input."},
                    "locations": [
                        {
                            "physicalLocation": {
                                "artifactLocation": {"uri": "src/db.py"},
                                "region": {"startLine": 12},
                            }
                        }
                    ],
                },
                {
                    "rule": {"id": "py/unused-import"},
                    "level": "note",
                    "message": {"text": "Unused import."},
                    "locations": [
                        {"physicalLocation": {"artifactLocation": {"uri": "a.py"}}}
                    ],
                },
                {"ruleId": "py/weak-hash", "message": {"text": "MD5."}},
            ],
        }
    ]
}


def test_each_result_is_a_finding_with_the_level_and_severity_of_its_rule() -> None:
    found = findings(CODEQL)

    assert found == [
        Finding(
            "CodeQL",
            "py/clear-text-logging",
            "warning",
            4.3,
            "Logs a | password\nin clear text.",
            "src/log.py",
            3,
        ),
        Finding(
            "CodeQL",
            "py/sql-injection",
            "error",
            8.8,
            "A query from user input.",
            "src/db.py",
            12,
        ),
        Finding(
            "CodeQL", "py/unused-import", "note", None, "Unused import.", "a.py", 0
        ),
        Finding("CodeQL", "py/weak-hash", "warning", 7.5, "MD5.", "", 0),
    ]
    # An error, or a security alert of high severity or more, as code scanning stops.
    assert [item.stops for item in found] == [False, True, False, True]
    assert [item.kind for item in found] == [
        "medium security alert",
        "high security alert",
        "note",
        "high security alert",
    ]


def test_a_finding_is_ranked_as_github_ranks_its_severity() -> None:
    def kind(severity: float | None, level: str = "warning") -> str:
        return Finding("t", "r", level, severity, "", "", 0).kind

    assert kind(9.8) == "critical security alert"
    assert kind(1.0) == "low security alert"
    assert kind(None, "error") == "error"
    assert Finding("t", "r", "error", None, "", "", 0).stops


@pytest.mark.parametrize("raw", ["high", None, [1]])
def test_a_severity_that_is_no_number_is_none(raw: object) -> None:
    sarif = {
        "runs": [
            {
                "tool": {
                    "driver": {
                        "rules": [{"id": "x", "properties": {"security-severity": raw}}]
                    }
                },
                "results": [{"ruleId": "x"}],
            }
        ]
    }

    (finding,) = findings(sarif)

    assert finding == Finding("The analysis", "x", "warning", None, "", "", 0)


def test_the_summary_lists_what_fails_the_check_first() -> None:
    text = summary(findings(CODEQL), "codeql-sarif")

    assert text.startswith("### What the analysis found\n\n")
    assert "the artifact `codeql-sarif` of this run" in text
    rows = [line for line in text.splitlines() if line.startswith("| ")]
    assert rows == [
        "| Fails | Finding | Rule | Where |",
        "| --- | --- | --- | --- |",
        "| yes | MD5. | `py/weak-hash` (high security alert) | - |",
        "| yes | A query from user input. | `py/sql-injection` (high security alert)"
        " | `src/db.py:12` |",
        "| no | Unused import. | `py/unused-import` (note) | `a.py` |",
        "| no | Logs a \\| password in clear text. | `py/clear-text-logging`"
        " (medium security alert) | `src/log.py:3` |",
    ]


def test_the_summary_of_nothing_found() -> None:
    assert summary([], "codeql-sarif").endswith("\n\nNothing found.\n")


def write(path: Path, data: object) -> str:
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def test_the_command_fails_on_what_code_scanning_would_stop(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    summary_file = tmp_path / "summary.md"
    summary_file.write_text("before\n", encoding="utf-8")
    files = [
        write(tmp_path / "python.sarif", CODEQL),
        write(tmp_path / "actions.sarif", {"runs": []}),
    ]

    code = cli.main(
        ["sarif", "--artifact", "codeql-sarif", "--summary", str(summary_file), *files]
    )

    assert code == 1
    out = capsys.readouterr().out
    assert out.splitlines() == [
        "::group::Annotations",
        "::error file=src/db.py,line=12,title=CodeQL%3A py/sql-injection::"
        "A query from user input.",
        "::error title=CodeQL%3A py/weak-hash::MD5.",
        "::endgroup::",
        "4 findings, 2 of them an error or a security alert of high or critical"
        " severity.",
    ]
    written = summary_file.read_text(encoding="utf-8")
    assert written.startswith("before\n### What the analysis found\n")


def test_the_command_passes_when_nothing_would_stop(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    summary_file = tmp_path / "summary.md"
    file = write(tmp_path / "python.sarif", {"runs": [{"results": []}]})

    code = cli.main(
        ["sarif", "--artifact", "codeql-sarif", "--summary", str(summary_file), file]
    )

    assert code == 0
    assert capsys.readouterr().out == (
        "0 findings, 0 of them an error or a security alert of high or critical"
        " severity.\n"
    )
    assert summary_file.read_text(encoding="utf-8").endswith("Nothing found.\n")


@pytest.mark.parametrize("content", ["[]", "{", None])
def test_a_file_that_is_no_sarif_fails_the_command(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], content: str | None
) -> None:
    file = tmp_path / "python.sarif"
    if content is not None:
        file.write_text(content, encoding="utf-8")
    summary_file = tmp_path / "summary.md"

    code = cli.main(
        ["sarif", "--artifact", "a", "--summary", str(summary_file), str(file)]
    )

    assert code == 2
    assert capsys.readouterr().err.startswith("blueprint.py: ")
    assert not summary_file.exists()
