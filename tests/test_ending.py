"""Tests of the acceptances of osv-scanner.toml that end soon: blueprint/ending.py, which
names each acceptance that ends within two weeks and keeps one issue about them, and the
command advisories --ending of blueprint.py, against a GitHub of answers."""

from __future__ import annotations

import datetime
import json
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from blueprint import dependabot, ending
from blueprint.cli import main
from blueprint.dependabot import Acceptance
from blueprint.ending import LABELS, MARKER, TITLE, WINDOW, body, keep_issue
from blueprint.github import Api, Json

GIT = shutil.which("git")
needs_git = pytest.mark.skipif(
    GIT is None, reason="the files of OSV-Scanner are those that git knows"
)
REPO = "octo/demo"
# Ten days before the end of the acceptance of the Pillow of Home Assistant, which
# would have passed quietly (repo-blueprint#851).
TODAY = datetime.date(2026, 11, 12)
PILLOW = """\
[[PackageOverrides]]
name = "pillow"
version = "12.3.0"
ecosystem = "PyPI"
vulnerability.ignore = true
effectiveUntil = 2026-11-22
reason = "Home Assistant pins it; the next test plugin moves it."

[[PackageOverrides]]
name = "uv"
version = "0.12.23"
ecosystem = "PyPI"
vulnerability.ignore = true
effectiveUntil = 2027-01-31
reason = "Home Assistant pins it."

[[IgnoredVulns]]
id = "GHSA-aaaa-bbbb-cccc"
ignoreUntil = 2026-11-01T12:00:00Z
reason = "Only the tests reach it."
"""
LATER = """\
[[PackageOverrides]]
name = "pillow"
version = "12.3.0"
ecosystem = "PyPI"
vulnerability.ignore = true
effectiveUntil = 2026-12-20
reason = "Home Assistant pins it."
"""


@pytest.fixture(autouse=True)
def fixed_day(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dependabot, "today", lambda: TODAY)


def acceptance(
    until: datetime.date,
    *,
    name: str = "pillow",
    advisory: str = "",
    config: str = "osv-scanner.toml",
    reason: str = "Pinned.",
) -> Acceptance:
    if advisory:
        return Acceptance(config, until, reason, advisory=advisory)
    return Acceptance(config, until, reason, "pip", name, "12.3.0")


def repository(root: Path, files: dict[str, str]) -> Path:
    """A git repository with these files."""
    assert GIT
    subprocess.run([GIT, "init", "--quiet", str(root)], check=True)
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8", newline="\n")
    return root


def test_an_acceptance_is_named_from_two_weeks_before_its_end() -> None:
    last = acceptance(TODAY + WINDOW, name="last")
    first = acceptance(TODAY + datetime.timedelta(days=3), name="first")
    ended = acceptance(TODAY - datetime.timedelta(days=1), advisory="CVE-2026-1")
    later = acceptance(TODAY + WINDOW + datetime.timedelta(days=1), name="later")

    assert ending.ending([last, later, first, ended], TODAY) == [ended, first, last]


@pytest.mark.parametrize(
    ("days", "said"),
    [
        (-3, "until 2026-11-09, which has come: OSV-Scanner reports it again"),
        (0, "until 2026-11-12, which has come: OSV-Scanner reports it again"),
        (1, "until 2026-11-13, tomorrow"),
        (10, "until 2026-11-22, in 10 days"),
    ],
)
def test_the_line_names_what_ends_and_how_near(days: int, said: str) -> None:
    until = TODAY + datetime.timedelta(days=days)

    assert ending.line(acceptance(until), TODAY) == (
        f"osv-scanner.toml accepts every advisory of pillow 12.3.0 {said}: Pinned."
    )
    assert ending.line(acceptance(until, advisory="GHSA-x"), TODAY).startswith(
        "osv-scanner.toml accepts the advisory GHSA-x until"
    )


def test_the_issue_names_the_file_the_package_the_version_and_the_date() -> None:
    text = body(
        [
            acceptance(
                datetime.date(2026, 11, 22),
                config="stacks/home-assistant/osv-scanner.toml",
                reason="Pinned for the tests.",
            )
        ]
    )

    assert text.startswith(f"{MARKER}\n")
    assert (
        "\n- `stacks/home-assistant/osv-scanner.toml` accepts every advisory of "
        "pillow 12.3.0 until **2026-11-22**: Pinned for the tests.\n"
    ) in text
    assert "advisories --fix" in text
    assert "move `effectiveUntil` (or `ignoreUntil`)" in text
    # The text changes with the acceptances alone, not with the day of the run.
    assert TODAY.isoformat() not in text


