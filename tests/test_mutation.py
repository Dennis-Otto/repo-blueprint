"""Tests of the mutation tests: the plan of the parts, the results of each part, the
kinds of survivors, the report of the run and the issue of a score that dropped."""

from __future__ import annotations

import fnmatch
import json
import re
import subprocess
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from blueprint import cli, mutation
from blueprint.github import Api
from blueprint.mutation import (
    LOGIC,
    MOST_FAILING,
    MOST_KEPT,
    NOTHING_MATCHES,
    TEXT,
    TITLE,
    VALUE,
    Module,
    Report,
    Unit,
    baseline_of,
    classify,
    collect,
    comparison,
    configuration,
    default_paths,
    diff_of,
    dropped,
    estimate,
    failing_tests,
    function_of,
    issue_body,
    keep_issue,
    kind_of,
    last_words,
    module_name,
    modules,
    no_mutant_ran,
    plan,
    read_parts,
    read_previous,
    split,
    summary,
    survivors_text,
)

REPO = "Dennis-Otto/demo"
RUN = "https://github.com/Dennis-Otto/demo/actions/runs/2"
BEFORE = "https://github.com/Dennis-Otto/demo/actions/runs/1"
NOW = datetime(2026, 10, 24, 3, 0, tzinfo=UTC)


def files(root: Path, entries: dict[str, str]) -> Path:
    for name, text in entries.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")
    return root


# ---------------------------------------------------------------- the plan


@pytest.mark.parametrize(
    ("entries", "kind"),
    [
        ({"appinfo/info.xml": "<info/>", ".python-version": "3.12\n"}, "php"),
        (
            {".python-version": "3.12\n", ".github/mutation-requirements.txt": ""},
            "python",
        ),
        (
            {".python-version": "3.12\n", "stacks/mutation/requirements.txt": ""},
            "python",
        ),
        # A Python project without the pinned mutmut, such as one of Node.
        ({".python-version": "3.12\n"}, ""),
        ({".github/mutation-requirements.txt": ""}, ""),
    ],
)
def test_the_tool_follows_the_kind_of_project(
    tmp_path: Path, entries: dict[str, str], kind: str
) -> None:
    assert kind_of(files(tmp_path, entries)) == kind


@pytest.mark.parametrize(
    ("names", "paths"),
    [
        (
            [
                "blueprint/__init__.py",
                "blueprint.py",
                "conftest.py",
                "tests/__init__.py",
            ],
            ["blueprint", "blueprint.py"],
        ),
        (["src/demo/__init__.py", "demo.py"], ["src"]),
        (["custom_components/demo/__init__.py", "src/x.py"], ["custom_components"]),
    ],
)
def test_without_a_configuration_the_plan_mutates_what_the_workflow_does(
    tmp_path: Path, names: list[str], paths: list[str]
) -> None:
    # tests/test_template.py runs the step of the workflow on the same folders.
    assert default_paths(files(tmp_path, dict.fromkeys(names, ""))) == paths


@pytest.mark.parametrize(
    ("entries", "expected"),
    [
        (
            {
                "pyproject.toml": '[tool.mutmut]\nsource_paths = ["lib"]\n'
                'only_mutate = ["lib/a.py"]\ndo_not_mutate = "lib/b.py"\n',
                "setup.cfg": "[mutmut]\nsource_paths=other\n",
            },
            (["lib"], ["lib/a.py"], ["lib/b.py"]),
        ),
        (
            {"pyproject.toml": '[tool.mutmut]\npaths_to_mutate = "lib"\n'},
            (["lib"], [], []),
        ),
        # mutmut reads setup.cfg only without a table of its own in pyproject.toml.
        (
            {
                "pyproject.toml": "[tool.ruff]\n",
                "setup.cfg": "[mutmut]\nsource_paths=\n    a\n    b.py\n"
                "do_not_mutate=a/c.py\n",
            },
            (["a", "b.py"], [], ["a/c.py"]),
        ),
        ({"setup.cfg": "[mutmut]\npaths_to_mutate=lib\n"}, (["lib"], [], [])),
        ({"setup.cfg": "[flake8]\nmax-line-length=99\n"}, None),
        ({}, None),
    ],
)
def test_the_configuration_of_the_project_wins(
    tmp_path: Path,
    entries: dict[str, str],
    expected: tuple[list[str], list[str], list[str]] | None,
) -> None:
    assert configuration(files(tmp_path, entries)) == expected


@pytest.mark.parametrize(
    ("path", "name"),
    [
        ("blueprint/cli.py", "blueprint.cli"),
        ("blueprint.py", "blueprint"),
        ("src/demo/__init__.py", "demo"),
        ("custom_components/demo/sensor.py", "custom_components.demo.sensor"),
    ],
)
def test_the_name_of_a_module_is_that_of_its_mutants(path: str, name: str) -> None:
    assert module_name(path) == name


SOURCE = '''"""The module."""
import functools

LIMIT = 3


def add(a: int, b: int = 1) -> int:
    """Adds."""
    total = a + b
    return total


class Run:
    def of(self, x):
        return x.lower() if x else "A"

    @staticmethod
    def static(x):
        return not x

    @property
    def skipped(self):
        return 1 + 2


@functools.cache
def cached():
    return 1


def every(items, flag):
    count: int = 0
    seen: set[str]
    for item in items:
        if item is None or item in ("a", "B") and flag:
            continue
        if item < 0 <= count:
            break
        count += 1
        key = lambda value: value
        print(f"{item + 1}", b"raw", None, 2.5, True, key, sep="")
    match flag:
        case 1:
            pass
        case _:
            pass
    match count:
        case _:
            pass
    return r"""raw""", count
'''


def test_the_estimate_counts_what_mutmut_changes() -> None:
    assert estimate(SOURCE) == {
        # The assignment, the operator and the default; no type, no docstring.
        "x_add": 3,
        # Two of the condition, the swap of lower and three changes of "A" but one
        # that leaves it as it is.
        "xǁRunǁof": 5,
        "xǁRunǁstatic": 1,
        # The function with a decorator, cached and skipped, runs as the module
        # loads and keeps its code; so does the code outside of a function.
        "x_every": 43,
    }


