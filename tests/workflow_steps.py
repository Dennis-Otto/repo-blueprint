"""Runs a step of a workflow as GitHub does, with a fake gh, for the tests of the bots.

A bot of the blueprint is mostly bash in the `run:` of a step: it deletes branches,
starts workflows, merges pull requests and comments. run_step() takes that script from
the parsed workflow and runs it in bash, with the options that GitHub runs it with, in
folders of the test for the workspace and $RUNNER_TEMP, and with the files of
$GITHUB_STEP_SUMMARY, $GITHUB_OUTPUT and $GITHUB_ENV. The variables of the step come
from its `env:`, those of the job and of the workflow: a value without an expression as
it is, one of a known context, such as `${{ github.repository }}`, as the test runner
sets it, and every other from the test, which fails without it. gh is
tests/fake_gh.py, which answers as the test planned and writes down every call, and
other commands can be stubs. acting_steps() finds the steps that change something on
GitHub, which tests/test_workflow_steps.py makes sure a test runs.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from shell import BASH, in_bash

ROOT = Path(__file__).parents[1]
FAKE_GH = Path(__file__).with_name("fake_gh.py")

# The values of the run that every step sees, as the runner sets them.
REPOSITORY = "o/r"
SHA = "abc1234def5678abc1234def5678abc1234def56"
RUN_ID = "5"
RUN_URL = f"https://github.com/{REPOSITORY}/actions/runs/{RUN_ID}"
TOKEN = "the-token"
CONTEXTS = {
    "github.repository": REPOSITORY,
    "github.repository_owner": REPOSITORY.split("/")[0],
    "github.sha": SHA,
    "github.run_id": RUN_ID,
    "github.server_url": "https://github.com",
    "github.token": TOKEN,
    "secrets.GITHUB_TOKEN": TOKEN,
}
EXPRESSION = re.compile(r"\$\{\{\s*(.*?)\s*\}\}")
# The variables of the machine that are the runner's: the tests set their own.
RUNNER_VARIABLES = re.compile(r"(GITHUB|GH|RUNNER|ACTIONS)_\w*")

# The script of gh, which starts tests/fake_gh.py: with arguments as bash passed them,
# which Git Bash would otherwise turn into Windows paths when one starts with /.
GH = """#!/usr/bin/env bash
export MSYS2_ARG_CONV_EXCL='*'
exec "$FAKE_GH_PYTHON" -I -S -X utf8 "$FAKE_GH" "$@"
"""


@dataclass(frozen=True)
class Answer:
    """How gh answers a call whose arguments, joined by spaces, match args in full:
    with out, err and code, or with json through the filter of --jq, which needs jq.
    An answer with once answers one call, and a later answer the next."""

    args: str
    out: str = ""
    err: str = ""
    code: int = 0
    json: Any = None
    once: bool = False


def exact(command: str, out: str = "", *, code: int = 0, err: str = "") -> Answer:
    """The answer to the call of gh with exactly these arguments, joined by spaces."""
    return Answer(re.escape(command), out, err, code)


@dataclass
class StepResult:
    """What a step did: its exit code and output, the calls of gh, each with what gh
    read for it by its option, such as --body-file, the calls of the stubs, and what
    it wrote to the files of the runner."""

    returncode: int
    stdout: str
    stderr: str
    calls: list[list[str]]
    read: list[dict[str, str]]
    stubbed: list[str]
    summary: str
    outputs: dict[str, str]
    exported: dict[str, str]
    workspace: Path
    runner_temp: Path = field(repr=False)

    @property
    def commands(self) -> list[str]:
        """The calls of gh, each as its arguments joined by spaces."""
        return [" ".join(call) for call in self.calls]

    def called(self, pattern: str) -> list[str]:
        """The calls of gh whose arguments, joined by spaces, start with a match."""
        return [command for command in self.commands if re.match(pattern, command)]

    def read_by(self, pattern: str, option: str) -> list[str]:
        """What gh read for the option, such as --body-file, in the calls that match."""
        return [
            read[option]
            for command, read in zip(self.commands, self.read, strict=True)
            if re.match(pattern, command) and option in read
        ]


@cache
def _parsed(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        data: dict[Any, Any] = yaml.safe_load(file)
    # YAML 1.1, which PyYAML reads, takes the key on for true.
    if True in data:
        data["on"] = data.pop(True)
    return data


def workflow(name: str, root: Path = ROOT) -> dict[str, Any]:
    """A workflow of .github/workflows, parsed; the same object for each test, which
    none changes."""
    return _parsed((root / ".github/workflows" / name).resolve())


def job(name: str, job_id: str, root: Path = ROOT) -> dict[str, Any]:
    """A job of a workflow, by its id."""
    jobs: dict[str, Any] = workflow(name, root)["jobs"]
    assert job_id in jobs, f"{name} has no job {job_id}, but {sorted(jobs)}"
    return dict(jobs[job_id])


def step(name: str, job_id: str, step_name: str, root: Path = ROOT) -> dict[str, Any]:
    """A step of a job, by its name or its id."""
    steps = job(name, job_id, root).get("steps", [])
    for found in steps:
        if step_name in (found.get("name"), found.get("id")):
            return dict(found)
    names = [found.get("name") or found.get("id") for found in steps]
    raise AssertionError(f"{name}/{job_id} has no step {step_name!r}, but {names}")


def resolve(value: object, contexts: Mapping[str, str]) -> str | None:
    """The value of a variable of env: as the runner sets it, or None while it has an
    expression whose context the test runner doesn't know."""
    text = str(value).lower() if isinstance(value, bool) else str(value)
    unknown = False

    def known(found: re.Match[str]) -> str:
        nonlocal unknown
        if found[1] in contexts:
            return contexts[found[1]]
        unknown = True
        return found[0]

    resolved = EXPRESSION.sub(known, text)
    return None if unknown else resolved