class FakeClient:
    """GitHub with a list of issues, and the changes it was asked for."""

    def __init__(self, issues: list[Json]) -> None:
        self.issues = issues
        self.asked: list[str] = []
        self.changes: list[tuple[str, str, Json]] = []

    def get_all(self, path: str) -> list[Json]:
        self.asked.append(path)
        return self.issues

    def patch(self, path: str, body: Json) -> None:
        self.changes.append(("PATCH", path, body))

    def post(self, path: str, body: Json) -> None:
        self.changes.append(("POST", path, body))


def issue(number: int, text: str, **more: object) -> Json:
    return {"number": number, "body": text, **more}


@needs_git
def test_an_acceptance_that_ends_soon_opens_the_issue(tmp_path: Path) -> None:
    root = repository(tmp_path, {"osv-scanner.toml": PILLOW})
    # A pull request and an issue of a person with the label are not its own.
    client = FakeClient([issue(1, MARKER, pull_request={}), issue(2, "Other.")])

    outcome = keep_issue(client, REPO, root)

    assert client.asked == [f"repos/{REPO}/issues?state=open"]
    [(method, path, sent)] = client.changes
    assert (method, path) == ("POST", f"repos/{REPO}/issues")
    assert sent["title"] == TITLE
    assert sent["labels"] == LABELS
    assert "every advisory of pillow 12.3.0 until **2026-11-22**" in sent["body"]
    assert "the advisory GHSA-aaaa-bbbb-cccc until **2026-11-01**" in sent["body"]
    # uv ends in 80 days, far outside the window.
    assert "uv" not in sent["body"]
    assert [warning.split("::")[2] for warning in outcome.warnings] == [
        "osv-scanner.toml accepts the advisory GHSA-aaaa-bbbb-cccc until 2026-11-01, "
        "which has come: OSV-Scanner reports it again: Only the tests reach it.",
        "osv-scanner.toml accepts every advisory of pillow 12.3.0 until 2026-11-22, "
        "in 10 days: Home Assistant pins it; the next test plugin moves it.",
    ]
    assert all(
        warning.startswith("::warning title=An accepted advisory ends soon::")
        for warning in outcome.warnings
    )
    assert outcome.summary[-1] == "Opened an issue that names them."


@needs_git
def test_the_issue_follows_the_acceptances(tmp_path: Path) -> None:
    root = repository(tmp_path, {"osv-scanner.toml": PILLOW})
    found, _ = dependabot.acceptances(root)
    current = body(ending.ending(found, TODAY))

    changed = FakeClient([issue(7, f"{MARKER}\nOlder text.")])
    keep_issue(changed, REPO, root)
    same = FakeClient([issue(7, current)])
    outcome = keep_issue(same, REPO, root)

    assert changed.changes == [("PATCH", f"repos/{REPO}/issues/7", {"body": current})]
    assert same.changes == []
    assert outcome.summary[-1] == "#7 names them already."


UNEXPLAINED = """\
[[IgnoredVulns]]
id = "GHSA-dddd-eeee-ffff"
ignoreUntil = 2026-11-20
"""


@needs_git
def test_an_ignored_advisory_without_a_reason_is_named_too(tmp_path: Path) -> None:
    root = repository(tmp_path, {"osv-scanner.toml": UNEXPLAINED})
    # It closes no Dependabot alert, but it ends on its date all the same.
    assert dependabot.acceptances(root)[0] == []
    # The issue whose label someone took away is still found by its mark.
    client = FakeClient([issue(7, f"{MARKER}\nOlder text.", labels=[])])

    outcome = keep_issue(client, REPO, root)

    [(method, path, sent)] = client.changes
    assert (method, path) == ("PATCH", f"repos/{REPO}/issues/7")
    assert (
        "the advisory GHSA-dddd-eeee-ffff until **2026-11-20**: (no reason given)"
        in sent["body"]
    )
    assert len(outcome.warnings) == 1


@needs_git
def test_the_issue_closes_once_no_acceptance_ends_soon(tmp_path: Path) -> None:
    root = repository(tmp_path, {"stacks/osv-scanner.toml": LATER})
    client = FakeClient([issue(7, MARKER)])

    outcome = keep_issue(client, REPO, root)

    assert client.changes == [
        (
            "PATCH",
            f"repos/{REPO}/issues/7",
            {"state": "closed", "state_reason": "completed"},
        )
    ]
    assert outcome.warnings == []
    assert outcome.summary == [
        "No acceptance of an osv-scanner.toml ends within 14 days.",
        "Closed #7.",
    ]