def test_code_that_doesnt_parse_has_no_estimate() -> None:
    assert estimate("def broken(:\n") is None


def test_the_modules_of_the_plan(tmp_path: Path) -> None:
    root = files(
        tmp_path,
        {
            "pyproject.toml": '[tool.mutmut]\nsource_paths = ["lib", "tool.py", "gone"]\n'
            'do_not_mutate = ["lib/skip.py"]\n',
            "lib/__init__.py": "VERSION = 1\n",
            "lib/core.py": "def a(x):\n    return x + 1\n",
            "lib/skip.py": "def b(x):\n    return x + 1\n",
            "lib/new.py": "def c(x):\n    match x:\n        case 1 if y:\n            pass\n",
            "lib/newer.py": "def d[T](x: T) -> T:\n    return x\nprint(x)!\n",
            "tool.py": "def e(x):\n    return -x\n",
        },
    )

    found = {module.name: module for module in modules(root)}

    # No __init__ without a function, and the code that doesn't parse here counts
    # a mutant for each of its lines.
    assert sorted(found) == ["lib.core", "lib.new", "lib.newer", "tool"]
    assert found["lib.core"].functions == {"x_a": 2}
    assert found["lib.newer"] == Module("lib.newer", {}, lines=3)
    assert found["lib.newer"].mutants == 3
    assert found["tool"].mutants == 1


def test_only_mutate_keeps_the_modules_it_names(tmp_path: Path) -> None:
    root = files(
        tmp_path,
        {
            "setup.cfg": "[mutmut]\nonly_mutate=\n    a/b*\n",
            "a/b.py": "def f(x):\n    return x + 1\n",
            "a/c.py": "def g(x):\n    return x + 1\n",
        },
    )

    assert [module.name for module in modules(root)] == []
    (root / "setup.cfg").write_text(
        "[mutmut]\nsource_paths=a\nonly_mutate=a/b*\n", encoding="utf-8"
    )
    assert [module.name for module in modules(root)] == ["a.b"]


def test_a_script_and_a_package_of_one_name_are_one_module(tmp_path: Path) -> None:
    root = files(
        tmp_path,
        {
            "tool.py": "def main(x):\n    return x + 1\n",
            "tool/__init__.py": "def main(x):\n    return x - 1\n\ndef run(x):\n"
            "    return not x\n",
        },
    )

    # tool.py and tool/__init__.py both name their mutants tool.x_main__mutmut_1.
    assert modules(root) == [Module("tool", {"x_main": 4, "x_run": 1})]


def test_a_module_in_one_part_or_its_functions_in_several() -> None:
    module = Module("app.run", {"x_run": 3, "x_run_all": 2, "xǁJobǁstart": 1})

    assert module.whole() == Unit("app.run", ("app.run.x_*", "app.run.xǁ*"), 6)
    # run is the start of run_all: its pattern takes only its own mutants.
    assert module.split() == [
        Unit("app.run.x_run", ("app.run.x_run__mutmut_*",), 3),
        Unit("app.run.x_run_all", ("app.run.x_run_all*",), 2),
        Unit("app.run.xǁJobǁstart", ("app.run.xǁJobǁstart*",), 1),
    ]
    # Code that doesn't parse here has no functions to split.
    assert Module("app.new", {}, lines=9).split() == [
        Unit("app.new", ("app.new.x_*", "app.new.xǁ*"), 9)
    ]


def test_the_parts_have_about_the_same_number_of_mutants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mutation, "PART_MUTANTS", 10)
    found = [
        Module("big", {"x_a": 9, "x_b": 8, "x_c": 0}),
        Module("small", {"x_d": 2}),
        Module("tiny", {"x_e": 1}),
    ]

    parts = split(found, None)

    # 20 mutants make two parts, of 10 at most each: big splits into its functions,
    # which have more mutants than a part has. Its function that the estimate puts
    # at none comes last, into the smallest part: mutmut may still find mutants there.
    assert [[unit.name for unit in part] for part in parts] == [
        ["big.x_a", "tiny", "big.x_c"],
        ["big.x_b", "small"],
    ]
    assert [[unit.name for unit in part] for part in split(found, 1)] == [
        ["big", "small", "tiny"]
    ]
    # No more parts than units, and never more than the most.
    assert len(split(found, 5)) == 4
    monkeypatch.setattr(mutation, "MOST_PARTS", 2)
    assert len(split(found, 5)) == 2
    assert split([], None) == [[]]


def test_the_plan_of_each_kind(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert plan(tmp_path, None) == ("", [])
    php = files(tmp_path / "php", {"appinfo/info.xml": "<info/>"})
    assert plan(php, None) == (
        "php",
        [{"part": 1, "parts": 1, "patterns": "", "mutants": 0}],
    )
    python = files(
        tmp_path / "python",
        {
            ".python-version": "3.12\n",
            ".github/mutation-requirements.txt": "",
            "a.py": "def f(x):\n    return x + 1\n",
            "b.py": "def g(x):\n    return x - 1\n",
        },
    )
    # One part runs every mutant, without names.
    assert plan(python, None) == (
        "python",
        [{"part": 1, "parts": 1, "patterns": "", "mutants": 4}],
    )
    assert plan(python, 2) == (
        "python",
        [
            {"part": 1, "parts": 2, "patterns": "a.x_*\na.xǁ*", "mutants": 2},
            {"part": 2, "parts": 2, "patterns": "b.x_*\nb.xǁ*", "mutants": 2},
        ],
    )


def test_every_function_of_a_large_module_is_in_a_part(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mutation, "PART_MUTANTS", 4)
    python = files(
        tmp_path,
        {
            ".python-version": "3.12\n",
            ".github/mutation-requirements.txt": "",
            "a.py": "def f(x):\n    return x + 1 + 2 + 3\n\n"
            "def g(x):\n    return x - 1 - 2 - 3\n\n"
            "def h(x):\n    return x\n",
        },
    )

    _, parts = plan(python, None)

    # h has no mutant that the estimate sees; mutmut may find one all the same, which
    # then belongs to a part.
    patterns = [pattern for part in parts for pattern in part["patterns"].split()]
    assert sorted(patterns) == ["a.x_f*", "a.x_g*", "a.x_h*"]
    for name in ("a.x_f__mutmut_1", "a.x_g__mutmut_1", "a.x_h__mutmut_1"):
        assert any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns)