def commands_file(text: str) -> dict[str, str]:
    """The values of a file such as $GITHUB_OUTPUT: name=value, or name<<END, the lines
    of the value and END."""
    values: dict[str, str] = {}
    lines = iter(text.splitlines())
    for line in lines:
        if "<<" in line and ("=" not in line or line.index("<<") < line.index("=")):
            name, end = line.split("<<", 1)
            value = []
            for following in lines:
                if following == end:
                    break
                value.append(following)
            values[name] = "\n".join(value)
        elif "=" in line:
            name, value_of_line = line.split("=", 1)
            values[name] = value_of_line
    return values


def shell_options(
    name: str, job_id: str, found: Mapping[str, Any], root: Path = ROOT
) -> list[str]:
    """The options of bash for the step, as GitHub starts it: -e by default on Linux,
    and with pipefail and without the profile for `shell: bash`."""
    shell = found.get("shell") or (
        job(name, job_id, root).get("defaults", {}).get("run", {}).get("shell")
        or workflow(name, root).get("defaults", {}).get("run", {}).get("shell")
    )
    if shell is None:
        return ["-e"]
    assert shell == "bash", f"{name}/{job_id}: the tests run bash steps, not {shell}"
    return ["--noprofile", "--norc", "-e", "-o", "pipefail"]


def recording(name: str, then: str = "") -> str:
    """The text of a stub that writes its call down for StepResult.stubbed, then runs
    the bash of then."""
    return f'printf "%s\\n" "{name} $*" >> "$STUB_CALLS"\n{then}\n'


