"""Tests of the rules of Renovate for what osv-scanner.toml accepts: blueprint/advisories.py,
which reads the [[PackageOverrides]] of each osv-scanner.toml and writes a rule for each
version whose every advisory it accepts into .github/renovate-accepted.json5."""

from __future__ import annotations

import datetime
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from blueprint import advisories
from blueprint.advisories import Accepted, check, configs, preset, read
from blueprint.cli import main

ROOT = Path(__file__).parents[1]
GIT = shutil.which("git")
needs_git = pytest.mark.skipif(
    GIT is None, reason="the files of OSV-Scanner are those that git knows"
)

# Home Assistant pins Pillow and uv exactly, so their advisories wait for its next
# release: OSV-Scanner reported 40 of them in stacks/home-assistant/, and Renovate
# logged an empty commit for each of the two in every run (repo-blueprint#381, #382,
# #384).
PINNED = """\
# The test tools that Home Assistant pins.

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
ignore = true
effectiveUntil = 2026-11-22T12:00:00Z
reason = "Home Assistant pins it."
"""


def repository(root: Path, files: dict[str, str]) -> Path:
    """A git repository with these files."""
    assert GIT
    subprocess.run([GIT, "init", "--quiet", str(root)], check=True)
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8", newline="\n")
    return root


def rules(text: str) -> list[dict[str, Any]]:
    """The rules of the preset, which is JSON after its comments."""
    found = json.loads(text[text.index("{") :])["packageRules"]
    assert isinstance(found, list)
    return found


@needs_git
def test_every_version_that_is_accepted_with_every_advisory_gets_a_rule(
    tmp_path: Path,
) -> None:
    root = repository(tmp_path, {"stacks/home-assistant/osv-scanner.toml": PINNED})

    accepted, problems = read(root, Path("stacks/home-assistant/osv-scanner.toml"))

    assert problems == []
    until = datetime.date(2026, 11, 22)
    assert accepted == [
        Accepted(
            "stacks/home-assistant",
            "pillow",
            "12.3.0",
            "PyPI",
            until,
            "Home Assistant pins it; the next test plugin moves it.",
        ),
        Accepted(
            "stacks/home-assistant",
            "uv",
            "0.12.23",
            "PyPI",
            until,
            "Home Assistant pins it.",
        ),
    ]
    pillow, uv = rules(preset(accepted))
    # Renovate makes no update of that version in the lock files of the folder, the
    # fix of a vulnerability neither, and matches the version and the folder exactly.
    assert pillow == {
        "description": "stacks/home-assistant/osv-scanner.toml accepts every advisory "
        "of pillow 12.3.0 until 2026-11-22: Home Assistant pins it; the next test "
        "plugin moves it.",
        "matchFileNames": ["/^stacks/home-assistant/[^/]+$/"],
        "matchDatasources": ["pypi"],
        "matchPackageNames": ["pillow"],
        "matchCurrentVersion": "/^12\\.3\\.0$/",
        "enabled": False,
    }
    assert uv["matchCurrentVersion"] == "/^0\\.12\\.23$/"


def test_a_file_in_the_root_matches_the_lock_files_of_the_root_alone() -> None:
    accepted = Accepted(
        "", "lib", "1.0.0+local", "npm", datetime.date(2026, 1, 1), "Pinned."
    )
    rule = accepted.rule()
    assert rule["description"].startswith("osv-scanner.toml accepts every advisory")
    # Renovate takes "*" for every file, also those in folders, so the root is a
    # regular expression without a /.
    assert rule["matchFileNames"] == ["/^[^/]+$/"]
    assert rule["matchDatasources"] == ["npm"]
    assert rule["matchCurrentVersion"] == "/^1\\.0\\.0\\+local$/"
    nested = Accepted("a.b/c", "x", "1", "Go", datetime.date(2026, 1, 1), "r")
    assert nested.rule()["matchFileNames"] == ["/^a\\.b/c/[^/]+$/"]