def test_the_plan_is_written_for_the_workflow(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = files(
        tmp_path,
        {
            ".python-version": "3.12\n",
            ".github/mutation-requirements.txt": "",
            "a.py": "def f(x):\n    return x + 1\n",
            "b.py": "def g(x):\n    return x - 1\n",
        },
    )

    assert cli.main(["mutation", "plan", "--parts", "2"], root=root) == 0

    captured = capsys.readouterr()
    lines = captured.out.splitlines()
    assert lines[0] == "kind=python"
    assert lines[1].startswith("parts=")
    assert [part["part"] for part in json.loads(lines[1].removeprefix("parts="))] == [
        1,
        2,
    ]
    # The names stay as they are, not escaped, for the step of each part.
    assert "xǁ" in lines[1]
    assert "Part 2 of 2: about 2 mutants" in captured.err
    assert cli.main(["mutation", "plan"], root=root) == 0


@pytest.mark.parametrize("parts", ["0", "two", "-1"])
def test_the_parts_are_a_number(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], parts: str
) -> None:
    assert cli.main(["mutation", "plan", "--parts", parts], root=tmp_path) == 2
    assert "a number or auto" in capsys.readouterr().err


# ---------------------------------------------------------------- the kinds of survivors


def change(old: str, new: str, before: str = "", after: str = "") -> str:
    """A change as mutmut show prints it, between the lines before and after."""
    lines = ["# a.x_f__mutmut_1: survived", "--- a.py", "+++ a.py", "@@ -1,3 +1,3 @@"]
    lines += [f" {line}" for line in before.splitlines()]
    lines += [f"-{line}" for line in old.splitlines()]
    lines += [f"+{line}" for line in new.splitlines()]
    lines += [f" {line}" for line in after.splitlines()]
    return "\n".join(lines)


@pytest.mark.parametrize(
    ("diff", "kind"),
    [
        # A text, as of a message or a help.
        (change('    print("Done")', '    print("XXDoneXX")'), TEXT),
        (change("    log('Done')  # pragma", "    log('done')  # pragma"), TEXT),
        # A text that a comparison reads decides a branch.
        (change('    if kind == "php":', '    if kind == "XXphpXX":'), LOGIC),
        (change('    if "a" in kind:', '    if "XXaXX" in kind:'), LOGIC),
        # So does a key, the name of an attribute and a text after in, as mutmut
        # changed them in a run.
        (change('    x = now["score"]', '    x = now["XXscoreXX"]'), LOGIC),
        (change('    x = {"score": 1}', '    x = {"SCORE": 1}'), LOGIC),
        (change('    x = data.get("base")', '    x = data.get("XXbaseXX")'), LOGIC),
        (change('    x = os.getenv("CI", "a")', '    x = os.getenv("CI", "A")'), TEXT),
        (change('    x = getattr(a, "name")', '    x = getattr(a, "NAME")'), LOGIC),
        (
            change(
                '    x = getattr(f(a), "b", "c")', '    x = getattr(f(a), "b", "C")'
            ),
            TEXT,
        ),
        (
            change(
                '    if state in ("killed", "survived"):',
                '    if state in ("killed", "XXsurvivedXX"):',
            ),
            LOGIC,
        ),
        (change('    x = [f(a), "b"]', '    x = [f(a), "B"]'), TEXT),
        (change('    x = g({"a": "Done"})', '    x = g({"a": "DONE"})'), TEXT),
        # The code in the braces of an f-string is code; its texts are texts.
        (change('    x = f"{a + 1}!"', '    x = f"{a - 1}!"'), LOGIC),
        (change("    x = f\"{f(a, 'b')}\"", '    x = f"{f(a, )}"'), VALUE),
        (change("    x = rf'{a[\"k\"]}'", "    x = rf'{a[\"XXkXX\"]}'"), LOGIC),
        (change('    x = f"{{a}}{b:>3}"', '    x = f"{{a}}{b:>4}"'), LOGIC),
        (change('    x = f"{ {1: a}[1] }"', '    x = f"{ {1: a}[2] }"'), LOGIC),
        (change('    x = f"{a", "b"', '    x = f"{a", "B"'), TEXT),
        (change('    x = "a"', '    x = "b"'), TEXT),
        (change('    ("a")', '    ("XXaXX")'), TEXT),
        # An index, not a text, and a bracket closed before the text.
        (change('    x = a[1], "b"', '    x = a[1], "B"'), TEXT),
        # A value that becomes None, or None that becomes a text.
        (change("    run(a, b)", "    run(None, b)"), VALUE),
        (change("    x = compute()", "    x = None"), VALUE),
        (change("    x = None", '    x = ""'), VALUE),
        # An argument left out: the first, the last, or one on a line of its own.
        (change("    run(a, b)", "    run(b)"), VALUE),
        (change("    run(a, b)", "    run(a, )"), VALUE),
        (
            change('        help="the x",', "", '    add(\n        "--x",', "    )"),
            VALUE,
        ),
        # The last argument of a call on lines of their own, whose comma the match
        # of the tokens takes from the line before, as mutmut showed it in a run.
        (
            change(
                '        "https://example.com/new",\n    ),',
                "        ),",
                '    Step(\n        "A title",\n        "projects/" in readme,',
                "    Step(",
            ),
            VALUE,
        ),
        (change("    run(a, b, a)", "    run(a, b)"), VALUE),
        (change("    run(b, b)", "    run(b)"), VALUE),
        (change("    f(a, a, b, c)", "    f(a, b, c)"), VALUE),
        # Not a value: a part of an expression left out.
        (change("    return -x", "    return x"), LOGIC),
        # The logic: an operator, a removed not, a condition, a number.
        (change("    return a + b", "    return a - b"), LOGIC),
        (change("    if not ready:", "    if ready:"), LOGIC),
        (change("    y = a if c else b", "    y = a if (c) and False else b"), LOGIC),
        (change("    x = 1  # one", "    x = 2  # one"), LOGIC),
        (change("    return x", "    return x"), LOGIC),
        # The kind that matters most wins.
        (change('    f("a", 1)', '    f("b", 2)'), LOGIC),
        (change('    f("a", b)', '    f("XXaXX", None)'), VALUE),
    ],
)
def test_the_kind_of_a_survivor(diff: str, kind: str) -> None:
    assert classify(diff) == kind