def run_step(
    tmp_path: Path,
    workflow_name: str,
    job_id: str,
    step_name: str,
    *,
    answers: Sequence[Answer] = (),
    env: Mapping[str, str] | None = None,
    stubs: Mapping[str, str] | None = None,
    files: Mapping[str, str] | None = None,
    root: Path = ROOT,
) -> StepResult:
    """Runs the step of the job as GitHub does, in tmp_path: gh answers with answers,
    each stub, a name with the text of its bash, comes first on the PATH, and files are
    the files of the workspace by their paths, such as those that a checkout brings,
    or of $RUNNER_TEMP by a path that starts with it, such as those of a step before."""
    assert BASH, "the steps run in bash, Git Bash on Windows"
    found = step(workflow_name, job_id, step_name, root)
    script = found.get("run")
    assert script, f"{step_name} runs no script"
    # GitHub puts the values of expressions into the script before it runs; the bots
    # hand them over as variables, which the tests set.
    assert "${{" not in script, f"{step_name} has an expression in its script"
    folders = {
        name: tmp_path / name for name in ("workspace", "runner", "stubs", "github")
    }
    for folder in folders.values():
        folder.mkdir(parents=True, exist_ok=True)
    for name, text in (files or {}).items():
        folder, inside = folders["workspace"], name
        if name.startswith("$RUNNER_TEMP/"):
            folder, inside = folders["runner"], name.removeprefix("$RUNNER_TEMP/")
        target = folder / inside
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    github = folders["github"]
    paths = {
        name: github / name
        for name in ("summary", "output", "env", "path", "calls", "stubbed", "used")
    }
    for empty in paths.values():
        empty.write_text("", encoding="utf-8")
    (github / "answers.json").write_text(
        json.dumps(
            [
                {
                    key: value
                    for key, value in asdict(answer).items()
                    if key != "json" or answer.json is not None
                }
                for answer in answers
            ]
        ),
        encoding="utf-8",
    )
    for name, text in {"gh": GH, **(stubs or {})}.items():
        stub = folders["stubs"] / name
        body = text if text.startswith("#!") else f"#!/usr/bin/env bash\n{text}"
        stub.write_text(body, encoding="utf-8", newline="\n")
        stub.chmod(0o755)
    (github / "step.sh").write_text(script, encoding="utf-8", newline="\n")

    runner_temp = folders["runner"].as_posix()
    contexts = {**CONTEXTS, "runner.temp": runner_temp}
    declared = {
        **workflow(workflow_name, root).get("env", {}),
        **job(workflow_name, job_id, root).get("env", {}),
        **found.get("env", {}),
    }
    given = dict(env or {})
    variables: dict[str, str] = {}
    for name, value in declared.items():
        resolved = resolve(value, contexts)
        if name in given:
            continue
        # A value that the script reads comes from the test; one of the job that
        # this step doesn't read is empty, as an expression without a value is.
        reads = re.search(rf"\$\{{?{name}\b", script)
        assert resolved is not None or not reads, (
            f"the test gives no value for {name}: {value}"
        )
        variables[name] = resolved or ""
    environment = {
        **{
            name: value
            for name, value in os.environ.items()
            if not RUNNER_VARIABLES.fullmatch(name)
        },
        "CI": "true",
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": REPOSITORY,
        "GITHUB_REPOSITORY_OWNER": REPOSITORY.split("/")[0],
        "GITHUB_SHA": SHA,
        "GITHUB_RUN_ID": RUN_ID,
        "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_WORKSPACE": folders["workspace"].as_posix(),
        "GITHUB_STEP_SUMMARY": paths["summary"].as_posix(),
        "GITHUB_OUTPUT": paths["output"].as_posix(),
        "GITHUB_ENV": paths["env"].as_posix(),
        "GITHUB_PATH": paths["path"].as_posix(),
        "RUNNER_TEMP": runner_temp,
        "RUNNER_OS": "Linux",
        "STUBS": folders["stubs"].as_posix(),
        "STUB_CALLS": paths["stubbed"].as_posix(),
        "FAKE_GH": FAKE_GH.as_posix(),
        "FAKE_GH_PYTHON": Path(sys.executable).as_posix(),
        "FAKE_GH_ANSWERS": (github / "answers.json").as_posix(),
        "FAKE_GH_LOG": paths["calls"].as_posix(),
        "FAKE_GH_USED": paths["used"].as_posix(),
        **variables,
        **given,
    }
    options = shell_options(workflow_name, job_id, found, root)
    done = subprocess.run(
        in_bash(*options, (github / "step.sh").as_posix()),
        cwd=folders["workspace"] / found.get("working-directory", "."),
        env=environment,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )
    logged = [
        json.loads(line)
        for line in paths["calls"].read_text(encoding="utf-8").splitlines()
    ]
    return StepResult(
        returncode=done.returncode,
        stdout=done.stdout,
        stderr=done.stderr,
        calls=[call["args"] for call in logged],
        read=[call["read"] for call in logged],
        stubbed=paths["stubbed"].read_text(encoding="utf-8").splitlines(),
        summary=paths["summary"].read_text(encoding="utf-8"),
        outputs=commands_file(paths["output"].read_text(encoding="utf-8")),
        exported=commands_file(paths["env"].read_text(encoding="utf-8")),
        workspace=folders["workspace"],
        runner_temp=folders["runner"],
    )


