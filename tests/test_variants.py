"""Tests of variants.py, which finds the legs of the Variants workflow that a pull
request changes, with a template of a few files and Copier as the plan runs it, all
offline; and once with the template of the blueprint itself."""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import threading
import warnings
from collections.abc import Mapping
from pathlib import Path

import pytest
import workflow_steps
from copier._cli import CopierApp
from shared import copy_of

import variants

ROOT = Path(__file__).parents[1]
COPIER = """\
_subdirectory: template
_answers_file: .copier-answers.yml
project_name:
  type: str
description:
  type: str
project_type:
  type: str
  choices:
    A Home Assistant integration: home-assistant
    A repository without a build: generic
owner:
  type: str
issue_assistant_ai:
  type: bool
  default: true
"""
HOME_ASSISTANT = (
    "template/{% if project_type == 'home-assistant' %}requirements-test.txt"
    "{% endif %}.jinja"
)
FILES = {
    "copier.yml": COPIER,
    ".python-version": "3.12\n",
    "requirements-dev.txt": "copier==9.19.1\n",
    ".github/workflows/variants.yml": "name: Variants\n",
    "variants.py": "# The plan.\n",
    "downstream.py": "# Part of the plan.\n",
    "template/{{ _copier_conf.answers_file }}.jinja": (
        "# The answers of the blueprint\n{{ _copier_answers | to_nice_yaml -}}\n"
    ),
    "template/README.md.jinja": "# {{ project_name }} of {{ owner }}\n",
    # A file of the tool in every project, and the lock file of one kind, which the
    # template includes from outside its folder, as the blueprint does.
    "template/tool.py.jinja": "{% include 'blueprint/tool.py' %}",
    "blueprint/tool.py": "print('The tool')\n",
    HOME_ASSISTANT: "{% include 'stacks/home-assistant/requirements-test.txt' %}",
    "stacks/home-assistant/requirements-test.txt": "pytest==8\n",
    "docs/images/picture.svg": "<svg/>\n",
    "tests/test_template.py": "# The tests.\n",
    "tests/answers/homedarts.yml": (
        "project_name: HomeDarts\ndescription: Darts\n"
        "project_type: home-assistant\nowner: Dennis-Otto\n"
    ),
    "tests/answers/website.yml": (
        "project_name: Website\ndescription: Pages\n"
        "project_type: generic\nowner: Dennis-Otto\n"
    ),
}
KINDS = {
    "variant (home-assistant)": {"kind": "home-assistant", "start": "new"},
    "update (home-assistant)": {"kind": "home-assistant", "start": "update"},
    "variant (generic)": {
        "kind": "generic",
        "start": "new",
        "owner": "octo-org",
        "ai": "false",
    },
    "update (generic)": {"kind": "generic", "start": "update"},
}
ADOPTED = {
    "adopted (homedarts)": {
        "kind": "home-assistant",
        "start": "adopted",
        "answers": "homedarts",
    },
    "adopted (website)": {"kind": "generic", "start": "adopted", "answers": "website"},
}
EVERY = {**KINDS, **ADOPTED}