@pytest.mark.parametrize(
    ("name", "function"),
    [
        ("blueprint.cli.x_main__mutmut_3", "blueprint.cli.main"),
        ("a.b.xǁRunǁof__mutmut_12", "a.b.Run.of"),
        ("x_add__mutmut_1", "add"),
    ],
)
def test_the_function_of_a_mutant(name: str, function: str) -> None:
    assert function_of(name) == function


# ---------------------------------------------------------------- one part

RESULTS = """\
    a.x_f__mutmut_1: killed
    a.x_f__mutmut_2: survived
    a.x_f__mutmut_3: survived
    a.xǁRunǁof__mutmut_1: timeout
    b.x_g__mutmut_1: not checked
some other line
"""
SHOWN = {
    "a.x_f__mutmut_2": change("    return a + b", "    return a - b"),
    "a.x_f__mutmut_3": change('    log("Done")', '    log("XXDoneXX")'),
}
# The output of mutmut when the tests fail without a mutant, with its spinner.
FAILED = (
    "⠋ Generating mutants\r⠙ Generating mutants\n"
    "    done in 597ms (2 files mutated, 0 ignored, 0 unmodified)\n"
    "⠋ Running stats\r"
    "FAILED tests/test_a.py::test_one - AssertionError: assert 1 == 2\n"
    "FAILED tests/test_a.py::test_one - AssertionError: assert 1 == 2\n"
    "ERROR tests/test_b.py - ImportError: no module named b\n"
    "FAILED: Unable to force test failures\n"
    "failed to collect stats. runner returned 1\n"
)


def test_a_part_keeps_its_own_mutants_and_the_change_of_each_survivor() -> None:
    part = collect(RESULTS, "done\n", ["a.x_*", "a.xǁ*"], 0, (1, 2), SHOWN.__getitem__)

    assert part["part"] == 1
    assert part["parts"] == 2
    assert part["generated"] == 5
    assert part["results"] == {
        "a.x_f__mutmut_1": "killed",
        "a.x_f__mutmut_2": "survived",
        "a.x_f__mutmut_3": "survived",
        "a.xǁRunǁof__mutmut_1": "timeout",
    }
    assert part["survivors"] == [
        {
            "name": "a.x_f__mutmut_2",
            "kind": LOGIC,
            "diff": "-    return a + b\n+    return a - b",
        },
        {
            "name": "a.x_f__mutmut_3",
            "kind": TEXT,
            "diff": '-    log("Done")\n+    log("XXDoneXX")',
        },
    ]
    # Mutants ran, so nothing failed without them.
    assert part["failing"] == []
    assert part["last_words"] == []
    assert not part["empty"]


def test_a_part_without_names_keeps_every_mutant() -> None:
    part = collect(RESULTS, "", [], 124, (1, 1), SHOWN.__getitem__, workers=0)

    assert len(part["results"]) == 5
    assert part["status"] == 124


def test_a_part_names_the_tests_that_fail_without_any_mutant() -> None:
    results = "    a.x_f__mutmut_1: not checked\n"

    part = collect(results, FAILED, [], 1, (1, 1), SHOWN.__getitem__)

    assert part["failing"] == ["tests/test_a.py::test_one", "tests/test_b.py"]
    assert part["last_words"][0] == "⠙ Generating mutants"
    assert part["last_words"][-1] == "failed to collect stats. runner returned 1"


def test_a_part_without_mutants_is_empty() -> None:
    part = collect(
        "", f"AssertionError: {NOTHING_MATCHES}\n", ["c.x_*"], 1, (2, 2), str
    )

    assert part["empty"]
    assert Report.of([part]).silent == []


def test_the_last_words_and_the_failing_tests_of_mutmut() -> None:
    assert last_words("a\rb\nc\n") == ["b", "c"]
    # Parameters with spaces, a " - " and brackets of their own, as pytest prints
    # them; the message after the id may hold brackets too.
    workflow = "steps:\\n      - uses: a@b # v1\\n-False"
    assert failing_tests(
        "FAILED tests/x.py::t[1-2] - boom - again [3]\nERROR x\n"
        f"FAILED tests/x.py::t[{workflow}] - assert [1] == []\n"
        "ERROR tests/y.py - ImportError\nFAILED tests/x.py::t[[a] b]\n"
        "FAILED tests/x.py::t[unclosed - boom\n"
    ) == [
        "tests/x.py::t[1-2]",
        f"tests/x.py::t[{workflow}]",
        "tests/y.py",
        "tests/x.py::t[[a] b]",
        "tests/x.py::t[unclosed - boom",
    ]


def test_the_change_without_the_headers_of_mutmut_show() -> None:
    assert diff_of(SHOWN["a.x_f__mutmut_2"]) == "-    return a + b\n+    return a - b"
    assert diff_of("-a\n+b") == "-a\n+b"


def part_data(**fields: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "part": 1,
        "parts": 1,
        "status": 0,
        "empty": False,
        "generated": 0,
        "results": {},
        "survivors": [],
        "failing": [],
        "last_words": [],
    }
    data.update(fields)
    return data