def test_an_accepted_advisory_alone_and_an_override_that_ignores_nothing_get_no_rule(
    tmp_path: Path,
) -> None:
    (tmp_path / "osv-scanner.toml").write_text(
        """\
[[IgnoredVulns]]
id = "GHSA-g6cj-pr64-35w5"
ignoreUntil = 2026-11-22
reason = "Not shipped."

[[PackageOverrides]]
name = "lib"
ecosystem = "npm"
license.override = ["MIT"]

[[PackageOverrides]]
name = "other"
vulnerability.ignore = false
""",
        encoding="utf-8",
    )
    assert read(tmp_path, Path("osv-scanner.toml")) == ([], [])


@pytest.mark.parametrize(
    ("entry", "problem"),
    [
        (
            'version = "1.0.0"\necosystem = "PyPI"',
            "names no name: accept one version of one package",
        ),
        (
            'name = "lib"\nversion = " "\necosystem = "PyPI"',
            "names no version: accept one version of one package",
        ),
        (
            'name = "lib"\nversion = "1.0.0"',
            "names the ecosystem None, which is none of PyPI, npm,",
        ),
        (
            'name = "lib"\nversion = "1.0.0"\necosystem = "Hackage"',
            "names the ecosystem 'Hackage'",
        ),
    ],
)
def test_an_override_names_one_version_of_one_package_in_a_known_ecosystem(
    tmp_path: Path, entry: str, problem: str
) -> None:
    (tmp_path / "osv-scanner.toml").write_text(
        f"[[PackageOverrides]]\n{entry}\nvulnerability.ignore = true\n"
        'effectiveUntil = 2026-11-22\nreason = "Pinned."\n',
        encoding="utf-8",
    )
    accepted, problems = read(tmp_path, Path("osv-scanner.toml"))
    assert accepted == []
    assert len(problems) == 1
    assert problems[0].startswith("osv-scanner.toml: [[PackageOverrides]] 1 ")
    assert problem in problems[0]


def test_an_acceptance_has_a_reason_and_an_end(tmp_path: Path) -> None:
    (tmp_path / "osv-scanner.toml").write_text(
        '[[PackageOverrides]]\nname = "lib"\nversion = "1"\necosystem = "PyPI"\n'
        'vulnerability.ignore = true\neffectiveUntil = "soon"\nreason = ""\n',
        encoding="utf-8",
    )
    accepted, problems = read(tmp_path, Path("osv-scanner.toml"))
    assert accepted == []
    assert [problem.split(": ", 2)[1] for problem in problems] == [
        "[[PackageOverrides]] 1 has no effectiveUntil, a date such as 2026-11-22",
        "[[PackageOverrides]] 1 has no reason",
    ]


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        (
            'Ignored = 1\n[[PackageOverrides]]\nname = "a"\nversion.ignore = true\n'
            "vulnerability.skip = true\nlicense.allow = []\n"
            '[[IgnoredVulns]]\nid = "X"\nuntil = 2026-01-01\n',
            "OSV-Scanner ignores the whole file for the unknown key(s) Ignored, "
            "IgnoredVulns.until, PackageOverrides.license.allow, "
            "PackageOverrides.vulnerability.skip, and reports every advisory",
        ),
        (
            '[PackageOverrides]\nname = "a"\n',
            "OSV-Scanner can't read PackageOverrides, which is a list of tables, each "
            "written as [[PackageOverrides]]",
        ),
        ('IgnoredVulns = ["X"]\n', "OSV-Scanner can't read IgnoredVulns"),
        ("[[PackageOverrides]\n", "OSV-Scanner can't read it: "),
    ],
)
def test_a_file_that_osv_scanner_would_ignore_whole_is_a_problem(
    tmp_path: Path, text: str, problem: str
) -> None:
    # OSV-Scanner ignores such a file with a line in its log, and reports every
    # advisory that it accepts.
    (tmp_path / "osv-scanner.toml").write_text(text, encoding="utf-8")
    accepted, problems = read(tmp_path, Path("osv-scanner.toml"))
    assert accepted == []
    assert len(problems) == 1
    assert problems[0].startswith("osv-scanner.toml: ")
    assert problem in problems[0]


def test_a_file_that_is_no_text_is_a_problem(tmp_path: Path) -> None:
    (tmp_path / "osv-scanner.toml").write_bytes(b"\xff\xfe")
    _, problems = read(tmp_path, Path("osv-scanner.toml"))
    assert problems[0].startswith("osv-scanner.toml: OSV-Scanner can't read it: ")


