"""Tests of the Dependabot alerts of what osv-scanner.toml accepts: blueprint/dependabot.py,
which dismisses each open alert that an acceptance covers, with its reason and its end,
and opens again each one that it dismissed once no acceptance covers it, and the command
advisories --dependabot of blueprint.py, against a GitHub of answers."""

from __future__ import annotations

import datetime
import json
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from blueprint import advisories, dependabot
from blueprint.cli import main
from blueprint.dependabot import (
    COMMENT_LIMIT,
    ECOSYSTEMS,
    MARKER,
    Acceptance,
    Alert,
    Change,
    Manifests,
    Outcome,
    acceptances,
    covers,
    ignored,
    package_key,
    pinned,
    sync,
)
from blueprint.github import Api, Json

GIT = shutil.which("git")
needs_git = pytest.mark.skipif(
    GIT is None, reason="the files of OSV-Scanner are those that git knows"
)
REPO = "octo/demo"
TODAY = datetime.date(2026, 10, 25)
UNTIL = datetime.date(2026, 11, 22)
# Home Assistant pins Pillow 12.3.0 for the tests of an integration, and Dependabot
# kept 41 alerts of it open in repo-blueprint and homedarts-for-autodarts.
PILLOW = """\
[[PackageOverrides]]
name = "pillow"
version = "12.3.0"
ecosystem = "PyPI"
vulnerability.ignore = true
effectiveUntil = 2026-11-22
reason = \"\"\"Home Assistant pins it;
the next test plugin moves it.\"\"\"

[[PackageOverrides]]
name = "uv"
version = "0.12.23"
ecosystem = "PyPI"
vulnerability.ignore = true
effectiveUntil = 2026-10-25
reason = "Home Assistant pins it."

[[IgnoredVulns]]
id = "GHSA-aaaa-bbbb-cccc"
ignoreUntil = 2026-12-01T12:00:00Z
reason = "Only the tests reach it."

[[IgnoredVulns]]
id = "CVE-2026-1"
"""
REQUIREMENTS = """\
pillow==12.3.0 \\
    --hash=sha256:00
uv==0.12.23 \\
    --hash=sha256:01
"""
WEB = """\
[[IgnoredVulns]]
id = "cve-2026-777"
ignoreUntil = 2026-11-01
reason = "The tool runs in the build alone."
"""


def repository(root: Path, files: dict[str, str]) -> Path:
    """A git repository with these files."""
    assert GIT
    subprocess.run([GIT, "init", "--quiet", str(root)], check=True)
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8", newline="\n")
    return root


def alert(
    number: int,
    name: str = "Pillow",
    manifest: str = "requirements-test.txt",
    *,
    ecosystem: str = "pip",
    state: str = "open",
    ids: Sequence[str] = (),
    comment: str | None = None,
) -> dict[str, Any]:
    """A Dependabot alert as GitHub's API answers it."""
    ghsa = f"GHSA-{number:04d}-xxxx-yyyy"
    return {
        "number": number,
        "state": state,
        "html_url": f"https://github.com/{REPO}/security/dependabot/{number}",
        "dependency": {
            "package": {"ecosystem": ecosystem, "name": name},
            "manifest_path": manifest,
            "scope": "runtime",
        },
        "security_advisory": {
            "ghsa_id": ghsa,
            "cve_id": None,
            "identifiers": [{"type": "GHSA", "value": ghsa}]
            + [{"type": "CVE", "value": value} for value in ids],
        },
        "dismissed_comment": comment,
    }


class FakeClient:
    """GitHub with a list of alerts, and the changes it was asked for."""

    def __init__(self, alerts: list[Json]) -> None:
        self.alerts = alerts
        self.asked: list[str] = []
        self.patched: list[tuple[str, Json]] = []

    def get_all(self, path: str) -> list[Json]:
        self.asked.append(path)
        return self.alerts

    def patch(self, path: str, body: Json) -> None:
        self.patched.append((path, body))


@pytest.fixture(autouse=True)
def fixed_day(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dependabot, "today", lambda: TODAY)


def test_every_ecosystem_of_the_acceptances_has_its_name_of_dependabot() -> None:
    assert set(ECOSYSTEMS) == set(advisories.DATASOURCES)