def test_why_no_mutant_ran() -> None:
    failing = [f"tests/test_a.py::test_{number}" for number in range(MOST_FAILING + 2)]
    text = no_mutant_ran(part_data(failing=failing, last_words=["failed to collect"]))

    assert text.startswith("**The tests fail without any mutant.**")
    assert "- `tests/test_a.py::test_0`\n" in text
    assert f"- `tests/test_a.py::test_{MOST_FAILING}`" not in text
    assert "- and 2 more\n" in text
    assert "`@pytest.mark.mutation_unsafe`" in text
    assert "`cache_clear()`" in text
    assert text.endswith("```text\nfailed to collect\n```")
    assert no_mutant_ran(part_data()) == (
        "No mutant ran. The end of the output of mutmut:\n\n```text\n\n```"
    )


# ---------------------------------------------------------------- the whole run


def survivor(name: str, kind: str, diff: str = "-a\n+b") -> dict[str, Any]:
    return {"name": name, "kind": kind, "diff": diff}


def two_parts() -> list[dict[str, Any]]:
    return [
        part_data(
            part=2,
            parts=2,
            generated=6,
            results={
                "b.x_g__mutmut_1": "killed",
                "b.x_g__mutmut_2": "survived",
                "a.x_f__mutmut_9": "killed",
            },
            survivors=[survivor("b.x_g__mutmut_2", VALUE)],
        ),
        part_data(
            part=1,
            parts=2,
            generated=6,
            results={
                "a.x_f__mutmut_1": "killed",
                "a.x_f__mutmut_2": "survived",
                "a.x_f__mutmut_3": "survived",
                "a.x_f__mutmut_9": "survived",
                "a.xǁRunǁof__mutmut_1": "timeout",
            },
            survivors=[
                survivor("a.x_f__mutmut_2", LOGIC),
                survivor("a.x_f__mutmut_3", TEXT),
            ],
        ),
    ]


def test_the_parts_make_one_report() -> None:
    report = Report.of(two_parts())

    assert report.parts == 2
    assert [part["part"] for part in report.reported] == [1, 2]
    # A mutant that two parts ran counts once, as the first part found it.
    assert report.results["a.x_f__mutmut_9"] == "survived"
    assert (report.killed, report.survived, report.other) == (2, 4, 1)
    assert report.measured
    assert report.complete
    assert report.score == pytest.approx(100 * 2 / 6)
    # Only the survivors that change the logic count against the logic.
    assert report.logic_score == pytest.approx(100 * 2 / 3)
    assert report.by_function(LOGIC) == {"a.f": 1}
    assert report.data(RUN, NOW) == {
        "tool": "mutmut",
        "run": RUN,
        "date": "2026-10-24T03:00:00+00:00",
        "complete": True,
        "parts": 2,
        "killed": 2,
        "survived": 4,
        "other": 1,
        "score": 33.3,
        "logic_score": 66.7,
        "kinds": {LOGIC: 1, VALUE: 1, TEXT: 1},
        "logic_by_function": {"a.f": 1},
    }
    assert report.results_text().startswith(
        "    a.x_f__mutmut_1: killed\n    a.x_f__mutmut_2: survived\n"
    )


def test_a_run_with_a_gap_is_incomplete() -> None:
    first, second = two_parts()[1], two_parts()[0]

    missing = Report.of([first])
    assert missing.missing == [2]
    # The mutants of the missing part aren't counted twice as unknown.
    assert missing.unmatched == 0
    assert not missing.complete
    stopped = Report.of([{**first, "status": 124}, second])
    assert stopped.stopped
    assert not stopped.complete
    unmatched = Report.of([{**first, "generated": 9}, second])
    # The two parts ran 7 of the 9 mutants that mutmut made.
    assert unmatched.unmatched == 2
    assert not unmatched.complete
    silent = Report.of(
        [{**first, "results": {"a.x_f__mutmut_1": "not checked"}}, second]
    )
    assert [part["part"] for part in silent.silent] == [1]
    assert not silent.complete
    assert not Report.of([]).measured
    assert Report.of([]).score == 0


def test_the_summary_lists_the_logic_first() -> None:
    report = Report.of(
        [
            part_data(
                generated=6,
                results={
                    "a.x_f__mutmut_1": "killed",
                    "a.x_f__mutmut_2": "survived",
                    "a.x_f__mutmut_3": "survived",
                    "a.x_g__mutmut_1": "survived",
                    "a.x_h__mutmut_1": "survived",
                    "a.x_h__mutmut_2": "survived",
                },
                survivors=[
                    survivor("a.x_f__mutmut_2", LOGIC, "-    a + b\n+    a - b"),
                    survivor("a.x_f__mutmut_3", LOGIC, "-    1\n+    2"),
                    survivor("a.x_g__mutmut_1", LOGIC, "-    c\n+    d"),
                    survivor("a.x_h__mutmut_1", VALUE),
                    survivor("a.x_h__mutmut_2", TEXT),
                ],
            )
        ]
    )

    text = summary(report, report.data(RUN, NOW), None, most_diffs=2)

    assert text.startswith(
        "### Mutation tests (mutmut)\n\n**16.7 %** of the mutants were noticed by a "
        "test: 1 killed, 5 survived, 0 other.\n\nThe score of the logic is "
        "**25.0 %**: 3 of the survivors change what the code does, 1 pass None or "
        "leave out an argument, and 1 change only a text.\n"
    )
    assert "No complete run before this one to compare with." in text
    logic = text.index("#### 3 survivors change the logic")
    assert logic < text.index("#### 1 survivors pass None or leave out an argument")
    assert text.index("#### 1 survivors pass None") < text.index(
        "#### 1 survivors change only a text"
    )
    # The function with the most survivors first, each with its change while the
    # summary has room for it.
    assert text.index("<code>a.f</code>: 2") < text.index("<code>a.g</code>: 1")
    assert "```diff\n-    a + b\n+    a - b\n```" in text
    assert "```diff\n-    c\n+    d\n```" not in text
    assert "`a.x_g__mutmut_1`" in text
    assert "The changes of the other 1 are in `survivors.md`" in text
    assert "| `a.h` | 1 |" in text
    assert "`# pragma: no mutate`" in text
    assert text.endswith("\n")
    assert not text.endswith("\n\n")


