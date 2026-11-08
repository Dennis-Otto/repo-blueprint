"""Every call of GitHub's REST API asks for the version that the blueprint is written
for (decision 0125): the Python of the blueprint, which starts gh at a few places, and
the workflows, whose steps run gh api; tests/test_template.py checks the workflows of
the blueprint and of each kind of project with calls_without_the_version()."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest
from workflow_steps import calls_without_the_version

from blueprint.github import API_VERSION, API_VERSION_HEADER, gh_command

ROOT = Path(__file__).parents[1]
# The Python of the blueprint that runs gh, other than its tests: the scripts at the
# root, the package and the scripts of .github/ and of the fuzz tests.
SOURCES = sorted(
    [
        *ROOT.glob("*.py"),
        *(ROOT / "blueprint").rglob("*.py"),
        *(ROOT / ".github").rglob("*.py"),
        *(ROOT / "fuzz").rglob("*.py"),
    ]
)


def test_the_header_names_the_version() -> None:
    assert f"X-GitHub-Api-Version: {API_VERSION}" == API_VERSION_HEADER


@pytest.mark.parametrize(
    ("arguments", "command"),
    [
        (
            ["api", "--include", "repos/o/r"],
            ["gh", "api", "--include", "repos/o/r", "--header", API_VERSION_HEADER],
        ),
        (
            ("api", "graphql", "-f", "query=x"),
            ["gh", "api", "graphql", "-f", "query=x", "--header", API_VERSION_HEADER],
        ),
        (["repo", "view", "--json", "name"], ["gh", "repo", "view", "--json", "name"]),
        (["run", "download", "1"], ["gh", "run", "download", "1"]),
        ([], ["gh"]),
    ],
)
def test_a_call_of_the_api_asks_for_the_version_and_no_other_command_does(
    arguments: list[str], command: list[str]
) -> None:
    assert gh_command(arguments) == command


def kinds_of_gh(source: str) -> list[str]:
    """What each list or tuple of the source that starts with "gh" is: "api" for a call
    of the API that asks at its end with --header and API_VERSION_HEADER, "unversioned"
    for one that doesn't, "any" for one that takes the arguments of its caller, and
    "other" for another command of gh."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.List | ast.Tuple) or not node.elts:
            continue
        first, *rest = node.elts
        if not isinstance(first, ast.Constant) or first.value != "gh":
            continue
        command = rest[0] if rest else None
        if isinstance(command, ast.Starred):
            found.append("any")
        elif not isinstance(command, ast.Constant) or command.value != "api":
            found.append("other")
        else:
            found.append("api" if ends_with_the_version(rest[1:]) else "unversioned")
    return found


def ends_with_the_version(words: list[ast.expr]) -> bool:
    """Whether the words end with --header and the constant API_VERSION_HEADER."""
    if len(words) < 2:
        return False
    flag, value = words[-2:]
    name = value.attr if isinstance(value, ast.Attribute) else getattr(value, "id", "")
    return (
        isinstance(flag, ast.Constant)
        and flag.value == "--header"
        and name == "API_VERSION_HEADER"
    )


@pytest.mark.parametrize(
    ("source", "kind"),
    [
        ('run(["gh", "api", path, "--header", API_VERSION_HEADER])', "api"),
        ('run(("gh", "api", *words, "--header", github.API_VERSION_HEADER))', "api"),
        ('run(["gh", "api", path])', "unversioned"),
        ('run(["gh", "api"])', "unversioned"),
        ('run(["gh", "api", "--header", API_VERSION_HEADER, path])', "unversioned"),
        (
            'run(["gh", "api", path, "--header", "X-GitHub-Api-Version: 2022-11-28"])',
            "unversioned",
        ),
        ('run(["gh", "api", path, "--input", API_VERSION_HEADER])', "unversioned"),
        ('run(["gh", *arguments])', "any"),
        ('run(["gh", "pr", "create", "--fill"])', "other"),
        ('run(["gh", option])', "other"),
        ('run(["gh"])', "other"),
    ],
)
def test_a_call_of_gh_in_the_python_is_told_by_its_kind(source: str, kind: str) -> None:
    assert kinds_of_gh(source) == [kind]


def test_lists_that_start_with_another_word_are_no_calls_of_gh() -> None:
    assert kinds_of_gh('words = ["git", "push"]; empty = []; first = ("api",)') == []


# mutmut's copy holds the mutants of each function next to it, so a module with
# mutants, such as blueprint/bootstrap.py when a pull request changes it, has each of
# its calls of gh many times there.
@pytest.mark.mutation_unsafe
def test_every_call_of_the_api_in_the_python_asks_for_the_version() -> None:
    kinds = {
        path.relative_to(ROOT).as_posix(): kinds_of_gh(path.read_text("utf-8"))
        for path in SOURCES
    }

    def where(kind: str) -> dict[str, int]:
        return {
            name: found.count(kind) for name, found in kinds.items() if kind in found
        }

    assert where("unversioned") == {}
    # gh_command() alone starts gh with any arguments: the runners of the Api, which
    # most of the blueprint calls, go through it, and it adds the version.
    assert where("any") == {"blueprint/github.py": 1}
    assert where("api") == {
        "blueprint/app.py": 1,
        "blueprint/bootstrap.py": 1,
        "dashboard.py": 1,
    }


VERSION = {"API_VERSION_HEADER": API_VERSION_HEADER}
ASKS = 'gh api --header "$API_VERSION_HEADER" repos/o/r'


@pytest.mark.parametrize(
    ("workflow", "problems"),
    [
        ({"env": VERSION, "jobs": {"a": {"steps": [{"run": ASKS}]}}}, []),
        ({"jobs": {"a": {"env": VERSION, "steps": [{"run": ASKS}]}}}, []),
        ({"jobs": {"a": {"steps": [{"env": VERSION, "run": ASKS}]}}}, []),
        (
            {
                "env": VERSION,
                "jobs": {
                    "a": {
                        "steps": [
                            {"name": "Read", "run": f"{ASKS}\nx=$(gh api repos/o/r)"}
                        ]
                    }
                },
            },
            ["a: Read: x=$(gh api repos/o/r)"],
        ),
        (
            {
                "env": VERSION,
                "jobs": {
                    "a": {
                        "steps": [
                            {"run": 'gh api --header "X-GitHub-Api-Version: 1" x'}
                        ]
                    }
                },
            },
            ['a: step 1: gh api --header "X-GitHub-Api-Version: 1" x'],
        ),
        (
            {
                "jobs": {
                    "a": {
                        "steps": [
                            {"run": "gh pr list"},
                            {"env": {"API_VERSION_HEADER": "x"}, "run": ASKS},
                        ]
                    }
                }
            },
            [f"a: step 2: API_VERSION_HEADER is 'x': {ASKS}"],
        ),
        (
            {"jobs": {"a": {"steps": [{"name": "Read", "run": ASKS}]}}},
            [f"a: Read: API_VERSION_HEADER is None: {ASKS}"],
        ),
        (
            {"jobs": {"a": {"steps": [{"run": "# gh api repos/o/r\ngh apis"}]}}},
            [],
        ),
        ({"jobs": {"a": {"steps": [{"uses": "actions/checkout@v5"}]}}}, []),
        ({"jobs": {"a": {"uses": "./.github/workflows/b.yml"}}}, []),
        ({"on": "push"}, []),
    ],
)
def test_a_call_of_gh_api_in_a_workflow_without_the_version_is_found(
    workflow: dict[str, Any], problems: list[str]
) -> None:
    assert calls_without_the_version(workflow) == problems