@pytest.fixture(autouse=True)
def plain_git(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Git without the configuration of the machine, which may sign every commit."""
    config = tmp_path_factory.mktemp("home") / "gitconfig"
    config.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "Test")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "test@example.com")


# The render of the plan, and the lock around Copier in this process.
RENDER = variants.render
ONE_AT_A_TIME = threading.Lock()


def render_here(tree: Path, answers: variants.Answers, folder: Path) -> variants.Files:
    """What variants.render makes, with the same command of Copier in this process: a
    Python of its own takes half a second to import Copier, and most tests render a
    small template a dozen times. Copier changes the process, so one at a time, in the
    folder of the template, as the real one runs. A render that fails goes to the real
    one, which says why."""
    project = folder / "variant"
    command = [
        "copier",
        "copy",
        "--quiet",
        "--defaults",
        *answers,
        tree.as_posix(),
        project.as_posix(),
    ]
    with ONE_AT_A_TIME, contextlib.chdir(tree), warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            code = CopierApp.run(command, exit=False)[1]
        except Exception:
            code = 1
    return RENDER(tree, answers, folder) if code else variants.files_of(project)


@pytest.fixture(autouse=True)
def copier_in_this_process(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(variants, "render", render_here)


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=root, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def write(root: Path, files: Mapping[str, str | None]) -> None:
    for name, content in files.items():
        path = root / name
        if content is None:
            path.unlink()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")


def commit(root: Path, files: Mapping[str, str | None]) -> str:
    write(root, files)
    git(root, "add", "--all")
    git(root, "commit", "--quiet", "--allow-empty", "--message", "A change")
    return git(root, "rev-parse", "HEAD")


@pytest.fixture
def blueprint(tmp_path: Path) -> Path:
    """A template of a few files, with one commit, the main of a pull request."""
    root = tmp_path / "blueprint"
    root.mkdir()
    git(root, "init", "--quiet")
    commit(root, FILES)
    return root


def plan(root: Path, work: Path) -> dict[str, variants.Decision]:
    """The decision on each leg of HEAD against the commit before it, by its name."""
    decisions = variants.decide(root, "HEAD", git(root, "rev-parse", "HEAD^"), work)
    return {decision.leg.name: decision for decision in decisions}


def running(decisions: Mapping[str, variants.Decision]) -> list[str]:
    return [name for name, decision in decisions.items() if decision.runs]


def test_every_leg_of_the_blueprint() -> None:
    # A new repository and an update of each kind of copier.yml, in its order, and an
    # update with each file of tests/answers/, in the order of their names.
    kinds = [
        "home-assistant",
        "nextcloud-app",
        "github-action",
        "python-package",
        "node-package",
        "chrome-extension",
        "container",
        "generic",
    ]
    answers = sorted(path.stem for path in (ROOT / "tests/answers").glob("*.yml"))
    legs = variants.legs_of(ROOT)
    assert [leg.name for leg in legs] == [
        *(f"{start} ({kind})" for kind in kinds for start in ("variant", "update")),
        *(f"adopted ({name})" for name in answers),
    ]
    # Only the new generic repository has another owner and no AI of the assistant.
    others = [leg.matrix for leg in legs if leg.owner or leg.ai]
    assert others == [
        {"kind": "generic", "start": "new", "owner": "octo-org", "ai": "false"}
    ]
    # Each adopted leg with the kind of its answers.
    homedarts = next(leg for leg in legs if leg.answers == "homedarts-for-autodarts")
    assert homedarts.matrix == {
        "kind": "home-assistant",
        "start": "adopted",
        "answers": "homedarts-for-autodarts",
    }


def test_the_plan_renders_a_leg_with_the_answers_of_its_job() -> None:
    # Those that the job names for a new repository, $OWNER and $AI from its matrix.
    script = workflow_steps.step(
        "variants.yml", "variant", "Render the project from this commit"
    )["run"]
    leg = variants.Leg("container", "new", owner="octo-org", ai="false")
    arguments = variants.answers_of(leg)
    assert arguments[::2] == ("--data",) * 5
    expected = {
        "project_name": '--data project_name="Demo Project"',
        "description": (
            "--data \"description=A $KIND of the blueprint's tests,"
            ' with \\"quotes\\" and Ümlauts."'
        ),
        "project_type": '--data project_type="$KIND"',
        "owner": '--data owner="$OWNER"',
        "issue_assistant_ai": '--data issue_assistant_ai="$AI"',
    }
    for text in expected.values():
        assert text in script
    assert dict(item.split("=", 1) for item in arguments[1::2]) == {
        "project_name": "Demo Project",
        "description": (
            'A container of the blueprint\'s tests, with "quotes" and Ümlauts.'
        ),
        "project_type": "container",
        "owner": "octo-org",
        "issue_assistant_ai": "false",
    }
    # The same project for both legs of a kind, which is rendered once. An update takes
    # the default of the AI of the assistant, as the workflow does not name it.
    assert variants.answers_of(variants.Leg("container", "new")) == variants.answers_of(
        variants.Leg("container", "update")
    )
    update = workflow_steps.step(
        "variants.yml",
        "variant",
        "Render the project from the latest release and update it to this commit",
    )["run"]
    assert "issue_assistant_ai" not in update
    # An adopted leg with the answers of its repository.
    assert variants.answers_of(
        variants.Leg("generic", "adopted", answers="website")
    ) == ("--data-file", "tests/answers/website.yml")
    assert '--data-file "$GITHUB_WORKSPACE/tests/answers/$ANSWERS.yml"' in update


def test_a_change_of_documents_and_tests_runs_no_leg(
    blueprint: Path, tmp_path: Path
) -> None:
    commit(
        blueprint,
        {
            "docs/images/picture.svg": "<svg></svg>\n",
            "tests/test_template.py": "# More tests.\n",
        },
    )
    decisions = plan(blueprint, tmp_path / "work")
    assert list(decisions) == list(EVERY)
    assert running(decisions) == []
    assert {decision.why for decision in decisions.values()} == {variants.SAME}


def test_the_lock_file_of_a_stack_runs_only_the_legs_of_that_stack(
    blueprint: Path, tmp_path: Path
) -> None:
    commit(blueprint, {"stacks/home-assistant/requirements-test.txt": "pytest==9\n"})
    decisions = plan(blueprint, tmp_path / "work")
    assert running(decisions) == [
        "variant (home-assistant)",
        "update (home-assistant)",
        "adopted (homedarts)",
    ]
    assert decisions["update (home-assistant)"].why == (
        "their project changes in `requirements-test.txt`"
    )
    assert decisions["update (generic)"].why == variants.SAME


@pytest.mark.parametrize(
    "change",
    [
        {"blueprint/tool.py": "print('Another tool')\n"},
        {"template/README.md.jinja": "# {{ project_name }}\n"},
        # A file that a new version of the template adds or removes.
        {"template/SUPPORT.md": "Ask.\n"},
        {"template/tool.py.jinja": None},
    ],
    ids=["what-it-includes", "changed", "added", "removed"],
)
def test_what_every_project_gets_runs_every_leg(
    blueprint: Path, tmp_path: Path, change: Mapping[str, str | None]
) -> None:
    commit(blueprint, change)
    assert running(plan(blueprint, tmp_path / "work")) == list(EVERY)


@pytest.mark.parametrize("name", variants.EVERY_LEG)
def test_what_every_leg_runs_with_runs_every_leg(
    blueprint: Path, tmp_path: Path, name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_render(*_: object) -> variants.Files:
        raise AssertionError("every leg runs: nothing is rendered")

    monkeypatch.setattr(variants, "render", no_render)
    commit(blueprint, {name: f"{FILES[name]}# A change\n"})
    decisions = plan(blueprint, tmp_path / "work")
    assert running(decisions) == list(EVERY)
    assert decisions["update (generic)"].why == (
        f"`{name}` changes, {variants.EVERY_LEG[name]}"
    )


def test_the_files_of_every_leg_are_files_that_every_leg_runs_with() -> None:
    # Files of the blueprint, under the paths that a change names.
    for name in variants.EVERY_LEG:
        assert (ROOT / name).is_file(), name
    # And what each leg installs before it renders is among them.
    workflow = (ROOT / ".github/workflows/variants.yml").read_text(encoding="utf-8")
    assert "uv pip install --system --require-hashes -r requirements-dev.txt" in (
        workflow
    )
    assert "python-version-file: .python-version" in workflow


def test_a_change_of_answers_runs_only_their_leg(
    blueprint: Path, tmp_path: Path
) -> None:
    # Whatever they render: this answer is one that no file of the template shows.
    commit(
        blueprint,
        {"tests/answers/website.yml": f"{FILES['tests/answers/website.yml']}x: y\n"},
    )
    decisions = plan(blueprint, tmp_path / "work")
    assert running(decisions) == ["adopted (website)"]
    assert decisions["adopted (website)"].why == ("`tests/answers/website.yml` changes")


def test_a_new_canary_runs_its_leg(blueprint: Path, tmp_path: Path) -> None:
    answers = FILES["tests/answers/website.yml"]
    commit(blueprint, {"tests/answers/new.yml": answers})
    decisions = plan(blueprint, tmp_path / "work")
    assert running(decisions) == ["adopted (new)"]


def test_a_canary_that_leaves_has_no_leg(blueprint: Path, tmp_path: Path) -> None:
    commit(blueprint, {"tests/answers/website.yml": None})
    decisions = plan(blueprint, tmp_path / "work")
    assert running(decisions) == []
    assert "adopted (website)" not in decisions


@pytest.mark.parametrize("broken", ["head", "base"])
def test_a_project_that_fails_to_render_runs_every_leg(
    tmp_path: Path, blueprint: Path, broken: str, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = {"template/tool.py.jinja": "{% include 'blueprint/missing.py' %}"}
    if broken == "base":
        commit(blueprint, missing)
        commit(blueprint, {"template/tool.py.jinja": "print('Fixed')\n"})
    else:
        commit(blueprint, missing)
    decisions = plan(blueprint, tmp_path / "work")
    assert running(decisions) == list(EVERY)
    why = decisions["update (generic)"].why
    assert why.startswith("a project failed to render, so nothing shows which legs")
    assert f"project_type=home-assistant from the {broken} commit: " in why
    assert f"::warning title=Variants plan::Every leg runs: {why}\n" in (
        capsys.readouterr().out
    )


def test_no_base_runs_every_leg_without_a_render(
    blueprint: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_render(*_: object) -> variants.Files:
        raise AssertionError("every leg runs: nothing is rendered")

    monkeypatch.setattr(variants, "render", no_render)
    decisions = variants.decide(blueprint, "HEAD", None, tmp_path / "work")
    assert [decision.leg.name for decision in decisions] == list(EVERY)
    assert all(decision.runs for decision in decisions)
    assert {decision.why for decision in decisions} == {variants.EVERY_RUN}


@pytest.mark.skipif(os.name == "nt", reason="Windows keeps no executable bit")
def test_a_script_that_becomes_executable_changes_its_project(
    blueprint: Path, tmp_path: Path
) -> None:
    git(blueprint, "update-index", "--chmod=+x", "template/tool.py.jinja")
    git(blueprint, "commit", "--quiet", "--message", "An executable tool")
    decisions = plan(blueprint, tmp_path / "work")
    assert running(decisions) == list(EVERY)
    assert decisions["update (generic)"].why == "their project changes in `tool.py`"


def test_the_answers_of_a_project_count_but_the_place_of_the_template(
    tmp_path: Path,
) -> None:
    one, other = tmp_path / "one", tmp_path / "other"
    answers = "_src_path: {}\nowner: Dennis-Otto\n"
    write(one, {".copier-answers.yml": answers.format("/here")})
    write(other, {".copier-answers.yml": answers.format("/there")})
    assert variants.files_of(one) == variants.files_of(other)
    write(other, {".copier-answers.yml": answers.format("/there") + "more: answers\n"})
    assert variants.changed_in(variants.files_of(one), variants.files_of(other)) == [
        ".copier-answers.yml"
    ]
    # Only that file and only that line.
    write(one, {"README.md": "_src_path: /here\n"})
    write(other, {"README.md": "_src_path: /there\n"})
    assert "README.md" in variants.changed_in(
        variants.files_of(one), variants.files_of(other)
    )


def test_the_change_of_many_files_fills_no_page() -> None:
    assert variants.listing(["a", "b"]) == "`a`, `b`"
    assert variants.listing(["a", "b", "c"]) == "`a`, `b`, `c`"
    assert variants.listing(["a", "b", "c", "d", "e"]) == "`a`, `b`, `c` and 2 more"


def test_the_command_writes_the_legs_for_the_job_and_why_for_people(
    blueprint: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    base = git(blueprint, "rev-parse", "HEAD")
    commit(blueprint, {"stacks/home-assistant/requirements-test.txt": "pytest==9\n"})
    output, report = tmp_path / "output", tmp_path / "summary"
    arguments = ["--base", base, "--output", str(output), "--summary", str(report)]
    assert variants.main(arguments, blueprint) == 0
    assert capsys.readouterr().out == ""
    matrix, run = output.read_text(encoding="utf-8").splitlines()
    assert matrix.startswith("matrix=")
    assert json.loads(matrix.removeprefix("matrix=")) == {
        "include": [
            KINDS["variant (home-assistant)"],
            KINDS["update (home-assistant)"],
            ADOPTED["adopted (homedarts)"],
        ]
    }
    assert run == "run=true"
    assert report.read_text(encoding="utf-8") == (
        "## The legs of the Variants\n"
        "\n"
        f"3 of 6 legs run against `{base[:7]}`.\n"
        "\n"
        "They run:\n"
        "\n"
        "- `variant (home-assistant)`, `update (home-assistant)`, "
        "`adopted (homedarts)`: their project changes in `requirements-test.txt`.\n"
        "\n"
        "They don't run:\n"
        "\n"
        "- `variant (generic)`, `update (generic)`, `adopted (website)`: their "
        "project stays the same to the byte.\n"
    )


def test_a_plan_without_a_leg_says_so_to_the_job(
    blueprint: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # In the files of the step, as GitHub names them.
    base = git(blueprint, "rev-parse", "HEAD")
    commit(blueprint, {"docs/images/picture.svg": "<svg></svg>\n"})
    output, report = tmp_path / "output", tmp_path / "summary"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(report))
    assert variants.main(["--base", base], blueprint) == 0
    assert output.read_text(encoding="utf-8") == ('matrix={"include":[]}\nrun=false\n')
    summary = report.read_text(encoding="utf-8")
    assert f"0 of 6 legs run against `{base[:7]}`.\n" in summary
    assert "They run:" not in summary
    assert "`adopted (website)`: their project stays the same to the byte." in summary


def test_on_a_machine_the_command_prints_every_leg(
    blueprint: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert variants.main([], blueprint) == 0
    out = capsys.readouterr().out
    assert "6 of 6 legs run.\n" in out
    assert "They don't run:" not in out
    assert f": {variants.EVERY_RUN}.\n" in out
    assert "\nrun=true\n" in out
    matrix = next(line for line in out.splitlines() if line.startswith("matrix="))
    assert json.loads(matrix.removeprefix("matrix="))["include"] == list(EVERY.values())


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"copier.yml": "project_type: {type: str}\n"}, "offers no kind of project"),
        ({"copier.yml": "project_name: {type: str}\n"}, "offers no kind of project"),
        ({"copier.yml": "project_type: [\n"}, "can't be read as YAML"),
        ({"tests/answers/website.yml": "owner: me\n"}, "website.yml names no project"),
    ],
    ids=["no-choices", "no-question", "no-yaml", "no-kind"],
)
def test_a_plan_that_can_name_no_legs_fails(
    blueprint: Path,
    change: Mapping[str, str],
    message: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    commit(blueprint, change)
    assert variants.main(["--base", "HEAD^"], blueprint) == 2
    captured = capsys.readouterr()
    assert captured.err.startswith("variants.py: ")
    assert message in captured.err
    assert captured.out == ""


def test_a_commit_that_is_none_fails(
    blueprint: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert variants.main(["--base", "nothing"], blueprint) == 2
    assert "nothing is no commit" in capsys.readouterr().err


def test_a_repository_without_a_commit_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    git(tmp_path, "init", "--quiet")
    assert variants.main([], tmp_path) == 2
    assert "HEAD could not be read" in capsys.readouterr().err


def test_the_plan_runs_as_a_script(blueprint: Path, tmp_path: Path) -> None:
    # As the job runs it, from a checkout, with its own folder on the import path.
    done = subprocess.run(
        [sys.executable, str(ROOT / "variants.py"), "--help"],
        cwd=tmp_path,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert "--base" in done.stdout


def test_the_template_of_the_blueprint_shows_a_lock_file_in_one_kind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(variants, "render", RENDER)
    # The real template, in a plain copy: the lock file of Home Assistant, as Renovate
    # changes it in #324, is in the projects of that kind only, with default answers
    # or those of a repository, and every required question has its answer.
    tree = tmp_path / "blueprint"
    copy_of(ROOT, tree)
    legs = [
        variants.Leg("home-assistant", "new"),
        variants.Leg("generic", "new", owner="octo-org", ai="false"),
        variants.Leg("home-assistant", "adopted", answers="homedarts-for-autodarts"),
    ]
    renders = [variants.answers_of(leg) for leg in legs]
    before = variants.projects(tree, renders, tmp_path / "before")
    lock = tree / "stacks/home-assistant/requirements-test.txt"
    with lock.open("a", encoding="utf-8", newline="\n") as file:
        file.write("# A new version of a tool.\n")
    # A picture of the documentation, which no project has.
    (tree / "docs/images/picture-of-the-test.svg").write_text(
        "<svg/>", encoding="utf-8"
    )
    after = variants.projects(tree, renders, tmp_path / "after")
    assert variants.changed_in(before[renders[0]], after[renders[0]]) == [
        "requirements-test.txt"
    ]
    assert variants.changed_in(before[renders[1]], after[renders[1]]) == []
    assert variants.changed_in(before[renders[2]], after[renders[2]]) == [
        "requirements-test.txt"
    ]