def test_the_summary_shows_the_first_functions_of_a_table() -> None:
    report = Report.of(
        [
            part_data(
                results={
                    "a.x_f__mutmut_1": "killed",
                    "a.x_f__mutmut_2": "survived",
                    "a.x_g__mutmut_1": "survived",
                    "a.x_h__mutmut_1": "survived",
                },
                survivors=[
                    survivor("a.x_f__mutmut_2", TEXT),
                    survivor("a.x_g__mutmut_1", TEXT),
                    survivor("a.x_h__mutmut_1", TEXT),
                ],
            )
        ]
    )

    text = summary(report, report.data(RUN, NOW), None, most_rows=1)

    assert "#### 3 survivors change only a text" in text
    assert "| `a.f` | 1 |\n| 2 more functions | 2 |" in text
    assert "change the logic" not in text
    assert "#### 3 survivors pass None" not in text


def test_the_summary_leaves_out_the_kinds_without_survivors() -> None:
    report = Report.of(
        [
            part_data(
                results={"a.x_f__mutmut_1": "survived"},
                survivors=[survivor("a.x_f__mutmut_1", LOGIC)],
            )
        ]
    )

    text = summary(report, report.data(RUN, NOW), None)

    assert "#### 1 survivors change the logic" in text
    assert "pass None or leave out an argument\n" not in text
    assert "change only a text\n" not in text


def test_the_summary_of_a_run_that_measured_nothing() -> None:
    parts = two_parts()
    parts[1]["results"] = {"a.x_f__mutmut_1": "not checked"}
    parts[1]["failing"] = ["tests/test_a.py::test_one"]
    parts[0]["results"] = {}

    report = Report.of(parts)
    text = summary(report, report.data(RUN, NOW), None)

    assert text.startswith(
        "### Mutation tests (mutmut)\n\nNo mutant ran, in 2 parts.\n"
    )
    assert "Part 1 of 2: **The tests fail without any mutant.**" in text
    assert "Part 2 of 2: No mutant ran. The end of the output of mutmut:" in text
    assert "score of the logic" not in text


def test_the_summary_names_the_gaps_of_a_run() -> None:
    first = two_parts()[1]

    text = summary(Report.of([{**first, "status": 124}]), {}, None)

    assert "Part 2 of 2 sent no results: its job failed." in text
    assert "The run stopped at its time limit" in text
    assert "The run is incomplete, so it is compared with no other." in text
    unmatched = Report.of([{**first, "generated": 9}, two_parts()[0]])
    assert "2 mutants belong to no part of the plan" in summary(unmatched, {}, None)


def comparable(score: float, logic_score: float, **fields: Any) -> dict[str, Any]:
    return {
        "complete": True,
        "score": score,
        "logic_score": logic_score,
        "kinds": {LOGIC: 3, VALUE: 0, TEXT: 0},
        "logic_by_function": {"a.f": 2, "a.g": 1},
        "run": BEFORE,
        "date": "2026-10-17T03:00:00+00:00",
        **fields,
    }


def test_the_comparison_with_the_run_before() -> None:
    now = comparable(80.0, 90.0, run=RUN, date="2026-10-24T03:00:00+00:00")

    assert comparison(now, comparable(82.2, 96.0)) == (
        f"Since [the run of 2026-10-17]({BEFORE}): the score 82.2 % → 80.0 %, the "
        "score of the logic 96.0 % → 90.0 %."
    )
    assert comparison(now, {"complete": False}) == (
        "No complete run before this one to compare with."
    )
    assert comparison({"complete": True, "score": "x"}, None).startswith(
        "The run is incomplete"
    )


@pytest.mark.parametrize(
    ("now", "before", "fell"),
    [
        ((80.0, 96.0), (82.2, 96.0), True),
        ((82.2, 94.0), (82.2, 96.0), True),
        # Within the tolerance of a run that measures a little differently.
        ((81.8, 95.6), (82.2, 96.0), False),
        ((90.0, 99.0), (82.2, 96.0), False),
    ],
)
def test_a_drop_of_the_score_or_of_the_score_of_the_logic(
    now: tuple[float, float], before: tuple[float, float], fell: bool
) -> None:
    assert dropped(comparable(*now), comparable(*before)) is fell


def test_the_artifact_keeps_every_survivor_with_its_change() -> None:
    text = survivors_text(Report.of(two_parts()))

    assert text.startswith(
        "# The surviving mutants\n\n## Survivors that change the logic: 1"
    )
    assert "### `a.x_f__mutmut_2`\n\n```diff\n-a\n+b\n```" in text
    assert "## Survivors that change only a text: 1" in text


def test_the_parts_and_the_run_before_from_their_files(tmp_path: Path) -> None:
    folder = tmp_path / "parts"
    files(
        folder,
        {
            "part-1.json": json.dumps(part_data(part=1)),
            "nested/part-2.json": json.dumps(part_data(part=2)),
            "part-3.json": json.dumps([1]),
            "part-4.json": json.dumps({"results": []}),
            "other.json": json.dumps(part_data(part=5)),
        },
    )

    assert [part["part"] for part in read_parts(folder)] == [2, 1]
    assert read_parts(tmp_path / "none") == []
    assert read_previous(None) is None
    assert read_previous(tmp_path / "none.json") is None
    files(tmp_path, {"bad.json": "{", "list.json": "[]", "good.json": '{"score": 1}'})
    assert read_previous(tmp_path / "bad.json") is None
    assert read_previous(tmp_path / "list.json") is None
    assert read_previous(tmp_path / "good.json") == {"score": 1}


# ---------------------------------------------------------------- the issue