def test_today_is_the_date_in_utc(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.undo()
    assert dependabot.today() == datetime.datetime.now(datetime.UTC).date()


def test_an_acceptance_ends_on_its_date() -> None:
    acceptance = Acceptance("osv-scanner.toml", UNTIL, "pinned")

    assert acceptance.active(UNTIL - datetime.timedelta(days=1))
    assert not acceptance.active(UNTIL)


def test_the_comment_names_the_file_the_end_and_the_reason() -> None:
    short = Acceptance("stacks/a/osv-scanner.toml", UNTIL, "Home Assistant pins it.")
    long = Acceptance("osv-scanner.toml", UNTIL, "word " * 100)

    assert short.comment() == (
        "Accepted in stacks/a/osv-scanner.toml until 2026-11-22: Home Assistant pins it."
    )
    assert short.comment().startswith(MARKER)
    # GitHub takes no longer comment.
    assert len(long.comment()) == COMMENT_LIMIT
    assert long.comment().endswith(" wo…")


def test_names_compare_as_their_ecosystem_does() -> None:
    assert package_key("pip", "Zope.Interface_x") == "zope-interface-x"
    assert package_key("npm", "Left-Pad") == "left-pad"


def test_an_alert_has_every_id_of_its_advisory() -> None:
    found = Alert.of(
        {
            "number": 7,
            "state": "dismissed",
            "dependency": {"package": {"ecosystem": "pip", "name": "Pillow"}},
            "security_advisory": {
                "ghsa_id": "GHSA-a",
                "cve_id": "cve-1",
                "identifiers": [{"value": "GHSA-a"}, {"value": None}],
            },
            "dismissed_comment": f"{MARKER}osv-scanner.toml until 2026-11-22: x",
        }
    )
    bare = Alert.of({"number": "8"})

    assert found.ids == {"GHSA-A", "CVE-1"}
    assert found.ours
    assert found.manifest == ""
    assert bare == Alert(8, "", "", "", "", frozenset(), "", "")
    assert not bare.ours


def test_a_person_dismissed_an_alert_without_the_marker() -> None:
    assert not Alert.of(alert(1, state="dismissed", comment="Not used.")).ours
    assert not Alert.of(alert(1, comment=f"{MARKER}x")).ours


def write(root: Path, name: str, text: str | bytes) -> None:
    (root / name).parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        (root / name).write_bytes(text)
    else:
        (root / name).write_text(text, encoding="utf-8")


def test_the_versions_of_each_kind_of_lock_file(tmp_path: Path) -> None:
    write(
        tmp_path, "requirements-test.txt", REQUIREMENTS + "Foo_Bar[extra] === 2.0 ; x\n"
    )
    write(
        tmp_path,
        "uv.lock",
        '[[package]]\nname = "Pillow"\nversion = "12.3.0"\n\n[[package]]\nname = 1\n',
    )
    write(
        tmp_path,
        "web/package-lock.json",
        json.dumps(
            {
                "packages": {
                    "": {"version": "1.0.0"},
                    "node_modules/a": {"version": "1.0.0"},
                    "node_modules/b/node_modules/@scope/c": {"version": "2.0.0"},
                    "node_modules/d": {},
                    "node_modules/e": "x",
                }
            }
        ),
    )
    write(
        tmp_path,
        "composer.lock",
        json.dumps(
            {
                "packages": [{"name": "Vendor/A", "version": "v6.4.0"}, "x"],
                "packages-dev": [{"name": "vendor/b", "version": "1.2"}, {"name": 1}],
            }
        ),
    )

    assert pinned(tmp_path, "requirements-test.txt", "pip") == {
        "pillow": {"12.3.0"},
        "uv": {"0.12.23"},
        "foo-bar": {"2.0"},
    }
    assert pinned(tmp_path, "uv.lock", "pip") == {"pillow": {"12.3.0"}}
    assert pinned(tmp_path, "web/package-lock.json", "npm") == {
        "a": {"1.0.0"},
        "@scope/c": {"2.0.0"},
    }
    assert pinned(tmp_path, "composer.lock", "composer") == {
        "vendor/a": {"v6.4.0", "6.4.0"},
        "vendor/b": {"1.2"},
    }


@pytest.mark.parametrize(
    ("manifest", "text"),
    [
        # Not outside the checkout, nor a file that isn't there.
        ("", None),
        ("../requirements.txt", None),
        ("/etc/requirements.txt", None),
        ("missing.txt", None),
        ("bad.txt", b"\xff\xfe"),
        # A lock file that the command can't read, or doesn't know.
        ("uv.lock", "not toml ["),
        ("poetry.lock", 'package = "x"\n'),
        ("package-lock.json", "{"),
        ("package-lock.json", "[]"),
        ("package-lock.json", '{"packages": []}'),
        ("composer.lock", '{"packages": {}}'),
        ("yarn.lock", "pillow@1:\n"),
    ],
)
def test_a_lock_file_that_it_cant_read_pins_nothing(
    tmp_path: Path, manifest: str, text: str | bytes | None
) -> None:
    if text is not None:
        write(tmp_path, manifest, text)

    assert pinned(tmp_path, manifest, "pip") == {}


def test_each_lock_file_is_read_once(tmp_path: Path) -> None:
    write(tmp_path, "requirements.txt", "pillow==1\n")
    manifests = Manifests(tmp_path)

    assert manifests.versions("requirements.txt", "pip") == {"pillow": {"1"}}
    (tmp_path / "requirements.txt").unlink()
    assert manifests.versions("requirements.txt", "pip") == {"pillow": {"1"}}


def test_an_acceptance_covers_its_folder_its_package_and_its_version(
    tmp_path: Path,
) -> None:
    write(tmp_path, "requirements-test.txt", REQUIREMENTS)
    write(tmp_path, "web/requirements.txt", "pillow==12.3.0\n")
    manifests = Manifests(tmp_path)
    version = Acceptance("osv-scanner.toml", UNTIL, "pinned", "pip", "pillow", "12.3.0")
    advisory = Acceptance("web/osv-scanner.toml", UNTIL, "x", advisory="cve-2026-9")

    def covered(acceptance: Acceptance, data: dict[str, Any]) -> bool:
        return covers(acceptance, Alert.of(data), manifests)

    assert covered(version, alert(1, "Pillow"))
    # Another folder, ecosystem, package or version.
    assert not covered(version, alert(2, manifest="web/requirements.txt"))
    assert not covered(version, alert(3, ecosystem="npm"))
    assert not covered(version, alert(4, "uv"))
    assert not covered(
        Acceptance("osv-scanner.toml", UNTIL, "x", "pip", "uv", "0.13.0"),
        alert(5, "uv"),
    )
    # An advisory by any of its ids, in every package of its folder.
    assert covered(advisory, alert(6, "x", "web/requirements.txt", ids=["CVE-2026-9"]))
    assert not covered(advisory, alert(7, "x", "web/requirements.txt"))
    assert not covered(advisory, alert(8, ids=["CVE-2026-9"]))


@needs_git
def test_the_acceptances_of_every_osv_scanner_toml(tmp_path: Path) -> None:
    root = repository(
        tmp_path,
        {
            "osv-scanner.toml": PILLOW,
            "web/osv-scanner.toml": WEB,
            # OSV-Scanner can't use these, and advisories says why.
            "broken/osv-scanner.toml": "[[PackageOverrides]\n",
            "unknown/osv-scanner.toml": 'Extra = 1\n[[IgnoredVulns]]\nid = "X"\n',
            "listed/osv-scanner.toml": 'IgnoredVulns = "x"\n',
            "overrides/osv-scanner.toml": 'PackageOverrides = "x"\n',
            "bad/osv-scanner.toml": "",
        },
    )
    (root / "bad/osv-scanner.toml").write_bytes(b"\xff")

    found, notes = acceptances(root)

    assert found == [
        Acceptance(
            "osv-scanner.toml",
            UNTIL,
            "Home Assistant pins it; the next test plugin moves it.",
            "pip",
            "pillow",
            "12.3.0",
        ),
        Acceptance(
            "osv-scanner.toml",
            datetime.date(2026, 10, 25),
            "Home Assistant pins it.",
            "pip",
            "uv",
            "0.12.23",
        ),
        Acceptance(
            "osv-scanner.toml",
            datetime.date(2026, 12, 1),
            "Only the tests reach it.",
            advisory="GHSA-aaaa-bbbb-cccc",
        ),
        Acceptance(
            "web/osv-scanner.toml",
            datetime.date(2026, 11, 1),
            "The tool runs in the build alone.",
            advisory="cve-2026-777",
        ),
    ]
    assert [note.split(":")[0] for note in notes] == [
        "bad/osv-scanner.toml",
        "broken/osv-scanner.toml",
        "listed/osv-scanner.toml",
        "osv-scanner.toml",
        "overrides/osv-scanner.toml",
        "unknown/osv-scanner.toml",
    ]
    assert notes[3] == (
        "osv-scanner.toml: [[IgnoredVulns]] 2 has no reason and no ignoreUntil, so "
        "its Dependabot alerts stay open: an acceptance that closes them names its "
        "advisory, says why and ends"
    )


def test_an_entry_without_its_id_closes_nothing(tmp_path: Path) -> None:
    write(tmp_path, "osv-scanner.toml", '[[IgnoredVulns]]\nreason = "x"\n')

    found, notes = ignored(tmp_path, Path("osv-scanner.toml"))

    assert found == []
    assert notes == [
        "osv-scanner.toml: [[IgnoredVulns]] 1 has no id and no ignoreUntil, so its "
        "Dependabot alerts stay open: an acceptance that closes them names its "
        "advisory, says why and ends"
    ]


@needs_git
@pytest.mark.parametrize("dry_run", [False, True])
def test_sync_closes_the_accepted_alerts_and_opens_the_rest_again(
    tmp_path: Path, dry_run: bool
) -> None:
    root = repository(
        tmp_path,
        {
            "osv-scanner.toml": PILLOW,
            "requirements-test.txt": REQUIREMENTS,
            "web/osv-scanner.toml": WEB,
            "web/package-lock.json": json.dumps(
                {"packages": {"node_modules/tool": {"version": "1.0.0"}}}
            ),
        },
    )
    ours = f"{MARKER}osv-scanner.toml until 2026-11-22: x"
    client = FakeClient(
        [
            alert(3, "Pillow"),
            alert(1, "pillow"),
            # The acceptance of uv ended today.
            alert(2, "uv"),
            alert(
                4,
                "tool",
                "web/package-lock.json",
                ecosystem="npm",
                ids=["CVE-2026-777"],
            ),
            alert(5, "other", ids=["GHSA-AAAA-BBBB-CCCC"]),
            # Closed by the command before: uv is no longer accepted, Pillow is.
            alert(6, "uv", state="dismissed", comment=ours),
            alert(7, "Pillow", state="dismissed", comment=ours),
            # Closed by a person, or fixed: none of the command's business.
            alert(8, "uv", state="dismissed", comment="We don't ship it."),
            alert(9, "uv", state="fixed"),
        ]
    )

    outcome = sync(client, REPO, root, dry_run=dry_run)

    assert client.asked == [f"repos/{REPO}/dependabot/alerts?state=open,dismissed"]
    assert [
        (change.alert.number, change.acceptance and change.acceptance.config)
        for change in outcome.changes
    ] == [
        (1, "osv-scanner.toml"),
        (3, "osv-scanner.toml"),
        (4, "web/osv-scanner.toml"),
        (5, "osv-scanner.toml"),
        (6, None),
    ]
    assert (outcome.kept, outcome.uncovered) == (1, 1)
    assert outcome.notes == [
        "osv-scanner.toml: [[IgnoredVulns]] 2 has no reason and no ignoreUntil, so "
        "its Dependabot alerts stay open: an acceptance that closes them names its "
        "advisory, says why and ends"
    ]
    expected = [
        (
            f"repos/{REPO}/dependabot/alerts/1",
            {
                "state": "dismissed",
                "dismissed_reason": "tolerable_risk",
                "dismissed_comment": "Accepted in osv-scanner.toml until 2026-11-22: "
                "Home Assistant pins it; the next test plugin moves it.",
            },
        ),
        (f"repos/{REPO}/dependabot/alerts/3", outcome.changes[1].body()),
        (f"repos/{REPO}/dependabot/alerts/4", outcome.changes[2].body()),
        (f"repos/{REPO}/dependabot/alerts/5", outcome.changes[3].body()),
        (f"repos/{REPO}/dependabot/alerts/6", {"state": "open"}),
    ]
    assert client.patched == ([] if dry_run else expected)


def test_the_report_names_each_alert_by_its_number_and_link() -> None:
    acceptance = Acceptance("stacks/a/osv-scanner.toml", UNTIL, "x")
    outcome = Outcome(
        [
            Change(Alert.of(alert(1)), acceptance),
            Change(Alert.of({"number": 2}), None),
        ],
        kept=3,
        uncovered=4,
        notes=["a note"],
    )
    url = f"https://github.com/{REPO}/security/dependabot/1"

    assert outcome.report(REPO, dry_run=False) == [
        f"The Dependabot alerts of {REPO} and the advisories that its "
        "osv-scanner.toml files accept:",
        f"- closed #1 {url}: accepted in stacks/a/osv-scanner.toml until 2026-11-22",
        "- opened again #2: no acceptance covers it any more",
        "1 closed, 1 opened again, 3 closed before and still accepted, 4 open that "
        "no acceptance covers.",
        "a note",
    ]
    assert outcome.report(REPO, dry_run=True)[:4] == [
        f"The Dependabot alerts of {REPO} and the advisories that its "
        "osv-scanner.toml files accept (a dry run: nothing changed):",
        f"- would close #1 {url}: accepted in stacks/a/osv-scanner.toml until "
        "2026-11-22",
        "- would open again #2: no acceptance covers it any more",
        "1 to close, 1 to open again, 3 closed before and still accepted, 4 open "
        "that no acceptance covers.",
    ]


class Runner:
    """The GitHub CLI with an answer for the list of alerts, and every PATCH."""

    def __init__(self, listed: subprocess.CompletedProcess[str]) -> None:
        self.listed = listed
        self.patched: list[tuple[str, Json]] = []

    def __call__(
        self, arguments: Sequence[str], payload: str | None
    ) -> subprocess.CompletedProcess[str]:
        if "--paginate" in arguments:
            return self.listed
        self.patched.append((arguments[4], json.loads(payload or "null")))
        return subprocess.CompletedProcess(
            arguments, 0, "HTTP/2.0 200 OK\r\n\r\n{}", ""
        )


def pages(alerts: list[Json]) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], 0, json.dumps([alerts]), "")


