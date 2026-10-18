"""Tests of the template: every kind of project renders completely and consistently."""

from __future__ import annotations

import ast
import base64
import configparser
import contextlib
import datetime
import fnmatch
import hashlib
import importlib.util
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import textwrap
import time
import tomllib
import warnings
import zipfile
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any, NamedTuple
from unittest import mock
from xml.etree import ElementTree

import pathspec
import pytest
import workflow_steps
import yaml
from copier import _main as copier_main
from copier import run_copy
from mypy import api as mypy_api
from shared import copy_of, git_environment, once, run_folder
from shell import BASH, in_bash
from workflow_steps import RUN_URL, Answer, exact

import downstream
import pins
from blueprint.bot_health import (
    CRON,
    FAILED,
    LABEL,
    LABEL_COLOR,
    LABEL_DESCRIPTION,
    OWN_ISSUE,
    RENOVATE_LABEL,
    TYPE,
    Cron,
    after_pull_requests,
)
from blueprint.changelog import Fragment, release_changelog
from blueprint.coach import Catalog, missing, undeclared
from blueprint.fixes import fixers
from blueprint.mutation import default_paths
from blueprint.pages import layouts, shown
from blueprint.pr_report import WEBSITE_ARTIFACT, WEBSITE_DAYS
from blueprint.settings import Settings, allows

ROOT = Path(__file__).parents[1]
KINDS = [
    "home-assistant",
    "nextcloud-app",
    "github-action",
    "python-package",
    "node-package",
    "container",
    "generic",
]
# The delimiters of the template; no rendered file may hold them.
LEFTOVER = re.compile(r"\{=|=\}|\[%|%\]")
GUARD = "    # Not in the blueprint itself; generated repositories don't have this line.\n    if: github.repository != 'Dennis-Otto/repo-blueprint'\n"
PINNED = re.compile(
    r"uses: (?:\./|docker://[^@\s]+@sha256:[0-9a-f]{64}|[\w.-]+/[\w./-]+@[0-9a-f]{40})"
)
# The namespace of the elements of psalm.xml.
PSALM = {"psalm": "https://getpsalm.org/schema/config"}
# The settings tool, which every repository gets in .github/: the script that starts
# it and every file of its package. The mutation tests run in a copy of the repository,
# where mutmut keeps what it knows of each module next to it, as cli.py.meta and
# cli.py.spans; those are no part of the tool.
TOOL = sorted(
    [
        "blueprint.py",
        *(
            f"blueprint/{path.name}"
            for path in (ROOT / "blueprint").iterdir()
            if path.is_file() and path.suffix not in (".meta", ".spans")
        ),
    ]
)


class Template:
    """The blueprint as Copier renders it in the tests: the repository itself until the
    fixture template has made a copy of its files, which renders faster."""

    folder = ROOT


# The owner of the projects of the tests, unless a test names another: the owner of the
# blueprint, as in every repository of the Rollout. The question has no default.
OWNER = "Dennis-Otto"


def render(destination: Path, *, overwrite: bool = False, **data: str | bool) -> Path:
    data = {"owner": OWNER, **data}
    with warnings.catch_warnings(), contextlib.ExitStack() as stack:
        # Uncommitted changes of a repository render too, with a warning.
        warnings.simplefilter("ignore")
        # Copier asks Git for each file that it renders whether the index of the
        # destination needs its executable bit: a process for each file, which takes
        # seconds for a project on Windows. The destination of a test is no
        # repository, where Git never needs it.
        if hasattr(copier_main, "is_git_available"):
            stack.enter_context(
                mock.patch.object(copier_main, "is_git_available", return_value=False)
            )
        run_copy(
            str(Template.folder),
            destination,
            data=data,
            defaults=True,
            overwrite=overwrite,
            vcs_ref="HEAD",
            quiet=True,
        )
    return destination


@pytest.fixture(scope="session", autouse=True)
def template(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """The files of the blueprint, copied once for the whole run into a folder without
    Git, from which render() renders. The copy of the Mutation workflow has no Git, and
    renders as it is."""
    if (ROOT / ".git").exists():
        Template.folder = once(
            run_folder(tmp_path_factory) / "copy-of-the-blueprint",
            lambda folder: copy_of(ROOT, folder),
        )
    yield Template.folder
    Template.folder = ROOT


class Projects(Mapping[str, Path]):
    """The project of each kind, rendered when a test first asks for it, once for the
    whole run: with pytest-xdist, the first process that needs a kind renders it, and
    the others wait for it. The tests only read them; one that changes a project works
    on a copy."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder

    def __getitem__(self, kind: str) -> Path:
        if kind not in KINDS:
            raise KeyError(kind)
        return once(
            self.folder / kind,
            lambda project: render(
                project,
                project_name="Demo Project",
                description=f'A {kind} of the tests, with "quotes" and Ümlauts.',
                project_type=kind,
            ),
        )

    def __iter__(self) -> Iterator[str]:
        return iter(KINDS)

    def __len__(self) -> int:
        return len(KINDS)


@pytest.fixture(scope="session")
def projects(tmp_path_factory: pytest.TempPathFactory) -> Mapping[str, Path]:
    return Projects(run_folder(tmp_path_factory) / "projects")


def text_files(project: Path) -> list[Path]:
    files = []
    for path in sorted(project.rglob("*")):
        if path.is_file() and ".git" not in path.parts and path.suffix != ".png":
            files.append(path)
    return files


def workflows(project: Path) -> dict[str, str]:
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in (project / ".github/workflows").glob("*.yml")
    }


def job_of(workflow: str, name: str) -> str:
    """The text of a job of a workflow, up to the next job."""
    start = workflow.index(f"\n  {name}:\n")
    end = re.compile(r"\n\n  [\w-]+:\n").search(workflow, start + 1)
    return workflow[start : end.start() if end else len(workflow)]


def condition_of(job: str) -> str:
    """The condition of a job, on one line."""
    found = re.search(r"^    if: (>-\n(?:      .+\n)+|.+)", job + "\n", re.M)
    assert found, job
    return " ".join(found[1].removeprefix(">-").split())


def triggers(workflow: str) -> dict[str, list[str]]:
    """The events that start a workflow, each with the lines of its settings, without
    their comments."""
    events: dict[str, list[str]] = {}
    settings: list[str] = []
    for line in workflow.split("\non:\n", 1)[1].splitlines():
        if line and not line.startswith(" "):
            break
        if re.match(r"  [\w-]+:", line):
            settings = events.setdefault(line.strip().split(":")[0], [])
        elif line.strip() and not line.lstrip().startswith("#"):
            settings.append(line)
    return events


def paths_of(workflow: str, event: str) -> list[str]:
    """The path filters of an event that starts a workflow, in their order."""
    settings = triggers(workflow)[event]
    patterns = []
    for line in settings[settings.index("    paths:") + 1 :]:
        if not line.startswith("      - "):
            break
        patterns.append(line.removeprefix("      - ").strip('"'))
    return patterns


def runs_for(patterns: list[str], changed: list[str]) -> bool:
    """Whether a change of these files starts a workflow with these path filters, as
    GitHub matches them: in their order, where a later ! takes a path out again."""

    def expression(pattern: str) -> str:
        parts = re.split(r"(\*\*/|\*\*|\*)", pattern)
        wildcards = {"**/": "(?:.*/)?", "**": ".*", "*": "[^/]*"}
        return "".join(wildcards.get(part, re.escape(part)) for part in parts)

    def included(path: str) -> bool:
        result = False
        for pattern in patterns:
            negated = pattern.startswith("!")
            if re.fullmatch(expression(pattern.removeprefix("!")), path):
                result = not negated
        return result

    return any(included(path) for path in changed)


def files_of(root: Path) -> list[str]:
    """The files of a repository, by their paths from its root."""
    if root == ROOT:
        listed = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            capture_output=True,
            check=True,
            text=True,
            env=git_environment(ROOT),
        ).stdout
        return [name for name in listed.split("\0") if name]
    return [
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(root).parts
    ]


def script_of(workflow: str, step: str) -> str:
    """The script of a step of a workflow, as the runner hands it to bash."""
    start = workflow.index(f"      - name: {step}\n")
    run = workflow.index("        run: |\n", start) + len("        run: |\n")
    lines = []
    for line in workflow[run:].splitlines(keepends=True):
        if line.strip() and not line.startswith("          "):
            break
        lines.append(line)
    return textwrap.dedent("".join(lines))


def step_of(workflow: str, start: str) -> str:
    """The text of the step of a workflow whose first line starts with start, such as
    "      - name: Run the checks", up to the next step or job."""
    begin = workflow.index(f"\n{start}") + 1
    end = re.compile(r"\n(?= {0,6}\S)").search(workflow, begin)
    return workflow[begin : end.start() + 1 if end else len(workflow)]


@pytest.mark.parametrize("kind", KINDS)
def test_no_template_syntax_is_left(projects: dict[str, Path], kind: str) -> None:
    for path in text_files(projects[kind]):
        text = path.read_text(encoding="utf-8")
        assert not LEFTOVER.search(text), path
        assert text == "" or text.endswith("\n"), path
        assert "\r" not in text, path
        assert not LEFTOVER.search(str(path.relative_to(projects[kind]))), path


@pytest.mark.parametrize("kind", KINDS)
def test_the_workflows_are_the_blueprints_own(
    projects: dict[str, Path], kind: str
) -> None:
    sources = ROOT / ".github/workflows"
    for name, text in workflows(projects[kind]).items():
        source_name = name
        if name == "ci.yml":
            flavor = re.search(r"^name: CI \((.+)\)$", text, re.M)
            assert flavor, "ci.yml names its flavor"
            source_name = f"ci-{flavor.group(1)}.yml"
        source = (sources / source_name).read_text(encoding="utf-8").replace(GUARD, "")
        if name == "fuzz.yml":
            source = source.replace(
                "stacks/fuzz/requirements.txt", "requirements-fuzz.txt"
            )
        if name == "docs.yml":
            source = source.replace(
                "stacks/docs/requirements-docs.txt", ".github/docs-requirements.txt"
            )
        if name == "codeql.yml":
            source = re.sub(
                r"          # The languages of this repository.*\n          languages: .*\n",
                "",
                source,
            )
            text = re.sub(r"          languages: .*\n", "", text)
        if name in ("after-checks.yml", "update-branches.yml"):
            # The workflows they watch; the bots after the checks and the branch bot
            # test them.
            watched = r"    # The (?:workflows of the )?checks of this repository.*\n(?:    # .*\n)*    workflows: \[.*\]\n"
            source = re.sub(watched, "", source)
            text = re.sub(watched, "", text)
        if name == "bot-health.yml":
            # The bots it watches, without those of the blueprint alone in a project.
            watched = r"    # The bots and the scheduled workflows of every repository.*\n    workflows: \[.*\]\n"
            source = re.sub(watched, "", source)
            text = re.sub(watched, "", text)
        assert text == source, name


@pytest.mark.parametrize("kind", KINDS)
def test_every_action_is_pinned_to_a_commit(
    projects: dict[str, Path], kind: str
) -> None:
    for name, text in workflows(projects[kind]).items():
        # The key alone, not the end of one such as permission-statuses.
        for line in re.findall(r"(?<![\w-])uses: \S+", text):
            assert PINNED.match(line), f"{name}: {line}"


def test_no_workflow_pins_an_action_to_a_branch() -> None:
    # zizmor reports a commit pin whose comment names no version (ref-version-mismatch)
    # as soon as the branch in the comment moves on, and the Findings workflow fails
    # until the pin catches up. A tool that follows its branch on purpose runs as an
    # image. Every workflow of a new repository is one of these.
    for path in sorted((ROOT / ".github/workflows").glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        for action, comment in re.findall(r"uses: (\S+@[0-9a-f]{40})( # \S+)?", text):
            # As Renovate tells a version from a branch: v1, 1.2.3.
            assert re.match(r" # v?\d", comment), f"{path.name}: {action}{comment}"


# The runner of the jobs, named with its version, and the one that the Next runner
# workflow tries every week before the jobs move to it. A move changes both here.
RUNNER = "ubuntu-24.04"
NEXT_RUNNER = "ubuntu-26.04"
# The issue assistant's templates, which its check keeps equal to the action's: the
# issue assistant names their runners in its own repository.
ISSUE_ASSISTANT_WORKFLOWS = {
    "issue-assistant.yml",
    "issue-lifecycle.yml",
    "labels.yml",
    "findings.yml",
}


@pytest.mark.parametrize("project", ["blueprint", *KINDS])
def test_every_job_runs_on_a_runner_named_with_its_version(
    projects: dict[str, Path], project: str
) -> None:
    # GitHub moves ubuntu-latest to a new image one job at a time, over weeks: the
    # runs of one workflow would land on either image at random, and what the new one
    # breaks would look like a flaky test in every repository. Only a pull request
    # moves the jobs, once the variants pass on the next runner.
    root = ROOT if project == "blueprint" else projects[project]
    flows = workflows(root)
    assert set(flows) >= ISSUE_ASSISTANT_WORKFLOWS
    # In workflows of the blueprint alone, which no project has.
    exceptions = {
        # The checks of the blueprint on Windows, as a contributor there runs them.
        ("windows.yml", "windows-2025"),
        # The variants, on the runner that a run by hand or the Next runner names.
        ("variants.yml", f"${{{{ inputs.runner || '{RUNNER}' }}}}"),
    }
    for name, text in flows.items():
        if name in ISSUE_ASSISTANT_WORKFLOWS:
            continue
        jobs = re.findall(r"^  [\w-]+:$", text.split("\njobs:\n", 1)[1], re.M)
        runners = re.findall(r"^    runs-on: (.+)$", text, re.M)
        callers = re.findall(r"^    uses: ", text, re.M)
        # Every job names its runner, but one that calls a workflow, whose jobs do: the
        # Variants, the build and the check of a release here, and OSV-Scanner its own.
        assert len(runners) + len(callers) == len(jobs), name
        for runner in runners:
            assert runner == RUNNER or (name, runner) in exceptions, f"{name}: {runner}"


def test_the_next_runner_runs_the_variants_every_week(
    projects: dict[str, Path],
) -> None:
    flows = workflows(ROOT)
    next_runner, variants = flows["next-runner.yml"], flows["variants.yml"]
    # Every week and by hand, not in pull requests: the next image breaks main and every
    # pull request alike, and none waits for it.
    assert set(triggers(next_runner)) == {"schedule", "workflow_dispatch"}
    job = job_of(next_runner, "next-runner")
    assert "    uses: ./.github/workflows/variants.yml\n" in job
    assert f"    with:\n      runner: {NEXT_RUNNER}\n" in job
    # The issue of a failure names the runner that failed.
    assert f"          RUNNER: {NEXT_RUNNER}\n" in job_of(next_runner, "report")
    # The Variants take the runner from their caller or from a run by hand, and run on
    # the runner of the jobs otherwise: in pull requests and in their own weekly run.
    assert set(triggers(variants)) == {
        "pull_request",
        "schedule",
        "workflow_dispatch",
        "workflow_call",
    }
    assert (
        "        type: choice\n"
        f"        options: [{RUNNER}, {NEXT_RUNNER}]\n"
        f"        default: {RUNNER}\n"
    ) in variants
    assert f"    runs-on: ${{{{ inputs.runner || '{RUNNER}' }}}}\n" in job_of(
        variants, "variant"
    )
    # Neither the required check variants nor any other waits for the next runner.
    settings = tomllib.loads(
        (ROOT / ".github/repository.toml").read_text(encoding="utf-8")
    )
    names = re.findall(r"^    name: (.+)$", next_runner, re.M)
    assert names == ["next runner", "report"]
    assert not set(names) & set(settings["branch"]["required_checks"])
    # The workflow of the blueprint alone, whose variants are those of every project.
    for project in projects.values():
        assert not (project / ".github/workflows/next-runner.yml").exists()


def keep_the_issue_of_a_bot(
    tmp_path: Path, name: str, step: str, open_issue: str, **variables: str
) -> str:
    """Runs the step of the job report that keeps the issue of a bot, with a gh whose
    list of issues finds open_issue, and returns the calls that open, change or close
    an issue, one on each line."""
    done = workflow_steps.run_step(
        tmp_path,
        name,
        "report",
        step,
        answers=[
            Answer(r"issue list --state open .*", f"{open_issue}\n"),
            Answer(r"issue (create|edit|close) .*"),
        ],
        env=variables,
    )
    assert done.returncode == 0, done.stderr
    return "\n".join(done.called("issue (create|edit|close)"))


def only_the_report_writes_issues(name: str) -> None:
    """Only the job report of the workflow may write issues, which runs no code of the
    project, and it needs no other right."""
    assert "issues" not in workflow_steps.workflow(name).get("permissions", {})
    jobs = workflow_steps.workflow(name)["jobs"]
    writers = [
        job_id
        for job_id, settings in jobs.items()
        if "issues" in (settings.get("permissions") or {})
    ]
    assert writers == ["report"]
    assert jobs["report"]["permissions"] == {"issues": "write"}


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize(
    ("result", "open_issue", "call"),
    [
        # A failure opens the issue, or brings the open one up to date.
        ("failure", "", "issue create --title The variants fail on the next runner"),
        ("failure", "7", "issue edit 7 --body"),
        # The next run closes it once the variants pass again.
        ("success", "7", f"issue close 7 --comment The variants pass on {NEXT_RUNNER}"),
        ("success", "", ""),
    ],
)
def test_a_failure_on_the_next_runner_keeps_an_issue_open(
    tmp_path: Path, result: str, open_issue: str, call: str
) -> None:
    # No pull request shows the run, so its warning needs a place of its own.
    report = workflow_steps.job("next-runner.yml", "report")
    assert report["needs"] == "next-runner"
    assert report["if"] == (
        "!cancelled() && github.ref == 'refs/heads/main' && "
        """contains(fromJSON('["success", "failure"]'), needs.next-runner.result)"""
    )
    # Only the job that runs no code of the variants may write issues.
    only_the_report_writes_issues("next-runner.yml")
    calls = keep_the_issue_of_a_bot(
        tmp_path,
        "next-runner.yml",
        "Keep the issue of the next runner current",
        open_issue,
        RESULT=result,
    )

    assert calls.startswith(call), calls
    assert (call == "") == (calls == "")
    assert ("--label maintenance" in calls) == (call.startswith("issue create"))
    assert (f"The Variants workflow fails on {NEXT_RUNNER}," in calls) == (
        result == "failure"
    )
    assert (f"The latest failure: {RUN_URL}" in calls) == (result == "failure")


@pytest.mark.parametrize("project", ["blueprint", *KINDS])
def test_the_required_checks_exist(projects: dict[str, Path], project: str) -> None:
    root = ROOT if project == "blueprint" else projects[project]
    settings = tomllib.loads(
        (root / ".github/repository.toml").read_text(encoding="utf-8")
    )
    names = set()
    for text in workflows(root).values():
        names.update(re.findall(r"^    name: (.+)$", text, re.M))
    for check in settings["branch"]["required_checks"]:
        assert check in names, check


# The actions that listed actions run in turn, which no workflow names: `blueprint.py
# settings check` finds them on GitHub, at the commit of each pin, and names those that
# the list lacks. Each with the action that runs it.
RUN_IN_TURN = {
    "google/osv-scanner-action/osv-reporter-action@*": (
        "google/osv-scanner-action/.github/workflows/osv-scanner-reusable.yml"
    ),
    "google/osv-scanner-action/osv-scanner-action@*": (
        "google/osv-scanner-action/.github/workflows/osv-scanner-reusable.yml"
    ),
    "oven-sh/setup-bun@*": "anthropics/claude-code-action",
}


@pytest.mark.parametrize("project", ["blueprint", *KINDS])
def test_only_the_listed_actions_run(projects: dict[str, Path], project: str) -> None:
    root = ROOT if project == "blueprint" else projects[project]
    settings = Settings.load(root / ".github/repository.toml")
    assert settings.actions["allowed_actions"] == "selected"
    selected = settings.actions["selected"]
    assert selected["github_owned_allowed"] is True
    assert selected["verified_allowed"] is False
    # Every action and reusable workflow that a workflow names may run, or the
    # workflow would fail to start once the settings bot applies the list.
    assert [ref for ref in settings.workflows if not allows(selected, ref)] == []
    # The list names nothing else, other than what these run in turn, in order.
    named = {ref.partition("@")[0].casefold() for ref in settings.workflows}
    patterns = selected["patterns_allowed"]
    for pattern in patterns:
        name = pattern.removesuffix("@*").casefold()
        assert name in named or RUN_IN_TURN[pattern].casefold() in named, pattern
    assert patterns == sorted(patterns, key=str.casefold)


@pytest.mark.parametrize("project", ["blueprint", *KINDS])
def test_a_new_alert_of_codeql_stops_the_merge(
    projects: dict[str, Path], project: str
) -> None:
    root = ROOT if project == "blueprint" else projects[project]
    settings = Settings.load(root / ".github/repository.toml")
    main = next(item for item in settings.rulesets if item["name"] == "Protect main")
    assert main["rules"][-1] == {
        "type": "code_scanning",
        "parameters": {
            "code_scanning_tools": [
                {
                    "tool": "CodeQL",
                    "alerts_threshold": "errors",
                    "security_alerts_threshold": "high_or_higher",
                }
            ]
        },
    }
    # A missing analysis stops a merge too, so CodeQL analyzes every pull request.
    codeql = (root / ".github/workflows/codeql.yml").read_text(encoding="utf-8")
    trigger = re.search(r"^  pull_request:\n((?:    .+\n)*)", codeql, re.M)
    assert trigger, codeql
    assert "paths" not in trigger[1]
    assert "\n    if:" not in job_of(codeql, "codeql")
    assert settings.security["secret_scanning_non_provider_patterns"] is True


@pytest.mark.parametrize("kind", KINDS)
def test_the_versions_agree(projects: dict[str, Path], kind: str) -> None:
    project = projects[kind]
    assert json.loads(
        (project / ".release-please-manifest.json").read_text(encoding="utf-8")
    ) == {".": "0.0.0"}
    config = json.loads(
        (project / "release-please-config.json").read_text(encoding="utf-8")
    )["packages"]["."]
    for extra in config.get("extra-files", []):
        assert "0.0.0" in (project / extra["path"]).read_text(encoding="utf-8"), extra[
            "path"
        ]
    if config["release-type"] == "simple":
        assert (project / "version.txt").read_text(encoding="utf-8") == "0.0.0\n"


@pytest.mark.parametrize("kind", KINDS)
def test_a_breaking_change_below_1_0_0_is_said_to_raise_the_minor_version(
    projects: dict[str, Path], kind: str
) -> None:
    # Below 1.0.0 the release bot raises the minor version for a breaking change, and
    # the release pull request and the contributing guide say so, here and downstream.
    for root in (ROOT, projects[kind]):
        config = json.loads(
            (root / "release-please-config.json").read_text(encoding="utf-8")
        )["packages"]["."]
        assert config["bump-minor-pre-major"] is True
        said = "a major version, or a minor one while the version is below 1.0.0"
        assert f"BREAKING CHANGE: {said})" in config["pull-request-header"]
        contributing = (root / "CONTRIBUTING.md").read_text(encoding="utf-8")
        assert f"`!` {said}." in contributing


@pytest.mark.parametrize("kind", KINDS)
def test_dependabot_watches_existing_folders(
    projects: dict[str, Path], kind: str
) -> None:
    project = projects[kind]
    text = (project / ".github/dependabot.yml").read_text(encoding="utf-8")
    for directory in re.findall(r"directory: (\S+)", text):
        assert (project / directory.lstrip("/")).is_dir(), directory


@pytest.mark.parametrize("kind", KINDS)
def test_every_area_of_the_forms_has_a_label(
    projects: dict[str, Path], kind: str
) -> None:
    project = projects[kind]
    labels = tomllib.loads(
        (project / ".github/labels.toml").read_text(encoding="utf-8")
    )["label"]
    mapped = {option for label in labels for option in label.get("form_options", [])}
    form = (project / ".github/ISSUE_TEMPLATE/bug_report.yml").read_text(
        encoding="utf-8"
    )
    area = form.split("label: Area", 1)[1].split("validations:", 1)[0]
    for option in re.findall(r"^        - (.+)$", area, re.M):
        assert option in mapped or option == "Other", option


def test_someone_sets_every_label(projects: dict[str, Path]) -> None:
    for project in (ROOT, *projects.values()):
        text = (project / ".github/labels.toml").read_text(encoding="utf-8")
        setters = set(re.findall(r"^#   (\w+) ", text, re.MULTILINE))
        labels = tomllib.loads(text)["label"]
        assert {label["group"] for label in labels} <= setters, project
        # Dependabot updates one ecosystem and so sets no label of an ecosystem, only
        # dependencies; Renovate sets none.
        assert "dependencies" in {label["name"] for label in labels}, project
        assert "dependabot" not in setters, project


def test_the_composer_lock_belongs_to_the_composer_json(
    projects: dict[str, Path],
) -> None:
    project = projects["nextcloud-app"]
    manifest = json.loads((project / "composer.json").read_text(encoding="utf-8"))
    lock = json.loads((project / "composer.lock").read_text(encoding="utf-8"))
    keys = [
        "name",
        "version",
        "require",
        "require-dev",
        "conflict",
        "replace",
        "provide",
        "minimum-stability",
        "prefer-stable",
        "repositories",
        "extra",
    ]
    relevant = {key: manifest[key] for key in keys if key in manifest}
    relevant["config"] = {"platform": manifest["config"]["platform"]}
    encoded = json.dumps(dict(sorted(relevant.items())), separators=(",", ":")).replace(
        "/", "\\/"
    )

    assert manifest["name"] == "dennis-otto/demo-project"
    assert manifest["autoload"]["psr-4"] == {"OCA\\DemoProject\\": "lib/"}
    assert (
        lock["content-hash"]
        == hashlib.md5(encoded.encode(), usedforsecurity=False).hexdigest()
    )


def test_the_package_lock_belongs_to_the_package_json(
    projects: dict[str, Path],
) -> None:
    project = projects["node-package"]
    manifest = json.loads((project / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((project / "package-lock.json").read_text(encoding="utf-8"))
    root = lock["packages"][""]

    assert lock["name"] == root["name"] == manifest["name"] == "demo-project"
    assert root["devDependencies"] == manifest["devDependencies"]
    assert root["engines"] == manifest["engines"]
    assert root["license"] == manifest["license"]


@pytest.mark.parametrize(
    ("license_id", "first_line", "holder"),
    [
        ("MIT", "MIT License", True),
        ("MIT-0", "MIT No Attribution", True),
        ("BSD-3-Clause", "Copyright (c) ", True),
        ("Apache-2.0", "Apache License", False),
        ("GPL-3.0-or-later", "GNU GENERAL PUBLIC LICENSE", False),
        ("AGPL-3.0-or-later", "GNU AFFERO GENERAL PUBLIC LICENSE", False),
    ],
)
def test_the_license(
    tmp_path: Path, license_id: str, first_line: str, holder: bool
) -> None:
    project = render(
        tmp_path,
        project_name="Demo",
        description="A demo.",
        project_type="generic",
        license=license_id,
    )
    text = (project / "LICENSE").read_text(encoding="utf-8")
    source = (ROOT / "LICENSES" / f"{license_id}.txt").read_text(encoding="utf-8")

    assert first_line in text.split("\n", 1)[0]
    # One line break at the end, also where the SPDX text has a blank line there.
    assert text.endswith("\n")
    assert not text.endswith("\n\n")
    assert (project / "LICENSES" / f"{license_id}.txt").read_text(
        encoding="utf-8"
    ) == source
    assert f'SPDX-License-Identifier = "{license_id}"' in (
        project / "REUSE.toml"
    ).read_text(encoding="utf-8")
    if holder:
        assert "Copyright" in text
        assert "Dennis Otto" in text
        assert not re.search(
            r"<(year|owner|YEAR|COPYRIGHT HOLDER)>|\[(year|fullname)\]", text
        )
    else:
        # Long licenses stay verbatim, appendix included.
        assert text == source.rstrip("\n") + "\n"


def test_a_project_without_a_sponsor(tmp_path: Path) -> None:
    project = render(
        tmp_path,
        project_name="Demo",
        description="A demo.",
        project_type="generic",
        sponsor="",
    )

    assert not (project / ".github/FUNDING.yml").exists()
    assert "sponsor" not in (project / "README.md").read_text(encoding="utf-8").lower()


def test_the_blueprint_follows_its_own_template(tmp_path: Path) -> None:
    project = render(
        tmp_path,
        project_name="Repo Blueprint",
        project_slug="repo-blueprint",
        description="A Copier template for GitHub repositories, with tests, releases, security checks and bots built in, for seven kinds of projects.",
        project_type="github-action",
        python_package="blueprint",
        license="MIT-0",
        successor=True,
        homepage="https://dennis-otto.github.io/repo-blueprint/",
    )
    for name in (
        ".bestpractices.json",
        ".editorconfig",
        ".gitattributes",
        ".gitignore",
        ".python-version",
        "CLAUDE.md",
        "CODE_OF_CONDUCT.md",
        "GOVERNANCE.md",
        "LICENSE",
        "SECURITY.md",
        "SUPPORT.md",
        "release-please-config.json",
        "scripts/check.sh",
        "scripts/diagrams.sh",
        ".github/FUNDING.yml",
        ".github/findings.toml",
        ".github/checks.toml",
        ".github/pull_request_template.md",
        ".github/ISSUE_TEMPLATE/config.yml",
        ".github/ISSUE_TEMPLATE/feature_request.yml",
        ".github/DISCUSSION_TEMPLATE/q-a.yml",
        ".github/DISCUSSION_TEMPLATE/ideas.yml",
        ".github/social-preview/Dockerfile",
        ".github/actionlint.yaml",
        ".github/egress-firewall.yaml",
        ".github/markdownlint.jsonc",
        ".github/prose/cspell.json",
        ".github/prose/package.json",
        ".github/prose/package-lock.json",
        ".github/a11y/check.mjs",
        ".github/a11y/package.json",
        ".github/a11y/package-lock.json",
        ".github/mkdocs-blueprint.css",
        ".github/mkdocs-blueprint.js",
        ".github/cspell-words.txt",
        ".vale.ini",
        ".github/sign-tag.sh",
        ".github/renovate-blueprint.json5",
        ".github/mkdocs-blueprint.yml",
        ".github/mkdocs_blueprint.py",
        ".markdownlint-cli2.jsonc",
        ".markdownlint.jsonc",
        ".devcontainer/devcontainer.json",
        ".devcontainer/devcontainer-lock.json",
        ".devcontainer/Dockerfile",
        ".devcontainer/setup.sh",
    ):
        own = (ROOT / name).read_text(encoding="utf-8")
        if name == ".devcontainer/setup.sh":
            # The blueprint keeps the tools of the website in stacks/docs/, from where
            # every repository gets them as .github/docs-requirements.txt.
            own = own.replace(
                "stacks/docs/requirements-docs.txt", ".github/docs-requirements.txt"
            )
        if name == "SECURITY.md":
            own = as_an_action(own)
        assert own == (project / name).read_text(encoding="utf-8"), name


def as_an_action(security: str) -> str:
    """The security policy of the blueprint as that of the GitHub Action it is
    rendered as: the blueprint is a template, so a repository made from it receives a
    fix with its blueprint bot, which verifies the signed tag of a release, where users
    of an action pin a commit."""
    security, supported = re.subn(
        r"A repository made from the blueprint receives a fix .*",
        "Repositories that use the action pin its commit hash; merge the update pull"
        " request of Dependabot or Renovate for a new release to receive a fix.",
        security,
    )
    security, verified = re.subn(
        r"Copier renders a repository from the tag of a release.*?\n```\n",
        "Repositories that use the action pin the commit hash of a release;"
        " `gh release verify` shows which commit the tag of a release stands for.\n",
        security,
        flags=re.DOTALL,
    )
    # The Dashboard workflow publishes the website of the blueprint, with the
    # dashboard, where the Docs workflow publishes that of every other repository.
    security, website = re.subn(
        r"(## Verify the website\n.*?)(?=\n## )",
        lambda section: (
            section[1]
            .replace("The Dashboard workflow", "The Docs workflow")
            .replace("/.github/workflows/dashboard.yml", "/.github/workflows/docs.yml")
        ),
        security,
        flags=re.DOTALL,
    )
    assert (supported, verified, website) == (1, 1, 1)
    return security


@pytest.mark.parametrize("kind", ["python-package", "github-action"])
def test_python_projects_are_fuzzed(projects: dict[str, Path], kind: str) -> None:
    project = projects[kind]

    assert (project / "fuzz/fuzz_demo_project.py").read_text(encoding="utf-8").count(
        "import atheris"
    ) == 1
    assert "atheris==" in (project / "requirements-fuzz.txt").read_text(
        encoding="utf-8"
    )
    assert "FuzzingID" not in (project / ".github/findings.toml").read_text(
        encoding="utf-8"
    )


@pytest.mark.parametrize("kind", KINDS)
def test_every_repository_gets_the_settings_tool(
    projects: dict[str, Path], kind: str
) -> None:
    github = projects[kind] / ".github"
    copies = sorted(
        path.relative_to(github).as_posix()
        for path in [github / "blueprint.py", *(github / "blueprint").iterdir()]
        if path.is_file()
    )

    assert copies == TOOL
    for name in TOOL:
        copy = (github / name).read_text(encoding="utf-8")
        assert copy == (ROOT / name).read_text(encoding="utf-8"), name


# In the copy of the mutation tests, the tool is the code with the mutants, which the
# variables of mutmut switch in the process that this test starts.
@pytest.mark.mutation_unsafe
@pytest.mark.parametrize("kind", KINDS)
def test_the_settings_tool_runs_in_every_repository(
    projects: dict[str, Path], kind: str, tmp_path: Path
) -> None:
    # On a copy, and without the folder for bytecode of the run, so that a tool that
    # wrote __pycache__ would write it here, and not into the project of every test.
    project = shutil.copytree(projects[kind], tmp_path / kind)
    # As the workflows run it: the script imports the package next to it.
    result = subprocess.run(
        [sys.executable, ".github/blueprint.py", "--help"],
        cwd=project,
        capture_output=True,
        encoding="utf-8",
        env=without_bytecode_prefix(os.environ),
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("usage: blueprint.py")
    assert "The settings of a repository as code" in result.stdout
    # Like the single file it was, the tool leaves no __pycache__ in the repository.
    assert not (project / ".github/blueprint/__pycache__").exists()


def without_bytecode_prefix(environment: Mapping[str, str]) -> dict[str, str]:
    """The environment in which Python writes __pycache__ next to the code: without
    PYTHONPYCACHEPREFIX, which the run sets for every test, and without
    PYTHONDONTWRITEBYTECODE, which a machine may set. Either would keep __pycache__ out
    of the repository whatever the tool does."""
    return {
        name: value
        for name, value in environment.items()
        if name not in {"PYTHONPYCACHEPREFIX", "PYTHONDONTWRITEBYTECODE"}
    }


def test_the_settings_tool_keeps_the_ruff_settings_of_the_blueprint() -> None:
    # Ruff uses the closest configuration of each file and no other: in a repository,
    # .github/blueprint/ keeps these settings, not those of the project.
    own = tomllib.loads((ROOT / "blueprint/ruff.toml").read_text(encoding="utf-8"))
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert own.pop("src") == [".."]
    assert own == pyproject["tool"]["ruff"]


def settings_code() -> list[str]:
    """The modules of the package whose code settings apply runs: the command line,
    blueprint.settings and what it imports of the package, and so on."""
    found = {"__init__.py", "cli.py"}
    unread = ["settings.py"]
    while unread:
        name = unread.pop()
        found.add(name)
        tree = ast.parse((ROOT / "blueprint" / name).read_text(encoding="utf-8"))
        imported = [
            f"{node.module.removeprefix('blueprint.')}.py"
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith("blueprint.")
        ]
        unread += [module for module in imported if module not in found]
    return sorted(found)


@pytest.mark.parametrize("kind", KINDS)
def test_the_settings_bot_runs_when_its_code_changes(
    projects: dict[str, Path], kind: str
) -> None:
    # A release of the blueprint that changes how a setting is applied reaches GitHub
    # with the merge of its update, not with the weekly run.
    rendered = paths_of(workflows(projects[kind])["settings.yml"], "push")
    own = paths_of(
        (ROOT / ".github/workflows/settings.yml").read_text(encoding="utf-8"), "push"
    )
    modules = settings_code()

    assert {"github.py", "settings.py"} < set(modules)
    for name in modules:
        assert runs_for(rendered, [f".github/blueprint/{name}"]), name
        assert runs_for(own, [f"blueprint/{name}"]), name
    for path in (
        ".github/blueprint.py",
        ".github/repository.toml",
        ".github/repository.project.toml",
        ".github/workflows/settings.yml",
    ):
        assert runs_for(rendered, [path]), path
    # A workflow or an action that runs a new action, also in turn: the check of the
    # allowed actions comes with its merge.
    for path in (
        ".github/workflows/ci.yml",
        ".github/actions/setup/action.yml",
        "action.yml",
    ):
        assert runs_for(rendered, [path]), path
        assert runs_for(own, [path]), path
    assert runs_for(own, ["blueprint.py"])
    # In the blueprint, a change of another bot starts no run.
    assert not runs_for(own, ["blueprint/coach.py"])
    # A change of the labels is the Labels workflow's: two workflows that create the
    # same label at once would fail one of them.
    assert not runs_for(rendered, [".github/labels.toml"])


def test_the_readme_of_an_integration_works_in_hacs(projects: dict[str, Path]) -> None:
    # HACS shows the README outside GitHub, where relative links lead nowhere.
    readme = (projects["home-assistant"] / "README.md").read_text(encoding="utf-8")

    for target in re.findall(r"\]\(([^)\s]+)\)", readme):
        assert target.startswith(("https://", "#")), target


def test_an_integration_is_validated_by_the_current_images_of_hacs_and_hassfest(
    projects: dict[str, Path],
) -> None:
    ci = (projects["home-assistant"] / ".github/workflows/ci.yml").read_text(
        encoding="utf-8"
    )
    # Their moving images, as their actions run them, but without the actions: a pin
    # to a commit of their branches falls behind with every commit to them.
    assert "uses: hacs/action" not in ci
    assert "uses: home-assistant/actions" not in ci
    hacs = job_of(ci, "hacs")
    validation = hacs[: hacs.index("      # The PR coach needs")]
    assert validation.endswith("\n            ghcr.io/hacs/action:main\n")
    # HACS reads the repository through the API, so the job checks nothing out but
    # what the PR coach needs when it failed.
    assert "actions/checkout" not in validation
    assert hacs.count("actions/checkout") == 1
    # hassfest checks the checkout, read-only, exactly as the Variants workflow does.
    command = (
        'docker run --rm --volume "$PWD:/github/workspace:ro"'
        " ghcr.io/home-assistant/hassfest:latest\n"
    )
    assert command in job_of(ci, "hassfest")
    variants = (ROOT / ".github/workflows/variants.yml").read_text(encoding="utf-8")
    assert command.replace("$PWD", "$PWD/$PROJECT") in variants


def run_the_step_with_docker(
    tmp_path: Path, job: str, environment: dict[str, str]
) -> tuple[str, list[str]]:
    # The step runs in the folder workspace/, as in the checkout of a runner.
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    # Its script, up to the next step, such as the one of the PR coach.
    step = job[job.index("        run: |\n") + len("        run: |\n") :]
    end = re.search(r"^      [-#]", step, re.M)
    script = textwrap.dedent(step[: end.start()] if end else step)
    (workspace / "step.sh").write_text(script, encoding="utf-8", newline="\n")
    # docker writes down what the container would get: its variables, its mounts,
    # with the folder of the step as $PWD, its folder, its image and its command.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(
        """#!/usr/bin/env bash
[[ "$1" == run ]] || exit 1
shift
while (($#)); do
  case "$1" in
    --rm) ;;
    --env) shift; if [[ "$1" == *=* ]]; then echo "env $1"; else echo "env $1=${!1}"; fi ;;
    --volume) shift; echo "volume ${1/#"$PWD"/\\$PWD}" ;;
    --workdir) shift; echo "workdir $1" ;;
    *) echo "image $1"; shift; if (($#)); then echo "command $*"; fi; break ;;
  esac
  shift
done >> "$CALLS"
""",
        encoding="utf-8",
        newline="\n",
    )
    docker.chmod(0o755)
    calls = tmp_path / "calls"
    calls.touch()
    # As GitHub runs a step: bash -e.
    assert BASH
    result = subprocess.run(
        [BASH, "-e", "step.sh"],
        cwd=workspace,
        env={
            **os.environ,
            **environment,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "CALLS": str(calls),
        },
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout, calls.read_text(encoding="utf-8").splitlines()


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
def test_hacs_gets_the_inputs_of_its_action(
    projects: dict[str, Path], tmp_path: Path
) -> None:
    ci = (projects["home-assistant"] / ".github/workflows/ci.yml").read_text(
        encoding="utf-8"
    )
    hacs = job_of(ci, "hacs")
    # The inputs of the action reach its image as INPUT_ variables, as GitHub passes
    # them, and the event as a file, from which it reads the branch to validate.
    inputs = {
        name: value.strip('"').replace("${{ github.token }}", "the token")
        for name, value in re.findall(r"^          (INPUT_\w+): (.+)$", hacs, re.M)
    }
    event = (tmp_path / "event.json").as_posix()

    _, calls = run_the_step_with_docker(
        tmp_path,
        hacs,
        {**inputs, "GITHUB_REPOSITORY": "o/r", "GITHUB_EVENT_PATH": event},
    )

    assert calls == [
        "env INPUT_CATEGORY=integration",
        "env INPUT_COMMENT=false",
        "env INPUT_GITHUB_TOKEN=the token",
        "env GITHUB_REPOSITORY=o/r",
        "env GITHUB_EVENT_PATH=/github/workflow/event.json",
        f"volume {event}:/github/workflow/event.json:ro",
        "image ghcr.io/hacs/action:main",
    ]


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
def test_hassfest_shows_its_errors_as_annotations(
    projects: dict[str, Path], tmp_path: Path
) -> None:
    ci = (projects["home-assistant"] / ".github/workflows/ci.yml").read_text(
        encoding="utf-8"
    )
    runner_temp = tmp_path / "runner"
    runner_temp.mkdir()

    output, calls = run_the_step_with_docker(
        tmp_path, job_of(ci, "hassfest"), {"RUNNER_TEMP": runner_temp.as_posix()}
    )

    assert calls == [
        "volume $PWD:/github/workspace:ro",
        "image ghcr.io/home-assistant/hassfest:latest",
    ]
    # The problem matcher of its action turns each error and warning into one.
    assert f"::add-matcher::{runner_temp.as_posix()}/hassfest.json\n" in output
    matcher = json.loads((runner_temp / "hassfest.json").read_text(encoding="utf-8"))
    pattern = matcher["problemMatcher"][0]["pattern"][0]
    error = re.match(
        pattern["regexp"],
        "* [ERROR] [MANIFEST] Invalid manifest: value must be one of"
        " ['assumed_state', 'calculated'] at 'iot_class'. Got 'nonsense'",
    )
    assert error
    assert error[pattern["severity"]] == "ERROR"
    assert error[pattern["message"]].startswith("[MANIFEST] Invalid manifest: ")
    assert not re.match(pattern["regexp"], "Integrations: 1")


HADOLINT = re.compile(r"ghcr\.io/hadolint/hadolint:v\d+\.\d+\.\d+@sha256:[0-9a-f]{64}")


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
def test_hadolint_runs_in_its_image_and_shows_its_findings_as_annotations(
    projects: dict[str, Path], tmp_path: Path
) -> None:
    # Not by its action, whose Dockerfile every job that names it built at its start,
    # in the Variants all fourteen, although only the container needs it.
    for folder in (ROOT, *projects.values()):
        for name, text in workflows(folder).items():
            assert "hadolint/hadolint-action" not in text, name
    ci = (projects["container"] / ".github/workflows/ci.yml").read_text(
        encoding="utf-8"
    )
    step = step_of(ci, "      - name: Lint the Dockerfile")
    image = HADOLINT.search(step)
    assert image
    runner_temp = tmp_path / "runner"
    runner_temp.mkdir()

    output, calls = run_the_step_with_docker(
        tmp_path, step, {"RUNNER_TEMP": runner_temp.as_posix()}
    )

    # In the checkout, read-only, where Hadolint finds the .hadolint.yaml of the
    # project and names the file as GitHub knows it.
    assert calls == [
        "volume $PWD:/repo:ro",
        "workdir /repo",
        f"image {image[0]}",
        "command hadolint --no-color Dockerfile",
    ]
    # The problem matcher of its action turns each finding into an annotation, of
    # this step alone: it goes when the step ends, also when Hadolint fails, before
    # the checks of the image, whose output it would otherwise read as findings too.
    assert f"::add-matcher::{runner_temp.as_posix()}/hadolint.json\n" in output
    assert output.endswith("::remove-matcher owner=hadolint::\n")
    assert "trap 'echo \"::remove-matcher owner=hadolint::\"' EXIT\n" in step
    matcher = json.loads((runner_temp / "hadolint.json").read_text(encoding="utf-8"))
    pattern = matcher["problemMatcher"][0]["pattern"][0]
    # As Hadolint 2.15 writes a finding without colors.
    finding = re.match(
        pattern["regexp"],
        "Dockerfile:2 DL3018 warning: Pin versions in apk add."
        " Instead of `apk add <package>` use `apk add <package>=<version>`",
    )
    assert finding
    assert finding[pattern["file"]] == "Dockerfile"
    assert finding[pattern["line"]] == "2"
    assert finding[pattern["code"]] == "DL3018"
    assert finding[pattern["severity"]] == "warning"
    assert finding[pattern["message"]].startswith("Pin versions in apk add.")
    assert not re.match(
        pattern["regexp"], "Dockerfile:2 DL3018 \x1b[93mwarning\x1b[0m: x"
    )
    # The Variants workflow runs the same image in the container it renders, and only
    # there.
    variants = (ROOT / ".github/workflows/variants.yml").read_text(encoding="utf-8")
    lint = step_of(variants, "      - name: Lint the Dockerfile")
    assert (
        "        if: matrix.start != 'adopted' && matrix.kind == 'container'\n" in lint
    )
    command = step[step.index("docker run ") :].rstrip()
    assert lint.rstrip().endswith(command.replace('"$PWD:', '"$PWD/$PROJECT:'))
    assert HADOLINT.findall(variants) == [image[0]]


@pytest.mark.parametrize("kind", KINDS)
def test_python_projects_run_property_tests_every_night(
    projects: dict[str, Path], kind: str
) -> None:
    project = projects[kind]
    workflow = project / ".github/workflows/properties.yml"

    if kind in ("home-assistant", "python-package", "github-action"):
        assert workflow.exists()
        assert 'settings.register_profile("local"' in (
            project / "tests/conftest.py"
        ).read_text(encoding="utf-8")
    else:
        assert not workflow.exists()


def test_several_copyright_holders(tmp_path: Path) -> None:
    project = render(
        tmp_path,
        project_name="Demo",
        description="A demo.",
        project_type="generic",
        copyright="2024 Example contributors; 2026 Dennis Otto",
    )

    lines = (project / "LICENSE").read_text(encoding="utf-8").splitlines()
    assert lines[2:4] == [
        "Copyright (c) 2024 Example contributors",
        "Copyright (c) 2026 Dennis Otto",
    ]
    reuse = tomllib.loads((project / "REUSE.toml").read_text(encoding="utf-8"))
    assert reuse["annotations"][0]["SPDX-FileCopyrightText"] == [
        "2024 Example contributors",
        "2026 Dennis Otto",
        "Contributors to Demo",
    ]


@pytest.mark.parametrize("kind", KINDS)
def test_every_project_has_a_dev_container(
    projects: dict[str, Path], kind: str
) -> None:
    project = projects[kind]
    config = json.loads(
        (project / ".devcontainer/devcontainer.json").read_text(encoding="utf-8")
    )
    dockerfile = (project / ".devcontainer/Dockerfile").read_text(encoding="utf-8")
    setup = (project / ".devcontainer/setup.sh").read_text(encoding="utf-8")

    assert config["postCreateCommand"] == "bash .devcontainer/setup.sh"
    # Every Feature is locked; Docker for all, Node for the projects with a frontend.
    lock = json.loads(
        (project / ".devcontainer/devcontainer-lock.json").read_text(encoding="utf-8")
    )
    assert set(config["features"]) == set(lock["features"])
    node = "ghcr.io/devcontainers/features/node:2" in config["features"]
    assert node == (kind in ("home-assistant", "nextcloud-app"))
    if node:
        # The Features that Dependabot keeps current in the blueprint.
        watched = json.loads(
            (ROOT / "stacks/devcontainer/.devcontainer/devcontainer.json").read_text(
                encoding="utf-8"
            )
        )
        assert watched["features"] == config["features"]
    assert re.search(
        r"^FROM mcr\.microsoft\.com/devcontainers/\S+@sha256:[0-9a-f]{64}$",
        dockerfile,
        re.M,
    )
    assert "git config core.hooksPath .githooks" in setup
    # Where Git ignores the modes of the files, the hook gets its mode on disk.
    assert "chmod +x .githooks/*" in setup
    requirements = {
        "home-assistant": "requirements-test.txt",
        "python-package": "requirements-dev.txt",
        "github-action": "requirements-dev.txt",
    }
    if kind in requirements:
        assert f"-r {requirements[kind]}" in setup
        assert (project / requirements[kind]).exists()
        assert "charliermarsh.ruff" in config["customizations"]["vscode"]["extensions"]
    biome = "biomejs.biome" in config["customizations"]["vscode"]["extensions"]
    assert biome == (kind == "node-package")


@pytest.mark.parametrize("kind", KINDS)
def test_npm_never_runs_the_install_scripts_of_the_packages(
    projects: dict[str, Path], kind: str
) -> None:
    # The scripts that a package runs as it installs are how a package that was taken
    # over reaches a machine: the CI, the dev container and every command that the
    # documentation gives install without them.
    project = projects[kind]
    for path in text_files(project):
        text = path.read_text(encoding="utf-8", errors="replace")
        for line in re.findall(r"^.*\bnpm ci\b.*$", text, re.MULTILINE):
            assert "--ignore-scripts" in line, f"{path.relative_to(project)}: {line}"
    if kind == "node-package":
        setup = (project / ".devcontainer/setup.sh").read_text(encoding="utf-8")
        assert "\nnpm ci --ignore-scripts\n" in setup
        for name in ("CONTRIBUTING.md", "AGENTS.md"):
            text = (project / name).read_text(encoding="utf-8")
            assert "npm ci --ignore-scripts\nbash scripts/check.sh\n" in text, name


@pytest.mark.parametrize("kind", KINDS)
def test_npx_never_fetches_a_package_in_place_of_biome(
    projects: dict[str, Path], kind: str
) -> None:
    # The unscoped package `biome` on npm is not Biome: without --no, npx fetches
    # and runs it when @biomejs/biome is not installed, and in the CI or for an
    # agent it asks no question first. Every documented install skips the scripts.
    project = projects[kind]
    for path in text_files(project):
        text = path.read_text(encoding="utf-8", errors="replace")
        where = path.relative_to(project)
        for line in re.findall(r"^.*\bnpx\b.*\bbiome\b.*$", text, re.MULTILINE):
            assert not re.search(r"\bnpx (?!--no -- )", line), f"{where}: {line}"
        adds = r"^.*\bnpm (?:install|i) (?:--save-dev|-D)\b.*$"
        for line in re.findall(adds, text, re.MULTILINE):
            assert "--ignore-scripts" in line, f"{where}: {line}"


@pytest.mark.parametrize("kind", KINDS)
def test_a_node_package_lints_and_formats_its_code_with_biome(
    projects: dict[str, Path], kind: str
) -> None:
    project = projects[kind]
    check = (project / "scripts/check.sh").read_text(encoding="utf-8")
    node = kind == "node-package"

    assert (project / "biome.jsonc").is_file() == node
    assert ('\nstep "Lint and format"\n' in check) == node
    if not node:
        return
    # Before the types and the tests, as Ruff in a Python project; a warning fails.
    assert check.index('\nstep "Lint and format"\n') < check.index('\nstep "Types"\n')
    assert "\n  npx --no -- biome ci --error-on-warnings .\n" in check
    manifest = json.loads((project / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((project / "package-lock.json").read_text(encoding="utf-8"))
    assert "@biomejs/biome" in manifest["devDependencies"]
    # Locked with its hash, as every package of the lock.
    biome = lock["packages"]["node_modules/@biomejs/biome"]
    assert biome["integrity"].startswith("sha512-")
    # The settings: the files of the blueprint in .github/ keep its format, and the
    # indentation comes from .editorconfig, which has it for JSONC too.
    settings = (project / "biome.jsonc").read_text(encoding="utf-8")
    config = json.loads(re.sub(r"^//.*\n", "", settings, flags=re.MULTILINE))
    assert config["files"]["includes"] == ["**", "!.github"]
    assert config["formatter"]["useEditorconfig"] is True
    assert config["linter"]["rules"]["preset"] == "recommended"
    assert config["vcs"]["useIgnoreFile"] is True
    editorconfig = configparser.ConfigParser()
    editorconfig.read_string(
        "[top]\n" + (project / ".editorconfig").read_text(encoding="utf-8")
    )
    assert editorconfig["*.{json,jsonc,toml,yml,yaml,ts,js,mjs}"]["indent_size"] == "2"
    # The coverage of the tests as the LCOV report that the CI keeps, which git and
    # the package leave out.
    assert "--test-reporter-destination=lcov.info" in manifest["scripts"]["test"]
    assert (
        "--test-reporter=spec --test-reporter-destination=stdout"
        in (manifest["scripts"]["test"])
    )
    ignored = (project / ".gitignore").read_text(encoding="utf-8").split("\n")
    assert "/lcov.info" in ignored
    assert manifest["files"] == ["dist"]


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize("listed", [True, False])
def test_the_lint_of_a_node_package_waits_for_biome_in_its_package_json(
    projects: dict[str, Path], tmp_path: Path, listed: bool
) -> None:
    # package.json belongs to the project: one from before the blueprint brought Biome
    # lacks it, and the step says how to add it instead of failing the update.
    check = (projects["node-package"] / "scripts/check.sh").read_text(encoding="utf-8")
    start = check.index('step "Lint and format"')
    script = (
        check[: check.index('step "Text files"')]
        + check[start : check.index('step "Types"', start)]
    )
    repository = tmp_path / "repository"
    subprocess.run(["git", "init", "--quiet", str(repository)], check=True)
    manifest = json.loads(
        (projects["node-package"] / "package.json").read_text(encoding="utf-8")
    )
    if not listed:
        del manifest["devDependencies"]["@biomejs/biome"]
    (repository / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    calls = tmp_path / "calls"
    (stubs / "npx").write_text(
        f"#!/usr/bin/env bash\necho \"$*\" >> '{calls.as_posix()}'\n",
        encoding="utf-8",
        newline="\n",
    )
    (stubs / "npx").chmod(0o755)

    result = run_the_steps(
        repository, script, path=f"{stubs}{os.pathsep}{os.environ['PATH']}", ci=True
    )

    assert result.returncode == 0, result.stdout + result.stderr
    if listed:
        assert result.stdout == "\n== Lint and format\n"
        assert calls.read_text(encoding="utf-8") == (
            "--no -- biome ci --error-on-warnings .\n"
        )
    else:
        assert result.stdout == (
            "\n== Lint and format\npackage.json lacks @biomejs/biome, which lints and "
            "formats the code; add it: npm install --save-dev --ignore-scripts "
            "@biomejs/biome\n"
        )
        assert not calls.exists()


def renders_a_script(path: Path) -> bool:
    """Whether the file of the blueprint is, or renders as, a script with a shebang:
    a file of the template that only includes another renders as that one."""
    text = path.read_bytes()
    include = re.fullmatch(rb'\[% include "([^"]+)" -%\]\n?', text)
    if include:
        text = (ROOT / include.group(1).decode()).read_bytes()
    return text.startswith(b"#!")


# It asks Git for the modes of the files, which the copy of the mutation tests has none
# of.
@pytest.mark.mutation_unsafe
def test_every_script_of_the_blueprint_is_executable_in_git() -> None:
    # Copier gives a file of a new repository the mode that Git has for it in the
    # template, on Windows too, and the blueprint bot brings a new mode to an existing
    # repository. Git runs a hook only when it is executable: the pre-push hook was a
    # plain file, which Git on Linux, macOS, in the dev container and in Codespaces
    # skipped, so that a push went through with failing checks.
    listing = subprocess.run(
        ["git", "ls-files", "--stage", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        env=git_environment(ROOT),
    ).stdout.decode()
    modes = {}
    for entry in listing.split("\0")[:-1]:
        meta, path = entry.split("\t", 1)
        mode = meta.split(" ", 1)[0]
        # Files, not links or submodules.
        if mode in ("100644", "100755"):
            modes[path] = mode
    scripts = {path for path in modes if renders_a_script(ROOT / path)}
    executable = {path for path, mode in modes.items() if mode == "100755"}

    assert executable == scripts
    assert {
        ".githooks/pre-push",
        "template/.githooks/pre-push.jinja",
        "template/.github/sign-tag.sh.jinja",
        "template/.devcontainer/setup.sh.jinja",
        "template/scripts/check.sh.jinja",
    } <= scripts


# Copier asks Git for the modes of the files of the template, which the copy of the
# mutation tests has no Git for.
@pytest.mark.mutation_unsafe
@pytest.mark.skipif(os.name == "nt", reason="Windows has no executable files")
@pytest.mark.parametrize("kind", KINDS)
def test_every_script_of_a_new_repository_is_executable(
    projects: dict[str, Path], kind: str
) -> None:
    project = projects[kind]
    modes = {
        path.relative_to(project).as_posix(): path.stat().st_mode & 0o111
        for path in text_files(project)
    }
    scripts = {
        name for name in modes if (project / name).read_bytes().startswith(b"#!")
    }

    assert {name for name, mode in modes.items() if mode} == scripts
    assert all(modes[name] == 0o111 for name in scripts)
    assert {".githooks/pre-push", ".devcontainer/setup.sh", "scripts/check.sh"} <= (
        scripts
    )


# The author of the commits of the tests, whatever this computer has set up.
IDENTITY = ("-c", "user.name=Dev", "-c", "user.email=dev@example.com")


# It needs the modes that Copier takes from Git, which the copy of the mutation tests
# has no Git for.
@pytest.mark.mutation_unsafe
@pytest.mark.skipif(BASH is None, reason="the hook runs bash, Git Bash on Windows")
def test_the_hook_stops_a_push_whose_checks_fail(
    projects: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert BASH
    project = tmp_path / "project"
    remote = tmp_path / "remote.git"
    shutil.copytree(projects["generic"], project)
    # No configuration of this computer, such as signed commits, gets in the way, and
    # the hook finds the bash of the tests, Git Bash on Windows.
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("PATH", f"{Path(BASH).parent}{os.pathsep}{os.environ['PATH']}")

    def git(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *IDENTITY, *arguments],
            cwd=project,
            capture_output=True,
            encoding="utf-8",
            check=False,
        )

    assert git("init", "--quiet", "--bare", str(remote)).returncode == 0
    # A new repository as the README starts it, with the hook turned on as
    # CONTRIBUTING.md and the dev container turn it on.
    assert git("init", "--quiet").returncode == 0
    assert git("add", "--all").returncode == 0
    assert git("commit", "--quiet", "--message", "chore: start").returncode == 0
    assert git("config", "core.hooksPath", ".githooks").returncode == 0
    # Checks that say that they ran, and fail when FAIL is set.
    (project / "scripts/check.sh").write_text(
        'echo "The checks ran."\nexit "${FAIL:-0}"\n', encoding="utf-8", newline="\n"
    )

    monkeypatch.setenv("FAIL", "1")
    failed = git("push", str(remote), "HEAD:refs/heads/main")
    monkeypatch.delenv("FAIL")
    passed = git("push", str(remote), "HEAD:refs/heads/main")

    assert failed.returncode != 0, failed.stderr
    assert "The checks ran." in failed.stdout + failed.stderr
    assert "ignored" not in failed.stderr
    assert passed.returncode == 0, passed.stderr
    assert "The checks ran." in passed.stdout + passed.stderr


# It needs the modes that Copier takes from Git, which the copy of the mutation tests
# has no Git for.
@pytest.mark.mutation_unsafe
@pytest.mark.skipif(BASH is None, reason="the hook runs bash, Git Bash on Windows")
def test_the_checks_of_the_hook_find_the_repository_from_its_folder(
    projects: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # In a worktree, Git hands the hook GIT_DIR, which every git of the checks would
    # follow: also git init and the commits of a test in a throwaway repository, which
    # landed in the repository that ran the checks. Only where the variables alone find
    # the repository, as for a worktree in a container, the checks keep them.
    assert BASH
    project = tmp_path / "project"
    worktree = tmp_path / "worktree"
    remote = tmp_path / "remote.git"
    shutil.copytree(projects["generic"], project)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.setenv("PATH", f"{Path(BASH).parent}{os.pathsep}{os.environ['PATH']}")
    # Checks that say what GIT_DIR named for them.
    (project / "scripts/check.sh").write_text(
        'echo "GIT_DIR=${GIT_DIR-}."\n', encoding="utf-8", newline="\n"
    )

    def git(folder: Path, *arguments: str) -> str:
        return subprocess.run(
            ["git", *IDENTITY, *arguments],
            cwd=folder,
            capture_output=True,
            encoding="utf-8",
            check=True,
        ).stdout.strip()

    git(project, "init", "--quiet", "--bare", str(remote))
    git(project, "init", "--quiet")
    git(project, "add", "--all")
    git(project, "commit", "--quiet", "--message", "chore: start")
    git(project, "config", "core.hooksPath", ".githooks")
    git(project, "worktree", "add", "--quiet", "-b", "change", str(worktree))
    gitdir = git(worktree, "rev-parse", "--absolute-git-dir")
    pushed = subprocess.run(
        ["git", "push", str(remote), "HEAD:refs/heads/change"],
        cwd=worktree,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    # A worktree in a container: its .git names the folder of another computer, so
    # only GIT_DIR and GIT_WORK_TREE find the repository. Git on Windows hides the file,
    # which Windows then lets no one overwrite, only delete.
    (worktree / ".git").unlink()
    (worktree / ".git").write_text(
        "gitdir: /elsewhere/.git/worktrees/worktree\n", encoding="utf-8"
    )
    contained = subprocess.run(
        [BASH, ".githooks/pre-push", str(remote), str(remote)],
        cwd=worktree,
        capture_output=True,
        encoding="utf-8",
        env={**os.environ, "GIT_DIR": gitdir, "GIT_WORK_TREE": str(worktree)},
        check=False,
    )

    assert pushed.returncode == 0, pushed.stderr
    assert "GIT_DIR=." in pushed.stdout + pushed.stderr
    assert contained.returncode == 0, contained.stderr
    assert contained.stdout == f"GIT_DIR={gitdir}.\n"


def hooks_step(check: str) -> str:
    start = check.index('step "Git hooks"')
    return check[start : check.index('step "Shell scripts"', start)]


@pytest.mark.parametrize("kind", KINDS)
def test_the_checks_look_at_the_modes_of_the_hooks(
    projects: dict[str, Path], kind: str
) -> None:
    check = (projects[kind] / "scripts/check.sh").read_text(encoding="utf-8")
    generic = (projects["generic"] / "scripts/check.sh").read_text(encoding="utf-8")

    # In every kind of project the same, right before the shell scripts.
    assert check.index('\nstep "Git hooks"\n') < check.index('\nstep "Shell scripts"\n')
    assert hooks_step(check) == hooks_step(generic)
    contributing = (projects[kind] / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "`git update-index --chmod=+x .githooks/pre-push`" in contributing


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
def test_the_checks_fail_while_git_would_skip_a_hook(
    projects: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert BASH
    check = (projects["generic"] / "scripts/check.sh").read_text(encoding="utf-8")
    repository = tmp_path / "repository"
    (repository / "scripts").mkdir(parents=True)
    # Its set-up, such as set -euo pipefail and the folder it runs in, and the step.
    script = check[: check.index('step "Text files"')] + hooks_step(check)
    (repository / "scripts/hooks.sh").write_text(script, encoding="utf-8", newline="\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")

    def git(*arguments: str) -> None:
        subprocess.run(["git", *arguments], cwd=repository, check=True)

    def step() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [BASH, "scripts/hooks.sh"],
            cwd=repository,
            capture_output=True,
            encoding="utf-8",
            check=False,
        )

    git("init", "--quiet")
    # The modes in Git alone, the same on every system: as on Windows, a new file is
    # a plain one.
    git("config", "core.fileMode", "false")
    without_hooks = step()
    (repository / ".githooks").mkdir()
    for hook in ("pre-commit", "pre-push"):
        (repository / ".githooks" / hook).write_text(
            "#!/bin/sh\n", encoding="utf-8", newline="\n"
        )
    git("add", ".githooks")
    plain = step()
    git("update-index", "--chmod=+x", ".githooks/pre-push")
    one_plain = step()
    git("update-index", "--chmod=+x", ".githooks/pre-commit")
    executable = step()

    # Every plain hook, and the command that makes them executable.
    assert (plain.returncode, plain.stdout) == (
        1,
        "\n== Git hooks\n"
        ".githooks/pre-commit: is not executable, so git skips it\n"
        ".githooks/pre-push: is not executable, so git skips it\n"
        "Make it executable and commit that: git update-index --chmod=+x"
        " .githooks/pre-commit .githooks/pre-push\n",
    )
    assert (one_plain.returncode, one_plain.stdout) == (
        1,
        "\n== Git hooks\n"
        ".githooks/pre-commit: is not executable, so git skips it\n"
        "Make it executable and commit that: git update-index --chmod=+x"
        " .githooks/pre-commit\n",
    )
    for passed in (without_hooks, executable):
        assert (passed.returncode, passed.stdout) == (
            0,
            "\n== Git hooks\nEvery hook in .githooks/ is executable.\n",
        ), passed.stderr


def text_step(check: str) -> str:
    """The step Text files, with the function before it that lists the files of git."""
    start = check.index("# The files of git, tracked or new, each once")
    return check[start : check.index('step "Diagrams"', start)]


def shell_step(check: str) -> str:
    start = check.index('step "Shell scripts"')
    return check[start : check.index("\nfi\n", start) + 4]


@pytest.mark.parametrize("kind", KINDS)
def test_every_repository_checks_its_text_files_and_scripts_as_the_blueprint(
    projects: dict[str, Path], kind: str
) -> None:
    check = (projects[kind] / "scripts/check.sh").read_text(encoding="utf-8")
    own = (ROOT / "scripts/check.sh").read_text(encoding="utf-8")

    assert text_step(check) == text_step(own)
    assert shell_step(check) == shell_step(own)
    assert "--deduplicate" in text_step(check)


def path_without(folder: Path, *commands: str) -> str:
    """A PATH without these commands, for a step that must do without them: on Linux
    and macOS a folder with a link to every other command of the PATH, and on Windows,
    which makes no links without privileges, the folders of bash and git alone, where
    the test runs only when they lack the commands."""
    if os.name == "nt":
        git = shutil.which("git")
        assert BASH
        assert git
        folders = os.pathsep.join([str(Path(BASH).parent), str(Path(git).parent)])
        if any(shutil.which(command, path=folders) for command in commands):
            pytest.skip(f"the folders of bash and git have {', '.join(commands)}")
        return folders
    folder.mkdir()
    for entry in os.environ["PATH"].split(os.pathsep):
        if not Path(entry).is_dir():
            continue
        for program in Path(entry).iterdir():
            link = folder / program.name
            if (
                program.name not in commands
                and not link.is_symlink()
                and program.is_file()
                and os.access(program, os.X_OK)
            ):
                link.symlink_to(program)
    return str(folder)


def run_the_steps(
    repository: Path, script: str, *, path: str | None = None, ci: bool = False
) -> subprocess.CompletedProcess[str]:
    """The set-up of scripts/check.sh and steps after it, as script, in the repository:
    from a file that git leaves out, without the variables of a run of the CI or with
    those of GitHub Actions, and with this PATH."""
    (repository / "scripts").mkdir(exist_ok=True)
    (repository / "scripts/steps.sh").write_text(script, encoding="utf-8", newline="\n")
    (repository / ".git/info").mkdir(exist_ok=True)
    (repository / ".git/info/exclude").write_text(
        "/scripts/steps.sh\n", encoding="utf-8"
    )
    environment = {
        name: value
        for name, value in os.environ.items()
        if name != "CI" and not name.startswith("GITHUB_")
    }
    if ci:
        environment |= {"CI": "true", "GITHUB_ACTIONS": "true"}
    if path is not None:
        environment["PATH"] = path
    assert BASH
    return subprocess.run(
        [BASH, "scripts/steps.sh"],
        cwd=repository,
        env=environment,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )


def a_repository_with_problems(repository: Path) -> Path:
    """A repository with a text file for each problem, one with all of them, a merge
    that leaves a conflict, and the files that the step leaves alone: binary, empty,
    deleted and ignored ones and the licenses."""

    def git(*arguments: str) -> None:
        subprocess.run(
            ["git", "-c", "core.autocrlf=false", *arguments],
            cwd=repository,
            capture_output=True,
            check=arguments[0] != "merge",
        )

    repository.mkdir()
    git("init", "--quiet", "--initial-branch=main")
    files = {
        "crlf.md": b"one\r\ntwo\r\n",
        "spaces.txt": b"one\ntwo \n",
        "tab.py": b"x = 1\t\n",
        "end.txt": b"one\ntwo",
        "all.txt": b"<<<<<<< HEAD\r\nx \r\nend ",
        "conflict.py": b"a = 1\n<<<<<<< HEAD\nb = 2\n=======\nb = 3\n>>>>>>> side\n",
        # A marker alone, before the CR of its line ending, on every system.
        "bare.txt": b"x\r\n>>>>>>>\r\n",
        # A heading of Markdown, and lines that only look like markers.
        "no conflict.md": b"Title\n=======\n\n<<<<<<<< eight\n> >>>>>>> quoted\nx <<<<<<<\n",
        "binary.bin": b"\0one \r\n<<<<<<< HEAD\nend",
        "LICENSE": b"license \n",
        "LICENSES/MIT.txt": b"text \r\nend",
        "empty.txt": b"",
        "lines.txt": b"\n\n",
        "clean.txt": b"clean\n",
        "gone.txt": b"gone \n",
        "merged.txt": b"start\n",
        ".gitignore": b"ignored.txt\n",
    }
    for name, content in files.items():
        (repository / name).parent.mkdir(parents=True, exist_ok=True)
        (repository / name).write_bytes(content)
    git("add", "--all")
    git("commit", "--quiet", "-m", "start")
    git("switch", "--quiet", "--create", "side")
    (repository / "merged.txt").write_bytes(b"side\n")
    git("commit", "--quiet", "--all", "-m", "side")
    git("switch", "--quiet", "main")
    (repository / "merged.txt").write_bytes(b"main\n")
    git("commit", "--quiet", "--all", "-m", "main")
    git("merge", "side")
    (repository / "gone.txt").unlink()
    (repository / "new.txt").write_bytes(b"new \n")
    (repository / "ignored.txt").write_bytes(b"ignored \n")
    return repository


@pytest.fixture
def isolated_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Git without the configuration of this machine, and with a name for commits."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "Tester")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "tester@example.com")


@pytest.mark.usefixtures("isolated_git")
@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
def test_the_checks_find_every_problem_of_a_text_file(
    projects: dict[str, Path], tmp_path: Path
) -> None:
    check = (projects["generic"] / "scripts/check.sh").read_text(encoding="utf-8")
    script = check[: check.index('step "Diagrams"')]
    repository = a_repository_with_problems(tmp_path / "repository")

    local = run_the_steps(repository, script)
    ci = run_the_steps(repository, script, ci=True)

    assert local.returncode == 1, local.stderr
    assert local.stderr == ""
    lines = local.stdout.splitlines()
    assert lines[:2] == ["", "== Text files"]
    # Each problem once, those of the file of the merge too, which git lists for each
    # side of its conflict.
    assert sorted(lines[2:-2]) == [
        "all.txt: has CRLF line endings",
        "all.txt: has conflict markers",
        "all.txt: has trailing whitespace",
        "all.txt: lacks the line break at its end",
        "bare.txt: has CRLF line endings",
        "bare.txt: has conflict markers",
        "conflict.py: has conflict markers",
        "crlf.md: has CRLF line endings",
        "end.txt: lacks the line break at its end",
        "merged.txt: has conflict markers",
        "new.txt: has trailing whitespace",
        "spaces.txt: has trailing whitespace",
        "tab.py: has trailing whitespace",
    ]
    # The problems of a file together, in the order of the checks.
    first = lines.index("all.txt: has CRLF line endings")
    assert lines[first : first + 4] == [
        "all.txt: has CRLF line endings",
        "all.txt: has trailing whitespace",
        "all.txt: lacks the line break at its end",
        "all.txt: has conflict markers",
    ]
    assert lines[-2:] == [
        "Fix the 13 problem(s) above; .editorconfig sets up most editors for it.",
        "A conflict needs a person: keep the lines that belong, and delete the markers.",
    ]
    # In the CI, each problem is an annotation at its line as well.
    assert ci.returncode == 1
    annotations = [line for line in ci.stdout.splitlines() if line.startswith("::")]
    assert len(annotations) == 13
    for annotation in [
        "::error file=conflict.py,line=2,title=Text files::has conflict markers",
        "::error file=bare.txt,line=2,title=Text files::has conflict markers",
        "::error file=merged.txt,line=1,title=Text files::has conflict markers",
        "::error file=all.txt,line=1,title=Text files::has conflict markers",
        "::error file=all.txt,line=3,title=Text files::lacks the line break at its end",
        "::error file=tab.py,line=1,title=Text files::has trailing whitespace",
    ]:
        assert annotation in annotations


@pytest.mark.usefixtures("isolated_git")
@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
def test_the_checks_find_the_same_problems_without_perl(
    projects: dict[str, Path], tmp_path: Path
) -> None:
    check = (projects["generic"] / "scripts/check.sh").read_text(encoding="utf-8")
    script = check[: check.index('step "Diagrams"')]
    repository = a_repository_with_problems(tmp_path / "repository")
    without = path_without(tmp_path / "bin", "perl")

    with_perl = run_the_steps(repository, script)
    with_tail = run_the_steps(repository, script, path=without)

    assert "lacks the line break at its end" in with_perl.stdout
    assert (with_tail.returncode, with_tail.stdout) == (1, with_perl.stdout)


def stub_in_front(folder: Path, name: str, script: str) -> str:
    """A PATH with a bash script as the command name in front of the PATH of the
    tests: the script runs the real command after it drops its own folder."""
    folder.mkdir()
    (folder / name).write_text(
        f'#!/usr/bin/env bash\n{script}\nPATH="${{PATH#*:}}"\nexec {name} "$@"\n',
        encoding="utf-8",
        newline="\n",
    )
    (folder / name).chmod(0o755)
    return f"{folder}{os.pathsep}{os.environ['PATH']}"


@pytest.mark.usefixtures("isolated_git")
@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
def test_the_checks_find_the_same_problems_with_the_grep_of_macos(
    projects: dict[str, Path], tmp_path: Path
) -> None:
    # The grep of macOS reads -Z as gzip, and ends no name with a NUL for it: the
    # step asks for the NUL with --null, which every grep knows.
    check = (projects["generic"] / "scripts/check.sh").read_text(encoding="utf-8")
    script = check[: check.index('step "Diagrams"')]
    repository = a_repository_with_problems(tmp_path / "repository")
    bsd = stub_in_front(
        tmp_path / "bsd",
        "grep",
        'for word in "$@"; do\n'
        '  if [[ "$word" == -[!-]*Z* ]]; then echo "-Z is gzip here" >&2; exit 2; fi\n'
        "done",
    )

    gnu = run_the_steps(repository, script)
    macos = run_the_steps(repository, script, path=bsd)

    assert "has conflict markers" in gnu.stdout
    assert (macos.returncode, macos.stdout, macos.stderr) == (1, gnu.stdout, "")


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
def test_the_checks_stop_on_a_git_older_than_2_31(
    projects: dict[str, Path], tmp_path: Path
) -> None:
    check = (projects["generic"] / "scripts/check.sh").read_text(encoding="utf-8")
    repository = tmp_path / "repository"
    subprocess.run(["git", "init", "--quiet", str(repository)], check=True)
    (repository / "spaces.txt").write_bytes(b"spaces \n")
    old = stub_in_front(
        tmp_path / "old",
        "git",
        'for word in "$@"; do\n'
        '  if [[ "$word" == --deduplicate ]]; then exit 129; fi\n'
        "done",
    )

    result = run_the_steps(
        repository, check[: check.index('step "Diagrams"')], path=old
    )

    assert (result.returncode, result.stdout, result.stderr) == (
        1,
        "\n== Text files\n",
        "scripts/check.sh needs Git 2.31 or newer.\n",
    )


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize("files", [{}, {"binary.bin": b"\0text \n"}])
def test_the_checks_pass_without_text_files(
    projects: dict[str, Path], tmp_path: Path, files: dict[str, bytes]
) -> None:
    check = (projects["generic"] / "scripts/check.sh").read_text(encoding="utf-8")
    repository = tmp_path / "repository"
    subprocess.run(["git", "init", "--quiet", str(repository)], check=True)
    for name, content in files.items():
        (repository / name).write_bytes(content)

    result = run_the_steps(repository, check[: check.index('step "Diagrams"')])

    assert (result.returncode, result.stdout, result.stderr) == (
        0,
        "\n== Text files\nEvery text file is clean.\n",
        "",
    )


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
def test_the_ci_never_skips_shellcheck(
    projects: dict[str, Path], tmp_path: Path
) -> None:
    check = (projects["generic"] / "scripts/check.sh").read_text(encoding="utf-8")
    script = check[: check.index('step "Text files"')] + shell_step(check)
    repository = tmp_path / "repository"
    subprocess.run(["git", "init", "--quiet", str(repository)], check=True)
    (repository / "tool.sh").write_text("echo tool\n", encoding="utf-8", newline="\n")
    without = path_without(tmp_path / "bin", "shellcheck")
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    calls = tmp_path / "calls"
    (stubs / "shellcheck").write_text(
        f"#!/usr/bin/env bash\nprintf '%s\\n' \"$@\" >> '{calls.as_posix()}'\n",
        encoding="utf-8",
        newline="\n",
    )
    (stubs / "shellcheck").chmod(0o755)

    local = run_the_steps(repository, script, path=without)
    ci = run_the_steps(repository, script, path=without, ci=True)
    checked = run_the_steps(repository, script, path=f"{stubs}{os.pathsep}{without}")

    assert (local.returncode, local.stdout) == (
        0,
        "\n== Shell scripts\nshellcheck is not installed here; the CI runs it.\n",
    )
    assert (ci.returncode, ci.stdout) == (
        1,
        "\n== Shell scripts\n"
        "Checking the shell scripts needs ShellCheck, which this runner lacks.\n",
    )
    assert (checked.returncode, checked.stdout) == (
        0,
        "\n== Shell scripts\nshellcheck found nothing in 1 script(s).\n",
    )
    assert calls.read_text(encoding="utf-8") == "tool.sh\n"


def pages_step(check: str) -> str:
    start = check.index('step "Pages in one column"')
    return check[start : check.index('step "Changelog fragments"', start)]


def fragments_step(check: str) -> str:
    start = check.index('step "Changelog fragments"')
    return check[start : check.index('step "Version"', start)]


@pytest.mark.parametrize("kind", KINDS)
def test_every_repository_checks_that_its_pages_have_one_column(
    projects: dict[str, Path], kind: str
) -> None:
    project = projects[kind]
    check = (project / "scripts/check.sh").read_text(encoding="utf-8")
    generic = (projects["generic"] / "scripts/check.sh").read_text(encoding="utf-8")
    own = (ROOT / "scripts/check.sh").read_text(encoding="utf-8")

    # In every kind of project the same, right after the diagrams, without Docker.
    assert check.index('\nstep "Diagrams"\n') < check.index(
        '\nstep "Pages in one column"\n'
    )
    assert pages_step(check) == pages_step(generic) == pages_step(own)
    assert '"$python" "$tool" pages\n' in pages_step(check)
    assert "docker" not in pages_step(check)
    # The pages that a new repository starts with have one column.
    checked = [
        page
        for page in project.rglob("*.md")
        if ".git" not in page.parts and shown(page.relative_to(project))
    ]
    assert project / "README.md" in checked
    assert project / "CONTRIBUTING.md" in checked
    for page in checked:
        assert layouts(page.read_text(encoding="utf-8")) == [], page
    contributing = (project / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "## Pages in one column" in contributing
    assert "`python3 .github/blueprint.py pages --fix`" in contributing


# In the copy of the mutation tests, the tool is the code with the mutants, which the
# variables of mutmut switch in the process that this test starts.
@pytest.mark.mutation_unsafe
@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
def test_the_checks_fail_on_a_page_with_columns_side_by_side(
    projects: dict[str, Path], tmp_path: Path
) -> None:
    assert BASH
    project = shutil.copytree(projects["generic"], tmp_path / "repository")
    check = (project / "scripts/check.sh").read_text(encoding="utf-8")
    # Its set-up, such as set -euo pipefail and the folder it runs in, and the step.
    script = check[: check.index('step "Text files"')] + pages_step(check)
    (project / "scripts/pages.sh").write_text(script, encoding="utf-8", newline="\n")
    subprocess.run(["git", "init", "--quiet", str(project)], check=True)
    # The Python of the tests first, without the variables of a run of the CI.
    environment = {
        name: value
        for name, value in os.environ.items()
        if name not in ("CI", "GITHUB_ACTIONS")
    }
    environment["PATH"] = os.pathsep.join(
        [str(Path(sys.executable).parent), environment.get("PATH", "")]
    )

    def step() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [BASH, "scripts/pages.sh"],
            cwd=project,
            env=environment,
            capture_output=True,
            encoding="utf-8",
            check=False,
        )

    passed = step()
    readme = project / "README.md"
    text = readme.read_text(encoding="utf-8")
    readme.write_text(
        text
        + '\n<table><tr>\n<td width="50%">The card</td>\n'
        + '<td><img src="docs/images/card.png" alt="The card"></td>\n</tr></table>\n',
        encoding="utf-8",
        newline="\n",
    )
    failed = step()
    fix = subprocess.run(
        [sys.executable, ".github/blueprint.py", "pages", "--fix"],
        cwd=project,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    fixed = step()

    assert passed.returncode == 0, passed.stdout + passed.stderr
    assert "page(s) that GitHub shows have one column." in passed.stdout
    line = text.count("\n") + 2
    assert failed.returncode == 1, failed.stdout + failed.stderr
    assert f"\nREADME.md:{line}: a <table> that sets a picture beside" in failed.stdout
    assert (
        "python3 .github/blueprint.py pages --fix puts 1 of them in one column"
        in failed.stdout
    )
    assert fix.returncode == 0, fix.stdout + fix.stderr
    assert readme.read_text(encoding="utf-8").endswith(
        '\nThe card\n\n<img src="docs/images/card.png" alt="The card">\n'
    )
    assert fixed.returncode == 0, fixed.stdout + fixed.stderr


@pytest.mark.parametrize("kind", KINDS)
def test_every_repository_checks_every_fragment_of_its_changelog(
    projects: dict[str, Path], kind: str
) -> None:
    check = (projects[kind] / "scripts/check.sh").read_text(encoding="utf-8")
    generic = (projects["generic"] / "scripts/check.sh").read_text(encoding="utf-8")
    own = (ROOT / "scripts/check.sh").read_text(encoding="utf-8")

    # Right after the pages, whose Python and blueprint.py it takes, the same in every
    # kind of project and in the blueprint, over the whole folder, without Docker.
    assert check.index('\nstep "Pages in one column"\n') < check.index(
        '\nstep "Changelog fragments"\n'
    )
    assert fragments_step(check) == fragments_step(generic) == fragments_step(own)
    assert '  "$python" "$tool" fragments\n' in fragments_step(check)
    assert "--folder" not in fragments_step(check)
    assert "docker" not in fragments_step(check)
    contributing = (projects[kind] / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "`bash scripts/check.sh` checks every fragment" in contributing


# In the copy of the mutation tests, the tool is the code with the mutants, which the
# variables of mutmut switch in the process that this test starts.
@pytest.mark.mutation_unsafe
@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
def test_the_checks_fail_on_a_fragment_that_the_release_cannot_take_in(
    projects: dict[str, Path], tmp_path: Path
) -> None:
    assert BASH
    project = shutil.copytree(projects["generic"], tmp_path / "repository")
    check = (project / "scripts/check.sh").read_text(encoding="utf-8")
    # Its set-up, the step of the pages, which finds the Python, and the step.
    script = (
        check[: check.index('step "Text files"')]
        + pages_step(check)
        + fragments_step(check)
    )
    (project / "scripts/fragments.sh").write_text(
        script, encoding="utf-8", newline="\n"
    )
    subprocess.run(["git", "init", "--quiet", str(project)], check=True)
    # The Python of the tests first, without the variables of a run of the CI.
    environment = {
        name: value
        for name, value in os.environ.items()
        if name not in ("CI", "GITHUB_ACTIONS")
    }
    environment["PATH"] = os.pathsep.join(
        [str(Path(sys.executable).parent), environment.get("PATH", "")]
    )

    def step() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [BASH, "scripts/fragments.sh"],
            cwd=project,
            env=environment,
            capture_output=True,
            encoding="utf-8",
            check=False,
        )

    # A new repository has the folder, without a fragment.
    empty = step()
    folder = project / "changelog.d"
    (folder / "dark-mode.md").write_text(FEATURE_FRAGMENT, encoding="utf-8")
    fine = step()
    # A fragment that waits on main for the release, such as one that a pull request
    # wrote before the rules got stricter, fails here, before the release does.
    (folder / "typo.md").write_text("### Fixes\n\n- A fix.\n", encoding="utf-8")
    failed = step()

    assert empty.returncode == 0, empty.stdout + empty.stderr
    assert "\n== Changelog fragments\n" in empty.stdout
    assert "The 0 fragment(s) in changelog.d/ are fine." in empty.stdout
    assert fine.returncode == 0, fine.stdout + fine.stderr
    assert "The 1 fragment(s) in changelog.d/ are fine." in fine.stdout
    assert failed.returncode == 1, failed.stdout + failed.stderr
    assert (
        "\nchangelog.d/typo.md: `### Fixes` is no kind of change of the changelog. "
        "Did you mean `### Fixed`?" in failed.stdout
    )


def step_of_the_tests(check: str) -> str:
    start = check.index('step "Tests, with every line and branch covered"')
    return check[start : check.index("\nstep ", start) + 1]


@pytest.mark.parametrize("plugins", [True, False])
def test_the_tests_of_a_python_project_run_on_every_core(
    projects: dict[str, Path], tmp_path: Path, plugins: bool
) -> None:
    assert BASH
    project = shutil.copytree(projects["python-package"], tmp_path / "repository")
    check = (project / "scripts/check.sh").read_text(encoding="utf-8")
    # Its set-up, such as set -euo pipefail and the folder it runs in, and the step.
    (project / "scripts/tests.sh").write_text(
        check[: check.index('step "Text files"')] + step_of_the_tests(check),
        encoding="utf-8",
        newline="\n",
    )
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    if not plugins:
        # The Python of a project made before the blueprint brought pytest-xdist and
        # pytest-cov, whose lock file is its own and lacks them.
        stub = stubs / "python"
        stub.write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8", newline="\n")
        stub.chmod(0o755)
    # The tools of the tests first, two processes for -n auto, and none of the
    # variables of the pytest that runs this test.
    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("PYTEST_", "COV_CORE_", "COVERAGE_"))
    }
    environment["PATH"] = os.pathsep.join(
        [str(Path(sys.executable).parent), environment.get("PATH", "")]
    )
    environment["STUBS"] = stubs.as_posix()
    environment["PYTEST_XDIST_AUTO_NUM_WORKERS"] = "2"

    def step() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            in_bash("scripts/tests.sh"),
            cwd=project,
            env=environment,
            capture_output=True,
            encoding="utf-8",
            check=False,
        )

    passed = step()
    # A function that no test calls.
    module = project / "src/demo_project/__init__.py"
    with module.open("a", encoding="utf-8", newline="\n") as code:
        code.write("\n\ndef untested() -> int:\n    return 1\n")
    failed = step()

    assert passed.returncode == 0, passed.stdout + passed.stderr
    assert ("created: 2/2 workers" in passed.stdout) is plugins, passed.stdout
    assert re.search(r"^TOTAL .* 100%$", passed.stdout, re.M), passed.stdout
    # The data that the CI shows in the summary of the check.
    assert (project / ".coverage").is_file()
    # [tool.coverage] of pyproject.toml applies either way: fail_under fails the
    # step, and the report names the line that no test runs.
    assert failed.returncode != 0
    assert ("created: 2/2 workers" in failed.stdout) is plugins, failed.stdout
    assert re.search(
        r"^src[\\/]demo_project[\\/]__init__\.py .* \d+$", failed.stdout, re.M
    ), failed.stdout
    assert "Coverage failure: total of" in failed.stdout + failed.stderr


@pytest.mark.parametrize("kind", ["home-assistant", "github-action", "python-package"])
def test_every_python_project_can_run_its_tests_on_every_core(
    projects: dict[str, Path], kind: str
) -> None:
    project = projects[kind]
    tools = (
        "requirements-test.txt" if kind == "home-assistant" else "requirements-dev.txt"
    )
    lock = (project / tools).read_text(encoding="utf-8")
    settings = tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))
    pytest_settings = settings["tool"]["pytest"]["ini_options"]

    # pytest-xdist runs the tests on every core, pytest-cov measures each process,
    # and pytest-timeout fails a test that hangs.
    for plugin in ("pytest-xdist", "pytest-cov", "pytest-timeout"):
        assert re.search(rf"^{plugin}==\S+ \\$", lock, re.M), (kind, plugin)
    assert pytest_settings["timeout"] == 30
    # -n stays out of the settings, because mutmut runs pytest within its own process.
    assert not any(option.startswith("-n") for option in pytest_settings["addopts"])
    assert "python -m pytest -n auto --cov --cov-report= --cov-fail-under=0" in (
        project / "scripts/check.sh"
    ).read_text(encoding="utf-8")


@pytest.mark.skipif(
    os.name == "nt" or BASH is None, reason="Windows has no executable files"
)
@pytest.mark.parametrize("file_mode", ["false", "true"])
def test_the_dev_container_makes_the_hook_executable_where_git_ignores_modes(
    projects: dict[str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    file_mode: str,
) -> None:
    assert BASH
    repository = tmp_path / "repository"
    (repository / ".devcontainer").mkdir(parents=True)
    (repository / ".githooks").mkdir()
    shutil.copy(
        projects["generic"] / ".devcontainer/setup.sh",
        repository / ".devcontainer/setup.sh",
    )
    hook = repository / ".githooks/pre-push"
    hook.write_text("#!/bin/sh\n", encoding="utf-8", newline="\n")
    # On disk, the hook of a repository whose hook Git has as a plain file.
    hook.chmod(0o644)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")

    def git(*arguments: str) -> str:
        return subprocess.run(
            ["git", *IDENTITY, *arguments],
            cwd=repository,
            capture_output=True,
            encoding="utf-8",
            check=True,
        ).stdout

    git("init", "--quiet")
    git("config", "core.fileMode", file_mode)
    git("add", "--all")
    git("commit", "--quiet", "--message", "chore: start")
    # Without mkdocs.yml, the set-up installs nothing.
    setup = subprocess.run(
        [BASH, ".devcontainer/setup.sh"],
        cwd=repository,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )

    assert setup.returncode == 0, setup.stdout + setup.stderr
    assert git("config", "core.hooksPath") == ".githooks\n"
    # Executable where Git ignores the modes; elsewhere the mode in Git applies, so
    # that the set-up changes nothing that Git would see.
    assert bool(hook.stat().st_mode & 0o111) == (file_mode == "false")
    assert git("status", "--porcelain") == ""


def remapper(project: Path) -> Callable[[str], str]:
    """The remaps of lychee.toml, as lychee applies them: the first rule whose regular
    expression matches a link changes it."""
    config = tomllib.loads((project / "lychee.toml").read_text(encoding="utf-8"))
    rules = []
    for rule in config["remap"]:
        pattern, replacement = rule.split()
        # Lychee writes a group of the regular expression as $1, Python as \g<1>.
        rules.append((re.compile(pattern), re.sub(r"\$(\d)", r"\\g<\1>", replacement)))

    def remapped(url: str) -> str:
        for pattern, replacement in rules:
            if pattern.search(url):
                return pattern.sub(replacement, url)
        return url

    return remapped


def test_the_link_check_checks_the_anchors_that_it_can_see(
    projects: dict[str, Path],
) -> None:
    config = tomllib.loads(
        (projects["generic"] / "lychee.toml").read_text(encoding="utf-8")
    )
    # Every anchor of a link, also in the README of another repository.
    assert config["include_fragments"] == "anchor-only"
    remapped = remapper(projects["generic"])
    # GitHub draws #readme with a script; the check asks for the repository.
    assert remapped("https://github.com/owner/repo#readme") == (
        "https://github.com/owner/repo"
    )
    assert remapped("https://github.com/owner/repo/#readme") == (
        "https://github.com/owner/repo"
    )
    for url in (
        "https://github.com/owner/repo#start-a-repository",
        "https://github.com/owner/repo/tree/main#readme",
        "https://example.org/page#readme",
    ):
        assert remapped(url) == url
    # The anchors of the Markdown files of the repository, which --8<-- may put
    # together from others, are the build's to check; the file is still checked.
    assert remapped("file:///repo/docs/guide.md#kinds-of-projects") == (
        "file:///repo/docs/guide.md"
    )
    assert remapped("file:///repo/docs/page.html#part") == (
        "file:///repo/docs/page.html#part"
    )
    # A page of HTML of the repository is one of the built website, such as
    # cards.html of docs/cards.md, which the check docs checks there.
    excluded = [re.compile(pattern) for pattern in config["exclude"]]
    for url in (
        "file:///repo/docs/cards.html",
        "file:///repo/docs/cards.html#play",
        "file:///repo/docs/index.html?x=1",
    ):
        assert any(pattern.search(url) for pattern in excluded), url
    for url in (
        "file:///repo/docs/images/demo.png",
        "file:///repo/docs/cards.md",
        "https://example.org/page.html",
    ):
        assert not any(pattern.search(url) for pattern in excluded), url


def test_the_link_check_asks_for_a_file_of_github_where_github_answers(
    projects: dict[str, Path],
) -> None:
    # github.com answers the page of a file with 503 at times; raw.githubusercontent.com
    # has the same file, and answers 404 for a missing one as well.
    remapped = remapper(projects["generic"])

    raw = "https://raw.githubusercontent.com/owner/repo"
    blob = "https://github.com/owner/repo/blob"
    assert (
        remapped(f"{blob}/main/docs/guide.md#setup")
        == f"{raw}/main/docs/guide.md#setup"
    )
    assert remapped(f"{blob}/v1.0.0/LICENSE") == f"{raw}/v1.0.0/LICENSE"
    for url in (
        "https://github.com/owner/repo",
        "https://github.com/owner/repo/tree/main/docs",
        "https://github.com/owner/repo/issues/1",
    ):
        assert remapped(url) == url


class PullRequest(NamedTuple):
    """A repository as the checkout of a pull request leaves it."""

    repository: Path
    # The squash commit that main got after the base that the event names.
    squash: str
    # The commits of the pull request, the oldest first; the last one is its head.
    commits: list[str]


def a_pull_request_on_a_newer_main(
    tmp_path: Path, changes: dict[str, str | None], *signed_off: bool
) -> PullRequest:
    """A pull request whose branch starts on a newer main than the base that its event
    names, as the branch of the release bot does when the bot builds it again. Main got
    a squash commit since that base, which deletes docs/old.md and adds docs/main.md and
    whose sign-off names another address than GitHub gives its author. The first commit
    of the pull request makes the changes; each one has a sign-off or not. A change of
    None deletes the file, one that starts with -> moves it. origin/main is the base
    branch, HEAD the merge commit that the checkout of a pull request leaves."""
    repository = tmp_path / "repository"
    repository.mkdir()

    def git(*arguments: str) -> str:
        identity = ["-c", "user.name=Dev", "-c", "user.email=dev@example.com"]
        return subprocess.run(
            ["git", *identity, "-c", "commit.gpgsign=false", *arguments],
            cwd=repository,
            capture_output=True,
            check=True,
            encoding="utf-8",
        ).stdout.strip()

    def commit(message: str, *options: str) -> str:
        git("add", "--all")
        git("commit", "--quiet", "--allow-empty", "-m", message, *options)
        return git("rev-parse", "HEAD")

    git("init", "--quiet", "--initial-branch=main")
    for name in (
        "README.md",
        "docs/guide.md",
        "docs/old.md",
        "CHANGELOG.md",
        "changelog.d/old.md",
        "lychee.toml",
    ):
        (repository / name).parent.mkdir(parents=True, exist_ok=True)
        (repository / name).write_text(f"{name}\n", encoding="utf-8", newline="\n")
    commit("The base", "--signoff")
    (repository / "docs/old.md").unlink()
    (repository / "docs/main.md").write_text("main\n", encoding="utf-8", newline="\n")
    # GitHub authors a squash commit with the noreply address of the account, while
    # the sign-off of its pull request names the address of the commits there.
    squash = commit(
        "fix: a change of main (#1)\n\nSigned-off-by: Dev <dev@example.com>",
        "--author=Dev <1+dev@users.noreply.github.com>",
    )
    git("switch", "--quiet", "--create", "feature")
    for name, content in changes.items():
        path = repository / name
        if content is None:
            path.unlink()
        elif content.startswith("->"):
            git("mv", name, content.removeprefix("->"))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
    commits = [
        commit(
            f"Commit {number} of the pull request", *(["--signoff"] if signed else [])
        )
        for number, signed in enumerate(signed_off, start=1)
    ]
    git("update-ref", "refs/remotes/origin/main", "main")
    git("switch", "--quiet", "--detach", "main")
    git("merge", "--quiet", "--no-ff", "-m", "Merge the pull request", commits[-1])
    return PullRequest(repository, squash, commits)


def choose_the_documents_to_check(
    tmp_path: Path,
    changes: dict[str, str | None],
    event: str = "pull_request",
    workflow: str = "links.yml",
    step: str = "Choose the documents to check",
) -> tuple[dict[str, str], str]:
    """Runs the step of a workflow that chooses the documents, by default that of the
    link check, in a repository whose pull request makes the changes, as GitHub does,
    with tmp_path as its RUNNER_TEMP; returns its outputs and its summary."""
    source = (ROOT / ".github/workflows" / workflow).read_text(encoding="utf-8")
    repository = a_pull_request_on_a_newer_main(tmp_path, changes, True).repository
    output = tmp_path / "output"
    summary = tmp_path / "summary"
    output.touch()
    summary.touch()
    (tmp_path / "step.sh").write_text(
        script_of(source, step),
        encoding="utf-8",
        newline="\n",
    )
    assert BASH
    result = subprocess.run(
        [BASH, "-e", str(tmp_path / "step.sh")],
        cwd=repository,
        env={
            **os.environ,
            "EVENT": event,
            "BASE_REF": "main",
            "GITHUB_OUTPUT": str(output),
            "GITHUB_STEP_SUMMARY": str(summary),
            "RUNNER_TEMP": tmp_path.as_posix(),
        },
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    outputs = dict(
        line.split("=", 1) for line in output.read_text(encoding="utf-8").splitlines()
    )
    return outputs, summary.read_text(encoding="utf-8")


EVERY_DOCUMENT = {"files": "'./**/*.md' './docs/**/*.html'", "every": "true"}


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize(
    ("changes", "event", "outputs"),
    [
        # The documents that the pull request adds or changes, by their paths, so that
        # none reads as an option.
        (
            {"docs/guide.md": "changed\n"},
            "pull_request",
            {"files": "'./docs/guide.md' "},
        ),
        (
            {"README.md": "changed\n", "docs/new.md": "new\n", "src/app.py": "\n"},
            "pull_request",
            {"files": "'./README.md' './docs/new.md' "},
        ),
        # A page of HTML of the website, such as one that leads to another address.
        (
            {"docs/dashboard/index.html": "<p>x</p>\n", "src/page.html": "\n"},
            "pull_request",
            {"files": "'./docs/dashboard/index.html' "},
        ),
        # The changelog alone is no document to check, and neither is code.
        ({"CHANGELOG.md": "changed\n", "src/app.py": "\n"}, "pull_request", {}),
        # Nor is a fragment of the changelog, which no document links to.
        ({"changelog.d/dark-mode.md": "### Features\n"}, "pull_request", {}),
        ({"changelog.d/old.md": None}, "pull_request", {}),
        (
            {"changelog.d/dark-mode.md": "x\n", "docs/guide.md": "changed\n"},
            "pull_request",
            {"files": "'./docs/guide.md' "},
        ),
        # New rules apply to every document.
        (
            {"lychee.toml": "max_retries = 5\n", "README.md": "x\n"},
            "pull_request",
            EVERY_DOCUMENT,
        ),
        # A document may link to a file that the pull request deletes or moves.
        ({"docs/guide.md": None}, "pull_request", EVERY_DOCUMENT),
        ({"docs/guide.md": "->docs/manual.md"}, "pull_request", EVERY_DOCUMENT),
        # lychee gets the names through a shell.
        ({"docs/it's $(here).md": "x\n"}, "pull_request", EVERY_DOCUMENT),
        # Main deleted and added a document since the base that the event names; that
        # is no change of the pull request.
        ({}, "pull_request", {}),
        # main and the weekly run check every document.
        ({"docs/guide.md": "changed\n"}, "push", EVERY_DOCUMENT),
        ({}, "schedule", EVERY_DOCUMENT),
    ],
)
def test_the_link_check_of_a_pull_request_reads_the_documents_it_changes(
    tmp_path: Path, changes: dict[str, str | None], event: str, outputs: dict[str, str]
) -> None:
    # A site that is down for a moment fails only the pull requests that link to it.
    chosen, summary = choose_the_documents_to_check(tmp_path, changes, event)

    assert chosen == outputs
    if not outputs:
        assert "changes no document" in summary


def test_the_checks_of_a_pull_request_compare_it_with_its_base_branch() -> None:
    # The base that the event of a pull request names can be older than the commit of
    # main that its branch starts on: the release bot builds its branch again on a
    # newer main, and the event keeps the old base. The base branch, which the checkout
    # fetches with the whole history, is current.
    lint = (ROOT / ".github/workflows/lint.yml").read_text(encoding="utf-8")
    links = (ROOT / ".github/workflows/links.yml").read_text(encoding="utf-8")
    for workflow, name in ((lint, "lint"), (lint, "dco"), (links, "links")):
        job = job_of(workflow, name)
        assert "base.sha" not in job, name
        assert "BASE_REF: ${{ github.event.pull_request.base.ref }}" in job, name
        assert "fetch-depth: 0" in job or "'pull_request' && '0' ||" in job, name


def check_the_sign_offs(
    tmp_path: Path, *signed_off: bool
) -> tuple[PullRequest, subprocess.CompletedProcess[str]]:
    """Runs the DCO check, as GitHub does, on a pull request whose commits each have a
    sign-off or not, on a newer main than the base that its event names."""
    lint = (ROOT / ".github/workflows/lint.yml").read_text(encoding="utf-8")
    pull_request = a_pull_request_on_a_newer_main(tmp_path, {}, *signed_off)
    (tmp_path / "step.sh").write_text(
        script_of(lint, "Check the sign-off of every commit"),
        encoding="utf-8",
        newline="\n",
    )
    assert BASH
    return pull_request, subprocess.run(
        [BASH, "-e", str(tmp_path / "step.sh")],
        cwd=pull_request.repository,
        env={
            **os.environ,
            "BASE_REF": "main",
            "HEAD_SHA": pull_request.commits[-1],
            "PR_AUTHOR": "dev",
        },
        capture_output=True,
        encoding="utf-8",
        check=False,
    )


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize("signed_off", [(True,), (True, True)])
def test_the_sign_off_check_passes_a_pull_request_on_a_newer_main(
    tmp_path: Path, signed_off: tuple[bool, ...]
) -> None:
    # The squash commit of main lacks the sign-off of its author, but it is no commit
    # of the pull request, though it came after the base that the event names.
    pull_request, result = check_the_sign_offs(tmp_path, *signed_off)

    assert result.returncode == 0, result.stdout + result.stderr
    assert f"Checked the sign-off of {len(signed_off)} commit(s)." in result.stdout
    assert pull_request.squash not in result.stdout


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize("signed_off", [(False,), (True, False), (False, True)])
def test_the_sign_off_check_fails_a_commit_of_the_pull_request_without_one(
    tmp_path: Path, signed_off: tuple[bool, ...]
) -> None:
    pull_request, result = check_the_sign_offs(tmp_path, *signed_off)
    unsigned = pull_request.commits[signed_off.index(False)]

    assert result.returncode == 1
    assert (
        f"::error::Commit {unsigned} lacks the sign-off "
        "'Signed-off-by: Dev <dev@example.com>'. Commit with git commit -s."
    ) in result.stdout


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize(
    ("changes", "documents"),
    [
        # Main deleted and added a document since the base that the event names.
        ({}, []),
        (
            {
                "docs/guide.md": "changed\n",
                "docs/a new guide.md": "new\n",
                "CHANGELOG.md": "x\n",
            },
            ["docs/a new guide.md", "docs/guide.md"],
        ),
    ],
)
def test_the_prose_hints_give_vale_the_documents_that_the_pull_request_changes(
    tmp_path: Path, changes: dict[str, str | None], documents: list[str]
) -> None:
    lint = (ROOT / ".github/workflows/lint.yml").read_text(encoding="utf-8")
    # The step before finds the documents; the hints run only when it found some.
    outputs, _ = choose_the_documents_to_check(
        tmp_path, changes, workflow="lint.yml", step="Find the changed documents"
    )
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    # npm installs nothing; docker writes down the documents that Vale gets.
    for name in ("npm", "docker"):
        (stubs / name).write_text(
            f'#!/usr/bin/env bash\necho "{name} $*" >> "$CALLS"\n',
            encoding="utf-8",
            newline="\n",
        )
        (stubs / name).chmod(0o755)
    (tmp_path / "calls").touch()
    (tmp_path / "hints.sh").write_text(
        script_of(lint, "Hint at the spelling and the style of the changed documents"),
        encoding="utf-8",
        newline="\n",
    )
    if outputs.get("changed") == "true":
        result = subprocess.run(
            in_bash("-e", (tmp_path / "hints.sh").as_posix()),
            cwd=tmp_path / "repository",
            env={
                **os.environ,
                "STUBS": stubs.as_posix(),
                "CALLS": (tmp_path / "calls").as_posix(),
                "VALE": "vale",
                "GITHUB_STEP_SUMMARY": (tmp_path / "summary").as_posix(),
                "RUNNER_TEMP": tmp_path.as_posix(),
            },
            capture_output=True,
            encoding="utf-8",
            check=False,
        )
        assert result.returncode == 0, result.stderr
    summary = (tmp_path / "summary").read_text(encoding="utf-8")
    calls = (tmp_path / "calls").read_text(encoding="utf-8").splitlines()

    if documents:
        [docker] = [call for call in calls if call.startswith("docker ")]
        assert docker.endswith(" sh " + " ".join(documents)), docker
        assert f"in {len(documents)} changed document(s)." in summary
    else:
        assert calls == []
        assert "No document changes." in summary


def test_the_link_check_keeps_the_answers_of_the_sites_for_a_day() -> None:
    links = (ROOT / ".github/workflows/links.yml").read_text(encoding="utf-8")
    job = job_of(links, "links")
    cache = job[job.index("      - name: Restore the answers of the sites\n") :]
    assert "        uses: actions/cache@" in cache
    assert "          path: .lycheecache\n" in cache
    assert "          key: lychee-${{ github.run_id }}\n" in cache
    assert "          restore-keys: lychee-\n" in cache
    check = job[job.index("      - name: Check the links of the documentation\n") :]
    assert (
        "args: --config lychee.toml --no-progress --cache --max-cache-age 1d ${{ steps.documents.outputs.files }}\n"
        in check
    )
    # Without a document to check, neither runs; a changed document may have no link.
    for step in (cache, check):
        assert "        if: steps.documents.outputs.files != ''\n" in step
    assert "failIfEmpty: ${{ steps.documents.outputs.every == 'true' }}" in check
    # A pull request compares its documents with its base.
    assert (
        "fetch-depth: ${{ github.event_name == 'pull_request' && '0' || '1' }}" in job
    )


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize(
    ("changes", "documents"),
    [
        (
            {
                "README.md": "A changed README.\n",
                "docs/a new guide.md": "A new guide.\n",
                "CHANGELOG.md": "The changelog, which the release bot writes.\n",
                "lychee.toml": "A file that isn't a document.\n",
            },
            ["README.md", "docs/a new guide.md"],
        ),
        ({"CHANGELOG.md": "Only the changelog.\n"}, []),
        ({"docs/guide.md": None}, []),
        ({}, []),
    ],
)
def test_the_prose_hints_read_the_documents_that_a_pull_request_changes(
    tmp_path: Path, changes: dict[str, str | None], documents: list[str]
) -> None:
    outputs, summary = choose_the_documents_to_check(
        tmp_path, changes, workflow="lint.yml", step="Find the changed documents"
    )

    if documents:
        assert outputs == {"changed": "true"}
        # One name after the other, each ended by a NUL, which no name holds.
        listed = (tmp_path / "documents").read_text(encoding="utf-8")
        assert listed.split("\0") == [*documents, ""]
        assert summary == ""
    else:
        assert outputs == {}
        assert summary == "No document changes.\n"


@pytest.mark.parametrize("kind", ["blueprint", *KINDS])
def test_the_prose_hints_install_their_tools_from_the_cache_of_npm(
    projects: dict[str, Path], kind: str
) -> None:
    folder = ROOT if kind == "blueprint" else projects[kind]
    prose = job_of(
        (folder / ".github/workflows/lint.yml").read_text(encoding="utf-8"), "lint"
    )
    setup = step_of(prose, "      - uses: actions/setup-node@")
    hints = step_of(
        prose,
        "      - name: Hint at the spelling and the style of the changed documents",
    )
    assert "          cache: npm\n" in setup
    lock = re.search(r"\n          cache-dependency-path: (\S+)\n", setup)
    assert lock
    assert (folder / lock[1]).is_file()
    install = re.search(r"\n +npm ci --prefix (\S+) ", hints)
    assert install
    assert install[1] == Path(lock[1]).parent.as_posix()
    # Node and the packages come only for changed documents, the runs that install
    # them, so that every run with npm's cache has one to save.
    changed = (
        "        if: ${{ !cancelled() && steps.documents.outputs.changed == 'true' }}\n"
    )
    assert changed in setup
    assert changed in hints
    # The names that the step before found, which may hold spaces.
    assert "\n          mapfile -d '' -t files < \"$RUNNER_TEMP/documents\"\n" in hints


def test_a_nextcloud_app_packages_only_what_it_needs(
    projects: dict[str, Path],
) -> None:
    project = projects["nextcloud-app"]
    ignored = (project / ".nextcloudignore").read_text(encoding="utf-8").split("\n")
    for path in (
        ".devcontainer",
        ".githooks",
        ".lycheeignore",
        # The fragments of the changelog, which the release takes into CHANGELOG.md.
        "changelog.d",
        # The configuration of the mutation tests that a project commits, which the
        # weekly Mutation workflow reads in place of the one it writes.
        "infection.json5",
        "lychee.toml",
        "mkdocs.yml",
        "screenshots",
        # LICENSE carries the license text; LICENSES/ serves REUSE in the repository.
        "LICENSES",
    ):
        assert f"/{path}" in ignored, path
    # Every other file of the repository stays out of the package, also a new one.
    shipped = {"appinfo", "lib", "templates", "js", "css", "img", "l10n", "LICENSE"}
    shipped |= {"README.md", "CHANGELOG.md"}
    for entry in project.iterdir():
        assert entry.name in shipped or {entry.name, f"/{entry.name}"} & set(ignored), (
            entry.name
        )
    config = json.loads(
        (project / "release-please-config.json").read_text(encoding="utf-8")
    )["packages"]["."]
    # Lines of info.xml with the version elsewhere, such as screenshots at a tag.
    assert {"type": "generic", "path": "appinfo/info.xml"} in config["extra-files"]
    review = (project / ".github/dependency-review.yml").read_text(encoding="utf-8")
    assert "pkg:composer/netresearch/jsonmapper" in review
    assert "pkg:npm/%40cspell/dict-django" in review


def test_the_ci_builds_with_the_krankerl_of_the_release() -> None:
    pins = [
        dict(
            re.findall(
                r"(KRANKERL_(?:VERSION|SHA256)): (\S+)",
                (ROOT / ".github/workflows" / name).read_text(encoding="utf-8"),
            )
        )
        for name in ("ci-php.yml", "build-release.yml")
    ]
    assert len(pins[0]) == 2
    assert pins[0] == pins[1]


# Each curl of a script or of a step, with the lines it continues on; not one that a
# comment names.
CURL = re.compile(r"^[^#\n]*?\bcurl ((?:.*\\\n)*.*)$", re.MULTILINE)
# Where the blueprint and every repository made from it run curl.
SCRIPTS = (
    ".github/workflows/*.yml",
    ".github/*.sh",
    "scripts/*.sh",
    ".devcontainer/*.sh",
    ".githooks/*",
)
# What every download needs so that a passing error of GitHub or of another server,
# like the 504 of a release download that failed the checks of a Nextcloud app on
# main (Dennis-Otto/paperless-unified-search#94), fails no run: an answer with an
# error status is an error (--fail); every error, a reset connection too, brings
# another try after a pause that doubles each time (--retry, --retry-all-errors); a
# connection that hangs fails and tries again instead of holding the job until its
# time limit (--connect-timeout, --max-time); and the download goes into a file, which
# curl empties before it tries again, where in a pipe the start of a broken try would
# stay in front of the next one (--output).
DOWNLOAD = (
    "--fail",
    "--retry ",
    "--retry-all-errors",
    "--connect-timeout ",
    "--max-time ",
    "--output ",
)


def run_workflow_step(
    tmp_path: Path,
    script: str,
    cwd: Path,
    tools: dict[str, str],
    without: tuple[str, ...] = (),
    **variables: str,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    """Runs the script of a step as GitHub does, with bash -e and stand-ins for its
    tools, which write what they are called with to $CALLS, and without the variables
    named; the result, and the calls. The stand-ins come first on the PATH even in the
    bash of Git for Windows, which puts its own curl in front of it (in_bash)."""
    step = tmp_path / "step.sh"
    step.write_text(script, encoding="utf-8", newline="\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool, body in tools.items():
        (bin_dir / tool).write_text(
            f'#!/usr/bin/env bash\necho "{tool} $*" >> "$CALLS"\n{body}',
            encoding="utf-8",
            newline="\n",
        )
        (bin_dir / tool).chmod(0o755)
    calls = tmp_path / "calls"
    calls.touch()
    environment = {
        **{key: value for key, value in os.environ.items() if key not in without},
        "STUBS": bin_dir.as_posix(),
        "CALLS": calls.as_posix(),
        **variables,
    }
    result = subprocess.run(
        in_bash("-e", step.as_posix()),
        cwd=cwd,
        env=environment,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    return result, calls.read_text(encoding="utf-8").splitlines()


@pytest.mark.parametrize("kind", ["blueprint", *KINDS])
def test_every_download_tries_again_after_a_passing_error(
    projects: dict[str, Path], kind: str
) -> None:
    folder = ROOT if kind == "blueprint" else projects[kind]
    downloads = 0
    for pattern in SCRIPTS:
        for path in sorted(folder.glob(pattern)):
            for found in CURL.findall(path.read_text(encoding="utf-8")):
                command = re.sub(r"\\\n\s*", "", found)
                # An upload retries only where its API takes a second one without
                # harm, as the release in the App Store does.
                if "--request POST" in command:
                    continue
                # A request for a status that is an error, such as the 404 of an
                # address that leads nowhere, tries again only after an error of the
                # server or of the network, which --retry alone does.
                if "--write-out '%{http_code}'" in command:
                    for option in DOWNLOAD:
                        assert (option in command) is (
                            option not in ("--fail", "--retry-all-errors")
                        ), f"{path.name}: curl {command}"
                    continue
                downloads += 1
                for option in DOWNLOAD:
                    assert option in command, f"{path.name}: curl {command}"
    # The gitsign of the signed release tags, in every repository.
    assert downloads > 0


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize("cache", ["empty", "krankerl", "changed"])
def test_the_ci_of_a_nextcloud_app_takes_krankerl_from_its_cache(
    tmp_path: Path, cache: str
) -> None:
    workflow = (ROOT / ".github/workflows/ci-php.yml").read_text(encoding="utf-8")
    version = dict(re.findall(r"(KRANKERL_(?:VERSION|SHA256)): (\S+)", workflow))[
        "KRANKERL_VERSION"
    ]
    # Restored before the install, under a key that changes with krankerl; GitHub
    # saves it only after a run that passed, which checked it.
    restore = step_of(workflow, "      - name: Restore krankerl from the cache")
    assert workflow.index(restore) < workflow.index("      - name: Install krankerl")
    assert "uses: actions/cache@" in restore
    assert "path: ${{ runner.temp }}/krankerl\n" in restore
    assert (
        "key: krankerl-${{ env.KRANKERL_VERSION }}-${{ env.KRANKERL_SHA256 }}\n"
        in restore
    )
    package = b"the package of krankerl\n"
    temp = tmp_path / "temp"
    deb = temp / f"krankerl/krankerl_{version}_amd64.deb"
    if cache != "empty":
        deb.parent.mkdir(parents=True)
        deb.write_bytes(package if cache == "krankerl" else b"a changed package\n")
    script = script_of(
        workflow, "Install krankerl, which builds the package of the app"
    )

    result, calls = run_workflow_step(
        tmp_path,
        script,
        tmp_path,
        {
            "curl": textwrap.dedent(
                """\
                while (($# > 0)); do
                  if [[ "$1" == --output ]]; then echo "the package of krankerl" > "$2"; fi
                  shift
                done
                """
            ),
            "sudo": "",
        },
        RUNNER_TEMP=temp.as_posix(),
        KRANKERL_VERSION=version,
        KRANKERL_SHA256=hashlib.sha256(package).hexdigest(),
    )

    downloads = [call for call in calls if call.startswith("curl ")]
    installs = [call for call in calls if call.startswith("sudo ")]
    if cache == "changed":
        # The checksum is checked for a package of the cache too.
        assert result.returncode != 0
        assert downloads == []
        assert installs == []
        return
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(downloads) == (1 if cache == "empty" else 0)
    for download in downloads:
        assert all(option in download for option in DOWNLOAD), download
        assert f"--output {deb.as_posix()} " in download
    assert installs == [f"sudo dpkg --install {deb.as_posix()}"]


def test_a_nextcloud_app_follows_untrusted_input(projects: dict[str, Path]) -> None:
    project = projects["nextcloud-app"]
    check = (project / "scripts/check.sh").read_text(encoding="utf-8")
    # Psalm sees no input in a Nextcloud app on its own, which passes the parameters of
    # a request to a controller as arguments, and none of the sinks of Nextcloud: the
    # plugin of the blueprint teaches it both, for the app and for its canary.
    plugin = ".github/psalm/NextcloudTaintPlugin.php"
    assert (project / plugin).is_file()
    for config in ("psalm.xml", ".github/psalm/canary.xml"):
        root = ElementTree.parse(project / config).getroot()
        plugins = root.find("psalm:plugins", PSALM)
        assert plugins is not None, config
        assert [entry.get("filename") for entry in plugins] == [plugin], config
    # The canary proves that the analysis still sees, before it checks the app, whose
    # paths the CI shows in code scanning.
    steps = re.findall(r'^step "(Psalm[^"]*)"$', check, re.M)
    assert steps == ["Psalm", "Psalm taint canary", "Psalm taint analysis"]
    assert (
        "\nvendor/bin/psalm --taint-analysis --threads=1 --no-cache"
        " --report=build/psalm-taint.sarif\n" in check
    )
    # Only a Nextcloud app has PHP.
    for kind in KINDS:
        if kind != "nextcloud-app":
            assert not (projects[kind] / ".github/psalm").exists(), kind


def test_the_canary_has_a_path_to_each_kind_of_sink(projects: dict[str, Path]) -> None:
    psalm = projects["nextcloud-app"] / ".github/psalm"
    plugin = (psalm / "NextcloudTaintPlugin.php").read_text(encoding="utf-8")
    canary = (psalm / "canary/CanaryController.php").read_text(encoding="utf-8")
    expected = re.findall(r"// expect: (\w+)$", canary, re.M)
    # Each kind of sink that the plugin adds, and the queries, which nextcloud/ocp
    # marks itself, for a parameter of a controller, which only the plugin makes input.
    issues = {"FILE": "TaintedFile", "SSRF": "TaintedSSRF", "HEADER": "TaintedHeader"}
    kinds = set(re.findall(r"TaintKind::INPUT_(\w+)", plugin))
    assert kinds == set(issues)
    assert set(expected) == {*issues.values(), "TaintedSql"}
    # A sink of an interface, of the interface that it extends, of the data of the
    # app, and of a constructor.
    for call in (
        "$this->folder->newFile($name); // expect: TaintedFile",
        "$this->file->move('/user/files/' . $target); // expect: TaintedFile",
        "$this->appData->getFile($name); // expect: TaintedFile",
        "return new RedirectResponse($url); // expect: TaintedHeader",
    ):
        assert call in canary, call
    # Nextcloud routes to a public static method too, so its parameters are input.
    assert "\tpublic static function back(string $url): RedirectResponse {\n" in canary
    assert "isStatic" not in plugin
    # The sources that the plugin adds by their methods: the term of a search and the
    # answer of another server.
    assert "$this->folder->get($query->getTerm()); // expect: TaintedFile" in canary
    assert "->getBody();" in canary
    for source in ("'getTerm'", "'getBody'"):
        assert source in plugin, source
    # What the canary must not find: input that a function of the app escapes, and the
    # parameters of a class that is no controller.
    assert "@psalm-taint-escape file" in canary
    assert "$this->folder->newFile(self::fileName($name));\n" in canary
    assert "final class CanaryService {" in canary
    # A name that nextcloud/ocp no longer has stops the analysis, instead of leaving it
    # blind to that sink.
    assert "throw self::changed(" in plugin


PHP = shutil.which("php")


@pytest.mark.skipif(PHP is None, reason="the comparison of the canary runs in PHP")
@pytest.mark.parametrize("change", ["none", "missed", "unexpected", "no report"])
def test_the_canary_fails_unless_the_analysis_finds_its_paths_and_no_other(
    projects: dict[str, Path], tmp_path: Path, change: str
) -> None:
    assert PHP
    shutil.copytree(projects["nextcloud-app"] / ".github/psalm", tmp_path / "psalm")
    canary = tmp_path / "psalm/canary/CanaryController.php"
    lines = canary.read_text(encoding="utf-8").splitlines()
    expected = [
        (number, found[1])
        for number, line in enumerate(lines, 1)
        if (found := re.search(r"// expect: (\w+)$", line))
    ]
    # As Psalm reports each path: its kind, the file and the line where it arrives.
    issues = [
        {"type": issue, "file_path": canary.as_posix(), "line_from": number}
        for number, issue in expected
    ]
    escaped = lines.index("\t\t$this->folder->newFile(self::fileName($name));") + 1
    if change == "missed":
        issues.pop(0)
    elif change == "unexpected":
        issues.append(
            {
                "type": "TaintedFile",
                "file_path": canary.as_posix(),
                "line_from": escaped,
            }
        )
    if change != "no report":
        (tmp_path / "psalm-canary.json").write_text(
            json.dumps(issues), encoding="utf-8"
        )

    result = subprocess.run(
        [PHP, "psalm/check-canary.php", "psalm-canary.json"],
        cwd=tmp_path,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )

    if change == "none":
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.stdout == (
            f"The taint analysis finds each of the {len(expected)} paths of the canary,"
            " and no other.\n"
        )
        return
    assert result.returncode == 1
    number, issue = expected[0]
    message = {
        "missed": "The taint analysis missed the path that the canary expects at"
        f" CanaryController.php:{number} {issue}.\n",
        "unexpected": "The taint analysis found a path at"
        f" CanaryController.php:{escaped} TaintedFile, which the canary doesn't"
        " expect.\n",
        "no report": "Psalm wrote no report of the canary to psalm-canary.json; its"
        " output above says why.\n",
    }[change]
    assert message in result.stdout + result.stderr


@pytest.mark.skipif(BASH is None, reason="the check runs in bash, Git Bash on Windows")
@pytest.mark.parametrize("sees", [True, False])
def test_the_canary_of_the_taint_analysis_runs_beside_the_types(
    projects: dict[str, Path], tmp_path: Path, sees: bool
) -> None:
    check = (projects["nextcloud-app"] / "scripts/check.sh").read_text(encoding="utf-8")
    start = check.index('step "Psalm"\n')
    steps = check[start : check.index('step "Tests, with every line covered"', start)]
    repository = tmp_path / "repository"
    (repository / "scripts").mkdir(parents=True)
    # Its set-up, such as set -euo pipefail and the folder it runs in, and the steps.
    (repository / "scripts/psalm.sh").write_text(
        check[: check.index('step "Text files"')] + steps,
        encoding="utf-8",
        newline="\n",
    )
    # The report of a run before, which passed.
    (repository / "build").mkdir()
    (repository / "build/psalm-canary.json").write_text("every path", encoding="utf-8")
    psalm = repository / "vendor/bin/psalm"
    psalm.parent.mkdir(parents=True)
    psalm.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            echo "psalm $*" >> "$CALLS"
            echo "Psalm ran with $1"
            if [[ "$1" == --config=* && -n "$SEES" ]]; then
              echo "every path" > build/psalm-canary.json
            fi
            """
        ),
        encoding="utf-8",
        newline="\n",
    )
    psalm.chmod(0o755)
    php = (
        'grep -q "every path" "$2" 2>/dev/null && exit 0\n'
        "echo 'The taint analysis missed a path.'\n"
        "exit 1\n"
    )

    result, calls = run_workflow_step(
        tmp_path,
        "bash scripts/psalm.sh\n",
        repository,
        {"php": php},
        SEES="yes" if sees else "",
    )

    # The canary runs in the background, with the plugin and the public API of
    # Nextcloud of the app, and writes its findings for the comparison.
    canary = (
        "psalm --config=.github/psalm/canary.xml --taint-analysis --threads=1"
        " --no-cache --no-progress --monochrome --report=build/psalm-canary.json"
    )
    assert canary in calls
    assert "psalm --threads=1 --no-cache" in calls
    assert "php .github/psalm/check-canary.php build/psalm-canary.json" in calls
    analysis = (
        "psalm --taint-analysis --threads=1 --no-cache --report=build/psalm-taint.sarif"
    )
    if sees:
        assert result.returncode == 0, result.stdout + result.stderr
        assert analysis in calls
        assert "Psalm ran with --config" not in result.stdout
    else:
        # An analysis that has gone blind, or a canary that wrote no report, checks no
        # app, and shows what Psalm said; the report of a run before doesn't count.
        assert result.returncode == 1
        assert analysis not in calls
        assert result.stdout.endswith(
            "\n== Psalm taint canary\nThe taint analysis missed a path.\n"
            "Psalm ran with --config=.github/psalm/canary.xml\n"
        )


@pytest.mark.skipif(BASH is None, reason="the check runs in bash, Git Bash on Windows")
def test_a_failed_check_of_the_types_leaves_no_canary_running(
    projects: dict[str, Path], tmp_path: Path
) -> None:
    check = (projects["nextcloud-app"] / "scripts/check.sh").read_text(encoding="utf-8")
    start = check.index('step "Psalm"\n')
    steps = check[start : check.index('step "Tests, with every line covered"', start)]
    repository = tmp_path / "repository"
    (repository / "scripts").mkdir(parents=True)
    (repository / "scripts/psalm.sh").write_text(
        check[: check.index('step "Text files"')] + steps,
        encoding="utf-8",
        newline="\n",
    )
    psalm = repository / "vendor/bin/psalm"
    psalm.parent.mkdir(parents=True)
    # The canary takes its time and says when it is stopped; the types have an error.
    # The types wait until the canary listens for its stop, or a busy runner kills the
    # canary before it could say so.
    psalm.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            echo "psalm $*" >> "$CALLS"
            if [[ "$1" == --config=* ]]; then
              trap 'kill "$!"; echo "canary stopped" >> "$CALLS"; exit 143' TERM
              sleep 30 &
              touch "$CALLS.listens"
              wait
              echo "canary finished" >> "$CALLS"
              exit 0
            fi
            for _ in $(seq 100); do
              [[ -e "$CALLS.listens" ]] && break
              sleep 0.1
            done
            echo "ERROR: a type"
            exit 2
            """
        ),
        encoding="utf-8",
        newline="\n",
    )
    psalm.chmod(0o755)

    result, _ = run_workflow_step(
        tmp_path, "bash scripts/psalm.sh\n", repository, {"php": "exit 0\n"}
    )

    # The check stops at the types, and stops the canary that it started.
    assert result.returncode == 1
    assert "== Psalm taint canary" not in result.stdout
    calls = tmp_path / "calls"
    for _ in range(100):
        if "canary stopped" in calls.read_text(encoding="utf-8"):
            break
        time.sleep(0.1)
    assert "canary stopped" in calls.read_text(encoding="utf-8")
    assert "canary finished" not in calls.read_text(encoding="utf-8")


def test_code_scanning_shows_the_paths_of_the_taint_analysis() -> None:
    workflow = (ROOT / ".github/workflows/ci-php.yml").read_text(encoding="utf-8")
    assert "\npermissions:\n  contents: read\n\n" in workflow
    check = job_alone(workflow, "check")
    keep = step_of(check, "      - name: Keep the report of the taint analysis")
    assert "        id: taint\n" in keep
    # Also when the analysis found a path, which fails the check.
    assert (
        "        if: always() && hashFiles('build/psalm-taint.sarif') != ''\n" in keep
    )
    assert "          path: build/psalm-taint.sarif\n" in keep
    assert "    outputs:\n" in check
    assert "      taint: ${{ steps.taint.outcome }}\n" in check
    # The job that runs the tools of Composer and the code of a pull request can't
    # write alerts; the one that uploads them runs no code of the app.
    assert "security-events" not in check
    report = job_alone(workflow, "taint-report")
    assert "    name: taint report (php)\n" in report
    assert "    needs: check\n" in report
    assert condition_of(report) == (
        "!cancelled() && needs.check.outputs.taint == 'success' &&"
        " (github.event_name != 'pull_request' ||"
        " github.event.pull_request.head.repo.full_name == github.repository)"
    )
    assert "    permissions:\n      contents: read\n      security-events: write\n" in (
        report
    )
    for code in ("composer", "scripts/check.sh", "vendor/bin"):
        assert code not in report, code
    assert "          persist-credentials: false\n" in report
    upload = step_of(report, "      - name: Upload the paths to code scanning")
    assert "        uses: github/codeql-action/upload-sarif@" in upload
    assert (
        "          sarif_file: ${{ runner.temp }}/psalm-taint/psalm-taint.sarif\n"
        in upload
    )
    assert "          category: psalm-taint\n" in upload
    assert report.endswith(explain_step("taint report (php)"))


def test_psalm_reads_ahead_only_the_packages_that_composer_cannot_load(
    projects: dict[str, Path],
) -> None:
    # Psalm reads the files of extraFiles before it checks the code, and finds every
    # other class through the autoloader of Composer when the code uses it. Reading
    # all of vendor/, some 5,000 files, took 30 of the 35 seconds of each of its two
    # runs, for the same findings; so it reads ahead the packages that the autoloader
    # can't find, and only those.
    project = projects["nextcloud-app"]
    extra = (
        ElementTree.parse(project / "psalm.xml")
        .getroot()
        .find("psalm:extraFiles", PSALM)
    )
    assert extra is not None
    assert [entry.tag for entry in extra] == [f"{{{PSALM['psalm']}}}directory"]
    read_ahead = [str(entry.get("name")) for entry in extra]
    lock = json.loads((project / "composer.lock").read_text(encoding="utf-8"))
    without_autoloader = sorted(
        f"vendor/{package['name']}"
        for package in (*lock["packages"], *lock["packages-dev"])
        # A tool, such as the PHAR of php-cs-fixer, holds no code that the app uses.
        if not package.get("autoload") and package.get("type", "library") == "library"
    )
    assert read_ahead == without_autoloader == ["vendor/nextcloud/ocp"]
    # The canary of the taint analysis reads the same, from the root of the repository.
    canary = ElementTree.parse(project / ".github/psalm/canary.xml").getroot()
    assert canary.get("resolveFromConfigFile") == "false"
    extra = canary.find("psalm:extraFiles", PSALM)
    assert extra is not None
    assert [str(entry.get("name")) for entry in extra] == read_ahead
    # No run keeps a cache of its own, so that no result depends on one.
    check = (project / "scripts/check.sh").read_text(encoding="utf-8")
    assert check.count("vendor/bin/psalm ") == 3
    assert check.count(" --threads=1 --no-cache") == 3


@pytest.mark.skipif(BASH is None, reason="the check runs in bash, Git Bash on Windows")
@pytest.mark.parametrize("broken", [False, True])
def test_the_syntax_check_of_a_nextcloud_app_reads_the_files_at_once(
    projects: dict[str, Path], tmp_path: Path, broken: bool
) -> None:
    check = (projects["nextcloud-app"] / "scripts/check.sh").read_text(encoding="utf-8")
    start = check.index('step "PHP syntax"')
    syntax = check[start : check.index('step "Oldest PHP"', start)]
    repository = tmp_path / "repository"
    (repository / "scripts").mkdir(parents=True)
    # Its set-up, such as set -euo pipefail and the folder it runs in, and the step.
    (repository / "scripts/syntax.sh").write_text(
        check[: check.index('step "Text files"')] + syntax,
        encoding="utf-8",
        newline="\n",
    )
    names = [
        "appinfo/routes.php",
        "lib/AppInfo/Application.php",
        "lib/Service/A Service.php",
        "tests/Unit/AppInfo/ApplicationTest.php",
        *(["lib/Broken.php"] if broken else []),
    ]
    for name in [*names, "vendor/autoload.php"]:
        (repository / name).parent.mkdir(parents=True, exist_ok=True)
        (repository / name).write_text("<?php\n", encoding="utf-8")

    # As PHP answers without a php.ini: everything on stdout, and 255 for an error,
    # after which xargs starts no further PHP.
    php = textwrap.dedent(
        """\
        if [[ "$2" == *Broken.php ]]; then
          printf '\\nParse error: Unclosed "(" in %s on line 2\\n' "$2"
          echo "Errors parsing $2"
          exit 255
        fi
        echo "No syntax errors detected in $2"
        """
    )
    result, calls = run_workflow_step(
        tmp_path,
        "bash scripts/syntax.sh\n",
        repository,
        {"php": php, "getconf": "echo 4\n"},
    )

    # One PHP for each file of the app, as many at once as there are processors, and
    # only the errors show.
    assert calls[0] == "getconf _NPROCESSORS_ONLN"
    every = {f"php --syntax-check {name}" for name in names}
    assert "No syntax errors detected" not in result.stdout
    if broken:
        assert result.returncode != 0
        assert "php --syntax-check lib/Broken.php" in calls
        assert set(calls[1:]) <= every
        assert (
            'Parse error: Unclosed "(" in lib/Broken.php on line 2\n' in result.stdout
        )
        assert "Errors parsing lib/Broken.php\n" in result.stdout
        assert "Every PHP file parses." not in result.stdout
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert sorted(calls[1:]) == sorted(every)
        assert result.stdout == "\n== PHP syntax\nEvery PHP file parses.\n"


@pytest.mark.skipif(BASH is None, reason="the check runs in bash, Git Bash on Windows")
@pytest.mark.parametrize(
    ("oldest", "installed", "failure", "expected"),
    [
        # An app whose tools still run on its oldest PHP, as one made before PHP 8.3.
        ("8.3", False, None, "The tools run on PHP 8.3, the oldest PHP of the app.\n"),
        # An appinfo/info.xml without a PHP: Nextcloud then takes each PHP that it runs on.
        ("", False, None, "The tools run on PHP 8.3, the oldest PHP of the app.\n"),
        (
            "8.2",
            True,
            None,
            "The code of the app parses on PHP 8.2, and the packages that it ships"
            " install there.\n",
        ),
        ("8.2", True, "syntax", None),
        ("8.2", True, "packages", None),
        ("8.2", False, "missing", None),
        (
            "8.2",
            False,
            "elsewhere",
            "PHP 8.2, the oldest PHP of appinfo/info.xml, is not installed here as"
            " php8.2; the CI checks the code on it.\n",
        ),
    ],
)
def test_the_code_of_a_nextcloud_app_parses_and_installs_on_its_oldest_php(
    projects: dict[str, Path],
    tmp_path: Path,
    oldest: str,
    installed: bool,
    failure: str | None,
    expected: str | None,
) -> None:
    check = (projects["nextcloud-app"] / "scripts/check.sh").read_text(encoding="utf-8")
    start = check.index('step "Oldest PHP"')
    step = check[start : check.index('step "Coding standard"', start)]
    # Right after the syntax on the PHP of the tools.
    assert check.index('step "PHP syntax"') < start
    repository = tmp_path / "repository"
    (repository / "scripts").mkdir(parents=True)
    (repository / "scripts/oldest.sh").write_text(
        check[: check.index('step "Text files"')] + step,
        encoding="utf-8",
        newline="\n",
    )
    # What the app ships, and the tests and the tools, which only the PHP of the tools
    # runs.
    shipped = [
        "appinfo/routes.php",
        "lib/AppInfo/Application.php",
        "lib/Service/A Service.php",
        "templates/main.php",
        *(["lib/Broken.php"] if failure == "syntax" else []),
    ]
    for name in [*shipped, "tests/Unit/ApplicationTest.php", "vendor/autoload.php"]:
        (repository / name).parent.mkdir(parents=True, exist_ok=True)
        (repository / name).write_text("<?php\n", encoding="utf-8")
    # The PHP of the tools answers the two questions of the step: the oldest PHP of
    # appinfo/info.xml and its own version.
    php = textwrap.dedent(
        """\
        case "$2" in
          *simplexml_load_file*) printf '%s' "$OLDEST" ;;
          *PHP_MAJOR_VERSION*) printf 8.3 ;;
        esac
        """
    )
    oldest_php = textwrap.dedent(
        """\
        if [[ "$1" == --syntax-check ]]; then
          if [[ "$2" == *Broken.php ]]; then
            printf '\nParse error: syntax error, unexpected identifier in %s on line 2\n' "$2"
            echo "Errors parsing $2"
            exit 255
          fi
          echo "No syntax errors detected in $2"
        elif [[ -n "$NEEDS_NEWER" ]]; then
          echo "php 8.2.34 acme/clock requires php (>=8.3) failed"
          exit 2
        else
          echo "php 8.2.34 success"
        fi
        """
    )
    tools = {"php": php, "composer": "", "getconf": "echo 4\n"}
    if installed:
        tools["php8.2"] = oldest_php
    # No PHP 8.2 of this computer stands in for the missing one.
    path = os.pathsep.join(
        folder
        for folder in os.environ.get("PATH", "").split(os.pathsep)
        if not (Path(folder) / "php8.2").exists()
    )
    result, calls = run_workflow_step(
        tmp_path,
        "bash scripts/oldest.sh\n",
        repository,
        tools,
        ("CI",) if failure == "elsewhere" else (),
        OLDEST=oldest,
        NEEDS_NEWER="yes" if failure == "packages" else "",
        PATH=path,
        **({} if failure == "elsewhere" else {"CI": "true"}),
    )

    on_oldest = [call for call in calls if call.startswith("php8.2 ")]
    if expected is not None:
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.stdout.endswith(expected)
    else:
        assert result.returncode != 0
        assert "The code of the app parses" not in result.stdout
    if not installed:
        assert not on_oldest
    if failure == "missing":
        assert result.stderr == (
            "PHP 8.2, the oldest PHP of appinfo/info.xml, is missing: the CI needs it"
            " as php8.2 beside PHP 8.3, the PHP of the tools.\n"
        )
    if failure == "syntax":
        assert "Errors parsing lib/Broken.php\n" in result.stdout
        assert not any("check-platform-reqs" in call for call in on_oldest)
    if installed and failure != "syntax":
        # Each file that the app ships, on as many processors as there are, and none of
        # its tests or tools; then the packages that it ships, on the same PHP.
        syntax = sorted(call for call in on_oldest if "--syntax-check" in call)
        assert syntax == sorted(f"php8.2 --syntax-check {name}" for name in shipped)
        assert "No syntax errors detected" not in result.stdout
        # The Composer of the PATH, a PHAR that the oldest PHP runs.
        assert re.fullmatch(
            r"php8\.2 \S+/bin/composer check-platform-reqs --lock --no-dev",
            on_oldest[-1],
        )
        assert ("acme/clock requires php (>=8.3) failed" in result.stdout) == (
            failure == "packages"
        )


def test_the_ci_of_a_nextcloud_app_keeps_the_packages_of_composer() -> None:
    workflow = (ROOT / ".github/workflows/ci-php.yml").read_text(encoding="utf-8")
    find = step_of(workflow, "      - name: Find the cache of Composer")
    restore = step_of(
        workflow, "      - name: Restore the packages of Composer from the cache"
    )
    install = workflow.index("      - name: Install the locked tools\n")
    assert workflow.index(find) < workflow.index(restore) < install
    assert "        id: composer\n" in find
    assert (
        '        run: echo "files=$(composer config cache-files-dir)" >> "$GITHUB_OUTPUT"\n'
        in find
    )
    assert "        uses: actions/cache@" in restore
    assert "          path: ${{ steps.composer.outputs.files }}\n" in restore
    # A changed lock file starts from the packages of the one before.
    assert (
        "          key: composer-${{ runner.os }}-${{ hashFiles('composer.lock') }}\n"
        in restore
    )
    assert "          restore-keys: composer-${{ runner.os }}-\n" in restore


# The two PHPs of the CI of a Nextcloud app, in the CI and in the Variants, which run
# its checks with its own tools.
PHP_WORKFLOWS = [
    ("ci-php.yml", ""),
    ("variants.yml", "matrix.kind == 'nextcloud-app' && "),
]


@pytest.mark.parametrize(("name", "condition"), PHP_WORKFLOWS)
def test_the_tools_of_a_nextcloud_app_run_on_the_php_of_its_composer_json(
    name: str, condition: str
) -> None:
    workflow = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
    find = step_of(
        workflow,
        "      - name: Find the PHP of the tools and the oldest PHP of the app",
    )
    oldest = step_of(workflow, "      - name: Set up the oldest PHP of the app")
    tools = step_of(workflow, "      - name: Set up the PHP of the tools")
    # The oldest PHP first and that of the tools last, which php runs then; both
    # before Composer installs the tools.
    assert workflow.index(find) < workflow.index(oldest) < workflow.index(tools)
    assert workflow.index(tools) < workflow.index("composer install")
    assert "        id: php\n" in find
    assert (
        f"        if: {condition}steps.php.outputs.oldest != steps.php.outputs.tools\n"
        in oldest
    )
    assert "          php-version: ${{ steps.php.outputs.oldest }}\n" in oldest
    assert "          coverage: none\n" in oldest
    assert "          php-version: ${{ steps.php.outputs.tools }}\n" in tools
    assert "          coverage: pcov\n" in tools
    assert "          tools: composer:v2\n" in tools
    # The same extensions on both, which the packages of the app may need.
    extensions = "          extensions: dom, libxml, mbstring, xml\n"
    assert extensions in oldest
    assert extensions in tools
    # No PHP of its own beside the two that the app names.
    assert workflow.count("uses: shivammathur/setup-php@") == 2
    assert 'php-version: "' not in workflow
    # The same versions in the CI and in the Variants.
    ci = (ROOT / ".github/workflows/ci-php.yml").read_text(encoding="utf-8")
    assert script_of(
        workflow, "Find the PHP of the tools and the oldest PHP of the app"
    ) == (script_of(ci, "Find the PHP of the tools and the oldest PHP of the app"))


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize(
    ("platform", "php", "expected"),
    [
        # A new app: its tools on PHP 8.3, its code from PHP 8.2 on.
        ({"php": "8.3.16"}, '<php min-version="8.2"/>', "tools=8.3\noldest=8.2\n"),
        # An app made before, whose tools still run on its oldest PHP.
        ({"php": "8.2.27"}, '<php min-version="8.2"/>', "tools=8.2\noldest=8.2\n"),
        # Without a platform, Composer locks the tools for the oldest PHP.
        ({}, '<php min-version="8.2.0" max-version="8.5"/>', "tools=8.2\noldest=8.2\n"),
        # Without a PHP in appinfo/info.xml, the app runs on that of its tools.
        ({"php": "8.4.1"}, "", "tools=8.4\noldest=8.4\n"),
        ({}, "", None),
    ],
)
def test_the_ci_reads_the_php_of_the_tools_and_the_oldest_php_of_the_app(
    tmp_path: Path, platform: dict[str, str], php: str, expected: str | None
) -> None:
    workflow = (ROOT / ".github/workflows/ci-php.yml").read_text(encoding="utf-8")
    script = script_of(
        workflow, "Find the PHP of the tools and the oldest PHP of the app"
    )
    app = tmp_path / "app"
    (app / "appinfo").mkdir(parents=True)
    config: dict[str, object] = {"sort-packages": True}
    if platform:
        config["platform"] = platform
    manifest = {"require": {"php": "^8.2"}, "config": config}
    (app / "composer.json").write_text(json.dumps(manifest), encoding="utf-8")
    (app / "appinfo/info.xml").write_text(
        f"<info><id>demo</id><dependencies>{php}"
        '<nextcloud min-version="33" max-version="35"/></dependencies></info>\n',
        encoding="utf-8",
    )
    output = tmp_path / "output"
    output.touch()

    result, _ = run_workflow_step(
        tmp_path,
        script,
        app,
        # The Python of the tests, not one that the PATH of Windows names.
        {"python3": f'exec "{Path(sys.executable).as_posix()}" "$@"\n'},
        GITHUB_OUTPUT=output.as_posix(),
    )

    if expected is None:
        assert result.returncode != 0
        assert result.stderr == (
            "Neither config.platform.php of composer.json nor appinfo/info.xml names a"
            " PHP.\n"
        )
        assert output.read_text(encoding="utf-8") == ""
    else:
        assert result.returncode == 0, result.stderr
        assert output.read_text(encoding="utf-8") == expected


def test_php_cs_fixer_starts_from_the_cache_of_the_ci(
    projects: dict[str, Path],
) -> None:
    workflow = (ROOT / ".github/workflows/ci-php.yml").read_text(encoding="utf-8")
    restore = step_of(workflow, "      - name: Restore the cache of php-cs-fixer")
    assert workflow.index(restore) < workflow.index("      - name: Run the checks\n")
    assert "        uses: actions/cache@" in restore
    assert "          path: .php-cs-fixer.cache\n" in restore
    tools = "${{ hashFiles('composer.lock', '.php-cs-fixer.dist.php') }}"
    # Every run saves what it checked; the next one starts from the latest.
    assert f"          key: php-cs-fixer-{tools}-${{{{ github.sha }}}}\n" in restore
    assert f"          restore-keys: php-cs-fixer-{tools}-\n" in restore
    # php-cs-fixer keeps its cache there, as the configuration of the app leaves it,
    # and Git ignores it.
    project = projects["nextcloud-app"]
    config = (project / ".php-cs-fixer.dist.php").read_text(encoding="utf-8")
    assert "setCacheFile" not in config
    assert "setUsingCache" not in config
    assert "\n/.php-cs-fixer.cache\n" in (project / ".gitignore").read_text(
        encoding="utf-8"
    )
    check = (project / "scripts/check.sh").read_text(encoding="utf-8")
    assert "\nvendor/bin/php-cs-fixer fix --dry-run --diff\n" in check


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize(
    ("ci", "reachable", "code", "message"),
    [
        ("true", True, 0, "appinfo/info.xml follows the schema of the App Store."),
        ("", True, 0, "appinfo/info.xml follows the schema of the App Store."),
        # Locally, the CI checks it then.
        (
            "",
            False,
            0,
            "The schema of the App Store is out of reach here; the CI checks it.",
        ),
        # In the CI, nothing else would: a broken info.xml could merge while the App
        # Store is down.
        (
            "true",
            False,
            1,
            "The schema of the App Store is out of reach, and the CI checks"
            " appinfo/info.xml against it; run the checks again once"
            " apps.nextcloud.com answers.",
        ),
    ],
)
def test_the_ci_checks_the_metadata_of_a_nextcloud_app_in_any_case(
    projects: dict[str, Path],
    tmp_path: Path,
    ci: str,
    reachable: bool,
    code: int,
    message: str,
) -> None:
    check = (projects["nextcloud-app"] / "scripts/check.sh").read_text(encoding="utf-8")
    start = check.index('step "App metadata"')
    metadata = check[start : check.index('step "PHP syntax"', start)]
    repository = tmp_path / "repository"
    (repository / "scripts").mkdir(parents=True)
    # Its set-up, such as set -euo pipefail and the folder it runs in, and the step.
    (repository / "scripts/metadata.sh").write_text(
        check[: check.index('step "Text files"')] + metadata,
        encoding="utf-8",
        newline="\n",
    )
    temporary = tmp_path / "tmp"
    temporary.mkdir()
    curl = (
        textwrap.dedent(
            """\
            while (($# > 0)); do
              if [[ "$1" == --output ]]; then echo "<xs:schema/>" > "$2"; fi
              shift
            done
            """
        )
        if reachable
        else 'echo "curl: (22) The requested URL returned error: 504" >&2\nexit 22\n'
    )
    result, calls = run_workflow_step(
        tmp_path,
        "bash scripts/metadata.sh\n",
        repository,
        {"curl": curl, "php": ""},
        without=("CI",),
        TMPDIR=temporary.as_posix(),
        **({"CI": ci} if ci else {}),
    )

    assert result.returncode == code, result.stdout + result.stderr
    assert result.stdout.endswith(f"\n{message}\n")
    assert len(calls) == (2 if reachable else 1), calls
    assert all(option in calls[0] for option in DOWNLOAD), calls[0]
    # PHP checks info.xml against the schema that curl downloaded.
    assert [call.split(" ", 2)[:2] for call in calls[1:]] == (
        [["php", "-r"]] if reachable else []
    )
    # The schema goes again.
    assert list(temporary.iterdir()) == []


# It starts the tool, which in the copy of the mutation tests is the code with the
# mutants, and the variables of mutmut switch them in that process too.
@pytest.mark.mutation_unsafe
@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
def test_a_dry_run_of_the_upstream_bot_shows_its_pull_request_and_changes_nothing(
    projects: dict[str, Path], tmp_path: Path
) -> None:
    project = projects["nextcloud-app"]
    work = tmp_path / "work"
    for name in ("appinfo/info.xml", "CHANGELOG.md", ".github/blueprint.py"):
        (work / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(project / name, work / name)
    shutil.copytree(project / ".github/blueprint", work / ".github/blueprint")
    supported = re.search(
        r'max-version="(\d+)"', (work / "appinfo/info.xml").read_text(encoding="utf-8")
    )
    assert supported
    # The next major version of Nextcloud is out.
    newest = int(supported[1]) + 1
    for command in (
        ["init", "--quiet"],
        ["config", "core.autocrlf", "false"],
        ["add", "."],
        [
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--quiet",
            "--message",
            "start",
        ],
    ):
        subprocess.run(["git", *command], cwd=work, check=True)
    script = script_of(
        (ROOT / ".github/workflows/upstream.yml").read_text(encoding="utf-8"),
        "Raise max-version to the newest major version of Nextcloud",
    )

    result, calls = run_workflow_step(
        tmp_path,
        script,
        work,
        {
            # Only what a dry run may ask; it writes nothing to GitHub.
            "gh": textwrap.dedent(
                f"""\
                case "$*" in
                  "api repos/nextcloud/server/releases/latest --jq .tag_name") echo v{newest}.0.1 ;;
                  "pr list --head upstream/nextcloud-{newest} --state open --json number --jq .[].number") ;;
                  *) exit 1 ;;
                esac
                """
            ),
            "python3": f'exec "{Path(sys.executable).as_posix()}" "$@"\n',
        },
        GH_TOKEN="token",
        GH_REPO="Someone/app",
        AUTOMERGE="",
        DRY_RUN="true",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert [call for call in calls if call.startswith("gh ")] == [
        "gh api repos/nextcloud/server/releases/latest --jq .tag_name",
        f"gh pr list --head upstream/nextcloud-{newest} --state open --json number"
        " --jq .[].number",
    ]
    assert (
        f'A dry run: the pull request "feat: support Nextcloud {newest}" from the'
        f" branch upstream/nextcloud-{newest} would make this change."
    ) in result.stdout
    # The change of the commit that it would make.
    assert re.search(
        rf'^\+\t\t<nextcloud min-version="\d+" max-version="{newest}"/>$',
        result.stdout,
        re.MULTILINE,
    )
    # The entry in a fragment of its own, which no release conflicts with.
    assert f"\n+++ b/changelog.d/nextcloud-{newest}.md\n" in result.stdout
    assert f"\n+### Changed\n+\n+- Supports Nextcloud {newest}.\n" in result.stdout
    assert "CHANGELOG.md" not in result.stdout
    # And its description says where the entry goes.
    workflow = (project / ".github/workflows/upstream.yml").read_text(encoding="utf-8")
    assert "a fragment of the changelog, changelog.d/nextcloud-<version>.md" in workflow
    assert "CHANGELOG.md" not in workflow


@pytest.mark.parametrize("kind", KINDS)
def test_secrets_stay_out_of_git(projects: dict[str, Path], kind: str) -> None:
    ignored = (projects[kind] / ".gitignore").read_text(encoding="utf-8").split("\n")
    for pattern in (".env", "*.pem", "*.key", "auth.json", "!.env.example"):
        assert pattern in ignored, pattern


def files_of_the_project() -> list[str]:
    """The patterns of _skip_if_exists in copier.yml: the files that belong to a
    project after its first copy, which an update never overwrites."""
    config = (ROOT / "copier.yml").read_text(encoding="utf-8")
    block = config.split("_skip_if_exists:", 1)[1].split("\n\n", 1)[0]
    return re.findall(r'^  - "?([^"\n]+?)"?$', block, re.MULTILINE)


def test_updates_reach_every_file_of_the_blueprint() -> None:
    # Copier matches _skip_if_exists like .gitignore; a pattern without a slash
    # would match at any depth and keep the blueprint's files from their updates.
    skip = files_of_the_project()
    assert "/*.py" in skip
    # The patterns as Copier reads them.
    matcher = pathspec.PathSpec.from_lines("gitignore", skip)
    for owned in (
        "README.md",
        "CHANGELOG.md",
        "mkdocs.yml",
        "docs/index.md",
        "issue_assistant.py",
        "Dockerfile",
        "img/app.svg",
        "tests/test_demo.py",
        "tests/bootstrap.php",
        "custom_components/demo/__init__.py",
        ".github/labels.toml",
        ".github/checks.project.toml",
        "docs/security.md",
        ".github/agents.project.md",
    ):
        assert matcher.match_file(owned), owned
    for updated in (
        *(f".github/{name}" for name in TOOL),
        ".devcontainer/Dockerfile",
        ".github/social-preview/Dockerfile",
        ".github/workflows/ci.yml",
        ".github/workflows/docs.yml",
        ".github/docs-requirements.txt",
        ".github/checks.toml",
        "docs/README.md",
        "scripts/check.sh",
        "scripts/diagrams.sh",
        "changelog.d/.gitkeep",
        "AGENTS.md",
        "CLAUDE.md",
    ):
        assert not matcher.match_file(updated), updated


def listed_files_of_the_project(agents: str) -> list[str]:
    """The patterns that the list of the files of the project in an AGENTS.md names,
    one per code span, from the line that introduces the list to the next heading."""
    start = agents.index("\nThe files of this project, as `_skip_if_exists`")
    end = agents.index("\n## ", start)
    patterns = []
    for line in agents[start:end].splitlines()[1:]:
        if line.startswith("- **"):
            patterns += re.findall(r"`([^`]+)`", line.split(":** ", 1)[1])
    return patterns


# The commands that set up the tools of each kind of project and run its tests,
# which AGENTS.md names for coding agents.
AGENT_COMMANDS = {
    "home-assistant": [
        "pip install --require-hashes -r requirements-test.txt",
        "coverage run -m pytest && coverage report",
        "`pytest -n auto --cov` runs them on every core",
    ],
    "nextcloud-app": ["composer install", "vendor/bin/phpunit"],
    "github-action": [
        "pip install --require-hashes -r requirements-dev.txt",
        "coverage run -m pytest && coverage report",
        "`pytest -n auto --cov` runs them on every core",
    ],
    "python-package": [
        "pip install --require-hashes -r requirements-dev.txt",
        "coverage run -m pytest && coverage report",
        "`pytest -n auto --cov` runs them on every core",
    ],
    "node-package": [
        "npm ci --ignore-scripts",
        "`npm test`",
        "`npx --no -- biome check --write .`",
    ],
    "container": ["docker run --rm demo-project:check --self-test"],
    "generic": ["no build and no tests of its own"],
}


@pytest.mark.parametrize("kind", KINDS)
def test_every_project_tells_coding_agents_its_rules(
    projects: dict[str, Path], kind: str
) -> None:
    project = projects[kind]
    agents = (project / "AGENTS.md").read_text(encoding="utf-8")
    # The commands of the kind of project, and the rules of every pull request.
    for command in (*AGENT_COMMANDS[kind], "bash scripts/check.sh"):
        assert command in agents, command
    for rule in (
        "`git commit -s`",
        # The entry of the changelog is a fragment, which conflicts with no other
        # pull request, and a diagram a picture of its source, never a mermaid block.
        "a new file `changelog.d/<branch>.md`",
        "`python3 .github/blueprint.py fragments`",
        "`docs/diagrams/<name>.mmd`",
        "`bash scripts/diagrams.sh`",
        "Never write a `mermaid` block",
        "Conventional Commit",
        "`fix` and `perf` a patch, `feat` a minor",
        "`Fixes #123`",
        "`--no-verify`",
        "`scripts/check-project.sh`",
        "`.github/repository.project.toml`",
        "`python3 .github/blueprint.py fix run`",
    ):
        assert rule in agents, rule
    # A test's own repository leaves the one that runs the tests alone; a generic
    # project has no tests.
    contributing = (project / "CONTRIBUTING.md").read_text(encoding="utf-8")
    clear = "`unset $(git rev-parse --local-env-vars)`"
    assert (clear in agents, clear in contributing) == (kind != "generic",) * 2
    # The files of the project are exactly those that an update never overwrites,
    # so that the list for coding agents can't drift from copier.yml.
    listed = listed_files_of_the_project(agents)
    assert sorted(listed) == sorted(files_of_the_project())
    assert len(listed) == len(set(listed))
    # It ends with the notes of the project, which belong to the project.
    assert agents.endswith(
        "## Project notes\n\nSee [.github/agents.project.md](.github/agents.project.md).\n"
    )
    notes = (project / ".github/agents.project.md").read_text(encoding="utf-8")
    assert "Demo Project: A " in notes
    assert "## Where things are" in notes
    # Every link of AGENTS.md to a file of the repository leads to one.
    for link in re.findall(r"\]\(([^)#]+)(?:#[^)]*)?\)", agents):
        if not link.startswith("https://"):
            assert (project / link).is_file(), link
    # Claude Code reads AGENTS.md and the notes through the imports of CLAUDE.md,
    # each on a line of its own; Codex and GitHub Copilot read AGENTS.md directly.
    claude = (project / "CLAUDE.md").read_text(encoding="utf-8").splitlines()
    assert "@AGENTS.md" in claude
    assert "@.github/agents.project.md" in claude


def test_the_blueprint_tells_coding_agents_its_rules() -> None:
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for rule in (
        "bash scripts/check.sh",
        "`pytest -n auto --cov`",
        "`git commit -s`",
        "a new file `changelog.d/<branch>.md`",
        "`python3 blueprint.py fragments`",
        "`docs/diagrams/<name>.mmd`",
        "`bash scripts/diagrams.sh`",
        "Never write a `mermaid` block",
        "`Fixes #123`",
        "`README.md` and `README.de.md` together",
        "`tests/test_template.py`",
        "`_skip_if_exists`",
        "`template/AGENTS.md.jinja`",
        "`git_environment` of `tests/shared.py`",
    ):
        assert rule in agents, rule
    assert agents.endswith(
        "## Project notes\n\nSee [.github/agents.project.md](.github/agents.project.md).\n"
    )
    for link in re.findall(r"\]\(([^)#]+)(?:#[^)]*)?\)", agents):
        if not link.startswith("https://"):
            assert (ROOT / link).is_file(), link
    notes = (ROOT / ".github/agents.project.md").read_text(encoding="utf-8")
    assert "`docs/diagrams/<name>.mmd`" in notes
    assert "never a `mermaid` block" in notes
    # Its CLAUDE.md is the one of every repository, which test_the_blueprint_
    # follows_its_own_template keeps equal.
    claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8").splitlines()
    assert "@AGENTS.md" in claude
    assert "@.github/agents.project.md" in claude


def test_copying_runs_no_code_of_the_blueprint() -> None:
    # Without tasks, migrations or Jinja extensions, Copier only renders the template
    # in its sandbox and needs no --trust; docs/security.md promises it.
    config = (ROOT / "copier.yml").read_text(encoding="utf-8")
    for key in ("_tasks", "_migrations", "_jinja_extensions"):
        assert not re.search(rf"^{key}:", config, re.MULTILINE), key


@pytest.mark.parametrize("kind", KINDS)
def test_every_project_documents_its_security_and_its_roles(
    projects: dict[str, Path], kind: str
) -> None:
    def lines(name: str) -> list[str]:
        return (projects[kind] / name).read_text(encoding="utf-8").splitlines()

    security = lines("SECURITY.md")
    for heading in (
        "## Verify a release",
        "## Assurance case",
        "### Threat model",
        "### Trust boundaries",
        "### Secure design principles",
        "### Common weaknesses",
    ):
        assert heading in security, heading
    assert "gh release verify vX.Y.Z --repo Dennis-Otto/demo-project" in security
    # The assurance case leads to the security design of the software, which the
    # project keeps after the first copy.
    assert "(docs/security.md)" in "\n".join(security)
    design = lines("docs/security.md")
    for heading in (
        "## What you can expect",
        "## Trust boundaries",
        "## Threats and countermeasures",
        "## Residual risks",
    ):
        # Every section has its content for the kind of project.
        index = design.index(heading)
        assert design[index + 1] == "", heading
        assert design[index + 2].startswith(("- ", "1. ", "| ")), heading
    governance = lines("GOVERNANCE.md")
    assert "## Roles and responsibilities" in governance
    assert "the bus factor of the project is 1" in "\n".join(governance)
    assert "A successor is planned" in "\n".join(governance)
    contributing = lines("CONTRIBUTING.md")
    assert contributing[contributing.index("## Coding standards") + 2].startswith(
        "- **"
    )
    # A project with code requires tests for every new function and every fix.
    assert ("## Tests" in contributing) == (kind != "generic")


def test_a_release_names_the_files_to_verify(projects: dict[str, Path]) -> None:
    def security(kind: str) -> str:
        return (projects[kind] / "SECURITY.md").read_text(encoding="utf-8")

    assert "gh attestation verify demo_project.zip" in security("home-assistant")
    nextcloud = security("nextcloud-app")
    assert "gh attestation verify demo_project.tar.gz" in nextcloud
    assert "app-certificate-requests/master/demo_project/demo_project.crt" in nextcloud
    assert "gh attestation verify ./*.whl" in security("python-package")
    assert "npm audit signatures" in security("node-package")
    assert "oci://ghcr.io/dennis-otto/demo-project:X.Y.Z" in security("container")
    # Each attestation only of the workflow that builds the release: the isolated
    # build of build-release.yml, and the release workflow for the image that it
    # pushes, so that one of another workflow of the repository fails.
    for kind in KINDS:
        verify = [
            line
            for line in security(kind).splitlines()
            # Not that of the website, which the Docs workflow signs.
            if line.startswith("gh attestation verify ") and "artifact.tar" not in line
        ]
        assert len(verify) == (0 if kind in ("generic", "github-action") else 1), kind
        workflow = "release.yml" if kind == "container" else "build-release.yml"
        for line in verify:
            assert line.endswith(
                " --repo Dennis-Otto/demo-project --signer-workflow"
                f" Dennis-Otto/demo-project/.github/workflows/{workflow}"
            ), line


@pytest.mark.parametrize("kind", KINDS)
def test_a_release_tells_how_to_scan_what_it_ships(
    projects: dict[str, Path], kind: str
) -> None:
    security = (projects[kind] / "SECURITY.md").read_text(encoding="utf-8")
    verify = security[
        security.index("## Verify a release") : security.index("## Assurance case")
    ]
    # The SBOMs and the OpenVEX document under the names that build-release.yml gives
    # them, and the root of the SBOMs by the name of the repository.
    assert (
        "gh release download vX.Y.Z --repo Dennis-Otto/demo-project"
        " --pattern 'demo-project.*.json'\n"
        "grype sbom:demo-project.spdx.json --vex demo-project.openvex.json\n"
    ) in verify
    assert "under the name `demo-project` and the version of the release" in verify
    package = kind in (
        "home-assistant",
        "nextcloud-app",
        "python-package",
        "node-package",
    )
    assert ("the package that you install" in verify) == package
    assert ("the files of its tag, without those that only" in verify) != package
    assert ("The image carries an SBOM" in verify) == (kind == "container")


@pytest.mark.parametrize("kind", KINDS)
def test_an_existing_repository_takes_no_sample_code(tmp_path: Path, kind: str) -> None:
    # An update would bring the samples back that an adopted repository deleted.
    project = render(
        tmp_path,
        project_name="Demo",
        description="A demo.",
        project_type=kind,
        sample_code=False,
    )
    for sample in (
        "fuzz",
        "docs/index.md",
        "src",
        "test",
        "lib",
        "app",
        "Dockerfile",
        "custom_components",
        "action.yml",
        "demo.py",
        "scripts/screenshots.sh",
        ".github/screenshots-paths.txt",
    ):
        assert not (project / sample).exists(), sample
    # No sample test either: a Nextcloud app gets only the files that its psalm.xml
    # and phpunit.xml name, which belong to the blueprint.
    assert sorted(files_of(project / "tests")) == (
        ["bootstrap.php", "stubs/Emitter.php", "stubs/OC.php"]
        if kind == "nextcloud-app"
        else []
    )
    if kind == "nextcloud-app":
        assert_psalm_and_phpunit_find_every_file_they_name(project)
    assert (project / "scripts/check.sh").exists()
    assert (project / ".github/workflows/ci.yml").exists()
    # The website waits for the pages of the project; the check docs passes until then.
    assert (project / "mkdocs.yml").exists()
    assert "sample_code: false" in (project / ".copier-answers.yml").read_text(
        encoding="utf-8"
    )


def assert_psalm_and_phpunit_find_every_file_they_name(project: Path) -> None:
    # psalm.xml and phpunit.xml belong to the blueprint and reach an app adopted
    # without the sample code as well; psalm stops at a stub it can't find, phpunit
    # at a missing bootstrap, before either looks at the code.
    psalm = ElementTree.parse(project / "psalm.xml").getroot()
    stubs = [
        str(stub.get("name")) for stub in psalm.findall("psalm:stubs/psalm:file", PSALM)
    ]
    bootstrap = str(
        ElementTree.parse(project / "phpunit.xml").getroot().get("bootstrap")
    )
    # The files that the bootstrap loads before the autoloader of Composer.
    loaded = [
        f"tests/{name}"
        for name in re.findall(
            r"^require_once __DIR__ \. '/([^']+)';$",
            (project / bootstrap).read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        if not name.startswith("../vendor/")
    ]
    assert stubs == ["tests/stubs/Emitter.php"]
    assert loaded == ["tests/stubs/Emitter.php", "tests/stubs/OC.php"]
    for name in (*stubs, bootstrap, *loaded):
        assert (project / name).is_file(), name


def test_psalm_and_phpunit_find_every_file_they_name(projects: dict[str, Path]) -> None:
    # With the sample code; test_an_existing_repository_takes_no_sample_code checks
    # the app adopted without it.
    assert_psalm_and_phpunit_find_every_file_they_name(projects["nextcloud-app"])


def test_adopting_a_nextcloud_app_keeps_its_own_tests(tmp_path: Path) -> None:
    # An app adopted before the blueprint brought its bootstrap carries its own;
    # /tests in _skip_if_exists keeps every file of it, and only what is missing
    # comes from the blueprint, on the copy as on every update.
    own = {
        "tests/bootstrap.php": "<?php\n\nrequire_once __DIR__ . '/stubs/Emitter.php';\n",
        "tests/stubs/Emitter.php": "<?php\n\nnamespace OC\\Hooks;\n\ninterface Emitter {\n}\n",
        "tests/Unit/ServiceTest.php": "<?php\n\nfinal class ServiceTest {\n}\n",
    }
    for name, text in own.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text, encoding="utf-8", newline="\n")
    render(
        tmp_path,
        overwrite=True,
        project_name="Demo",
        description="A demo.",
        project_type="nextcloud-app",
        sample_code=False,
    )

    for name, text in own.items():
        assert (tmp_path / name).read_text(encoding="utf-8") == text, name
    assert (tmp_path / "tests/stubs/OC.php").is_file()
    assert sorted(files_of(tmp_path / "tests")) == [
        "Unit/ServiceTest.php",
        "bootstrap.php",
        "stubs/Emitter.php",
        "stubs/OC.php",
    ]


def test_the_area_labels_of_pull_requests_exist() -> None:
    labels = tomllib.loads((ROOT / ".github/labels.toml").read_text(encoding="utf-8"))
    defined = {label["name"] for label in labels["label"]}
    rules = (ROOT / ".github/labeler.yml").read_text(encoding="utf-8")
    used = set(re.findall(r'^"([^"]+)":$', rules, re.MULTILINE))
    assert used
    assert used <= defined, used - defined


@pytest.mark.parametrize("kind", KINDS)
def test_every_project_starts_with_area_rules(
    projects: dict[str, Path], kind: str
) -> None:
    rules = (projects[kind] / ".github/labeler.yml").read_text(encoding="utf-8")
    # No areas yet: an empty mapping, which the labeler accepts.
    assert rules.rstrip().endswith("{}")


def test_the_website_of_the_owner_lives_at_the_root(tmp_path: Path) -> None:
    project = render(
        tmp_path,
        project_name="Dennis Otto",
        project_slug="dennis-otto.github.io",
        description="The projects of the owner.",
        project_type="generic",
    )
    config = (project / "mkdocs.yml").read_text(encoding="utf-8")

    assert "\nsite_url: https://dennis-otto.github.io/\n" in config
    assert (
        "\nrepo_url: https://github.com/Dennis-Otto/dennis-otto.github.io\n" in config
    )
    # Its footer leads to no website of itself.
    assert footer_of(project) == [
        "https://github.com/Dennis-Otto",
        "https://github.com/sponsors/Dennis-Otto",
    ]


def footer_of(project: Path) -> list[str]:
    """The addresses of the links in the footer that the hooks of the website of
    project give every page, with the addresses of its mkdocs.yml."""
    spec = importlib.util.spec_from_file_location(
        f"hooks_of_{re.sub(r'\W', '_', project.name)}",
        project / ".github/mkdocs_blueprint.py",
    )
    assert spec is not None
    assert spec.loader is not None
    hooks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hooks)
    text = (project / "mkdocs.yml").read_text(encoding="utf-8")
    addresses = dict(re.findall(r"^(site_url|repo_url): (\S+)$", text, re.M))
    config = SimpleNamespace(
        config_file_path=str(project / "mkdocs.yml"),
        docs_dir=str(project / "docs"),
        site_url=addresses["site_url"],
        repo_url=addresses["repo_url"],
        edit_uri=None,
        theme={"language": "en"},
        plugins={},
        extra={},
        extra_css=[],
        extra_javascript=[],
        nav=None,
    )
    hooks.on_config(config)
    return [link["link"] for link in config.extra.get("social", [])]


@pytest.mark.parametrize("kind", KINDS)
def test_the_issue_assistant_shows_its_limits_of_the_ai_runs(
    projects: dict[str, Path], kind: str
) -> None:
    # The defaults of the issue assistant since 1.3.0, which config.toml shows, so a
    # maintainer finds them; the blueprint's own config has them too.
    for root in (projects[kind], ROOT):
        config = tomllib.loads(
            (root / ".github/issue-assistant/config.toml").read_text(encoding="utf-8")
        )
        assert config["engine"] == {
            "name": "claude",
            "max_per_day": 20,
            "max_per_author_per_day": 3,
            "release_replies": 2,
        }


@pytest.mark.parametrize("kind", KINDS)
def test_actionlint_ignores_only_the_queue_of_the_issue_assistant(
    projects: dict[str, Path], kind: str
) -> None:
    config = (projects[kind] / ".github/actionlint.yaml").read_text(encoding="utf-8")
    assert config == (ROOT / ".github/actionlint.yaml").read_text(encoding="utf-8")
    # actionlint 1.7.12 doesn't know the queue of a concurrency group, which the issue
    # assistant uses since 1.3.0: only that message, and only in its workflow.
    paths = config[config.index("\npaths:\n") + 1 :]
    assert paths.startswith(
        "paths:\n  .github/workflows/issue-assistant.yml:\n    ignore:\n"
    )
    ignored = [
        line.strip() for line in paths.splitlines() if line.strip().startswith("- ")
    ]
    assert ignored == ['- \'unexpected key "queue" for "concurrency" section\'']


def test_the_issue_forms_point_to_the_documentation(tmp_path: Path) -> None:
    project = render(
        tmp_path,
        project_name="Demo Project",
        description="A project with a website.",
        project_type="generic",
        homepage="https://dennis-otto.github.io/demo-project/",
    )
    config = (project / ".github/ISSUE_TEMPLATE/config.yml").read_text(encoding="utf-8")

    assert config.index("name: Documentation") < config.index(
        "name: Security vulnerability"
    )
    assert "url: https://dennis-otto.github.io/demo-project/" in config


def test_a_designated_successor_continues_the_project(tmp_path: Path) -> None:
    project = render(
        tmp_path,
        project_name="Demo Project",
        description="An app with a successor.",
        project_type="nextcloud-app",
        successor=True,
    )
    governance = (project / "GOVERNANCE.md").read_text(encoding="utf-8")

    assert "GitHub's account successor setting" in governance
    assert "the bus factor of the project is 2" in governance
    assert "don't pass with the repository" in governance
    assert "A successor is planned" not in governance
    assert "bus factor of the project is 1" not in governance


# The criteria of OpenSSF Best Practices, of its levels passing, silver and gold and
# of the OSPS Baseline, as bestpractices.dev knows them; the file names their source.
BEST_PRACTICES: dict[str, dict[str, Any]] = json.loads(
    (ROOT / "tests/data/bestpractices-criteria.json").read_text(encoding="utf-8")
)["criteria"]
# What only a project knows, of its software or of its people, and no file of the
# blueprint can promise: .bestpractices.json leaves it out, so that bestpractices.dev
# keeps the answers that a maintainer gives there. So do the criteria of crypto_.
PROJECT_SPECIFIC = {
    "description_good",
    "interact",
    "documentation_basics",
    "documentation_interface",
    "maintained",
    "report_responses",
    "enhancement_responses",
    "release_notes_vulns",
    "vulnerability_report_response",
    "build",
    "know_secure_design",
    "know_common_errors",
    "test_most",
    "tests_are_added",
    "warnings_strict",
    "vulnerabilities_fixed_60_days",
    "vulnerabilities_critical_fixed",
    "dynamic_analysis_unsafe",
    "dynamic_analysis_enable_assertions",
    "documentation_roadmap",
    "documentation_architecture",
    "documentation_security",
    "documentation_quick_start",
    "documentation_achievements",
    "internationalization",
    "regression_tests_added50",
    "test_statement_coverage80",
    "implement_secure_design",
    "input_validation",
    "hardening",
    "assurance_case",
    # Multi-factor authentication, the user guides, the design, the interfaces, the
    # security assessment and a second person's review.
    "osps_ac_01_01",
    "osps_do_01_01",
    "osps_sa_01_01",
    "osps_sa_02_01",
    "osps_sa_03_01",
    "osps_qa_07_01",
    # The check of the website only reports for now, and the user interface of an app
    # or of the cards of an integration is the project's own.
    "accessibility_best_practices",
}
# Every answer of a repository: none of them can do without these.
GUARANTEED = {
    "contribution",
    "license_location",
    "vulnerability_report_private",
    "static_analysis",
    "dco",
    "governance",
    "signed_releases",
    "version_tags_signed",
    "osps_ac_03_01",
    "osps_ac_03_02",
    "osps_ac_04_02",
    "osps_br_01_03",
    "osps_br_07_01",
    "osps_gv_01_01",
    "osps_le_01_01",
    "osps_le_03_01",
    "osps_qa_03_01",
    "osps_vm_02_01",
    "osps_vm_04_02",
    "osps_vm_06_02",
}


def best_practices(project: Path) -> dict[str, str]:
    """The answers of .bestpractices.json, which may name each field only once."""

    def once_each(pairs: list[tuple[str, str]]) -> dict[str, str]:
        names = [name for name, _ in pairs]
        assert len(names) == len(set(names)), names
        return dict(pairs)

    answers: dict[str, str] = json.loads(
        (project / ".bestpractices.json").read_text(encoding="utf-8"),
        object_pairs_hook=once_each,
    )
    return answers


def anchors(markdown: str) -> set[str]:
    """The anchors of the headings of a Markdown file, as GitHub makes them."""
    return {
        re.sub(r"[^\w\- ]", "", title.strip().lower()).replace(" ", "-")
        for title in re.findall(r"^#{1,6} (.+)$", markdown, re.MULTILINE)
    }


def proposed_criteria(project: Path, repository: str) -> set[str]:
    """The criteria that the .bestpractices.json of a project answers, once each of
    them is an answer that bestpractices.dev takes and every file that it names, with
    its heading, is there."""
    answers = best_practices(project)
    criteria = {name.rsplit("_", 1)[0] for name in answers}
    assert set(answers) == {
        f"{criterion}_{field}"
        for criterion in criteria
        for field in ("status", "justification")
    }
    assert criteria <= set(BEST_PRACTICES), criteria - set(BEST_PRACTICES)
    assert not criteria & PROJECT_SPECIFIC
    assert not [criterion for criterion in criteria if criterion.startswith("crypto_")]
    files = f"https://github.com/{repository}/blob/main/"
    for criterion in criteria:
        justification = answers[f"{criterion}_justification"]
        assert answers[f"{criterion}_status"] == "Met", criterion
        links = re.findall(r"https://\S+", justification)
        if BEST_PRACTICES[criterion]["met_url_required"]:
            assert links, criterion
        for link in links:
            assert link.startswith(f"https://github.com/{repository}"), (
                criterion,
                link,
            )
            if not link.startswith(files):
                continue
            path, _, anchor = link.removeprefix(files).partition("#")
            assert (project / path).is_file(), (criterion, path)
            if anchor:
                markdown = (project / path).read_text(encoding="utf-8")
                assert anchor in anchors(markdown), (criterion, link)
    return criteria


@pytest.mark.parametrize("kind", KINDS)
def test_every_repository_proposes_its_answers_of_openssf_best_practices(
    projects: dict[str, Path], kind: str
) -> None:
    project = projects[kind]
    criteria = proposed_criteria(project, "Dennis-Otto/demo-project")

    assert criteria >= GUARANTEED
    # The test suite of scripts/check.sh, and the manifests of the dependencies.
    tested = kind not in ("generic", "container")
    for criterion in ("test", "automated_integration_testing", "osps_qa_06_01"):
        assert (criterion in criteria) == tested, criterion
    for criterion in ("external_dependencies", "osps_qa_02_01"):
        assert (criterion in criteria) == tested, criterion
    assert ("dynamic_analysis" in criteria) == (
        kind in ("python-package", "github-action")
    )
    # The sites are on GitHub, and only a designated successor continues a project.
    assert {"sites_https", "osps_br_03_01"} <= criteria
    assert not {"access_continuity", "bus_factor"} & criteria
    answers = best_practices(project)
    assert "GitHub Discussions" in answers["discussion_justification"]
    # What osps_ac_04_01 says: every workflow starts with read-only permissions or none.
    for name, workflow in workflows(project).items():
        top = re.search(r"^permissions:(.*(?:\n  .*)*)", workflow, re.MULTILINE)
        assert top, name
        assert re.fullmatch(r" (?:\{\}|read-all)|(?:\n  [\w-]+: read)+", top[1]), name


def test_the_answers_of_openssf_best_practices_follow_those_of_copier(
    tmp_path: Path,
) -> None:
    project = render(
        tmp_path,
        project_name="Demo Project",
        description="A demo.",
        project_type="python-package",
        sample_code=False,
        successor=True,
        discussions=False,
        homepage="http://demo.example",
    )
    criteria = proposed_criteria(project, "Dennis-Otto/demo-project")
    answers = best_practices(project)

    # The project on PyPI doesn't pass with the repository to the successor.
    assert "bus_factor" in criteria
    assert "access_continuity" not in criteria
    # Without the fuzz targets of the samples, nothing says that fuzzing finds anything.
    assert "dynamic_analysis" not in criteria
    # A site of its own, which the blueprint can't vouch for.
    assert not {"sites_https", "sites_password_security", "osps_br_03_01"} & criteria
    assert "Discussions" not in answers["discussion_justification"]
    assert "discussions" not in answers["osps_gv_02_01_justification"]
    assert "from PyPI" in answers["delivery_mitm_justification"]


def test_a_successor_alone_cannot_release_in_a_store(tmp_path: Path) -> None:
    # GOVERNANCE.md says that the entry of the App Store doesn't pass with the
    # repository, so the successor can't release there within a week on their own.
    project = render(
        tmp_path,
        project_name="Demo Project",
        description="A demo.",
        project_type="nextcloud-app",
        successor=True,
    )
    criteria = proposed_criteria(project, "Dennis-Otto/demo-project")

    assert "bus_factor" in criteria
    assert "access_continuity" not in criteria
    answers = best_practices(project)
    assert (
        "Psalm's taint analysis"
        in answers["static_analysis_common_vulnerabilities_justification"]
    )


@pytest.mark.parametrize(
    "answers",
    sorted((ROOT / "tests/answers").glob("*.yml")),
    ids=lambda path: path.stem,
)
def test_the_downstream_repositories_propose_their_answers(
    tmp_path: Path, answers: Path
) -> None:
    # The answers of the real repositories, which the Rollout brings the file to:
    # every file and heading that their .bestpractices.json names is there.
    data = yaml.safe_load(answers.read_text(encoding="utf-8"))
    project = render(tmp_path, **data)
    criteria = proposed_criteria(project, f"{data['owner']}/{data['project_slug']}")

    assert criteria >= GUARANTEED


def test_the_blueprint_proposes_its_own_answers_of_openssf_best_practices() -> None:
    # Its own .bestpractices.json is that of the GitHub Action it is rendered as, which
    # test_the_blueprint_follows_its_own_template keeps equal; its files are its own.
    criteria = proposed_criteria(ROOT, "Dennis-Otto/repo-blueprint")

    assert criteria >= GUARANTEED | {"sites_https", "access_continuity", "test"}


@pytest.mark.parametrize("kind", KINDS)
def test_releases_are_announced_in_the_discussions(
    projects: dict[str, Path], kind: str
) -> None:
    project = projects[kind]
    for form in ("q-a.yml", "ideas.yml"):
        assert (project / ".github/DISCUSSION_TEMPLATE" / form).is_file(), form
    release = workflows(project)["release.yml"]
    publish = release[release.index("  publish:") :]
    publish = publish[: publish.index("\n  pypi:")]
    assert "discussions: write" in publish
    # Only a release for everybody, not a prerelease, is announced.
    assert publish.index("exit 0") < publish.index("--discussion-category")
    assert "has_discussions = true" in (project / ".github/repository.toml").read_text(
        encoding="utf-8"
    )


def test_a_project_without_discussions(tmp_path: Path) -> None:
    project = render(
        tmp_path,
        project_name="Demo",
        description="A demo.",
        project_type="generic",
        discussions=False,
    )

    assert not (project / ".github/DISCUSSION_TEMPLATE").exists()
    assert "discussions" not in (project / "SUPPORT.md").read_text(encoding="utf-8")
    assert "has_discussions = false" in (project / ".github/repository.toml").read_text(
        encoding="utf-8"
    )


def test_a_nextcloud_app_covers_every_line(projects: dict[str, Path]) -> None:
    project = projects["nextcloud-app"]
    check = (project / "scripts/check.sh").read_text(encoding="utf-8")
    assert "--coverage-cobertura build/coverage.xml" in check
    assert '["line-rate"]' in check
    assert "<directory>lib</directory>" in (project / "phpunit.xml").read_text(
        encoding="utf-8"
    )
    ci = (ROOT / ".github/workflows/ci-php.yml").read_text(encoding="utf-8")
    assert "coverage: pcov" in ci


@pytest.mark.parametrize("kind", KINDS)
def test_renovate_keeps_every_project_current(
    projects: dict[str, Path], kind: str
) -> None:
    project = projects[kind]
    entry = (project / ".github/renovate.json5").read_text(encoding="utf-8")
    # The project's file extends the blueprint's, so that its own rules come last.
    assert '"local>Dennis-Otto/demo-project//.github/renovate-blueprint.json5"' in entry
    rules = (project / ".github/renovate-blueprint.json5").read_text(encoding="utf-8")
    for setting in (
        'minimumReleaseAge: "7 days"',
        "platformAutomerge: true",
        "minimumReleaseAge: null",
        "copier: { enabled: false }",
        "devcontainer: { enabled: false }",
        '"pre-commit": { enabled: true }',
    ):
        assert setting in rules, setting
    python = kind in ("home-assistant", "github-action", "python-package")
    # Ruff and its pre-commit hook run the same version.
    assert ('matchDepNames: ["ruff", "astral-sh/ruff-pre-commit"]' in rules) == python
    assert ('matchManagers: ["pip-compile", "pep621", "pre-commit"]' in rules) == python
    # The test plugin of Home Assistant, now and then on a beta, moves on its own.
    test_base = 'groupName: "the Home Assistant test base"'
    assert (test_base in rules) == (kind == "home-assistant")
    # The Nextcloud apps get only the releases that run on their oldest PHP.
    assert ('constraintsFiltering: "strict"' in rules) == (kind == "nextcloud-app")
    review = (project / ".github/dependency-review.yml").read_text(encoding="utf-8")
    assert ("- pkg:pypi/regex\n" in review) == (kind == "home-assistant")
    # The images of the scripts, also in a variable with quotes.
    pattern = re.search(r'^\s*"(\(\?:\^\|.*sha256.*)",$', rules, re.MULTILINE)
    assert pattern
    images = re.compile(json.loads(f'"{pattern[1]}"').replace("(?<", "(?P<"))
    digest = "sha256:" + "0" * 64
    for line in (
        f"  image: ghcr.io/owner/tool:v1.2.3@{digest}",
        f'IMAGE="mcr.microsoft.com/playwright:v1.63.0-noble@{digest}"',
        f"IMAGE=docker.io/library/python:3.14@{digest}",
    ):
        found = images.search(line)
        assert found, line
        assert found["currentDigest"] == digest
    # Dependabot keeps only the Features of the dev container and their lock file.
    dependabot = (project / ".github/dependabot.yml").read_text(encoding="utf-8")
    assert re.findall(r"package-ecosystem: (\S+)", dependabot) == ["devcontainers"]
    settings = (project / ".github/repository.toml").read_text(encoding="utf-8")
    assert "dependabot_security_updates = false" in settings


def scheduled_runs_a_week(root: Path) -> dict[str, int]:
    """The runs that the schedules of each workflow of a repository start in a week."""
    week = [
        datetime.date(2026, 10, 12) + datetime.timedelta(days=day) for day in range(7)
    ]
    runs: dict[str, int] = {}
    for name, text in workflows(root).items():
        for line in CRON.findall(text):
            cron = Cron.parse(line)
            assert cron, (name, line)
            times = len(cron.hours) * len(cron.minutes)
            runs[name] = runs.get(name, 0) + times * sum(map(cron.runs_on, week))
    return runs


@pytest.mark.parametrize("kind", KINDS)
def test_the_schedules_of_a_project_start_a_dozen_runs_a_day_at_most(
    projects: dict[str, Path], kind: str
) -> None:
    # Every bot starts from an event, and a schedule is only a safety net, which
    # GitHub runs hours late and often not at all. In a private repository each run is
    # a minute at least of the 2,000 a month of GitHub Free; the hourly release bot and
    # the half-hourly branch bot alone came to 72 runs a day.
    runs = scheduled_runs_a_week(projects[kind])
    assert sum(runs.values()) <= 12 * 7, runs
    assert runs["release.yml"] == 7
    assert runs["update-branches.yml"] == 4 * 7


@pytest.mark.parametrize("project", ["blueprint", *KINDS])
def test_no_schedule_starts_on_the_full_hour_or_promises_its_time(
    projects: dict[str, Path], project: str
) -> None:
    # GitHub has the most schedules to start on the full hour, and drops runs then.
    # It runs every schedule as it can, often hours late, so no comment promises one.
    root = ROOT if project == "blueprint" else projects[project]
    promise = re.compile(
        r"\b(?:hourly|half-hourly|every (?:hour|half hour|two hours|morning|\d+ minutes))\b",
        re.IGNORECASE,
    )
    for name, text in workflows(root).items():
        for line in CRON.findall(text):
            cron = Cron.parse(line)
            assert cron, (name, line)
            assert 0 not in cron.minutes, (name, line)
        if name in ISSUE_ASSISTANT_WORKFLOWS:
            # Templates of the issue assistant, whose comments only it can reword: the
            # "runs every hour" of issue-lifecycle.yml is a follow-up there.
            continue
        # A promise may wrap onto the next line of a comment, so whole blocks count.
        for block in re.findall(r"(?:^[ \t]*#.*\n?)+", text, re.MULTILINE):
            comment = re.sub(r"\s*\n[ \t]*#\s*", " ", block)
            assert not promise.search(comment), (name, comment)


@pytest.mark.parametrize("project", ["blueprint", *KINDS])
def test_dependabot_merges_as_the_release_app(
    projects: dict[str, Path], project: str
) -> None:
    # A merge that auto-merge does with the token of a workflow starts no workflow, so
    # the release bot and the branch bot waited for their schedules; the merge of the
    # release app starts them at once, as Renovate's does.
    root = ROOT if project == "blueprint" else projects[project]
    text = (root / ".github/workflows/dependabot-automerge.yml").read_text(
        encoding="utf-8"
    )
    # pull_request_target runs on main, the only branch that may use the environment
    # with the private key of the app, and the job checks out nothing.
    assert set(triggers(text)) == {"pull_request_target"}
    job = job_of(text, "auto-merge")
    assert "    environment:\n      name: release\n      deployment: false\n" in job
    assert "actions/checkout" not in text
    assert text.count("run: ") == 2
    app = job.split("      - name: Create a token of the release app\n", 1)[1]
    app = app.split("\n      - name: ", 1)[0]
    # A token that fails still lets the job's token turn auto-merge on, and says so.
    assert "        continue-on-error: true\n" in app
    parts = job.split("      - name: Explain a token of the release app that failed\n")
    assert len(parts) == 2
    explain = parts[1].split("\n      - name: ", 1)[0]
    assert "        if: steps.app.outcome == 'failure'\n" in explain
    assert "::warning title=Release app token failed::" in explain
    assert '>> "$GITHUB_STEP_SUMMARY"' in explain
    assert "vars.RELEASE_AUTOMATION_CLIENT_ID != ''" in app
    assert "client-id: ${{ vars.RELEASE_AUTOMATION_CLIENT_ID }}" in app
    assert "private-key: ${{ secrets.RELEASE_AUTOMATION_PRIVATE_KEY }}" in app
    assert re.findall(r"permission-([\w-]+): (\w+)", app) == [
        ("contents", "write"),
        ("pull-requests", "write"),
    ]
    merge = job.split("      - name: Enable automatic squash merge", 1)[1]
    # Without the app, the job's own token still turns auto-merge on.
    assert "GH_TOKEN: ${{ steps.app.outputs.token || secrets.GITHUB_TOKEN }}" in merge
    assert (
        'run: gh pr merge --auto --squash --match-head-commit "$PR_HEAD_SHA" "$PR_URL"'
        in merge
    )
    zizmor = (ROOT / ".github/zizmor.yml").read_text(encoding="utf-8")
    dangerous = zizmor.split("  dangerous-triggers:", 1)[1].split("\n  self-", 1)[0]
    assert "      - dependabot-automerge.yml\n" in dangerous


def test_the_release_bot_keeps_its_pull_request_current_with_every_merge() -> None:
    # main takes only a pull request that is up to date with it, so a release pull
    # request that only the schedule rebuilt couldn't merge for hours, and its notes
    # would miss what merged since (decision 0033).
    text = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert triggers(text)["push"] == ["    branches: [main]"]
    assert triggers(text)["schedule"] == ['    - cron: "25 5 * * *"']
    rebuild = text.split("      - name: Have the release pull request rebuilt", 1)[1]
    assert rebuild.split("\n", 2)[1] == "        if: steps.app.outputs.token != ''"
    assert "skip-github-pull-request" not in text


@pytest.mark.parametrize("kind", KINDS)
def test_renovate_follows_an_action_pinned_to_a_branch_at_once(
    projects: dict[str, Path], kind: str
) -> None:
    # A workflow of the project may still pin an action to a commit of a branch, with
    # the branch in its comment. Renovate looks such a pin up as a github-digest, for
    # which every commit to the branch is a new release: with the week of waiting, a
    # branch that moves every few days would never be followed, and zizmor reports
    # the pin all the while.
    rules = (projects[kind] / ".github/renovate-blueprint.json5").read_text(
        encoding="utf-8"
    )
    rule = re.search(
        r'\{\n(?:\s+//.*\n)+\s+matchManagers: \["github-actions"\],\n'
        r'\s+matchDatasources: \["github-digest"\],\n'
        r"\s+minimumReleaseAge: null,\n"
        r'\s+schedule: \["at any time"\],\n'
        r"\s+automerge: true,\n"
        r'\s+groupName: "the actions that follow a branch",\n\s+\},',
        rules,
    )
    assert rule
    # After the groups of the actions, so that its own group and schedule apply.
    for group in ("the actions", "the actions to a new major version"):
        assert rules.index(f'groupName: "{group}"') < rule.start(), group


# It asks Git for the files of the repository, which the copy of the mutation tests
# has none of.
@pytest.mark.mutation_unsafe
def test_renovate_compiles_every_lock_file_for_its_own_python() -> None:
    # Renovate installs pip-tools once per repository and run, for the Python of the
    # first lock file it compiles: the lock files of pip-compile share one Python, and
    # one for another Python is compiled with uv, for a Python with its patch level.
    # So is the one of mutmut, which leaves out the pytest of the project with an
    # option that Renovate allows for uv alone.
    pip_compile = {}
    uv = {}
    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
        env=git_environment(ROOT),
    ).stdout.split("\0")
    for name in tracked:
        if not re.search(r"(^|/)requirements[^/]*\.txt$", name):
            continue
        header = "".join((ROOT / name).read_text(encoding="utf-8").splitlines(True)[:5])
        if found := re.search(
            r"autogenerated by pip-compile with Python (\S+)", header
        ):
            pip_compile[name] = found[1]
            # pip-tools 7.6.1 recorded it by mistake, and Renovate refuses it.
            assert "--no-index" not in header, name
        else:
            command = re.search(
                r"^#    uv pip compile .*--python-version=(\d+\.\d+(?:\.\d+)?) ",
                header,
                re.M,
            )
            assert command, name
            uv[name] = command[1]
    assert len(set(pip_compile.values())) == 1, pip_compile
    assert sorted(uv) == [
        "stacks/home-assistant/requirements-test.txt",
        "stacks/mutation/requirements.txt",
    ]
    copier = (ROOT / "copier.yml").read_text(encoding="utf-8")
    python = re.search(r"stack == 'home-assistant' %\]([\d.]+)\[% else", copier)
    assert python
    assert uv["stacks/home-assistant/requirements-test.txt"].startswith(python[1] + ".")
    # mutmut runs on the Python of each Python project, from the oldest on, which the
    # lock files of pip-compile are for.
    assert uv["stacks/mutation/requirements.txt"] == next(iter(pip_compile.values()))
    # The pinned test plugin makes a Home Assistant that needs a newer Python fail
    # its update, instead of an older Home Assistant being chosen.
    inputs = (ROOT / "stacks/home-assistant/requirements-test.in").read_text(
        encoding="utf-8"
    )
    assert re.search(r"^pytest-homeassistant-custom-component==\S+$", inputs, re.M)


# How Renovate reads the command in the header of a lock file of pip-compile, after
# lib/modules/manager/pip-compile/common.ts and utils.ts of the version that the
# Renovate workflow runs. It compiles the file again with that command, and skips a
# file whose command it can't read in every run, with no more than a warning in its
# log: the file gets no update from then on, not even one that fixes a
# vulnerability. The job "renovate rules" lets Renovate itself read every file.
HEADER = re.compile(r"^(?:#.*?\r?\n)+# {4}(?P<command>\S*)(?P<arguments> .*?)?\r?\n")
PYTHON_OF_PIP_COMPILE = re.compile(
    r"^(?:#.*?\r?\n)*# This file is autogenerated by pip-compile with Python "
    r"\d+(?:\.\d+)*\s",
    re.IGNORECASE,
)
WITH_A_VALUE = {"--output-file", "--extra", "--extra-index-url"}
PIP_WITH_A_VALUE = {"--resolver", "--constraint", *WITH_A_VALUE}
UV_WITH_A_VALUE = {
    *("--constraints", "--constraint", "--python-version", "--no-emit-package"),
    *("--prerelease", "--format", "--resolution", "--fork-strategy"),
    *("--exclude-newer", "--exclude-newer-package", "--group", "--override"),
    *("--overrides", *WITH_A_VALUE),
}
FOR_BOTH = {
    "-v",
    "--generate-hashes",
    "--emit-index-url",
    "--index-url",
    "--all-extras",
}
KNOWN_OPTIONS = {
    "pip-compile": {
        *("--allow-unsafe", "--generate-hashes", "--no-emit-index-url"),
        *("--strip-extras", *FOR_BOTH, *PIP_WITH_A_VALUE),
    },
    "uv": {"--no-strip-extras", "--universal", *FOR_BOTH, *UV_WITH_A_VALUE},
}


def why_renovate_skips(root: Path, name: str) -> list[str]:
    """What keeps Renovate from compiling the lock file root/name again; nothing for a
    file that it reads."""
    content = (root / name).read_text(encoding="utf-8")
    header = HEADER.match(content)
    if not header:
        return ["no command in the header"]
    command = header["command"]
    if command not in KNOWN_OPTIONS:
        return [f"{command}, a command of its own"]
    problems = []
    sources, output = [], ""
    for argument in shlex.split(header["arguments"] or ""):
        if command == "uv" and argument in ("pip", "compile"):
            continue
        if not argument.startswith("-"):
            sources.append(argument)
            continue
        option, _, value = argument.partition("=")
        if argument == "--no-header":
            problems.append("--no-header, which Renovate refuses")
        elif argument in PIP_WITH_A_VALUE | UV_WITH_A_VALUE:
            problems.append(f"{argument} without = before its value")
        elif option not in KNOWN_OPTIONS[command]:
            problems.append(f"{argument}, an option that Renovate doesn't know")
        elif option == "--output-file":
            output = value
    # Renovate finds the folder of the command from the path of the output file.
    if output and Path(output).name != Path(name).name:
        problems.append(f"{output} as the output file")
    if not sources:
        problems.append("no source file")
    for source in sources:
        if not (root / name).parent.joinpath(source).is_file():
            problems.append(f"{source}, a source file that doesn't exist")
    # The Python to compile it for, which Renovate installs.
    if command == "pip-compile" and not PYTHON_OF_PIP_COMPILE.match(content):
        problems.append("no Python in the header")
    return problems


def lock_files_of_pip_compile(names: list[str]) -> list[str]:
    """The files that Renovate's pip-compile finds, by its managerFilePatterns."""
    rules = (ROOT / ".github/renovate-blueprint.json5").read_text(encoding="utf-8")
    pattern = re.search(
        r'"pip-compile": \{ managerFilePatterns: \["/(.+)/"\] \}', rules
    )
    assert pattern
    found = re.compile(json.loads(f'"{pattern[1]}"'))
    return sorted(name for name in names if found.search(name))


@pytest.mark.parametrize(
    ("header", "problems"),
    [
        (
            "# This file was autogenerated by uv via the following command:\n"
            "#    uv pip compile --generate-hashes --python-version 3.14.8"
            " --output-file=requirements.txt requirements.in\n",
            # Without the =, the value reads as one more file to compile.
            [
                "--python-version without = before its value",
                "3.14.8, a source file that doesn't exist",
            ],
        ),
        (
            "#\n# This file is autogenerated by pip-compile with Python 3.12\n"
            "# by the following command:\n#\n"
            "#    pip-compile --generate-hashes --output-file=requirements.txt"
            " --strip-extras --unsafe-package=coverage requirements.in\n",
            ["--unsafe-package=coverage, an option that Renovate doesn't know"],
        ),
        (
            "# This file was autogenerated by uv via the following command:\n"
            "#    uv pip compile --python-platform=linux --no-header"
            " --output-file=requirements-dev.txt\n",
            [
                "--python-platform=linux, an option that Renovate doesn't know",
                "--no-header, which Renovate refuses",
                "requirements-dev.txt as the output file",
                "no source file",
            ],
        ),
        (
            "#\n# This file is autogenerated by pip-compile\n#\n"
            "#    pip-compile --generate-hashes --output-file=requirements.txt"
            " requirements.in elsewhere.in\n",
            [
                "elsewhere.in, a source file that doesn't exist",
                "no Python in the header",
            ],
        ),
        ("# by make:\n#    make requirements.txt\n", ["make, a command of its own"]),
        ("mutmut==3.8.0\n", ["no command in the header"]),
        # What the lock files of the blueprint have.
        (
            "#\n# This file is autogenerated by pip-compile with Python 3.12\n"
            "# by the following command:\n#\n"
            "#    pip-compile --allow-unsafe --generate-hashes"
            " --output-file=requirements.txt --strip-extras requirements.in\n",
            [],
        ),
        (
            "# This file was autogenerated by uv via the following command:\n"
            "#    uv pip compile --generate-hashes --universal --python-version=3.12"
            " --no-emit-package=pytest --output-file=requirements.txt"
            " requirements.in\n",
            [],
        ),
    ],
)
def test_the_guard_of_the_lock_files_finds_what_renovate_skips(
    tmp_path: Path, header: str, problems: list[str]
) -> None:
    (tmp_path / "requirements.in").write_text("mutmut\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text(
        f"{header}mutmut==3.8.0\n", encoding="utf-8"
    )

    assert why_renovate_skips(tmp_path, "requirements.txt") == problems


# It asks Git for the files of the repository, which the copy of the mutation tests
# has none of.
@pytest.mark.mutation_unsafe
def test_renovate_reads_every_lock_file_of_the_blueprint() -> None:
    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
        env=git_environment(ROOT),
    ).stdout.split("\0")
    names = lock_files_of_pip_compile(tracked)

    assert {name: why_renovate_skips(ROOT, name) for name in names} == {
        name: [] for name in names
    }
    # The tools of the blueprint's tests and of every kind of project.
    assert len(names) == 1 + len(list((ROOT / "stacks").glob("*/requirements*.txt")))


@pytest.mark.parametrize("kind", KINDS)
def test_renovate_reads_every_lock_file_of_a_project(
    projects: dict[str, Path], kind: str
) -> None:
    project = projects[kind]
    names = lock_files_of_pip_compile(
        [path.relative_to(project).as_posix() for path in project.rglob("*.txt")]
    )

    assert {name: why_renovate_skips(project, name) for name in names} == {
        name: [] for name in names
    }
    expected = {
        "home-assistant": ["requirements-test.txt"],
        "python-package": ["requirements-dev.txt", "requirements-fuzz.txt"],
        "github-action": ["requirements-dev.txt", "requirements-fuzz.txt"],
    }
    assert names == expected.get(kind, [])


def renovate_rules(text: str) -> dict[str, Any]:
    """The rules of a .json5 file of Renovate: JSON with comments, names without
    quotes and commas before a closing bracket."""
    out, position = [], 0
    token = re.compile(
        r'(?P<string>"(?:[^"\\]|\\.)*")|(?P<comment>//[^\n]*)'
        r"|(?P<name>[A-Za-z_$][\w$]*)(?=\s*:)|(?P<comma>,(?=\s*[}\]]))"
    )
    for found in token.finditer(text):
        out.append(text[position : found.start()])
        if found["string"]:
            out.append(found["string"])
        elif found["name"]:
            out.append(json.dumps(found["name"]))
        position = found.end()
    out.append(text[position:])
    rules = json.loads("".join(out))
    assert isinstance(rules, dict)
    return rules


@pytest.mark.parametrize("kind", [*KINDS, "blueprint"])
def test_the_weekly_refresh_of_the_lock_files_waits_for_the_maintainer(
    projects: dict[str, Path], kind: str
) -> None:
    root = ROOT if kind == "blueprint" else projects[kind]
    shared = renovate_rules(
        (root / ".github/renovate-blueprint.json5").read_text(encoding="utf-8")
    )
    own = renovate_rules((root / ".github/renovate.json5").read_text(encoding="utf-8"))
    # Every package manager refreshes its lock files once a week, in the same window
    # as the other updates.
    assert shared["lockFileMaintenance"] == {
        "enabled": True,
        "schedule": shared["schedule"],
    }
    # The refresh brings the newest version of every indirect dependency, also one of
    # minutes ago, without the week of waiting: so it never merges on its own. A rule
    # that could apply to it decides, the last one with a say.
    automerge = shared.get("automerge", False)
    rules = [*shared["packageRules"], *own.get("packageRules", [])]
    refresh = [
        rule
        for rule in rules
        if rule.get("matchUpdateTypes") == ["lockFileMaintenance"]
    ]
    # Renovate builds it anew only in its window: a change of main after the review
    # doesn't bring versions that the maintainer hasn't seen.
    assert refresh == [
        {
            "matchUpdateTypes": ["lockFileMaintenance"],
            "minimumReleaseAge": None,
            "automerge": False,
            "updateNotScheduled": False,
        }
    ]
    for rule in rules:
        # A refresh has no dependency, datasource or version of its own to match.
        about_a_dependency = any(
            key.startswith("match")
            and key not in ("matchUpdateTypes", "matchManagers", "matchFileNames")
            for key in rule
        )
        types = rule.get("matchUpdateTypes", ["lockFileMaintenance"])
        if "lockFileMaintenance" in types and not about_a_dependency:
            automerge = rule.get("automerge", automerge)
    assert automerge is False


@pytest.mark.parametrize("kind", [*KINDS, "blueprint"])
def test_renovate_keeps_a_dependency_dashboard_and_the_whole_monday(
    projects: dict[str, Path], kind: str
) -> None:
    root = ROOT if kind == "blueprint" else projects[kind]
    shared = renovate_rules(
        (root / ".github/renovate-blueprint.json5").read_text(encoding="utf-8")
    )
    own = renovate_rules((root / ".github/renovate.json5").read_text(encoding="utf-8"))
    # One issue lists the updates that wait, for their week, their window or the
    # maintainer, and those that failed, with checkboxes to open or retry each: without
    # it, a major update whose lock file couldn't be written closed itself unseen.
    assert ":disableDependencyDashboard" not in shared["extends"] + own["extends"]
    assert {
        key: value
        for key, value in shared.items()
        if key.startswith("dependencyDashboard")
    } == {
        "dependencyDashboard": True,
        "dependencyDashboardTitle": "Dependency dashboard",
        "dependencyDashboardLabels": ["dependencies"],
        "dependencyDashboardOSVVulnerabilitySummary": "all",
    }
    assert not any(key.startswith("dependencyDashboard") for key in own)
    labels = tomllib.loads((root / ".github/labels.toml").read_text(encoding="utf-8"))
    assert "dependencies" in {label["name"] for label in labels["label"]}
    # GitHub starts the scheduled runs of the bot every two hours only roughly and
    # skips some: in the week of 2026-10-05, one run fell into the window of 00:00 to
    # 06:59 of Monday. The whole Monday has a dozen; fixes of vulnerabilities come at
    # any time.
    assert shared["schedule"] == ["* * * * 1"]
    assert shared["lockFileMaintenance"]["schedule"] == ["* * * * 1"]
    assert shared["vulnerabilityAlerts"]["schedule"] == ["at any time"]
    assert "schedule" not in own


# The rules of config:recommended that decide the type of Renovate's commits, from
# :semanticPrefixFixDepsChoreOthers of Renovate 44: fix(deps) for the dependencies of
# npm and the require of Composer only, chore(deps) for everything else.
RECOMMENDED_COMMIT_TYPES = [
    {"matchPackageNames": ["*"], "semanticCommitType": "chore"},
    {"matchDepTypes": ["dependencies", "require"], "semanticCommitType": "fix"},
]
# An update of what the users of each kind of project run: its manager, its type of
# dependency, and its file.
WHAT_THE_USERS_RUN = {
    "home-assistant": [
        ("homeassistant-manifest", "", "custom_components/demo/manifest.json")
    ],
    "nextcloud-app": [("composer", "require", "composer.json")],
    "github-action": [
        ("github-actions", "action", "action.yml"),
        ("pep621", "project.dependencies", "pyproject.toml"),
    ],
    "python-package": [("pep621", "project.dependencies", "pyproject.toml")],
    "node-package": [("npm", "dependencies", "package.json")],
    "container": [("dockerfile", "final", "Dockerfile")],
    "generic": [],
}
# Updates of the tools of every kind, and of each kind's own.
THE_TOOLS = [
    ("github-actions", "action", ".github/workflows/ci.yml"),
    ("custom.regex", "", ".github/workflows/docs.yml"),
    ("custom.regex", "", "scripts/diagrams.sh"),
    ("pip-compile", "", ".github/docs-requirements.txt"),
    ("dockerfile", "final", ".devcontainer/Dockerfile"),
    ("dockerfile", "final", ".github/social-preview/Dockerfile"),
    ("npm", "devDependencies", ".github/prose/package.json"),
    ("npm", "devDependencies", ".github/a11y/package.json"),
    ("custom.regex", "", ".github/mkdocs_blueprint.py"),
    ("pre-commit", "repository", ".pre-commit-config.yaml"),
]
THE_TOOLS_OF_A_KIND = {
    "home-assistant": [("pip-compile", "", "requirements-test.txt")],
    "nextcloud-app": [("composer", "require-dev", "composer.json")],
    "github-action": [("pip-compile", "", "requirements-dev.txt")],
    "python-package": [
        ("pip-compile", "", "requirements-dev.txt"),
        ("pep621", "dependency-groups", "pyproject.toml"),
    ],
    "node-package": [("npm", "devDependencies", "package.json")],
    "container": [],
    "generic": [],
}


def commit_type(
    rules: list[dict[str, Any]], manager: str, dep_type: str, file: str
) -> str | None:
    """The type of Renovate's commit of an update: the last rule that matches it."""
    found = None
    for rule in rules:
        if "semanticCommitType" not in rule:
            continue
        conditions = {key for key in rule if key.startswith("match")}
        # A rule on anything else needs a case here first.
        assert conditions <= {
            "matchPackageNames",
            "matchManagers",
            "matchDepTypes",
            "matchFileNames",
        }, rule
        if (
            rule.get("matchPackageNames", ["*"]) == ["*"]
            and manager in rule.get("matchManagers", [manager])
            and dep_type in rule.get("matchDepTypes", [dep_type])
            and any(
                fnmatch.fnmatchcase(file, name)
                for name in rule.get("matchFileNames", [file])
            )
        ):
            found = rule["semanticCommitType"]
    return found


@pytest.mark.parametrize("kind", [*KINDS, "blueprint"])
def test_updates_of_what_the_users_run_lead_to_a_patch_release(
    projects: dict[str, Path], kind: str
) -> None:
    # The title of the squashed commit decides the release: fix(deps) leads to a patch
    # release, chore(deps) to none. config:recommended commits only the dependencies
    # of npm and Composer as fix, so the requirements of a Home Assistant integration,
    # the dependencies of a Python package, the actions of an action and the base
    # images of a container never reached their users.
    root = ROOT if kind == "blueprint" else projects[kind]
    shared = renovate_rules(
        (root / ".github/renovate-blueprint.json5").read_text(encoding="utf-8")
    )
    own = renovate_rules((root / ".github/renovate.json5").read_text(encoding="utf-8"))
    assert shared["extends"][:2] == ["config:recommended", ":semanticCommits"]
    rules = [
        *RECOMMENDED_COMMIT_TYPES,
        *shared["packageRules"],
        *own.get("packageRules", []),
    ]
    if kind == "blueprint":
        # What every repository gets from the blueprint is what its users run, apart
        # from the tools of the blueprint's own tests.
        for update in [
            *THE_TOOLS,
            ("pip-compile", "", "stacks/python/requirements-dev.txt"),
            ("pep621", "dependency-groups", "pyproject.toml"),
        ]:
            assert commit_type(rules, *update) == "fix", update
        assert commit_type(rules, "pip-compile", "", "requirements-dev.txt") == "chore"
        return
    for update in WHAT_THE_USERS_RUN[kind]:
        assert commit_type(rules, *update) == "fix", update
    for update in [*THE_TOOLS, *THE_TOOLS_OF_A_KIND[kind]]:
        assert commit_type(rules, *update) == "chore", update


# A version pinned in a workflow or a script: NAME_VERSION: 1.2.3, or version=1.2.3.
PINNED_VERSION = re.compile(
    r'^[ \t]*(?:[A-Z][A-Z0-9_]*_VERSION: |version=)"?v?\d', re.MULTILINE
)


@pytest.mark.parametrize("kind", [*KINDS, "blueprint"])
def test_renovate_finds_every_version_that_a_workflow_or_script_pins(
    projects: dict[str, Path], kind: str
) -> None:
    # A version without its line "# renovate:" stays where it is for good, as gitsign
    # and Infection did: their pins in YAML had none, and Renovate's pattern knew only
    # YAML, not the shell of .github/sign-tag.sh.
    root = ROOT if kind == "blueprint" else projects[kind]
    rules = renovate_rules(
        (root / ".github/renovate-blueprint.json5").read_text(encoding="utf-8")
    )
    patterns = [
        re.compile(pattern.replace("(?<", "(?P<"))
        for manager in rules["customManagers"]
        if "datasourceTemplate" not in manager
        for pattern in manager["matchStrings"]
    ]
    files = [
        path
        for folder in (".github/workflows/*.yml", ".github/*.sh", "scripts/*.sh")
        for path in sorted(root.glob(folder))
    ]
    pinned = 0
    for path in files:
        text = path.read_text(encoding="utf-8")
        found = {
            match.end("currentValue"): match
            for pattern in patterns
            for match in pattern.finditer(text)
        }
        for line in PINNED_VERSION.finditer(text):
            end = text.index("\n", line.start())
            match = found.get(end) or found.get(end - 1)
            assert match, f"{path.name}: {text[line.start() : end].strip()}"
            assert match["datasource"] == "github-releases", path.name
            # The version as the files use it, without the v of the tag.
            assert re.fullmatch(r"\d+(\.\d+)+", match["currentValue"]), path.name
            tag = match["extractVersion"]
            assert tag in (None, "^v(?<version>.+)$"), path.name
            pinned += 1
    # gitsign in sign-tag.sh and verify-release.yml, krankerl and Nextcloud in the
    # release of a Nextcloud app and syft for its SBOMs, which every kind has, krankerl
    # in the checks of a Nextcloud app too, and Infection in the mutation tests.
    assert pinned == {
        "blueprint": 7,
        "nextcloud-app": 7,
        "home-assistant": 6,
        "github-action": 6,
        "python-package": 6,
    }.get(kind, 5)


@pytest.mark.parametrize("kind", [*KINDS, "blueprint"])
def test_the_downloads_of_the_workflows_follow_the_blueprint(
    projects: dict[str, Path], kind: str
) -> None:
    # The workflows and .github/sign-tag.sh belong to the blueprint, which moves the
    # tools they download together with their sha256; the next release brings both to
    # every repository. A repository's own Renovate would move only the version, and
    # the download would fail its checksum in the next release.
    root = ROOT if kind == "blueprint" else projects[kind]
    shared = renovate_rules(
        (root / ".github/renovate-blueprint.json5").read_text(encoding="utf-8")
    )
    own = renovate_rules((root / ".github/renovate.json5").read_text(encoding="utf-8"))
    downloads = set(pins.load_record(ROOT))
    enabled, tasks = True, None
    for rule in [*shared["packageRules"], *own.get("packageRules", [])]:
        if downloads & set(rule.get("matchDepNames", [])):
            assert set(rule["matchDepNames"]) == downloads
            assert rule["matchManagers"] == ["custom.regex"]
            assert rule["matchFileNames"] == [
                ".github/workflows/**",
                ".github/sign-tag.sh",
            ]
            enabled = rule["enabled"]
            tasks = rule.get("postUpgradeTasks", tasks)
    assert enabled is (kind == "blueprint")
    if kind != "blueprint":
        assert tasks is None
        assert not (root / "pins.py").exists()
        assert not (root / pins.RECORD).exists()
        return
    # After Renovate moved a version, pins.py writes its sha256, and Renovate commits
    # the files it changed; the bot allows that one command and no other.
    assert tasks == {
        "commands": ["python3 pins.py"],
        "fileFilters": [pins.RECORD, ".github/sign-tag.sh", ".github/workflows/*.yml"],
        "executionMode": "branch",
    }
    bot = renovate_rules(
        (ROOT / ".github/renovate-global.json5").read_text(encoding="utf-8")
    )
    assert bot["allowedCommands"] == ["^python3 pins\\.py$"]
    assert all(
        re.search(allowed, command)
        for command in tasks["commands"]
        for allowed in bot["allowedCommands"]
    )
    assert "allowShellExecutorForPostUpgradeCommands" not in bot
    for pin in pins.find_pins(ROOT):
        assert any(fnmatch.fnmatchcase(pin.path, name) for name in tasks["fileFilters"])


@pytest.mark.parametrize("kind", [*KINDS, "blueprint"])
def test_renovate_leaves_the_issue_assistant_to_the_sync_bot(
    projects: dict[str, Path], kind: str
) -> None:
    root = ROOT if kind == "blueprint" else projects[kind]
    shared = renovate_rules(
        (root / ".github/renovate-blueprint.json5").read_text(encoding="utf-8")
    )
    own = renovate_rules((root / ".github/renovate.json5").read_text(encoding="utf-8"))
    rules = [*shared["packageRules"], *own.get("packageRules", [])]
    # A pin that moved alone would fail the check issue-assistant, which compares the
    # workflows with the templates of the pinned release; the sync bot of the blueprint
    # moves both together. No later rule turns the updates on again.
    action = "Dennis-Otto/issue-assistant"
    off = [
        index
        for index, rule in enumerate(rules)
        if action in rule.get("matchDepNames", [])
    ]
    assert len(off) == 1
    assert rules[off[0]] == {
        "matchManagers": ["github-actions"],
        "matchDepNames": [action],
        "enabled": False,
    }

    def about_the_action(rule: dict[str, Any]) -> bool:
        names = rule.get("matchDepNames")
        managers = rule.get("matchManagers")
        files = rule.get("matchFileNames")
        return (
            (names is None or action in names)
            and (managers is None or "github-actions" in managers)
            and (
                files is None
                or any(
                    name == "**" or name.startswith(".github/workflows")
                    for name in files
                )
            )
        )

    assert not any(
        rule.get("enabled") and about_the_action(rule) for rule in rules[off[0] + 1 :]
    )
    # The sync bot is the blueprint's alone: a repository gets the release with the
    # update of the blueprint.
    if kind != "blueprint":
        assert not (root / ".github/workflows/sync-issue-assistant.yml").exists()
        assert not (root / "sync_issue_assistant.py").exists()


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize(
    ("log", "status", "errors"),
    [
        (
            [
                {
                    "level": 30,
                    "msg": "Extracted dependencies",
                    "sources": {
                        "requirements.in": ["requirements.txt"],
                        "stacks/demo/requirements.in": ["stacks/demo/requirements.txt"],
                    },
                }
            ],
            0,
            [],
        ),
        (
            # Two lock files of one source are one package file of Renovate.
            [
                {
                    "level": 30,
                    "msg": "Extracted dependencies",
                    "sources": {
                        "requirements.in": [
                            "requirements.txt",
                            "stacks/demo/requirements.txt",
                        ]
                    },
                }
            ],
            0,
            [],
        ),
        (
            [
                {
                    "level": 40,
                    "msg": "pip-compile error",
                    "repository": "local",
                    "matchedFile": "stacks/demo/requirements.txt",
                    "errorMessage": "Option --unsafe-package=coverage not supported (yet)",
                },
                {
                    "level": 30,
                    "msg": "Extracted dependencies",
                    "sources": {"requirements.in": ["requirements.txt"]},
                },
            ],
            0,
            [
                'pip-compile error: {"matchedFile": "stacks/demo/requirements.txt",'
                ' "errorMessage": "Option --unsafe-package=coverage not supported'
                ' (yet)"}',
                "Renovate doesn't read the lock file stacks/demo/requirements.txt.",
            ],
        ),
        (
            [{"level": 30, "msg": "Extracted dependencies", "sources": {}}],
            0,
            [
                "Renovate doesn't read the lock file requirements.txt.",
                "Renovate doesn't read the lock file stacks/demo/requirements.txt.",
            ],
        ),
        (
            # Renovate ends with exit code 1 after an error, as with broken rules.
            [{"level": 60, "msg": "Repository has invalid config"}],
            1,
            [
                "Repository has invalid config: {}",
                "Renovate didn't finish reading the files.",
                "Renovate ended with exit code 1.",
            ],
        ),
        (
            # docker can't start Renovate at all.
            [],
            125,
            [
                "Renovate didn't finish reading the files.",
                "Renovate ended with exit code 125.",
            ],
        ),
    ],
)
def test_the_renovate_rules_check_that_renovate_reads_every_lock_file(
    tmp_path: Path, log: list[dict[str, object]], status: int, errors: list[str]
) -> None:
    workflow = (ROOT / ".github/workflows/renovate.yml").read_text(encoding="utf-8")
    job = job_of(workflow, "validate")
    step = job[job.index("      - name: Read every file of the dependencies") :]
    run = "        run: |\n"
    script = textwrap.dedent(step[step.index(run) + len(run) :])
    # A checkout with two lock files of pip-compile, as GitHub leaves it.
    checkout = tmp_path / "checkout"
    for name in ("requirements.txt", "stacks/demo/requirements.txt", "notes.txt"):
        (checkout / name).parent.mkdir(parents=True, exist_ok=True)
        (checkout / name).write_text("# A file.\n", encoding="utf-8")
    author = ["-c", "user.name=Dev", "-c", "user.email=dev@example.com"]
    for command in (
        ["init", "--quiet"],
        ["add", "."],
        [*author, "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "a"],
    ):
        subprocess.run(["git", *command], cwd=checkout, check=True)
    (checkout / "step.sh").write_text(script, encoding="utf-8", newline="\n")
    # Renovate's log as JSON lines, with the package files it found of pip-compile,
    # and a line of its own; docker notes what it gets and ends as Renovate does,
    # python3 is the Python of the tests.
    lines = []
    for entry in log:
        if "sources" in entry:
            sources = entry.pop("sources")
            assert isinstance(sources, dict)
            entry["packageFiles"] = {
                "pip-compile": [
                    {"packageFile": source, "lockFiles": locks, "deps": []}
                    for source, locks in sources.items()
                ],
                "pip_requirements": [{"packageFile": "requirements.txt"}],
            }
        lines.append(json.dumps({"name": "renovate", "pid": 7, "v": 0, **entry}))
    (tmp_path / "log").write_text(
        "Starting Renovate\n" + "".join(f"{line}\n" for line in lines),
        encoding="utf-8",
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool, body in {
        # The archive that it mounts, and its arguments.
        "docker": 'tar -tf - < "${4%:/tmp/repository.tar:ro}" > "$CALLS.tar"\n'
        'printf \'%s\\n\' "$@" > "$CALLS"\ncat "$LOG"\nexit "$STATUS"\n',
        "python3": f'exec "{Path(sys.executable).as_posix()}" "$@"\n',
    }.items():
        (bin_dir / tool).write_text(
            f"#!/usr/bin/env bash\n{body}", encoding="utf-8", newline="\n"
        )
        (bin_dir / tool).chmod(0o755)
    (tmp_path / "temp").mkdir()
    summary = tmp_path / "summary"
    summary.touch()
    calls = tmp_path / "calls"
    environment = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "RUNNER_TEMP": (tmp_path / "temp").as_posix(),
        "GITHUB_STEP_SUMMARY": summary.as_posix(),
        "IMAGE": "renovate",
        "CALLS": calls.as_posix(),
        "LOG": (tmp_path / "log").as_posix(),
        "STATUS": str(status),
    }
    # As GitHub runs a step: bash -e.
    assert BASH
    result = subprocess.run(
        [BASH, "-e", "step.sh"],
        cwd=checkout,
        env=environment,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == (1 if errors else 0), result.stderr
    assert re.findall(r"^::error title=Renovate::(.*)$", result.stdout, re.M) == errors
    # Lines that are no JSON stay in the log of the job.
    assert result.stdout.startswith("Starting Renovate\n")
    expected = "" if errors else "the 2 lock files of pip-compile among them"
    assert expected in summary.read_text(encoding="utf-8")
    # The committed files reach Renovate, in its container, as the rules of the
    # blueprint, without a token, and with every warning in its log.
    archive = (tmp_path / "calls.tar").read_text(encoding="utf-8").splitlines()
    assert sorted(name for name in archive if not name.endswith("/")) == [
        "notes.txt",
        "requirements.txt",
        "stacks/demo/requirements.txt",
    ]
    arguments = calls.read_text(encoding="utf-8").splitlines()
    assert arguments[:3] == ["run", "--rm", "--volume"]
    for argument in (
        "LOG_LEVEL=info",
        "LOG_FORMAT=json",
        "RENOVATE_GITHUB_TOKEN_WARN=false",
        "RENOVATE_CONFIG_FILE=/tmp/repository/.github/renovate-blueprint.json5",
        "renovate",
    ):
        assert argument in arguments, argument
    assert not any(
        "TOKEN=" in argument and "WARN" not in argument for argument in arguments
    )
    assert arguments[-1].strip().endswith("renovate --platform=local --dry-run=extract")


def test_the_renovate_rules_run_for_every_change_of_a_lock_file() -> None:
    workflow = (ROOT / ".github/workflows/renovate.yml").read_text(encoding="utf-8")
    events = workflow[
        workflow.index("\n  pull_request:\n") : workflow.index("\n  workflow_dispatch:")
        + 1
    ]
    for path in (
        ".github/renovate*.json5",
        ".github/workflows/renovate.yml",
        '"**/requirements*.txt"',
        '"**/requirements*.in"',
    ):
        assert f"      - {path}\n" in events, path
    # The step lists the lock files as Renovate finds them.
    step = workflow[
        workflow.index("      - name: Read every file of the dependencies") :
    ]
    pattern = re.search(r"grep -E '([^']+)'", step)
    assert pattern
    rules = (ROOT / ".github/renovate-blueprint.json5").read_text(encoding="utf-8")
    assert f'managerFilePatterns: ["/{json.dumps(pattern[1])[1:-1]}/"]' in rules


def test_a_pull_request_checks_the_renovate_rules_without_waiting_for_the_bot() -> None:
    workflow = (ROOT / ".github/workflows/renovate.yml").read_text(encoding="utf-8")
    # Renovate's run opens several pull requests of lock files at once: a group of
    # the whole workflow would let them wait for the bot and cancel each other.
    assert not re.search(r"^concurrency:", workflow, re.M)
    assert (
        "    concurrency:\n"
        "      group: renovate-rules-${{ github.event.pull_request.number }}\n"
        "      cancel-in-progress: true\n"
    ) in job_of(workflow, "validate")
    # One run of the bot at a time, and a waiting one isn't cancelled by a check.
    assert (
        "    concurrency:\n      group: renovate\n      cancel-in-progress: false\n"
    ) in job_of(workflow, "renovate")


def test_renovate_filters_composer_by_the_php_of_the_stack() -> None:
    composer = json.loads(
        (ROOT / "stacks/php/composer.json").read_text(encoding="utf-8")
    )
    platform = composer["config"]["platform"]["php"]
    expected = f'constraints: {{ php: "{".".join(platform.split(".")[:2])}.*" }}'
    for name in (
        ".github/renovate.json5",
        "template/.github/renovate-blueprint.json5.jinja",
    ):
        assert expected in (ROOT / name).read_text(encoding="utf-8"), name


# The oldest PHP that each major version of PHPUnit runs on, as its composer.json says.
PHPUNIT_PHP = {10: (8, 1), 11: (8, 2), 12: (8, 3), 13: (8, 4)}


def test_renovate_proposes_no_phpunit_that_the_php_of_the_tools_cannot_run() -> None:
    composer = json.loads(
        (ROOT / "stacks/php/composer.json").read_text(encoding="utf-8")
    )
    major, minor = map(int, composer["config"]["platform"]["php"].split(".")[:2])
    newest = max(
        version for version, php in PHPUNIT_PHP.items() if php <= (major, minor)
    )
    # A new app starts on the newest PHPUnit that runs on the PHP of its tools, while
    # it still runs on PHP 8.2 itself.
    assert composer["require"]["php"] == "^8.2"
    assert composer["require-dev"]["phpunit/phpunit"].startswith(f"^{newest}.")
    lock = json.loads((ROOT / "stacks/php/composer.lock").read_text(encoding="utf-8"))
    phpunit = next(
        package
        for package in lock["packages-dev"]
        if package["name"] == "phpunit/phpunit"
    )
    assert phpunit["version"].startswith(f"{newest}.")
    assert phpunit["require"]["php"] == ">={}.{}".format(*PHPUNIT_PHP[newest])
    # Renovate's filter by PHP let PHPUnit 13 through to the apps, whose checks then
    # failed (Dennis-Otto/paperless-sync#80), so a rule holds back the next major
    # version, and each major version comes on its own.
    rule = (
        '      matchDepNames: ["phpunit/phpunit"],\n'
        f'      allowedVersions: "<{newest + 1}",\n'
    )
    for name in (
        ".github/renovate.json5",
        "template/.github/renovate-blueprint.json5.jinja",
    ):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert rule in text, name
        assert "      separateMultipleMajor: true,\n" in text, name


def test_the_dev_container_of_a_nextcloud_app_runs_the_php_of_its_tools() -> None:
    composer = json.loads(
        (ROOT / "stacks/php/composer.json").read_text(encoding="utf-8")
    )
    php = ".".join(composer["config"]["platform"]["php"].split(".")[:2])
    dockerfile = (ROOT / "stacks/php/devcontainer/Dockerfile").read_text(
        encoding="utf-8"
    )
    assert f"\nFROM mcr.microsoft.com/devcontainers/php:{php}@sha256:" in dockerfile


# The attributes of <phpunit> that the schemas of PHPUnit 10.5, 11.5, 12.5 and 13.4
# all know, so that the phpunit.xml of the blueprint fits an app on each of them;
# failOnPhpunitNotice, for one, came only with PHPUnit 12.
PHPUNIT_ATTRIBUTES = {
    "bootstrap",
    "cacheDirectory",
    "colors",
    "failOnDeprecation",
    "failOnNotice",
    "failOnWarning",
    "failOnRisky",
    "failOnPhpunitDeprecation",
    "beStrictAboutOutputDuringTests",
    "executionOrder",
    "resolveDependencies",
}
SCHEMA = "{http://www.w3.org/2001/XMLSchema-instance}noNamespaceSchemaLocation"


def test_the_tests_of_a_nextcloud_app_run_in_a_new_random_order(
    projects: dict[str, Path],
) -> None:
    project = projects["nextcloud-app"]
    root = ElementTree.parse(project / "phpunit.xml").getroot()
    # The schema of the PHPUnit that the app installs, whichever its major version.
    assert root.get(SCHEMA) == "vendor/phpunit/phpunit/phpunit.xsd"
    assert set(root.attrib) - {SCHEMA} <= PHPUNIT_ATTRIBUTES
    # A new order each time, each test after those that it depends on.
    assert root.get("executionOrder") == "depends,random"
    assert root.get("resolveDependencies") == "true"
    # A test that prints, or that uses what PHPUnit deprecates, fails.
    assert root.get("beStrictAboutOutputDuringTests") == "true"
    assert root.get("failOnRisky") == "true"
    assert root.get("failOnPhpunitDeprecation") == "true"
    # How to run an order again, which PHPUnit names as it starts.
    contributing = (project / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "`vendor/bin/phpunit --random-order-seed 1734`" in contributing
    assert "The tests run in a new random order each time" in contributing


def test_every_release_of_the_blueprint_rolls_out_one_repository_at_a_time(
    projects: dict[str, Path],
) -> None:
    rollout = (ROOT / ".github/workflows/rollout.yml").read_text(encoding="utf-8")
    plan = rollout[rollout.index("\n  plan:\n") : rollout.index("\n  rollout:\n")]
    job = rollout[rollout.index("\n  rollout:\n") :]
    # After a successful run of the Release workflow on main, and only in the blueprint.
    assert "workflows: [Release]" in rollout
    assert "branches: [main]" in rollout
    assert "github.event.workflow_run.conclusion == 'success'" in plan
    assert "github.repository == 'Dennis-Otto/repo-blueprint'" in plan
    # A run of any event can make a release: for a push only the merge of a release
    # pull request, whose title the merge commit starts with, so that the merges of
    # every other pull request start no runner.
    assert "github.event.workflow_run.event != 'push' ||" in plan
    prefix = "chore: release "
    assert (
        f"startsWith(github.event.workflow_run.head_commit.message, '{prefix}')" in plan
    )
    config = json.loads(
        (ROOT / "release-please-config.json").read_text(encoding="utf-8")
    )
    assert config["packages"]["."]["pull-request-title-pattern"].startswith(prefix)
    # The release that the run published, not the one at its commit: the job of the
    # Release workflow that makes it public tells.
    assert "HEAD_SHA" not in rollout
    release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "    name: publish the release\n" in release
    assert 'select(.name == "publish the release")' in plan
    # One repository after the other, every one of them, each with a token of its own
    # that can only start workflows and read; 15 looks at most before the next one.
    assert "      max-parallel: 1\n      fail-fast: false\n" in job
    assert "repository: ${{ fromJSON(needs.plan.outputs.repositories) }}" in job
    assert "repositories: ${{ matrix.repository }}" in job
    permissions = re.findall(r"^\s+permission-([\w-]+): (\w+)$", plan, re.M)
    assert permissions == [("metadata", "read")]
    permissions = re.findall(r"^\s+permission-([\w-]+): (\w+)$", job, re.M)
    assert permissions == [
        ("actions", "write"),
        ("checks", "read"),
        ("contents", "read"),
        ("pull-requests", "read"),
        ("statuses", "read"),
    ]
    assert "looks=15\n" in job
    assert "    timeout-minutes: 25\n" in job
    assert "gh workflow run blueprint-update.yml" in job
    # One rollout at a time in each repository, never for the whole workflow: GitHub
    # starts a Rollout run after every run of the Release workflow, and a group of the
    # workflow would let one that rolls nothing out cancel the waiting rollout of a
    # release. The group is on the job that a run without a release skips.
    assert not re.search(r"^concurrency:", rollout, re.M)
    assert re.findall(r"^\s+concurrency:$", rollout, re.M) == ["    concurrency:"]
    assert (
        "    concurrency:\n"
        "      group: rollout-${{ matrix.repository }}\n"
        "      cancel-in-progress: false\n"
    ) in job
    assert "    if: needs.plan.outputs.repositories != ''\n" in job
    zizmor = (ROOT / ".github/zizmor.yml").read_text(encoding="utf-8")
    assert "      - rollout.yml\n" in zizmor
    # The bot it starts can be started by hand; a project has no rollout of its own.
    for project in projects.values():
        update = project / ".github/workflows/blueprint-update.yml"
        assert "  workflow_dispatch:\n" in update.read_text(encoding="utf-8")
        assert not (project / ".github/workflows/rollout.yml").exists()


def test_renovate_runs_one_release_everywhere() -> None:
    pins = set()
    for name in ("renovate.yml", "variants.yml"):
        text = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
        pins |= set(
            re.findall(
                r"ghcr\.io/renovatebot/renovate:[\w.]+@sha256:[0-9a-f]{64}", text
            )
        )
        pins |= {
            f"ghcr.io/renovatebot/renovate:{version}"
            for version in re.findall(r"renovate-version: (\S+)", text)
        }
    assert len(pins) == 1, pins


def test_copier_updates_without_the_maintenance_of_git_in_the_background(
    projects: dict[str, Path],
) -> None:
    # Since Git 2.47, a commit starts git maintenance in the background, and copier
    # update deletes the repositories it commits to right away: the two collided now
    # and then, and the update failed with "Directory not empty".
    command = re.compile(r"^(?!\s*#).*\bcopier update\b", re.MULTILINE)
    settings = (
        'GIT_CONFIG_COUNT: "1"',
        "GIT_CONFIG_KEY_0: maintenance.auto",
        'GIT_CONFIG_VALUE_0: "false"',
    )
    steps = [
        (name, step)
        for root in (projects["generic"], ROOT)
        for name, text in workflows(root).items()
        for step in text.split("\n      - ")[1:]
        if command.search(step)
    ]

    # The blueprint bot of a project and of the blueprint itself, and Variants.
    assert sorted(name for name, _ in steps) == [
        "blueprint-update.yml",
        "blueprint-update.yml",
        "variants.yml",
    ]
    for name, step in steps:
        assert all(setting in step for setting in settings), name


# It starts the tool, which in the copy of the mutation tests is the code with the
# mutants, and the variables of mutmut switch them in that process too.
@pytest.mark.mutation_unsafe
@pytest.mark.parametrize("kind", KINDS)
def test_the_blueprint_bot_keeps_one_pull_request(
    projects: dict[str, Path], kind: str
) -> None:
    project = projects[kind]
    text = (project / ".github/workflows/blueprint-update.yml").read_text(
        encoding="utf-8"
    )
    steps = text.split("\n      - ")
    release = next(step for step in steps if "gh release view" in step)
    update = next(step for step in steps if "copier update --" in step)

    # Only to a published release: the Release workflow pushes the tag first.
    assert 'gh release view --repo "$source" --json tagName --jq .tagName' in release
    assert "TAG: ${{ steps.release.outputs.tag }}" in update
    assert "SOURCE: ${{ steps.release.outputs.source }}" in update
    assert '--source "$SOURCE"' in update
    assert 'copier update --defaults --conflict inline --vcs-ref "$TAG"' in update
    # The bot of main commits, copied before the update changes it, as the app whose
    # commits it may replace; the scratch branch of a commit without modes is per run.
    assert (
        update.index("cp -R .github/blueprint.py .github/blueprint")
        < update.index("copier update --")
        < update.index("git add --all")
        < update.index("update-commit")
    )
    assert "APP: ${{ steps.app.outputs.app-slug }}" in update
    assert '--app "${APP}[bot]"' in update
    assert '--run-id "$GITHUB_RUN_ID"' in update
    # The workflow no longer puts the branch back on main, which closed the pull
    # request, nor scans the whole repository for markers.
    for gone in ("force", "createCommitOnBranch", "git grep", "gh pr merge"):
        assert gone not in text, gone
    tool = (project / ".github/blueprint/update.py").read_text(encoding="utf-8")
    assert '"--disable-auto"' in tool
    assert 'f"{BRANCH}-{run_id}"' in tool
    assert 'BRANCH = "blueprint/update"' in tool
    result = subprocess.run(
        [sys.executable, ".github/blueprint.py", "update-commit", "--help"],
        cwd=project,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "--app APP" in result.stdout
    assert "--source SOURCE" in result.stdout
    # Its description shows the written notes of every release that it brings, with
    # the changelog of the tool that every kind has, and references that still lead
    # to the issues of the blueprint.
    notes = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.path.insert(0, '.github');"
            " from blueprint.update import curated;"
            " print(curated(sys.argv[1], 'Owner/blueprint'), end='')",
            "### Features\n\n- Dark mode (#7).\n\n"
            "## Every pull request of this release\n\n- dark mode\n",
        ],
        cwd=project,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    assert notes.returncode == 0, notes.stderr
    assert notes.stdout == "#### Features\n\n- Dark mode (Owner/blueprint#7)."


def run_the_release_step(tmp_path: Path, source: str) -> tuple[int, str, str]:
    """The step of the blueprint bot that finds the release to update to, with a gh
    that knows the releases of the blueprint and of a fork, and their names as GitHub
    spells them."""
    text = (ROOT / ".github/workflows/blueprint-update.yml").read_text(encoding="utf-8")
    step = next(step for step in text.split("\n      - ") if "gh release view" in step)
    script = textwrap.dedent(step.split("        run: |\n", 1)[1])
    (tmp_path / "step.sh").write_text(script, encoding="utf-8", newline="\n")
    (tmp_path / ".copier-answers.yml").write_text(
        f"_commit: v1.0.0\n_src_path: {source}\n", encoding="utf-8", newline="\n"
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(
        """#!/usr/bin/env bash
case "$*" in
  "api repos/"*" --jq .full_name")
    name="${2#repos/}"
    case "${name,,}" in
      dennis-otto/repo-blueprint) echo Dennis-Otto/repo-blueprint ;;
      someone/blueprint) echo Someone/blueprint ;;
      someone/new) echo Someone/new ;;
      *) echo '{"message":"Not Found","status":"404"}'; echo "gh: Not Found (HTTP 404)" >&2; exit 1 ;;
    esac
    ;;
  "release view --repo Dennis-Otto/repo-blueprint --json tagName --jq .tagName") echo v1.2.0 ;;
  "release view --repo Someone/blueprint --json tagName --jq .tagName") echo v0.3.0 ;;
  "release view --repo Someone/new --json tagName --jq .tagName") ;;
  *) echo "unexpected: gh $*" >&2; exit 1 ;;
esac
""",
        encoding="utf-8",
        newline="\n",
    )
    gh.chmod(0o755)
    output = tmp_path / "output"
    output.touch()
    environment = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "GITHUB_OUTPUT": str(output),
    }
    assert BASH
    result = subprocess.run(
        [BASH, "-e", "step.sh"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    return result.returncode, output.read_text(encoding="utf-8"), result.stdout


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize(
    ("source", "output"),
    [
        (
            "https://github.com/Dennis-Otto/repo-blueprint.git",
            "source=Dennis-Otto/repo-blueprint\ntag=v1.2.0\n",
        ),
        # A repository made from a fork updates to the fork's releases, whose tags
        # the fork has.
        ("gh:Someone/blueprint", "source=Someone/blueprint\ntag=v0.3.0\n"),
        (
            "https://github.com/Someone/blueprint",
            "source=Someone/blueprint\ntag=v0.3.0\n",
        ),
        (
            "git@github.com:Someone/blueprint.git",
            "source=Someone/blueprint\ntag=v0.3.0\n",
        ),
        # GitHub takes the name in any case, the signature of a tag only as GitHub
        # spells it.
        ("gh:someone/BLUEPRINT", "source=Someone/blueprint\ntag=v0.3.0\n"),
    ],
)
def test_the_blueprint_bot_updates_to_the_release_of_its_source(
    tmp_path: Path, source: str, output: str
) -> None:
    assert run_the_release_step(tmp_path, source)[:2] == (0, output)


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize(
    "source",
    [
        # A blueprint elsewhere, or in a folder: no release there can be verified,
        # and no other blueprint's release stands in for it.
        "https://gitlab.com/Someone/blueprint.git",
        "gl:Someone/blueprint",
        "/home/me/repo-blueprint",
    ],
)
def test_the_blueprint_bot_updates_only_from_a_blueprint_on_github(
    tmp_path: Path, source: str
) -> None:
    code, output, stdout = run_the_release_step(tmp_path, source)

    assert code == 1
    assert output == ""
    assert (
        f"::error::The blueprint {source} is not a repository on GitHub; the bot"
        " updates only to a release that it can verify there."
    ) in stdout.splitlines()


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
def test_the_blueprint_bot_needs_a_published_release(tmp_path: Path) -> None:
    code, output, stdout = run_the_release_step(tmp_path, "gh:Someone/new")

    assert code == 1
    assert output == ""
    assert "::error::The blueprint Someone/new has no published release" in stdout


@pytest.mark.parametrize("kind", KINDS)
def test_the_blueprint_bot_verifies_the_release_before_it_updates(
    projects: dict[str, Path], kind: str
) -> None:
    project = projects[kind]
    text = (project / ".github/workflows/blueprint-update.yml").read_text(
        encoding="utf-8"
    )
    steps = text.split("\n      - ")
    names = [step.split("\n", 1)[0] for step in steps]
    release = names.index("name: Find the latest published release of the blueprint")
    verify = names.index("name: Verify the release before updating to it")
    update = names.index("name: Update to the latest release of the blueprint")
    # Between finding the release and the update, and nothing renders before it.
    assert release < verify < update
    assert not any("copier update" in step for step in steps[1 : verify + 1])
    step = steps[verify]
    assert "SOURCE: ${{ steps.release.outputs.source }}" in step
    assert "TAG: ${{ steps.release.outputs.tag }}" in step
    # The job's own token reads the public blueprint; the step needs no secret.
    assert "GH_TOKEN: ${{ github.token }}" in step
    assert "secrets." not in step
    assert 'ask "repos/$SOURCE/releases/tags/$TAG" --jq .immutable' in step
    assert 'ask "repos/$SOURCE/compare/$commit...main" --jq .status' in step
    # Not a commit before the version that the repository has.
    assert "old=\"$(sed -n 's/^_commit: *//p' .copier-answers.yml)\"" in step
    assert 'since="$(ask "repos/$SOURCE/compare/$old...$commit" --jq .status)"' in step
    # The tag's signature, checked by the script that checks the release tags of the
    # repository itself, with gitsign pinned by version and checksum.
    assert (
        'bash .github/sign-tag.sh verify "$TAG" "$commit" "$SOURCE" || verified=$?'
        in step
    )
    assert (project / ".github/sign-tag.sh").read_text(encoding="utf-8") == (
        ROOT / ".github/sign-tag.sh"
    ).read_text(encoding="utf-8")
    # Copier updates to exactly the tag that was verified.
    assert (
        'copier update --defaults --conflict inline --vcs-ref "$TAG"' in steps[update]
    )


def run_the_verify_step(
    tmp_path: Path,
    immutable: str,
    status: str,
    signed: bool,
    failures: int = 0,
    unchecked: bool = False,
    since: str = "ahead",
    old: str = "v1.1.0",
    base: str = "v1.1.0",
) -> tuple[subprocess.CompletedProcess[str], list[str], str]:
    """The step of the blueprint bot that verifies the release, with a gh that answers
    for a release of a fork of the blueprint, after failing the first `failures` times
    as GitHub does now and then, and a sign-tag.sh that only records how it is called
    and fails where the tag isn't signed, or with 2 where it couldn't check it. The
    repository has the version `old` of the blueprint, which gh knows as `base` and
    compares with the release as `since`, or doesn't know where `since` is "missing"."""
    text = (ROOT / ".github/workflows/blueprint-update.yml").read_text(encoding="utf-8")
    step = next(
        step
        for step in text.split("\n      - ")
        if step.startswith("name: Verify the release before updating to it")
    )
    script = textwrap.dedent(step.split("        run: |\n", 1)[1])
    (tmp_path / "step.sh").write_text(script, encoding="utf-8", newline="\n")
    (tmp_path / ".copier-answers.yml").write_text(
        "# Changes here will be overwritten by Copier; NEVER EDIT MANUALLY\n"
        + (f"_commit: {old}\n" if old else "")
        + "_src_path: gh:Someone/blueprint\n",
        encoding="utf-8",
        newline="\n",
    )
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github/sign-tag.sh").write_text(
        'echo "sign-tag.sh $*" >> "$CALLS"\n'
        '[[ "$UNCHECKED" == true ]] && exit 2\n'
        '[[ "$SIGNED" == true ]]\n',
        encoding="utf-8",
        newline="\n",
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(
        """#!/usr/bin/env bash
echo "gh $*" >> "$CALLS"
failed=$(grep -c "^HTTP 502" "$CALLS" || true)
if ((failed < FAILURES)); then
  echo "HTTP 502" >> "$CALLS"
  # As gh does: the body of the error on stdout, even with --jq.
  echo '{"message":"Bad Gateway","status":"502"}'
  echo "gh: Bad Gateway (HTTP 502)" >&2
  exit 1
fi
case "$*" in
  "api repos/Someone/blueprint/releases/tags/v1.2.0 --jq .immutable") echo "$IMMUTABLE" ;;
  "api repos/Someone/blueprint/commits/v1.2.0 --jq .sha") echo abc123 ;;
  "api repos/Someone/blueprint/compare/abc123...main --jq .status") echo "$STATUS" ;;
  "api repos/Someone/blueprint/compare/$BASE...abc123 --jq .status")
    if [[ "$SINCE" == missing ]]; then
      echo '{"message":"Not Found","status":"404"}'
      echo "gh: Not Found (HTTP 404)" >&2
      exit 1
    fi
    echo "$SINCE" ;;
  *) echo "unexpected: gh $*" >&2; exit 1 ;;
esac
""",
        encoding="utf-8",
        newline="\n",
    )
    gh.chmod(0o755)
    # The step waits 10 and 20 seconds between its questions; the test doesn't.
    sleep = bin_dir / "sleep"
    sleep.write_text(
        '#!/usr/bin/env bash\necho "sleep $*" >> "$CALLS"\n',
        encoding="utf-8",
        newline="\n",
    )
    sleep.chmod(0o755)
    calls = tmp_path / "calls"
    summary = tmp_path / "summary"
    for file in (calls, summary):
        file.touch()
    environment = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "STUBS": str(bin_dir),
        "CALLS": str(calls),
        "GITHUB_STEP_SUMMARY": str(summary),
        "SOURCE": "Someone/blueprint",
        "TAG": "v1.2.0",
        "IMMUTABLE": immutable,
        "STATUS": status,
        "SINCE": since,
        "BASE": base,
        "SIGNED": "true" if signed else "false",
        "UNCHECKED": "true" if unchecked else "false",
        "FAILURES": str(failures),
    }
    # As GitHub runs a step: bash -e.
    result = subprocess.run(
        in_bash("-e", "step.sh"),
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    return (
        result,
        calls.read_text(encoding="utf-8").splitlines(),
        summary.read_text(encoding="utf-8"),
    )


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize(
    ("status", "since", "old", "base"),
    [
        # main is at the release, or has moved on from it.
        ("identical", "ahead", "v1.1.0", "v1.1.0"),
        ("ahead", "ahead", "v1.1.0", "v1.1.0"),
        # The repository has the release already.
        ("ahead", "identical", "v1.2.0", "v1.2.0"),
        # A repository made from a commit past a tag, as git describe names it.
        ("ahead", "ahead", "v1.1.0-3-gdef4567", "def4567"),
    ],
)
def test_a_signed_immutable_release_on_main_passes(
    tmp_path: Path, status: str, since: str, old: str, base: str
) -> None:
    result, calls, summary = run_the_verify_step(
        tmp_path, "true", status, signed=True, since=since, old=old, base=base
    )

    assert result.returncode == 0, result.stdout + result.stderr
    # Compared with the version that the repository has.
    assert (
        f"gh api repos/Someone/blueprint/compare/{base}...abc123 --jq .status" in calls
    )
    # The signature of the tag, of the release workflow of the blueprint, at the commit
    # that is on its main.
    assert calls[-1] == "sign-tag.sh verify v1.2.0 abc123 Someone/blueprint"
    assert (
        "The release v1.2.0 of Someone/blueprint is immutable, on its main, no older"
        f" than {base} and signed by its release workflow."
    ) in summary


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize(
    ("immutable", "status", "since", "signed", "error"),
    [
        (
            "false",
            "ahead",
            "ahead",
            True,
            "::error::The release v1.2.0 of Someone/blueprint is not immutable; the bot"
            " updates only to an immutable release.",
        ),
        # The tag of a commit that main never had, or one past main.
        (
            "true",
            "diverged",
            "ahead",
            True,
            "::error::The tag v1.2.0 of Someone/blueprint points at abc123, which is"
            " not on its main (diverged).",
        ),
        (
            "true",
            "behind",
            "ahead",
            True,
            "::error::The tag v1.2.0 of Someone/blueprint points at abc123, which is"
            " not on its main (behind).",
        ),
        # An older commit of main under a newer version, or one that the version of the
        # repository isn't part of: either would take the repository back.
        (
            "true",
            "ahead",
            "behind",
            True,
            "::error::The tag v1.2.0 of Someone/blueprint points at abc123, which"
            " doesn't come after v1.1.0, the version this repository has (behind).",
        ),
        (
            "true",
            "ahead",
            "diverged",
            True,
            "::error::The tag v1.2.0 of Someone/blueprint points at abc123, which"
            " doesn't come after v1.1.0, the version this repository has (diverged).",
        ),
        # A lightweight tag, one at another commit, or one that another workflow
        # signed: sign-tag.sh says which, in tests/test_sign_tag.py.
        (
            "true",
            "ahead",
            "ahead",
            False,
            "::error::The tag v1.2.0 of Someone/blueprint is not one that its release"
            " workflow signed at abc123.",
        ),
    ],
)
def test_any_other_release_stops_the_update(
    tmp_path: Path, immutable: str, status: str, since: str, signed: bool, error: str
) -> None:
    result, calls, summary = run_the_verify_step(
        tmp_path, immutable, status, signed, since=since
    )

    assert result.returncode == 1
    assert error in result.stdout.splitlines()
    # The summary says why, what it means and what to do.
    assert summary.startswith(
        "### The blueprint bot refused the release v1.2.0 of Someone/blueprint\n\n"
        f"{error.removeprefix('::error::')}\n\n"
    )
    assert "Nothing has changed here." in summary
    assert (
        "(https://github.com/Someone/blueprint/blob/main/SECURITY.md#verify-a-release)"
        in summary
    )
    assert "is immutable, on its main, no older than" not in summary
    # The signature is checked last, only for an immutable release on main that
    # comes after the version of the repository.
    verified = [call for call in calls if call.startswith("sign-tag.sh ")]
    assert verified == (
        ["sign-tag.sh verify v1.2.0 abc123 Someone/blueprint"] if not signed else []
    )


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
def test_the_verification_asks_github_again_after_a_failure(tmp_path: Path) -> None:
    result, calls, summary = run_the_verify_step(
        tmp_path, "true", "ahead", signed=True, failures=2
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert calls[:5] == [
        "gh api repos/Someone/blueprint/releases/tags/v1.2.0 --jq .immutable",
        "HTTP 502",
        "sleep 10",
        "gh api repos/Someone/blueprint/releases/tags/v1.2.0 --jq .immutable",
        "HTTP 502",
    ]
    assert calls[5:7] == [
        "sleep 20",
        "gh api repos/Someone/blueprint/releases/tags/v1.2.0 --jq .immutable",
    ]
    assert calls[-1] == "sign-tag.sh verify v1.2.0 abc123 Someone/blueprint"
    assert "is immutable, on its main, no older than v1.1.0 and signed" in summary


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
def test_every_question_gets_its_answer_after_a_failure(tmp_path: Path) -> None:
    # One failure before the first answer, whose body gh prints too.
    result, calls, summary = run_the_verify_step(
        tmp_path, "true", "ahead", signed=True, failures=1
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "::error::" not in result.stdout
    # The commit, not the body of the error before it, goes into the comparison.
    assert "gh api repos/Someone/blueprint/compare/abc123...main --jq .status" in calls
    assert calls[-1] == "sign-tag.sh verify v1.2.0 abc123 Someone/blueprint"
    assert "is immutable, on its main, no older than v1.1.0 and signed" in summary


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
def test_a_signature_that_could_not_be_checked_fails_but_refuses_nothing(
    tmp_path: Path,
) -> None:
    result, calls, summary = run_the_verify_step(
        tmp_path, "true", "ahead", signed=True, unchecked=True
    )

    assert result.returncode == 1
    assert (
        "::error::The signature of the release v1.2.0 of Someone/blueprint could not"
        " be checked; nothing has changed, and the next run checks it again."
    ) in result.stdout.splitlines()
    assert calls[-1] == "sign-tag.sh verify v1.2.0 abc123 Someone/blueprint"
    # Not a refusal: gitsign, GitHub or Sigstore didn't answer.
    assert summary == ""


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
def test_a_github_without_an_answer_fails_the_update_but_refuses_nothing(
    tmp_path: Path,
) -> None:
    result, calls, summary = run_the_verify_step(
        tmp_path, "true", "ahead", signed=True, failures=3
    )

    assert result.returncode == 1
    assert "Bad Gateway" in result.stderr
    assert "::error::" not in result.stdout
    assert calls.count("HTTP 502") == 3
    assert [call for call in calls if call.startswith("sleep")] == [
        "sleep 10",
        "sleep 20",
    ]
    # Not a refusal: GitHub didn't answer, and the next run asks again.
    assert summary == ""
    assert not any(call.startswith("sign-tag.sh") for call in calls)


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
def test_a_version_that_github_doesnt_know_fails_but_refuses_nothing(
    tmp_path: Path,
) -> None:
    # The version of the repository isn't in the blueprint, or GitHub doesn't answer.
    result, calls, summary = run_the_verify_step(
        tmp_path, "true", "ahead", signed=True, since="missing"
    )

    assert result.returncode == 1
    assert (
        "::error::GitHub could not compare v1.1.0, the version of Someone/blueprint"
        " that this repository has, with the tag v1.2.0; nothing has changed, and the"
        " next run asks again."
    ) in result.stdout.splitlines()
    assert "Not Found" in result.stderr
    # Asked three times, as every question.
    compare = "gh api repos/Someone/blueprint/compare/v1.1.0...abc123 --jq .status"
    assert calls.count(compare) == 3
    assert summary == ""
    assert not any(call.startswith("sign-tag.sh") for call in calls)


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
def test_answers_without_a_version_fail_but_refuse_nothing(tmp_path: Path) -> None:
    result, calls, summary = run_the_verify_step(
        tmp_path, "true", "ahead", signed=True, old=""
    )

    assert result.returncode == 1
    assert (
        "::error::.copier-answers.yml doesn't name the version of the blueprint that"
        " this repository has, so the bot can't tell whether v1.2.0 comes after it;"
        " nothing has changed."
    ) in result.stdout.splitlines()
    assert not any("...abc123" in call for call in calls)
    assert summary == ""
    assert not any(call.startswith("sign-tag.sh") for call in calls)


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize(
    ("client", "key", "missing"),
    [
        (
            "",
            "false",
            "names no release app in the variable RELEASE_AUTOMATION_CLIENT_ID",
        ),
        (
            "Iv23liOcto",
            "false",
            "has no private key of its release app in the secret"
            " RELEASE_AUTOMATION_PRIVATE_KEY of the environment release",
        ),
    ],
    ids=["no app", "no key"],
)
def test_the_blueprint_bot_says_what_its_release_app_lacks(
    tmp_path: Path, client: str, key: str, missing: str
) -> None:
    done = workflow_steps.run_step(
        tmp_path,
        "blueprint-update.yml",
        "update",
        "Check that the release app is set up",
        env={"CLIENT_ID": client, "KEY_SET": key},
    )

    assert done.returncode == 1
    assert done.stdout.splitlines() == [
        f"::error::This repository {missing}, which the blueprint bot needs to push an"
        " update and open its pull request; nothing has changed."
    ]
    assert done.summary.startswith(
        "### The blueprint bot needs the release app of the owner\n\n"
        f"This repository {missing}. "
    )
    assert "`python3 .github/blueprint.py checklist` shows the steps" in done.summary
    assert done.calls == []


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
def test_the_blueprint_bot_goes_on_with_its_release_app(tmp_path: Path) -> None:
    done = workflow_steps.run_step(
        tmp_path,
        "blueprint-update.yml",
        "update",
        "Check that the release app is set up",
        env={"CLIENT_ID": "Iv23liOcto", "KEY_SET": "true"},
    )

    assert done.returncode == 0
    assert done.stdout == ""
    assert done.summary == ""
    # Before the token of the app, which would fail without it.
    names = [
        found.get("name")
        for found in workflow_steps.job("blueprint-update.yml", "update")["steps"]
    ]
    assert names.index("Check that the release app is set up") + 1 == names.index(
        "Create a token of the release app"
    )


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
def test_the_release_bot_explains_a_missing_release_app(tmp_path: Path) -> None:
    found = workflow_steps.step(
        "release.yml", "release-please", "Explain a missing release app"
    )
    assert found["if"] == "vars.RELEASE_AUTOMATION_CLIENT_ID == ''"
    done = workflow_steps.run_step(
        tmp_path, "release.yml", "release-please", "Explain a missing release app"
    )

    # A warning: release-please still keeps its pull request.
    assert done.returncode == 0
    assert done.stdout.startswith(
        "::warning::This repository names no release app in the variable"
        " RELEASE_AUTOMATION_CLIENT_ID"
    )
    assert done.summary.startswith("### No release app\n\n")
    assert "`python3 .github/blueprint.py checklist` shows how" in done.summary
    assert done.calls == []


# Anything that names the blueprint owner as a person or an account, or the release app
# of the blueprint owner, but a reference to one of its repositories, such as the
# blueprint itself or its issue assistant.
BLUEPRINT_OWNER = re.compile(
    r"(?i)dennis[ -]otto(?!/[\w.-])|Iv23liP9PIEHOV74AiIA|\b4739928\b"
)


@pytest.mark.parametrize("kind", KINDS)
def test_a_foreign_owner_gets_no_wiring_of_the_blueprint_owner(
    tmp_path: Path, kind: str
) -> None:
    project = render(
        tmp_path / "project",
        project_name="Demo Project",
        description="A project of another owner.",
        project_type=kind,
        owner="octo-org",
    )

    found = [
        f"{path.relative_to(project).as_posix()}: {match[0]}"
        for path in text_files(project)
        for match in BLUEPRINT_OWNER.finditer(path.read_text(encoding="utf-8"))
    ]
    assert found == []
    # Their own name, in the license and the governance.
    answers = yaml.safe_load((project / ".copier-answers.yml").read_text("utf-8"))
    assert answers["author"] == "octo-org"
    assert answers["sponsor"] == "octo-org"
    assert "maintained by octo-org" in (project / "GOVERNANCE.md").read_text("utf-8")
    # No release app yet: no variable names one, no ruleset lets one create the release
    # tags, and the environment release waits for no private key of one.
    assert answers["release_app"] == ""
    assert "release_app_client_id" not in answers
    assert "release_app_id" not in answers
    settings = Settings.load(project / ".github/repository.toml")
    assert not {
        "RELEASE_APP",
        "RELEASE_AUTOMATION_CLIENT_ID",
        "RELEASE_AUTOMATION_APP_ID",
    } & set(settings.variables)
    assert "Release tag creation" not in {
        ruleset["name"] for ruleset in settings.rulesets
    }
    assert (
        "RELEASE_AUTOMATION_PRIVATE_KEY"
        not in (settings.environments["release"]["secrets"])
    )
    toml = (project / ".github/repository.toml").read_text(encoding="utf-8")
    assert "`python3 .github/blueprint.py checklist` shows how to register" in toml


def test_a_foreign_owner_names_a_release_app_of_their_own(tmp_path: Path) -> None:
    project = render(
        tmp_path / "project",
        project_name="Demo Project",
        description="A project of another owner.",
        project_type="nextcloud-app",
        owner="octo-org",
        author="Octo Org",
        release_app="octo-org-release-automation",
        release_app_client_id="Iv23liOcto",
        release_app_id="12345",
    )

    settings = Settings.load(project / ".github/repository.toml")
    assert settings.variables == {
        "PUBLISH_TO": "nextcloud-appstore",
        "RELEASE_APP": "octo-org-release-automation",
        "RELEASE_AUTOMATION_CLIENT_ID": "Iv23liOcto",
        "RELEASE_AUTOMATION_APP_ID": "12345",
    }
    creation = next(
        ruleset
        for ruleset in settings.rulesets
        if ruleset["name"] == "Release tag creation"
    )
    assert creation["bypass_actors"] == [
        {"actor_id": 12345, "actor_type": "Integration", "bypass_mode": "always"}
    ]
    assert settings.environments["release"]["secrets"] == [
        "RELEASE_AUTOMATION_PRIVATE_KEY",
        "APP_PRIVATE_KEY",
        "APPSTORE_TOKEN",
    ]
    toml = (project / ".github/repository.toml").read_text(encoding="utf-8")
    assert "https://github.com/apps/octo-org-release-automation" in toml
    assert "maintained by Octo Org" in (project / "GOVERNANCE.md").read_text("utf-8")


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({}, 'Question "owner" is required'),
        ({"owner": "octo org"}, "Name the GitHub account or organization"),
        (
            {"owner": "octo-org", "release_app": "Octo App"},
            "Name the app as its address does",
        ),
        (
            {
                "owner": "octo-org",
                "release_app": "octo-app",
                "release_app_client_id": "12345",
                "release_app_id": "12345",
            },
            "Copy the Client ID from the settings page of the app",
        ),
        (
            {
                "owner": "octo-org",
                "release_app": "octo-app",
                "release_app_client_id": "Iv23liOcto",
                "release_app_id": "Iv23liOcto",
            },
            "Copy the App ID, a number",
        ),
    ],
    ids=["no owner", "owner", "app", "client id", "app id"],
)
def test_the_questions_of_the_owner_refuse_what_github_would_not_take(
    tmp_path: Path, data: dict[str, str], message: str
) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with pytest.raises(ValueError, match=re.escape(message)):
            run_copy(
                str(Template.folder),
                tmp_path / "project",
                data={
                    "project_name": "Demo Project",
                    "description": "A demo.",
                    "project_type": "generic",
                    **data,
                },
                defaults=True,
                vcs_ref="HEAD",
                quiet=True,
            )


def test_the_owner_of_the_blueprint_keeps_the_answers_of_its_repositories(
    projects: Mapping[str, Path],
) -> None:
    # copier update --defaults gives each repository of the Rollout the release app
    # that it has, from the defaults of the blueprint owner, so the update changes none
    # of its settings.
    answers = yaml.safe_load(
        (projects["generic"] / ".copier-answers.yml").read_text(encoding="utf-8")
    )
    keys = ("author", "release_app", "release_app_client_id", "release_app_id")
    for name, theirs in ANSWERS.items():
        assert {key: theirs[key] for key in keys} == {
            key: answers[key] for key in keys
        }, name
    # The defaults are those of the blueprint's own repository.
    copier = yaml.safe_load((ROOT / "copier.yml").read_text(encoding="utf-8"))
    own = copier["blueprint_owner"]["default"]
    settings = Settings.load(ROOT / ".github/repository.toml")
    assert own == {
        "account": OWNER,
        "author": "Dennis Otto",
        "release_app": settings.variables["RELEASE_APP"],
        "release_app_client_id": settings.variables["RELEASE_AUTOMATION_CLIENT_ID"],
        "release_app_id": settings.variables["RELEASE_AUTOMATION_APP_ID"],
    }


@pytest.mark.parametrize(
    ("folder", "owner", "cd"),
    [
        ("my-project", "octo-org", "  cd my-project\n"),
        ("my project", "octo-org", '  cd "my project"\n'),
        (".", OWNER, ""),
    ],
    ids=["folder", "folder with a space", "here"],
)
def test_copier_names_what_the_copy_needs_and_the_one_command_after_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    folder: str,
    owner: str,
    cd: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        # What a person sees, without the files: Copier writes none.
        run_copy(
            str(Template.folder),
            folder,
            data={
                "project_name": "Demo Project",
                "description": "A demo.",
                "project_type": "generic",
                "owner": owner,
            },
            defaults=True,
            vcs_ref="HEAD",
            pretend=True,
        )
    said = capsys.readouterr().err

    before, _, after = said.partition("Copying from template version")
    # Before the questions: what the command after the copy needs, and no --trust.
    assert "Copying runs no code of the blueprint, so Copier needs no --trust" in before
    assert "Python 3.12 or\nlater and GitHub CLI 2.48 or later" in before
    # After the files: the one command, which every copy brings, and no checkout of
    # the blueprint, whose path Copier can't know.
    assert (
        f"Demo Project is ready. Make it the repository {owner}/demo-project on GitHub:\n"
        f"\n{cd}  python3 .github/blueprint.py create\n\ncreate commits" in after
    )
    assert "blueprint.py" in TOOL
    assert "<blueprint>" not in after
    assert "gh repo create --" not in after
    # Only an owner without a release app is told that the checklist registers one.
    assert ("The checklist starts with the release app of" in after) is (owner != OWNER)


def test_renovate_keeps_the_copier_of_the_quick_start_current() -> None:
    renovate = (ROOT / ".github/renovate.json5").read_text(encoding="utf-8")
    assert '"/^README(\\\\.de)?\\\\.md$/"' in renovate
    # The pattern of the manager, as JSON reads its string, in the syntax of Python.
    written = re.search(r'\n {8}("\(\?<depName>copier\)[^\n]+"),\n', renovate)
    assert written is not None
    pattern = json.loads(written[1]).replace("(?<", "(?P<")
    copier = yaml.safe_load((ROOT / "copier.yml").read_text(encoding="utf-8"))
    least = tuple(int(part) for part in copier["_min_copier_version"].split("."))
    for readme in ("README.md", "README.de.md"):
        text = (ROOT / readme).read_text(encoding="utf-8")
        found = [match.groupdict() for match in re.finditer(pattern, text)]
        # The command of uv and that of pipx, with one release that the template takes.
        assert len(found) == 2, readme
        assert {item["depName"] for item in found} == {"copier"}
        (version,) = {item["currentValue"] for item in found}
        assert tuple(int(part) for part in version.split(".")) >= least
        assert f"uvx --from copier=={version} copier copy gh:" in text
        assert f"pipx run --spec copier=={version} copier copy gh:" in text


@pytest.mark.parametrize("kind", KINDS)
def test_only_the_release_app_creates_the_release_tags_of_a_project(
    projects: dict[str, Path], kind: str
) -> None:
    settings = Settings.load(projects[kind] / ".github/repository.toml")
    # The App ID next to the Client ID of the same app, and the name in its address.
    assert settings.variables["RELEASE_APP"] == "dennis-otto-release-automation"
    assert settings.variables["RELEASE_AUTOMATION_CLIENT_ID"] == "Iv23liP9PIEHOV74AiIA"
    assert settings.variables["RELEASE_AUTOMATION_APP_ID"] == "4739928"
    creation = next(
        ruleset
        for ruleset in settings.rulesets
        if ruleset["name"] == "Release tag creation"
    )
    assert creation["rules"] == [{"type": "creation"}]
    assert creation["bypass_actors"] == [
        {"actor_id": 4739928, "actor_type": "Integration", "bypass_mode": "always"}
    ]
    # The blueprint has the same app.
    blueprint = Settings.load(ROOT / ".github/repository.toml")
    assert creation in blueprint.rulesets


def test_every_release_tag_is_created_with_the_token_of_the_release_app() -> None:
    # The only rule with an exception: a tag that the job token of a workflow created
    # would fail the ruleset Release tag creation and stop the release.
    release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    steps = release.split("\n      - ")
    creating = [
        step
        for step in steps
        if "bash .github/sign-tag.sh" in step or "gh release create" in step
    ]
    # The tag of a release, and that of a beta, which gh release create only finds.
    assert len(creating) == 2
    for step in creating:
        assert "GH_TOKEN: ${{ steps.app.outputs.token }}" in step
        assert "steps.app.outputs.token != ''" in step
    beta = next(step for step in creating if "gh release create" in step)
    assert beta.index('bash .github/sign-tag.sh "v$version"') < beta.index(
        "gh release create"
    )
    assert "--verify-tag" in beta
    # release-please creates no tag: only a release on the tag that a run signed.
    please = next(step for step in steps if "googleapis/release-please-action@" in step)
    assert "skip-github-release: ${{ steps.sign.outputs.signed != 'true' }}" in please
    # The major tag of an action, such as v1, may move and is no release tag.
    assert 'git tag -fa "$MAJOR"' in release


def test_the_branch_bot_brings_renovate_up_to_date_as_renovate_itself() -> None:
    text = (ROOT / ".github/workflows/update-branches.yml").read_text(encoding="utf-8")
    # Renovate's pull requests take their place in the line, but not the release bot's,
    # and a conflicting one of Renovate gets no label and no comment: blueprint.py
    # next-branch decides, which tests/test_branches.py tests.
    assert "next-branch" in text
    # The bot's merge commits come from the release app, as Renovate's own commits
    # do, so Renovate doesn't take the branch for edited and keeps it current.
    assert "client-id: ${{ vars.RELEASE_AUTOMATION_CLIENT_ID }}" in text
    bot = (ROOT / ".github/renovate-global.json5").read_text(encoding="utf-8")
    assert 'username: "dennis-otto-release-automation[bot]"' in bot
    assert 'gitAuthor: "dennis-otto-release-automation[bot] <' in bot


def test_the_branch_bot_moves_its_line_on_at_once() -> None:
    text = (ROOT / ".github/workflows/update-branches.yml").read_text(encoding="utf-8")
    events = triggers(text)
    assert set(events) == {
        "push",
        "pull_request_target",
        "workflow_run",
        "schedule",
        "workflow_dispatch",
    }
    # Turning auto-merge on or off, and a check that fails, move the line on; a merge
    # into main does too, and the schedule is the safety net.
    assert events["pull_request_target"] == [
        "    types: [auto_merge_enabled, auto_merge_disabled]"
    ]
    assert "    types: [completed]" in events["workflow_run"]
    assert "often hours late" in text
    job = job_of(text, "update")
    condition = condition_of(job)
    assert "github.event.pull_request.head.repo.full_name == github.repository" in (
        condition
    )
    assert (
        "github.event.pull_request.base.ref == github.event.repository.default_branch"
        in condition
    )
    # The title's check runs on pull_request_target.
    assert (
        """contains(fromJSON('["pull_request", "pull_request_target"]'), """
        "github.event.workflow_run.event)" in condition
    )
    # A failed test moves the line on only when it stays failed, at the second
    # attempt, since the bots after the checks run it once more; the other checks move
    # it on at once: the same list as theirs, without the release.
    assert "github.event.workflow_run.run_attempt > 1" in condition
    listed = re.search(
        r"contains\(fromJSON\('(\[[^\]]+\])'\), github\.event\.workflow_run\.name\)",
        condition,
    )
    assert listed
    assert set(json.loads(listed[1])) == OTHER_CHECKS | SCANNER_WORKFLOWS
    # The token reads the checks and the statuses of the line.
    for permission in ("checks: read", "statuses: read", "contents: write"):
        assert f"          permission-{permission}\n" in job, permission
    assert (
        """contains(fromJSON('["failure", "timed_out", "startup_failure"]'), """
        "github.event.workflow_run.conclusion)" in condition
    )
    # A group on the job: a run whose job skips, as after checks that passed, would
    # otherwise cancel the run that updates.
    assert not re.search(r"^concurrency:", text, re.M)
    assert (
        "    concurrency:\n      group: update-branches\n      cancel-in-progress: true\n"
        in job
    )
    # It checks out the default branch, without the token, and runs nothing of a pull
    # request: no value of the event reaches a command.
    assert "persist-credentials: false" in job
    assert "ref:" not in job
    run = job[job.index("        run: |") :]
    assert "${{" not in run
    assert 'next-branch "${only[@]}" | tee -a "$GITHUB_STEP_SUMMARY"' in run
    # A run for auto-merge shows as a check of that pull request, and the bot-health
    # bot ignores it: it passes with the warnings.
    assert '[[ "$GITHUB_EVENT_NAME" == pull_request_target ]]' in run
    assert "only=(--warnings-only)" in run
    assert "set -o pipefail" in run
    zizmor = (ROOT / ".github/zizmor.yml").read_text(encoding="utf-8")
    dangerous = zizmor.split("  dangerous-triggers:", 1)[1].split("\n  self-", 1)[0]
    assert "      - update-branches.yml\n" in dangerous


@pytest.mark.parametrize("project", ["blueprint", *KINDS])
def test_a_failed_check_moves_the_line_of_the_branch_bot_on(
    projects: dict[str, Path], project: str
) -> None:
    # The branch bot follows the workflows of the checks that the bots after the
    # checks follow, of every kind of project, but not the release.
    root = ROOT if project == "blueprint" else projects[project]
    flows = root / ".github/workflows"
    after = (flows / "after-checks.yml").read_text(encoding="utf-8")
    update = (flows / "update-branches.yml").read_text(encoding="utf-8")
    assert watched_after_the_checks(update) == watched_after_the_checks(after) - {
        "Release"
    }
    assert ("the blueprint sets them" in update) == (project == "blueprint")


def test_a_beta_of_the_next_release_follows_every_change_for_users() -> None:
    release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    job = release[release.index("  release-please:") : release.index("\n  assets:")]
    assert "vars.BETA_CHANNEL == 'true'" in job
    assert "github.event_name == 'push'" in job
    assert "steps.release.outputs.release_created != 'true'" in job
    # Dependency updates make no beta; the outputs carry a beta like a release.
    assert '"${BASH_REMATCH[3]}" == deps*' in job
    assert "steps.release.outputs.tag_name || steps.beta.outputs.tag" in job
    assert 'gh release create "v$version" --draft --prerelease' in job


# The workflows of the required checks besides the tests, the same in every repository.
OTHER_CHECKS = {
    "CodeQL",
    "Dependency review",
    "Docs",
    "Lint",
    "Pull request title",
    "Secret scan",
}
# The workflows of the scanners of the pull requests that change what they read; the PR
# coach reports them too.
SCANNER_WORKFLOWS = {"Fuzzing", "Links", "OSV-Scanner", "Workflow security"}


def watched_after_the_checks(workflow: str) -> set[str]:
    watched = re.search(r"^    workflows: \[(.+)\]$", workflow, re.MULTILINE)
    assert watched
    return set(watched[1].split(", "))


def after_the_checks_job(name: str) -> str:
    after = (ROOT / ".github/workflows/after-checks.yml").read_text(encoding="utf-8")
    return job_of(after, name)


def test_the_bots_after_the_checks_watch_what_runs_in_the_blueprint() -> None:
    # The checks of every kind of project are only templates here, whose jobs skip.
    after = (ROOT / ".github/workflows/after-checks.yml").read_text(encoding="utf-8")
    assert (
        watched_after_the_checks(after)
        == {
            "CI (python)",
            "Variants",
            "Windows",
            "Release",
            "Issue assistant sync",
            "Downstream",
        }
        | OTHER_CHECKS
        | SCANNER_WORKFLOWS
    )
    assert "github.event.workflow_run.run_attempt == 1" in after


# The workflows of the pull requests of the blueprint that the bots after the checks
# leave alone: the bots of the pull requests themselves, and the tools that check only
# their own set-up, in the pull requests that change it.
UNWATCHED = {
    "Area labels",
    "Update branches",
    "Dependabot maintenance",
    "Issue lifecycle",
    "Welcome",
    "Mutation",
    "Renovate",
}


def test_the_pr_coach_follows_the_checks_of_a_pull_request_of_the_blueprint() -> None:
    folder = ROOT / ".github/workflows"
    watched = watched_after_the_checks(
        (folder / "after-checks.yml").read_text(encoding="utf-8")
    )
    names = set()
    for path in folder.glob("*.yml"):
        text = path.read_text(encoding="utf-8")
        name = re.search(r"^name: (.+)$", text, re.M)
        assert name, path
        names.add(name[1])
        # The checks of the other kinds of project are only templates here.
        template = path.name.startswith("ci-") or path.name == "action-test.yml"
        if template and name[1] != "CI (python)":
            continue
        if re.search(r"^  pull_request(?:_target)?:", text, re.M):
            assert (name[1] in watched) != (name[1] in UNWATCHED), path.name
    assert names >= UNWATCHED


@pytest.mark.parametrize("kind", KINDS)
def test_the_bots_after_the_checks_watch_the_checks_of_the_project(
    projects: dict[str, Path], kind: str
) -> None:
    workflows = projects[kind] / ".github/workflows"
    after = (workflows / "after-checks.yml").read_text(encoding="utf-8")
    watched = watched_after_the_checks(after)
    names = {"Docker E2E"}
    for path in workflows.glob("*.yml"):
        name = re.search(r"^name: (.+)$", path.read_text(encoding="utf-8"), re.M)
        assert name, path
        if path.name in ("ci.yml", "action-test.yml"):
            names.add(name[1])
    assert watched == names | OTHER_CHECKS | SCANNER_WORKFLOWS | {"Release"}
    assert "the blueprint sets them" not in after
    assert not (workflows / "flaky.yml").exists()
    assert not (workflows / "coverage.yml").exists()


def test_the_bots_after_the_checks_watch_the_other_tests_that_a_project_names(
    tmp_path: Path,
) -> None:
    # Visual tests or a bot that renders screenshots flake as the CI does.
    project = render(
        tmp_path,
        project_name="Demo",
        description="A demo.",
        project_type="home-assistant",
        test_workflows=" Visual check,Screenshot bot , ",
    )
    after = (project / ".github/workflows/after-checks.yml").read_text(encoding="utf-8")

    assert (
        "    workflows: [CI (home-assistant), Docker E2E, Visual check, Screenshot bot, CodeQL,"
        in after
    )
    assert (
        watched_after_the_checks(after)
        == {
            "CI (home-assistant)",
            "Docker E2E",
            "Visual check",
            "Screenshot bot",
            "Release",
        }
        | OTHER_CHECKS
        | SCANNER_WORKFLOWS
    )


@pytest.mark.parametrize("names", ["Visual: check", "Visual check]", "Bot # 2", "`x`"])
def test_the_other_tests_of_a_project_are_named_as_their_workflows_are(
    tmp_path: Path, names: str
) -> None:
    # The names go into a list of YAML in the workflow.
    with pytest.raises(ValueError, match="test_workflows"):
        render(
            tmp_path,
            project_name="Demo",
            description="A demo.",
            project_type="generic",
            test_workflows=names,
        )


@pytest.mark.parametrize("project", ["blueprint", *KINDS])
def test_the_bot_for_cancelled_checks_watches_every_required_check(
    projects: dict[str, Path], project: str
) -> None:
    # A late run for an older commit may cancel the run of any of them.
    root = ROOT if project == "blueprint" else projects[project]
    settings = tomllib.loads(
        (root / ".github/repository.toml").read_text(encoding="utf-8")
    )
    required = set(settings["branch"]["required_checks"])
    watched = watched_after_the_checks(
        (root / ".github/workflows/after-checks.yml").read_text(encoding="utf-8")
    )
    providers = set()
    for path in (root / ".github/workflows").glob("*.yml"):
        text = path.read_text(encoding="utf-8")
        if required & set(re.findall(r"^    name: (.+)$", text, re.M)):
            name = re.search(r"^name: (.+)$", text, re.M)
            assert name, path
            providers.add(name[1])
            # Runs of a pull request cancel the older runs of the same one.
            assert "cancel-in-progress:" in text, path
    assert providers >= OTHER_CHECKS
    assert providers <= watched


def test_the_flaky_test_bot_leaves_the_other_required_checks_alone() -> None:
    # Their checks fail the same way again, or, as the changelog, pass once the pull
    # request changed: no flaky test either way. The release has a bot of its own.
    for job in ("rerun", "report"):
        listed = re.search(
            r"!contains\(fromJSON\('(\[.+?\])'\), github\.event\.workflow_run\.name\)",
            after_the_checks_job(job),
        )
        assert listed, job
        assert set(json.loads(listed[1])) == (
            OTHER_CHECKS | SCANNER_WORKFLOWS | {"Release"}
        ), job


def job_alone(workflow: str, key: str) -> str:
    """The text of a job, without the comment that comes before the next job."""
    start = workflow.index(f"\n  {key}:\n")
    end = re.compile(r"\n  [#\w-]").search(workflow, start + 1)
    return workflow[start : end.start() if end else len(workflow)].rstrip("\n") + "\n"


EXPLAIN_COMMENT = (
    "      # The PR coach: what failed, why it matters and how to fix it, in the summary\n"
    "      # of the check and as its annotation, from .github/checks.toml.\n"
)


def explain_step(check: str, python: str = "python3") -> str:
    """The last step of the job of a check: the PR coach explains its failure."""
    value = f'"{check}"' if " " in check else check
    return EXPLAIN_COMMENT + (
        "      - name: Explain the failure\n"
        "        if: failure()\n"
        "        env:\n"
        f"          CHECK: {value}\n"
        "        run: |\n"
        "          script=.github/blueprint.py\n"
        '          [[ -f "$script" ]] || script=blueprint.py\n'
        f'          {python} "$script" coach explain "$CHECK"\n'
    )


PARTS_COMMENT = (
    "      # The PR coach: what failed, why it matters and how to fix it, in the summary\n"
    "      # of the check and as its annotation, from .github/checks.toml: each check\n"
    "      # of the job that failed, or the job itself when none of them did.\n"
)


def explain_parts_step(check: str, failed: list[tuple[str, str]]) -> str:
    """The last step of the job of a check that runs several others: the PR coach
    explains each of them that failed, by its condition and its name."""
    value = f'"{check}"' if " " in check else check
    lines = "".join(
        f"            ${{{{ {condition} && '{name}' || '' }}}}\n"
        for condition, name in failed
    )
    return PARTS_COMMENT + (
        "      - name: Explain the failure\n"
        "        if: failure()\n"
        "        env:\n"
        f"          CHECK: {value}\n"
        "          FAILED: |\n"
        f"{lines}"
        "        run: |\n"
        "          script=.github/blueprint.py\n"
        '          [[ -f "$script" ]] || script=blueprint.py\n'
        '          mapfile -t parts < <(grep . <<<"$FAILED" || true)\n'
        '          python3 "$script" coach explain "$CHECK" --parts "${parts[@]}"\n'
    )


# The checks that the job of each of these checks runs, in the order of its steps.
PARTS = {
    "lint": ["workflow-lint", "reuse", "markdown", "issue-assistant", "dco"],
    "conventional title": ["conventional title", "changelog"],
    "home-assistant": ["hacs", "hassfest"],
}


# Only what the PR coach needs, and only after a failure, for a job that checks out
# nothing else.
COACH_CHECKOUT = re.compile(
    r"      - uses: actions/checkout@[0-9a-f]{40} # v[\d.]+\n"
    r"        if: failure\(\)\n"
    r"        with:\n"
    r"          persist-credentials: false\n"
    r"          sparse-checkout: \|\n"
    r"            \.github\n"
    r"            blueprint\n"
)


@pytest.mark.parametrize("project", ["blueprint", *KINDS])
def test_every_required_check_explains_its_failure(
    projects: dict[str, Path], project: str
) -> None:
    root = ROOT if project == "blueprint" else projects[project]
    settings = tomllib.loads(
        (root / ".github/repository.toml").read_text(encoding="utf-8")
    )
    jobs = {}
    for text in workflows(root).values():
        for key in re.findall(r"^  ([\w-]+):\n    name: ", text, re.M):
            job = job_alone(text, key)
            name = re.search(r"^    name: (.+)$", job, re.M)
            assert name
            jobs[name[1]] = job
    explained = Catalog.load(root)
    for check in settings["branch"]["required_checks"]:
        job = jobs[check]
        # The summary and the annotation of the check say how to fix it, those of a
        # check that runs several others for each of them that failed.
        comment = PARTS_COMMENT if check in PARTS else EXPLAIN_COMMENT
        if check in PARTS:
            failed = re.findall(
                r"^            \$\{\{ (.+) && '([^']+)' \|\| '' \}\}$", job, re.M
            )
            assert [name for _, name in failed] == PARTS[check], check
            assert job.endswith(explain_parts_step(check, failed)), check
            for condition, name in failed:
                assert explained.check(name), name
                # Each step runs also when one before it failed, so that the check
                # reports all of them.
                for step in re.findall(r"steps\.([\w-]+)\.outcome", condition):
                    assert f"        id: {step}\n" in job, step
                    if name != PARTS[check][0]:
                        assert (
                            f"        id: {step}\n        if: ${{{{ !cancelled()" in job
                        )
        else:
            assert job.endswith(explain_step(check)), check
        before = job[: job.index(comment)]
        checkouts = before.count("actions/checkout@")
        coach = COACH_CHECKOUT.findall(before)
        assert checkouts == 1, check
        # A job that checks nothing out gets only what the PR coach needs.
        if coach:
            assert before.endswith(coach[0])
            assert before.index("actions/checkout@") > before.index("run: |")


def test_the_checks_of_a_matrix_explain_each_failure() -> None:
    variants = (ROOT / ".github/workflows/variants.yml").read_text(encoding="utf-8")
    variant = job_alone(variants, "variant")
    name = (
        "${{ matrix.start == 'new' && 'variant' || matrix.start }}"
        " (${{ matrix.answers || matrix.kind }})"
    )
    assert f"    name: {name}\n" in variant
    assert variant.endswith(explain_step(name))
    # The scanners of the pull requests, which aren't required, explain theirs too.
    for workflow, check in (("zizmor", "zizmor"), ("links", "links"), ("fuzz", "fuzz")):
        text = (ROOT / f".github/workflows/{workflow}.yml").read_text(encoding="utf-8")
        assert job_alone(text, check).endswith(explain_step(check)), workflow
    # And the checks on Windows, whose runner has python, not python3.
    windows = (ROOT / ".github/workflows/windows.yml").read_text(encoding="utf-8")
    assert job_alone(windows, "check").endswith(
        explain_step("check (Windows)", "python")
    )


# The checks that a job of several checks replaces. Their own jobs stay for one
# release, so that a pull request passes the rulesets of every repository until the
# settings bot applies the required checks of this release; the next one removes them.
REPLACED = {
    "lint": ["workflow-lint", "reuse", "markdown", "issue-assistant", "dco"],
    "conventional title": ["changelog"],
    "home-assistant": ["hacs", "hassfest"],
}


@pytest.mark.parametrize("project", ["blueprint", *KINDS])
def test_a_job_of_several_checks_replaces_their_jobs_in_the_required_checks(
    projects: dict[str, Path], project: str
) -> None:
    root = ROOT if project == "blueprint" else projects[project]
    settings = tomllib.loads(
        (root / ".github/repository.toml").read_text(encoding="utf-8")
    )
    required = settings["branch"]["required_checks"]
    names = set()
    for workflow in workflows(root).values():
        names |= set(re.findall(r"^    name: (.+)$", workflow, re.M))
    home_assistant = project == "home-assistant"
    for check, replaced in REPLACED.items():
        if check == "home-assistant" and not home_assistant:
            assert check not in required
            continue
        assert check in required, check
        assert not set(replaced) & set(required), check
        # Until the next release, the old jobs report as well.
        assert set(replaced) <= names, check
    assert "prose" not in names


def test_one_job_runs_every_linter_and_reports_each_one() -> None:
    lint = job_alone(
        (ROOT / ".github/workflows/lint.yml").read_text(encoding="utf-8"), "lint"
    )
    steps = re.split(r"\n(?=      - )", lint)
    after = "${{ !cancelled() && steps.checkout.outcome == 'success'"
    for name in (
        "Lint the workflows",
        "Check that every file names its license",
        "Lint the Markdown of every document",
        "Check the issue assistant's set-up",
        "Check the sign-off of every commit",
    ):
        step = next(step for step in steps if f"- name: {name}\n" in step)
        # Each linter runs also when one before it failed, but not without the files.
        assert f"        if: {after}" in step, name
    # REUSE runs its image, pinned to a digest, without the action, which builds an
    # image of its own in every run.
    assert "fsfe/reuse-action" not in lint
    assert re.search(r"REUSE: fsfe/reuse:[\d.]+@sha256:[0-9a-f]{64}\n", lint)
    assert "GIT_CONFIG_KEY_0=safe.directory" in lint
    # The hints at the prose never fail the check.
    for name in ("Find the changed documents", "Hint at the spelling"):
        step = next(step for step in steps if f"- name: {name}" in step)
        assert "        continue-on-error: true\n" in step, name
    setup = next(step for step in steps if "actions/setup-node@" in step)
    assert "        continue-on-error: true\n" in setup
    # Markdownlint fixes the head of the pull request after every other linter, as
    # the fixes of lint, and the PR coach explains last.
    head = lint.index("- name: Check out the head of the pull request for the fixes")
    assert lint.index("- name: Hint at the spelling") < head
    assert "steps.markdown.outcome == 'failure'" in lint[head:]
    assert "          name: fixes-lint\n" in lint
    assert lint.index("          name: fixes-lint\n") < lint.index(PARTS_COMMENT)
    # The sign-off and the changed documents need the history.
    assert "          fetch-depth: 0\n" in lint


def test_the_check_of_the_title_checks_the_changelog_as_well() -> None:
    workflow = (ROOT / ".github/workflows/pull-request-title.yml").read_text(
        encoding="utf-8"
    )
    title = job_alone(workflow, "title")
    assert (
        "      - name: Require an entry in the changelog for a change for users\n"
        in (title)
    )
    assert "        id: entry\n        if: ${{ !cancelled() }}\n" in title
    assert "        id: fragments\n        if: ${{ !cancelled() &&" in title
    # It reads the files of the pull request through the API and sets its labels.
    assert "      pull-requests: write\n" in title
    # The job changelog only reports for the rulesets that still require it: it
    # checks nothing out and runs nothing of the pull request.
    changelog = job_alone(workflow, "changelog")
    assert "actions/checkout@" not in changelog
    assert "GH_TOKEN" not in changelog
    assert changelog.count("      - name: ") == 2


@pytest.mark.parametrize("kind", KINDS)
def test_one_job_runs_codeql_for_every_language(
    projects: dict[str, Path], kind: str
) -> None:
    codeql = (projects[kind] / ".github/workflows/codeql.yml").read_text(
        encoding="utf-8"
    )
    languages = re.findall(r"^          languages: (.+)$", codeql, re.M)
    expected = {
        "python-package": "python, actions",
        "home-assistant": "python, actions",
        "node-package": "javascript-typescript, actions",
        "github-action": "python, actions",
    }
    assert languages == [expected.get(kind, "actions")]
    assert "matrix" not in codeql
    assert re.findall(r"^  ([\w-]+):\n    name: (.+)$", codeql, re.M) == [
        ("codeql", "codeql")
    ]
    # Each language keeps the category of its analysis, under which code scanning
    # keeps its alerts, and the results go up once, after every analysis.
    assert "          upload: never\n" in codeql
    assert """'.runs[].automationDetails = {id: $id}'""" in codeql
    assert '--arg id "/language:$language/"' in codeql
    pins = set(re.findall(r"uses: github/codeql-action/\w+(@\w+)", codeql))
    assert len(pins) == 1
    assert codeql.index("upload-sarif@") > codeql.index("analyze@")


def test_the_pr_coach_reads_the_checks_and_runs_no_code_of_the_pull_request() -> None:
    job = after_the_checks_job("coach")
    assert "    name: PR coach\n" in job
    assert condition_of(job) == (
        "!github.event.repository.fork && "
        """contains(fromJSON('["pull_request", "pull_request_target"]'), github.event.workflow_run.event)"""
    )
    # One report at a time for each commit, the newest last, and none cancelled.
    assert (
        "      group: ${{ github.workflow }}-coach-${{ github.event.workflow_run.head_sha }}\n"
        "      cancel-in-progress: false\n"
    ) in job
    permissions = job[job.index("    permissions:\n") : job.index("    steps:\n")]
    assert permissions.splitlines()[1:] == [
        "      actions: read # the coverage reports and the website that the checks kept",
        "      checks: read",
        "      contents: read",
        "      pull-requests: write",
    ]
    # The default branch, which the run is of, and only blueprint.py with the
    # explanations; nothing of the pull request.
    checkout = job[job.index("actions/checkout@") : job.index("      - name: Fetch")]
    assert "ref:" not in checkout
    assert "persist-credentials: false" in checkout
    assert (
        "sparse-checkout: |\n            .github\n            blueprint\n" in checkout
    )
    # The values of the event reach the script as variables only.
    fetch = script_of(job, "Fetch the coverage reports of the head and of main")
    script = script_of(job, "Keep the one report of the PR coach up to date")
    assert "${{" not in fetch + script
    assert '--repo "$GH_REPO" coach report "$SHA" --pull "$NUMBER"' in script
    # The coverage is fetched in every run, also one that a bot started: the bots push
    # to pull requests of people too (update branches, the fix bot, the diagram bot).
    step = job[job.index("      - name: Fetch the coverage") :]
    assert "if:" not in step[: step.index("        run: |")]
    assert "actor.type" not in job
    assert "SHA: ${{ github.event.workflow_run.head_sha }}" in job
    assert "NUMBER: ${{ github.event.workflow_run.pull_requests[0].number }}" in job


@pytest.mark.parametrize("kind", KINDS)
def test_every_project_gets_the_pr_coach(projects: dict[str, Path], kind: str) -> None:
    project = projects[kind]
    github = project / ".github"
    assert (github / "checks.toml").read_text(encoding="utf-8") == (
        ROOT / ".github/checks.toml"
    ).read_text(encoding="utf-8")
    # The explanations of the project's own checks: only an example to start from.
    own = (github / "checks.project.toml").read_text(encoding="utf-8")
    assert tomllib.loads(own) == {}
    assert '# [check."e2e (*)"]' in own
    # Every required check and every step of its checks is explained, and each link
    # leads to a section of its contributing guide.
    explained = Catalog.load(project)
    required = tomllib.loads((github / "repository.toml").read_text(encoding="utf-8"))
    checks = required["branch"]["required_checks"]
    check = (project / "scripts/check.sh").read_text(encoding="utf-8")
    steps = re.findall(r'^step "(.+)"$', check, re.M)
    assert missing(explained, checks, steps) == []
    contributing = (project / "CONTRIBUTING.md").read_text(encoding="utf-8")
    anchors = {
        re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
        for heading in re.findall(r"^#+ (.+)$", contributing, re.M)
    }
    assert "when-a-check-fails" in anchors
    used = [explained.check(name) for name in checks]
    used += [explained.step(name) for name in steps]
    for entry in used:
        assert entry
        if entry.docs.startswith("CONTRIBUTING.md#"):
            assert entry.docs.removeprefix("CONTRIBUTING.md#") in anchors, entry.key
    # A step that fails is explained; nothing else sets the trap of the script.
    assert check.count("\ntrap coach EXIT\n") == 1
    assert re.findall(r"^trap ", check, re.M) == ["trap "]


# What each kind of project fixes by a command when its checks fail, besides the text
# files and the pages of every kind.
FIXED_STEPS = {
    "python": ["Ruff"],
    "github-action": ["Ruff"],
    "home-assistant": ["Ruff"],
    "php": ["Coding standard"],
    "node": ["Lint and format"],
    "container": [],
    "generic": [],
}


@pytest.mark.parametrize("kind", KINDS)
def test_every_project_fixes_what_a_command_can_fix(
    projects: dict[str, Path], kind: str
) -> None:
    project = projects[kind]
    github = project / ".github"
    # The tool of the fix bot, as the blueprint has it.
    assert (github / "blueprint/fixes.py").read_text(encoding="utf-8") == (
        ROOT / "blueprint/fixes.py"
    ).read_text(encoding="utf-8")
    # Every explanation says how it fixes itself, or why it can't.
    explained = Catalog.load(project)
    assert undeclared(explained) == []
    # The check of the project runs the commands of its steps when it fails, on the
    # head of the pull request, and keeps what they fixed before it explains itself.
    ci = (github / "workflows/ci.yml").read_text(encoding="utf-8")
    check = job_alone(ci, "check")
    name = re.search(r"^    name: (check \(.+\))$", check, re.M)
    assert name
    stack = name[1].removeprefix("check (").removesuffix(")")
    assert "          fetch-depth: 2\n" in check
    fix = check.index("      - name: Fix what a command can fix\n")
    keep = check.index("      - name: Keep the fixes for the fix bot\n")
    assert fix < keep < check.index("      - name: Explain the failure\n")
    assert f'          CHECK: "{name[1]}"\n' in check[fix:keep]
    steps = [step for step, _ in fixers(explained, project, name[1])]
    expected = ["Text files", "Pages in one column", *FIXED_STEPS.get(stack, [])]
    assert list(dict.fromkeys(steps)) == expected, stack
    # Lint keeps what markdownlint fixed, and the fix bot after the checks takes the
    # fixes of both, with the CI of this kind among the workflows that it follows.
    lint = (github / "workflows/lint.yml").read_text(encoding="utf-8")
    assert "          name: fixes-markdown\n" in job_alone(lint, "markdown")
    after = (github / "workflows/after-checks.yml").read_text(encoding="utf-8")
    assert {name[1].replace("check", "CI"), "Lint"} <= watched_after_the_checks(after)
    bot = job_alone(after, "fixes")
    assert "startsWith(github.event.workflow_run.name, 'CI (')" in bot
    assert "Dennis-Otto" not in bot


def test_every_explanation_belongs_to_a_check_or_a_step(
    projects: dict[str, Path],
) -> None:
    # Of a job of a workflow, of a step of scripts/check.sh of some kind of project,
    # or of CodeQL, the check of GitHub's code scanning, which no workflow names.
    names = {"CodeQL"}
    steps = set()
    for root in (ROOT, *projects.values()):
        for text in workflows(root).values():
            names.update(re.findall(r"^    name: (.+)$", text, re.M))
        check = (root / "scripts/check.sh").read_text(encoding="utf-8")
        steps.update(re.findall(r'^ *step "(.+)"$', check, re.M))
    # A name of a matrix, with its expressions, stands for every name it can be.
    matrix = [
        re.compile(".+".join(map(re.escape, re.split(r"\$\{\{.+?\}\}", name))))
        for name in names
        if "${{" in name
    ]
    explained = Catalog.load(ROOT)
    for key in explained.checks:
        sample = key.replace("*", "x")
        assert any(fnmatch.fnmatchcase(name, key) for name in names) or any(
            pattern.fullmatch(sample) for pattern in matrix
        ), key
    assert set(explained.steps) <= steps, set(explained.steps) - steps


# In the copy of the mutation tests, the tool is the code with the mutants.
@pytest.mark.mutation_unsafe
@pytest.mark.parametrize("kind", KINDS)
def test_the_pr_coach_runs_in_every_repository(
    projects: dict[str, Path], kind: str, tmp_path: Path
) -> None:
    # On a copy and without the folder for bytecode of the run, as the settings tool.
    project = shutil.copytree(projects[kind], tmp_path / kind)

    def coach(*arguments: str) -> subprocess.CompletedProcess[str]:
        environment = {
            name: value
            for name, value in without_bytecode_prefix(os.environ).items()
            if not name.startswith("GITHUB_")
        }
        return subprocess.run(
            [sys.executable, ".github/blueprint.py", "coach", *arguments],
            cwd=project,
            capture_output=True,
            encoding="utf-8",
            env=environment,
            check=False,
        )

    verified = coach("verify")
    assert verified.returncode == 0, verified.stderr
    explained = coach("explain", "--step", "Text files")
    assert explained.returncode == 0, explained.stderr
    assert explained.stdout.startswith("PR coach: Text files (scripts/check.sh)\n")
    assert not (project / ".github/blueprint/__pycache__").exists()


def test_the_bot_for_cancelled_checks_only_starts_the_runs_of_the_head_again() -> None:
    cancelled = workflow_steps.job("after-checks.yml", "cancelled")
    assert "github.event.workflow_run.conclusion == 'cancelled'" in cancelled["if"]
    events = """contains(fromJSON('["pull_request", "pull_request_target"]'), github.event.workflow_run.event)"""
    assert events in cancelled["if"]
    # Twice at most, whatever cancels the run again.
    assert "github.event.workflow_run.run_attempt < 3" in cancelled["if"]
    # It reads the runs, their checks and pull requests and starts a run again; it
    # checks out nothing.
    assert cancelled["permissions"] == {
        "actions": "write",
        "checks": "read",
        "pull-requests": "read",
    }
    steps = cancelled["steps"]
    assert not any("actions/checkout" in found.get("uses", "") for found in steps)
    # Every job of the run starts again, so that each of its checks reports.
    script = workflow_steps.step("after-checks.yml", "cancelled", CANCELLED_STEP)["run"]
    assert 'gh run rerun "$RUN"\n' in script
    assert "--failed" not in script
    # The values of the event reach the scripts as variables only.
    assert not any("${{" in found.get("run", "") for found in steps)


CANCELLED_STEP = "Run the checks of the head of the pull request again"


def run_the_bot_for_cancelled_checks(
    tmp_path: Path, pull: str, newer: str, message: str
) -> tuple[list[str], str]:
    # gh answers as the API does, after the filters of jq.
    done = workflow_steps.run_step(
        tmp_path,
        "after-checks.yml",
        "cancelled",
        CANCELLED_STEP,
        answers=[
            Answer(r"api repos/o/r/commits/abc1234def/pulls --jq .+", f"{pull}\n"),
            Answer(
                r"api repos/o/r/actions/workflows/3/runs\?head_sha=abc1234def"
                r" --paginate --jq .+",
                f"{newer}\n",
            ),
            Answer(
                r"api repos/o/r/actions/runs/5/attempts/1/jobs --paginate --jq .+",
                "11\n12\n",
            ),
            Answer(
                r"api repos/o/r/check-runs/1[12]/annotations --paginate"
                r" --jq \.\[\]\.message",
                f"{message}\n",
            ),
            exact("run rerun 5"),
        ],
        env={
            "RUN": "5",
            "ATTEMPT": "1",
            "WORKFLOW": "3",
            "NAME": "CodeQL",
            "SHA": "abc1234def",
        },
    )
    assert done.returncode == 0, done.stderr
    return done.commands, done.summary


RACED = "Canceling since a higher priority waiting request for CodeQL-136 exists"


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize(
    ("pull", "newer", "message", "summary"),
    [
        # A newer push replaced the commit, or the pull request is closed.
        ("", "", RACED, "abc1234 is not the head of an open pull request"),
        # Another run of the same commit, such as one of an edited title, reports.
        ("136", "7", RACED, "A newer run of CodeQL for abc1234 reports"),
        # A person cancelled it.
        ("136", "", "The operation was canceled.", "it stays cancelled"),
        # A late run for an older commit cancelled the run for the head.
        ("136", "", RACED, "the head of #136; it runs again"),
    ],
)
def test_the_bot_for_cancelled_checks_starts_only_a_run_that_lost_a_race(
    tmp_path: Path, pull: str, newer: str, message: str, summary: str
) -> None:
    calls, written = run_the_bot_for_cancelled_checks(tmp_path, pull, newer, message)

    assert summary in written
    assert ("run rerun 5" in calls) == summary.endswith("it runs again")


# The bots of the blueprint alone, which a project's bot-health bot leaves out.
BLUEPRINT_BOTS = {
    "Dashboard",
    "Docs pictures",
    "Issue assistant sync",
    "Renovate",
    "Rollout",
    "Weekly report",
}


def names_of_workflows(root: Path) -> dict[str, str]:
    """The workflows of a repository by their names."""
    named = {}
    for text in workflows(root).values():
        name = re.search(r"^name: (.+)$", text, re.MULTILINE)
        assert name
        named[name[1]] = text
    return named


def watched_by_bot_health(root: Path) -> set[str]:
    text = (root / ".github/workflows/bot-health.yml").read_text(encoding="utf-8")
    watched = re.search(r"^    workflows: \[(.+)\]$", text, re.MULTILINE)
    assert watched
    return set(watched[1].split(", "))


@pytest.mark.parametrize("project", ["blueprint", *KINDS])
def test_the_bot_health_bot_watches_every_bot(
    projects: dict[str, Path], project: str
) -> None:
    root = ROOT if project == "blueprint" else projects[project]
    watched = watched_by_bot_health(root)

    # Each is the name of a workflow of the blueprint: a typo would watch nothing.
    assert watched <= set(names_of_workflows(ROOT))
    if project == "blueprint":
        assert watched >= BLUEPRINT_BOTS
    else:
        assert not watched & BLUEPRINT_BOTS
    # Every workflow on a schedule that pull requests don't run, whose every run is
    # one of the default branch; Diagrams, Newest Python and the Next runner keep an
    # issue of their own.
    for name, text in names_of_workflows(root).items():
        events = set(triggers(text))
        if "schedule" in events and not events & {
            "pull_request",
            "pull_request_target",
        }:
            assert name in watched | OWN_ISSUE | {"Bot health"}, name
    # Not the checks of pull requests, each of whose runs would start a run of the
    # bot that skips: the daily look covers their runs on the default branch.
    assert not watched & OTHER_CHECKS
    assert "Bot health" not in watched


@pytest.mark.parametrize("project", ["blueprint", *KINDS])
def test_the_bot_health_bot_counts_no_run_after_the_checks_of_a_pull_request(
    projects: dict[str, Path], project: str
) -> None:
    # GitHub gives a run that the end of a check of a pull request starts the default
    # branch and its latest commit. A watched workflow that such an end starts, as
    # CodeQL starts Findings, skips those runs in each of its jobs, so that they end
    # skipped; the daily look counts only the other runs of such a workflow.
    root = ROOT if project == "blueprint" else projects[project]
    named = names_of_workflows(root)
    after_checks = after_pull_requests(named.items())
    assert {"After the checks", "Findings"} <= after_checks
    # The branch bot is the one that acts on such an end: a failed check of a pull
    # request moves its line on, which is a run of the bot on the default branch like
    # any other, and one that fails is a failure of the bot.
    assert "Update branches" in after_checks
    for name in watched_by_bot_health(root) & after_checks - {"Update branches"}:
        text = named[name]
        for job in re.findall(r"^  ([\w-]+):$", text.split("\njobs:\n", 1)[1], re.M):
            condition = condition_of(job_of(text, job))
            assert (
                "github.event.workflow_run.head_branch == "
                "github.event.repository.default_branch" in condition
            ), (name, job)


def test_the_bot_health_bot_acts_on_runs_of_the_default_branch_only() -> None:
    text = (ROOT / ".github/workflows/bot-health.yml").read_text(encoding="utf-8")
    assert set(triggers(text)) == {"workflow_run", "schedule", "workflow_dispatch"}
    run = job_of(text, "run")
    condition = condition_of(run)
    for part in (
        "github.event_name == 'workflow_run'",
        "!github.event.repository.fork",
        "github.event.workflow_run.head_branch == github.event.repository.default_branch",
        "github.event.workflow_run.head_repository.full_name == github.repository",
        '!contains(fromJSON(\'["pull_request", "pull_request_target"]\'), '
        "github.event.workflow_run.event)",
    ):
        assert part in condition, part
    ends = re.search(
        r"contains\(fromJSON\('(\[[^\]]+\])'\), github\.event\.workflow_run\.conclusion\)",
        condition,
    )
    assert ends
    assert set(json.loads(ends[1])) == FAILED | {"success"}
    assert "github.event_name != 'workflow_run'" in condition_of(job_of(text, "sweep"))
    # One run at a time per workflow, set on the job: a run that skips, for a pull
    # request, never replaces the waiting one for the default branch.
    assert "\nconcurrency:" not in text
    assert (
        "group: ${{ github.workflow }}-${{ github.event.workflow_run.workflow_id }}"
        in run
    )
    for name in ("run", "sweep"):
        job = job_of(text, name)
        # The default branch, without the token in the checkout.
        assert "persist-credentials: false" in job, name
        assert "ref:" not in job, name
        assert "bot-health" in job, name
        assert "issues: write" in job, name
    zizmor = (ROOT / ".github/zizmor.yml").read_text(encoding="utf-8")
    dangerous = zizmor.split("  dangerous-triggers:", 1)[1].split("\n  self-", 1)[0]
    assert "      - bot-health.yml\n" in dangerous


@pytest.mark.parametrize("project", ["blueprint", *KINDS])
def test_every_repository_has_the_labels_of_the_bot_health_bot(
    projects: dict[str, Path], project: str
) -> None:
    root = ROOT if project == "blueprint" else projects[project]
    text = (root / ".github/labels.toml").read_text(encoding="utf-8")
    labels = {label["name"]: label for label in tomllib.loads(text)["label"]}

    assert {TYPE, RENOVATE_LABEL} <= set(labels)
    # The bot creates the label where a repository's own labels.toml lacks it.
    assert labels[LABEL]["color"] == LABEL_COLOR
    assert labels[LABEL]["description"] == LABEL_DESCRIPTION


def test_renovate_reports_its_problems_in_one_issue() -> None:
    text = (ROOT / ".github/workflows/renovate.yml").read_text(encoding="utf-8")
    job = job_of(text, "renovate")
    log = re.search(r"RENOVATE_LOG_FILE: (\S+)", job)
    # Renovate reads the path in lower case, and the action shares /tmp with it.
    assert log
    assert log[1].startswith("/tmp/")
    assert log[1] == log[1].lower()
    assert "RENOVATE_LOG_FILE_LEVEL: warn" in job
    step = "Keep the issue of Renovate's problems current"
    assert job.index(f"- name: {step}") > job.index("- name: Run Renovate")
    assert f"bot-health renovate {log[1]} " in script_of(text, step)
    assert "if: ${{ !cancelled() }}" in job.split(f"- name: {step}", 1)[1]
    assert "issues: write" in job


# jq, which gh runs for its option --jq: the steps that rely on its filters run with
# it, on Linux and wherever else it is installed.
JQ = shutil.which("jq")
WITH_JQ = pytest.mark.skipif(
    BASH is None or JQ is None, reason="the step runs in bash, with the jq of gh"
)
# The answers of gh: an API call by its path, any other command by its first two
# words, each through jq as gh does. The jq of gh ends its lines with LF on every
# system, the jq of Windows with CRLF. What it is given to write, it keeps by the
# words of its command, and the input of an API call as input. An answer with the
# suffix .error is the error of gh, which fails.
FAKE_GH = """#!/usr/bin/env bash
echo "$*" >> "$CALLS"
filter=""
if [[ "$1" == api ]]; then
  key=""
  shift
  while (($#)); do
    case "$1" in
      --jq) filter="$2"; shift 2 ;;
      --input) cat -- "$2" >> "$WRITTEN/input"; shift 2 ;;
      --method | -f | -F | -H) shift 2 ;;
      --paginate | --silent) shift ;;
      *) key="$1"; shift ;;
    esac
  done
else
  key="$1 $2"
  shift 2
  while (($#)); do
    case "$1" in
      --jq) filter="$2"; shift 2 ;;
      --body) printf '%s' "$2" > "$WRITTEN/${key// /-}"; shift 2 ;;
      --body-file) cp "$2" "$WRITTEN/${key// /-}"; shift 2 ;;
      --state | --search | --json | --title | --label) shift 2 ;;
      *) shift ;;
    esac
  done
fi
answer="$ANSWERS/$(tr '/ ?' '___' <<<"$key")"
if [[ -f "$answer.error" ]]; then
  cat "$answer.error" >&2
  exit 1
fi
if [[ ! -f "$answer" ]]; then
  case "$key" in
    "run rerun" | "issue comment" | "issue create") exit 0 ;;
  esac
  echo "gh has no answer for $key" >&2
  exit 1
fi
if [[ -n "$filter" ]]; then
  jq -r "$filter" "$answer" | tr -d '\\r'
else
  cat "$answer"
fi
"""
TIMED_OUT = "The job has exceeded the maximum execution time of 30m0s"
CANCELLED = "The operation was canceled."
EXITED = "Process completed with exit code 1."


@WITH_JQ
def test_codeql_files_the_results_of_each_language_under_its_category(
    tmp_path: Path,
) -> None:
    workflow = (ROOT / ".github/workflows/codeql.yml").read_text(encoding="utf-8")
    (tmp_path / "step.sh").write_text(
        script_of(workflow, "File the results of each language under its own category"),
        encoding="utf-8",
        newline="\n",
    )
    results = tmp_path / "codeql"
    results.mkdir()
    for language in ("python", "actions", "javascript", "java", "cpp"):
        (results / f"{language}.sarif").write_text(
            json.dumps({"runs": [{"tool": {"driver": {"name": "CodeQL"}}}]}),
            encoding="utf-8",
        )
    summary = tmp_path / "summary.md"
    environment = {
        **os.environ,
        "RUNNER_TEMP": str(tmp_path),
        "GITHUB_STEP_SUMMARY": str(summary),
    }
    assert BASH
    done = subprocess.run(
        [BASH, "-e", str(tmp_path / "step.sh")],
        env=environment,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )

    assert done.returncode == 0, done.stderr
    # The extractor names map back to the configured names, the old categories.
    for extractor, language in (
        ("python", "python"),
        ("actions", "actions"),
        ("javascript", "javascript-typescript"),
        ("java", "java-kotlin"),
        ("cpp", "c-cpp"),
    ):
        sarif = json.loads((results / f"{extractor}.sarif").read_text(encoding="utf-8"))
        assert sarif["runs"][0]["automationDetails"] == {"id": f"/language:{language}/"}
    assert "- python: `/language:python`" in summary.read_text(encoding="utf-8")
    assert (
        "- javascript-typescript: `/language:javascript-typescript`"
        in summary.read_text(encoding="utf-8")
    )

    # Without results, the step fails rather than uploading nothing.
    for found in results.iterdir():
        found.unlink()
    done = subprocess.run(
        [BASH, "-e", str(tmp_path / "step.sh")],
        env=environment,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    assert done.returncode == 1
    assert "::error::CodeQL wrote no results." in done.stdout


def run_a_bot_after_the_checks(
    tmp_path: Path,
    job: str,
    step: str,
    answers: dict[str, object],
    stubs: dict[str, str] | None = None,
    **variables: str,
) -> tuple[list[str], str, dict[str, str]]:
    """Runs a step of a bot after the checks, as GitHub does, with the fake gh and these
    stubs of other commands; returns the calls of gh, the summary of the step and what
    gh was given to write."""
    (tmp_path / "step.sh").write_text(
        script_of(after_the_checks_job(job), step), encoding="utf-8", newline="\n"
    )
    folders = {name: tmp_path / name for name in ("bin", "answers", "written")}
    for folder in folders.values():
        folder.mkdir()
    for key, answer in answers.items():
        (folders["answers"] / re.sub(r"[/ ?]", "_", key)).write_text(
            answer if isinstance(answer, str) else json.dumps(answer),
            encoding="utf-8",
            newline="\n",
        )
    for name, text in {"gh": FAKE_GH, **(stubs or {})}.items():
        (folders["bin"] / name).write_text(text, encoding="utf-8", newline="\n")
        (folders["bin"] / name).chmod(0o755)
    calls = tmp_path / "calls"
    summary = tmp_path / "summary"
    calls.touch()
    summary.touch()
    environment = {
        **os.environ,
        "PATH": f"{folders['bin']}{os.pathsep}{os.environ['PATH']}",
        "GH_REPO": "o/r",
        "RUN": "5",
        "NAME": "CI (python)",
        "BRANCH": "feature",
        "HEAD_REPO": "o/r",
        "SHA": "abc1234def",
        "RUNNER_TEMP": str(tmp_path),
        "GITHUB_STEP_SUMMARY": str(summary),
        "CALLS": str(calls),
        "ANSWERS": str(folders["answers"]),
        "WRITTEN": str(folders["written"]),
        **variables,
    }
    assert BASH
    result = subprocess.run(
        [BASH, "-e", "step.sh"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    written = {
        path.name: path.read_text(encoding="utf-8")
        for path in folders["written"].iterdir()
    }
    return (
        calls.read_text(encoding="utf-8").splitlines(),
        summary.read_text(encoding="utf-8"),
        written,
    )


def job_of_a_run(
    number: int, name: str, conclusion: str, *steps: tuple[str, str]
) -> dict[str, object]:
    """A job as the API of the workflow runs answers it."""
    return {
        "id": number,
        "name": name,
        "conclusion": conclusion,
        "html_url": f"https://github.com/o/r/actions/runs/5/job/{number}",
        "steps": [{"name": step, "conclusion": result} for step, result in steps],
    }


def annotations_of_a_job(*messages: str) -> list[dict[str, str]]:
    """The annotations of a job: its failures, and a notice of the runner."""
    return [
        *({"annotation_level": "failure", "message": message} for message in messages),
        {"annotation_level": "notice", "message": "The ubuntu-latest label moves on."},
    ]


def runs_of_the_branch(*before: int, conclusion: str = "failure") -> dict[str, object]:
    """The completed runs of the workflow for the branch, the newest first: a later one,
    the run itself, another run of its commit, one of a fork's branch of the same name,
    and those for the commits before, which ended with the conclusion."""

    def run(
        number: int, sha: str, repository: str = "o/r", end: str = "success"
    ) -> dict[str, object]:
        return {
            "id": number,
            "head_sha": sha,
            "head_repository": {"full_name": repository},
            "conclusion": end,
        }

    return {
        "workflow_runs": [
            run(6, "fedcba9"),
            run(5, "abc1234def"),
            run(4, "abc1234def"),
            run(3, "1111111", "fork/r"),
            *(run(number, f"{number:07}", end=conclusion) for number in before),
        ]
    }


def test_the_flaky_test_bot_takes_runs_that_failed_or_ran_out_of_time() -> None:
    job = after_the_checks_job("rerun")
    condition = condition_of(job)
    assert "github.event.workflow_run.run_attempt == 1" in condition
    assert (
        """contains(fromJSON('["failure", "cancelled"]'), github.event.workflow_run.conclusion)"""
        in condition
    )
    # It reads the jobs of the runs and their annotations, and starts the failed jobs
    # again; it checks out nothing.
    permissions = job[job.index("    permissions:\n") : job.index("    steps:\n")]
    assert permissions.splitlines()[1:] == [
        "      actions: write",
        "      checks: read",
    ]
    assert "actions/checkout" not in job
    # The values of the event reach the script as variables only.
    assert "${{" not in job[job.index("        run: |\n") :]


@WITH_JQ
@pytest.mark.parametrize(
    ("first", "messages", "before", "again"),
    [
        # A test failed at first.
        ("failure", [EXITED], None, True),
        # A job ran out of time: GitHub cancelled it at its time limit.
        ("cancelled", [TIMED_OUT, CANCELLED], None, True),
        # A newer run cancelled it: the bot for cancelled checks sees to it.
        ("cancelled", [RACED], None, False),
        # A person cancelled it.
        ("cancelled", [CANCELLED], None, False),
        # The run for the commit before ended with the same failure: a real one.
        ("failure", [EXITED], ("failure", [EXITED]), False),
        ("cancelled", [TIMED_OUT], ("cancelled", [TIMED_OUT]), False),
        # A newer push cancelled the run for the commit before, or it passed.
        ("failure", [EXITED], ("cancelled", [RACED]), True),
        ("failure", [EXITED], ("success", []), True),
    ],
)
def test_the_flaky_test_bot_runs_the_failed_jobs_once_more(
    tmp_path: Path,
    first: str,
    messages: list[str],
    before: tuple[str, list[str]] | None,
    again: bool,
) -> None:
    answers: dict[str, object] = {
        "repos/o/r/actions/runs/5/attempts/1/jobs": {
            "jobs": [
                job_of_a_run(11, "test (3.12)", first),
                job_of_a_run(12, "test (3.13)", "success"),
            ]
        },
        "repos/o/r/check-runs/11/annotations": annotations_of_a_job(*messages),
        "repos/o/r/actions/workflows/3/runs": runs_of_the_branch(
            *([2] if before else []), conclusion=before[0] if before else "failure"
        ),
    }
    if before:
        conclusion, earlier = before
        answers["repos/o/r/actions/runs/2/jobs"] = {
            "jobs": [
                job_of_a_run(21, "test (3.12)", conclusion),
                job_of_a_run(22, "test (3.13)", "success"),
            ]
        }
        answers["repos/o/r/check-runs/21/annotations"] = annotations_of_a_job(*earlier)

    calls, summary, _ = run_a_bot_after_the_checks(
        tmp_path,
        "rerun",
        "Run the failed jobs once more",
        answers,
        CONCLUSION=first,
        WORKFLOW="3",
        EVENT="pull_request",
        HEAD_REPO="o/r",
    )

    assert ("run rerun 5 --failed" in calls) == again
    if before:
        # The run for the commit before, on the same branch of the same repository.
        assert any(
            call.startswith("api repos/o/r/actions/runs/2/jobs ") for call in calls
        )
        assert not any(
            "actions/runs/3/" in call or "actions/runs/4/" in call for call in calls
        )
        assert ("broke for the commit before" in summary) != again


@WITH_JQ
def test_the_flaky_test_bot_runs_a_job_once_more_that_broke_for_the_first_time(
    tmp_path: Path,
) -> None:
    # The commit before broke one of the two jobs: the other may be flaky.
    answers: dict[str, object] = {
        "repos/o/r/actions/runs/5/attempts/1/jobs": {
            "jobs": [
                job_of_a_run(11, "test (3.12)", "failure"),
                job_of_a_run(12, "test (3.13)", "failure"),
            ]
        },
        "repos/o/r/actions/workflows/3/runs": runs_of_the_branch(2, 1),
        "repos/o/r/actions/runs/2/jobs": {
            "jobs": [
                job_of_a_run(21, "test (3.12)", "failure"),
                job_of_a_run(22, "test (3.13)", "success"),
            ]
        },
    }

    calls, _, _ = run_a_bot_after_the_checks(
        tmp_path,
        "rerun",
        "Run the failed jobs once more",
        answers,
        CONCLUSION="failure",
        WORKFLOW="3",
        EVENT="push",
        BRANCH="main",
        HEAD_REPO="o/r",
    )

    assert "run rerun 5 --failed" in calls
    runs = next(call for call in calls if "/workflows/3/runs" in call)
    assert runs.startswith(
        "api --method GET repos/o/r/actions/workflows/3/runs -f branch=main -f event=push -f status=completed "
    )
    # Only the latest run before counts.
    assert not any("actions/runs/1/" in call for call in calls)


def variants_of_a_run(
    jobs: str, leg: str, messages: tuple[str, ...], first: int
) -> dict[str, object]:
    """The jobs of a run of Variants that was cancelled, such as run 38396054999, whose
    legs a newer run cancelled: a leg that ended as given, one that was cancelled with
    the messages, and the job that waits for the legs, which failed because they did
    not pass."""
    answers: dict[str, object] = {
        jobs: {
            "jobs": [
                job_of_a_run(first, "variant (generic)", leg),
                job_of_a_run(first + 1, "update (generic)", "cancelled"),
                job_of_a_run(first + 2, "variants", "failure", ("Check", "failure")),
            ]
        },
        f"repos/o/r/check-runs/{first + 1}/annotations": annotations_of_a_job(
            *messages
        ),
        f"repos/o/r/check-runs/{first + 2}/annotations": annotations_of_a_job(EXITED),
    }
    if leg == "cancelled":
        answers[f"repos/o/r/check-runs/{first}/annotations"] = annotations_of_a_job(
            *messages
        )
    return answers


@WITH_JQ
@pytest.mark.parametrize(
    ("leg", "messages", "again"),
    [
        # A newer run cancelled it, after a leg had failed or before.
        ("cancelled", (RACED, CANCELLED), False),
        ("failure", (RACED, CANCELLED), False),
        # A person cancelled it.
        ("cancelled", (CANCELLED,), False),
        ("failure", (CANCELLED,), False),
        # A leg ran out of time.
        ("success", (TIMED_OUT, CANCELLED), True),
    ],
)
def test_the_flaky_test_bot_runs_a_cancelled_run_again_only_when_it_ran_out_of_time(
    tmp_path: Path, leg: str, messages: tuple[str, ...], again: bool
) -> None:
    # The job that waits for the legs failed only because they were cancelled; run
    # again, the run for an older commit would cancel the one for the head.
    calls, summary, _ = run_a_bot_after_the_checks(
        tmp_path,
        "rerun",
        "Run the failed jobs once more",
        {
            **variants_of_a_run(
                "repos/o/r/actions/runs/5/attempts/1/jobs", leg, messages, 11
            ),
            "repos/o/r/actions/workflows/3/runs": runs_of_the_branch(),
        },
        NAME="Variants",
        CONCLUSION="cancelled",
        WORKFLOW="3",
        EVENT="pull_request",
        HEAD_REPO="o/r",
    )

    assert ("run rerun 5 --failed" in calls) == again
    assert ("a newer run or a person cancelled it" in summary) != again


@WITH_JQ
@pytest.mark.parametrize(
    ("conclusion", "messages", "again"),
    [
        # A newer push cancelled the run for the commit before, after a leg had failed.
        ("cancelled", (RACED, CANCELLED), True),
        # A person cancelled it.
        ("cancelled", (CANCELLED,), True),
        # It failed: the same jobs broke.
        ("failure", (CANCELLED,), False),
    ],
)
def test_the_flaky_test_bot_counts_no_failure_of_a_cancelled_run_before(
    tmp_path: Path, conclusion: str, messages: tuple[str, ...], again: bool
) -> None:
    calls, summary, _ = run_a_bot_after_the_checks(
        tmp_path,
        "rerun",
        "Run the failed jobs once more",
        {
            "repos/o/r/actions/runs/5/attempts/1/jobs": {
                "jobs": [
                    job_of_a_run(11, "variant (generic)", "failure"),
                    job_of_a_run(12, "update (generic)", "success"),
                    job_of_a_run(13, "variants", "failure"),
                ]
            },
            "repos/o/r/actions/workflows/3/runs": runs_of_the_branch(
                2, conclusion=conclusion
            ),
            **variants_of_a_run(
                "repos/o/r/actions/runs/2/jobs", "failure", messages, 21
            ),
        },
        NAME="Variants",
        CONCLUSION="failure",
        WORKFLOW="3",
        EVENT="pull_request",
        HEAD_REPO="o/r",
    )

    assert ("run rerun 5 --failed" in calls) == again
    assert ("broke for the commit before" in summary) != again


# The first attempt of a run of the tests, which passed when it ran again: a test that
# failed, a job that ran out of time, one that failed in its build, one without a log,
# and jobs that passed or that the failure of another cancelled.
FIRST_ATTEMPT: dict[str, object] = {
    "repos/o/r/actions/runs/5/attempts/1": {"conclusion": "failure"},
    "repos/o/r/actions/runs/5/attempts/1/jobs": {
        "jobs": [
            job_of_a_run(
                11,
                "test (3.12)",
                "failure",
                ("Set up Python", "success"),
                ("Run the tests", "failure"),
                ("Post Set up Python", "skipped"),
            ),
            job_of_a_run(12, "test (3.13)", "success", ("Run the tests", "success")),
            job_of_a_run(
                13,
                "e2e (Safari)",
                "cancelled",
                ("Start Home Assistant", "success"),
                ("Run the browser tests", "cancelled"),
            ),
            job_of_a_run(
                14, "e2e (Chrome)", "cancelled", ("Run the browser tests", "cancelled")
            ),
            job_of_a_run(
                15, "build", "failure", ("Pull", "failure"), ("Build", "failure")
            ),
            job_of_a_run(16, "docs", "failure", ("Build the website", "failure")),
        ]
    },
    "repos/o/r/check-runs/11/annotations": annotations_of_a_job(EXITED),
    "repos/o/r/check-runs/13/annotations": annotations_of_a_job(TIMED_OUT, CANCELLED),
    "repos/o/r/check-runs/14/annotations": annotations_of_a_job(CANCELLED),
    "repos/o/r/check-runs/15/annotations": annotations_of_a_job(
        EXITED, "Error: the image   could not\nbe pulled"
    ),
    "repos/o/r/check-runs/16/annotations": annotations_of_a_job(EXITED),
    "repos/o/r/actions/jobs/11/logs": (
        "2026-10-12T09:15:58.0000000Z ===== short test summary info =====\n"
        "2026-10-12T09:15:58.0000001Z \x1b[31mFAILED\x1b[0m"
        " tests/test_cards.py::test_board[dark] - AssertionError: assert 1 == 2\n"
        "2026-10-12T09:15:58.0000002Z FAILED tests/test_cards.py::test_score - TimeoutError\n"
        "2026-10-12T09:15:58.0000003Z ERROR    homeassistant.setup:setup.py:12 no test\n"
    ),
    "repos/o/r/actions/jobs/13/logs": "2026-10-12T09:15:58.0000000Z Open the board\n",
    "repos/o/r/actions/jobs/15/logs": "2026-10-12T09:15:58.0000000Z Pull the image\n",
}
# An empty cell of the table.
NOTHING = "\N{EN DASH}"
FLAKY_ROWS = [
    "| [`test (3.12)`](https://github.com/o/r/actions/runs/5/job/11) | `Run the tests`"
    " | `tests/test_cards.py::test_board[dark], tests/test_cards.py::test_score`"
    " | `AssertionError: assert 1 == 2` |",
    "| [`e2e (Safari)`](https://github.com/o/r/actions/runs/5/job/13)"
    f" | `Run the browser tests` | {NOTHING} | `{TIMED_OUT}` |",
    "| [`build`](https://github.com/o/r/actions/runs/5/job/15) | `Pull, Build`"
    f" | {NOTHING} | `Error: the image could not be pulled` |",
    "| [`docs`](https://github.com/o/r/actions/runs/5/job/16)"
    f" | `Build the website` | {NOTHING} | `{EXITED}` |",
]


@WITH_JQ
def test_the_flaky_test_bot_names_the_step_the_test_and_the_error(
    tmp_path: Path,
) -> None:
    calls, summary, written = run_a_bot_after_the_checks(
        tmp_path,
        "report",
        "Add the jobs that failed at first to the issue of flaky tests",
        {**FIRST_ATTEMPT, "issue list": []},
        URL="https://github.com/o/r/actions/runs/5",
    )

    assert written["issue-create"] == "\n".join(
        [
            "The flaky-test bot lists here every job that failed and then passed without"
            " a change of the code, with the step, the test and the error that failed."
            " Fix its test, then close this issue.",
            "",
            "**CI (python)** failed at first and passed when it ran again, on `feature`"
            " at abc1234 ([the run](https://github.com/o/r/actions/runs/5)):",
            "",
            "| Job | Step | Test | Error |",
            "| --- | --- | --- | --- |",
            *FLAKY_ROWS,
            "",
        ]
    )
    assert any(
        call.startswith("issue create --title Flaky tests --label maintenance ")
        for call in calls
    )
    assert "\n".join(FLAKY_ROWS) in summary


@WITH_JQ
def test_the_flaky_test_bot_keeps_one_issue(tmp_path: Path) -> None:
    calls, _, written = run_a_bot_after_the_checks(
        tmp_path,
        "report",
        "Add the jobs that failed at first to the issue of flaky tests",
        {
            **FIRST_ATTEMPT,
            "issue list": [
                {"number": 8, "title": "Flaky tests of the website"},
                {"number": 7, "title": "Flaky tests"},
            ],
        },
        URL="https://github.com/o/r/actions/runs/5",
    )

    assert "issue-create" not in written
    assert any(call.startswith("issue comment 7 --body ") for call in calls)
    assert written["issue-comment"].endswith("\n".join(FLAKY_ROWS))


@WITH_JQ
def test_the_flaky_test_bot_reports_no_run_that_a_newer_one_cancelled(
    tmp_path: Path,
) -> None:
    # The bot for cancelled checks started it again: no test failed.
    calls, summary, written = run_a_bot_after_the_checks(
        tmp_path,
        "report",
        "Add the jobs that failed at first to the issue of flaky tests",
        {
            "repos/o/r/actions/runs/5/attempts/1/jobs": {
                "jobs": [
                    job_of_a_run(
                        11, "test (3.12)", "cancelled", ("Run the tests", "cancelled")
                    ),
                    job_of_a_run(
                        12, "test (3.13)", "cancelled", ("Run the tests", "cancelled")
                    ),
                ]
            },
            "repos/o/r/actions/runs/5/attempts/1": {"conclusion": "cancelled"},
            "repos/o/r/check-runs/11/annotations": annotations_of_a_job(RACED),
            "repos/o/r/check-runs/12/annotations": annotations_of_a_job(RACED),
        },
        URL="https://github.com/o/r/actions/runs/5",
    )

    assert "nothing to report" in summary
    assert not written
    assert not any(call.startswith("issue ") for call in calls)


@WITH_JQ
@pytest.mark.parametrize("leg", ["cancelled", "failure"])
@pytest.mark.parametrize(
    "messages", [(RACED, CANCELLED), (CANCELLED,)], ids=["raced", "by a person"]
)
def test_the_flaky_test_bot_reports_no_job_that_failed_because_others_were_cancelled(
    tmp_path: Path, leg: str, messages: tuple[str, ...]
) -> None:
    # The bot for cancelled checks or a person started a cancelled run of Variants
    # again, and it passed: the job that waits for the legs failed in no test.
    calls, summary, written = run_a_bot_after_the_checks(
        tmp_path,
        "report",
        "Add the jobs that failed at first to the issue of flaky tests",
        {
            "repos/o/r/actions/runs/5/attempts/1": {"conclusion": "cancelled"},
            **variants_of_a_run(
                "repos/o/r/actions/runs/5/attempts/1/jobs", leg, messages, 11
            ),
            "issue list": [],
        },
        NAME="Variants",
        URL="https://github.com/o/r/actions/runs/5",
    )

    assert "nothing to report" in summary
    assert not written
    assert not any(call.startswith("issue ") for call in calls)
    assert not any("/logs" in call for call in calls)


@WITH_JQ
def test_the_flaky_test_bot_reports_the_job_of_a_cancelled_run_that_ran_out_of_time(
    tmp_path: Path,
) -> None:
    _, _, written = run_a_bot_after_the_checks(
        tmp_path,
        "report",
        "Add the jobs that failed at first to the issue of flaky tests",
        {
            "repos/o/r/actions/runs/5/attempts/1": {"conclusion": "cancelled"},
            **variants_of_a_run(
                "repos/o/r/actions/runs/5/attempts/1/jobs",
                "success",
                (TIMED_OUT, CANCELLED),
                11,
            ),
            "issue list": [],
        },
        NAME="Variants",
        URL="https://github.com/o/r/actions/runs/5",
    )

    # Not the job that waits for the legs.
    assert [
        line for line in written["issue-create"].splitlines() if line.startswith("| [")
    ] == [
        "| [`update (generic)`](https://github.com/o/r/actions/runs/5/job/12)"
        f" | {NOTHING} | {NOTHING} | `{TIMED_OUT}` |"
    ]


@WITH_JQ
def test_the_flaky_test_bot_writes_names_and_logs_as_plain_code(
    tmp_path: Path,
) -> None:
    # A pull request names its jobs, its steps and its branch and writes its logs: none
    # of them may end the code, the cell or the line, or mention anybody.
    _, _, written = run_a_bot_after_the_checks(
        tmp_path,
        "report",
        "Add the jobs that failed at first to the issue of flaky tests",
        {
            "repos/o/r/actions/runs/5/attempts/1": {"conclusion": "failure"},
            "repos/o/r/actions/runs/5/attempts/1/jobs": {
                "jobs": [
                    job_of_a_run(
                        11,
                        "x` | @team\n[a](https://e.vil)",
                        "failure",
                        ("s`|\tt", "failure"),
                    ),
                    job_of_a_run(12, "long", "failure", ("Run", "failure")),
                ]
            },
            "repos/o/r/check-runs/11/annotations": annotations_of_a_job(
                "<b>`@team`</b>\r\n| y"
            ),
            "repos/o/r/check-runs/12/annotations": annotations_of_a_job("é" * 200),
            "repos/o/r/actions/jobs/11/logs": "FAILED tests/x.py::`@team` - z\n",
            "issue list": [],
        },
        URL="https://github.com/o/r/actions/runs/5",
        BRANCH="`@team`\n# x",
    )

    body = written["issue-create"]
    assert "on `@team # x` at abc1234" in body
    rows = body.splitlines()
    assert (
        "| [`x \\| @team\\n[a](https://e.vil)`](https://github.com/o/r/actions/runs/5/job/11)"
        " | `s\\|\\tt` | `tests/x.py::@team` | `<b>@team</b> \\| y` |"
    ) in rows
    # An error fills a line at most.
    assert (
        "| [`long`](https://github.com/o/r/actions/runs/5/job/12)"
        f" | `Run` | {NOTHING} | `{'é' * 149}\N{HORIZONTAL ELLIPSIS}` |"
    ) in rows
    # The code of the branch and of the cells.
    assert body.count("`") == 2 * 8


@WITH_JQ
def test_the_flaky_test_bot_names_no_branch_of_a_fork(tmp_path: Path) -> None:
    # A fork names its branches as it likes, and the issue is the repository's.
    _, _, written = run_a_bot_after_the_checks(
        tmp_path,
        "report",
        "Add the jobs that failed at first to the issue of flaky tests",
        {**FIRST_ATTEMPT, "issue list": []},
        URL="https://github.com/o/r/actions/runs/5",
        BRANCH="`@team` [a](https://e.vil)",
        HEAD_REPO="fork/r",
    )

    body = written["issue-create"]
    assert (
        "**CI (python)** failed at first and passed when it ran again, on a branch of"
        " a fork at abc1234 ([the run](https://github.com/o/r/actions/runs/5)):"
    ) in body.splitlines()
    assert "@team" not in body
    assert "e.vil" not in body


def test_the_release_of_a_merge_that_failed_runs_once_more() -> None:
    # The failed push of the tag of v0.10.0 held the release and its rollout for 35
    # minutes, until a person ran it again.
    job = after_the_checks_job("release")
    condition = condition_of(job)
    for part in (
        "!github.event.repository.fork",
        "github.event.workflow_run.name == 'Release'",
        "github.event.workflow_run.event == 'push'",
        "github.event.workflow_run.conclusion == 'failure'",
        "github.event.workflow_run.run_attempt == 1",
    ):
        assert part in condition
    permissions = job[job.index("    permissions:\n") : job.index("    steps:\n")]
    assert permissions.splitlines()[1:] == ["      actions: write"]
    script = script_of(job, "Run the failed jobs of the release once more")
    assert script.startswith('gh run rerun "$RUN" --failed\n')
    assert "${{" not in job[job.index("        run: |\n") :]


# The checks that take seconds, whose runs for different commits never cancel each
# other, and some that take minutes, whose runs for a newer commit cancel the older.
QUICK_CHECKS = [
    "pull-request-title.yml",
    "dependency-review.yml",
    "secret-scan.yml",
    "area-labels.yml",
    "docs.yml",
]
LONG_CHECKS = ["ci-python.yml", "codeql.yml", "variants.yml", "lint.yml"]


def concurrency_of(name: str) -> str:
    workflow = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
    found = re.search(
        r"^concurrency:\n  group: (.+)\n  cancel-in-progress: ", workflow, re.M
    )
    assert found, name
    return found[1]


@pytest.mark.parametrize("name", QUICK_CHECKS)
def test_a_quick_check_never_cancels_the_run_for_another_commit(name: str) -> None:
    # The release bot edits its pull request while release-please pushes to it, and a
    # late run for the older commit cancelled the required checks of the head. Runs for
    # the same commit, such as those of an edited title, still replace each other.
    group = concurrency_of(name)
    assert "github.event.pull_request.number" in group
    assert group.endswith("-${{ github.event.pull_request.head.sha }}")


@pytest.mark.parametrize("name", LONG_CHECKS)
def test_a_long_check_cancels_the_runs_for_older_commits(name: str) -> None:
    # Their runners are worth more than the race, which the bot for cancelled checks
    # repairs.
    assert "head.sha" not in concurrency_of(name)


def test_the_tests_start_the_bash_of_the_path() -> None:
    # A bare "bash" ran the steps in WSL on Windows, and scripts/check.sh failed there:
    # the first argument of a call or of a list or tuple, alone or after env; only the
    # search for it may name it. A search of the whole PATH finds the same WSL from
    # PowerShell or an IDE: every test takes BASH of tests/shell.py.
    bare = re.compile(r'(?:\[|(?<!which)\()\s*(?:"/usr/bin/env",\s*)?"bash"\s*[,\])]')
    anywhere = re.compile(r'which\(\s*"bash"\s*\)')
    for path in sorted((ROOT / "tests").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        assert not bare.search(text), path.name
        assert not anywhere.search(text), path.name


def test_the_checks_run_on_windows_as_well(projects: dict[str, Path]) -> None:
    # Contributors on Windows run scripts/check.sh in Git Bash; the other workflows
    # run on Linux only.
    windows = (ROOT / ".github/workflows/windows.yml").read_text(encoding="utf-8")
    assert "    runs-on: windows-2025\n" in windows
    assert "    shell: bash\n" in windows
    assert "run: pip install --require-hashes -r requirements-dev.txt\n" in windows
    assert "run: bash scripts/check.sh\n" in windows
    # Every week, and for each pull request that changes what the checks run, the
    # template that the tests render among it: its paths must be valid on Windows too.
    assert "  schedule:\n    - cron: " in windows
    paths = re.search(r"  pull_request:\n    paths:\n((?:      - .+\n)+)", windows)
    assert paths
    assert {line[8:].strip('"') for line in paths[1].splitlines()} >= {
        "**.py",
        "blueprint/**",
        "tests/**",
        "template/**",
        "includes/**",
        "copier.yml",
        "pyproject.toml",
        "requirements-dev.txt",
        "scripts/check.sh",
        ".github/workflows/windows.yml",
    }
    # A check of the blueprint alone, which no pull request has to wait for.
    settings = tomllib.loads(
        (ROOT / ".github/repository.toml").read_text(encoding="utf-8")
    )
    assert re.findall(r"^    name: (.+)$", windows, re.M) == ["check (Windows)"]
    assert "check (Windows)" not in settings["branch"]["required_checks"]
    for project in projects.values():
        assert not (project / ".github/workflows/windows.yml").exists()


# The release pull request: the branch of the release bot in this repository, not a
# branch of a fork that is named like it.
RELEASE_PULL_REQUEST = (
    "!startsWith(github.head_ref, 'release-please--') || "
    "github.event.pull_request.head.repo.full_name != github.repository"
)
# The scanners of pull requests, by workflow and job, each for the files it reads.
SCANNERS = {
    "fuzz.yml": "fuzz",
    "zizmor.yml": "zizmor",
    "osv-scanner.yml": "pull-request",
    "links.yml": "links",
}


def test_the_release_pull_request_runs_nothing_that_its_change_cannot_fail() -> None:
    # It changes the changelog and the version, which no kind of project renders and
    # no scanner reads, and the pull requests it releases ran every check already.
    flows = workflows(ROOT)
    skipped = {"variants.yml": "variant", **SCANNERS}
    for name, job in skipped.items():
        assert RELEASE_PULL_REQUEST in condition_of(job_of(flows[name], job)), name
    # The hints at the prose, steps of lint, which start with the changed documents.
    documents = step_of(
        job_of(flows["lint.yml"], "lint"), "      - name: Find the changed documents"
    )
    found = re.search(r"^        if: >-\n((?:          .+\n)+)", documents, re.M)
    assert found
    assert RELEASE_PULL_REQUEST in " ".join(found[1].split())


def test_one_check_stands_for_every_variant() -> None:
    variants = (ROOT / ".github/workflows/variants.yml").read_text(encoding="utf-8")
    gate = job_of(variants, "variants")
    assert "\n    name: variants\n" in gate
    assert "\n    needs: variant\n" in gate
    # Also after a variant failed, so that the check reports the failure.
    assert condition_of(gate) == "always()"
    settings = tomllib.loads(
        (ROOT / ".github/repository.toml").read_text(encoding="utf-8")
    )
    # A matrix that its condition skips reports none of its legs, so none is required.
    required = settings["branch"]["required_checks"]
    assert [check for check in required if check.startswith(("variant", "update"))] == [
        "variants"
    ]


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize(
    ("result", "passes"),
    [("success", True), ("skipped", True), ("failure", False), ("cancelled", False)],
)
def test_the_check_variants_passes_when_every_variant_passed_or_none_ran(
    tmp_path: Path, result: str, passes: bool
) -> None:
    variants = (ROOT / ".github/workflows/variants.yml").read_text(encoding="utf-8")
    script = script_of(variants, "Require every variant to pass, or none to run")
    (tmp_path / "step.sh").write_text(script, encoding="utf-8", newline="\n")
    assert BASH
    done = subprocess.run(
        [BASH, "-e", "step.sh"],
        cwd=tmp_path,
        env={**os.environ, "RESULT": result},
        capture_output=True,
        encoding="utf-8",
        check=False,
    )

    assert (done.returncode == 0) == passes, done.stderr


@pytest.mark.parametrize("targets", [1, 2, 5])
@pytest.mark.parametrize("weekly", [True, False])
def test_the_fuzzing_ends_within_its_timeout_however_many_targets(
    tmp_path: Path, targets: int, weekly: bool
) -> None:
    # Every week the targets share one budget, so a new target doesn't push the job
    # past its timeout; a pull request fuzzes each one for a minute.
    workflow = (ROOT / ".github/workflows/fuzz.yml").read_text(encoding="utf-8")
    timeout = re.search(r"timeout-minutes: (\d+)\n    steps:", workflow)
    weekly_budget = re.search(r"'schedule' && '(\d+)'", workflow)
    assert timeout, "the fuzzing has a timeout"
    assert weekly_budget, "the weekly fuzzing has a budget"
    weekly_seconds = int(weekly_budget[1])
    # Five minutes are left for the setup and for the end of the last run.
    assert weekly_seconds + 5 * 60 <= int(timeout[1]) * 60
    repository = tmp_path / "repository"
    (repository / "fuzz").mkdir(parents=True)
    for number in range(targets):
        (repository / f"fuzz/fuzz_{number}.py").write_text("", encoding="utf-8")
    result, calls = run_workflow_step(
        tmp_path,
        script_of(workflow, "Fuzz every target"),
        repository,
        {"python": ""},
        RUNNER_TEMP=(tmp_path / "temp").as_posix(),
        WEEKLY_SECONDS=str(weekly_seconds) if weekly else "",
    )
    assert result.returncode == 0, result.stderr
    budgets = [
        int(found) for found in re.findall(r"-max_total_time=(\d+)", "\n".join(calls))
    ]
    assert len(budgets) == targets
    if weekly:
        assert sum(budgets) <= weekly_seconds
        assert budgets == [weekly_seconds // targets] * targets
    else:
        assert budgets == [60] * targets


def test_a_merge_runs_only_what_keeps_a_baseline_of_main() -> None:
    # main takes a pull request only when it is up to date, so a merge gives main the
    # tree that the checks of the pull request passed with.
    flows = workflows(ROOT)
    for name in ("variants.yml", "lint.yml", "secret-scan.yml", "sbom.yml", "fuzz.yml"):
        assert "push" not in triggers(flows[name]), name
    # What depends on tools and sites that move on their own runs every week instead.
    for name in ("variants.yml", "secret-scan.yml", "sbom.yml", "fuzz.yml"):
        assert "schedule" in triggers(flows[name]), name
    # Every release carries an SBOM of its own; the weekly one is the repository's.
    assert set(triggers(flows["sbom.yml"])) == {"schedule", "workflow_dispatch"}
    # After every merge: the coverage of main, the newest Python, the analyses that code
    # scanning compares pull requests with, the website, the release and the branch bot.
    for name in (
        "ci-python.yml",
        "newest-python.yml",
        "codeql.yml",
        "zizmor.yml",
        "osv-scanner.yml",
        "scorecard.yml",
        "docs.yml",
        "release.yml",
        "update-branches.yml",
    ):
        assert triggers(flows[name])["push"] == ["    branches: [main]"], name


@pytest.mark.parametrize("project", ["blueprint", *KINDS])
def test_a_scanner_runs_in_the_pull_requests_that_change_what_it_reads(
    projects: dict[str, Path], project: str
) -> None:
    root = ROOT if project == "blueprint" else projects[project]
    flows = workflows(root)
    scanners = [name for name in SCANNERS if name in flows]
    filters = {name: paths_of(flows[name], "pull_request") for name in scanners}
    # Only Python projects are fuzzed.
    python = project in ("blueprint", "python-package", "github-action")
    assert ("fuzz.yml" in filters) == python

    def reads(scanner: str, path: str) -> bool:
        name = path.rsplit("/", 1)[-1]
        if scanner == "fuzz.yml":
            return path.endswith(".py") or path.startswith("fuzz/")
        if scanner == "zizmor.yml":
            return path.startswith(".github/workflows/") or path in (
                "action.yml",
                ".github/dependabot.yml",
                ".github/zizmor.yml",
            )
        if scanner == "osv-scanner.yml":
            return bool(re.search(r"requirements[^/]*\.txt$", name)) or name in (
                "package-lock.json",
                "composer.lock",
                "osv-scanner.toml",
            )
        return (
            path.endswith(".md")
            and path != "CHANGELOG.md"
            and not path.startswith("changelog.d/")
        )

    for path in files_of(root):
        for scanner, patterns in filters.items():
            if reads(scanner, path):
                assert runs_for(patterns, [path]), f"{scanner}: {path}"
    # A change of the documentation starts only the link check, and the release pull
    # request, with the changelog and the version, starts none.
    for changed in (
        ["README.md", "docs/index.md"],
        [
            "CHANGELOG.md",
            "changelog.d/dark-mode.md",
            "version.txt",
            ".release-please-manifest.json",
        ],
    ):
        for scanner, patterns in filters.items():
            expected = scanner == "links.yml" and "README.md" in changed
            assert runs_for(patterns, changed) == expected, (scanner, changed)


@pytest.mark.parametrize("project", ["blueprint", *KINDS])
def test_a_required_check_never_waits_for_a_path_filter(
    projects: dict[str, Path], project: str
) -> None:
    # A workflow that its path filter leaves out reports none of its checks, and a
    # required check that never reports blocks the pull request for good.
    root = ROOT if project == "blueprint" else projects[project]
    settings = tomllib.loads(
        (root / ".github/repository.toml").read_text(encoding="utf-8")
    )
    required = set(settings["branch"]["required_checks"])
    providers = 0
    for name, text in workflows(root).items():
        if required & set(re.findall(r"^    name: (.+)$", text, re.M)):
            providers += 1
            events = triggers(text)
            assert {"pull_request", "pull_request_target"} & set(events), name
            for event in ("pull_request", "pull_request_target"):
                for line in events.get(event, []):
                    assert not line.startswith("    paths"), f"{name}: {line}"
    assert providers >= len(OTHER_CHECKS)


@pytest.mark.parametrize("project", ["blueprint", *KINDS])
def test_the_newest_python_checks_main_and_every_week(
    projects: dict[str, Path], project: str
) -> None:
    root = ROOT if project == "blueprint" else projects[project]
    flows = workflows(root)
    python = project in ("blueprint", "python-package", "github-action")
    assert ("newest-python.yml" in flows) == python
    for name, text in flows.items():
        if name != "newest-python.yml":
            assert "check (newest Python)" not in text, name
    if python:
        newest = flows["newest-python.yml"]
        # Not in pull requests: a new Python breaks them all alike, and none waits for
        # this check. A workflow of its own, so that it leaves the CI of main green.
        assert set(triggers(newest)) == {"push", "schedule", "workflow_dispatch"}
        assert "\n    name: check (newest Python)\n" in newest
        assert 'python-version: "3.x"\n          allow-prereleases: true\n' in newest
        assert "run: bash scripts/check.sh\n" in newest


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize(
    ("result", "open_issue", "call"),
    [
        # A failure opens the issue, or brings the open one up to date.
        ("failure", "", "issue create --title The checks fail with the newest Python"),
        ("failure", "7", "issue edit 7 --body"),
        # The weekly run closes it once the checks pass again.
        ("success", "7", "issue close 7"),
        ("success", "", ""),
    ],
)
def test_a_failure_with_the_newest_python_keeps_an_issue_open(
    tmp_path: Path, result: str, open_issue: str, call: str
) -> None:
    # No pull request shows the check, so its warning needs a place of its own.
    report = workflow_steps.job("newest-python.yml", "report")
    assert report["if"] == (
        "!cancelled() && github.ref == 'refs/heads/main' && "
        "(needs.newest-python.result == 'failure' || github.event_name == 'schedule')"
    )
    # Only the job without the code of the project may write issues.
    only_the_report_writes_issues("newest-python.yml")
    calls = keep_the_issue_of_a_bot(
        tmp_path,
        "newest-python.yml",
        "Keep the issue of the newest Python current",
        open_issue,
        RESULT=result,
    )

    if not call:
        assert calls == ""
        return
    assert calls.startswith(call), calls
    assert (f"The latest failure: {RUN_URL}" in calls) == (result == "failure")


@pytest.mark.parametrize("kind", ["blueprint", *KINDS])
def test_the_check_docs_keeps_the_website_of_a_pull_request(
    projects: Mapping[str, Path], kind: str
) -> None:
    # The artifact that the report of the PR coach links, by the name it looks for.
    root = ROOT if kind == "blueprint" else projects[kind]
    docs = (root / ".github/workflows/docs.yml").read_text(encoding="utf-8")
    step = docs[docs.index("      - name: Keep the website of the pull request\n") :]
    # Its lines up to the next comment or step.
    lines = re.split(r"\n      (?! )", step)[0].splitlines()[1:]
    assert lines == [
        "        if: ${{ !cancelled() && steps.build.outcome == 'success'"
        " && github.event_name == 'pull_request' }}",
        "        uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
        " # v7.0.1",
        "        timeout-minutes: 5",
        "        with:",
        f"          name: {WEBSITE_ARTIFACT}",
        "          path: site",
        f"          retention-days: {WEBSITE_DAYS}",
        "          include-hidden-files: true",
    ]


def run_the_search_for_the_website(
    tmp_path: Path, root: Path, event: str, pages: str, fork: bool
) -> tuple[str, str]:
    docs = (ROOT / ".github/workflows/docs.yml").read_text(encoding="utf-8")
    script = tmp_path / "step.sh"
    script.write_text(
        script_of(docs, "Look for the website"), encoding="utf-8", newline="\n"
    )
    # gh answers as GitHub Pages does: its build type, or 404 where it is off.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(
        """#!/usr/bin/env bash
if [[ "$*" != "api repos/o/r/pages --jq .build_type" || -z "$PAGES" ]]; then
  exit 1
fi
echo "$PAGES"
""",
        encoding="utf-8",
        newline="\n",
    )
    gh.chmod(0o755)
    output = tmp_path / "output"
    output.touch()
    environment = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "EVENT": event,
        "FORK": str(fork).lower(),
        "GITHUB_REF": "refs/heads/main" if event == "push" else "refs/pull/1/merge",
        "GITHUB_REPOSITORY": "o/r",
        "GITHUB_OUTPUT": str(output),
        "PAGES": pages,
    }
    assert BASH
    result = subprocess.run(
        [BASH, "-e", script.as_posix()],
        cwd=root,
        env=environment,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout, output.read_text(encoding="utf-8")


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize(
    ("project", "event", "pages", "fork", "output", "notice"),
    [
        # Every pull request builds the website as the check docs.
        ("generic", "pull_request", "workflow", False, "build=true\n", ""),
        # main publishes what it built where GitHub Pages publishes from a workflow.
        ("generic", "push", "workflow", False, "build=true\npublish=true\n", ""),
        (
            "generic",
            "push",
            "",
            False,
            "build=true\n",
            "doesn't publish from GitHub Actions",
        ),
        # The blueprint's Dashboard publishes it with the dashboard; main only builds it.
        (
            "blueprint",
            "push",
            "workflow",
            False,
            "build=true\n",
            "dashboard.yml publishes",
        ),
        # A fork of the blueprint runs no Dashboard, so its Docs publishes the website.
        ("blueprint", "push", "workflow", True, "build=true\npublish=true\n", ""),
        ("none", "push", "workflow", False, "", "No website here"),
    ],
)
def test_the_docs_workflow_publishes_the_website_unless_another_workflow_does(
    projects: dict[str, Path],
    tmp_path: Path,
    project: str,
    event: str,
    pages: str,
    fork: bool,
    output: str,
    notice: str,
) -> None:
    roots = {"blueprint": ROOT, "none": tmp_path}
    root = roots.get(project) or projects[project]

    printed, written = run_the_search_for_the_website(
        tmp_path, root, event, pages, fork
    )

    assert written == output
    assert (notice in printed) if notice else printed == ""


@pytest.mark.parametrize("kind", ["blueprint", *KINDS])
def test_the_docs_workflow_builds_the_website_once_and_keeps_its_downloads_a_week(
    projects: dict[str, Path], kind: str
) -> None:
    folder = ROOT if kind == "blueprint" else projects[kind]
    docs = (folder / ".github/workflows/docs.yml").read_text(encoding="utf-8")
    # The check builds the website, and on main the same job hands it to GitHub Pages:
    # no job builds it a second time, and the required check keeps its name.
    assert jobs_of(docs) == ["docs", "deploy"]
    job = job_of(docs, "docs")
    assert "\n    name: docs\n" in job
    assert "      publish: ${{ steps.site.outputs.publish }}\n" in job
    deploy = job_of(docs, "deploy")
    assert "\n    needs: docs\n" in deploy
    assert condition_of(deploy) == "needs.docs.outputs.publish == 'true'"
    # An artifact needs no permission: the job of the check still only reads.
    assert "    permissions:\n      contents: read\n      pages: read #" in job
    assert ": write" not in job
    build = job.index("      - name: Build the website\n")
    upload = step_of(job, "      - name: Hand the website to GitHub Pages")
    assert setting_of(upload, "if") == "steps.site.outputs.publish == 'true'"
    assert "uses: actions/upload-pages-artifact@" in upload
    assert "          path: site\n" in upload
    # Files and folders whose name starts with a dot, such as .well-known for
    # security.txt, reach the website; the action leaves them out otherwise.
    assert "          include-hidden-files: true\n" in upload
    assert job.index(upload) > build

    # Material's cache of what its plugins download, as its documentation has it: one
    # for each ISO week and each configuration, which a run restores before the build,
    # or else the latest one of the same week, and which only a push saves, once.
    restore = step_of(job, "      - name: Restore the downloads of the website")
    save = step_of(job, "      - name: Keep the downloads of the website for the week")
    assert "uses: actions/cache/restore@" in restore
    assert "uses: actions/cache/save@" in save
    assert job.index(restore) < build < job.index(save) < job.index(upload)
    # Badges and pictures show the state of now, so the build downloads them anew.
    fresh = step_of(job, "      - name: Download the badges and pictures anew")
    assert setting_of(fresh, "if") == "steps.site.outputs.build == 'true'"
    assert job.index(restore) < job.index(fresh) < build
    installed = UV_PIP.search(job)
    assert installed
    lock = LOCK.search(installed[1])
    assert lock
    files = ("mkdocs.yml", ".github/mkdocs-blueprint.yml", lock[0])
    for name in files:
        assert (folder / name).is_file(), name
    week = "mkdocs-material-${{ steps.week.outputs.id }}-"
    hashed = ", ".join(f"'{name}'" for name in files)
    assert f"          key: {week}${{{{ hashFiles({hashed}) }}}}\n" in restore
    assert f"          restore-keys: {week}\n" in restore
    assert "          key: ${{ steps.cache.outputs.cache-primary-key }}\n" in save
    saved_when = save.split("        if: >-\n", 1)[1].split("        uses: ", 1)[0]
    assert " ".join(saved_when.split()) == (
        "steps.site.outputs.build == 'true' && github.event_name == 'push' &&"
        " steps.cache.outputs.cache-hit != 'true'"
    )
    # Where the plugins of Material keep their downloads, which no website moves, and
    # which git ignores.
    for step in (restore, save):
        assert "          path: .cache\n" in step
    base = (folder / ".github/mkdocs-blueprint.yml").read_text(encoding="utf-8")
    assert "cache_dir" not in base
    assert "/.cache/" in (folder / ".gitignore").read_text(encoding="utf-8").split("\n")


@pytest.mark.parametrize("kind", ["blueprint", *KINDS])
def test_the_check_docs_checks_the_website_that_it_built(
    projects: dict[str, Path], kind: str
) -> None:
    folder = ROOT if kind == "blueprint" else projects[kind]
    docs = (folder / ".github/workflows/docs.yml").read_text(encoding="utf-8")
    links = (folder / ".github/workflows/links.yml").read_text(encoding="utf-8")
    job = job_of(docs, "docs")
    build = step_of(job, "      - name: Build the website")
    assert setting_of(build, "id") == "build"
    promises = step_of(job, "      - name: Check what the hooks of the website promise")
    address = step_of(job, "      - name: Lay out the address of the website")
    lychee = step_of(job, "      - name: Check the links and anchors of the website")
    project = step_of(job, "      - name: Check the website as this project does")
    accessible = step_of(job, "      - uses: actions/setup-node@")
    publish = step_of(job, "      - name: Hand the website to GitHub Pages")
    order = [job.index(step) for step in (build, promises, address, lychee, project)]
    assert order == sorted(order)
    assert order[-1] < job.index(accessible) < job.index(publish)
    # Each check of the built website runs once the build passed, also when the
    # check before it failed, so that one run names everything to fix.
    built = "!cancelled() && steps.build.outcome == 'success'"
    node = step_of(job, "      - name: Set up the accessibility check")
    a11y_tests = step_of(job, "      - name: Test the accessibility check")
    a11y = step_of(job, "      - name: Check the accessibility of the website")
    for step in (promises, address, lychee, accessible, node, a11y):
        assert setting_of(step, "if") == f"${{{{ {built} }}}}", step
    assert setting_of(a11y_tests, "if") == (
        f"${{{{ {built} && hashFiles('.github/a11y/check.test.mjs') != '' }}}}"
    )
    assert setting_of(project, "if") == (
        f"${{{{ {built} && hashFiles('scripts/check-site.sh') != '' }}}}"
    )
    # What the hooks promise, with the languages for the job that publishes.
    assert setting_of(promises, "id") == "promises"
    assert 'python3 "$script" site-check site --output "$GITHUB_OUTPUT"' in promises
    assert "      languages: ${{ steps.promises.outputs.languages }}\n" in job
    assert "          ROOT: ${{ steps.promises.outputs.root }}\n" in address
    assert "          ADDRESS: ${{ runner.temp }}/address\n" in address
    # lychee of the Links workflow, without the network and away from its rules.
    pinned = re.search(r"uses: lycheeverse/lychee-action@\S+ # v\S+", links)
    assert pinned
    assert f"        {pinned[0]}\n" in lychee
    assert "          workingDirectory: site\n" in lychee
    assert (
        "          args: --offline --include-fragments --root-dir"
        " ${{ runner.temp }}/address --no-progress '**/*.html'\n"
    ) in lychee
    assert "fail:" not in lychee
    # The checks of the project alone, in a file that the blueprint never writes.
    assert "        run: bash scripts/check-site.sh site\n" in project
    assert not (folder / "scripts/check-site.sh").exists()


@pytest.mark.parametrize("kind", ["blueprint", *KINDS])
def test_the_job_that_publishes_the_website_signs_and_asks_for_it(
    projects: dict[str, Path], kind: str
) -> None:
    folder = ROOT if kind == "blueprint" else projects[kind]
    for name, before in (("docs", "docs"), ("dashboard", "build")):
        path = folder / f".github/workflows/{name}.yml"
        if not path.exists():
            assert kind != "blueprint"
            continue
        deploy = job_of(path.read_text(encoding="utf-8"), "deploy")
        assert (
            "    permissions:\n"
            "      attestations: write # keeps the signed provenance of the website\n"
            "      id-token: write # proves to GitHub Pages and to Sigstore which"
            " workflow publishes\n"
            "      pages: write # publishes the website\n"
        ) in deploy
        published = deploy.index("uses: actions/deploy-pages@")
        taken = step_of(deploy, "      - name: Take the website that GitHub Pages")
        attested = step_of(deploy, "      - name: Attest the provenance of the website")
        asked = step_of(deploy, "      - name: Ask the published website for its pages")
        assert published < deploy.index(taken) < deploy.index(attested)
        assert deploy.index(attested) < deploy.index(asked)
        assert "uses: actions/download-artifact@" in taken
        assert "          name: github-pages\n" in taken
        assert "uses: actions/attest-build-provenance@" in attested
        assert "          subject-path: ${{ runner.temp }}/pages/artifact.tar\n" in (
            attested
        )
        assert (
            f"          LANGUAGES: ${{{{ needs.{before}.outputs.languages }}}}\n"
        ) in asked
    security = (folder / "SECURITY.md").read_text(encoding="utf-8")
    signer = "dashboard.yml" if kind == "blueprint" else "docs.yml"
    repository = "Dennis-Otto/" + (
        "repo-blueprint" if kind == "blueprint" else "demo-project"
    )
    assert "\n## Verify the website\n" in security
    assert (
        f"gh attestation verify artifact.tar --repo {repository} --signer-workflow"
        f" {repository}/.github/workflows/{signer}\n"
    ) in security


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
def test_the_cache_of_the_website_belongs_to_the_iso_week(tmp_path: Path) -> None:
    docs = (ROOT / ".github/workflows/docs.yml").read_text(encoding="utf-8")
    step = step_of(docs, "      - name: Name the cache of this week")
    script = setting_of(step, "run")
    assert script
    output = tmp_path / "output"
    output.touch()
    assert BASH
    # The week of the ISO calendar, with its own year: 2026-W53 ends on 2027-01-03.
    before = datetime.datetime.now(datetime.UTC).isocalendar()
    subprocess.run(
        [BASH, "-c", script],
        env={**os.environ, "GITHUB_OUTPUT": str(output)},
        check=True,
    )
    after = datetime.datetime.now(datetime.UTC).isocalendar()

    weeks = {f"id={day.year}-{day.week:02d}\n" for day in (before, after)}
    assert output.read_text(encoding="utf-8") in weeks


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
def test_the_website_downloads_its_badges_anew_and_keeps_its_fonts(
    tmp_path: Path,
) -> None:
    docs = (ROOT / ".github/workflows/docs.yml").read_text(encoding="utf-8")
    step = step_of(docs, "      - name: Download the badges and pictures anew")
    block = step.split("        run: |\n", 1)[1]
    script = "".join(line[10:] for line in block.splitlines(keepends=True))
    assert "find " in script
    assert BASH
    # Without a cache there is nothing to clean up, and the step still passes.
    subprocess.run([BASH, "-c", script], cwd=tmp_path, check=True)

    external = tmp_path / ".cache/plugin/privacy/assets/external"
    kept = [
        "fonts.gstatic.com/s/roboto/v51/a.woff2",
        "fonts.gstatic.com/s/roboto/v51/b.woff",
        "fonts.gstatic.com/s/roboto/v51/c.ttf",
        "fonts.googleapis.com/css.49ea35f2.css",
        "unpkg.com/mermaid@11/dist/mermaid.min.js",
    ]
    dropped = [
        "github.com/owner/name/actions/workflows/ci.yml/badge.svg",
        "api.scorecard.dev/projects/github.com/owner/name/badge.svg",
        "raw.githubusercontent.com/owner/name/main/_github/social-preview.png",
        "example.org/picture.jpg",
    ]
    for name in (*kept, *dropped):
        (external / name).parent.mkdir(parents=True, exist_ok=True)
        (external / name).write_text("x", encoding="utf-8")
    social = tmp_path / ".cache/plugin/social/card.png"
    social.parent.mkdir(parents=True)
    social.write_text("x", encoding="utf-8")

    subprocess.run([BASH, "-c", script], cwd=tmp_path, check=True)

    assert [name for name in kept if not (external / name).is_file()] == []
    assert [name for name in dropped if (external / name).exists()] == []
    assert social.is_file()


@pytest.mark.parametrize("kind", KINDS)
def test_every_project_records_its_decisions(
    projects: dict[str, Path], kind: str
) -> None:
    decisions = projects[kind] / "docs/decisions"
    index = (decisions / "README.md").read_text(encoding="utf-8")
    for record in sorted(decisions.glob("0*.md")):
        if record.name != "0000-template.md":
            assert f"]({record.name})" in index, record.name
    assert (decisions / "0000-template.md").is_file()


def test_the_pr_coach_reads_every_coverage_report_of_the_checks() -> None:
    # The coach takes the report of the newest run of the tests, a workflow CI (...).
    step = script_of(
        after_the_checks_job("coach"),
        "Fetch the coverage reports of the head and of main",
    )
    assert 'startswith("CI (")' in step
    keep = set()
    for path in (ROOT / ".github/workflows").glob("ci-*.yml"):
        ci = path.read_text(encoding="utf-8")
        if "name: coverage\n" in ci:
            name = re.search(r"^name: (.+)$", ci, re.MULTILINE)
            assert name, path
            assert name[1].startswith("CI ("), name[1]
            keep.add(path.name)
    # Every kind of project with tests, the Node packages with the LCOV report of
    # their test runner, which the coach reads by its name.
    assert keep == {
        "ci-python.yml",
        "ci-github-action.yml",
        "ci-home-assistant.yml",
        "ci-php.yml",
        "ci-node.yml",
    }
    node = step_of(
        (ROOT / ".github/workflows/ci-node.yml").read_text(encoding="utf-8"),
        "      - name: Keep the coverage report",
    )
    assert "if: always() && hashFiles('lcov.info') != ''" in node
    assert "path: lcov.info\n" in node
    assert "--test-reporter-destination=lcov.info" in (
        ROOT / "template/[% if stack == 'node' %]package.json[% endif %].jinja"
    ).read_text(encoding="utf-8")
    # The job that kept a comment of its own is gone; the report holds the table.
    assert "\n  coverage:\n" not in (
        ROOT / ".github/workflows/after-checks.yml"
    ).read_text(encoding="utf-8")


# The runs of the head: the tests, which kept a report, after a run that was cancelled.
RUNS_OF_THE_HEAD = [
    {
        "databaseId": 8,
        "workflowDatabaseId": 2,
        "workflowName": "Docs",
        "conclusion": "success",
    },
    {
        "databaseId": 9,
        "workflowDatabaseId": 3,
        "workflowName": "CI (python)",
        "conclusion": "cancelled",
    },
    {
        "databaseId": 11,
        "workflowDatabaseId": 3,
        "workflowName": "CI (python)",
        "conclusion": "failure",
    },
]


@WITH_JQ
# The report of Cobertura, and that of the test runner of Node, which the coach
# reads as LCOV by its name.
@pytest.mark.parametrize("report", ["coverage.xml", "lcov.info"])
def test_the_pr_coach_fetches_the_coverage_of_the_head_and_of_main(
    tmp_path: Path, report: str
) -> None:
    output = tmp_path / "output"
    # What the download of the head gives, which the fake gh doesn't write.
    (tmp_path / "head").mkdir()
    (tmp_path / "head" / report).touch()
    calls, summary, _ = run_a_bot_after_the_checks(
        tmp_path,
        "coach",
        "Fetch the coverage reports of the head and of main",
        {"run list": RUNS_OF_THE_HEAD, "run download": ""},
        GITHUB_OUTPUT=str(output),
    )

    assert calls[0].startswith("run list --commit abc1234def --status completed ")
    assert calls[1] == f"run download 11 --name coverage --dir {tmp_path}/head"
    # main: the newest run of the same workflow, as the fake answers with the runs.
    assert calls[2].startswith("run list --workflow 3 --branch main --event push ")
    assert calls[3] == f"run download 8 --name coverage --dir {tmp_path}/base"
    assert output.read_text(encoding="utf-8") == (
        f"head={tmp_path}/head/{report}\nbase={tmp_path}/base/{report}\n"
    )
    assert not summary


@WITH_JQ
@pytest.mark.parametrize(
    "answers",
    [
        # The tests haven't ended, or ended without a result.
        {"run list": RUNS_OF_THE_HEAD[:2]},
        # Their run kept no report.
        {"run list": RUNS_OF_THE_HEAD, "run download.error": "no artifact"},
    ],
)
def test_the_pr_coach_reports_without_coverage_before_the_tests_kept_it(
    tmp_path: Path, answers: dict[str, object]
) -> None:
    output = tmp_path / "output"
    calls, summary, _ = run_a_bot_after_the_checks(
        tmp_path,
        "coach",
        "Fetch the coverage reports of the head and of main",
        answers,
        GITHUB_OUTPUT=str(output),
    )

    assert summary == "No run of the tests of abc1234 kept a coverage report so far.\n"
    assert not output.exists()
    assert not any("--branch main" in call for call in calls)


@WITH_JQ
@pytest.mark.parametrize(
    ("coverage", "expected"),
    [
        ("", "--coverage  --coverage-base "),
        (
            "/t/head/coverage.xml",
            "--coverage /t/head/coverage.xml --coverage-base /t/b",
        ),
    ],
)
def test_the_pr_coach_hands_the_coverage_to_its_report(
    tmp_path: Path, coverage: str, expected: str
) -> None:
    calls, summary, _ = run_a_bot_after_the_checks(
        tmp_path,
        "coach",
        "Keep the one report of the PR coach up to date",
        {},
        {"python3": '#!/usr/bin/env bash\necho "python3 $*" >> "$CALLS"\necho done\n'},
        NUMBER="7",
        COVERAGE=coverage,
        COVERAGE_BASE=coverage and "/t/b",
    )

    assert calls == [
        "python3 blueprint.py --repo o/r coach report abc1234def --pull 7 " + expected
    ]
    assert summary == "done\n"


def test_the_coverage_report_of_the_blueprint_names_every_file_by_its_path() -> None:
    # Each folder under source becomes a source of the report, relative to which it
    # names the files, such as cli.py for blueprint/cli.py; with several, the coverage
    # comment can't tell them apart. Packages and modules by name keep one, the root.
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    run = config["tool"]["coverage"]["run"]
    assert "source" not in run
    assert "blueprint" in run["source_pkgs"]


@pytest.mark.parametrize("kind", KINDS)
def test_every_project_has_a_website(projects: dict[str, Path], kind: str) -> None:
    project = projects[kind]
    config = (project / "mkdocs.yml").read_text(encoding="utf-8")

    for line in (
        'site_name: "Demo Project"',
        f'site_description: "A {kind} of the tests, with \\"quotes\\" and Ümlauts."',
        "site_url: https://dennis-otto.github.io/demo-project/",
        "repo_url: https://github.com/Dennis-Otto/demo-project",
        "INHERIT: .github/mkdocs-blueprint.yml",
        "  - Home: index.md",
        # German pages follow the pattern of the comments.
        "#   i18n:",
        "#     enabled: true",
    ):
        assert f"\n{line}\n" in config, line
    # What every website shares is the blueprint's, which it keeps current; plugins
    # and Markdown extensions are mappings, so that those of a project merge with them.
    base = (project / ".github/mkdocs-blueprint.yml").read_text(encoding="utf-8")
    assert base == (ROOT / ".github/mkdocs-blueprint.yml").read_text(encoding="utf-8")
    for line in (
        "edit_uri: edit/main/docs/",
        "  name: material",
        "    - navigation.tabs",
        "  search: {}",
        "  privacy: {}",
        # The cards need Cairo, which Windows lacks: only the CI, where GitHub's
        # runners set CI to true, makes them, and a preview builds without them.
        "  social:\n    enabled: !ENV [CI, false]",
        # A picture for one scheme alone is in the lightbox of that scheme.
        "  glightbox:\n    auto_themed: true",
        "  git-revision-date-localized:",
        "  - .github/mkdocs_blueprint.py",
        "    strict: false",
        "  admonition: {}",
    ):
        assert f"\n{line}\n" in base, line
    assert "\n  - " not in base.split("\nplugins:\n")[1].split("\n\n")[0]
    # The languages come before the dates, which fail the build otherwise, and are off
    # until a project names its own; instant loading would break the language switch.
    assert "\n  i18n:\n    enabled: false\n    docs_structure: suffix\n" in base
    assert base.index("\n  i18n:\n") < base.index("\n  git-revision-date-localized:\n")
    assert "navigation.instant" not in base
    assert "/.cache/" in (project / ".gitignore").read_text(encoding="utf-8").split(
        "\n"
    )
    assert (
        (project / "docs/index.md")
        .read_text(encoding="utf-8")
        .startswith("# Demo Project\n")
    )
    # The tools of the Docs workflow are the blueprint's, which it keeps current.
    tools = (project / ".github/docs-requirements.txt").read_text(encoding="utf-8")
    assert tools == (ROOT / "stacks/docs/requirements-docs.txt").read_text(
        encoding="utf-8"
    )
    assert "mkdocs-material==" in tools
    docs = workflows(project)["docs.yml"]
    assert (
        "uv pip install --system --require-hashes -r .github/docs-requirements.txt"
        in docs
    )
    assert "repo-blueprint" not in docs.replace(
        "https://github.com/Dennis-Otto/repo-blueprint", ""
    )
    # The Docs workflow publishes it; only the blueprint has another workflow for that,
    # its Dashboard.
    publishers = [
        name
        for name, text in workflows(project).items()
        if "uses: actions/deploy-pages@" in text
    ]
    assert publishers == ["docs.yml"]
    settings = tomllib.loads(
        (project / ".github/repository.toml").read_text(encoding="utf-8")
    )
    assert settings["pages"] == {"build_type": "workflow"}
    assert "docs" in settings["branch"]["required_checks"]
    # A link out of docs/ leads nowhere on the website; such links go to GitHub.
    pages = (project / "docs").resolve()
    for page in pages.rglob("*.md"):
        text = page.read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^)\s#]+)", text):
            if "://" not in target:
                assert (page.parent / target).resolve().is_relative_to(pages), target


@pytest.mark.parametrize("kind", KINDS)
def test_every_website_shows_the_automation_of_its_repository(
    projects: dict[str, Path], kind: str
) -> None:
    project = projects[kind]
    spec = importlib.util.spec_from_file_location(
        f"hooks_of_{kind.replace('-', '_')}", project / ".github/mkdocs_blueprint.py"
    )
    assert spec is not None
    assert spec.loader is not None
    hooks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hooks)
    address = "https://github.com/Dennis-Otto/demo-project"
    config = SimpleNamespace(
        config_file_path=str(project / "mkdocs.yml"),
        docs_dir=str(project / "docs"),
        site_name="Demo Project",
        repo_url=address,
        edit_uri=None,
        theme={"language": "en"},
        plugins={},
    )

    folder = hooks.automated(config)
    assert folder == project / ".github/workflows"
    page = hooks.automation_pages(folder, config)["automation.md"]

    # Every workflow, with the comment at its top, where it comes from and what
    # starts it: a repository runs each one of them.
    files = sorted(folder.glob("*.yml"))
    assert f"its {len(files)} workflows of GitHub Actions" in page
    for path in files:
        text = path.read_text(encoding="utf-8")
        data = yaml.safe_load(text)
        anchor = re.sub(r"[^a-z0-9]+", "-", path.stem.lower())
        assert f"[{data['name']}](#{anchor}) | " in page, path.name
        first = re.search(r"^# (.+)$", text, re.M)
        assert first is not None, path.name
        assert first[1].split("`")[0].replace("&", "&amp;") in page, path.name
        source = f"{address}/blob/HEAD/.github/workflows/{path.name}"
        assert f"- **Source:** [`.github/workflows/{path.name}`]({source})" in page
    assert (
        "- **When:** every push to <code>main</code>, every day at 05:25 UTC, by hand"
        in page
    )
    # Every check that main requires, with the workflow that makes it.
    settings = tomllib.loads(
        (project / ".github/repository.toml").read_text(encoding="utf-8")
    )
    for check in settings["branch"]["required_checks"]:
        assert f"\n- <code>{check}</code> of [" in page, check
    assert "- **Environments:** <code>release</code>" in page
    blueprint = "https://github.com/Dennis-Otto/repo-blueprint"
    assert f"from the [Repo Blueprint]({blueprint})" in page
    nav = (project / "mkdocs.yml").read_text(encoding="utf-8").split("\nnav:\n")[1]
    assert "\n  - automation.md\n" in nav


@pytest.mark.parametrize("kind", KINDS)
def test_every_website_leads_to_its_owner_and_asks_github_for_nothing(
    projects: dict[str, Path], kind: str
) -> None:
    project = projects[kind]

    # The profile of the owner, the website with all of their projects, and the
    # sponsor button of the repository.
    assert footer_of(project) == [
        "https://github.com/Dennis-Otto",
        "https://dennis-otto.github.io/",
        "https://github.com/sponsors/Dennis-Otto",
    ]
    settings = (project / ".github/mkdocs-blueprint.yml").read_text(encoding="utf-8")
    assert settings == (ROOT / ".github/mkdocs-blueprint.yml").read_text(
        encoding="utf-8"
    )
    # No list of links in the settings of the blueprint takes their place.
    assert "\n  social:" not in settings.partition("\nextra:\n")[2]
    assert "asks the API of GitHub" in settings


@pytest.mark.parametrize("kind", [*KINDS, "blueprint"])
def test_every_website_is_checked_for_its_accessibility(
    projects: Mapping[str, Path], kind: str
) -> None:
    root = ROOT if kind == "blueprint" else projects[kind]
    # The check, its tools and the stylesheet and script of the hook are the
    # blueprint's, the same in every repository.
    for name in (
        ".github/a11y/check.mjs",
        ".github/a11y/package.json",
        ".github/a11y/package-lock.json",
        ".github/mkdocs-blueprint.css",
        ".github/mkdocs-blueprint.js",
    ):
        assert (root / name).read_bytes() == (ROOT / name).read_bytes(), name
    # Each tool by its exact version, locked with its hash.
    package = json.loads((root / ".github/a11y/package.json").read_text("utf-8"))
    lock = json.loads((root / ".github/a11y/package-lock.json").read_text("utf-8"))
    tools = package["devDependencies"]
    assert set(tools) == {"@axe-core/playwright", "playwright-core"}
    assert lock["packages"][""]["devDependencies"] == tools
    for name, version in tools.items():
        assert re.fullmatch(r"\d+\.\d+\.\d+", version), name
        assert lock["packages"][f"node_modules/{name}"]["version"] == version
    for name, locked in lock["packages"].items():
        assert not name or locked["integrity"].startswith("sha512-"), name
    ignored = (root / ".gitignore").read_text(encoding="utf-8").split("\n")
    assert "/.github/a11y/node_modules/" in ignored
    # The check docs runs it after the build, and reports for one release before
    # it fails the check.
    docs = (root / ".github/workflows/docs.yml").read_text(encoding="utf-8")
    step = docs[docs.index("      - name: Check the accessibility of the website\n") :]
    assert re.split(r"\n      (?! )", step)[0].splitlines()[1:] == [
        "        if: ${{ !cancelled() && steps.build.outcome == 'success' }}",
        "        continue-on-error: true",
        "        timeout-minutes: 5",
        "        env:",
        '          REPORT_ONLY: "true"',
        "        run: node .github/a11y/check.mjs site",
    ]
    assert docs.index("        run: mkdocs build --strict\n") < docs.index(step)
    tools_step = (
        "        run: npm ci --prefix .github/a11y --ignore-scripts --no-audit"
        " --no-fund\n"
    )
    assert docs.index("        run: mkdocs build --strict\n") < docs.index(tools_step)
    # The tests of the check run where the blueprint keeps them, before the check.
    tests = "        run: node --test .github/a11y/check.test.mjs\n"
    assert docs.index(tools_step) < docs.index(tests) < docs.index(step)
    assert "hashFiles('.github/a11y/check.test.mjs') != ''" in docs
    assert (root / ".github/a11y/check.test.mjs").is_file() == (kind == "blueprint")
    setup = docs[: docs.index(step)].rsplit("      - uses: ", 1)[1]
    assert setup.startswith("actions/setup-node@")
    assert "          node-version: 24\n" in setup
    if kind == "blueprint":
        # The website with the dashboard, which the Dashboard workflow publishes.
        dashboard = (root / ".github/workflows/dashboard.yml").read_text("utf-8")
        # The pages of the documentation are the check docs', the dashboard alone
        # is new.
        assert dashboard.index("python3 dashboard.py") < dashboard.index(
            "\n          node .github/a11y/check.mjs site dashboard/index.html\n"
        )
        for path in (".github/a11y/**", ".github/mkdocs-blueprint.css"):
            assert f"\n      - {path}\n" in dashboard, path


@pytest.mark.parametrize("kind", KINDS)
def test_every_project_draws_its_diagrams_as_pictures(
    projects: dict[str, Path], kind: str
) -> None:
    # The GitHub app and the stores show a ```mermaid block as code; a diagram is a
    # source in docs/diagrams/ and pictures of it, which the blueprint's script draws.
    project = projects[kind]
    script = (project / "scripts/diagrams.sh").read_text(encoding="utf-8")
    assert script == (ROOT / "scripts/diagrams.sh").read_text(encoding="utf-8")
    # The image, by its digest, where the rules of Renovate find it.
    assert re.search(
        r'^image="minlag/mermaid-cli:[^"@]+@sha256:[0-9a-f]{64}"$', script, re.M
    )
    # The check of check.sh needs neither Docker nor Python, right after the text files.
    check = (project / "scripts/check.sh").read_text(encoding="utf-8")
    step = check.index('\nstep "Diagrams"\n')
    version = check.index('\nstep "Version"\n')
    assert check.index('\nstep "Text files"\n') < step < version
    assert "\nbash scripts/diagrams.sh --check\n" in check[step:version]
    # The check that draws them anew, which every pull request must pass.
    settings = tomllib.loads(
        (project / ".github/repository.toml").read_text(encoding="utf-8")
    )
    assert "diagrams" in settings["branch"]["required_checks"]
    job = job_of(workflows(project)["lint.yml"], "diagrams")
    assert "\n            bash scripts/diagrams.sh --extract\n" in job
    assert "\n            git checkout --quiet --detach HEAD^2\n" in job
    assert "          name: diagrams\n" in job
    # The diagram bot commits what the check drew, onto a branch of the repository
    # alone, as the release app, with the tool of main; it never checks out a pull
    # request.
    bot = job_of(workflows(project)["after-checks.yml"], "diagrams")
    condition = condition_of(bot)
    for part in (
        "!github.event.repository.fork",
        "github.event.workflow_run.name == 'Lint'",
        "github.event.workflow_run.event == 'pull_request'",
        "github.event.workflow_run.conclusion == 'failure'",
        "github.event.workflow_run.head_repository.full_name == github.repository",
    ):
        assert part in condition, part
    assert "      name: release\n" in bot
    assert "ref:" not in bot
    assert "sparse-checkout: |\n            .github/blueprint\n" in bot
    assert ' diagrams commit "$kept" --branch "$BRANCH" \\\n' in bot
    assert '--head "$SHA"' in bot
    # Its commit lands on top of the branch and never needs to change a workflow.
    assert "permission-workflows" not in bot
    assert "      - name: Say on the pull request that the bot failed\n" in bot
    # No expression in a script, where the name of a branch could run as code.
    for script in bot.split("        run: |\n")[1:]:
        assert "${{" not in script.split("\n      - ")[0]
    # The diagram bot of main keeps one pull request from bot/diagrams, which merges
    # itself; only the job that draws nothing has the release app.
    main = workflows(project)["diagrams.yml"]
    assert "  push:\n    branches: [main]\n" in main
    assert "  schedule:\n" in main
    assert "  BRANCH: bot/diagrams\n" in main
    draw = job_of(main, "draw")
    assert "\n          bash scripts/diagrams.sh --extract\n" in draw
    assert "secrets." not in draw
    assert "environment:" not in draw
    opener = job_of(main, "pull-request")
    assert "      name: release\n" in opener
    assert "bash scripts/diagrams.sh" not in opener
    # Its branch moves from an older main to the newest, across changes of workflows.
    assert "\n          permission-workflows: write\n" in opener
    assert '\n          gh pr merge "$BRANCH" --auto --squash\n' in opener
    for script in opener.split("        run: |\n")[1:]:
        assert "${{" not in script.split("\n      - ")[0]
    # The website draws the sources live, and GitHub folds the pictures in diffs.
    hooks = (project / ".github/mkdocs_blueprint.py").read_text(encoding="utf-8")
    assert "def on_page_content(" in hooks
    attributes = (project / ".gitattributes").read_text(encoding="utf-8")
    assert "\ndocs/images/diagrams/*.svg linguist-generated=true\n" in attributes
    contributing = (project / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "`bash scripts/diagrams.sh`" in contributing
    assert "`docs/diagrams/" in contributing
    # The colors of the blueprint's diagrams, the same in every repository.
    for color in ("`#526cfe`", "`#f59e0b`", "`#16a34a`"):
        assert color in contributing, color


def test_renovate_keeps_the_renderer_of_the_diagrams_current() -> None:
    # A new version of mermaid-cli may draw the pictures otherwise: Renovate updates
    # its image on a branch of the repository, where the check draws them anew and
    # the diagram bot commits them.
    rules = renovate_rules(
        (ROOT / ".github/renovate-blueprint.json5").read_text(encoding="utf-8")
    )
    script = (ROOT / "scripts/diagrams.sh").read_text(encoding="utf-8")
    image = re.search(
        r'^image="([^:"]+):([^@"]+)@(sha256:[0-9a-f]{64})"$', script, re.M
    )
    assert image
    found = []
    for manager in rules["customManagers"]:
        files = [re.compile(name.strip("/")) for name in manager["managerFilePatterns"]]
        if not any(name.search("scripts/diagrams.sh") for name in files):
            continue
        for pattern in manager["matchStrings"]:
            for match in re.finditer(pattern.replace("(?<", "(?P<"), script):
                found.append(
                    (match["depName"], match["currentValue"], match["currentDigest"])
                )
    assert found == [image.groups()]


@pytest.mark.parametrize("kind", KINDS)
def test_the_screenshot_bot_is_in_every_repository_and_waits_for_its_script(
    projects: Mapping[str, Path], kind: str
) -> None:
    # Every repository has the screenshot bot of the blueprint, which renders nothing
    # until the project has scripts/screenshots.sh. A new repository starts with one
    # that renders the social preview, and with the list of the files it shows; both
    # belong to the project from then on.
    project = projects[kind]
    found = workflows(project)
    bot = found["screenshot-bot.yml"]
    assert bot == (ROOT / ".github/workflows/screenshot-bot.yml").read_text(
        encoding="utf-8"
    )
    # Under a name of its own: a project's own screenshots.yml, as ha-autodarts has,
    # stays the project's, and the picture bot of the blueprint's documentation stays
    # in the blueprint.
    assert "screenshots.yml" not in found
    assert "docs-pictures.yml" not in found
    assert (project / ".github/blueprint/screenshots.py").read_text(
        encoding="utf-8"
    ) == (ROOT / "blueprint/screenshots.py").read_text(encoding="utf-8")
    assert (project / ".github/screenshots-requirements.txt").read_text(
        encoding="utf-8"
    ) == (ROOT / "stacks/screenshots/requirements.txt").read_text(encoding="utf-8")
    script = (project / "scripts/screenshots.sh").read_text(encoding="utf-8")
    assert script.startswith("#!/usr/bin/env bash\n")
    assert "\nbash scripts/social-preview.sh\n" in script
    paths = (project / ".github/screenshots-paths.txt").read_text(encoding="utf-8")
    assert "\n.github/social-preview.html\n" in paths
    copier = (ROOT / "copier.yml").read_text(encoding="utf-8")
    agents = (project / "AGENTS.md").read_text(encoding="utf-8")
    for owned in ("/scripts/screenshots.sh", ".github/screenshots-paths.txt"):
        assert f"\n  - {owned}\n" in copier, owned
        assert f"`{owned}`" in agents, owned
    # The tool of the project knows the bot: with the script, it renders.
    decided = subprocess.run(
        [sys.executable, ".github/blueprint.py", "screenshots", "due"],
        cwd=project,
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
    )
    assert decided.returncode == 0, decided.stderr
    assert "`scripts/screenshots.sh`" in decided.stdout


def test_the_screenshot_bot_runs_no_code_with_a_token_that_writes() -> None:
    workflow = (ROOT / ".github/workflows/screenshot-bot.yml").read_text(
        encoding="utf-8"
    )
    # After a change of main, a release and every week; never for a pull request.
    for trigger in ("push:\n    branches: [main]", "workflow_run:", "schedule:"):
        assert f"\n  {trigger}" in workflow, trigger
    assert "pull_request" not in workflow
    assert "\npermissions: {}\n" in workflow
    assert "  BRANCH: bot/screenshots\n" in workflow
    assert '  HEADLINE: "docs: update the screenshots"\n' in workflow
    plan = job_of(workflow, "plan")
    assert " screenshots due --since " in plan
    assert (
        "startsWith(github.event.workflow_run.head_commit.message, 'chore: release ')"
        in condition_of(plan)
    )
    # Only the push run of a release, not its daily or manual runs on the same commit.
    assert "github.event.workflow_run.event == 'push'" in condition_of(plan)
    # A push that is not due never replaces a waiting render of one that is.
    assert not re.search(r"^concurrency:", workflow, re.M)
    assert "concurrency:" not in plan
    # The script of the project runs without secrets and with a token that reads.
    render = job_of(workflow, "render")
    assert "\n        run: bash scripts/screenshots.sh\n" in render
    assert "    permissions:\n      contents: read\n" in render
    for secret in ("secrets.", "environment:", "persist-credentials: true"):
        assert secret not in render, secret
    assert " screenshots keep " in render
    assert (
        "    concurrency:\n      group: ${{ github.workflow }}-render\n"
        "      cancel-in-progress: false\n"
    ) in render
    assert "uv venv --quiet .venv-docs\n" in render
    # Only the job that runs nothing of the script has the release app, and takes
    # the pictures as data, checked by blueprint.py of main.
    opener = job_of(workflow, "pull-request")
    assert "      name: release\n" in opener
    assert "bash scripts/screenshots.sh" not in opener
    assert (
        "sparse-checkout: |\n            .github/blueprint\n            blueprint\n"
        in opener
    )
    assert " screenshots commit " in opener
    assert (
        "    concurrency:\n      group: ${{ github.workflow }}-pull-request\n"
        "      cancel-in-progress: false\n"
    ) in opener
    assert "\n          permission-workflows: write\n" in opener
    assert '\n          gh pr merge "$open" --auto --squash\n' in opener
    assert 'author.login == \\"app/$APP_SLUG\\"' in opener
    for job in (plan, render, opener):
        for script in job.split("        run: |\n")[1:]:
            assert "${{" not in script.split("\n      - ")[0]
    # The bot-health bot keeps an issue open while the bot fails.
    health = (ROOT / ".github/workflows/bot-health.yml").read_text(encoding="utf-8")
    assert ", Screenshots, " in health
    # zizmor accepts its start after a release, with the reason in its configuration.
    zizmor = (ROOT / ".github/zizmor.yml").read_text(encoding="utf-8")
    dangerous = zizmor.split("  dangerous-triggers:", 1)[1].split("\n  self-", 1)[0]
    for name in ("screenshot-bot.yml", "docs-pictures.yml"):
        assert f"      - {name}\n" in dangerous, name


def test_the_pictures_of_the_blueprint_renew_themselves_after_a_release() -> None:
    # The recording and the dashboard of the README come from
    # scripts/docs-pictures.sh, which the picture bot of the blueprint runs after a
    # release that changed what they show, and on demand.
    workflow = (ROOT / ".github/workflows/docs-pictures.yml").read_text(
        encoding="utf-8"
    )
    assert "  workflow_run:\n    workflows: [Release]\n" in workflow
    assert "  workflow_dispatch:\n" in workflow
    assert "pull_request" not in workflow
    assert "  BRANCH: bot/pictures\n" in workflow
    assert '  HEADLINE: "docs: renew the pictures"\n' in workflow
    assert "  SCRIPT: scripts/docs-pictures.sh\n" in workflow
    plan = job_of(workflow, "plan")
    assert "github.repository == 'Dennis-Otto/repo-blueprint'" in condition_of(plan)
    assert "github.event.workflow_run.event == 'push'" in condition_of(plan)
    assert '--script "$SCRIPT" --paths "$PATHS"' in plan
    render = job_of(workflow, "render")
    assert '\n        run: bash "$SCRIPT"\n' in render
    for secret in ("secrets.", "environment:"):
        assert secret not in render, secret
    opener = job_of(workflow, "pull-request")
    assert "      name: release\n" in opener
    assert '\n          gh pr merge "$open" --auto --squash\n' in opener
    for job in (plan, render, opener):
        for script in job.split("        run: |\n")[1:]:
            assert "${{" not in script.split("\n      - ")[0]
    # The files whose change in a release can change the pictures.
    listed = (ROOT / ".github/docs-pictures/paths.txt").read_text(encoding="utf-8")
    for pattern in ("copier.yml", "template/**", ".github/workflows/**"):
        assert f"\n{pattern}\n" in listed, pattern
    script = (ROOT / "scripts/docs-pictures.sh").read_text(encoding="utf-8")
    # The video that the website plays in place of the GIF, the picture that shows
    # until it plays, and the smaller social preview of the home page.
    assert '\n  tar -xf "$recording" -C docs/images\n' in script
    for picture in ("copier-copy.mp4", "copier-copy.webp", "social-preview.webp"):
        assert f" {picture}" in script, picture
    for picture in ("copier-copy.gif", "dashboard.png"):
        assert f"docs/images/{picture}" in script, picture


def test_the_tools_of_the_website_install_on_windows() -> None:
    # The plugin for the dates requires tzdata on Windows alone. pip-compile on Linux
    # left it out of the lock, and with --require-hashes pip refused all of it there.
    wanted = (ROOT / "stacks/docs/requirements-docs.in").read_text(encoding="utf-8")
    assert "\ntzdata\n" in wanted
    lock = (ROOT / "stacks/docs/requirements-docs.txt").read_text(encoding="utf-8")
    assert re.search(
        r"^tzdata==\S+ \\\n(?:    --hash=sha256:[0-9a-f]{64} \\\n)*"
        r"    --hash=sha256:[0-9a-f]{64}\n",
        lock,
        re.MULTILINE,
    )


# The workflows that install Python tools: the CI of the Python stacks, which a project
# gets as its ci.yml, the website, the fuzzing, the property and the mutation tests, the
# dashboard and the variants.
UV_WORKFLOWS = [
    "ci-python.yml",
    "ci-github-action.yml",
    "ci-home-assistant.yml",
    "docs.yml",
    "dashboard.yml",
    "fuzz.yml",
    "properties.yml",
    "mutation.yml",
    "variants.yml",
]
PIP = re.compile(r'(?<!\buv )\bpip3?"? install\b')
UV_PIP = re.compile(r"\buv pip install (?:--system|--python \S+) (.+)")
LOCK = re.compile(r"[\w./-]*requirements[\w.-]*\.txt")
# The lock files that the Variants workflow installs in the project it renders, by the
# lock file of the blueprint that the project gets as each.
RENDERED_FROM = {
    ".github/docs-requirements.txt": "stacks/docs/requirements-docs.txt",
    "requirements-dev.txt": "stacks/python/requirements-dev.txt",
    "requirements-test.txt": "stacks/home-assistant/requirements-test.txt",
}
UV_VERSION = re.compile(
    r'\n          # renovate: datasource=pypi depName=uv\n          version: "(\d+\.\d+\.\d+)"\n'
)


def jobs_of(workflow: str) -> list[str]:
    """The names of the jobs of a workflow, in their order."""
    return re.findall(r"^  ([\w-]+):\n", workflow.split("\njobs:\n", 1)[1], re.M)


def steps_of(job: str) -> list[str]:
    """The steps of a job of a workflow, each with the comments above it."""
    steps: list[str] = []
    comments = ""
    for line in job.split("\n    steps:\n", 1)[1].splitlines(keepends=True):
        if line.startswith("      - "):
            steps.append(comments + line)
            comments = ""
        elif line.startswith("      #"):
            comments += line
        elif steps:
            steps[-1] += line
    return steps


def setting_of(step: str, name: str) -> str | None:
    """A setting of a step on one line, such as its if or its timeout-minutes."""
    found = re.search(rf"^(?:      - |        ){name}: (.+)$", step, re.M)
    return found[1] if found else None


def matches_glob(pattern: str, path: str) -> bool:
    """Whether a pattern of @actions/glob, as setup-uv reads its cache-dependency-glob,
    matches a path from the root of the workspace."""
    parts = re.split(r"(\*\*/|\*)", pattern)
    wildcards = {"**/": "(?:.*/)?", "*": "[^/]*"}
    expression = "".join(wildcards.get(part, re.escape(part)) for part in parts)
    return re.fullmatch(expression, path) is not None


def test_a_glob_of_setup_uv_matches_as_the_action_does() -> None:
    assert matches_glob("requirements-dev.txt", "requirements-dev.txt")
    assert not matches_glob(
        "requirements-dev.txt", "stacks/python/requirements-dev.txt"
    )
    assert matches_glob(
        "stacks/**/requirements*.txt", "stacks/docs/requirements-docs.txt"
    )
    assert matches_glob("stacks/**/requirements*.txt", "stacks/requirements.txt")
    assert not matches_glob(
        "stacks/**/requirements*.txt", "stacks/docs/requirements.in"
    )


@pytest.mark.parametrize("kind", ["blueprint", *KINDS])
def test_the_ci_installs_the_python_tools_with_uv_from_its_cache(
    projects: dict[str, Path], kind: str
) -> None:
    # uv installs the hash-pinned tools in seconds, where pip took a minute for those
    # of Home Assistant even with its cache, and checks the hash of each package.
    # GitHub keeps the cache of uv under a key of the lock files that the job installs,
    # pruned to the wheels that uv built from source: in the Variants, uv downloaded
    # the tools of Home Assistant in 6 seconds, while a cache with them, 232 MB, took
    # 7 to 11 seconds to restore.
    folder = ROOT if kind == "blueprint" else projects[kind]
    found = workflows(folder)
    installs, versions = 0, set()
    for name in ("ci.yml", *UV_WORKFLOWS):
        if name not in found:
            continue
        workflow = found[name]
        assert not PIP.search(workflow), name
        # No cache of pip's downloads either.
        assert "cache: pip" not in workflow, name
        for job_name in jobs_of(workflow):
            job = job_of(workflow, job_name)
            steps = steps_of(job)
            for index, step in enumerate(steps):
                commands = UV_PIP.findall(step)
                if not commands:
                    continue
                assert all("--require-hashes " in command for command in commands)
                setups = [
                    setup
                    for setup in steps[:index]
                    if "uses: astral-sh/setup-uv@" in setup
                ]
                assert len(setups) == 1, f"{name}: {job_name}"
                setup = setups[0]
                assert setting_of(setup, "if") in (None, setting_of(step, "if"))
                assert "          enable-cache: true\n" in setup
                assert "          prune-cache: true\n" in setup
                version = UV_VERSION.search(setup)
                assert version, setup
                versions.add(version[1])
                # After the Python that uv installs into.
                python = [
                    position
                    for position, other in enumerate(steps)
                    if "uses: actions/setup-python@" in other
                ]
                assert python
                assert python[0] < steps.index(setup)
                glob = re.search(
                    r"\n          cache-dependency-glob: (?:\|\n((?:            .+\n)+)|(.+)\n)",
                    setup,
                )
                assert glob, setup
                patterns = glob[1].split() if glob[1] else [glob[2]]
                in_project = (
                    setting_of(step, "working-directory") == "${{ env.PROJECT }}"
                )
                locks = [
                    RENDERED_FROM[lock] if in_project else lock
                    for lock in LOCK.findall(step[step.index("        run: ") :])
                ]
                assert locks, step
                for lock in locks:
                    assert any(matches_glob(pattern, lock) for pattern in patterns), (
                        f"{name}: {lock}"
                    )
                # A step that always runs here installs a lock file that is here.
                guarded = "github.repository != 'Dennis-Otto/repo-blueprint'" in job
                if not guarded and setting_of(step, "if") is None:
                    assert any((folder / lock).is_file() for lock in locks), locks
                installs += len(commands)
    # Every kind has a website, whose tools uv installs.
    assert installs
    # One uv, which Renovate keeps current.
    assert len(versions) == 1


def test_renovate_keeps_uv_and_hadolint_current() -> None:
    rules = renovate_rules(
        (ROOT / ".github/renovate-blueprint.json5").read_text(encoding="utf-8")
    )
    for path in sorted((ROOT / ".github/workflows").glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        found: list[dict[str, str | None]] = []
        for manager in rules["customManagers"]:
            files = [
                re.compile(name.strip("/")) for name in manager["managerFilePatterns"]
            ]
            if not any(name.search(f".github/workflows/{path.name}") for name in files):
                continue
            for pattern in manager["matchStrings"]:
                for match in re.finditer(pattern.replace("(?<", "(?P<"), text):
                    found.append(match.groupdict())
        uv = [dependency for dependency in found if dependency["depName"] == "uv"]
        assert len(uv) == text.count("uses: astral-sh/setup-uv@"), path.name
        for dependency in uv:
            assert dependency["datasource"] == "pypi"
            assert re.fullmatch(r"\d+\.\d+\.\d+", dependency["currentValue"] or "")
        hadolint = [
            dependency
            for dependency in found
            if dependency["depName"] == "ghcr.io/hadolint/hadolint"
            and dependency["currentDigest"]
        ]
        assert len(hadolint) == len(HADOLINT.findall(text)), path.name


@pytest.mark.parametrize("kind", [*KINDS, "blueprint"])
def test_the_uv_of_the_workflows_follows_the_blueprint(
    projects: dict[str, Path], kind: str
) -> None:
    # The workflows that set uv up belong to the blueprint: the blueprint's Renovate
    # moves their uv, and the next release brings it to every repository. A pull
    # request of a repository's own Renovate for each weekly release of uv would
    # change the blueprint's files and conflict with its next update.
    root = ROOT if kind == "blueprint" else projects[kind]
    shared = renovate_rules(
        (root / ".github/renovate-blueprint.json5").read_text(encoding="utf-8")
    )
    own = renovate_rules((root / ".github/renovate.json5").read_text(encoding="utf-8"))
    enabled = True
    for rule in [*shared["packageRules"], *own.get("packageRules", [])]:
        if "uv" in rule.get("matchDepNames", []):
            assert rule == {
                "matchManagers": ["custom.regex"],
                "matchDepNames": ["uv"],
                "matchFileNames": [".github/workflows/**"],
                "enabled": rule["enabled"],
            }
            enabled = rule["enabled"]
    assert enabled is (kind == "blueprint")


# Each job ends after a few times its longest run, and each step that installs, builds
# or downloads after five minutes: a build of the website that hung on 2026-10-12 held
# a pull request for half an hour, until the Variants ran out of time.
JOB_LIMITS = {
    ("variants.yml", "variant"): 10,
    ("ci-python.yml", "check"): 8,
    ("ci-github-action.yml", "check"): 8,
    ("ci-home-assistant.yml", "check"): 15,
}
WORK = re.compile(
    r"\b(?:uv (?:pip install|venv)|npm ci|composer install|docker run|curl"
    r"|mkdocs build|copier (?:copy|update)|gh api)\b"
)
SETUP = re.compile(
    r"uses: (?:actions/setup-\w+|astral-sh/setup-uv|shivammathur/setup-php"
    r"|actions/cache(?:/restore|/save)?)@"
)


@pytest.mark.parametrize(
    "name",
    [*UV_WORKFLOWS, "ci-container.yml", "screenshot-bot.yml", "docs-pictures.yml"],
)
def test_every_step_that_installs_builds_or_downloads_has_a_time_limit(
    name: str,
) -> None:
    workflow = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
    bounded = 0
    for job_name in jobs_of(workflow):
        job = job_of(workflow, job_name)
        limit = re.search(r"^    timeout-minutes: (.+)$", job, re.M)
        assert limit, f"{name}: {job_name}"
        if (name, job_name) in JOB_LIMITS:
            assert limit[1] == str(JOB_LIMITS[name, job_name])
        for step in steps_of(job):
            code = "".join(
                line
                for line in step.splitlines(keepends=True)
                if not line.lstrip().startswith("#")
            )
            if not (WORK.search(code) or SETUP.search(code)):
                continue
            minutes = setting_of(step, "timeout-minutes")
            assert minutes, f"{name}: {step}"
            assert int(minutes) <= 10
            if limit[1].isdigit():
                assert int(minutes) < int(limit[1])
            bounded += 1
    assert bounded


@pytest.mark.parametrize(
    "check", ["check (python)", "variant (home-assistant)", "update (container)"]
)
def test_the_pr_coach_explains_a_step_before_the_checks_that_ran_out_of_time(
    check: str,
) -> None:
    # When the install of the tools or the pull of an image hangs, its step stops
    # after five minutes, before scripts/check.sh ever ran: the coach says that the
    # job runs again, rather than only pointing at the checks.
    entry = Catalog.load(ROOT).check(check)
    assert entry
    assert (
        "When that step comes before the checks, such as the one that installs the"
        " tools or pulls an image, a download failed or hung until the step ran out"
        " of its time: that usually passes when the job runs again, which the"
        " flaky-test bot does once by itself."
    ) in entry.problem
    # As the bot does for the checks of CI and the Variants.
    after = (ROOT / ".github/workflows/after-checks.yml").read_text(encoding="utf-8")
    rerun = job_of(after, "rerun")
    assert 'gh run rerun "$RUN" --failed' in rerun
    left_out = re.search(
        r"!contains\(fromJSON\('(\[.+?\])'\), github\.event\.workflow_run\.name\)",
        rerun,
    )
    assert left_out
    names = json.loads(left_out[1])
    assert not [name for name in names if name.startswith(("CI", "Variants"))]
    assert "    workflows: [CI (python), Variants, " in after


@pytest.mark.parametrize("kind", ["blueprint", *KINDS])
def test_mypy_starts_from_the_cache_of_the_last_run_that_passed(
    projects: dict[str, Path], kind: str
) -> None:
    folder = ROOT if kind == "blueprint" else projects[kind]
    name = "ci-python.yml" if kind == "blueprint" else "ci.yml"
    ci = (folder / ".github/workflows" / name).read_text(encoding="utf-8")
    if "\nmypy\n" not in (folder / "scripts/check.sh").read_text(encoding="utf-8"):
        assert "mypy" not in ci
        return
    job = job_of(ci, "check")
    cache = step_of(job, "      - name: Restore the cache of mypy")
    assert "uses: actions/cache@" in cache
    # Where mypy keeps it, which no project moves.
    assert "          path: .mypy_cache\n" in cache
    config = tomllib.loads((folder / "pyproject.toml").read_text(encoding="utf-8"))
    assert "cache_dir" not in config["tool"]["mypy"]
    assert ".mypy_cache/" in (folder / ".gitignore").read_text(encoding="utf-8")
    # Its own cache when no Python file changed, else the latest one of the same tools;
    # GitHub saves it after a run that passed.
    key = re.search(r"\n          key: (.+)\n", cache)
    restore = re.search(r"\n          restore-keys: (.+)\n", cache)
    assert key
    assert restore
    assert restore[1] == "mypy-${{ runner.os }}-${{ hashFiles('requirements*.txt') }}-"
    assert key[1] == restore[1] + "${{ hashFiles('**/*.py') }}"
    assert job.index(cache) < job.index("      - name: Run the checks\n")


def test_mypy_keeps_no_finding_in_its_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # mypy checks a module from its cache again when the module or one that it uses
    # changed, and keeps no module with an error, so the cache of the CI hides none.
    monkeypatch.chdir(tmp_path)
    Path("mypy.ini").write_text("[mypy]\nstrict = True\n", encoding="utf-8")
    Path("wrong.py").write_text('def f() -> int:\n    return "x"\n', encoding="utf-8")
    Path("used.py").write_text("def g() -> int:\n    return 1\n", encoding="utf-8")
    Path("user.py").write_text(
        "from used import g\n\n\ndef h() -> int:\n    return g()\n", encoding="utf-8"
    )

    def errors() -> list[str]:
        output, _, _ = mypy_api.run(
            [
                "--config-file=mypy.ini",
                "--cache-dir=cache",
                "--no-error-summary",
                "used.py",
                "user.py",
                "wrong.py",
            ]
        )
        return sorted(line.split(":", 1)[0] for line in output.splitlines())

    assert errors() == ["wrong.py"]
    assert Path("cache").is_dir()
    assert errors() == ["wrong.py"]
    Path("used.py").write_text('def g() -> str:\n    return "1"\n', encoding="utf-8")
    assert errors() == ["user.py", "wrong.py"]


def test_each_leg_of_the_variants_does_only_what_it_alone_can_show() -> None:
    variants = (ROOT / ".github/workflows/variants.yml").read_text(encoding="utf-8")
    job = job_of(variants, "variant")
    # An update must give every file of the blueprint as a new repository has it, and
    # keeps .github/renovate.json5 of the project: the rules of Renovate are checked
    # in the new repository of each kind.
    update = step_of(
        job,
        "      - name: Render the project from the latest release and update it to this commit",
    )
    assert "the update gives it another content than a new repository has" in update
    renovate = step_of(
        job, "      - name: Validate the rules of Renovate of the project"
    )
    assert setting_of(renovate, "if") == "matrix.start == 'new'"
    # Both legs of a kind fill one cache of uv, with the tools of that kind.
    setup = step_of(job, "      - uses: astral-sh/setup-uv@")
    assert "          cache-suffix: ${{ matrix.kind }}\n" in setup
    # No action that builds an image of its own when the job starts.
    assert "uses: hadolint/" not in job


# The answers of each repository that takes the blueprint, by the name of the
# repository; the Rollout brings it every release.
ANSWERS = {
    path.stem: downstream.read(path)
    for path in sorted((ROOT / "tests/answers").glob("*.yml"))
}


def test_the_answers_are_those_of_each_repository_of_the_rollout() -> None:
    rollout = (ROOT / ".github/workflows/rollout.yml").read_text(encoding="utf-8")
    order = re.search(r"^          ORDER: (.+)$", rollout, re.M)
    assert order
    assert sorted(order[1].split()) == list(ANSWERS)
    for name, answers in ANSWERS.items():
        assert answers["owner"] == "Dennis-Otto", name
        assert answers["project_slug"] == name
        # Never Copier's own, which name the version of the repository and the source.
        assert not {"_commit", "_src_path"} & set(answers), name
    # A leg of the Variants for each, with the kind of project of its answers.
    variants = (ROOT / ".github/workflows/variants.yml").read_text(encoding="utf-8")
    legs = re.findall(
        r"^          - \{ kind: ([\w-]+), start: adopted, answers: ([\w.-]+) \}$",
        variants,
        re.M,
    )
    assert legs == [
        (answers["project_type"], name) for name, answers in ANSWERS.items()
    ]


@pytest.mark.parametrize("name", list(ANSWERS))
def test_the_answers_of_each_repository_render_every_file(
    tmp_path: Path, name: str
) -> None:
    project = render(tmp_path / name, **ANSWERS[name])
    for path in text_files(project):
        text = path.read_text(encoding="utf-8")
        assert not LEFTOVER.search(text), path
        assert text == "" or text.endswith("\n"), path
        assert not LEFTOVER.search(str(path.relative_to(project))), path
    # Each answer of the repository is one that the blueprint asks, and the
    # repository answers each question: a new question gets its answer here too.
    stored = downstream.read(project / ".copier-answers.yml")
    assert {k: v for k, v in stored.items() if not k.startswith("_")} == ANSWERS[name]
    # A repository that takes the blueprint brings its own code and tests.
    assert not stored["sample_code"]
    assert not (project / "docs/index.md").exists()


def test_the_adopted_legs_check_what_the_blueprint_alone_gives() -> None:
    variants = (ROOT / ".github/workflows/variants.yml").read_text(encoding="utf-8")
    job = job_of(variants, "variant")
    steps = ["      - " + step for step in job.split("\n      - ")[1:]]
    # The update with the answers of the repository, from the latest release.
    update = step_of(
        job,
        "      - name: Render the project from the latest release and update it to this commit",
    )
    assert setting_of(update, "if") == "matrix.start != 'new'"
    assert (
        '            data=(--data-file "$GITHUB_WORKSPACE/tests/answers/$ANSWERS.yml")\n'
        in update
    )
    assert "      ANSWERS: ${{ matrix.answers }}\n" in job
    # Its website, with the home page that the repository brings.
    website = step_of(job, "      - name: Build the website of the project")
    assert setting_of(website, "if") is None
    assert "> docs/index.md\n" in website
    # Only in the adopted legs: a new repository must bring its own.
    assert (
        '          if [[ -n "$ANSWERS" && ! -f docs/index.md && ! -f docs/README.md ]];'
        " then\n"
    ) in website
    # No tool of its own code, which it alone has.
    own = [
        step
        for step in steps
        if step.split("\n")[0]
        in (
            "      - name: Install the hash-pinned tools of the project",
            "      - name: Find the PHP of the tools and the oldest PHP of the app",
            "      - name: Set up the PHP of the tools",
            "      - name: Install the locked tools of the app",
            "      - name: Install the locked packages",
            "      - name: Lint the Dockerfile",
            "      - name: Run the checks of the project",
            "      - name: Validate the integration with hassfest",
        )
        or "uses: actions/setup-node@" in step.split("\n")[0]
        or "python-version-file: ${{ env.PROJECT }}" in step
    ]
    assert len(own) == 10
    for step in own:
        assert (setting_of(step, "if") or "").startswith("matrix.start != 'adopted'"), (
            step
        )
    # The lint of its workflows and of its Markdown, as in every leg.
    for name in ("Lint the workflows", "Lint the Markdown"):
        assert (
            setting_of(step_of(job, f"      - name: {name} of the project"), "if")
            is None
        )


# A file of the blueprint that a file of the template takes in.
INCLUDE = re.compile(r"""\[%-?\s*include\s+["']([^"']+)["']""")


def test_the_downstream_workflow_updates_each_repository_read_only() -> None:
    workflow = (ROOT / ".github/workflows/downstream.yml").read_text(encoding="utf-8")
    events = triggers(workflow)
    assert set(events) == {"pull_request", "schedule", "workflow_dispatch"}
    # In the pull requests that change what a repository gets from the blueprint.
    paths = paths_of(workflow, "pull_request")
    for pattern in (
        "copier.yml",
        "template/**",
        "includes/**",
        "stacks/**",
        "blueprint/**",
        "blueprint.py",
        ".github/**",
        "downstream.py",
        "tests/answers/**",
    ):
        assert pattern in paths, pattern
    # Every file that the template includes from the blueprint.
    included: set[str] = set()
    for file in (ROOT / "template").rglob("*"):
        if file.is_file():
            text = file.read_text(encoding="utf-8", errors="replace")
            included |= set(INCLUDE.findall(text))
    assert included
    for name in included:
        assert any(fnmatch.fnmatch(name, pattern) for pattern in paths), name
    assert "  contents: read\n" in workflow
    assert "write" not in workflow
    job = job_alone(workflow, "downstream")
    assert "          fetch-depth: 0\n          persist-credentials: false\n" in job
    # The Copier of the blueprint bots, which Renovate updates apart from the tools
    # of the tests.
    assert (
        "        run: uv pip install --system --require-hashes"
        " -r stacks/copier/requirements.txt\n"
    ) in job
    assert "          cache-dependency-glob: stacks/copier/requirements.txt\n" in job
    run = script_of(job, "Update every repository that takes the blueprint")
    assert 'arguments=(--head "$(git rev-parse HEAD)")\n' in run
    assert 'arguments+=(--base "$(git rev-parse HEAD^1)")\n' in run
    assert 'python3 downstream.py "${arguments[@]}"\n' in run
    assert job.endswith(explain_step("downstream"))
    # No required check: a conflict can be the right change.
    settings = tomllib.loads(
        (ROOT / ".github/repository.toml").read_text(encoding="utf-8")
    )
    assert "downstream" not in settings["branch"]["required_checks"]


def website_step(check: str) -> str:
    start = check.index('step "Website"')
    return check[start : check.index("if [[ -f scripts/check-project.sh ]]", start)]


@pytest.mark.parametrize("kind", KINDS)
def test_the_checks_build_the_website(projects: dict[str, Path], kind: str) -> None:
    check = (projects[kind] / "scripts/check.sh").read_text(encoding="utf-8")
    generic = (projects["generic"] / "scripts/check.sh").read_text(encoding="utf-8")

    # After the checks of the stack and before those of the project alone, the same
    # in every kind of project.
    website = check.index('\nstep "Website"\n')
    assert check.rindex('\nstep "') == website
    assert website < check.index("if [[ -f scripts/check-project.sh ]]")
    assert website_step(check) == website_step(generic)
    contributing = (projects[kind] / "CONTRIBUTING.md").read_text(encoding="utf-8")
    # On Windows with the launcher of python.org, which every install has, and not
    # with python, which can be the stub of the Microsoft Store.
    assert (
        "On Windows, use `py -3` in place of `python3` and `.venv-docs/Scripts/` in"
        " place of `.venv-docs/bin/`"
    ) in contributing
    assert "`bash scripts/check.sh` builds the website strictly as well" in contributing


# A MkDocs that records how the step calls it, and whether the folder it builds into
# is a new one under TMPDIR, and that fails like a strict build with a broken link
# when FAIL is set.
FAKE_MKDOCS = """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "${NO_MKDOCS_2_WARNING:-}" "$@" > "$CALLS"
if [[ "$4" == "$TMPDIR"/* && -d "$4" ]]; then
  echo "a new folder" >> "$CALLS"
fi
echo "<h1>Demo</h1>" > "$4/index.html"
if [[ -n "${BROKEN:-}" ]]; then
  echo '<html lang="en"><link rel="canonical" href="https://x.org/">' > "$4/index.html"
  echo '<html lang="en"><meta name="generator" content="mkdocs-1.6.1">' > "$4/guide.html"
fi
echo "INFO    -  Building documentation to directory: $4"
if [[ -n "${FAIL:-}" ]]; then
  echo "WARNING -  Doc file 'index.md' contains a link 'nowhere.md', but the target is not found."
  echo "Aborted with 1 warnings in strict mode!"
  exit 1
fi
"""


def run_the_website_step(
    projects: dict[str, Path],
    tmp_path: Path,
    mkdocs: str,
    pages: tuple[str, ...] = ("mkdocs.yml", "docs/index.md"),
    fail: bool = False,
    tool: bool = False,
    broken: bool = False,
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    """The step Website of scripts/check.sh, in a repository with these pages and a
    fake MkDocs at this place: in .venv-docs, in an activated environment (VIRTUAL_ENV
    and its folder), alone on the PATH, or nowhere ("")."""
    check = (projects["generic"] / "scripts/check.sh").read_text(encoding="utf-8")
    repository = tmp_path / "repository"
    (repository / "scripts").mkdir(parents=True)
    # Its set-up, such as set -euo pipefail and the folder it runs in, and the step.
    script = check[: check.index('step "Text files"')]
    if tool:
        # The Python and blueprint.py that the step Pages in one column found.
        script += (
            f"python={shlex.quote(Path(sys.executable).as_posix())}\n"
            f"tool={shlex.quote((ROOT / 'blueprint.py').as_posix())}\n"
        )
    script += website_step(check)
    (repository / "scripts/website.sh").write_text(
        script, encoding="utf-8", newline="\n"
    )
    for page in pages:
        (repository / page).parent.mkdir(parents=True, exist_ok=True)
        (repository / page).write_text("# Demo\n", encoding="utf-8", newline="\n")
    # The PATH without a MkDocs of this computer.
    path = [
        entry
        for entry in os.environ.get("PATH", os.defpath).split(os.pathsep)
        if not shutil.which("mkdocs", path=entry)
    ]
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in {"NO_MKDOCS_2_WARNING", "FAIL", "VIRTUAL_ENV"}
    }
    if mkdocs:
        if mkdocs == "PATH":
            fake = tmp_path / "bin/mkdocs"
            path.insert(0, str(fake.parent))
        elif mkdocs.startswith("VIRTUAL_ENV/"):
            # As its activation leaves it, in bash or in PowerShell on Windows.
            fake = tmp_path / "environment" / mkdocs.removeprefix("VIRTUAL_ENV/")
            environment["VIRTUAL_ENV"] = str(tmp_path / "environment")
            path.insert(0, str(fake.parent))
        else:
            fake = repository / mkdocs
        fake.parent.mkdir(parents=True, exist_ok=True)
        fake.write_text(FAKE_MKDOCS, encoding="utf-8", newline="\n")
        fake.chmod(0o755)
    temporary = tmp_path / "tmp"
    temporary.mkdir()
    calls = tmp_path / "calls"
    environment.update(
        PATH=os.pathsep.join(path), TMPDIR=str(temporary), CALLS=str(calls)
    )
    if fail:
        environment["FAIL"] = "1"
    if broken:
        environment["BROKEN"] = "1"
    assert BASH
    result = subprocess.run(
        [BASH, "scripts/website.sh"],
        cwd=repository,
        env=environment,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    return result, calls, temporary


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize(
    "mkdocs",
    [
        # The tools of the preview, as CONTRIBUTING.md and the dev container set
        # them up on Linux and macOS, and on Windows.
        ".venv-docs/bin/mkdocs",
        ".venv-docs/Scripts/mkdocs.exe",
        # The tools of an activated environment.
        "VIRTUAL_ENV/bin/mkdocs",
        "VIRTUAL_ENV/Scripts/mkdocs.exe",
    ],
)
def test_the_website_step_builds_the_website_strictly(
    projects: dict[str, Path], tmp_path: Path, mkdocs: str
) -> None:
    result, calls, temporary = run_the_website_step(projects, tmp_path, mkdocs)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "The website builds strictly." in result.stdout
    # Its log only when the build fails.
    assert "INFO" not in result.stdout + result.stderr
    recorded = calls.read_text(encoding="utf-8").splitlines()
    assert recorded[:4] == ["true", "build", "--strict", "--site-dir"]
    assert recorded[5:] == ["a new folder"]
    # The website goes again: nothing is left in the temporary folder.
    assert list(temporary.iterdir()) == []


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize("broken", [False, True])
def test_the_website_step_checks_what_the_hooks_promise(
    projects: dict[str, Path], tmp_path: Path, broken: bool
) -> None:
    # As the check docs checks it after the build, with blueprint.py site-check.
    result, _, temporary = run_the_website_step(
        projects, tmp_path, ".venv-docs/bin/mkdocs", tool=True, broken=broken
    )

    assert "The website builds strictly." in result.stdout
    if broken:
        assert result.returncode == 1
        assert "/guide.html: no canonical address\n" in result.stdout
        assert (
            "The website breaks what its hooks promise; the lines above name each"
            " file.\n"
        ) in result.stdout
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert "keeps what its hooks promise (one language).\n" in result.stdout
    assert list(temporary.iterdir()) == []


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
def test_the_website_step_shows_why_the_build_fails(
    projects: dict[str, Path], tmp_path: Path
) -> None:
    result, _, temporary = run_the_website_step(
        projects, tmp_path, ".venv-docs/bin/mkdocs", fail=True
    )

    assert result.returncode == 1
    assert "contains a link 'nowhere.md', but the target is not found" in result.stdout
    # Which MkDocs failed, and where to find how to install it again.
    assert (
        "The website fails to build strictly with .venv-docs/bin/mkdocs; the log above"
        " says why.\nTools that are out of date or incomplete install again as"
        " CONTRIBUTING.md shows.\n"
    ) in result.stdout
    assert "The website builds strictly." not in result.stdout
    assert list(temporary.iterdir()) == []


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize(
    ("mkdocs", "pages", "message"),
    [
        # Without the tools, as in the CI, whose check docs builds the website.
        (
            "",
            ("mkdocs.yml", "docs/index.md"),
            "MkDocs is not installed here; the CI builds the website.",
        ),
        # A MkDocs from elsewhere, such as Homebrew or pipx, has neither the theme nor
        # the plugins of the website, and would fail every check.
        (
            "PATH",
            ("mkdocs.yml", "docs/index.md"),
            "MkDocs is not installed here; the CI builds the website.",
        ),
        # Without a home page, as before the first page of a project without sample
        # code, or without mkdocs.yml: no website, as in the Docs workflow.
        (
            ".venv-docs/bin/mkdocs",
            ("mkdocs.yml",),
            "No website here: it needs mkdocs.yml and a home page, docs/index.md.",
        ),
        (
            ".venv-docs/bin/mkdocs",
            ("docs/index.md",),
            "No website here: it needs mkdocs.yml and a home page, docs/index.md.",
        ),
    ],
)
def test_the_website_step_passes_without_tools_or_website(
    projects: dict[str, Path],
    tmp_path: Path,
    mkdocs: str,
    pages: tuple[str, ...],
    message: str,
) -> None:
    result, calls, _ = run_the_website_step(projects, tmp_path, mkdocs, pages)

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == f"\n== Website\n{message}\n"
    assert not calls.exists()


@pytest.mark.parametrize("kind", KINDS)
def test_the_dev_container_sets_up_the_tools_of_the_website(
    projects: dict[str, Path], kind: str
) -> None:
    setup = (projects[kind] / ".devcontainer/setup.sh").read_text(encoding="utf-8")
    tools = setup[setup.index("if [[ -f mkdocs.yml ]]; then") :]

    assert "\n  python3 -m venv .venv-docs\n" in tools
    assert (
        "\n  .venv-docs/bin/pip install --require-hashes -r .github/docs-requirements.txt\n"
        in tools
    )
    # The images of the Python projects have Python; the others get its venv first.
    python = "python3-venv" not in tools
    assert python == (kind in {"home-assistant", "github-action", "python-package"})
    if not python:
        assert tools.index("sudo apt-get update") < tools.index("python3 -m venv")
    # Last, so that the hook of the checks is set up even when they fail to install.
    assert setup.index("git config core.hooksPath") < setup.index(".venv-docs")


def test_the_clean_up_bot_keeps_the_work_of_others() -> None:
    bot = (ROOT / ".github/workflows/cleanup.yml").read_text(encoding="utf-8")
    # Only a branch that main holds completely goes.
    assert bot.index('if [[ "$ahead" == 0 ]]; then') < bot.index("--method DELETE")
    for kept in ("release-please--*", "renovate/*", "dependabot/*"):
        assert kept in bot, kept


def test_a_release_is_built_in_isolation() -> None:
    workflows_dir = ROOT / ".github/workflows"
    release = (workflows_dir / "release.yml").read_text(encoding="utf-8")
    build = (workflows_dir / "build-release.yml").read_text(encoding="utf-8")
    assets = release[release.index("  assets:") : release.index("\n  publish:")]
    assert "uses: ./.github/workflows/build-release.yml" in assets
    # The build gets the tag, its commit and the version as inputs, nothing else of
    # the caller.
    assert "needs." not in build
    for name in ("tag", "sha", "version"):
        line = f"      {name}: ${{{{ needs.release-please.outputs.{name} }}}}\n"
        assert line in assets, name
    assert "workflow_call:" in build
    verify = (workflows_dir / "verify-release.yml").read_text(encoding="utf-8")
    assert 'build="$GH_REPO/.github/workflows/build-release.yml"' in verify
    # The build signs a Nextcloud app with the key of the environment release, which a
    # called workflow sees only with the secrets of its caller.
    assert "secrets: inherit" in assets
    assert "environment:\n      name: release" in build


def test_a_release_left_as_a_draft_is_finished_by_hand() -> None:
    release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    job = release[release.index("  release-please:") : release.index("\n  assets:")]
    step = job[
        job.index("id: resume") : job.index("- name: Write the text of Unreleased and")
    ]
    assert "github.event_name == 'workflow_dispatch'" in step
    assert "--json isDraft" in step
    for output in ("created", "tag", "sha", "version", "major"):
        line = next(
            line for line in job.splitlines() if line.strip().startswith(f"{output}:")
        )
        assert "steps.resume.outputs." in line, output


# What each kind of release ships, which its SBOMs describe: the files of its package,
# as an archive in the assets, and what lies beside it that the SBOMs leave out.
PACKAGES: dict[str, dict[str, dict[str, str] | None]] = {
    "hacs": {"demo.zip": {"manifest.json": "{}\n", "sensor.py": ""}},
    "pypi": {
        "demo-1.2.3-py3-none-any.whl": {
            "demo/__init__.py": "",
            "demo-1.2.3.dist-info/METADATA": "Name: demo\nVersion: 1.2.3\n",
        },
        # The sources, which build the same files as the wheel.
        "demo-1.2.3.tar.gz": {"demo-1.2.3/PKG-INFO": ""},
    },
    "npm": {"demo-1.2.3.tgz": {"package/package.json": "{}\n"}},
    "nextcloud-appstore": {
        "demo.tar.gz": {"demo/appinfo/info.xml": "<info/>\n"},
        "demo.tar.gz.sig": None,
    },
}
SHIPPED = {
    "hacs": ["manifest.json", "sensor.py"],
    "pypi": ["demo-1.2.3.dist-info/METADATA", "demo/__init__.py"],
    "npm": ["package/package.json"],
    "nextcloud-appstore": ["demo/appinfo/info.xml"],
}
# The tree of the tag of a project that ships its sources, with what only checks,
# tests and documents it, the tools of the blueprint among them.
SOURCES = {
    "action.yml": "runs: {}\n",
    "demo.py": "",
    "requirements.txt": "requests==2.32.5\n",
    "requirements-dev.txt": "pytest==9.0.0\n",
    "requirements-fuzz.txt": "atheris==2.3.0\n",
    "requirements-test.in": "pytest\n",
    "requirements-images.txt": "playwright==1.55.0\n",
    "stacks/docs/requirements-docs.txt": "mkdocs==1.6.1\n",
    ".devcontainer/devcontainer.json": "{}\n",
    ".githooks/pre-push": "",
    ".github/workflows/ci.yml": "on: push\n",
    ".github/docs-requirements.txt": "mkdocs==1.6.1\n",
    "changelog.d/x.md": "",
    "docs/index.md": "",
    "fuzz/fuzz_demo.py": "",
    "scripts/check.sh": "",
    "test/demo.test.ts": "",
    "tests/test_demo.py": "",
}


def archive(path: Path, files: dict[str, str] | None) -> None:
    """A zip, a wheel or a gzipped tar of the files, by the name of path; a file that
    is no archive without them."""
    if files is None:
        path.write_bytes(b"a signature\n")
    elif path.suffix in (".zip", ".whl"):
        with zipfile.ZipFile(path, "w") as zipped:
            for name, text in files.items():
                zipped.writestr(name, text)
    else:
        with tarfile.open(path, "w:gz") as tarred:
            for name, text in files.items():
                data = text.encode()
                info = tarfile.TarInfo(name)
                info.size = len(data)
                tarred.addfile(info, io.BytesIO(data))


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize("publish_to", [*PACKAGES, "github-action", "ghcr", "none", ""])
def test_the_sboms_describe_what_a_release_ships(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, publish_to: str
) -> None:
    build = (ROOT / ".github/workflows/build-release.yml").read_text(encoding="utf-8")
    # The checkout of the tag, with a file that the tag doesn't have.
    checkout = tmp_path / "checkout"
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for name, text in SOURCES.items():
        (checkout / name).parent.mkdir(parents=True, exist_ok=True)
        (checkout / name).write_text(text, encoding="utf-8", newline="\n")
    for arguments in (
        ["init", "--quiet"],
        ["add", "--all"],
        ["-c", "user.name=A", "-c", "user.email=a@example.com", "commit", "-qm", "v"],
    ):
        subprocess.run(["git", *arguments], cwd=checkout, check=True)
    (checkout / "build").mkdir()
    (checkout / "build/demo.tar.gz").write_bytes(b"not a release\n")
    assets = tmp_path / "assets"
    assets.mkdir()
    for name, files in PACKAGES.get(publish_to, {}).items():
        archive(assets / name, files)

    # The paths relative to the checkout, which the tar of Git for Windows takes, where
    # it reads the C: of an absolute path as the name of a host.
    result, _ = run_workflow_step(
        tmp_path,
        script_of(build, "Unpack what the release ships"),
        checkout,
        {"python3": f'exec "{Path(sys.executable).as_posix()}" "$@"\n'},
        RUNNER_TEMP="../temp",
        ASSETS="../assets",
        PUBLISH_TO=publish_to,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    package = tmp_path / "temp/package"
    # Only what its users install; an action, an image or a project without a package
    # ships the sources of its tag, without the tools of its checks, its website and
    # its workflows.
    assert sorted(files_of(package)) == SHIPPED.get(
        publish_to, ["action.yml", "demo.py", "requirements.txt"]
    )


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
def test_a_release_without_its_package_gets_no_sboms(tmp_path: Path) -> None:
    build = (ROOT / ".github/workflows/build-release.yml").read_text(encoding="utf-8")
    (tmp_path / "assets").mkdir()

    result, _ = run_workflow_step(
        tmp_path,
        script_of(build, "Unpack what the release ships"),
        tmp_path,
        {},
        RUNNER_TEMP="temp",
        ASSETS="assets",
        PUBLISH_TO="pypi",
    )

    assert result.returncode == 1
    assert "::error::The release has no package for its SBOMs to describe." in (
        result.stdout
    )


# A stand-in for syft, in the archive of its release: it writes the root of each SBOM
# as syft does, by the name and version that it is given or by those of $ROOT, and one
# package, $PACKAGE, of the same version.
FAKE_SYFT = """\
#!/usr/bin/env bash
echo "syft $*" >> "$CALLS"
outputs=()
while (($#)); do
  case "$1" in
    --source-name) name="$2"; shift ;;
    --source-version) version="$2"; shift ;;
    --output) outputs+=("$2"); shift ;;
  esac
  shift
done
read -r name version <<<"${ROOT:-$name $version}"
root="SPDXRef-DocumentRoot-Directory-$name"
for output in "${outputs[@]}"; do
  case "$output" in
    spdx-json=*)
      printf '{"packages": [{"SPDXID": "SPDXRef-Package-x", "name": "%s", "versionInfo": "%s"},
        {"SPDXID": "%s", "name": "%s", "versionInfo": "%s"}], "relationships": [{"spdxElementId":
        "SPDXRef-DOCUMENT", "relatedSpdxElement": "%s", "relationshipType": "DESCRIBES"}]}\\n' \\
        "${PACKAGE:-x}" "$version" "$root" "$name" "$version" "$root" > "${output#*=}" ;;
    cyclonedx-json=*)
      printf '{"metadata": {"component": {"type": "file", "name": "%s", "version": "%s"}}}\\n' \\
        "$name" "$version" > "${output#*=}" ;;
  esac
done
"""


def describe_the_release(
    tmp_path: Path, publish_to: str, **variables: str
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    """Runs the step that writes the SBOMs, with the stand-in for syft in the archive
    of its release, which curl downloads and the step checks by its sha256."""
    build = (ROOT / ".github/workflows/build-release.yml").read_text(encoding="utf-8")
    pin = dict(re.findall(r"(SBOM_SYFT_(?:VERSION|SHA256)): (\S+)", build))
    release = tmp_path / "release.tar.gz"
    with tarfile.open(release, "w:gz") as tarred:
        data = FAKE_SYFT.encode()
        info = tarfile.TarInfo("syft")
        info.size = len(data)
        info.mode = 0o755
        tarred.addfile(info, io.BytesIO(data))
    for folder in ("temp", "assets"):
        (tmp_path / folder).mkdir()
    return run_workflow_step(
        tmp_path,
        script_of(build, "Describe it in the SBOMs, as SPDX and as CycloneDX"),
        tmp_path,
        {
            "curl": textwrap.dedent(
                """\
                while (($# > 0)); do
                  if [[ "$1" == --output ]]; then cp release.tar.gz "$2"; fi
                  shift
                done
                """
            )
        },
        **{
            "RUNNER_TEMP": "temp",
            "ASSETS": "assets",
            "PUBLISH_TO": publish_to,
            "NAME": "demo",
            "VERSION": "1.2.3",
            "SUPPLIER": "Someone",
            "SBOM_SYFT_VERSION": pin["SBOM_SYFT_VERSION"],
            "SBOM_SYFT_SHA256": hashlib.sha256(release.read_bytes()).hexdigest(),
            **variables,
        },
    )


@WITH_JQ
@pytest.mark.parametrize(
    ("publish_to", "catalogers"),
    [
        ("hacs", "image"),
        ("pypi", "image"),
        ("npm", "image"),
        ("nextcloud-appstore", "image"),
        ("github-action", "directory"),
        ("ghcr", "directory"),
        ("none", "directory"),
    ],
)
def test_the_sboms_name_the_release_by_its_version(
    tmp_path: Path, publish_to: str, catalogers: str
) -> None:
    result, calls = describe_the_release(tmp_path, publish_to)

    assert result.returncode == 0, result.stdout + result.stderr
    (download,) = [call for call in calls if call.startswith("curl ")]
    assert "/anchore/syft/releases/download/v" in download
    # A package lists what it installs, as an image does; sources what they declare.
    (scan,) = [call for call in calls if call.startswith("syft ")]
    assert scan == (
        f"syft scan dir:temp/package --quiet --override-default-catalogers {catalogers}"
        " --source-name demo --source-version 1.2.3 --source-supplier Someone"
        " --output spdx-json=assets/demo.spdx.json"
        " --output cyclonedx-json=assets/demo.cdx.json"
    )
    for name in ("demo.spdx.json", "demo.cdx.json"):
        assert (tmp_path / "assets" / name).is_file(), name


@WITH_JQ
@pytest.mark.parametrize(
    ("root", "package"),
    [
        # The folder of the repository, as the SBOMs of the releases before named it.
        (". 1.2.3", "x"),
        ("demo 1.2.2", "x"),
        # A package of the name and version of the release that isn't the root.
        ("other 1.2.3", "demo"),
    ],
)
def test_the_build_stops_at_an_sbom_that_does_not_name_the_release(
    tmp_path: Path, root: str, package: str
) -> None:
    result, _ = describe_the_release(tmp_path, "pypi", ROOT=root, PACKAGE=package)

    assert result.returncode == 1
    assert "::error::The SBOMs don't name the release demo 1.2.3 at their root" in (
        result.stdout
    )


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
def test_the_build_stops_at_a_syft_that_is_not_its_release(tmp_path: Path) -> None:
    result, calls = describe_the_release(tmp_path, "pypi", SBOM_SYFT_SHA256="0" * 64)

    assert result.returncode != 0
    assert not [call for call in calls if call.startswith("syft ")]


def test_the_sboms_of_a_release_are_checked_by_its_name_and_version() -> None:
    workflows = ROOT / ".github/workflows"
    build = (workflows / "build-release.yml").read_text(encoding="utf-8")
    verify = (workflows / "verify-release.yml").read_text(encoding="utf-8")
    describe = "Describe it in the SBOMs, as SPDX and as CycloneDX"
    write = script_of(build, describe)
    check = script_of(verify, "Verify the release as its users can")

    def filters(script: str) -> list[str]:
        return re.findall(r"^(?:spdx|cyclonedx)='.*?'$", script, re.DOTALL | re.M)

    # The build checks the SBOMs as the verification does, before the release is
    # immutable, so the tests of the build cover both.
    assert len(filters(write)) == 2
    assert filters(write) == filters(check)
    assert "for sbom in *.spdx.json *.cdx.json; do" in check
    assert 'name="${GH_REPO#*/}"' in check
    assert check.index('version="${TAG#v}"') < check.index("for sbom in")
    assert check.index('version="${TAG#v}"') < check.index('case "$PUBLISH_TO" in')
    # The name of the repository and the version of the release, in the build too.
    step = step_of(build, f"      - name: {describe}")
    assert "          NAME: ${{ github.event.repository.name }}\n" in step
    assert "          VERSION: ${{ inputs.version }}\n" in step
    # syft comes from its release, checked by its sha256, into the job that may write
    # the release; no action downloads its installer there.
    assert "anchore/sbom-action" not in build
    assert "sha256sum --check --strict" in write
    # After the package is built and before the assets are attested.
    order = [
        "      - name: Build and sign the Nextcloud app\n",
        "      - name: Unpack what the release ships\n",
        f"      - name: {describe}\n",
        "      - name: Write the advisories that don't affect the release\n",
        "      - name: Attest the provenance of every asset\n",
    ]
    assert [build.index(name) for name in order] == sorted(
        build.index(name) for name in order
    )
    # The advisories that don't affect the release name it as its SBOMs do, by the
    # default of the CLI: the tag without its v, as release.yml tags it. No --version,
    # which the blueprint.py of an older tag rejects when its draft is finished by hand.
    vex = script_of(build, "Write the advisories that don't affect the release")
    assert ' vex "$GITHUB_REPOSITORY" "$TAG" ' in vex
    assert "--version" not in vex
    assert 'tag="v$version"' in (ROOT / ".github/workflows/release.yml").read_text(
        encoding="utf-8"
    )


# Fragments of the changelog: the check of a pull request and the release bot.
FEATURE_FRAGMENT = "### Features\n\n- **Dark mode:** the settings follow the system.\n"
FIX_FRAGMENT = "### Bug fixes\n\n- **Token:** stays secret.\n"
MAIN_CHANGELOG = (
    "# Changelog\n\n## Unreleased\n\n### Features\n\n- **Voices:** a game by voice.\n\n"
    "## 1.2.2\n\n### Bug fixes\n\n- An older fix.\n"
)
RELEASE_BRANCH = "release-please--branches--main"


class Step(NamedTuple):
    """What a step did with the fake gh: its result, the calls of gh, its summary, its
    outputs and what gh was given to write."""

    result: subprocess.CompletedProcess[str]
    calls: list[str]
    summary: str
    output: str
    written: dict[str, str]


def run_a_step_with_the_fake_gh(
    tmp_path: Path, script: str, answers: dict[str, object], **variables: str
) -> Step:
    """Runs the script of a step in tmp_path/checkout, as GitHub runs it, with the fake
    gh, the Python of the tests as python3, a sleep that only notes its seconds in
    tmp_path/slept, and $RUNNER_TEMP in tmp_path/temp."""
    checkout = tmp_path / "checkout"
    checkout.mkdir(exist_ok=True)
    (tmp_path / "step.sh").write_text(script, encoding="utf-8", newline="\n")
    folders = {name: tmp_path / name for name in ("bin", "answers", "written", "temp")}
    for folder in folders.values():
        folder.mkdir()
    for key, answer in answers.items():
        (folders["answers"] / re.sub(r"[/ ?]", "_", key)).write_text(
            answer if isinstance(answer, str) else json.dumps(answer),
            encoding="utf-8",
            newline="\n",
        )
    for tool, body in {
        "gh": FAKE_GH,
        "python3": f'#!/usr/bin/env bash\nexec "{Path(sys.executable).as_posix()}" "$@"\n',
        "sleep": f'#!/usr/bin/env bash\necho "$*" >> "{(tmp_path / "slept").as_posix()}"\n',
    }.items():
        (folders["bin"] / tool).write_text(body, encoding="utf-8", newline="\n")
        (folders["bin"] / tool).chmod(0o755)
    files = {name: tmp_path / name for name in ("calls", "summary", "output")}
    for file in files.values():
        file.touch()
    assert BASH
    result = subprocess.run(
        [BASH, "-e", str(tmp_path / "step.sh")],
        cwd=checkout,
        env={
            **os.environ,
            "PATH": f"{folders['bin']}{os.pathsep}{os.environ['PATH']}",
            "GH_REPO": "o/r",
            "RUNNER_TEMP": str(folders["temp"]),
            "GITHUB_STEP_SUMMARY": str(files["summary"]),
            "GITHUB_OUTPUT": str(files["output"]),
            "CALLS": str(files["calls"]),
            "ANSWERS": str(folders["answers"]),
            "WRITTEN": str(folders["written"]),
            **variables,
        },
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    return Step(
        result,
        files["calls"].read_text(encoding="utf-8").splitlines(),
        files["summary"].read_text(encoding="utf-8"),
        files["output"].read_text(encoding="utf-8"),
        {
            path.name: path.read_text(encoding="utf-8")
            for path in folders["written"].iterdir()
        },
    )


def a_checkout_with_the_tool(tmp_path: Path, **fragments: str) -> Path:
    """The checkout of main: blueprint.py, CHANGELOG.md and the fragments."""
    checkout = tmp_path / "checkout"
    (checkout / "blueprint").mkdir(parents=True)
    for name in TOOL:
        shutil.copy(ROOT / name, checkout / name)
    (checkout / "CHANGELOG.md").write_text(MAIN_CHANGELOG, encoding="utf-8")
    (checkout / "changelog.d").mkdir()
    (checkout / "changelog.d/.gitkeep").touch()
    for name, text in fragments.items():
        (checkout / "changelog.d" / name).write_text(text, encoding="utf-8")
    return checkout


def pull_request_files(*files: tuple[str, str]) -> list[dict[str, str]]:
    """The files of a pull request as the API lists them: each name and its status."""
    return [{"filename": name, "status": status} for name, status in files]


def changelog_check() -> str:
    title = (ROOT / ".github/workflows/pull-request-title.yml").read_text(
        encoding="utf-8"
    )
    # A step of the check of the title.
    return job_alone(title, "title")


def test_the_changelog_check_reads_the_fragments_with_the_code_of_main() -> None:
    job = changelog_check()
    permissions = job[job.index("    permissions:\n") : job.index("    steps:\n")]
    # Writes only the labels of the pull request, which the title sets.
    assert [
        line.strip() for line in permissions.splitlines()[1:] if "#" not in line
    ] == ["contents: read", "issues: write", "pull-requests: write"]
    # The default branch, sparse, without credentials, and only for fragments or for
    # the PR coach after a failure.
    checkout = job[job.index("      - uses: actions/checkout@") :]
    checkout = checkout[: checkout.index("      - name:")]
    assert (
        "        if: ${{ !cancelled() && "
        "(steps.entry.outputs.fragments == 'true' || failure()) }}\n"
    ) in checkout
    assert "          persist-credentials: false\n" in checkout
    assert (
        "          sparse-checkout: |\n            .github\n            blueprint\n"
        in (checkout)
    )
    assert "ref:" not in checkout
    # The values of the event reach the scripts as variables only.
    for step in (
        "Require an entry in the changelog for a change for users",
        "Check the fragments as the release takes them in",
    ):
        assert "${{" not in script_of(job, step), step
    # The job may write, so the parser of the fragments, which the pull request
    # controls, never sees the token.
    script = script_of(job, "Check the fragments as the release takes them in")
    assert 'env -u GH_TOKEN python3 "$script" fragments' in script
    assert script.count("python3 ") == 1


@WITH_JQ
@pytest.mark.parametrize(
    ("title", "author", "files", "code", "message", "fragments"),
    [
        ("docs: a guide", "User", [], 0, "changes nothing for users", []),
        ("feat: a card", "Bot", [], 0, "Updates and bots write no entry.", []),
        ("fix(deps): bump", "User", [], 0, "Updates and bots write no entry.", []),
        # Whatever the type or the author, the release reads every fragment, so a
        # pull request that needs no entry still has its fragments checked.
        (
            "docs: a guide",
            "User",
            [("changelog.d/guide.md", "added"), ("CHANGELOG.md", "modified")],
            0,
            "changes nothing for users",
            ["changelog.d/guide.md"],
        ),
        (
            "docs: a guide",
            "User",
            [("changelog.d/README.md", "added"), ("changelog.d/notes.txt", "added")],
            1,
            '::error::"changelog.d/notes.txt" is no fragment of the changelog.',
            [],
        ),
        (
            "feat: a card",
            "Bot",
            [("changelog.d/my fix.md", "added")],
            1,
            '::error::"changelog.d/my fix.md" is no fragment of the changelog.',
            [],
        ),
        (
            "chore(deps): bump",
            "User",
            [(f"changelog.d/f{number}.md", "added") for number in range(21)],
            1,
            "::error title=Too many fragments::This pull request adds 21 fragments of "
            "the changelog;",
            [],
        ),
        (
            "feat: a card",
            "User",
            [("CHANGELOG.md", "modified"), ("src/app.py", "added")],
            0,
            "CHANGELOG.md has the entry of this change.",
            [],
        ),
        (
            "fix!: the token",
            "User",
            [
                ("changelog.d/token.md", "added"),
                ("changelog.d/dark_mode.v2.md", "modified"),
                ("src/app.py", "modified"),
            ],
            0,
            "::warning file=changelog.d/dark_mode.v2.md,title=The entry of another "
            "pull request::main has changelog.d/dark_mode.v2.md already",
            ["changelog.d/token.md", "changelog.d/dark_mode.v2.md"],
        ),
        # A fragment that main has already is the entry of another pull request, which
        # this one would take over, or push out of the release: it is checked, but it
        # is no entry of this pull request.
        (
            "feat: a card",
            "User",
            [("changelog.d/ci.md", "modified")],
            1,
            "::warning file=changelog.d/ci.md,title=The entry of another pull "
            "request::main has changelog.d/ci.md already",
            [],
        ),
        (
            "fix: the token",
            "User",
            [("changelog.d/token-2.md", "renamed"), ("src/app.py", "modified")],
            1,
            "::error title=No entry in the changelog::Describe what changes",
            [],
        ),
        (
            "fix: the token",
            "User",
            [("changelog.d/ci.md", "modified"), ("CHANGELOG.md", "modified")],
            0,
            "CHANGELOG.md has the entry of this change.",
            ["changelog.d/ci.md"],
        ),
        (
            "perf: a faster start",
            "User",
            [("changelog.d/ci.md", "modified"), ("changelog.d/faster.md", "copied")],
            0,
            "::warning file=changelog.d/ci.md,",
            ["changelog.d/ci.md", "changelog.d/faster.md"],
        ),
        (
            "docs: a guide",
            "User",
            [("changelog.d/ci.md", "modified")],
            0,
            "::warning file=changelog.d/ci.md,",
            ["changelog.d/ci.md"],
        ),
        # A hidden file, a fragment that goes, and other files are no entry.
        (
            "feat: a card",
            "User",
            [
                ("changelog.d/.gitkeep", "added"),
                ("changelog.d/old.md", "removed"),
                ("docs/changelog.md", "added"),
            ],
            1,
            "::error title=No entry in the changelog::Describe what changes for users "
            "in a new file of changelog.d/",
            [],
        ),
        # A file of changelog.d/ that the release can't read is named, as JSON.
        (
            "perf: faster",
            "User",
            [
                ("changelog.d/notes.txt", "added"),
                ("changelog.d/my fix.md", "added"),
                ("changelog.d/two\nlines.md", "added"),
                ("changelog.d/sub/x.md", "added"),
                ("changelog.d/fine.md", "added"),
            ],
            1,
            '::error::"changelog.d/notes.txt" is no fragment of the changelog.',
            [],
        ),
        (
            "feat: many",
            "User",
            [(f"changelog.d/f{number}.md", "added") for number in range(21)],
            1,
            "::error title=Too many fragments::This pull request adds 21 fragments of "
            "the changelog;",
            [],
        ),
    ],
)
def test_the_changelog_check_takes_an_entry_in_changelog_md_or_a_fragment(
    tmp_path: Path,
    title: str,
    author: str,
    files: list[tuple[str, str]],
    code: int,
    message: str,
    fragments: list[str],
) -> None:
    step = run_a_step_with_the_fake_gh(
        tmp_path,
        script_of(
            changelog_check(),
            "Require an entry in the changelog for a change for users",
        ),
        {"repos/o/r/pulls/7/files": pull_request_files(*files)},
        NUMBER="7",
        TITLE=title,
        AUTHOR=author,
    )

    assert step.result.returncode == code, step.result.stderr
    assert message in step.result.stdout + step.summary
    assert ("fragments=true" in step.output) == bool(fragments)
    listed = tmp_path / "temp/fragments"
    assert (listed.read_text(encoding="utf-8").splitlines() if fragments else []) == (
        fragments
    )
    # Every pull request has its files listed, to check its fragments.
    assert len(step.calls) == 1
    assert step.calls[0].startswith("api repos/o/r/pulls/7/files --paginate --jq ")
    # Only a change for users of a person needs an entry, and is told it has one.
    required = bool(re.match(r"(feat|fix|perf)!?: ", title)) and author == "User"
    if not required:
        assert "Describe what changes" not in step.result.stdout
        assert "CHANGELOG.md has the entry" not in step.summary
    # Each fragment that main has already, changed or renamed here, is named in a
    # warning, and is no entry of this pull request.
    name = re.compile(r"changelog\.d/[A-Za-z0-9][A-Za-z0-9._-]*\.md")
    theirs = [
        path
        for path, status in files
        if status in ("modified", "renamed") and name.fullmatch(path)
    ]
    warnings = [
        line for line in step.result.stdout.splitlines() if line.startswith("::warning")
    ]
    assert [warning.split(",")[0] for warning in warnings] == [
        f"::warning file={path}" for path in theirs
    ]
    for warning in warnings:
        assert "describe the change of this pull request in a new fragment" in warning
    # Every failure says in the summary what to do about it.
    if code:
        assert step.summary.strip()
    if "::error title=No entry in the changelog::" in step.result.stdout:
        assert (
            "Add a new file to `changelog.d/`, named after the branch without its type, "
            "such as `changelog.d/dark-mode.md` for the branch `feat/dark-mode`"
            in step.summary
        )
        assert "\n```markdown\n### Features\n\n- **Dark mode:**" in step.summary
        assert ("they don't count as its own" in step.summary) == bool(theirs)
    if "::error title=Too many fragments::" in step.result.stdout:
        assert "Put its entries into one fragment, or a few" in step.summary
    if title == "perf: faster":
        errors = [
            line for line in step.result.stdout.splitlines() if "::error::" in line
        ]
        assert [error.split(" is no fragment")[0] for error in errors] == [
            '::error::"changelog.d/notes.txt"',
            '::error::"changelog.d/my fix.md"',
            '::error::"changelog.d/two\\nlines.md"',
            '::error::"changelog.d/sub/x.md"',
        ]


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize(
    ("title", "author"), [("chore(deps): bump", "Bot"), ("feat: a card", "User")]
)
def test_the_changelog_check_asks_github_three_times_for_the_files(
    tmp_path: Path, title: str, author: str
) -> None:
    # The check is required of every pull request, those of bots included, so a
    # moment in which GitHub fails doesn't fail it at once.
    step = run_a_step_with_the_fake_gh(
        tmp_path,
        script_of(
            changelog_check(),
            "Require an entry in the changelog for a change for users",
        ),
        {"repos/o/r/pulls/7/files.error": "gh: Bad Gateway (HTTP 502)\n"},
        NUMBER="7",
        TITLE=title,
        AUTHOR=author,
    )

    assert step.result.returncode == 1
    assert len(step.calls) == 3
    assert all(call.startswith("api repos/o/r/pulls/7/files ") for call in step.calls)
    assert (tmp_path / "slept").read_text(encoding="utf-8").split() == ["10", "20"]
    assert (
        "::error::GitHub did not list the files of this pull request. Run the check "
        "again." in step.result.stdout
    )
    assert "fragments=true" not in step.output


# In the copy of the mutation tests, the tool is the code with the mutants, which the
# variables of mutmut switch in the process that this test starts.
@pytest.mark.mutation_unsafe
@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize(
    ("fragments", "code", "summary", "errors"),
    [
        (
            {"dark-mode.md": FEATURE_FRAGMENT, "token.md": FIX_FRAGMENT},
            0,
            "The 2 fragment(s) in changelog.d/ are fine.\n",
            [],
        ),
        (
            {"dark-mode.md": FEATURE_FRAGMENT, "typo.md": "### Fixes\n\n- A fix.\n"},
            1,
            "The release can't take in these fragments of the changelog:\n\n"
            "- changelog.d/typo.md: `### Fixes` is no kind of change of the changelog.",
            [
                "::error file=changelog.d/typo.md,title=The fragment of the changelog::"
                "`### Fixes` is no kind of change of the changelog. Did you mean "
                "`### Fixed`?"
            ],
        ),
    ],
)
def test_the_changelog_check_checks_each_fragment_as_the_release_takes_it_in(
    tmp_path: Path,
    fragments: dict[str, str],
    code: int,
    summary: str,
    errors: list[str],
) -> None:
    # main has the tool and the changelog; the fragments come from the pull request.
    a_checkout_with_the_tool(tmp_path)
    step_script = script_of(
        changelog_check(), "Check the fragments as the release takes them in"
    )
    # As the step before writes it, with LF on every system.
    (tmp_path / "listed").write_text(
        "".join(f"changelog.d/{name}\n" for name in fragments),
        encoding="utf-8",
        newline="\n",
    )
    step = run_a_step_with_the_fake_gh(
        tmp_path,
        f'cp "{(tmp_path / "listed").as_posix()}" "$RUNNER_TEMP/fragments"\n'
        + step_script,
        {
            f"repos/o/r/contents/changelog.d/{name}?ref=abc123": text
            for name, text in fragments.items()
        },
        HEAD_SHA="abc123",
    )

    assert step.result.returncode == code, step.result.stderr
    assert step.summary.startswith(summary)
    found = [
        line for line in step.result.stdout.splitlines() if line.startswith("::error")
    ]
    assert len(found) == len(errors)
    for line, error in zip(found, errors, strict=True):
        assert line.startswith(error), line
    assert step.calls == [
        "api -H Accept: application/vnd.github.raw+json "
        f"repos/o/r/contents/changelog.d/{name}?ref=abc123"
        for name in fragments
    ]


def release_please_answers(branch: str, listed: list[str] | None) -> dict[str, object]:
    """What GitHub answers the release bot: the release pull request of 1.3.0, the
    changelog that release-please wrote on its branch, and the fragments there."""
    answers: dict[str, object] = {
        "pr list": [{"headRefName": RELEASE_BRANCH}],
        f"repos/o/r/git/ref/heads/{RELEASE_BRANCH}": {"object": {"sha": "abc123"}},
        "repos/o/r/contents/.release-please-manifest.json?ref=abc123": {".": "1.3.0"},
        "repos/o/r/contents/CHANGELOG.md?ref=abc123": branch,
        "graphql": {"data": {"createCommitOnBranch": {"commit": {"oid": "def456"}}}},
    }
    folder = "repos/o/r/contents/changelog.d?ref=abc123"
    if listed is None:
        answers[f"{folder}.error"] = "gh: Not Found (HTTP 404)\n"
    else:
        answers[folder] = [{"path": f"changelog.d/{name}"} for name in listed]
    return answers


def release_branch_changelog(main: str) -> str:
    """What release-please writes on the branch: its section before the last one."""
    index = main.index("## 1.2.2")
    return f"{main[:index]}## [1.3.0](https://x/compare/v1.2.2...v1.3.0) (2026-10-13)\n\n### Features\n\n* a card\n\n{main[index:]}"


# In the copy of the mutation tests, the tool is the code with the mutants, which the
# variables of mutmut switch in the process that this test starts.
@pytest.mark.mutation_unsafe
@WITH_JQ
@pytest.mark.parametrize(
    ("fragments", "listed", "deleted"),
    [
        # Every fragment that the release takes in leaves with the same commit.
        (
            ["a-dark-mode.md", "b-token.md"],
            [".gitkeep", "a-dark-mode.md", "b-token.md"],
            ["a-dark-mode.md", "b-token.md"],
        ),
        # Only those that the branch still has.
        (
            ["a-dark-mode.md", "b-token.md"],
            [".gitkeep", "a-dark-mode.md"],
            ["a-dark-mode.md"],
        ),
        # A branch without the folder has none, and without fragments nobody asks.
        (["a-dark-mode.md"], None, []),
        ([], [".gitkeep"], []),
    ],
)
def test_the_release_bot_writes_the_fragments_into_the_release_and_deletes_them(
    tmp_path: Path, fragments: list[str], listed: list[str] | None, deleted: list[str]
) -> None:
    texts = {"a-dark-mode.md": FEATURE_FRAGMENT, "b-token.md": FIX_FRAGMENT}
    a_checkout_with_the_tool(tmp_path, **{name: texts[name] for name in fragments})
    branch = release_branch_changelog(MAIN_CHANGELOG)
    release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    step = run_a_step_with_the_fake_gh(
        tmp_path,
        script_of(
            release,
            "Write the text of Unreleased and of the fragments into the release pull request",
        ),
        release_please_answers(branch, listed),
        PR="",
    )

    assert step.result.returncode == 0, step.result.stderr
    assert (
        f"Writing the changelog of 1.3.0 into {RELEASE_BRANCH}." in step.result.stdout
    )
    mutation = json.loads(step.written["input"])["variables"]["input"]
    assert mutation["branch"] == {
        "repositoryNameWithOwner": "o/r",
        "branchName": RELEASE_BRANCH,
    }
    assert mutation["expectedHeadOid"] == "abc123"
    assert mutation["message"] == {"headline": "chore: write the changelog of 1.3.0"}
    changes = mutation["fileChanges"]
    [addition] = changes["additions"]
    assert addition["path"] == "CHANGELOG.md"
    written = base64.b64decode(addition["contents"]).decode("utf-8")
    assert written == release_changelog(
        "1.3.0",
        MAIN_CHANGELOG,
        branch,
        [Fragment(f"changelog.d/{name}", texts[name]) for name in fragments],
    )
    assert changes.get("deletions", []) == [
        {"path": f"changelog.d/{name}"} for name in deleted
    ]
    asked = [call for call in step.calls if "contents/changelog.d?" in call]
    assert len(asked) == (1 if fragments else 0)


# In the copy of the mutation tests, the tool is the code with the mutants, which the
# variables of mutmut switch in the process that this test starts.
@pytest.mark.mutation_unsafe
@WITH_JQ
def test_the_release_bot_leaves_a_release_that_is_written_already(
    tmp_path: Path,
) -> None:
    a_checkout_with_the_tool(tmp_path, **{"b-token.md": FIX_FRAGMENT})
    branch = release_branch_changelog(MAIN_CHANGELOG)
    fragments = [Fragment("changelog.d/b-token.md", FIX_FRAGMENT)]
    written = release_changelog("1.3.0", MAIN_CHANGELOG, branch, fragments)
    release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    script = script_of(
        release,
        "Write the text of Unreleased and of the fragments into the release pull request",
    )

    # Written and without the fragment: nothing to do.
    done = run_a_step_with_the_fake_gh(
        tmp_path, script, release_please_answers(written, [".gitkeep"]), PR=""
    )
    assert done.result.returncode == 0, done.result.stderr
    assert "The changelog of 1.3.0 is up to date." in done.result.stdout
    assert "input" not in done.written


# In the copy of the mutation tests, the tool is the code with the mutants, which the
# variables of mutmut switch in the process that this test starts.
@pytest.mark.mutation_unsafe
@WITH_JQ
def test_the_release_bot_stops_when_it_cannot_see_the_fragments_of_the_branch(
    tmp_path: Path,
) -> None:
    a_checkout_with_the_tool(tmp_path, **{"b-token.md": FIX_FRAGMENT})
    answers = release_please_answers(release_branch_changelog(MAIN_CHANGELOG), [])
    answers.pop("repos/o/r/contents/changelog.d?ref=abc123")
    answers["repos/o/r/contents/changelog.d?ref=abc123.error"] = (
        "gh: Server Error (HTTP 502)\n"
    )
    release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    step = run_a_step_with_the_fake_gh(
        tmp_path,
        script_of(
            release,
            "Write the text of Unreleased and of the fragments into the release pull request",
        ),
        answers,
        PR="",
    )

    # Rather no commit than a release whose fragments stay for the next one as well.
    assert step.result.returncode != 0
    assert "HTTP 502" in step.result.stderr
    assert "input" not in step.written


@pytest.mark.parametrize("kind", KINDS)
def test_every_repository_gets_the_folder_of_the_fragments(
    projects: dict[str, Path], kind: str
) -> None:
    project = projects[kind]
    assert (project / "changelog.d/.gitkeep").read_text(encoding="utf-8") == ""
    contributing = (project / "CONTRIBUTING.md").read_text(encoding="utf-8")
    for text in (
        # A branch such as feat/dark-mode has a slash, which no fragment's name has.
        "named after your branch without its type, such as `changelog.d/dark-mode.md` "
        "for the branch `feat/dark-mode`",
        "### The changelog",
        "`bash scripts/check.sh` checks every fragment as the release takes it in, "
        "those that wait on `main` for the next release too, with "
        "`python3 .github/blueprint.py fragments`.",
        "The check of the title, *conventional title*, takes only a new fragment as "
        "the entry of a pull request",
    ):
        assert text in contributing, text
    template = (project / ".github/pull_request_template.md").read_text(
        encoding="utf-8"
    )
    assert "a new file in `changelog.d/`" in template
    # The blueprint follows its template.
    assert (ROOT / "changelog.d/.gitkeep").read_text(encoding="utf-8") == ""


def test_release_tags_are_signed_and_verified_with_one_gitsign() -> None:
    sign = (ROOT / ".github/sign-tag.sh").read_text(encoding="utf-8")
    verify = (ROOT / ".github/workflows/verify-release.yml").read_text(encoding="utf-8")
    version = re.search(r"^version=(\S+)$", sign, re.MULTILINE)
    digest = re.search(r"^sha256=([0-9a-f]{64})$", sign, re.MULTILINE)
    assert version
    assert digest
    assert f"GITSIGN_VERSION: {version[1]}" in verify
    assert f"GITSIGN_SHA256: {digest[1]}" in verify
    release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    job = release[release.index("  release-please:") : release.index("\n  assets:")]
    assert "id-token: write" in job
    # The signed tag is there before release-please creates the release on it.
    assert job.index('bash .github/sign-tag.sh "$tag" "$commit"') < job.index(
        "googleapis/release-please-action"
    )


def test_every_release_run_signs_the_tag_of_a_merged_release() -> None:
    release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    start = release.index("      - name: Sign the tag of a release")
    step = release[start : release.index("      - name:", start + 1)]
    # Not only the push of the merge, which can be lost: the next run, a schedule or a
    # dispatch, signs the tag before release-please creates the release on it.
    assert "        if: steps.app.outputs.token != ''\n" in step
    assert "event_name" not in step
    assert "head_commit" not in step
    # The merged release pull requests come from the list of pull requests, which
    # doesn't lag behind a merge as their search does.
    assert 'pullRequests(labels: ["autorelease: pending"], states: MERGED' in step
    assert "gh pr list" not in step
    # A tag that exists already must be the signed one at the commit of the merge,
    # which sign-tag.sh checks (tests/test_sign_tag.py).
    assert 'bash .github/sign-tag.sh "$tag" "$commit"' in step
    # release-please creates a release only on a tag that the step signed: never on a
    # tag of its own, without a signature, for a release pull request merged after the
    # step looked, or in a run without the release app.
    assert "        id: sign\n" in step
    assert '          echo "signed=true" >> "$GITHUB_OUTPUT"\n' in step
    please = release[release.index("        id: release\n") :]
    please = please[: please.index("      - name:")]
    assert "googleapis/release-please-action@" in please
    skip = "skip-github-release: ${{ steps.sign.outputs.signed != 'true' }}"
    assert f"          {skip}\n" in please


def test_the_build_checks_the_tag_before_it_builds() -> None:
    build = (ROOT / ".github/workflows/build-release.yml").read_text(encoding="utf-8")
    inputs = build[build.index("    inputs:") : build.index("permissions:")]
    assert (
        "      sha:\n"
        "        description: The commit that the tag has to point at\n"
        "        required: true\n"
    ) in inputs
    step = build[
        build.index("      - name: Verify the tag before building") : build.index(
            "actions/checkout@"
        )
    ]
    # The script of the commit that runs the workflow, not the one of the tag.
    assert "contents/.github/sign-tag.sh?ref=$GITHUB_SHA" in step
    assert 'bash "$RUNNER_TEMP/sign-tag.sh" verify "$TAG" "$SHA"' in step
    assert "SHA: ${{ inputs.sha }}" in step
    release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    # The release at the merge, a beta at the commit of the run, and a draft taken up
    # at the last commit that changed the version.
    outputs = ("release", "beta", "resume")
    line = " || ".join(f"steps.{step}.outputs.sha" for step in outputs)
    assert f"      sha: ${{{{ {line} }}}}\n" in release
    assert 'echo "sha=$GITHUB_SHA"\n' in release
    manifest = "commits?path=.release-please-manifest.json&sha=$GITHUB_SHA&per_page=1"
    assert manifest in release


def test_a_release_of_a_scheduled_run_is_verified_in_full() -> None:
    # Called by the release workflow, verify-release.yml has the event of its run,
    # which may be its daily schedule; only its own weekly run is lenient.
    verify = (ROOT / ".github/workflows/verify-release.yml").read_text(encoding="utf-8")
    weekly = "github.event_name == 'schedule' && inputs.tag == ''"
    assert f"          WEEKLY: ${{{{ {weekly} }}}}\n" in verify
    assert "GITHUB_EVENT_NAME" not in verify
    assert verify.count('[[ "$WEEKLY" == true ]]') == 5
    release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    job = release[release.index("\n  verify:") :]
    assert "uses: ./.github/workflows/verify-release.yml" in job
    assert "      tag: ${{ needs.release-please.outputs.tag }}" in job


@pytest.mark.parametrize("kind", KINDS)
def test_the_code_of_a_project_meets_mutants_every_week(
    projects: dict[str, Path], kind: str
) -> None:
    project = projects[kind]
    mutation = project / ".github/workflows/mutation.yml"
    tools = project / ".github/mutation-requirements.txt"
    contributing = (project / "CONTRIBUTING.md").read_text(encoding="utf-8")
    # The plan, the parts and the report of the run, in the tool of every repository.
    assert (project / ".github/blueprint/mutation.py").is_file()
    python = kind in ("home-assistant", "python-package", "github-action")
    # How a contributor kills a survivor, or keeps mutmut away from a text.
    assert ("`# pragma: no mutate`" in contributing) == python
    assert ("`@pytest.mark.mutation_unsafe`" in contributing) == python
    # A block pragma on a line of its own reaches to the end of its block.
    assert (
        "`# pragma: no mutate start` … `# pragma: no mutate end`" in contributing
    ) == (python)
    assert ("up to the end of the block it stands in" in contributing) == python
    assert "\n\n\n" not in contributing
    if python:
        assert mutation.is_file()
        assert "mutmut==" in tools.read_text(encoding="utf-8")
    elif kind == "nextcloud-app":
        assert mutation.is_file()
        assert not tools.exists()
    else:
        assert not mutation.exists()


def mutation_step(name: str, kind: str) -> str:
    """The script of a step of the Mutation workflow for one kind of code, or with
    no kind of one that runs for every kind, as the plan and the report do."""
    workflow = (ROOT / ".github/workflows/mutation.yml").read_text(encoding="utf-8")
    condition = rf"        if: .*== '{kind}'\n" if kind else ""
    step = re.search(
        rf"      - name: {re.escape(name)}\n{condition}"
        r"(?:        (?!run: \|).*\n)*        run: \|\n((?:          .*\n|\n)+)",
        workflow,
    )
    assert step, name
    return textwrap.dedent(step[1])


def run_mutation_step(
    tmp_path: Path, name: str, kind: str, tools: dict[str, str], **variables: str
) -> tuple[int, str]:
    """Runs a step of the Mutation workflow in tmp_path/project as GitHub does, with
    stand-ins for its tools; the exit code and what it wrote to the summary."""
    step = tmp_path / "step.sh"
    step.write_text(mutation_step(name, kind), encoding="utf-8", newline="\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for tool, script in tools.items():
        (bin_dir / tool).write_text(
            f"#!/usr/bin/env bash\n{script}", encoding="utf-8", newline="\n"
        )
        (bin_dir / tool).chmod(0o755)
    (tmp_path / "temp").mkdir(exist_ok=True)
    summary = tmp_path / "summary"
    summary.touch()
    environment = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "RUNNER_TEMP": (tmp_path / "temp").as_posix(),
        "GITHUB_ENV": (tmp_path / "env").as_posix(),
        "GITHUB_STEP_SUMMARY": summary.as_posix(),
        "MUTMUT_LIMIT": "1m",
        # Not those of the part that runs the mutation tests of the blueprint.
        "PATTERNS": "",
        **variables,
    }
    # As GitHub runs a step: bash -e.
    assert BASH
    result = subprocess.run(
        [BASH, "-e", step.as_posix()],
        cwd=tmp_path / "project",
        env=environment,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    return result.returncode, summary.read_text(encoding="utf-8")


def mutmut_list(config: configparser.ConfigParser, key: str) -> list[str]:
    """A list of setup.cfg as mutmut 3 reads it: one item on each line, else the whole
    value as one item."""
    value = config.get("mutmut", key)
    return [item for item in value.split("\n") if item] if "\n" in value else [value]


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize(
    ("files", "paths"),
    [
        # The modules of the root and its packages, as in the blueprint, but not the
        # tests and not the settings tool in .github/.
        (
            [
                "blueprint/__init__.py",
                "blueprint.py",
                "dashboard.py",
                "weekly.py",
                "conftest.py",
                "tests/__init__.py",
                ".github/blueprint/__init__.py",
            ],
            ["blueprint", "blueprint.py", "dashboard.py", "weekly.py"],
        ),
        (["src/demo/__init__.py", "tests/test_demo.py"], ["src"]),
        (
            ["custom_components/demo/__init__.py", "tests/test_init.py"],
            ["custom_components"],
        ),
    ],
)
def test_mutmut_mutates_the_code_of_every_kind_of_project(
    tmp_path: Path, files: list[str], paths: list[str]
) -> None:
    project = tmp_path / "project"
    others = ["pyproject.toml", "docs/index.md", ".github/workflows/mutation.yml"]
    for name in [*files, *others, ".git/HEAD"]:
        (project / name).parent.mkdir(parents=True, exist_ok=True)
        (project / name).touch()
    calls = tmp_path / "calls"

    code, _ = run_mutation_step(
        tmp_path,
        "Run the mutants against the tests",
        "python",
        {"mutmut": 'echo "$*" >> "$CALLS"\n'},
        CALLS=calls.as_posix(),
    )

    assert code == 0
    config = configparser.ConfigParser()
    config.read(project / "setup.cfg", encoding="utf-8")
    # Not "blueprint,blueprint.py,dashboard.py,weekly.py": mutmut 3 takes that for one
    # path, which it doesn't find, and mutates nothing.
    assert mutmut_list(config, "source_paths") == paths
    # The tests may read any file of the repository; Git stays the checkout's own.
    copied = mutmut_list(config, "also_copy")
    assert {".github", "docs", "pyproject.toml", "tests"} <= set(copied)
    assert not {".git", "setup.cfg"} & set(copied)
    assert mutmut_list(config, "pytest_add_cli_args") == ["-m", "not mutation_unsafe"]
    # One part runs every mutant.
    assert re.fullmatch(r"run --max-children \d+\n", calls.read_text(encoding="utf-8"))
    # The plan splits what the step mutates.
    assert default_paths(project) == paths


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
def test_a_part_runs_the_mutants_of_its_code(tmp_path: Path) -> None:
    (tmp_path / "project").mkdir()
    calls = tmp_path / "calls"

    code, _ = run_mutation_step(
        tmp_path,
        "Run the mutants against the tests",
        "python",
        {"mutmut": 'printf "%s\\n" "$@" > "$CALLS"\n'},
        CALLS=calls.as_posix(),
        PATTERNS="demo.x_*\ndemo.xǁ*",
    )

    assert code == 0
    # Each name a word of its own, as mutmut run takes them.
    assert calls.read_text(encoding="utf-8").splitlines()[-2:] == [
        "demo.x_*",
        "demo.xǁ*",
    ]


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("setup.cfg", "[mutmut]\nsource_paths=lib\n"),
        ("pyproject.toml", '[tool.mutmut]\nsource_paths = ["lib"]\n'),
    ],
)
def test_mutmut_keeps_the_configuration_of_a_project(
    tmp_path: Path, name: str, text: str
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / name).write_text(text, encoding="utf-8")

    code, _ = run_mutation_step(
        tmp_path, "Run the mutants against the tests", "python", {"mutmut": "true\n"}
    )

    assert code == 0
    assert (project / name).read_text(encoding="utf-8") == text
    assert (project / "setup.cfg").exists() == (name == "setup.cfg")


MUTANTS = """\
    demo.x_add__mutmut_1: killed
    demo.x_add__mutmut_2: survived
    demo.x_add__mutmut_3: no tests
"""
# Stand-ins for the module of mutmut, which shows a survivor, and for its command,
# which lists the results.
SHOW = """\
import sys

print(f"# {sys.argv[2]}: survived")
print("--- demo.py\\n+++ demo.py\\n@@ -1,2 +1,2 @@\\n def add(a, b):")
print("-    return a + b\\n+    return a - b")
"""
MUTMUT = """\
case "$1" in
  results) printf '%s' "$RESULTS" ;;
esac
"""
PYTHON = f'exec "{Path(sys.executable).as_posix()}" "$@"\n'
# The output of mutmut, whose spinner redraws the line of each phase with \r, when a
# test fails without any mutant.
FAILING = (
    "⠋ Generating mutants\r⠙ Generating mutants\r⠇ Generating mutants\n"
    "    done in 597ms (2 files mutated, 0 ignored, 0 unmodified)\n"
    "⠋ Running stats\r⠹ Running stats\n"
    "FAILED tests/test_fixes.py::test_one - AssertionError: assert 1 == 2\n"
    "failed to collect stats. runner returned 1\n"
)


def with_the_tool(project: Path) -> None:
    """The project with blueprint.py in .github/, as a repository has it."""
    (project / ".github").mkdir(parents=True)
    shutil.copy(ROOT / "blueprint.py", project / ".github/blueprint.py")
    shutil.copytree(
        ROOT / "blueprint",
        project / ".github/blueprint",
        ignore=shutil.ignore_patterns("__pycache__", "*.meta"),
    )


# In the copy of the mutation tests, the tool is the code with the mutants, which the
# variables of mutmut switch in the process that this test starts.
@pytest.mark.mutation_unsafe
@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
def test_the_plan_splits_the_code_into_parts(tmp_path: Path) -> None:
    project = tmp_path / "project"
    with_the_tool(project)
    for name, text in {
        ".python-version": "3.12\n",
        ".github/mutation-requirements.txt": "mutmut==3.8.0\n",
        "demo.py": "def add(a, b):\n    return a + b\n",
        "other.py": "def sub(a, b):\n    return a - b\n",
    }.items():
        (project / name).write_text(text, encoding="utf-8")
    output = tmp_path / "output"

    code, summary = run_mutation_step(
        tmp_path,
        "Split the code into parts of about the same number of mutants",
        "",
        {"python3": PYTHON},
        GITHUB_OUTPUT=output.as_posix(),
        PARTS="2",
    )

    assert code == 0
    lines = output.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "kind=python"
    parts = json.loads(lines[1].removeprefix("parts="))
    assert [part["patterns"] for part in parts] == [
        "demo.x_*\ndemo.xǁ*",
        "other.x_*\nother.xǁ*",
    ]
    assert summary == ""
    (project / ".python-version").unlink()
    code, summary = run_mutation_step(
        tmp_path,
        "Split the code into parts of about the same number of mutants",
        "",
        {"python3": PYTHON},
        GITHUB_OUTPUT=output.as_posix(),
    )
    assert code == 0
    assert summary == "No mutation tool for this kind of project yet.\n"


# In the copy of the mutation tests, the tool is the code with the mutants, which the
# variables of mutmut switch in the process that this test starts.
@pytest.mark.mutation_unsafe
@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize(
    ("results", "output", "code", "expected"),
    [
        (MUTANTS, "done\n", 0, ""),
        # The tests that fail without any mutant, in the summary of the part.
        (
            "    demo.x_add__mutmut_1: not checked\n",
            FAILING,
            1,
            "**The tests fail without any mutant.** mutmut first runs the tests once",
        ),
        # No output at all, as when the installation failed.
        ("", None, 1, "No mutant ran. The end of the output of mutmut:\n"),
    ],
)
def test_a_part_keeps_its_results_and_the_change_of_each_survivor(
    tmp_path: Path, results: str, output: str | None, code: int, expected: str
) -> None:
    project = tmp_path / "project"
    with_the_tool(project)
    (tmp_path / "temp").mkdir()
    # The module of mutmut, which the step runs on the Python that has it.
    (tmp_path / "modules").mkdir()
    (tmp_path / "modules/mutmut.py").write_text(SHOW, encoding="utf-8")
    if output is not None:
        (tmp_path / "temp/run.txt").write_text(output, encoding="utf-8", newline="\n")

    exit_code, summary = run_mutation_step(
        tmp_path,
        "Keep the results of this part and the change of each survivor",
        "python",
        {"python3": PYTHON, "mutmut": MUTMUT},
        RESULTS=results,
        PYTHONPATH=(tmp_path / "modules").as_posix(),
        PART="2",
        PARTS="3",
        PATTERNS="demo.x_*\ndemo.xǁ*",
    )

    assert exit_code == code
    assert expected in summary
    assert "⠋" not in summary
    part = json.loads((tmp_path / "temp/part/part-2.json").read_text(encoding="utf-8"))
    assert (part["part"], part["parts"]) == (2, 3)
    if code == 0:
        assert summary == ""
        assert part["survivors"] == [
            {
                "name": "demo.x_add__mutmut_2",
                "kind": "logic",
                "diff": " def add(a, b):\n-    return a + b\n+    return a - b",
            }
        ]
    elif output:
        assert "- `tests/test_fixes.py::test_one`\n" in summary
        assert "⠇ Generating mutants\n" in summary
        # The artifact of the part keeps the whole output, without the spinner.
        kept = (tmp_path / "temp/part/run-2.txt").read_text(encoding="utf-8")
        assert kept.startswith("⠇ Generating mutants\n")
        assert kept.endswith("failed to collect stats. runner returned 1\n")


# In the copy of the mutation tests, the tool is the code with the mutants, which the
# variables of mutmut switch in the process that this test starts.
@pytest.mark.mutation_unsafe
@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize("measured", [True, False])
def test_the_report_puts_the_parts_together(tmp_path: Path, measured: bool) -> None:
    project = tmp_path / "project"
    with_the_tool(project)
    parts = tmp_path / "temp/parts"
    parts.mkdir(parents=True)
    results = {"demo.x_add__mutmut_1": "killed", "demo.x_add__mutmut_2": "survived"}
    if measured:
        for number, (name, state) in enumerate(results.items(), 1):
            part = {
                "part": number,
                "parts": 2,
                "status": 0,
                "generated": 2,
                "results": {name: state},
                "survivors": [{"name": name, "kind": "text", "diff": "-'a'\n+'b'"}]
                if state == "survived"
                else [],
            }
            (parts / f"part-{number}.json").write_text(
                json.dumps(part), encoding="utf-8"
            )

    code, summary = run_mutation_step(
        tmp_path,
        "Report the score and the surviving mutants",
        "",
        {"python3": PYTHON},
        GITHUB_REPOSITORY="Someone/demo",
        RUN_URL="https://github.com/Someone/demo/actions/runs/1",
        ISSUE="false",
    )

    assert summary.startswith("### Mutation tests (mutmut)\n")
    data = json.loads(
        (tmp_path / "temp/mutation/mutation.json").read_text(encoding="utf-8")
    )
    if measured:
        assert code == 0
        assert "**50.0 %** of the mutants were noticed by a test" in summary
        assert "in 2 parts" in summary
        assert data["score"] == 50.0
        assert data["run"] == "https://github.com/Someone/demo/actions/runs/1"
        # What the dashboard reads.
        results_text = (tmp_path / "temp/mutation/results.txt").read_text(
            encoding="utf-8"
        )
        assert results_text == (
            "    demo.x_add__mutmut_1: killed\n    demo.x_add__mutmut_2: survived\n"
        )
    else:
        # A run that measures nothing fails.
        assert code == 1
        assert "No mutant ran." in summary
        assert data["complete"] is False


def test_the_parts_and_the_report_hand_on_their_results() -> None:
    workflow = (ROOT / ".github/workflows/mutation.yml").read_text(encoding="utf-8")
    jobs = {
        name: workflow[start:]
        for name, start in (
            (match[1], match.start())
            for match in re.finditer(r"^  (\w+):\n", workflow, re.M)
        )
    }
    plan, mutation, report = jobs["plan"], jobs["mutation"], jobs["report"]
    issue = jobs["issue"]
    plan = plan[: plan.index("\n  mutation:")]
    mutation = mutation[: mutation.index("\n  report:")]
    report = report[: report.index("\n  # The one issue")]
    # The plan gives the matrix of the parts, one job each.
    assert "      parts: ${{ steps.plan.outputs.parts }}\n" in plan
    assert "PARTS: ${{ vars.MUTATION_PARTS }}" in plan
    assert "        include: ${{ fromJSON(needs.plan.outputs.parts) }}\n" in mutation
    assert "      fail-fast: false\n" in mutation
    assert "          PATTERNS: ${{ matrix.patterns }}\n" in mutation
    # Each part hands its results to the report, which puts them together also when a
    # part failed, and keeps the artifact that the dashboard and the next run read.
    assert "          name: mutation-part-${{ matrix.part }}\n" in mutation
    assert "    needs: [plan, mutation]\n" in report
    assert (
        "    if: ${{ !cancelled() && needs.plan.outputs.kind == 'python' }}\n" in report
    )
    assert (
        "          pattern: mutation-part-*\n          path: ${{ runner.temp }}/parts\n"
        in report
    )
    assert "          merge-multiple: true\n" in report
    assert '--name mutation --dir "$RUNNER_TEMP/previous"' in report
    assert '--previous "$RUNNER_TEMP/previous/mutation.json"' in report
    assert (
        "          name: mutation\n          path: ${{ runner.temp }}/mutation/\n"
        in report
    )
    # The weekly run compares with the one before; an artifact lives 90 days at most.
    assert "          retention-days: 90\n" in report
    # Only the job of the issue writes, the one issue of the default branch, and never
    # on a pull request, whose code the report runs.
    for job in (plan, mutation, report):
        assert "      contents: read\n" in job
        assert "write" not in job
    assert "      actions: read\n" in report
    assert "    name: mutation plan\n" in plan
    assert "    name: mutation report\n" in report
    assert "    name: mutation issue\n" in issue
    assert "    needs: report\n" in issue
    assert (
        "    if: ${{ needs.report.result == 'success' && (github.event_name == "
        "'schedule' || (github.event_name == 'workflow_dispatch' && github.ref_name "
        "== github.event.repository.default_branch)) }}\n"
    ) in issue
    assert "    permissions:\n      contents: read\n      issues: write\n" in issue
    assert (
        "          name: mutation\n          path: ${{ runner.temp }}/mutation\n"
        in (issue)
    )
    assert 'mutation issue "$RUNNER_TEMP/mutation"' in issue
    assert workflow.count("issues: write") == 1


# The end of the output of Infection.
INFECTION = """\
40 mutations were generated:
      35 mutants were killed by Test Framework
       5 covered mutants were not detected

Metrics:
         Mutation Score Indicator (MSI): 87%
         Mutation Code Coverage: 100%
         Covered Code MSI: 87%
"""


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize("bootstrap", [True, False])
def test_infection_runs_with_the_bootstrap_of_the_tests(
    tmp_path: Path, bootstrap: bool
) -> None:
    project = tmp_path / "project"
    (project / "tests").mkdir(parents=True)
    if bootstrap:
        (project / "tests/bootstrap.php").touch()
    calls = tmp_path / "calls"

    code, _ = run_mutation_step(
        tmp_path,
        "Run the mutants against the tests",
        "php",
        {"php": 'echo "$*" > "$CALLS"\nprintf "%s" "$OUTPUT"\n'},
        CALLS=calls.as_posix(),
        OUTPUT=INFECTION,
    )

    assert code == 0
    config = json.loads((project / "infection.json5").read_text(encoding="utf-8"))
    # The classes of Nextcloud, which Infection loads with the code of the app.
    assert config.get("bootstrap") == ("tests/bootstrap.php" if bootstrap else None)
    assert config["source"] == {"directories": ["lib"]}
    assert config["logs"]["summary"] == "build/infection-summary.log"
    # The score of the output, which no log of Infection has, for the dashboard.
    output = (project / "build/infection-output.log").read_text(encoding="utf-8")
    assert "Covered Code MSI: 87%" in output
    call = calls.read_text(encoding="utf-8")
    # A low score fails nothing, whatever minimum the project's configuration sets.
    assert " --min-msi=0 --min-covered-msi=0 " in call
    # The plain text that the report and the dashboard read, without colors.
    assert " --no-ansi " in call


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
def test_an_error_of_infection_fails_the_run(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "infection.json5").write_text("{}\n", encoding="utf-8")
    failing = "echo 'This application requires a PHP version matching \"^8.3\".' >&2\nexit 1\n"

    code, _ = run_mutation_step(
        tmp_path, "Run the mutants against the tests", "php", {"php": failing}
    )

    # Not hidden by the tail of its output, which succeeds.
    assert code == 1
    output = (project / "build/infection-output.log").read_text(encoding="utf-8")
    assert "requires a PHP version" in output
    assert (project / "infection.json5").read_text(encoding="utf-8") == "{}\n"


# The end of the output of Infection when its configuration finds no code to change;
# it ends well with a minimum score of 0.
NO_MUTANTS = """\
0 mutations were generated:
       0 mutants were killed by Test Framework

Metrics:
         Mutation Score Indicator (MSI): 0%
         Mutation Code Coverage: 0%
         Covered Code MSI: 0%

No mutations were generated for the selected code. Set a minimum MSI score to make this outcome fail.
"""


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize(
    ("output", "code", "expected"),
    [
        (
            INFECTION,
            0,
            "- Mutation Score Indicator (MSI): 87%\n- Mutation Code Coverage: 100%\n"
            "- Covered Code MSI: 87%\n",
        ),
        # A run that measures nothing fails: an error of Infection, no mutant, or
        # no output at all, as when its installation failed.
        (
            'Class "OCP\\AppFramework\\App" not found\n',
            1,
            'Infection reported no score. The end of its output:\n\n```text\nClass "OCP',
        ),
        (
            NO_MUTANTS,
            1,
            "Infection reported no score. The end of its output:\n\n```text\n"
            "0 mutations were generated:\n",
        ),
        (
            None,
            1,
            "Infection reported no score. The end of its output:\n\n```text\n```\n",
        ),
        # A later Infection that names its score in other words.
        (
            INFECTION.replace("Covered Code MSI", "Score"),
            1,
            "Infection reported no score.",
        ),
    ],
)
def test_the_score_of_infection_or_why_it_has_none(
    tmp_path: Path, output: str | None, code: int, expected: str
) -> None:
    build = tmp_path / "project/build"
    build.mkdir(parents=True)
    if output is not None:
        (build / "infection-output.log").write_text(output, encoding="utf-8")
    (build / "infection-summary.log").write_text("Total: 40\n", encoding="utf-8")

    exit_code, summary = run_mutation_step(tmp_path, "Report the score", "php", {})

    assert exit_code == code
    assert summary.startswith("### Mutation tests (Infection)\n")
    assert expected in summary
    assert summary.endswith("```text\nTotal: 40\n```\n")


def test_infection_gets_a_php_that_it_runs_on() -> None:
    # Infection 0.35 needs PHP 8.3, newer than the oldest PHP of a Nextcloud app and
    # than the PHP of the tools of an app that hasn't moved them to PHP 8.3 yet.
    workflow = (ROOT / ".github/workflows/mutation.yml").read_text(encoding="utf-8")
    assert "INFECTION_VERSION: 0.35." in workflow
    find = step_of(workflow, "      - name: Find the PHP of the tools\n")
    setup = step_of(workflow, "      - name: Set up the PHP of the tools\n")
    assert workflow.index(find) < workflow.index(setup)
    assert workflow.index(setup) < workflow.index("composer install")
    assert "        id: php\n" in find
    assert "          php-version: ${{ steps.php.outputs.version }}\n" in setup
    # No PHP of its own beside that of the tools.
    assert workflow.count("uses: shivammathur/setup-php@") == 1
    assert 'php-version: "' not in workflow


@pytest.mark.skipif(BASH is None, reason="the step runs in bash, Git Bash on Windows")
@pytest.mark.parametrize(
    ("platform", "expected"),
    [
        # A new app: its tools on PHP 8.3.
        ({"php": "8.3.16"}, "version=8.3\n"),
        # An app that moved its tools to a newer PHP runs the mutants on it.
        ({"php": "8.4.1"}, "version=8.4\n"),
        ({"php": "9.0"}, "version=9.0\n"),
        # An app whose tools are older still gets the PHP that Infection needs.
        ({"php": "8.2.27"}, "version=8.3\n"),
        ({}, "version=8.3\n"),
    ],
)
def test_the_mutants_run_on_the_php_of_the_tools(
    tmp_path: Path, platform: dict[str, str], expected: str
) -> None:
    workflow = (ROOT / ".github/workflows/mutation.yml").read_text(encoding="utf-8")
    script = script_of(workflow, "Find the PHP of the tools")
    app = tmp_path / "app"
    app.mkdir()
    config: dict[str, object] = {"sort-packages": True}
    if platform:
        config["platform"] = platform
    manifest = {"require": {"php": "^8.2"}, "config": config}
    (app / "composer.json").write_text(json.dumps(manifest), encoding="utf-8")
    output = tmp_path / "output"
    output.touch()

    result, _ = run_workflow_step(
        tmp_path,
        script,
        app,
        # The Python of the tests, not one that the PATH of Windows names.
        {"python3": f'exec "{Path(sys.executable).as_posix()}" "$@"\n'},
        GITHUB_OUTPUT=output.as_posix(),
    )

    assert result.returncode == 0, result.stderr
    assert output.read_text(encoding="utf-8") == expected


def test_a_pull_request_that_changes_how_the_mutants_run_tries_them() -> None:
    workflow = (ROOT / ".github/workflows/mutation.yml").read_text(encoding="utf-8")
    events = workflow[workflow.index("\non:\n") : workflow.index("\npermissions:")]
    for path in (
        ".github/workflows/mutation.yml",
        ".github/mutation-requirements.txt",
        "stacks/mutation/requirements.txt",
    ):
        assert f"      - {path}\n" in events, path
    # mutmut for 25 minutes in each part, every week for hours; it keeps the mutants
    # it reached. Each part first copies the code and runs every test, which took
    # 13 minutes of the 15 that a part of the blueprint had. Infection reports at its
    # end only.
    limit = re.search(r"\n      MUTMUT_LIMIT: \$\{\{ (.+) \}\}\n", workflow)
    assert limit
    assert limit[1] == "github.event_name == 'pull_request' && '25m' || '320m'"
    assert workflow.count('timeout "$MUTMUT_LIMIT" mutmut run ') == 1
    assert (
        "timeout-minutes: ${{ github.event_name == 'pull_request' && 40 || 350 }}"
        in workflow
    )


@pytest.mark.parametrize("kind", ["home-assistant", "github-action", "python-package"])
def test_a_test_can_stay_out_of_the_mutation_tests(
    projects: dict[str, Path], kind: str
) -> None:
    def marker(path: Path) -> list[str]:
        config = tomllib.loads(path.read_text(encoding="utf-8"))
        markers: list[str] = config["tool"]["pytest"]["ini_options"]["markers"]
        return [line for line in markers if line.startswith("mutation_unsafe: ")]

    assert marker(ROOT / "pyproject.toml")
    assert marker(projects[kind] / "pyproject.toml") == marker(ROOT / "pyproject.toml")