@needs_git
def test_the_files_are_those_that_osv_scanner_reads(tmp_path: Path) -> None:
    root = repository(
        tmp_path,
        {
            "osv-scanner.toml": "",
            "stacks/php/osv-scanner.toml": "",
            "build/osv-scanner.toml": "",
            ".gitignore": "build/\n",
            "osv-scanner.toml.example": "",
        },
    )
    assert configs(root) == [
        Path("osv-scanner.toml"),
        Path("stacks/php/osv-scanner.toml"),
    ]


@needs_git
def test_the_command_fails_until_the_rules_are_those_of_the_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repository(tmp_path, {"stacks/home-assistant/osv-scanner.toml": PINNED})

    assert main(["advisories"], root=root) == 1
    out = capsys.readouterr().out
    assert out.startswith(
        ".github/renovate-accepted.json5 is missing for the versions that "
        "osv-scanner.toml accepts with every advisory, so Renovate would go on"
    )
    assert "python3 blueprint.py advisories --fix writes it" in out

    assert main(["advisories", "--fix"], root=root) == 0
    assert capsys.readouterr().out == (
        ".github/renovate-accepted.json5: the rules of Renovate are those of "
        "osv-scanner.toml now\nThe 2 version(s) that osv-scanner.toml accepts with "
        "every advisory have their rules of Renovate in "
        ".github/renovate-accepted.json5.\n"
    )
    written = (root / advisories.PRESET).read_text(encoding="utf-8")
    assert written.startswith("// The versions that an osv-scanner.toml")
    assert [rule["matchPackageNames"] for rule in rules(written)] == [
        ["pillow"],
        ["uv"],
    ]

    # A version that moved on, without the rule that follows it.
    path = root / "stacks/home-assistant/osv-scanner.toml"
    path.write_text(PINNED.replace("12.3.0", "13.0.0"), encoding="utf-8")
    assert main(["advisories"], root=root) == 1
    assert capsys.readouterr().out.startswith(
        ".github/renovate-accepted.json5 differs from the versions"
    )
    assert main(["advisories", "--fix"], root=root) == 0
    assert "13\\\\.0\\\\.0" in (root / advisories.PRESET).read_text(encoding="utf-8")
    capsys.readouterr()

    # Without an acceptance, the file has no rule, and a fix that has nothing to do
    # writes nothing.
    path.unlink()
    assert main(["advisories", "--fix"], root=root) == 0
    assert main(["advisories", "--fix"], root=root) == 0
    assert (
        capsys.readouterr().out.splitlines()[1:]
        == [
            "No osv-scanner.toml accepts a version with every advisory, and "
            ".github/renovate-accepted.json5 has no rule."
        ]
        * 2
    )
    assert rules((root / advisories.PRESET).read_text(encoding="utf-8")) == []


@needs_git
def test_the_problems_of_a_file_fail_the_command_after_its_fix(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repository(
        tmp_path,
        {
            "osv-scanner.toml": PINNED
            + '\n[[PackageOverrides]]\nname = "x"\nignore = true\n',
            advisories.PRESET: "{}\n",
        },
    )
    assert main(["advisories", "--fix"], root=root) == 1
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith(".github/renovate-accepted.json5: the rules")
    assert lines[1].startswith(
        "osv-scanner.toml: [[PackageOverrides]] 3 names no version"
    )
    # The rules of the two versions that it accepts are there all the same.
    outcome = check(root)
    assert outcome.in_step
    assert len(outcome.accepted) == 2


def test_the_command_needs_the_files_of_git(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["advisories"], root=tmp_path / "missing") == 2
    assert capsys.readouterr().err.startswith("blueprint.py: ")


# The files are those that Git knows, and the copy of the mutation tests has no Git.
@pytest.mark.mutation_unsafe
@needs_git
def test_the_blueprint_tells_renovate_what_its_osv_scanner_files_accept() -> None:
    outcome = check(ROOT)
    assert outcome.problems == []
    assert outcome.in_step
    # The test tools of Home Assistant, which pins them for the tests of every
    # integration: Pillow; the uv of Home Assistant 2026.10.4 has no advisory.
    assert {(entry.folder, entry.name) for entry in outcome.accepted} >= {
        ("stacks/home-assistant", "pillow"),
    }