class FakeGitHub:
    """The issues of GitHub's API that the report uses, kept in memory."""

    def __init__(self) -> None:
        self.issues: dict[int, dict[str, Any]] = {}
        self.comments: dict[int, list[str]] = {}
        # GitHub refuses every request, as on a hiccup.
        self.down = False

    def __call__(
        self, arguments: Sequence[str], body: str | None
    ) -> subprocess.CompletedProcess[str]:
        method, path = arguments[3], arguments[4].removeprefix(f"repos/{REPO}")
        payload: Any = json.loads(body) if body else None
        status: int = 200
        data: Any = None
        if self.down:
            status, data = 502, {"message": "Bad Gateway"}
        elif path == "/issues?labels=maintenance&state=open&per_page=100":
            data = [
                dict(issue)
                for issue in self.issues.values()
                if issue["state"] == "open"
            ]
        elif path == "/issues":
            number = len(self.issues) + 1
            self.issues[number] = {**payload, "number": number, "state": "open"}
            status, data = 201, self.issues[number]
        elif match := re.fullmatch(r"/issues/(\d+)", path):
            self.issues[int(match[1])].update(payload)
        elif match := re.fullmatch(r"/issues/(\d+)/comments", path):
            self.comments.setdefault(int(match[1]), []).append(payload["body"])
            status = 201
        else:
            raise AssertionError(f"unexpected request {method} {path}")
        text = "" if data is None else json.dumps(data)
        return subprocess.CompletedProcess(
            arguments, 0, f"HTTP/2.0 {status} X\r\n\r\n{text}", ""
        )

    def add(self, body: str, **fields: Any) -> int:
        number = len(self.issues) + 1
        self.issues[number] = {
            "number": number,
            "body": body,
            "state": "open",
            **fields,
        }
        return number


def test_a_drop_opens_one_issue() -> None:
    github = FakeGitHub()
    now = comparable(
        80.0,
        90.0,
        run=RUN,
        date="2026-10-24T03:00:00+00:00",
        kinds={LOGIC: 9},
        logic_by_function={"a.f": 5, "a.g": 1, "a.h": 2},
    )

    line = keep_issue(Api(github), REPO, now, comparable(82.2, 96.0))

    assert line == "The score dropped: opened #1."
    issue = github.issues[1]
    assert issue["title"] == TITLE
    assert issue["labels"] == ["maintenance"]
    body = issue["body"]
    assert (
        f"dropped in [the run of 2026-10-24]({RUN}), below that of [the run of 2026-10-17]({BEFORE})"
        in body
    )
    assert "| Score | 82.2 % | 80.0 % |" in body
    assert "| Score of the logic | 96.0 % | 90.0 % |" in body
    assert "| Survivors that change the logic | 3 | 9 |" in body
    # The functions that gained survivors of the logic, the most first.
    assert "| `a.f` | 3 |\n| `a.h` | 2 |\n" in body
    assert "`a.g`" not in body


def test_the_issue_follows_the_score_until_it_is_back() -> None:
    github = FakeGitHub()
    api = Api(github)
    before = comparable(82.2, 96.0)
    keep_issue(api, REPO, comparable(80.0, 90.0, run=RUN), before)

    # Still low, compared with the run before the drop, not with the last one.
    line = keep_issue(
        api, REPO, comparable(81.0, 96.0, run=RUN), comparable(80.0, 90.0)
    )
    assert line == "The score is still below that before the drop: updated #1."
    assert "| Score | 82.2 % | 81.0 % |" in github.issues[1]["body"]

    line = keep_issue(
        api, REPO, comparable(82.0, 96.0, run=RUN, date="2026-10-31"), None
    )
    assert line == "The score is back: closed #1."
    assert github.issues[1]["state"] == "closed"
    assert github.issues[1]["state_reason"] == "completed"
    assert github.comments[1] == [
        f"[The run of 2026-10-31]({RUN}) is back at the score of "
        f"[the run of 2026-10-17]({BEFORE}) before the drop: 82.0 %."
    ]


@pytest.mark.parametrize(
    "previous",
    [
        None,
        {"complete": False, "score": 99.0, "logic_score": 99.0},
        comparable(80.0, 90.0),
    ],
)
def test_no_issue_without_a_drop(previous: dict[str, Any] | None) -> None:
    github = FakeGitHub()

    line = keep_issue(Api(github), REPO, comparable(80.0, 90.0), previous)

    assert line == "The score didn't drop."
    assert github.issues == {}


def test_an_incomplete_run_leaves_the_issue_alone() -> None:
    github = FakeGitHub()

    line = keep_issue(Api(github), REPO, {"complete": False}, comparable(99.0, 99.0))

    assert line == "An incomplete run leaves the issue of the score as it is."
    assert github.issues == {}


def test_other_issues_are_no_issue_of_the_score() -> None:
    github = FakeGitHub()
    github.add("A pull request <!-- mutation-score {} -->", pull_request={})
    github.add("Another issue.")
    github.add("<!-- mutation-score {broken} -->")
    github.add("<!-- mutation-score [1] -->")
    github.add('<!-- mutation-score {"baseline": {"complete": false}} -->')

    line = keep_issue(Api(github), REPO, comparable(80.0, 90.0), comparable(82.2, 96.0))

    assert line == "The score dropped: opened #6."


def test_the_issue_keeps_the_first_functions_of_the_run_before() -> None:
    many = {f"a.f{number}": 1 for number in range(MOST_KEPT + 5)}
    body = issue_body(
        comparable(80.0, 90.0, logic_by_function={}, kinds=None),
        comparable(82.2, 96.0, logic_by_function=many, note="a--b"),
    )

    state = json.loads(
        re.search(r"<!-- mutation-score (\{.*\}) -->", body)[1]  # type: ignore[index]
    )
    assert len(state["baseline"]["logic_by_function"]) == MOST_KEPT
    # Two hyphens would end the comment of the marker.
    assert "a--b" not in body
    assert state["baseline"]["note"] == "a--b"
    assert "| Survivors that change the logic | 3 | 0 |" in body
    assert "The functions with more survivors" not in body


# ---------------------------------------------------------------- the command line


