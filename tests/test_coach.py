"""Tests of the PR coach: the explanations of the checks, the summary and the
annotation of a check that fails, and the one comment on a pull request, against a
simulated GitHub with the recorded answers of its API for a pull request from a fork.
"""

from __future__ import annotations

import copy
import json
import os
import re
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from shell import BASH

import blueprint.coach
from blueprint import cli
from blueprint.coach import (
    BOT,
    FIX_HEADLINE,
    MARKER,
    Catalog,
    CatalogError,
    Entry,
    Run,
    annotation,
    check_steps,
    code,
    escape_data,
    escape_property,
    fence,
    html_code,
    link,
    missing,
    plain,
    report,
    required_checks,
    suggest_title,
    summary,
    undeclared,
)
from blueprint.github import Api

ROOT = Path(__file__).parents[1]
REPO = "Dennis-Otto/demo"
RECORDED = json.loads((ROOT / "tests/data/coach.json").read_text(encoding="utf-8"))
SHA = RECORDED["event"]["workflow_run"]["head_sha"]
# The pattern of the check of the title, as the workflow has it.
TITLE = re.search(
    r"pattern='(\^\(feat.+?)'\n",
    (ROOT / ".github/workflows/pull-request-title.yml").read_text(encoding="utf-8"),
)
assert TITLE


def catalog() -> Catalog:
    return Catalog.load(ROOT)


def write(root: Path, name: str, text: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


ENTRY = """
title = "The thing"
problem = "It broke."
why = "It matters."
fix = "Mend it."
autofix = "Only a person mends it."
"""


# ---------------------------------------------------------------- the explanations


def test_the_blueprint_explains_every_required_check_and_every_step() -> None:
    explained = catalog()
    checks = required_checks(ROOT)
    steps = check_steps(ROOT)

    assert "lint" in checks
    assert steps[0] == "Text files"
    assert "Website" in steps
    assert missing(explained, checks, steps) == []
    assert cli.main(["coach", "verify"], root=ROOT) == 0
    # Each link of them leads to a section of the contributing guide.
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    anchors = {
        re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
        for heading in re.findall(r"^#+ (.+)$", contributing, re.M)
    }
    used = [explained.check(name) for name in checks]
    used += [explained.step(name) for name in steps]
    for entry in used:
        assert entry
        if entry.docs.startswith("CONTRIBUTING.md#"):
            assert entry.docs.removeprefix("CONTRIBUTING.md#") in anchors, entry.key


def test_every_explanation_says_what_why_and_how(
    capsys: pytest.CaptureFixture[str],
) -> None:
    explained = catalog()
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    anchors = {
        re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
        for heading in re.findall(r"^#+ (.+)$", contributing, re.M)
    }
    for entry in [*explained.checks.values(), *explained.steps.values()]:
        # Whole sentences, which end with a full stop or lead to the commands.
        for text in (entry.problem, entry.why, entry.fix):
            assert text[-1] in ".:", (entry.key, text)
        assert entry.fix.endswith(":") == bool(entry.commands), entry.key
        if entry.docs.startswith("CONTRIBUTING.md#"):
            assert entry.docs.split("#")[1] in anchors, entry.key
        else:
            assert entry.docs.startswith("https://") or not entry.docs, entry.key
    # Each check has a title of its own, which names it in the summary.
    titles = [entry.title for entry in explained.checks.values()]
    assert len(titles) == len(set(titles))
    capsys.readouterr()


def test_a_check_and_a_step_without_an_explanation_fail_the_verification(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(tmp_path, ".github/checks.toml", f'[check.lint]{ENTRY}[step."Ruff"]{ENTRY}')
    write(tmp_path, ".github/repository.toml", '[branch]\nrequired_checks = ["lint"]\n')
    write(
        tmp_path,
        ".github/repository.project.toml",
        '[branch]\nrequired_checks = ["e2e (Firefox)", "lint"]\n',
    )
    write(tmp_path, "scripts/check.sh", 'step "Ruff"\nstep "Mypy"\nstep "$x"\n')

    assert required_checks(tmp_path) == ["lint", "e2e (Firefox)"]
    assert check_steps(tmp_path) == ["Ruff", "Mypy"]
    assert cli.main(["coach", "verify"], root=tmp_path) == 1
    error = capsys.readouterr().err
    assert "the check e2e (Firefox) has no explanation" in error
    assert "the step Mypy of scripts/check.sh has no explanation" in error
    assert "add it to .github/checks.project.toml" in error

    # The project explains its own check and step.
    write(
        tmp_path,
        ".github/checks.project.toml",
        f'[check."e2e (*)"]{ENTRY}[step.Mypy]{ENTRY}',
    )
    assert cli.main(["coach", "verify"], root=tmp_path) == 0
    assert "is explained" in capsys.readouterr().out


def test_nothing_to_explain_without_the_files(tmp_path: Path) -> None:
    empty = Catalog.load(tmp_path)

    assert empty.checks == {}
    assert empty.steps == {}
    assert required_checks(tmp_path) == []
    assert check_steps(tmp_path) == []


def test_the_explanations_of_the_project_win(tmp_path: Path) -> None:
    write(
        tmp_path,
        ".github/checks.toml",
        f'[check."check (*)"]{ENTRY}[check.docs]{ENTRY}[step.Ruff]{ENTRY}',
    )
    write(
        tmp_path,
        ".github/checks.project.toml",
        '[check.docs]\ntitle = "Our docs"\nproblem = "P."\nwhy = "W."\nfix = """Run\n'
        '  it:"""\ncommands = ["make docs"]\ndocs = "https://example.com/"\n'
        '[step.Ruff]\ntitle = "Lint"\nproblem = "P."\nwhy = "W."\nfix = "F."\n'
        f'[check."check (e2e*)"]{ENTRY}',
    )
    explained = Catalog.load(tmp_path)

    docs = explained.check("docs")
    assert docs == Entry(
        "docs",
        "Our docs",
        "P.",
        "W.",
        "Run it:",
        ("make docs",),
        "https://example.com/",
    )
    assert explained.step("Ruff") == Entry("Ruff", "Lint", "P.", "W.", "F.")
    # The name of a check that a pattern matches, and none that nothing explains.
    pattern = explained.check("check (python)")
    assert pattern is not None
    assert pattern.key == "check (*)"
    # A pattern of the project wins over one of the blueprint that matches too.
    e2e = explained.check("check (e2e Firefox)")
    assert e2e is not None
    assert e2e.key == "check (e2e*)"
    assert explained.check("checks") is None
    assert explained.step("Mypy") is None


def test_a_step_is_its_own_title(tmp_path: Path) -> None:
    write(
        tmp_path,
        ".github/checks.toml",
        '[step.Ruff]\nproblem = "P."\nwhy = "W."\nfix = "F."\n',
    )

    assert Catalog.load(tmp_path).steps["Ruff"].title == "Ruff"


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ("[check]\nlint = 1\n", "[check.'lint'] is no table"),
        ("check = 1\n", "check is no table of tables"),
        ("[other]\n", "has unknown tables: other"),
        (f"[check.lint]{ENTRY}color = 1\n", "has unknown keys: color"),
        (
            '[check.lint]\ntitle = "T"\nproblem = " "\nwhy = "W"\nfix = "F"\n',
            "needs the text problem",
        ),
        ('[check.lint]\nproblem = "P"\nwhy = "W"\nfix = "F"\n', "needs the text title"),
        (f"[check.lint]{ENTRY}commands = 'make'\n", "commands that are no list"),
        (f"[check.lint]{ENTRY}commands = [1]\n", "commands that are no list"),
        (f"[check.lint]{ENTRY}docs = 1\n", "docs that are no link"),
        ("[check.lint\n", ".github/checks.toml: "),
    ],
)
def test_an_incomplete_explanation_is_an_error(
    tmp_path: Path, text: str, error: str
) -> None:
    write(tmp_path, ".github/checks.toml", text)

    with pytest.raises(CatalogError, match=re.escape(error)):
        Catalog.load(tmp_path)


