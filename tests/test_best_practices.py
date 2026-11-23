"""The bot that compares the public entry on bestpractices.dev with .bestpractices.json,
with saved copies of real entries (decision 1046)."""

from __future__ import annotations

import ast
import http.client
import io
import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Sequence
from email.message import Message
from pathlib import Path
from typing import Any

import pytest

from blueprint import best_practices
from blueprint.best_practices import (
    BODY_LIMIT,
    LABELS,
    LIMIT,
    MARKER,
    PROJECT_ANSWERS,
    SITE,
    TITLE,
    Difference,
    Unreachable,
    body,
    criteria_levels,
    differences,
    edit_links,
    entry_field,
    gone_files,
    keep_issue,
    project_number,
    read_entry,
)
from blueprint.cli import main
from blueprint.github import Api, Json

ROOT = Path(__file__).resolve().parent.parent
# Copies of the public entries of two projects, as https://www.bestpractices.dev/
# projects/<number>.json gave them on 2026-11-18 without a login, with only the id,
# the name, the repository and the answers, and the .bestpractices.json of each
# repository on main that day.
DATA = ROOT / "tests/data/bestpractices"
BLUEPRINT = "Dennis-Otto/repo-blueprint"
PAGER = "Dennis-Otto/repo-pager"
README = (
    "# Demo\n\n[![OpenSSF Best Practices]"
    "(https://www.bestpractices.dev/projects/15284/badge)]"
    "(https://www.bestpractices.dev/projects/15284)\n"
)
LEVELS = criteria_levels()


def saved(name: str) -> dict[str, Json]:
    loaded: dict[str, Json] = json.loads(
        (DATA / f"{name}.json").read_text(encoding="utf-8")
    )
    return loaded


def query(url: str) -> dict[str, str]:
    """The fields that a link proposes, each once."""
    pairs = urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query)
    names = [name for name, _ in pairs]
    assert len(names) == len(set(names)), url
    return dict(pairs)


def test_a_field_of_the_baseline_has_another_name_in_the_entry() -> None:
    assert entry_field("osps_br_07_01_justification") == "OSPS-BR-07.01_justification"
    assert entry_field("osps_ac_03_02_status") == "OSPS-AC-03.02_status"
    assert entry_field("contribution_status") == "contribution_status"


def test_the_number_comes_from_a_badge_of_either_series() -> None:
    assert project_number(README) == "15284"
    assert (
        project_number("![](https://www.bestpractices.dev/projects/7/baseline)") == "7"
    )
    assert project_number("# Demo\n\nNo badge.\n") is None


def test_each_criterion_has_the_level_of_its_edit_page() -> None:
    assert LEVELS["contribution"] == "passing"
    # A criterion that silver asks more strictly is the field of passing.
    assert LEVELS["contribution_requirements"] == "passing"
    assert LEVELS["osps_br_07_01"] == "baseline-1"
    assert set(LEVELS.values()) == set(best_practices.LEVELS)


def test_the_stale_entry_of_the_blueprint_is_found() -> None:
    # On 2026-11-18, after release 1.22.0 moved the secret scan into quick-checks.yml.
    answers = saved("repo-blueprint.answers")
    entry = saved("repo-blueprint.entry")

    found = differences(answers, entry, BLUEPRINT, ROOT, LEVELS)

    assert len(answers) == 216
    assert len(found) == 55
    # Every status matches; only the justifications drifted.
    assert all(item.name.endswith("_justification") for item in found)
    # The two answers that link the workflow that is gone.
    gone = {item.name: item.gone for item in found if item.gone}
    assert gone == {
        "no_leaked_credentials_justification": (".github/workflows/secret-scan.yml",),
        "osps_br_07_01_justification": (".github/workflows/secret-scan.yml",),
    }
    secret = next(item for item in found if item.name == "osps_br_07_01_justification")
    assert "secret-scan.yml" in secret.found
    assert "quick-checks.yml" in secret.expected
    assert secret.level == "baseline-1"
    assert secret.forced


def test_the_answers_that_the_file_leaves_out_are_never_reported() -> None:
    answers = saved("repo-blueprint.answers")
    entry = saved("repo-blueprint.entry")
    # The entry answers what only the project knows, such as its user guides.
    assert entry["OSPS-DO-01.01_status"] == "Met"
    assert "osps_do_01_01_status" not in answers

    found = differences(answers, entry, BLUEPRINT, ROOT, LEVELS)

    assert {item.name for item in found} <= set(answers)


def test_the_links_of_a_long_level_are_split() -> None:
    # repo-pager differed in 96 answers, the passing level alone in 34.
    answers = saved("repo-pager.answers")
    found = differences(answers, saved("repo-pager.entry"), PAGER, ROOT, LEVELS)

    links = edit_links("16429", found)

    assert len(found) == 96
    assert [link.label for link in links] == [
        "passing, part 1 of 2",
        "passing, part 2 of 2",
        "silver",
        "baseline-1",
        "baseline-2",
        "baseline-3",
    ]
    # Every answer is in exactly one link, of the edit page of its own level, and each
    # link stays below the length that the site takes.
    names = [name for link in links for name in link.names]
    assert sorted(names) == sorted(item.name for item in found)
    by_name = {item.name: item for item in found}
    for link in links:
        assert len(link.url) <= LIMIT, link.label
        assert link.url.startswith(f"{SITE}/en/projects/16429/{link.level}/edit?")
        proposed = query(link.url)
        overrides = proposed.pop("overrides", "")
        assert set(proposed) == set(link.names)
        assert {by_name[name].level for name in proposed} == {link.level}
        assert all(value == by_name[name].expected for name, value in proposed.items())
        # overrides= forces exactly the answers that the entry gives otherwise.
        assert overrides.split(",") == [
            name for name in link.names if by_name[name].forced
        ]
    # A status and its justification stay in the same link.
    for link in links:
        criteria = {name.rsplit("_", 1)[0] for name in link.names}
        assert not [
            other
            for other in links
            if other is not link
            and criteria & {name.rsplit("_", 1)[0] for name in other.names}
        ]