def test_a_part_from_the_command_line(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "show_mutant", SHOWN.__getitem__)
    files(tmp_path, {"results.txt": RESULTS, "run.txt": "done\n"})
    out = tmp_path / "part-1.json"
    arguments = ["mutation", "collect", str(tmp_path / "results.txt")]

    code = cli.main(
        [
            *arguments,
            str(tmp_path / "run.txt"),
            "--part",
            "1/2",
            "--patterns",
            "a.x_*\na.xǁ*",
            "--out",
            str(out),
        ],
    )

    assert code == 0
    assert capsys.readouterr().out == ""
    part = json.loads(out.read_text(encoding="utf-8"))
    assert (part["part"], part["parts"]) == (1, 2)
    assert len(part["survivors"]) == 2

    files(tmp_path, {"results.txt": "    a.x_f__mutmut_1: not checked\n"})
    code = cli.main(
        [
            *arguments,
            str(tmp_path / "missing.txt"),
            "--part",
            "1",
            "--status",
            "1",
            "--out",
            str(out),
        ],
    )

    assert code == 1
    assert "No mutant ran. The end of the output of mutmut:" in capsys.readouterr().out


def test_mutmut_shows_a_survivor_on_the_python_that_has_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files(
        tmp_path,
        {
            "modules/mutmut.py": "import sys\nprint('shown:', *sys.argv[1:])\n",
            # The folder of the project comes after the modules of Python.
            "mutmut.py": "print('the project')\n",
        },
    )
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "modules"))
    monkeypatch.chdir(tmp_path)

    assert (
        cli.show_mutant("a.xǁRunǁof__mutmut_1") == "shown: show a.xǁRunǁof__mutmut_1\n"
    )


def report_of(
    folder: Path, parts: Sequence[dict[str, Any]], previous: Path | None
) -> tuple[int, dict[str, Any]]:
    """mutation report of these parts, with mutation.json of the run before."""
    found = folder / "parts"
    for part in parts:
        files(found, {f"part-{part['part']}.json": json.dumps(part)})
    out = folder / "mutation"
    arguments = ["mutation", "report", str(found), "--out", str(out), "--run", RUN]
    if previous is not None:
        arguments += ["--previous", str(previous)]
    code = cli.main(arguments)
    return code, json.loads((out / "mutation.json").read_text(encoding="utf-8"))


def test_the_report_from_the_command_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    previous = files(tmp_path, {"previous.json": json.dumps(comparable(90.0, 99.0))})
    github = FakeGitHub()
    out = tmp_path / "run/mutation"

    code, data = report_of(tmp_path / "run", two_parts(), previous / "previous.json")

    assert code == 0
    text = capsys.readouterr().out
    assert text.startswith("### Mutation tests (mutmut)\n\n**33.3 %**")
    assert data["score"] == 33.3
    assert data["run"] == RUN
    # A complete run is a baseline itself; it keeps what it compared with for the job
    # of the issue.
    assert "baseline" not in data
    assert json.loads((out / "previous.json").read_text(encoding="utf-8")) == (
        comparable(90.0, 99.0)
    )
    assert "a.x_f__mutmut_2: survived" in (out / "results.txt").read_text(
        encoding="utf-8"
    )
    assert (
        (out / "survivors.md").read_text(encoding="utf-8").startswith("# The surviving")
    )

    # The report writes nothing to GitHub: a job of its own keeps the issue.
    assert github.issues == {}
    issue = ["--repo", REPO, "mutation", "issue", str(out)]
    assert cli.main(issue, Api(github)) == 0
    assert capsys.readouterr().out == "The score dropped: opened #1.\n"
    github.down = True
    assert cli.main(issue, Api(github)) == 2
    assert "GitHub answered 502: Bad Gateway" in capsys.readouterr().err


def test_the_issue_needs_the_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["--repo", REPO, "mutation", "issue", str(tmp_path)]) == 1
    assert "No mutation.json in" in capsys.readouterr().out


def test_a_drop_past_an_incomplete_run_still_shows(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    first = files(tmp_path, {"first.json": json.dumps(comparable(90.0, 99.0))})

    # The second run lacks a part: it compares with no other and keeps the first.
    code, second = report_of(tmp_path / "second", two_parts()[:1], first / "first.json")
    assert code == 1
    assert second["complete"] is False
    assert second["baseline"] == comparable(90.0, 99.0)

    # The third compares with the first, through the second, and the issue opens.
    code, third = report_of(
        tmp_path / "third",
        two_parts(),
        tmp_path / "second/mutation/mutation.json",
    )
    assert code == 0
    assert third["complete"] is True
    assert "baseline" not in third
    assert f"Since [the run of 2026-10-17]({BEFORE})" in capsys.readouterr().out
    github = FakeGitHub()
    folder = str(tmp_path / "third/mutation")
    assert cli.main(["--repo", REPO, "mutation", "issue", folder], Api(github)) == 0
    assert capsys.readouterr().out == "The score dropped: opened #1.\n"


def test_the_baseline_of_a_run() -> None:
    assert baseline_of(None) is None
    assert baseline_of({"complete": False}) is None
    assert baseline_of({"complete": False, "baseline": "x"}) is None
    assert baseline_of({"complete": False, "baseline": {"complete": False}}) is None
    assert baseline_of(comparable(1.0, 2.0)) == comparable(1.0, 2.0)
    kept = {"complete": False, "baseline": comparable(1.0, 2.0)}
    assert baseline_of(kept) == comparable(1.0, 2.0)


def test_a_report_without_results_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "mutation"

    code = cli.main(["mutation", "report", str(tmp_path / "none"), "--out", str(out)])

    assert code == 1
    assert "No mutant ran." in capsys.readouterr().out
    assert (
        json.loads((out / "mutation.json").read_text(encoding="utf-8"))["complete"]
        is False
    )
    files(tmp_path, {"broken/part-1.json": "{"})
    assert (
        cli.main(["mutation", "report", str(tmp_path / "broken"), "--out", str(out)])
        == 2
    )