def test_every_explanation_says_how_it_fixes_itself_or_why_it_cannot() -> None:
    explained = catalog()

    assert undeclared(explained) == []
    for entry in [*explained.checks.values(), *explained.steps.values()]:
        assert bool(entry.autofix) != bool(entry.manual), entry.key
        # A reason is a whole sentence; a command of the blueprint is run by it.
        assert not entry.manual or entry.manual.endswith("."), entry.key
        for command in entry.autofix:
            assert "python3" not in command, (entry.key, command)
    fixed = [key for key, entry in explained.steps.items() if entry.autofix]
    assert fixed == ["Text files", "Pages in one column", "Ruff", "Coding standard"]
    markdown = explained.check("markdown")
    assert markdown
    assert markdown.autofix == ('npx markdownlint-cli2 --fix "**/*.md"',)


def test_an_explanation_without_its_autofix_fails_the_verification(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    silent = ENTRY.replace('autofix = "Only a person mends it."\n', "")
    write(tmp_path, ".github/checks.toml", f"[check.lint]{silent}[step.Ruff]{ENTRY}")
    write(tmp_path, "scripts/check.sh", 'step "Ruff"\n')

    assert undeclared(Catalog.load(tmp_path)) == ["the check lint"]
    assert cli.main(["coach", "verify"], root=tmp_path) == 1
    assert capsys.readouterr().err == (
        "blueprint.py: the explanation of the check lint has no autofix: the commands "
        "that fix what it finds, or the reason why no command can\n"
    )
    write(tmp_path, ".github/checks.toml", f"[check.lint]{silent}")
    assert undeclared(Catalog.load(tmp_path)) == ["the check lint"]
    write(tmp_path, ".github/checks.toml", f"[step.Mypy]{silent}")
    assert undeclared(Catalog.load(tmp_path)) == ["the step Mypy of scripts/check.sh"]


@pytest.mark.parametrize(
    ("autofix", "commands", "manual"),
    [
        (
            '["ruff format .", "ruff check --fix ."]',
            ("ruff format .", "ruff check --fix ."),
            "",
        ),
        ('"""Only a person\nknows."""', (), "Only a person knows."),
    ],
)
def test_an_autofix_is_commands_or_a_reason(
    tmp_path: Path, autofix: str, commands: tuple[str, ...], manual: str
) -> None:
    text = ENTRY.replace('"Only a person mends it."', autofix)
    write(tmp_path, ".github/checks.toml", f"[check.lint]{text}")

    entry = Catalog.load(tmp_path).check("lint")

    assert entry
    assert (entry.autofix, entry.manual, entry.declared) == (commands, manual, True)


@pytest.mark.parametrize("autofix", ["[]", '[""]', "[1]", '" "', "3", "{}"])
def test_an_autofix_of_nothing_is_an_error(tmp_path: Path, autofix: str) -> None:
    text = ENTRY.replace('"Only a person mends it."', autofix)
    write(tmp_path, ".github/checks.toml", f"[check.lint]{text}")

    with pytest.raises(CatalogError, match="has an autofix that is neither a list"):
        Catalog.load(tmp_path)


# ---------------------------------------------------------------- the summary of a check


def test_a_check_that_fixes_itself_says_so() -> None:
    ruff = catalog().step("Ruff")
    mypy = catalog().step("Mypy")
    assert ruff
    assert mypy

    assert (
        "\n\n**It fixes itself:** after the checks, the fix bot commits the fix onto a "
        "branch of this repository, and suggests it at its lines on a pull request "
        "from a fork.\n\n**How to fix it:**"
    ) in summary(ruff, step=True, url="")
    assert "It fixes itself" not in summary(mypy, step=True, url="")


def test_the_summary_of_a_failed_check() -> None:
    dco = catalog().check("dco")
    assert dco is not None

    text = summary(dco, step=False, url=link(dco.docs, REPO))

    assert text.startswith("### PR coach: The sign-off of every commit\n\n")
    assert "**What is wrong:** A commit lacks the line" in text
    assert "**Why it matters:** With the sign-off" in text
    assert "```sh\ngit commit --amend --signoff --no-edit\n" in text
    assert text.endswith(
        "More: [CONTRIBUTING.md#requirements-for-changes]"
        f"(https://github.com/{REPO}/blob/HEAD/CONTRIBUTING.md#requirements-for-changes)\n"
    )


def test_the_summary_of_a_step_without_commands_or_a_link() -> None:
    entry = Entry("Version", "Version", "P.", "W.", "F.")

    assert summary(entry, step=True, url="") == (
        "### PR coach: Version (scripts/check.sh)\n\n"
        "**What is wrong:** P.\n\n**Why it matters:** W.\n\n**How to fix it:** F.\n"
    )
    assert plain(entry, step=True) == (
        "PR coach: Version (scripts/check.sh)\n"
        "  What is wrong: P.\n  Why it matters: W.\n  How to fix it: F.\n"
    )


def test_a_link_leads_to_github_or_stays_as_it_is() -> None:
    assert link("CONTRIBUTING.md#checks", "o/r") == (
        "https://github.com/o/r/blob/HEAD/CONTRIBUTING.md#checks"
    )
    assert link("CONTRIBUTING.md#checks", "o/r", "https://ghe.example") == (
        "https://ghe.example/o/r/blob/HEAD/CONTRIBUTING.md#checks"
    )
    assert link("CONTRIBUTING.md#checks", None) == "CONTRIBUTING.md#checks"
    assert link("https://reuse.software/", "o/r") == "https://reuse.software/"
    assert link("", "o/r") == ""
    reuse = catalog().check("reuse")
    assert reuse is not None
    assert summary(reuse, False, link(reuse.docs, "o/r")).endswith(
        "More: [https://reuse.software/tutorial/](https://reuse.software/tutorial/)\n"
    )


def test_the_annotation_keeps_its_title_and_lines() -> None:
    entry = Entry("x", "A: b, c", "100% broken.", "W.", "Run:", ("a\r", "b"))

    line = annotation(entry, step=False)

    assert line == (
        "::error title=PR coach%3A A%3A b%2C c::100%25 broken.%0AHow to fix it: Run:%0Aa%0D%0Ab"
    )
    # A step's is a notice, which the errors of its tools can't push out.
    assert annotation(entry, step=True).startswith(
        "::notice title=PR coach%3A x (scripts/check.sh)::100%25 broken."
    )
    assert escape_data("50%\n") == "50%25%0A"
    assert escape_property("a:b,c") == "a%3Ab%2Cc"


def test_a_block_of_commands_that_its_lines_cannot_close() -> None:
    assert fence("sh", ["echo ```"]) == "````sh\necho ```\n````"
    assert fence("sh", ["echo"]) == "```sh\necho\n```"


def test_explain_shows_the_fix_in_the_terminal(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("GITHUB_ACTIONS", "GITHUB_STEP_SUMMARY", "GITHUB_REPOSITORY"):
        monkeypatch.delenv(name, raising=False)

    assert cli.main(["coach", "explain", "--step", "Ruff"], root=ROOT) == 0

    out = capsys.readouterr().out
    assert out.startswith("PR coach: Ruff (scripts/check.sh)\n  What is wrong:")
    assert "\n      ruff check --fix .\n      ruff format .\n" in out
    assert "  More: CONTRIBUTING.md#coding-standards\n" in out
    assert "::error" not in out


def test_explain_writes_the_summary_and_the_annotation_in_the_ci(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "summary.md"
    target.write_text("Before.\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(target))
    monkeypatch.setenv("GITHUB_REPOSITORY", REPO)
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.com")

    assert cli.main(["coach", "explain", "markdown"], root=ROOT) == 0

    out = capsys.readouterr().out
    assert (
        "\n::error title=PR coach%3A The Markdown of the documents::A Markdown" in out
    )
    written = target.read_text(encoding="utf-8")
    assert written.startswith("Before.\n### PR coach: The Markdown of the documents\n")
    assert (
        f"(https://github.com/{REPO}/blob/HEAD/CONTRIBUTING.md#coding-standards)"
        in written
    )
    # The commands name the repository of the run, also for a pull request from a fork.
    assert cli.main(["coach", "explain", "dco"], root=ROOT) == 0
    out = capsys.readouterr().out
    assert f"\n      git fetch https://github.com/{REPO}.git main\n" in out
    assert f"%0Agit fetch https://github.com/{REPO}.git main%0A" in out


def test_explain_explains_each_check_that_failed_in_a_job_of_several(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(target))
    monkeypatch.setenv("GITHUB_REPOSITORY", REPO)

    # As the job lint passes the linters that failed.
    arguments = ["coach", "explain", "lint", "--parts", "markdown", "dco"]
    assert cli.main(arguments, root=ROOT) == 0

    out = capsys.readouterr().out
    # Each annotation names the check whose job ran it, by which the report finds it.
    assert (
        "\n::error title=PR coach%3A The Markdown of the documents (in lint)::" in out
    )
    assert "\n::error title=PR coach%3A The sign-off of every commit (in lint)::" in out
    assert "PR coach: The linters" not in out
    written = target.read_text(encoding="utf-8")
    assert written.startswith("### PR coach: The Markdown of the documents (in lint)\n")
    assert "\n### PR coach: The sign-off of every commit (in lint)\n" in written
    assert written.count("### PR coach: ") == 2

    # When none of them failed, but a step before them, the check explains itself.
    assert cli.main(["coach", "explain", "lint", "--parts"], root=ROOT) == 0
    out = capsys.readouterr().out
    assert "\n::error title=PR coach%3A The linters::" in out
    assert "(in lint)" not in out


def test_explain_names_what_it_cannot_explain(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(target))

    assert cli.main(["coach", "explain", "e2e"], root=ROOT) == 0
    assert cli.main(["coach", "explain", "--step", "Lint"], root=ROOT) == 0

    out = capsys.readouterr().out
    assert "no explanation of the check e2e yet" in out
    assert "no explanation of the step Lint of scripts/check.sh yet" in out
    assert "::error" not in out
    assert "Explain it in .github/checks.project.toml" in target.read_text(
        encoding="utf-8"
    )


def test_explain_reports_a_broken_catalog(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(tmp_path, ".github/checks.toml", "[check.lint]\n")

    assert cli.main(["coach", "explain", "lint"], root=tmp_path) == 2
    assert "needs the text title" in capsys.readouterr().err


# ---------------------------------------------------------------- scripts/check.sh


def run_a_step(
    tmp_path: Path, script: str, *, failing: str
) -> subprocess.CompletedProcess[str]:
    """The set-up of scripts/check.sh, with the trap of the coach, and a step that
    passes, then one that fails as given, in a repository whose blueprint.py only
    says how it was called."""
    check = (ROOT / "scripts/check.sh").read_text(encoding="utf-8")
    setup = check[: check.index('step "Text files"')]
    write(
        tmp_path,
        "scripts/check.sh",
        f'{setup}step "Ruff"\ntrue\nstep "Mypy"\n{failing}\n',
    )
    write(tmp_path, script, "import sys\nprint('explained', *sys.argv[1:])\n")
    assert BASH
    return subprocess.run(
        [BASH, "scripts/check.sh"],
        cwd=tmp_path,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )


@pytest.mark.skipif(BASH is None, reason="needs bash")
@pytest.mark.parametrize("script", [".github/blueprint.py", "blueprint.py"])
def test_the_checks_explain_the_step_that_failed(tmp_path: Path, script: str) -> None:
    result = run_a_step(tmp_path, script, failing="exit 3")

    assert result.returncode == 3
    assert result.stdout.endswith("== Mypy\nexplained coach explain --step Mypy\n")
    assert "Ruff\nexplained" not in result.stdout


@pytest.mark.skipif(BASH is None, reason="needs bash")
def test_the_checks_explain_a_command_that_failed(tmp_path: Path) -> None:
    result = run_a_step(tmp_path, ".github/blueprint.py", failing="false")

    assert result.returncode == 1
    assert "explained coach explain --step Mypy" in result.stdout


@pytest.mark.skipif(BASH is None, reason="needs bash")
def test_checks_that_pass_explain_nothing(tmp_path: Path) -> None:
    result = run_a_step(tmp_path, ".github/blueprint.py", failing="true")

    assert result.returncode == 0
    assert "explained" not in result.stdout


def check_the_text_files(
    tmp_path: Path, files: dict[str, bytes], *, ci: bool
) -> subprocess.CompletedProcess[str]:
    """The step Text files of scripts/check.sh, in a repository with these files."""
    check = (ROOT / "scripts/check.sh").read_text(encoding="utf-8")
    write(tmp_path, "scripts/check.sh", check[: check.index('step "Version"')])
    for name, content in files.items():
        (tmp_path / name).write_bytes(content)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("GITHUB_")
    }
    if ci:
        environment["GITHUB_ACTIONS"] = "true"
    assert BASH
    return subprocess.run(
        [BASH, "scripts/check.sh"],
        cwd=tmp_path,
        capture_output=True,
        encoding="utf-8",
        env=environment,
        check=False,
    )


@pytest.mark.skipif(BASH is None, reason="needs bash")
def test_the_ci_shows_each_problem_of_a_text_file_at_its_line(tmp_path: Path) -> None:
    files = {
        "spaces.txt": b"one\ntwo \nthree\n",
        "crlf.md": b"one\r\ntwo\r\n",
        "end, 100%.txt": b"one\ntwo",
        "clean.txt": b"one\n",
    }

    result = check_the_text_files(tmp_path, files, ci=True)

    assert result.returncode == 1
    lines = result.stdout.splitlines()
    # The log says what it said before, and the annotation adds the line.
    assert "spaces.txt: has trailing whitespace" in lines
    assert (
        "::error file=spaces.txt,line=2,title=Text files::has trailing whitespace"
    ) in lines
    assert (
        "::error file=crlf.md,line=1,title=Text files::has CRLF line endings"
    ) in lines
    # A comma or a percent sign of a name can't end the property of the command.
    assert (
        "::error file=end%2C 100%25.txt,line=2,title=Text files"
        "::lacks the line break at its end"
    ) in lines
    assert not [line for line in lines if "clean.txt" in line]
    assert "Fix the 3 problem(s) above;" in result.stdout


@pytest.mark.skipif(BASH is None, reason="needs bash")
@pytest.mark.skipif(os.name == "nt", reason="Windows takes no colon in a file name")
def test_no_name_of_a_file_ends_the_command_of_the_runner(tmp_path: Path) -> None:
    files = {"a:b\n::warning::x": b"x \n", "::notice::y": b"y \n", " ::debug::z": b"z"}

    result = check_the_text_files(tmp_path, files, ci=True)

    assert result.returncode == 1
    assert (
        "::error file=a%3Ab%0A%3A%3Awarning%3A%3Ax,line=1,title=Text files"
        "::has trailing whitespace\n"
    ) in result.stdout
    # The log names each file on one line that starts no command of the runner.
    lines = result.stdout.splitlines()
    assert "a:b\\n::warning::x: has trailing whitespace" in lines
    assert "./::notice::y: has trailing whitespace" in lines
    assert "./ ::debug::z: lacks the line break at its end" in lines
    commands = [line for line in lines if line.lstrip().startswith("::")]
    assert len(commands) == 3
    assert all(line.startswith("::error file=") for line in commands)


@pytest.mark.skipif(BASH is None, reason="needs bash")
def test_the_text_files_have_no_annotations_outside_the_ci(tmp_path: Path) -> None:
    result = check_the_text_files(tmp_path, {"spaces.txt": b"one \n"}, ci=False)

    assert result.returncode == 1
    assert "spaces.txt: has trailing whitespace" in result.stdout
    assert "::error" not in result.stdout


def test_the_lint_of_the_workflows_shows_each_error_at_its_line() -> None:
    lint = (ROOT / ".github/workflows/lint.yml").read_text(encoding="utf-8")
    found = re.search(r"/actionlint\.json\" <<'EOF'\n(.+)\n +EOF\n", lint)
    assert found
    pattern = json.loads(found[1])["problemMatcher"][0]["pattern"][0]
    regexp = re.compile(pattern["regexp"])
    # Lines of actionlint 1.7.12: its errors, and the source that it shows below each.
    errors = {
        '.github/workflows/x.yml:3:5: unexpected key "branch" for "push" section. '
        'expected one of "branches", "tags" [syntax-check]': (
            ".github/workflows/x.yml",
            "3",
            "5",
            'unexpected key "branch" for "push" section. expected one of "branches", '
            '"tags"',
            "syntax-check",
        ),
        "ci.yml:8:9: shellcheck reported issue in this script: SC2086:info:1:6: "
        "Double quote to prevent globbing and word splitting [shellcheck]": (
            "ci.yml",
            "8",
            "9",
            "shellcheck reported issue in this script: SC2086:info:1:6: "
            "Double quote to prevent globbing and word splitting",
            "shellcheck",
        ),
    }
    for line, expected in errors.items():
        match = regexp.match(line)
        assert match, line
        keys = ("file", "line", "column", "message", "code")
        assert tuple(match[pattern[key]] for key in keys) == expected
    for source in ("  |", "3 |     branch: main", "  |     ^~~~~~~"):
        assert not regexp.match(source)
    # The job registers it before actionlint runs.
    assert lint.index("::add-matcher::$RUNNER_TEMP/actionlint.json") < lint.index(
        "uses: docker://rhysd/actionlint"
    )


# ---------------------------------------------------------------- untrusted text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("plain", "`plain`"),
        ("a `b` c", "``a `b` c``"),
        ("`a`", "`` `a` ``"),
        ("line\nbreak\r\tand\x00more\N{LINE SEPARATOR}", "`line break and more`"),
        ("", ""),
        (" \n ", ""),
    ],
)
def test_untrusted_text_shows_as_code(text: str, expected: str) -> None:
    assert code(text) == expected


def test_long_untrusted_text_is_cut() -> None:
    assert code("x" * 400) == f"`{'x' * 299}…`"
    assert code("word " * 100, 10) == "`word word…`"


def test_untrusted_text_in_html_is_escaped() -> None:
    assert html_code('<img src="x"> & @me') == (
        "<code>&lt;img src=&quot;x&quot;&gt; &amp; @me</code>"
    )


@pytest.mark.parametrize(
    ("url", "shown"),
    [
        ("https://github.com/o/r/actions/runs/1/job/2", True),
        ("https://github.com/o/r/runs/2?check_suite_focus=true", False),
        ("https://github.com/o/r) [Win a prize](https://evil.example", False),
        ("https://github.com/o/r/runs/2 'title'", False),
        ("https://github.com.evil.example/o/r", False),
        ("http://github.com/o/r/runs/2", False),
        ("", False),
    ],
)
def test_only_a_plain_link_to_github_leads_to_the_log(url: str, shown: bool) -> None:
    run = Run.parse({"id": 2, "name": "lint", "html_url": url})

    assert run.url == (url if shown else "")


@given(st.text())
def test_no_untrusted_text_leaves_its_code(text: str) -> None:
    shown = code(text)
    if not shown:
        return
    # A code span ends only at a run of backticks as long as the one it starts with,
    # and a line break or a control character never reaches it.
    found = re.fullmatch(r"(`+)( ?)(.*)\2\1", shown, re.S)
    assert found
    runs = {len(run) for run in re.findall(r"`+", found[3])}
    assert len(found[1]) not in runs
    assert not re.search(
        "[\x00-\x1f\x7f-\x9f\N{LINE SEPARATOR}\N{PARAGRAPH SEPARATOR}]", shown
    )


@pytest.mark.parametrize(
    ("title", "branch", "expected"),
    [
        (
            "Dark mode for the settings.",
            "feature/dark-mode",
            "feat: dark mode for the settings",
        ),
        ("Feat: Add a dark mode", "patch-1", "feat: add a dark mode"),
        (
            "Fix(Settings UI)!: Crash on save.",
            "main",
            "fix(settings-ui)!: crash on save",
        ),
        ("[Docs] update README", "", "docs: update README"),
        ("bugfix - empty list", "", "fix: empty list"),
        (
            "Crash when the token is empty",
            "patch-1",
            "fix: crash when the token is empty",
        ),
        ("README for the CLI", "contributor:main", "feat: README for the CLI"),
        ("Update: the CI", "ci/faster", "ci: update: the CI"),
        ("", "docs_typo", "docs: describe the change"),
        ("...", "", "feat: describe the change"),
    ],
)
def test_a_title_that_passes(title: str, branch: str, expected: str) -> None:
    assert TITLE
    suggestion = suggest_title(title, branch)

    assert suggestion == expected
    assert re.match(TITLE[1], suggestion)


@given(st.text(), st.text())
def test_every_suggested_title_passes(title: str, branch: str) -> None:
    assert TITLE
    suggestion = suggest_title(title, branch)

    assert re.match(TITLE[1], suggestion)
    assert "\n" not in suggestion


# ---------------------------------------------------------------- the report


class FakeGitHub:
    """GitHub with one pull request from a fork, its check runs and their
    annotations, as the API answered them, and its comments."""

    def __init__(self) -> None:
        recorded = copy.deepcopy(RECORDED)
        self.pulls: list[dict[str, Any]] = [recorded["pull"]]
        self.runs: list[dict[str, Any]] = recorded["check_runs"]
        self.annotations: dict[str, list[dict[str, Any]]] = recorded["annotations"]
        self.comments: list[dict[str, Any]] = []
        # The head of the pull request, a commit of a person.
        self.commit: dict[str, Any] = {
            "commit": {"message": "Add a feature"},
            "author": {"login": "contributor", "type": "User"},
            "files": [{"filename": "src/app.py"}],
        }
        self.calls: list[tuple[str, str]] = []
        self.waits: list[float] = []
        # What happens while the coach waits for the checks of other apps.
        self.meanwhile: Callable[[FakeGitHub], None] = lambda github: None

    def __call__(
        self, arguments: Sequence[str], body: str | None
    ) -> subprocess.CompletedProcess[str]:
        method, path = arguments[3], arguments[4]
        self.calls.append((method, path))
        local = path.removeprefix(f"repos/{REPO}/")
        status, data = self.route(method, local, json.loads(body) if body else None)
        return subprocess.CompletedProcess(
            arguments, 0, f"HTTP/2.0 {status} X\r\nA: b\r\n\r\n{json.dumps(data)}", ""
        )

    def page(self, items: list[Any], size: str, number: str) -> list[Any]:
        start = (int(number) - 1) * int(size)
        return items[start : start + int(size)]

    def route(self, method: str, path: str, body: Any) -> tuple[int, Any]:
        paged = r"per_page=(\d+)&page=(\d+)"
        if found := re.fullmatch(rf"pulls\?state=open&{paged}", path):
            return 200, self.page(self.pulls, *found.groups())
        if found := re.fullmatch(r"pulls/(\d+)", path):
            pulls = [pull for pull in self.pulls if pull["number"] == int(found[1])]
            return (200, pulls[0]) if pulls else (404, {"message": "Not Found"})
        if found := re.fullmatch(rf"commits/(\w+)/check-runs\?{paged}", path):
            runs = self.runs if found[1] == SHA else []
            return 200, {
                "total_count": len(runs),
                "check_runs": self.page(runs, found[2], found[3]),
            }
        if found := re.fullmatch(r"commits/(\w+)", path):
            return (200, self.commit) if found[1] == SHA else (404, {})
        if found := re.fullmatch(rf"check-runs/(\d+)/annotations\?{paged}", path):
            items = self.annotations.get(found[1], [])
            return 200, self.page(items, found[2], found[3])
        if found := re.fullmatch(rf"issues/42/comments\?{paged}", path):
            return 200, self.page(self.comments, *found.groups())
        if method == "POST" and path == "issues/42/comments":
            comment = {"id": 900 + len(self.comments), "user": {"login": BOT}}
            self.comments.append(comment | body)
            return 201, comment
        if found := re.fullmatch(r"issues/comments/(\d+)", path):
            assert method == "PATCH"
            for comment in self.comments:
                if comment["id"] == int(found[1]):
                    comment.update(body)
            return 200, {}
        raise AssertionError(f"unexpected request {method} {path}")

    def writes(self) -> list[tuple[str, str]]:
        return [call for call in self.calls if call[0] != "GET"]

    def finish(self, conclusion: str = "success") -> None:
        """Every check runs again for the same commit and ends with conclusion."""
        for run in self.runs:
            run.update(status="completed", conclusion=conclusion)

    def wait(self, seconds: float) -> None:
        self.waits.append(seconds)
        self.meanwhile(self)


def run_report(github: FakeGitHub, number: int | None = None) -> str:
    return report(Api(runner=github), REPO, SHA, number, catalog(), wait=github.wait)


def body_of(github: FakeGitHub) -> str:
    assert len(github.comments) == 1
    return str(github.comments[0]["body"])


def test_a_pull_request_from_a_fork_gets_one_report() -> None:
    github = FakeGitHub()
    # As the step of the workflow passes them: a run from a fork names no pull request.
    run = RECORDED["event"]["workflow_run"]
    assert run["pull_requests"] == []

    said = run_report(github, None)

    assert said.startswith("The report of #42:\n\n<!-- pr-coach -->\n")
    assert github.writes() == [("POST", f"repos/{REPO}/issues/42/comments")]
    body = body_of(github)
    assert body.startswith(f"{MARKER}\n### PR coach\n\n**5 checks failed.**")
    assert "\n\n1 check is still running.\n\n⚠️ **1 check stopped" in body
    assert "- `codeql` · [its log](https://github.com/Dennis-Otto/demo/" in body
    # A check of the workflows still runs, which starts the coach again when it ends.
    assert github.waits == []
    # Five sections, closed, as there are more than three.
    assert body.count("<details>") == 5
    assert "<details open>" not in body
    assert body.endswith(
        f"<sub>For {SHA[:7]}. The PR coach updates this comment after every run of the "
        f"checks. [How it works](https://github.com/{REPO}/blob/HEAD/CONTRIBUTING.md"
        "#when-a-check-fails)</sub>\n"
    )
    # No annotation of a check that passed, and none of one that has none.
    read = {path for method, path in github.calls}
    assert not any("52000000006" in path or "52000000005" in path for path in read)


def sections(body: str) -> dict[str, str]:
    """The section of each check in the report, by the name in its summary: up to the
    end of the HTML of the section, a line of its own."""
    found = re.findall(r"<summary>(.+?)</summary>\n(.*?)\n</details>\n", body, re.S)
    return {
        re.findall(r"<code>(.+?)</code>", summary)[0]: text for summary, text in found
    }


def test_the_report_explains_the_step_of_the_checks_that_failed() -> None:
    github = FakeGitHub()
    run_report(github)

    part = sections(body_of(github))["check (python)"]
    assert "It stopped at the step **Ruff** of `scripts/check.sh`." in part
    assert "```sh\nruff check --fix .\nruff format .\n```" in part
    assert "Then run every check on your machine with `bash scripts/check.sh`" in part
    # The step, not the whole check, and no annotation of the coach or of GitHub.
    assert "One of the checks of `scripts/check.sh` failed" not in part
    assert "What the check found" not in part
    assert "Process completed" not in part
    assert (
        "[The log of the check](https://github.com/Dennis-Otto/demo/actions/runs/"
        in part
    )


def test_the_report_lists_what_a_check_found() -> None:
    github = FakeGitHub()
    run_report(github)

    body = body_of(github)
    assert (
        "<summary>❌ <b>The Markdown of the documents</b> · <code>markdown</code></summary>"
        in body
    )
    part = sections(body)["markdown"]
    assert (
        "**What is wrong:** A Markdown document breaks a rule of markdownlint" in part
    )
    assert (
        "- `docs/guide.md:12` `MD022/blanks-around-headings: Headings should be "
        "surrounded by blank lines [Expected: 1; Actual: 0; Below]`"
    ) in part
    # Only errors, no warning.
    assert "colour" not in part


def test_the_report_shows_untrusted_text_only_as_code() -> None:
    github = FakeGitHub()
    run_report(github)

    body = body_of(github)
    part = sections(body)["dco"]
    finding = next(line for line in part.splitlines() if line.startswith("- "))
    # One code span with a fence longer than the backticks of the message: no HTML, no
    # mention, no link and no end of the section takes effect.
    assert finding.startswith("- ````Commit 1234567 lacks the sign-off")
    assert finding.endswith("Commit with git commit -s.````")
    # The </details> of the message is text inside the code; each section ends with
    # its own, on a line of its own.
    assert body.splitlines().count("</details>") == 5
    for text in ("<img", "@Dennis-Otto", "javascript:"):
        assert all(
            text not in line or line.startswith("- ````") for line in body.splitlines()
        ), text


def test_the_report_suggests_a_title() -> None:
    github = FakeGitHub()
    run_report(github)

    part = sections(body_of(github))["conventional title"]
    assert "**How to fix it:** Edit the title of the pull request" in part
    assert (
        "**A title that passes:**\n\n```text\nfeat: dark mode for the settings\n```"
        in part
    )


def coach_annotation(title: str) -> dict[str, Any]:
    """An annotation of the PR coach, as the API returns it."""
    return {
        "path": ".github",
        "start_line": 1,
        "annotation_level": "failure",
        "title": title,
        "message": "It broke.",
    }


def test_the_report_explains_each_linter_that_failed_in_lint() -> None:
    github = FakeGitHub()
    # The job of markdown is the one of every linter now.
    github.runs[1]["name"] = "lint"
    github.annotations["52000000002"] += [
        coach_annotation("PR coach: The Markdown of the documents (in lint)"),
        coach_annotation("PR coach: The license of every file (in lint)"),
        # One that the job of another check wrote is no part of lint.
        coach_annotation("PR coach: The workflows (in docs)"),
    ]
    github.runs[1]["output"]["annotations_count"] = 5

    run_report(github)

    part = sections(body_of(github))["lint"]
    assert "**The Markdown of the documents** · <code>markdown</code>" in part
    assert '```sh\nnpx markdownlint-cli2 --fix "**/*.md"\n```' in part
    assert "**The license of every file** · <code>reuse</code>" in part
    assert "<code>workflow-lint</code>" not in part
    # Not the explanation of lint itself, which is for a step before the linters.
    assert "before its linters ran" not in part
    # What markdownlint found, but not the annotations of the coach once more.
    assert "MD022/blanks-around-headings" in part
    assert "It broke." not in part


def test_the_report_suggests_a_title_only_when_the_title_failed() -> None:
    github = FakeGitHub()
    # The check of the title found only that the entry in the changelog is missing.
    github.annotations["52000000004"] = [
        coach_annotation("PR coach: The entry in the changelog (in conventional title)")
    ]

    run_report(github)

    part = sections(body_of(github))["conventional title"]
    assert "**The entry in the changelog** · <code>changelog</code>" in part
    assert "Edit the title of the pull request" not in part
    assert "A title that passes" not in part

    # Both failed: the title, with a title that passes, and the entry.
    github = FakeGitHub()
    # The check of the title names only the parts of other checks.
    github.annotations["52000000004"] = [
        coach_annotation("PR coach: The title of the pull request"),
        coach_annotation(
            "PR coach: The entry in the changelog (in conventional title)"
        ),
    ]
    github.runs[3]["output"]["annotations_count"] = 2

    run_report(github)

    part = sections(body_of(github))["conventional title"]
    assert "**How to fix it:** Edit the title of the pull request" in part
    assert "**A title that passes:**" in part
    assert "**The entry in the changelog** · <code>changelog</code>" in part
    assert part.index("A title that passes") < part.index("<code>changelog</code>")


def test_the_report_names_a_check_without_an_explanation() -> None:
    github = FakeGitHub()
    run_report(github)

    body = body_of(github)
    assert "<summary>❌ <code>e2e (Firefox)</code></summary>" in body
    part = sections(body)["e2e (Firefox)"]
    assert "no explanation of this check yet" in part
    assert "`.github/checks.project.toml`" in part
    # A link that doesn't lead to GitHub is left out.
    assert "evil.example" not in body
    assert "The log of the check" not in part


def test_the_report_follows_the_checks_in_its_one_comment() -> None:
    github = FakeGitHub()
    run_report(github)
    first = body_of(github)

    # Another run of the checks that changes nothing changes nothing.
    assert "is up to date" in run_report(github)
    assert len(github.writes()) == 1

    # The contributor fixes everything but the title; one check still runs.
    github.finish()
    github.runs[3]["conclusion"] = "failure"
    github.runs[7]["status"] = "queued"
    said = run_report(github)
    assert said.startswith("The report of #42, updated:")
    assert github.writes()[-1] == ("PATCH", f"repos/{REPO}/issues/comments/900")
    body = body_of(github)
    assert body != first
    assert "**1 check failed.**" in body
    assert body.count("<details open>") == 1

    # Nothing fails, two still run.
    github.runs[3]["conclusion"] = "success"
    github.runs[8]["status"] = "in_progress"
    run_report(github)
    assert (
        "⏳ No check has failed so far.\n\n2 checks are still running.\n\n<sub>"
    ) in body_of(github)

    # Every check passed.
    github.finish()
    run_report(github)
    body = body_of(github)
    assert "✅ **Every check passed.** Thank you!" in body
    assert "<details" not in body
    assert "still running" not in body
    assert len(github.comments) == 1


def test_a_cancelled_check_has_not_passed() -> None:
    github = FakeGitHub()
    run_report(github)
    github.finish()
    # A job that ran out of time, as GitHub reports it.
    github.runs[8]["conclusion"] = "cancelled"

    run_report(github)

    body = body_of(github)
    assert "Every check passed" not in body
    assert "⏳ No check has failed so far." in body
    assert (
        "⚠️ **1 check stopped before the end**, cancelled or held, and hasn't passed "
        "until it runs again."
    ) in body
    assert "- `codeql` · [its log](https://github.com/Dennis-Otto/demo/" in body
    assert "still running" not in body

    # Two, one of them with a link elsewhere, which is left out.
    github.runs[5].update(conclusion="action_required", html_url="https://evil.example")
    run_report(github)
    body = body_of(github)
    assert "**2 checks stopped before the end**" in body
    assert "haven't passed until they run again" in body
    assert "\n- `reuse`\n" in body
    assert "evil.example" not in body


def test_a_check_that_ran_again_counts_with_its_newest_run() -> None:
    github = FakeGitHub()
    run_report(github)
    github.finish()
    # The contributor edits the title, as the report says: the title check runs again
    # in a check suite of its own and passes, and the API still lists the run that
    # failed. An edit just before had cancelled an older run of another check.
    title, reuse = github.runs[3], github.runs[5]
    github.runs.append(title | {"id": title["id"] - 100, "conclusion": "failure"})
    github.runs.insert(0, reuse | {"id": reuse["id"] - 100, "conclusion": "cancelled"})

    run_report(github)

    body = body_of(github)
    assert "✅ **Every check passed.** Thank you!" in body
    assert "stopped before the end" not in body

    # A check of another app with the same name is a check of its own.
    other = reuse | {"id": reuse["id"] + 100, "app": {"slug": "another-app"}}
    github.runs.append(other | {"conclusion": "failure"})
    run_report(github)
    body = body_of(github)
    assert "**1 check failed.**" in body
    assert "<summary>❌ <b>" in body


def test_many_checks_keep_the_report_and_its_requests_within_bounds() -> None:
    github = FakeGitHub()
    # A fork may add a matrix of hundreds of legs that fail or are cancelled.
    markdown = github.runs[1]
    github.runs = [
        markdown
        | {
            "id": 60000000000 + index,
            "name": f"leg ({index:03})",
            "conclusion": "failure" if index % 2 else "cancelled",
        }
        for index in range(600)
    ]

    run_report(github)

    body = body_of(github)
    assert len(body) < 65536
    assert "**300 checks failed.**" in body
    assert "**300 checks stopped before the end**" in body
    assert "- `leg (008)`" in body
    assert "- `leg (020)`" not in body
    assert "\n- … and 290 more\n" in body
    assert body.count("<details>") == 20
    assert "… and 280 more; their logs say what they found." in body
    annotations = [path for method, path in github.calls if "/annotations?" in path]
    assert len(annotations) == 20


def test_the_coach_waits_for_the_checks_of_other_apps() -> None:
    github = FakeGitHub()
    run_report(github)
    github.finish()
    # The alerts of code scanning, after the last workflow ended.
    github.runs[6].update(status="in_progress", conclusion=None)

    def alerts(github: FakeGitHub) -> None:
        if len(github.waits) == 2:
            github.runs[6].update(status="completed", conclusion="failure")

    github.meanwhile = alerts
    run_report(github)

    assert github.waits == [20, 20]
    body = body_of(github)
    assert "**1 check failed.**" in body
    assert "<code>CodeQL</code>" in body
    assert "still running" not in body


def test_the_coach_waits_for_other_apps_only_a_while() -> None:
    github = FakeGitHub()
    run_report(github)
    github.finish()
    github.runs[6].update(status="queued", conclusion=None)

    run_report(github)

    assert github.waits == [20] * 9
    assert "⏳ No check has failed so far.\n\n1 check is still running." in body_of(
        github
    )


def test_a_variant_keeps_its_own_explanation_with_the_step() -> None:
    github = FakeGitHub()
    github.runs[0]["name"] = "variant (python-package)"

    run_report(github)

    part = sections(body_of(github))["variant (python-package)"]
    # The project that the variant made stopped at the step; the fix is in the
    # template, as the explanation of the variant says, not in this repository.
    assert "It stopped at the step **Ruff** of `scripts/check.sh`." in part
    assert "python -m pytest tests/test_template.py" in part
    assert "ruff format ." not in part
    assert "Then run every check on your machine" not in part


def test_the_fix_rebases_onto_the_main_of_the_repository() -> None:
    github = FakeGitHub()

    run_report(github)

    # Not onto origin/main, which is the fork's own on a pull request from a fork.
    part = sections(body_of(github))["dco"]
    assert (
        f"git fetch https://github.com/{REPO}.git main\n"
        "git rebase --signoff FETCH_HEAD\n"
    ) in part
    assert "origin/main" not in part
    gitleaks = catalog().check("gitleaks")
    assert gitleaks is not None
    assert gitleaks.within(None).commands[0] == (
        "git fetch https://github.com/OWNER/NAME.git main"
    )


@pytest.mark.parametrize("count", [0, 1, 12])
def test_the_report_names_the_commit_of_the_fix_bot(count: int) -> None:
    github = FakeGitHub()
    github.commit = {
        "commit": {"message": f"{FIX_HEADLINE}\n\nMade by the commands"},
        "author": {"login": "app[bot]", "type": "Bot"},
        "files": [{"filename": f"f{number:02}.py"} for number in range(count)],
    }

    body = (run_report(github, 42), body_of(github))[1]

    note = re.search(r"🔧 (.+)\n", body)
    assert note
    if count == 0:
        assert note[1] == (
            f"**The fix bot committed the automatic fixes** in {SHA[:7]}. They are "
            "what the commands of the checks make; pull the branch before you push "
            "again."
        )
    elif count == 1:
        assert f"in {SHA[:7]}: `f00.py`. They are" in note[1]
    else:
        assert "`f09.py` and 2 more. They are" in note[1]
        assert "`f10.py`" not in note[1]


def test_a_commit_of_another_bot_or_of_a_person_is_no_fix() -> None:
    github = FakeGitHub()
    github.commit = {"commit": {"message": FIX_HEADLINE}, "author": {"type": "User"}}
    run_report(github, 42)
    assert "🔧" not in body_of(github)
    github = FakeGitHub()
    github.commit = {"commit": {"message": "chore: x"}, "author": {"type": "Bot"}}
    run_report(github, 42)
    assert "🔧" not in body_of(github)


def test_a_pull_request_whose_checks_never_failed_gets_no_comment() -> None:
    github = FakeGitHub()
    github.finish()

    assert run_report(github, 42) == "No check of #42 failed; it needs no report.\n"
    assert github.writes() == []


def test_a_report_only_for_the_head_of_an_open_pull_request() -> None:
    github = FakeGitHub()
    github.pulls[0]["head"]["sha"] = "0" * 40

    assert "no longer the head of an open pull request" in run_report(github)
    assert "no longer the head" in run_report(github, 42)
    # A number that GitHub doesn't know.
    assert "no longer the head" in run_report(github, 7)
    github.pulls[0]["head"]["sha"] = SHA
    github.pulls[0]["state"] = "closed"
    assert "no longer the head" in run_report(github, 42)
    assert github.writes() == []


class PushedGitHub(FakeGitHub):
    """GitHub, where a push to the pull request comes while the coach reads the
    annotations of its checks."""

    pushed = False

    def route(self, method: str, path: str, body: Any) -> tuple[int, Any]:
        if self.pushed and "/annotations" in path:
            self.pulls[0]["head"]["sha"] = "0" * 40
        return super().route(method, path, body)


def test_a_push_while_the_coach_reads_leaves_the_comment_to_the_new_head() -> None:
    github = PushedGitHub()
    github.pushed = True

    # Neither a second comment next to that of the new head, nor an old report
    # over it.
    assert "is no longer the head of #42; no report" in run_report(github, 42)
    assert github.writes() == []
    github.pulls[0]["head"]["sha"] = SHA
    github.pushed = False
    run_report(github, 42)
    first = body_of(github)
    github.pushed = True
    github.runs[0]["conclusion"] = "success"
    assert "is no longer the head of #42; no report" in run_report(github, 42)
    assert body_of(github) == first
    assert [method for method, _ in github.writes()] == ["POST"]


def test_a_comment_of_someone_else_stays_as_it_is() -> None:
    github = FakeGitHub()
    github.comments.append(
        {"id": 1, "user": {"login": "mallory"}, "body": f"{MARKER}\nkeep me"}
    )
    github.comments.append({"id": 2, "user": None, "body": "Hello"})

    run_report(github, 42)

    assert github.writes() == [("POST", f"repos/{REPO}/issues/42/comments")]
    assert github.comments[0]["body"] == f"{MARKER}\nkeep me"


def test_the_report_reads_every_page(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(blueprint.coach, "PAGE", 2)
    github = FakeGitHub()
    others = [
        {
            "number": number,
            "state": "open",
            "head": {"sha": f"{number:040x}", "ref": "x"},
        }
        for number in range(1, 4)
    ]
    github.pulls = [*others, *github.pulls]
    findings = [
        {
            "path": f"docs/{index}.md",
            "start_line": index,
            "annotation_level": "failure",
            "title": "",
            "message": f"Problem {index}",
        }
        for index in range(13)
    ]
    github.annotations["52000000002"] = findings
    github.runs[1]["output"]["annotations_count"] = 13

    run_report(github)

    part = sections(body_of(github))["markdown"]
    assert "- `docs/9.md:9` `Problem 9`" in part
    assert "docs/10.md" not in part
    assert "- … and 3 more in the log of the check" in part
    assert (
        "GET",
        f"repos/{REPO}/commits/{SHA}/check-runs?per_page=2&page=5",
    ) in github.calls


def test_a_long_report_stays_within_what_github_takes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(blueprint.coach, "BODY_LENGTH", 3000)
    github = FakeGitHub()

    run_report(github)

    body = body_of(github)
    assert len(body) < 3000 + 1000
    assert re.search(r"… and \d more; their logs say what they found\.", body)


def test_report_from_the_command_line(capsys: pytest.CaptureFixture[str]) -> None:
    api = Api(runner=FakeGitHub())
    command = ["--repo", REPO, "coach", "report", SHA, "--pull"]

    assert cli.main([*command, ""], api=api, root=ROOT) == 0
    assert capsys.readouterr().out.startswith("The report of #42:")
    assert cli.main([*command, "42"], api=api, root=ROOT) == 0
    assert "is up to date" in capsys.readouterr().out


@pytest.mark.parametrize(
    "arguments",
    [["coach", "report", "abc"], ["coach", "report", SHA, "--pull", "42; rm"]],
)
def test_report_takes_only_a_commit_and_a_number(
    arguments: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(arguments, api=Api(runner=FakeGitHub())) == 2
    assert "a commit is 40 hex digits" in capsys.readouterr().err


def test_report_with_a_broken_catalog(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(tmp_path, ".github/checks.toml", "[check.lint]\n")

    result = cli.main(
        ["--repo", REPO, "coach", "report", SHA],
        api=Api(runner=FakeGitHub()),
        root=tmp_path,
    )

    assert result == 2
    assert "needs the text title" in capsys.readouterr().err
