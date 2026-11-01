"""The notice for a pull request that changes a file of the blueprint: the list of those
files, the step of the check lint, and the part and the label of the report."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
import yaml

import reference
from blueprint import cli
from blueprint.coach import Catalog
from blueprint.github import Api
from blueprint.ownership import (
    ANNOTATION,
    ANNOTATION_TITLE,
    FAIL,
    LABEL,
    LABEL_COLOR,
    LABEL_DESCRIPTION,
    LIST,
    MOST_NAMED,
    changed_names,
    check,
    exempt,
    keep_label,
    load,
    of_the_blueprint,
    proposal_link,
    report_part,
    report_text,
    workflow_commands,
)
from blueprint.pr_report import about

ROOT = Path(__file__).parents[1]
REPO = "o/r"
COPIER = """\
_answers_file: .copier-answers.yml
_skip_if_exists:
  - /README.md
  - /docs/decisions
  - .github/labels.toml
  - .github/workflows/action-test.yml
  - /src
  - "/*.py"
"""


def a_repository(tmp_path: Path, *owned: str) -> Path:
    (tmp_path / LIST).parent.mkdir(parents=True)
    head = "# The files of the blueprint\n\n"
    (tmp_path / LIST).write_text(
        head + "".join(f"{path}\n" for path in owned),
        encoding="utf-8",
        newline="\n",
    )
    return tmp_path


class Github:
    """GitHub with the labels that it knows, and each request that changes something."""

    def __init__(
        self, *known: str, refuse: bool = False, files: Sequence[Any] = ()
    ) -> None:
        self.known = set(known)
        self.refuse = refuse
        self.files = list(files)
        self.changes: list[tuple[str, str, Any]] = []

    def __call__(
        self, arguments: Sequence[str], body: str | None
    ) -> subprocess.CompletedProcess[str]:
        method, path = arguments[3], arguments[4].removeprefix(f"repos/{REPO}/")
        status, data = self.answer(method, path, body)
        text = f"HTTP/2.0 {status} X\r\n\r\n{json.dumps(data)}"
        code = 0 if status < 400 else 1
        return subprocess.CompletedProcess(arguments, code, text, "")

    def answer(self, method: str, path: str, body: str | None) -> tuple[int, Any]:
        if method == "GET":
            if path.startswith("pulls/"):
                return 200, self.files
            name = path.removeprefix("labels/")
            return (200, {}) if name in self.known else (404, {})
        if self.refuse:
            return 403, {"message": "Resource not accessible by integration"}
        self.changes.append((method, path, json.loads(body) if body else None))
        return (204 if method == "DELETE" else 201), {}


def a_pull(
    *labels: str,
    ref: str = "topic",
    head_repo: str | None = REPO,
    author: str = "User",
) -> dict[str, Any]:
    head: dict[str, Any] = {
        "ref": ref,
        "sha": "a" * 40,
        "repo": {"full_name": head_repo} if head_repo else None,
    }
    return {
        "number": 7,
        "head": head,
        "user": {"type": author},
        "title": "docs: x",
        "body": "",
        "labels": [{"name": label} for label in labels],
    }


# ---------------------------------------------------------------- the list


@pytest.mark.parametrize(
    ("template_file", "listed"),
    [
        # A file of the blueprint, by the name that it gets.
        ("CONTRIBUTING.md.jinja", True),
        ("scripts/check.sh.jinja", True),
        ("LICENSES/{= license =}.txt.jinja", True),
        # A file without the suffix of a template too.
        (".editorconfig", True),
        # A file of the project, by its pattern.
        ("README.md.jinja", False),
        (".github/labels.toml.jinja", False),
        # A pattern of a folder holds all that is in it, also below a condition.
        ("docs/decisions/0001-record.md.jinja", False),
        ("[% if a %]src[% endif %]/{= package =}/__init__.py.jinja", False),
        # /*.py holds the Python of the root and no deeper one.
        ("[% if a %]{= package =}.py[% endif %].jinja", False),
        ("setup.py.jinja", False),
        (".github/blueprint.py.jinja", True),
        (".github/blueprint/cli.py.jinja", True),
        # The pattern of a file behind the condition of its name.
        (".github/workflows/[% if a %]action-test.yml[% endif %].jinja", False),
        # A pattern with a leading slash holds nothing deeper.
        ("docs/README.md.jinja", True),
        # A name that merely begins like a folder of the project.
        ("srcs/a.txt", True),
        # The answers belong to the command that writes them.
        (".copier-answers.yml.jinja", False),
    ],
)
def test_the_list_leaves_out_what_the_patterns_of_a_project_hold(
    template_file: str, listed: bool
) -> None:
    written = reference.owned_list(COPIER, [template_file])
    assert written.startswith(reference.OWNED_HEAD)
    assert bool(written.removeprefix(reference.OWNED_HEAD)) is listed


@pytest.mark.parametrize(
    ("template_file", "path", "line"),
    [
        ("LICENSE.jinja", "LICENSE", "LICENSE\n"),
        (".editorconfig", ".editorconfig", ".editorconfig\n"),
        (
            ".github/[% if a == 'b' %]c.yml[% endif %].jinja",
            ".github/c.yml",
            "[%- if a == 'b' %]\n.github/c.yml\n[%- endif %]\n",
        ),
        (
            ".github/[% if a %]d[% endif %]/[% if b %]e[% endif %]",
            ".github/d/e",
            "[%- if a %][% if b %]\n.github/d/e\n[%- endif %][% endif %]\n",
        ),
    ],
)
def test_a_line_of_the_list_keeps_the_condition_of_its_file(
    template_file: str, path: str, line: str
) -> None:
    assert reference.owned_line(template_file) == (path, line)


def test_the_list_is_sorted_by_the_paths_of_its_files() -> None:
    files = ["z.txt", "[% if a %]m.txt[% endif %]", "b.txt"]
    assert reference.owned_list(COPIER, files).removeprefix(reference.OWNED_HEAD) == (
        "b.txt\n[%- if a %]\nm.txt\n[%- endif %]\nz.txt\n"
    )


def test_every_condition_of_a_name_in_the_template_is_one_the_list_understands() -> (
    None
):
    # Any other form would leave its [% if %] in the path, and in a repository with it
    # the list would name a file of no such name.
    written = reference.owned_list(
        (ROOT / "copier.yml").read_text(encoding="utf-8"),
        reference.template_files(ROOT),
    )
    for name in reference.template_files(ROOT):
        path, _ = reference.owned_line(name)
        assert "[%" not in path, name
    assert "scripts/check.sh\n" in written


def test_a_repository_without_a_list_has_no_file_of_a_blueprint(tmp_path: Path) -> None:
    assert load(tmp_path) is None
    assert load(ROOT) is None


def test_the_list_skips_its_comments_and_empty_lines(tmp_path: Path) -> None:
    assert load(a_repository(tmp_path, "a.yml", "b c.yml")) == frozenset(
        {"a.yml", "b c.yml"}
    )


# ---------------------------------------------------------------- who gets the notice


@pytest.mark.parametrize(
    ("branch", "head_repo", "author_type", "skipped"),
    [
        ("topic", REPO, "User", False),
        # The blueprint bot and the other bots of this repository.
        ("blueprint/update", REPO, "User", True),
        ("bot/self-heal", REPO, "User", True),
        ("bot/diagrams", REPO, "User", True),
        # An account of a GitHub App, such as that of Renovate.
        ("renovate/actions", REPO, "Bot", True),
        ("topic", "fork/r", "Bot", True),
        # A fork can name its branch as it likes, and still gets the notice.
        ("blueprint/update", "fork/r", "User", False),
        ("bot/self-heal", "fork/r", "User", False),
        # A branch that only looks like one of them.
        ("blueprint/update-2", REPO, "User", False),
        ("bots/x", REPO, "User", False),
    ],
)
def test_a_bot_that_brings_the_files_gets_no_notice(
    branch: str, head_repo: str, author_type: str, skipped: bool
) -> None:
    assert exempt(branch, head_repo, REPO, author_type) is skipped


def test_the_files_of_the_blueprint_among_the_changed_ones() -> None:
    owned = frozenset({"a.yml", "b.yml"})
    assert of_the_blueprint(["z.md", "b.yml", "a.yml", "b.yml", ""], owned) == [
        "a.yml",
        "b.yml",
    ]


def test_the_paths_of_a_rename_count_both() -> None:
    files = [
        {"filename": "new.yml", "previous_filename": "old.yml"},
        {"filename": "same.yml"},
    ]
    assert changed_names(files) == ["new.yml", "old.yml", "same.yml", ""]


# ---------------------------------------------------------------- the step


def checked(root: Path, listing: bytes, **changes: str) -> int:
    arguments = {
        "branch": "topic",
        "head_repo": REPO,
        "repo": REPO,
        "author_type": "User",
        "mode": "",
    }
    return check(root, listing, **(arguments | changes))


def test_a_changed_file_of_the_blueprint_is_a_notice(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = a_repository(tmp_path, "a.yml", "b.yml")
    assert checked(root, b"b.yml\0other.py\0") == 0
    assert capsys.readouterr().out == (
        f"::notice file=b.yml,title={ANNOTATION_TITLE}::{ANNOTATION}\n"
    )


def test_the_variable_makes_it_a_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = a_repository(tmp_path, "a.yml", "b.yml")
    assert checked(root, b"a.yml\0b.yml\0", mode=FAIL) == 1
    out = capsys.readouterr().out.splitlines()
    assert [line.split(",")[0] for line in out] == [
        "::error file=a.yml",
        "::error file=b.yml",
    ]


@pytest.mark.parametrize("mode", ["", "notice", "FAIL", "on"])
def test_any_other_value_of_the_variable_leaves_a_notice(
    tmp_path: Path, mode: str
) -> None:
    assert checked(a_repository(tmp_path, "a.yml"), b"a.yml\0", mode=mode) == 0


@pytest.mark.parametrize(
    ("owned", "changes", "said"),
    [
        (("a.yml",), {}, "no file of the blueprint"),
        (("c.yml",), {"branch": "blueprint/update"}, "A bot brings"),
        (("c.yml",), {"author_type": "Bot"}, "A bot brings"),
    ],
)
def test_nothing_to_say_passes_even_in_the_mode_that_fails(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    owned: tuple[str, ...],
    changes: dict[str, str],
    said: str,
) -> None:
    root = a_repository(tmp_path, *owned)
    assert checked(root, b"c.yml\0", **(changes | {"mode": FAIL})) == 0
    out = capsys.readouterr().out
    assert said in out
    assert "::" not in out


def test_the_blueprint_itself_has_no_list_and_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert checked(tmp_path, b".github/workflows/lint.yml\0", mode=FAIL) == 0
    assert "no file belongs to a blueprint" in capsys.readouterr().out


def test_a_name_in_an_annotation_can_end_nothing() -> None:
    line = workflow_commands(["a,b:c.yml"], False)[0]
    assert line.startswith(
        "::notice file=a%2Cb%3Ac.yml,title=A file of the blueprint::"
    )


def test_the_command_reads_what_git_wrote(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = a_repository(tmp_path / "repository", "a.yml")
    listing = tmp_path / "changed"
    listing.write_bytes(b"a.yml\0")
    arguments = [
        "--repo",
        REPO,
        "ownership",
        str(listing),
        "--branch=topic",
        f"--head-repo={REPO}",
        "--author-type=User",
    ]
    assert cli.main(arguments, root=root) == 0
    assert "::notice file=a.yml" in capsys.readouterr().out
    assert cli.main([*arguments, f"--mode={FAIL}"], root=root) == 1
    # A branch of a bot in the repository of the run, even in the mode that fails.
    assert cli.main([*arguments, f"--mode={FAIL}", "--branch=bot/x"], root=root) == 0


def test_the_command_says_when_it_has_no_listing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["ownership", str(tmp_path / "none")], root=tmp_path) == 2
    assert capsys.readouterr().err.startswith("blueprint.py: ")


# ---------------------------------------------------------------- the report


def test_the_report_names_the_files_and_the_way_out() -> None:
    text = report_text(REPO, [".github/workflows/lint.yml", "CONTRIBUTING.md"])
    assert text.startswith("#### Files of the blueprint\n")
    assert "- `.github/workflows/lint.yml`\n- `CONTRIBUTING.md`\n" in text
    for place in (
        ".github/repository.project.toml",
        "scripts/check-project.sh",
        ".github/checks.project.toml",
        ".github/agents.project.md",
        ".github/workflows/",
    ):
        assert f"`{place}`" in text
    assert (
        f"]({proposal_link(REPO, ['.github/workflows/lint.yml', 'CONTRIBUTING.md'])})"
        in text
    )
    assert "and … more" not in text


def test_the_report_of_many_files_stays_short() -> None:
    files = [f"f{index:03}.yml" for index in range(MOST_NAMED + 3)]
    text = report_text(REPO, files)
    assert f"- `f{MOST_NAMED - 1:03}.yml`" in text
    assert f"- `f{MOST_NAMED:03}.yml`" not in text
    assert "- … and 3 more\n" in text
    # A browser and GitHub take a link of this length.
    assert len(proposal_link(REPO, files)) < 2000


def test_the_link_fills_in_the_form_of_the_blueprint() -> None:
    link = urlsplit(proposal_link(REPO, ["a b.yml"]))
    assert link.netloc == "github.com"
    assert link.path == "/Dennis-Otto/repo-blueprint/issues/new"
    query = parse_qs(link.query)
    form = yaml.safe_load(
        (ROOT / ".github/ISSUE_TEMPLATE" / query["template"][0]).read_text(
            encoding="utf-8"
        )
    )
    fields = {field.get("id") for field in form["body"]}
    # Blank issues are off, so that the template is what opens, by its fields.
    assert set(query) - {"template", "title"} <= fields
    assert query["title"][0].endswith(REPO)
    assert "- `a b.yml`" in query["problem"][0]


@pytest.mark.parametrize(
    ("labels", "wanted", "known", "changes"),
    [
        ((), False, (), []),
        ((LABEL,), True, (LABEL,), []),
        # The label of a repository that has it, or whose labels.toml lacks it.
        (
            (),
            True,
            (LABEL,),
            [("POST", "issues/7/labels", {"labels": [LABEL]})],
        ),
        (
            ("other",),
            True,
            (),
            [
                (
                    "POST",
                    "labels",
                    {
                        "name": LABEL,
                        "color": LABEL_COLOR,
                        "description": LABEL_DESCRIPTION,
                    },
                ),
                ("POST", "issues/7/labels", {"labels": [LABEL]}),
            ],
        ),
        # A push that undoes the change takes the label away.
        ((LABEL,), False, (LABEL,), [("DELETE", f"issues/7/labels/{LABEL}", None)]),
    ],
)
def test_the_label_follows_the_files(
    labels: tuple[str, ...],
    wanted: bool,
    known: tuple[str, ...],
    changes: list[tuple[str, str, Any]],
) -> None:
    github = Github(*known)
    keep_label(Api(github), REPO, a_pull(*labels), wanted)
    assert github.changes == changes


@pytest.mark.parametrize(("labels", "wanted"), [((), True), ((LABEL,), False)])
def test_a_label_that_github_refuses_stops_no_report(
    capsys: pytest.CaptureFixture[str], labels: tuple[str, ...], wanted: bool
) -> None:
    github = Github(LABEL, refuse=True)
    keep_label(Api(github), REPO, a_pull(*labels), wanted)
    assert github.changes == []
    assert f"The label {LABEL} of #7 stays as it is" in capsys.readouterr().err


def test_the_part_is_news_with_the_label(tmp_path: Path) -> None:
    root = a_repository(tmp_path, "a.yml")
    github = Github(LABEL)
    files = [{"filename": "a.yml"}, {"filename": "other.py"}]
    part = report_part(Api(github), REPO, a_pull(), files, root)
    assert part is not None
    assert part.news
    assert "- `a.yml`" in part.text
    assert "other.py" not in part.text
    assert github.changes == [("POST", "issues/7/labels", {"labels": [LABEL]})]


def test_a_rename_of_a_file_of_the_blueprint_is_news(tmp_path: Path) -> None:
    root = a_repository(tmp_path, "a.yml")
    files = [{"filename": "b.yml", "previous_filename": "a.yml"}]
    part = report_part(Api(Github(LABEL)), REPO, a_pull(), files, root)
    assert part is not None
    assert "- `a.yml`" in part.text


def test_no_file_of_the_blueprint_is_no_part_and_no_label(tmp_path: Path) -> None:
    root = a_repository(tmp_path, "a.yml")
    github = Github(LABEL)
    files = [{"filename": "other.py"}]
    assert report_part(Api(github), REPO, a_pull(LABEL), files, root) is None
    assert github.changes == [("DELETE", f"issues/7/labels/{LABEL}", None)]


def test_a_fork_that_its_owner_deleted_still_gets_the_part(tmp_path: Path) -> None:
    root = a_repository(tmp_path, "a.yml")
    files = [{"filename": "a.yml"}]
    pull = a_pull(ref="bot/self-heal", head_repo=None)
    assert report_part(Api(Github(LABEL)), REPO, pull, files, root) is not None


def test_a_bot_branch_gets_no_part_and_loses_the_label(tmp_path: Path) -> None:
    root = a_repository(tmp_path, "a.yml")
    github = Github(LABEL)
    files = [{"filename": "a.yml"}]
    pull = a_pull(LABEL, ref="blueprint/update")
    assert report_part(Api(github), REPO, pull, files, root) is None
    assert github.changes == [("DELETE", f"issues/7/labels/{LABEL}", None)]


def test_the_blueprint_itself_gets_no_part_and_no_label(tmp_path: Path) -> None:
    github = Github(LABEL)
    files = [{"filename": ".github/workflows/lint.yml"}]
    assert report_part(Api(github), REPO, a_pull(LABEL), files, tmp_path) is None
    assert github.changes == []


def test_the_report_of_the_coach_holds_the_part(tmp_path: Path) -> None:
    root = a_repository(tmp_path, "a.yml")
    github = Github(LABEL, files=[{"filename": "a.yml", "status": "modified"}])
    parts = about(Api(github), REPO, a_pull(), root)
    assert [part.text.splitlines()[0] for part in parts if part.news] == [
        "#### Files of the blueprint"
    ]


# ---------------------------------------------------------------- what comes with it


def test_a_new_repository_has_the_label_as_the_report_creates_it() -> None:
    labels = (ROOT / "template/.github/labels.toml.jinja").read_text(encoding="utf-8")
    assert (
        f'name = "{LABEL}"\ncolor = "{LABEL_COLOR}"\n'
        f'description = "{LABEL_DESCRIPTION}"\n'
    ) in labels
    # GitHub takes a description of 100 characters at most.
    assert len(LABEL_DESCRIPTION) <= 100


def test_the_coach_explains_the_failure() -> None:
    entry = Catalog.load(ROOT).check("ownership")
    assert entry is not None
    assert "BLUEPRINT_OWNERSHIP" in entry.problem
    assert entry.declared
    # Only the author knows where the change belongs instead.
    assert not entry.autofix


@pytest.mark.parametrize("page", ["docs/faq.md", "docs/faq.de.md"])
def test_the_faq_mentions_the_notice(page: str) -> None:
    text = (ROOT / page).read_text(encoding="utf-8")
    assert "BLUEPRINT_OWNERSHIP" in text
    assert "`.github/blueprint/owned.txt`" in text