@needs_git
def test_nothing_ends_and_no_issue_is_open(tmp_path: Path) -> None:
    root = repository(tmp_path, {"osv-scanner.toml": LATER})
    client = FakeClient([])

    outcome = keep_issue(client, REPO, root)

    assert client.changes == []
    assert outcome.summary == [
        "No acceptance of an osv-scanner.toml ends within 14 days."
    ]


@needs_git
@pytest.mark.parametrize(
    ("files", "issues", "said"),
    [
        ({"osv-scanner.toml": PILLOW}, [], "Would open an issue that names them."),
        ({"osv-scanner.toml": PILLOW}, [issue(7, MARKER)], "Would update #7."),
        ({"osv-scanner.toml": LATER}, [issue(7, MARKER)], "Would close #7."),
    ],
)
def test_the_dry_run_changes_nothing(
    tmp_path: Path, files: dict[str, str], issues: list[Json], said: str
) -> None:
    client = FakeClient(issues)

    outcome = keep_issue(client, REPO, repository(tmp_path, files), dry_run=True)

    assert client.changes == []
    assert outcome.summary[-1] == said


class Runner:
    """The GitHub CLI with an answer for the list of issues, and every change."""

    def __init__(self, issues: list[Json]) -> None:
        self.issues = issues
        self.sent: list[tuple[str, str, Json]] = []

    def __call__(
        self, arguments: Sequence[str], payload: str | None
    ) -> subprocess.CompletedProcess[str]:
        if "--paginate" in arguments:
            return subprocess.CompletedProcess([], 0, json.dumps([self.issues]), "")
        self.sent.append((arguments[3], arguments[4], json.loads(payload or "null")))
        return subprocess.CompletedProcess(
            arguments, 0, 'HTTP/2.0 201 Created\r\n\r\n{"number": 9}', ""
        )


@needs_git
def test_the_command_warns_and_opens_the_issue(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repository(tmp_path, {"osv-scanner.toml": PILLOW})
    runner = Runner([])

    code = main(["--repo", REPO, "advisories", "--ending"], api=Api(runner), root=root)

    printed = capsys.readouterr()
    assert code == 0
    assert [(method, path) for method, path, _ in runner.sent] == [
        ("POST", f"repos/{REPO}/issues")
    ]
    assert printed.err.count("::warning title=An accepted advisory ends soon::") == 2
    assert printed.out.splitlines() == [
        f"The acceptances of the osv-scanner.toml files of {REPO} that end within 14 "
        "days:",
        "- osv-scanner.toml accepts the advisory GHSA-aaaa-bbbb-cccc until 2026-11-01, "
        "which has come: OSV-Scanner reports it again: Only the tests reach it.",
        "- osv-scanner.toml accepts every advisory of pillow 12.3.0 until 2026-11-22, "
        "in 10 days: Home Assistant pins it; the next test plugin moves it.",
        "Opened an issue that names them.",
    ]


@needs_git
def test_the_command_in_a_dry_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repository(tmp_path, {"osv-scanner.toml": LATER})
    runner = Runner([issue(7, MARKER)])

    code = main(
        ["--repo", REPO, "advisories", "--ending", "--dry-run"],
        api=Api(runner),
        root=root,
    )

    printed = capsys.readouterr().out
    assert code == 0
    assert runner.sent == []
    assert "end within 14 days (a dry run: nothing changed):" in printed
    assert printed.endswith("Would close #7.\n")


@needs_git
def test_the_check_names_an_acceptance_that_ends_soon(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repository(tmp_path, {"osv-scanner.toml": PILLOW})
    assert main(["advisories", "--fix"], root=root) == 0
    capsys.readouterr()

    # Only a note: the check stays green until the date.
    assert main(["advisories"], root=root) == 0

    lines = capsys.readouterr().out.splitlines()
    assert [line for line in lines if line.startswith("Ends soon: ")] == [
        "Ends soon: osv-scanner.toml accepts the advisory GHSA-aaaa-bbbb-cccc until "
        "2026-11-01, which has come: OSV-Scanner reports it again: Only the tests "
        "reach it.",
        "Ends soon: osv-scanner.toml accepts every advisory of pillow 12.3.0 until "
        "2026-11-22, in 10 days: Home Assistant pins it; the next test plugin moves "
        "it.",
    ]


@pytest.mark.parametrize(
    "options",
    [
        ["--ending", "--fix"],
        ["--ending", "--dependabot"],
        ["--fix", "--dependabot"],
        ["--fix", "--dry-run"],
        ["--dry-run"],
    ],
)
def test_the_modes_of_the_command_go_one_at_a_time(
    capsys: pytest.CaptureFixture[str], options: list[str]
) -> None:
    assert main(["advisories", *options]) == 2
    assert "--fix, --dependabot and --ending go one at a time" in (
        capsys.readouterr().err
    )