def test_a_level_that_fits_has_one_link() -> None:
    found = differences(
        saved("repo-blueprint.answers"),
        saved("repo-blueprint.entry"),
        BLUEPRINT,
        ROOT,
        LEVELS,
    )
    links = edit_links("15284", found)

    baseline = [link for link in links if link.level == "baseline-1"]
    assert [link.label for link in baseline] == ["baseline-1"]
    assert query(baseline[0].url) == {
        "osps_br_07_01_justification": next(
            item.expected for item in found if item.name == baseline[0].names[0]
        ),
        "overrides": "osps_br_07_01_justification",
    }


def answer(
    name: str, expected: str, found: str, level: str | None = "passing"
) -> Difference:
    return Difference(name, level, expected, found)


def test_only_an_answer_that_the_entry_gives_is_forced() -> None:
    found = [
        answer("contribution_status", "Met", "?"),
        answer("contribution_justification", "CONTRIBUTING.md", ""),
        answer("license_location_status", "Met", "Unmet"),
        answer("floss_license_justification", "MIT-0", "MIT"),
    ]

    (link,) = edit_links("7", found)

    assert query(link.url)["overrides"] == (
        "license_location_status,floss_license_justification"
    )
    assert "overrides=license_location_status%2Cfloss_license_justification" in link.url
    # Nothing to force: the link proposes only.
    (fills,) = edit_links("7", found[:2])
    assert "overrides" not in query(fills.url)


def test_one_criterion_longer_than_the_limit_still_gets_its_link() -> None:
    found = [
        answer("contribution_justification", "a" * 50, "b"),
        answer("floss_license_justification", "c" * 50, "d"),
    ]

    links = edit_links("7", found, limit=60)

    assert [link.names for link in links] == [
        ("contribution_justification",),
        ("floss_license_justification",),
    ]


def test_the_file_and_the_entry_compare_as_the_site_reads_them(tmp_path: Path) -> None:
    answers: dict[str, Json] = {
        "$schema": "a key that is no answer",
        "contribution_status": "met",
        "contribution_justification": "  CONTRIBUTING.md ",
        # The file doesn't know: it proposes nothing.
        "floss_license_status": "?",
        "license_location_status": "Met",
        "license_location_justification": 7,
        "osps_br_07_01_status": "Met",
    }
    entry: dict[str, Json] = {
        "contribution_status": "Met",
        "contribution_justification": "CONTRIBUTING.md",
        "floss_license_status": "Met",
        "license_location_status": None,
        "OSPS-BR-07.01_status": "Met",
    }

    found = differences(answers, entry, "o/r", tmp_path, LEVELS)

    assert found == [Difference("license_location_status", "passing", "Met", "")]
    assert not found[0].forced


def test_a_link_into_the_repository_is_checked_against_the_checkout(
    tmp_path: Path,
) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "SECURITY.md").write_text("Report it.\n", encoding="utf-8")
    text = (
        "See <https://github.com/O/R/blob/main/SECURITY.md>, "
        "https://github.com/o/r/tree/main/docs. "
        "https://github.com/o/r/blob/v1/gone%20file.md#part, "
        "(https://github.com/o/r/blob/main/old.yml), again "
        "https://github.com/o/r/blob/main/old.yml?plain=1 and another repository: "
        "https://github.com/o/other/blob/main/missing.md"
    )

    assert gone_files(text, "o/r", tmp_path) == ("gone file.md", "old.yml")


def test_the_issue_gives_the_links_the_reasons_and_the_texts() -> None:
    found = [
        Difference(
            "osps_br_07_01_justification",
            "baseline-1",
            "The secret scan of Quick checks.\nSecond line.\n\nThird.",
            "https://github.com/o/r/blob/main/secret-scan.yml",
            ("secret-scan.yml",),
        ),
        answer("contribution_justification", "CONTRIBUTING.md", ""),
        answer("license_location_status", "Met", "Unmet"),
        answer("floss_license_justification", "MIT-0", "MIT"),
        answer("unknown_justification", "Something new", "", level=None),
    ]

    text = body("7", found, edit_links("7", found))

    assert text.startswith(MARKER)
    assert "[project 7](https://www.bestpractices.dev/projects/7)" in text
    assert "in 5 answer(s)" in text
    assert (
        "- [passing](https://www.bestpractices.dev/en/projects/7/passing/edit?" in text
    )
    assert (
        "- [baseline-1](https://www.bestpractices.dev/en/projects/7/baseline-1/" in text
    )
    assert "No edit page takes these answers" in text
    assert (
        "- `osps_br_07_01_justification` (baseline-1) links `secret-scan.yml`, which "
        "the repository no longer has"
    ) in text
    assert "- `contribution_justification` (passing) is empty on the site" in text
    assert "- `license_location_status` (passing) is Unmet on the site" in text
    assert "- `floss_license_justification` (passing) says something else" in text
    assert "- `unknown_justification` (no level) is empty on the site" in text
    assert "> The secret scan of Quick checks.\n> Second line.\n>\n> Third." in text
    assert "<details>" in text