# What a command of a step changes on GitHub, by the pattern that finds it in the
# script, with the lines that a backslash continues joined.
ACTS = {
    "merges": r"\bgh pr merge\b",
    "comments": r"\bgh (?:pr|issue) comment\b|\bgh (?:pr|issue) close\b.*--comment\b",
    "deletes": (
        r"\bgh (?:release|cache|label|run|repo|issue|secret|variable) delete\b"
        r"|(?:--method[= ]?|(?<!\S)-X ?)DELETE\b|--delete-branch\b"
        r"|\bgit(?:\s+-[cC]\s+\S+)*\s+push\b.*(?:--delete\b|\s:\S)"
    ),
    "dispatches": r"\bgh workflow run\b|\bgh run rerun\b|/dispatches\b",
    "opens": r"\bgh (?:pr|issue|release|label) create\b|\bgh (?:pr|issue) reopen\b",
    "closes": r"\bgh (?:pr|issue) close\b",
    "cancels": r"\bgh run cancel\b",
    "edits": (
        r"\bgh (?:pr|issue|release|label|repo) edit\b|\bgh release upload\b"
        r"|\bgh pr (?:update-branch|ready|review)\b"
        r"|\bgh (?:pr|issue) (?:lock|unlock)\b|\bgh issue transfer\b"
        r"|\bgh (?:secret|variable) set\b|\bgh workflow (?:enable|disable)\b"
    ),
    "writes": r"(?:--method[= ]?|(?<!\S)-X ?)(?:POST|PATCH|PUT)\b",
    "pushes": r"\bgit(?:\s+-[cC]\s+\S+)*\s+push\b",
}
# gh takes the method of the API in any case.
IGNORING_CASE = {"deletes", "writes"}
# A call of the API with fields and no method is a POST: a write, other than a query
# of GraphQL.
FIELDS = re.compile(
    r"\bgh api\b(?!.*(?:--method\b|(?<!\S)-X))"
    r"(?=.*\s(?:-[fF]|--field|--raw-field|--input)\s)"
)
QUERY = re.compile(r"""\bgh api graphql\b.*\bquery=["']?query\b""")


def acts_of(script: str) -> list[str]:
    """What the commands of a script change on GitHub, by the names of ACTS."""
    lines = script.replace("\\\n", " ").splitlines()
    acts = {
        act
        for line in lines
        if not line.lstrip().startswith("#")
        for act, pattern in ACTS.items()
        if re.search(pattern, line, re.IGNORECASE if act in IGNORING_CASE else 0)
    }
    for line in lines:
        if line.lstrip().startswith("#"):
            continue
        if FIELDS.search(line) and not QUERY.search(line):
            acts.add("writes")
    return sorted(acts)


def acting_steps(root: Path = ROOT) -> dict[tuple[str, str, str], list[str]]:
    """The steps of the workflows that change something on GitHub, by the workflow,
    the job and the name of the step, each with what it changes."""
    found = {}
    for path in sorted((root / ".github/workflows").glob("*.yml")):
        for job_id, settings in (workflow(path.name, root).get("jobs") or {}).items():
            for each in settings.get("steps") or []:
                acts = acts_of(each.get("run") or "")
                if acts:
                    found[(path.name, job_id, each.get("name") or each["id"])] = acts
    return found