def refused(message: str, status: int) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], 1, "", f"gh: {message} (HTTP {status})")


@needs_git
def test_the_command_closes_the_accepted_alerts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repository(
        tmp_path,
        {"osv-scanner.toml": PILLOW, "requirements-test.txt": REQUIREMENTS},
    )
    runner = Runner(pages([alert(1)]))

    code = main(
        ["--repo", REPO, "advisories", "--dependabot"], api=Api(runner), root=root
    )

    printed = capsys.readouterr().out
    assert code == 0
    assert [path for path, _ in runner.patched] == [f"repos/{REPO}/dependabot/alerts/1"]
    assert "- closed #1 " in printed
    assert "1 closed, 0 opened again" in printed


@needs_git
def test_the_dry_run_changes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repository(
        tmp_path,
        {"osv-scanner.toml": PILLOW, "requirements-test.txt": REQUIREMENTS},
    )
    runner = Runner(pages([alert(1)]))

    code = main(
        ["--repo", REPO, "advisories", "--dependabot", "--dry-run"],
        api=Api(runner),
        root=root,
    )

    assert code == 0
    assert runner.patched == []
    assert "- would close #1 " in capsys.readouterr().out


@needs_git
@pytest.mark.parametrize(
    ("answer", "code", "said"),
    [
        (
            refused("Dependabot alerts are disabled for this repository.", 403),
            0,
            f"Dependabot alerts are off in {REPO}",
        ),
        (
            refused("Resource not accessible by integration", 403),
            1,
            f"blueprint.py: GitHub refused the Dependabot alerts of {REPO} (GitHub "
            "answered 403: Resource not accessible by integration). The token needs "
            "the permission Dependabot alerts (read and write)",
        ),
        (refused("Bad credentials", 401), 1, "Dependabot alerts (read and write)"),
        (refused("Server Error", 500), 2, "blueprint.py: GitHub answered 500"),
    ],
)
def test_the_command_says_what_github_refused(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    answer: subprocess.CompletedProcess[str],
    code: int,
    said: str,
) -> None:
    root = repository(tmp_path, {"osv-scanner.toml": PILLOW})

    done = main(
        ["--repo", REPO, "advisories", "--dependabot"],
        api=Api(Runner(answer)),
        root=root,
    )

    printed = capsys.readouterr()
    assert done == code
    assert said in printed.out + printed.err


@pytest.mark.parametrize(
    "options", [["--dry-run"], ["--fix", "--dependabot"], ["--fix", "--dry-run"]]
)
def test_a_dry_run_goes_with_dependabot_and_fix_without_it(
    capsys: pytest.CaptureFixture[str], options: list[str]
) -> None:
    assert main(["advisories", *options]) == 2
    assert "--dry-run goes with --dependabot, and --fix without it" in (
        capsys.readouterr().err
    )