def test_a_long_issue_leaves_the_texts_to_its_links() -> None:
    found = [
        answer(f"criterion{index}_justification", "x" * 600, "y") for index in range(60)
    ]

    text = body("7", found, edit_links("7", found))

    assert len(text) <= BODY_LIMIT
    assert "<details>" not in text
    assert "The texts to enter are left out" in text
    assert "- `criterion59_justification` (passing)" in text
    assert "follow" not in text


def test_an_issue_too_long_for_its_links_gives_the_rest_in_the_next_run() -> None:
    found = [
        answer(f"criterion{index}_justification", "x" * 1000, "y")
        for index in range(70)
    ]
    links = edit_links("7", found)

    text = body("7", found, links)

    assert len(text) <= BODY_LIMIT
    shown = text.count("- [passing, part ")
    assert 0 < shown < len(links)
    assert (
        f"{len(links) - shown} more link(s) follow in the next weekly run, once these "
        "are saved."
    ) in text


class Site:
    """bestpractices.dev, with the entry that it gives, and every request."""

    def __init__(self, answer: object) -> None:
        self.answer = answer
        self.requests: list[urllib.request.Request] = []

    def __call__(self, request: urllib.request.Request, timeout: float) -> Any:
        assert timeout == 30
        self.requests.append(request)
        if isinstance(self.answer, BaseException):
            raise self.answer
        if isinstance(self.answer, bytes):
            return io.BytesIO(self.answer)
        return io.BytesIO(json.dumps(self.answer).encode())


def test_the_entry_is_read_once_without_a_login() -> None:
    site = Site({"id": 15284})

    assert read_entry("15284", site) == {"id": 15284}
    (request,) = site.requests
    assert request.full_url == "https://www.bestpractices.dev/projects/15284.json"
    assert request.get_method() == "GET"
    assert request.get_header("Accept") == "application/json"
    assert "Authorization" not in request.headers


@pytest.mark.parametrize(
    "answer",
    [
        urllib.error.HTTPError(
            "https://www.bestpractices.dev/projects/7.json",
            503,
            "Service Unavailable",
            Message(),
            io.BytesIO(b"busy"),
        ),
        urllib.error.URLError("no route"),
        b"<html>maintenance</html>",
        b"[]",
        http.client.IncompleteRead(b""),
    ],
    ids=["error", "unreachable", "no json", "no entry", "cut off"],
)
def test_a_site_that_gives_no_entry_is_unreachable(answer: object) -> None:
    with pytest.raises(Unreachable, match=r"projects/7\.json"):
        read_entry("7", Site(answer))


class FakeClient:
    """GitHub with a list of issues, and the changes it was asked for."""

    def __init__(self, issues: list[Json]) -> None:
        self.issues = issues
        self.changes: list[tuple[str, str, Json]] = []

    def get_all(self, path: str) -> list[Json]:
        assert path == f"repos/{BLUEPRINT}/issues?state=open"
        return self.issues

    def patch(self, path: str, body: Json) -> None:
        self.changes.append(("PATCH", path, body))

    def post(self, path: str, body: Json) -> None:
        self.changes.append(("POST", path, body))


def repository(root: Path, readme: str = README, answers: str = "") -> Path:
    """A checkout with a README and the .bestpractices.json of the blueprint on
    2026-11-18, and no other file."""
    (root / "README.md").write_text(readme, encoding="utf-8")
    (root / ".bestpractices.json").write_text(
        answers or (DATA / "repo-blueprint.answers.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return root


def test_a_stale_entry_opens_the_issue(tmp_path: Path) -> None:
    client = FakeClient(
        [
            {"number": 3, "body": "another issue"},
            {"number": 4, "pull_request": {}, "body": MARKER},
        ]
    )
    site = Site(saved("repo-blueprint.entry"))

    outcome = keep_issue(client, BLUEPRINT, repository(tmp_path), opener=site)

    assert len(site.requests) == 1
    assert len(outcome.found) == 55
    ((method, path, sent),) = client.changes
    assert (method, path) == ("POST", f"repos/{BLUEPRINT}/issues")
    assert sent["title"] == TITLE
    assert sent["labels"] == LABELS
    assert sent["body"].startswith(MARKER)
    assert "/en/projects/15284/passing/edit?" in sent["body"]
    assert outcome.summary[-1] == "Opened an issue with the links of the edit pages."
    assert outcome.warnings == [
        "::warning title=The entry on bestpractices.dev is stale::55 answer(s) of "
        ".bestpractices.json differ from the entry of project 15284."
    ]


def test_the_issue_follows_the_entry(tmp_path: Path) -> None:
    root = repository(tmp_path)
    entry = saved("repo-blueprint.entry")
    client = FakeClient([{"number": 9, "body": f"{MARKER}\nolder"}])

    keep_issue(client, BLUEPRINT, root, opener=Site(entry))

    ((method, path, sent),) = client.changes
    assert (method, path) == ("PATCH", f"repos/{BLUEPRINT}/issues/9")
    # The same text again changes nothing.
    again = FakeClient([{"number": 9, "body": sent["body"]}])
    outcome = keep_issue(again, BLUEPRINT, root, opener=Site(entry))
    assert again.changes == []
    assert outcome.summary[-1] == "#9 names them already."


def test_the_issue_closes_once_the_entry_gives_every_answer(tmp_path: Path) -> None:
    answers = saved("repo-blueprint.answers")
    current = {
        best_practices.entry_field(name): value for name, value in answers.items()
    }
    # What the maintainer answered on the site alone stays and counts for nothing.
    current["OSPS-DO-01.01_status"] = "Met"
    client = FakeClient([{"number": 9, "body": MARKER}])

    outcome = keep_issue(client, BLUEPRINT, repository(tmp_path), opener=Site(current))

    assert client.changes == [
        (
            "PATCH",
            f"repos/{BLUEPRINT}/issues/9",
            {"state": "closed", "state_reason": "completed"},
        )
    ]
    assert outcome.summary == [
        "The entry of project 15284 gives every answer of .bestpractices.json.",
        "Closed #9.",
    ]
    assert outcome.warnings == []
    # Nothing differs and no issue is open: nothing to do.
    quiet = FakeClient([])
    keep_issue(quiet, BLUEPRINT, repository(tmp_path), opener=Site(current))
    assert quiet.changes == []


@pytest.mark.parametrize(
    ("issues", "entry", "said"),
    [
        ([], "stale", "Would open an issue with the links of the edit pages."),
        ([{"number": 9, "body": MARKER}], "stale", "Would update #9."),
        ([{"number": 9, "body": MARKER}], "current", "Would close #9."),
    ],
)
def test_the_dry_run_changes_nothing(
    tmp_path: Path, issues: list[Json], entry: str, said: str
) -> None:
    answers = saved("repo-blueprint.answers")
    given = (
        saved("repo-blueprint.entry")
        if entry == "stale"
        else {
            best_practices.entry_field(name): value for name, value in answers.items()
        }
    )
    client = FakeClient(issues)

    outcome = keep_issue(
        client, BLUEPRINT, repository(tmp_path), opener=Site(given), dry_run=True
    )

    assert client.changes == []
    assert outcome.summary[-1] == said


def test_a_repository_without_the_badge_asks_nothing(tmp_path: Path) -> None:
    site = Site({})
    client = FakeClient([{"number": 9, "body": MARKER}])

    outcome = keep_issue(
        client, BLUEPRINT, repository(tmp_path, readme="# Demo\n"), opener=site
    )
    (tmp_path / "README.md").unlink()
    without = keep_issue(client, BLUEPRINT, tmp_path, opener=site)

    assert site.requests == []
    assert client.changes == []
    assert (
        outcome.summary
        == without.summary
        == ["The README shows no badge of bestpractices.dev: nothing to compare."]
    )


def test_a_repository_without_the_file_asks_nothing(tmp_path: Path) -> None:
    root = repository(tmp_path)
    (root / ".bestpractices.json").unlink()
    site = Site({})

    outcome = keep_issue(FakeClient([]), BLUEPRINT, root, opener=site)

    assert site.requests == []
    assert outcome.summary == [
        "The repository has no .bestpractices.json: nothing to compare."
    ]


def test_a_site_that_doesnt_answer_leaves_the_issue_as_it_is(tmp_path: Path) -> None:
    client = FakeClient([{"number": 9, "body": MARKER}])

    outcome = keep_issue(
        client,
        BLUEPRINT,
        repository(tmp_path),
        opener=Site(urllib.error.URLError("timed out")),
    )

    assert client.changes == []
    (warning,) = outcome.warnings
    assert warning.startswith("::warning title=bestpractices.dev didn't answer::")
    assert "the issue stays as it is" in outcome.summary[0]


class Runner:
    """The GitHub CLI with an answer for the list of issues, and every change."""

    def __init__(self, issues: list[Json]) -> None:
        self.issues = issues
        self.sent: list[tuple[str, str]] = []

    def __call__(
        self, arguments: Sequence[str], payload: str | None
    ) -> subprocess.CompletedProcess[str]:
        if "--paginate" in arguments:
            return subprocess.CompletedProcess([], 0, json.dumps([self.issues]), "")
        self.sent.append((arguments[3], arguments[4]))
        return subprocess.CompletedProcess(
            arguments, 0, 'HTTP/2.0 201 Created\r\n\r\n{"number": 9}', ""
        )


@pytest.mark.parametrize("dry_run", [False, True])
def test_the_command_compares_and_keeps_the_issue(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    dry_run: bool,
) -> None:
    site = Site(saved("repo-blueprint.entry"))
    monkeypatch.setattr(urllib.request, "urlopen", site)
    runner = Runner([])
    command = ["--repo", BLUEPRINT, "best-practices"] + (
        ["--dry-run"] if dry_run else []
    )

    code = main(command, api=Api(runner), root=repository(tmp_path))

    printed = capsys.readouterr()
    assert code == 0
    assert len(site.requests) == 1
    assert runner.sent == ([] if dry_run else [("POST", f"repos/{BLUEPRINT}/issues")])
    assert "::warning title=The entry on bestpractices.dev is stale::" in printed.err
    lines = printed.out.splitlines()
    assert lines[0] == f"The entry of {BLUEPRINT} on bestpractices.dev" + (
        " (a dry run: nothing changed):" if dry_run else ":"
    )
    assert (
        "- `osps_br_07_01_justification` (baseline-1) links "
        "`.github/workflows/secret-scan.yml`, which the repository no longer has"
    ) in lines
    assert lines[-1].endswith("an issue with the links of the edit pages.")


# The answers that only a repository can give, in .github/bestpractices.project.toml
# (decision 1088).
OWN = (
    "pytest, and end-to-end tests in Docker: "
    "https://github.com/Dennis-Otto/repo-blueprint/blob/main/tests/e2e/run.sh"
)
EMPTY = (ROOT / "template" / PROJECT_ANSWERS).read_text(encoding="utf-8")


def with_own_answers(root: Path, text: str) -> Path:
    """The checkout with its project file."""
    (root / ".github").mkdir(exist_ok=True)
    (root / PROJECT_ANSWERS).write_text(text, encoding="utf-8", newline="\n")
    return root


def current_entry() -> dict[str, Json]:
    """The entry that gives every answer of the blueprint's file of 2026-11-18."""
    return {
        entry_field(name): value
        for name, value in saved("repo-blueprint.answers").items()
    }


def proposals(text: str, level: str) -> dict[str, str]:
    """The fields that the link of a level in the text of an issue proposes."""
    (link,) = re.findall(rf"\((https://\S+/{level}/edit\?[^)]+)\)", text)
    return query(link)


def test_an_answer_of_the_project_file_replaces_the_one_of_the_file(
    tmp_path: Path,
) -> None:
    root = with_own_answers(
        repository(tmp_path), f'{EMPTY}\n[test]\njustification = "{OWN}"\n'
    )
    # The file that the template's words link.
    (root / "scripts").mkdir()
    (root / "scripts/check.sh").write_text("pytest\n", encoding="utf-8")
    template = saved("repo-blueprint.answers")["test_justification"]
    # The entry gives the blueprint's words, as after the links of #1075 were saved.
    entry = current_entry()
    client = FakeClient([])

    outcome = keep_issue(client, BLUEPRINT, root, opener=Site(entry))

    assert outcome.found == [
        Difference("test_justification", "passing", OWN, str(template), (), True)
    ]
    ((method, path, sent),) = client.changes
    assert (method, path) == ("POST", f"repos/{BLUEPRINT}/issues")
    # The link forces the project's words over those of the template.
    assert proposals(sent["body"], "passing") == {
        "test_justification": OWN,
        "overrides": "test_justification",
    }
    assert (
        "- `test_justification` (passing, the project's own in "
        "`.github/bestpractices.project.toml`) says something else on the site"
    ) in sent["body"]
    assert (
        "differs from `.bestpractices.json` and `.github/bestpractices."
        in (sent["body"])
    )
    assert "Change them in that file, not on the site" in sent["body"]
    assert "the answers that neither file gives" in sent["body"]
    assert outcome.warnings == [
        "::warning title=The entry on bestpractices.dev is stale::1 answer(s) of "
        ".bestpractices.json and .github/bestpractices.project.toml differ from the "
        "entry of project 15284."
    ]

    # Once the entry gives the project's own answer, the issue closes.
    entry["test_justification"] = OWN
    closing = FakeClient([{"number": 9, "body": sent["body"]}])
    done = keep_issue(closing, BLUEPRINT, root, opener=Site(entry))
    assert closing.changes == [
        (
            "PATCH",
            f"repos/{BLUEPRINT}/issues/9",
            {"state": "closed", "state_reason": "completed"},
        )
    ]
    assert done.summary == [
        "The entry of project 15284 gives every answer of .bestpractices.json and "
        ".github/bestpractices.project.toml.",
        "Closed #9.",
    ]


@pytest.mark.parametrize(
    ("found", "forced"), [("", None), ("Unmet", "security_review_status")]
)
def test_a_criterion_that_only_the_project_file_answers_gets_its_own_level(
    tmp_path: Path, found: str, forced: str | None
) -> None:
    root = with_own_answers(
        repository(tmp_path),
        '[security_review]\nstatus = "Met"\njustification = "A review of 2026."\n',
    )
    entry = current_entry()
    if found:
        entry["security_review_status"] = found
        entry["security_review_justification"] = "A review of 2025."
    client = FakeClient([])

    outcome = keep_issue(client, BLUEPRINT, root, opener=Site(entry))

    assert [(item.name, item.level, item.own) for item in outcome.found] == [
        ("security_review_status", "gold", True),
        ("security_review_justification", "gold", True),
    ]
    ((_, _, sent),) = client.changes
    fields = proposals(sent["body"], "gold")
    assert fields.pop("security_review_status") == "Met"
    assert fields.pop("security_review_justification") == "A review of 2026."
    # Only an answer that the entry gives is forced.
    assert fields.get("overrides") == (
        None if forced is None else f"{forced},security_review_justification"
    )
    assert "/passing/edit?" not in sent["body"]


def test_without_answers_of_its_own_a_repository_gets_the_same_issue(
    tmp_path: Path,
) -> None:
    # The project file as the template renders it, and none at all.
    (tmp_path / "rendered").mkdir()
    (tmp_path / "missing").mkdir()
    rendered = with_own_answers(repository(tmp_path / "rendered"), EMPTY)
    missing = repository(tmp_path / "missing")
    issues: list[list[tuple[str, str, Json]]] = []
    for root in (rendered, missing):
        client = FakeClient([])
        keep_issue(client, BLUEPRINT, root, opener=Site(saved("repo-blueprint.entry")))
        issues.append(client.changes)

    assert issues[0] == issues[1]
    ((_, _, sent),) = issues[0]
    assert ".github/bestpractices.project.toml" not in sent["body"]
    assert "differs from `.bestpractices.json` in 55 answer(s)" in sent["body"]


def test_a_project_file_that_is_no_toml_leaves_the_issue_as_it_is(
    tmp_path: Path,
) -> None:
    root = with_own_answers(repository(tmp_path), "[test\n")
    site = Site(saved("repo-blueprint.entry"))
    client = FakeClient([{"number": 9, "body": MARKER}])

    outcome = keep_issue(client, BLUEPRINT, root, opener=site)

    assert site.requests == []
    assert client.changes == []
    assert outcome.summary[0].startswith(
        ".github/bestpractices.project.toml is no TOML"
    )
    assert outcome.summary[0].endswith(
        "so the issue stays as it is until the file passes blueprint.py "
        "best-practices --verify."
    )
    assert outcome.warnings[0].startswith(
        "::warning title=.github/bestpractices.project.toml is no TOML::"
    )


# It reads the blueprint's own files, which the copy of the mutation tests lacks.
@pytest.mark.mutation_unsafe
def test_the_answers_are_the_file_and_the_project_file() -> None:
    root = ROOT
    given, own = best_practices.answers(root)
    template = json.loads((ROOT / ".bestpractices.json").read_text(encoding="utf-8"))

    # The blueprint answers six criteria as only it can (decision 1088): it keeps the
    # tools of its website in stacks/docs/, from where every repository gets them as
    # .github/docs-requirements.txt (issue 1087), and its pyproject.toml lists no
    # dependencies, which its blueprint/ takes besides the standard library (issue 1109).
    assert own == {
        "external_dependencies_justification",
        "osps_qa_02_01_justification",
        "installation_development_quick_justification",
        "test_justification",
        "test_continuous_integration_justification",
        "version_tags_signed_justification",
    }
    assert set(given) == set(template)
    for name in own:
        assert given[name] != template[name]
    assert "v0.6.0" in str(given["version_tags_signed_justification"])
    quick = "installation_development_quick_justification"
    assert str(given[quick]) == str(template[quick]).replace(
        ".github/docs-requirements.txt", "stacks/docs/requirements-docs.txt"
    )
    assert (ROOT / "stacks/docs/requirements-docs.txt").is_file()
    assert not (ROOT / ".github/docs-requirements.txt").exists()
    assert best_practices.verify(ROOT) == best_practices.Verification([], [], 6)


# It reads the blueprint's own files, which the copy of the mutation tests lacks.
@pytest.mark.mutation_unsafe
def test_the_blueprint_names_what_its_code_takes_besides_the_standard_library() -> None:
    given, _ = best_practices.answers(ROOT)
    taken: dict[str, set[str]] = {}
    for path in [ROOT / "blueprint.py", *sorted((ROOT / "blueprint").rglob("*.py"))]:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
                names = [node.module]
            else:
                continue
            for name in names:
                top = name.partition(".")[0]
                if top not in sys.stdlib_module_names and top != "blueprint":
                    taken.setdefault(top, set()).add(path.relative_to(ROOT).as_posix())

    # Each package that the code imports besides the standard library is one that the
    # answers name, in the file that takes it, and nothing else (issue 1109).
    assert taken == {
        "PIL": {"blueprint/screenshots.py"},
        "yaml": {"blueprint/website.py"},
    }
    for criterion in ("external_dependencies", "osps_qa_02_01"):
        words, _, link = str(given[f"{criterion}_justification"]).rpartition(": ")
        assert "pyproject.toml" not in words
        assert "the screenshot bot, which takes Pillow from" in words
        assert "one step of the website, which takes PyYAML" in words
        named = re.findall(r"[\w/.-]+\.(?:in|txt)\b", words)
        assert named == [
            "stacks/screenshots/requirements.in",
            "requirements-dev.in",
            "requirements-dev.txt",
        ]
        for name in named:
            assert (ROOT / name).is_file(), name
        assert link == (
            "https://github.com/Dennis-Otto/repo-blueprint/blob/main/requirements-dev.in"
        )
    assert "pillow==" in (ROOT / "stacks/screenshots/requirements.in").read_text(
        encoding="utf-8"
    )


def test_what_is_no_answer_of_the_project_file_stays_out(tmp_path: Path) -> None:
    # What --verify fails on never reaches a link: a key that is no table, and a
    # status that is no text.
    root = with_own_answers(
        repository(tmp_path),
        'security_review = "Met"\n[test]\nstatus = 1\njustification = "Ours."\n',
    )

    given, own = best_practices.answers(root)

    assert own == {"test_justification"}
    assert given["test_justification"] == "Ours."
    assert given["test_status"] == "Met"
    assert "security_review_status" not in given


def test_what_verify_fails_on_never_keeps_the_issue_open(tmp_path: Path) -> None:
    # A criterion that the site doesn't know, and a status for one that
    # .bestpractices.json answers, as on main after a check that was skipped.
    root = with_own_answers(
        repository(tmp_path),
        '[no_such_criterion]\nstatus = "Met"\njustification = "x"\n'
        '[test]\nstatus = "Unmet"\n',
    )

    given, own = best_practices.answers(root)

    assert own == set()
    assert given["test_status"] == "Met"
    assert not any(name.startswith("no_such_criterion") for name in given)
    client = FakeClient([{"number": 9, "body": MARKER}])
    keep_issue(client, BLUEPRINT, root, opener=Site(current_entry()))
    assert client.changes == [
        (
            "PATCH",
            f"repos/{BLUEPRINT}/issues/9",
            {"state": "closed", "state_reason": "completed"},
        )
    ]


# A checkout for --verify: its .bestpractices.json answers test and contribution, and
# it has the files and the heading that the answers link.
REPO = "https://github.com/o/r/blob/main"
TEMPLATE: dict[str, Json] = {
    "$schema": "a key that is no answer",
    "test_status": "Met",
    "test_justification": f"pytest: {REPO}/scripts/check.sh",
    "contribution_status": "Met",
    "contribution_justification": f"The guide: {REPO}/CONTRIBUTING.md",
}


def verifiable(root: Path, own: str, template: dict[str, Json] | None = None) -> Path:
    """A checkout with its README, .bestpractices.json and project file."""
    (root / "README.md").write_text(README, encoding="utf-8")
    (root / ".bestpractices.json").write_text(
        json.dumps(TEMPLATE if template is None else template), encoding="utf-8"
    )
    (root / "scripts").mkdir()
    (root / "scripts/check.sh").write_text("pytest\n", encoding="utf-8")
    (root / "CONTRIBUTING.md").write_text("# Guide\n\n## Tests\n", encoding="utf-8")
    return with_own_answers(root, own)


@pytest.mark.parametrize(
    ("own", "said"),
    [
        (
            '[no_such_criterion]\nstatus = "Met"\njustification = "x"\n',
            "[no_such_criterion] is no criterion of bestpractices.dev",
        ),
        (
            'security_review = "Met"\n',
            "[security_review] is no table with status and justification.",
        ),
        (
            '[security_review]\nstatus = "Met"\njustification = "x"\nlevel = "gold"\n',
            "[security_review] has the key level: a table gives only status and "
            "justification.",
        ),
        (
            '[security_review]\nstatus = true\njustification = "x"\n',
            "[security_review]: status is no string.",
        ),
        (
            f'[test]\nstatus = "Unmet"\njustification = "Ours: {REPO}/scripts/check.sh"\n',
            "[test] gives a status, which .bestpractices.json gives for it",
        ),
        ("[test]\n", "[test] gives no justification."),
        (
            '[security_review]\nstatus = "Met"\n',
            "[security_review] needs both status and justification, as "
            ".bestpractices.json doesn't answer it.",
        ),
        (
            '[security_review]\njustification = "A review."\n',
            "[security_review] needs both status and justification",
        ),
        (
            '[security_review]\nstatus = "Yes"\njustification = "x"\n',
            "[security_review]: the status is Met, Unmet or N/A, not 'Yes'.",
        ),
        (
            '[security_review]\nstatus = "N/A"\njustification = "x"\n',
            "[security_review]: bestpractices.dev doesn't take N/A for it.",
        ),
        (
            '[documentation_architecture]\nstatus = "Met"\n'
            'justification = "In the README."\n',
            "[documentation_architecture]: Met needs a link that shows it.",
        ),
        (
            f'[test]\njustification = "pytest and Docker: {REPO}/tests/e2e/run.sh"\n',
            "[test] links tests/e2e/run.sh, which the repository doesn't have.",
        ),
        (
            f'[contribution]\njustification = "Ours: {REPO}/CONTRIBUTING.md#gone."\n',
            "[contribution] links CONTRIBUTING.md#gone, a heading that the file "
            "doesn't have.",
        ),
        (
            f'[contribution]\njustification = "Ours: {REPO}/GONE.md#part"\n',
            "[contribution] links GONE.md, which the repository doesn't have.",
        ),
        (
            '[security_review]\nstatus = "Met"\n'
            'justification = "See http://example.com/review"\n',
            "[security_review] links http://example.com/review: a link uses https.",
        ),
        (
            '[security_review]\nstatus = "Met"\njustification = "' + "x" * 8000 + '"\n',
            "[security_review]: the justification is too long for one link of the "
            "issue, which takes 8000 characters: ",
        ),
        (
            f'[test]\njustification = " pytest: {REPO}/scripts/check.sh "\n',
            "[test] repeats the justification of .bestpractices.json",
        ),
        ("[test\n", ".github/bestpractices.project.toml is no TOML: "),
    ],
    ids=[
        "unknown criterion",
        "no table",
        "other key",
        "no string",
        "status of the file",
        "nothing",
        "no justification",
        "no status",
        "unknown status",
        "N/A",
        "no link",
        "gone file",
        "gone heading",
        "gone Markdown file",
        "http",
        "too long",
        "repeated",
        "no TOML",
    ],
)
def test_the_check_of_the_project_file_names_each_problem(
    tmp_path: Path, own: str, said: str
) -> None:
    outcome = best_practices.verify(verifiable(tmp_path, own))

    assert [problem for problem in outcome.problems if said in problem], (
        outcome.problems
    )
    assert outcome.removed == []


def test_the_check_of_the_project_file_passes_what_the_site_takes(
    tmp_path: Path,
) -> None:
    own = (
        f'{EMPTY}\n[test]\njustification = "pytest and Docker: {REPO}/scripts/check.sh '
        f'and {REPO}/CONTRIBUTING.md#tests."\n\n'
        # A link to a heading that GitHub draws itself, and one to another site.
        f'[contribution]\njustification = """\nOurs: {REPO}/CONTRIBUTING.md#readme\n'
        'and https://example.com/guide."""\n\n'
        '[documentation_architecture]\nstatus = "N/A"\njustification = "No design."\n\n'
        '[security_review]\nstatus = "Unmet"\njustification = "None yet."\n'
    )
    root = verifiable(tmp_path, own)

    assert best_practices.verify(root) == best_practices.Verification([], [], 4)
    # Without .bestpractices.json nothing names the repository, and without the badge
    # a link counts with a number of five digits.
    (root / ".bestpractices.json").unlink()
    (root / "README.md").unlink()
    outcome = best_practices.verify(root)
    assert all(
        "needs both status and justification" in item for item in outcome.problems
    )
    assert len(outcome.problems) == 2
    # Without the project file, and with the one that the template renders, it passes.
    (root / PROJECT_ANSWERS).unlink()
    assert best_practices.verify(root) == best_practices.Verification([])
    with_own_answers(root, EMPTY)
    assert best_practices.verify(root) == best_practices.Verification([], [], 0)


def test_a_link_to_a_heading_counts_as_github_finds_it(tmp_path: Path) -> None:
    # A heading with an umlaut, as a browser copies its link, one in capitals, and a
    # repeated heading, which GitHub numbers from -1 on.
    links = (
        f"{REPO}/CONTRIBUTING.md#pr%C3%BCfungen-und-der-pr-coach, "
        f"{REPO}/CONTRIBUTING.md#Tests and {REPO}/CONTRIBUTING.md#tests-1"
    )
    root = verifiable(tmp_path, f'[contribution]\njustification = "Ours: {links}."\n')
    (root / "CONTRIBUTING.md").write_text(
        "# Guide\n\n## Prüfungen und der PR-Coach\n\n## Tests\n\n## Tests\n",
        encoding="utf-8",
    )

    assert best_practices.verify(root) == best_practices.Verification([], [], 1)
    with_own_answers(
        root,
        f'[contribution]\njustification = "Ours: {REPO}/CONTRIBUTING.md#tests-2"\n',
    )
    assert best_practices.verify(root).problems == [
        ".github/bestpractices.project.toml: [contribution] links "
        "CONTRIBUTING.md#tests-2, a heading that the file doesn't have."
    ]


def test_the_fix_removes_only_what_repeats_the_file(tmp_path: Path) -> None:
    own = (
        "# The answers of this repository.\n"
        "\n"
        "[test]\n"
        'status = "Met"\n'
        "# The words of the blueprint, on two lines.\n"
        'justification = """\n'
        f'pytest: {REPO}/scripts/check.sh"""\n'
        "\n"
        "[contribution]  # its own words\n"
        '"status" = "Met"\n'
        f'justification = "Our own guide: {REPO}/CONTRIBUTING.md#tests"\n'
        "\n"
        "[security_review]\n"
        'status = "Met"\n'
        'justification = "A review of 2026."\n'
    )
    root = verifiable(tmp_path, own)

    outcome = best_practices.verify(root, fix=True)

    assert outcome == best_practices.Verification(
        [],
        ["status of [test]", "justification of [test]", "status of [contribution]"],
        2,
    )
    assert (root / PROJECT_ANSWERS).read_text(encoding="utf-8") == (
        "# The answers of this repository.\n"
        "\n"
        "# The words of the blueprint, on two lines.\n"
        "\n"
        "[contribution]  # its own words\n"
        f'justification = "Our own guide: {REPO}/CONTRIBUTING.md#tests"\n'
        "\n"
        "[security_review]\n"
        'status = "Met"\n'
        'justification = "A review of 2026."\n'
    )
    # Once fixed, nothing is left to remove.
    again = best_practices.verify(root, fix=True)
    assert again == best_practices.Verification([], [], 2)


def test_the_fix_leaves_a_status_that_a_person_decides(tmp_path: Path) -> None:
    # The template answers a criterion now that the project file answered as Unmet:
    # one of them is wrong, which only a person knows.
    own = f'[test]\nstatus = "Unmet"\njustification = "Ours: {REPO}/scripts/check.sh"\n'
    root = verifiable(tmp_path, own)

    outcome = best_practices.verify(root, fix=True)

    assert outcome.removed == []
    assert len(outcome.problems) == 1
    assert (root / PROJECT_ANSWERS).read_text(encoding="utf-8") == own


@pytest.mark.parametrize("fix", [False, True])
def test_the_command_checks_the_project_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], fix: bool
) -> None:
    root = verifiable(
        tmp_path, f'[test]\njustification = "pytest: {REPO}/scripts/check.sh"\n'
    )
    command = ["best-practices", "--verify"] + (["--fix"] if fix else [])

    code = main(command, root=root)

    lines = capsys.readouterr().out.splitlines()
    if fix:
        assert code == 0
        assert lines == [
            ".github/bestpractices.project.toml: removed the justification of [test], "
            "which only repeated the blueprint's.",
            ".github/bestpractices.project.toml gives no answer of its own: the answers "
            "are those of .bestpractices.json.",
        ]
        return
    assert code == 1
    assert lines[0].startswith(
        ".github/bestpractices.project.toml: [test] repeats the justification"
    )
    assert lines[-1] == (
        "python3 blueprint.py best-practices --verify --fix removes a status "
        "Met and a justification that only repeat .bestpractices.json; the rest needs "
        "a person, who knows what holds for this repository."
    )
    # Its own answer passes.
    with_own_answers(
        root, '[security_review]\nstatus = "Met"\njustification = "A review."\n'
    )
    assert main(["best-practices", "--verify"], root=root) == 0
    assert capsys.readouterr().out == (
        ".github/bestpractices.project.toml answers 1 criterion(s) as this "
        "repository alone can.\n"
    )


@pytest.mark.parametrize(
    "arguments",
    [["--fix"], ["--verify", "--dry-run"], ["--fix", "--dry-run"]],
)
def test_the_options_of_the_check_go_together(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], arguments: list[str]
) -> None:
    assert main(["best-practices", *arguments], root=tmp_path) == 2
    assert "--fix goes with --verify" in capsys.readouterr().err


def test_a_project_file_that_is_no_text_fails_the_check(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".github").mkdir()
    (tmp_path / PROJECT_ANSWERS).write_bytes(b"\xff\xfe")

    assert main(["best-practices", "--verify"], root=tmp_path) == 2
    assert capsys.readouterr().err.startswith("blueprint.py: ")
