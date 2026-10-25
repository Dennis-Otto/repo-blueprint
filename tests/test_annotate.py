"""Tests of the annotations of the tools of scripts/check.sh: what each tool wrote in a
real run, and the annotations at the lines of the files of the repository."""

from __future__ import annotations

import io
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from blueprint import annotate, cli
from blueprint.annotate import (
    MESSAGE_LENGTH,
    Annotation,
    annotations_of,
    changes,
    junit,
    located,
    mypy,
    node_test,
    php_cs_fixer,
    shellcheck,
)

# The spec reporter of Node starts its lines with marks of information, which Ruff takes
# for letters.
# ruff: noqa: RUF001

DATA = Path(__file__).parent / "data/annotate"

# ShellCheck 0.11.0 --format=gcc, of a script with four kinds of findings.
SHELLCHECK = (
    "demo.sh:2:6: note: Double quote to prevent globbing and word splitting. [SC2086]",
    "demo.sh:3:1: warning: Use 'cd ... || exit' or 'cd ... || return' in case cd fails. [SC2164]",
    "demo.sh:4:10: error: Iterating over ls output is fragile. Use globs. [SC2045]",
    "demo.sh:5:3: warning: x is referenced but not assigned. [SC2154]",
)
# mypy 2.4.0 --no-pretty --show-error-end, strict, with a note of reveal_type of its own.
MYPY = (
    'demo.py:5:15:5:23: error: Incompatible types in assignment (expression has type "int", variable has type "str")  [assignment]',
    'demo.py:6:5:6:7: error: Argument 1 to "add" has incompatible type "str"; expected "int"  [arg-type]',
    'demo.py:8:12:8:12: error: Argument 1 to "loads" has incompatible type "int"; expected "str | bytes | bytearray"  [arg-type]',
    'demo.py:9:13:9:18: note: Revealed type is "str"',
    "Found 3 errors in 1 file (checked 1 source file)",
)
# mypy 2.4.0 with its default settings, an overload whose variants the notes name.
MYPY_OVERLOAD = (
    'demo.py:3: error: No overload variant of "get" of "dict" matches argument type "int"  [call-overload]',
    "demo.py:3: note: Possible overload variants:",
    "demo.py:3: note:     def get(self, str, None = ..., /) -> int | None",
    "demo.py:3: note:     def get(self, str, int, /) -> int",
    "demo.py:3: note:     def [_T] get(self, str, _T, /) -> int | _T",
    "Found 1 error in 1 file (checked 1 source file)",
)


def files(root: Path, *names: str) -> Path:
    for name in names:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text("text\n", encoding="utf-8")
    return root


def commands(found: Iterator[Annotation]) -> list[str]:
    return [annotation.command() for annotation in found]


def test_shellcheck_annotates_each_finding_with_its_rule(tmp_path: Path) -> None:
    root = files(tmp_path, "demo.sh")

    assert commands(shellcheck(SHELLCHECK, root)) == [
        "::error file=demo.sh,line=2,col=6,title=ShellCheck SC2086::Double quote to "
        "prevent globbing and word splitting. https://www.shellcheck.net/wiki/SC2086",
        "::error file=demo.sh,line=3,col=1,title=ShellCheck SC2164::Use 'cd ... || "
        "exit' or 'cd ... || return' in case cd fails. "
        "https://www.shellcheck.net/wiki/SC2164",
        "::error file=demo.sh,line=4,col=10,title=ShellCheck SC2045::Iterating over ls "
        "output is fragile. Use globs. https://www.shellcheck.net/wiki/SC2045",
        "::error file=demo.sh,line=5,col=3,title=ShellCheck SC2154::x is referenced "
        "but not assigned. https://www.shellcheck.net/wiki/SC2154",
    ]
    # A finding without a rule, which gcc's format allows, and a script that is gone.
    assert commands(
        shellcheck(["demo.sh:1:1: error: Broken.", "gone.sh:1:1: note: x"], root)
    ) == [
        "::error file=demo.sh,line=1,col=1,title=ShellCheck::Broken.",
        "::error title=ShellCheck::x",
    ]


def test_mypy_annotates_each_error_where_it_starts_and_ends(tmp_path: Path) -> None:
    root = files(tmp_path, "demo.py")

    assert commands(mypy(MYPY, root)) == [
        "::error file=demo.py,line=5,endLine=5,col=15,endColumn=23,title=Mypy "
        '(assignment)::Incompatible types in assignment (expression has type "int", '
        'variable has type "str")',
        "::error file=demo.py,line=6,endLine=6,col=5,endColumn=7,title=Mypy "
        '(arg-type)::Argument 1 to "add" has incompatible type "str"; expected "int"',
        # The note of reveal_type, at another line, is no part of it.
        "::error file=demo.py,line=8,endLine=8,col=12,endColumn=12,title=Mypy "
        '(arg-type)::Argument 1 to "loads" has incompatible type "int"; expected '
        '"str | bytes | bytearray"',
    ]
    # The notes at the line of an error belong to it; a note before any error is no
    # finding, and an error without its code has none in its title.
    assert commands(
        mypy(["demo.py:1: note: alone", *MYPY_OVERLOAD, "demo.py:4: error: x"], root)
    ) == [
        "::error file=demo.py,line=3,title=Mypy (call-overload)::No overload variant "
        'of "get" of "dict" matches argument type "int"%0APossible overload '
        "variants:%0A    def get(self, str, None = ..., /) -> int | None%0A    def "
        "get(self, str, int, /) -> int%0A    def [_T] get(self, str, _T, /) -> int | _T",
        "::error file=demo.py,line=4,title=Mypy::x",
    ]
    assert commands(mypy(["Success: no issues found in 1 source file"], root)) == []


# Node 24.14.1, npm test of the template: the spec reporter on stdout.
NODE_TEST = (
    "▶ add",
    "  ✔ adds (1.1104ms)",
    "  ✖ adds wrong (1.5115ms)",
    "✖ add (4.4254ms)",
    "✖ throws (0.1669ms)",
    "ℹ tests 3",
    "ℹ suites 1",
    "ℹ pass 1",
    "ℹ fail 2",
    "ℹ cancelled 0",
    "ℹ skipped 0",
    "ℹ todo 0",
    "ℹ duration_ms 278.9975",
    "ℹ start of coverage report",
    "ℹ ----------------------------------------------------------",
    "ℹ file      | line % | branch % | funcs % | uncovered lines",
    "ℹ ----------------------------------------------------------",
    "ℹ src       |        |          |         | ",
    "ℹ  add.ts   | 100.00 |   100.00 |  100.00 | ",
    "ℹ ----------------------------------------------------------",
    "ℹ all files | 100.00 |   100.00 |  100.00 | ",
    "ℹ ----------------------------------------------------------",
    "ℹ end of coverage report",
    "",
    "✖ failing tests:",
    "",
    "test at test\\add.test.ts:9:3",
    "✖ adds wrong (1.5115ms)",
    "  AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:",
    "  ",
    "  3 !== 4",
    "  ",
    "      at TestContext.<anonymous> (@URL@/test/add.test.ts:10:12)",
    "      at Test.runInAsyncScope (node:async_hooks:228:14)",
    "      at Test.run (node:internal/test_runner/test:1118:25)",
    "      at Suite.processPendingSubtests (node:internal/test_runner/test:787:18)",
    "      at Test.postRun (node:internal/test_runner/test:1247:19)",
    "      at Test.run (node:internal/test_runner/test:1175:12)",
    "      at async Promise.all (index 0)",
    "      at async Suite.run (node:internal/test_runner/test:1533:7)",
    "      at async startSubtestAfterBootstrap (node:internal/test_runner/harness:358:3) {",
    "    generatedMessage: true,",
    "    code: 'ERR_ASSERTION',",
    "    actual: 3,",
    "    expected: 4,",
    "    operator: 'strictEqual',",
    "    diff: 'simple'",
    "  }",
    "",
    "test at test\\add.test.ts:14:1",
    "✖ throws (0.1669ms)",
    "  Error: boom",
    "      at TestContext.<anonymous> (@URL@/test/add.test.ts:15:9)",
    "      at Test.runInAsyncScope (node:async_hooks:228:14)",
    "      at Test.run (node:internal/test_runner/test:1118:25)",
    "      at Test.processPendingSubtests (node:internal/test_runner/test:787:18)",
    "      at Suite.postRun (node:internal/test_runner/test:1247:19)",
    "      at Suite.run (node:internal/test_runner/test:1548:10)",
    "      at async startSubtestAfterBootstrap (node:internal/test_runner/harness:358:3)",
)

# PHP CS Fixer 3.95.27, fix --dry-run --diff with the Nextcloud coding standard.
PHP_CS_FIXER = (
    "You are running PHP CS Fixer on PHP 8.5.11, but the minimum PHP version supported by your project in composer.json is PHP 8.2. Executing PHP CS Fixer on newer PHP versions may introduce syntax or features not yet available in PHP 8.2, which could cause issues under that version. It is recommended to run PHP CS Fixer on PHP 8.2, to fit your project specifics.",
    "If you need help while solving warnings, ask at https://github.com/PHP-CS-Fixer/PHP-CS-Fixer/discussions/, we will help you!",
    "",
    "PHP CS Fixer 3.95.27 (730c761) Adalbertus by Fabien Potencier, Dariusz Ruminski and contributors.",
    "PHP runtime: 8.5.11",
    'Loaded config default from "@ROOT@/.php-cs-fixer.dist.php".',
    "Running analysis on 31 cores with 10 files per process.",
    " 0/2 [░░░░░░░░░░░░░░░░░░░░░░░░░░░░]   0%",
    " 1/2 [▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░]  50%",
    " 2/2 [▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓] 100%",
    "",
    "   1) lib/Calc.php",
    "      ---------- begin diff ----------",
    "--- @ROOT@/lib/Calc.php",
    "+++ @ROOT@/lib/Calc.php",
    "@@ -9,9 +9,10 @@",
    " \t\treturn $a + $b;",
    " \t}",
    " ",
    "-\tpublic function   sub(int $a,int $b): int",
    "-\t{",
    "-\t\tif($a>$b){ return $a - $b; }",
    "-\t\treturn $b-$a;",
    "+\tpublic function sub(int $a, int $b): int {",
    "+\t\tif ($a > $b) {",
    "+\t\t\treturn $a - $b;",
    "+\t\t}",
    "+\t\treturn $b - $a;",
    " \t}",
    " }",
    "",
    "      ----------- end diff -----------",
    "",
    "",
    "Found 1 of 2 files that can be fixed in 0.234 seconds, 20.00 MB memory used",
)


def real(lines: tuple[str, ...], root: Path) -> list[str]:
    """The lines of a real run, with the folder of this test where the run had its own."""
    return [
        line.replace("@URL@", root.as_uri()).replace("@ROOT@", root.as_posix())
        for line in lines
    ]


def test_php_cs_fixer_annotates_each_change_of_its_diff(tmp_path: Path) -> None:
    root = files(tmp_path, "lib/Calc.php")

    assert commands(php_cs_fixer(real(PHP_CS_FIXER, root), root)) == [
        "::error file=lib/Calc.php,line=12,endLine=15,title=PHP CS Fixer::The coding "
        "standard writes these lines as:%0A\tpublic function sub(int $a, int $b): int "
        "{%0A\t\tif ($a > $b) {%0A\t\t\treturn $a - $b;%0A\t\t}%0A\t\treturn $b - $a;"
        "%0Avendor/bin/php-cs-fixer fix makes the change.",
    ]


def test_php_cs_fixer_annotates_lines_that_it_adds_or_removes(tmp_path: Path) -> None:
    root = files(tmp_path, "lib/A.php")
    diff = [
        # As -v names the file, with its fixers.
        "   1) lib/A.php (no_trailing_whitespace, single_blank_line_at_eof)",
        "      ---------- begin diff ----------",
        "--- Original",
        "+++ New",
        "@@ -1,2 +1,3 @@",
        "+<?php",
        " ",
        "-x",
        "\\ No newline at end of file",
        "+x",
        "@@ -9 +9,26 @@",
        " y",
        *[f"+line {number}" for number in range(25)],
        "      ----------- end diff -----------",
        # A file outside the repository has no annotation, a cut diff ends.
        "   2) ../elsewhere.php",
        "@@ -1 +1 @@",
        "-a",
        "   3) lib/A.php",
        "@@ -5,2 +5,2 @@",
        "-b",
    ]

    found = list(php_cs_fixer(diff, root))

    assert [(item.title, item.line, item.end_line) for item in found] == [
        ("PHP CS Fixer (no_trailing_whitespace, single_blank_line_at_eof)", 1, 1),
        ("PHP CS Fixer (no_trailing_whitespace, single_blank_line_at_eof)", 2, 2),
        ("PHP CS Fixer (no_trailing_whitespace, single_blank_line_at_eof)", 9, 9),
        ("PHP CS Fixer", 5, 5),
    ]
    assert found[0].message.startswith(
        "The coding standard writes these lines as:\n<?php"
    )
    assert found[1].message.startswith(
        "The coding standard writes these lines as:\nx\n"
    )
    assert found[3].message.startswith("The coding standard removes these lines.")
    assert found[2].message.splitlines()[-2:] == [
        "… and 5 more lines",
        "vendor/bin/php-cs-fixer fix makes the change.",
    ]


def test_a_hunk_counts_its_lines_on_the_side_of_the_head() -> None:
    hunk = iter(["-a", "+b", "+c", " d", "-e", " f", "+g"])

    found = changes(hunk, 10, 4, 5)

    assert [(change.first, change.last, change.added) for change in found] == [
        (10, 10, ["b", "c"]),
        (12, 12, []),
        (13, 13, ["g"]),
    ]


def test_node_test_annotates_each_failing_test_at_its_line(tmp_path: Path) -> None:
    root = files(tmp_path, "test/add.test.ts")

    assert commands(node_test(real(NODE_TEST, root), root)) == [
        "::error file=test/add.test.ts,line=10,col=12,title=Node test%3A adds wrong::"
        "AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:%0A%0A3 "
        "!== 4",
        "::error file=test/add.test.ts,line=15,col=9,title=Node test%3A throws::Error: "
        "boom",
    ]


def test_node_test_falls_back_to_where_a_test_starts(tmp_path: Path) -> None:
    root = files(tmp_path, "test/a.test.ts")
    lines = [
        "✔ passes (1ms)",
        "✖ failing tests:",
        "",
        "test at test/a.test.ts:3:1",
        "✖ test/a.test.ts (159.327ms)",
        "  'test failed'",
        "npm error Lifecycle script `test` failed",
        # A stack of no file of the repository, and a test in a file that is gone.
        "test at test/a.test.ts:7:3",
        "✖ times out (5000ms)",
        "      at Timeout._onTimeout (file:///usr/lib/node/x.js:1:1)",
        "test at test/gone.test.ts:1:1",
    ]

    assert commands(node_test(lines, root)) == [
        "::error file=test/a.test.ts,line=3,col=1,title=Node test%3A test/a.test.ts::"
        "'test failed'",
        "::error file=test/a.test.ts,line=7,col=3,title=Node test%3A times out::The "
        "test failed.",
        "::error title=Node test::The test failed.",
    ]
    assert commands(node_test(["✔ passes (1ms)", "ℹ pass 1"], root)) == []


def test_junit_of_pytest_annotates_where_each_test_failed(tmp_path: Path) -> None:
    root = files(tmp_path, "tests/test_demo.py")
    report = (DATA / "pytest.xml").read_text(encoding="utf-8")

    assert commands(junit(report, root, annotate.PYTEST)) == [
        # Where the error happened, in the helper that the test calls.
        "::error file=tests/test_demo.py,line=5,title=pytest%3A "
        "tests/test_demo.py%3A%3Atest_raises::ValueError: bad value 3",
        # Without the colors of the diff that pytest keeps in the report.
        "::error file=tests/test_demo.py,line=13,title=pytest%3A "
        "tests/test_demo.py%3A%3Atest_fails::assert [1, 2] == [1, 3]%0A  %0A  At "
        "index 1 diff: 2 != 3%0A  Use -v to get more diff",
        "::error file=tests/test_demo.py,line=22,title=pytest%3A "
        "tests/test_demo.py%3A%3Atest_param[2]::AssertionError: n is not one%0Aassert "
        "2 == 1",
    ]


def test_junit_of_phpunit_annotates_where_each_test_failed(tmp_path: Path) -> None:
    root = files(tmp_path, "tests/Unit/CalcTest.php")
    report = (DATA / "phpunit.xml").read_text(encoding="utf-8")

    assert commands(
        junit(report.replace("@ROOT@", root.as_posix()), root, annotate.PHPUNIT)
    ) == [
        "::error file=tests/Unit/CalcTest.php,line=16,title=PHPUnit%3A "
        "CalcTest%3A%3AtestAddsWrong::one and two%0AFailed asserting that 3 is "
        "identical to 4.",
        "::error file=tests/Unit/CalcTest.php,line=20,title=PHPUnit%3A "
        "CalcTest%3A%3AtestThrows::RuntimeException: boom",
    ]


def test_junit_falls_back_to_where_a_test_starts(tmp_path: Path) -> None:
    root = files(tmp_path, "tests/test_a.py", "tests/ATest.php")
    report = """<testsuites>
      <testcase classname="tests.test_a.TestA" name="test_b" file="tests/test_a.py" line="4">
        <error message="failed on setup with &quot;KeyError&quot;">/usr/lib/x.py:3: KeyError</error>
      </testcase>
      <testcase classname="tests.test_a" name="test_c" line="x"><failure>boom</failure></testcase>
      <testcase classname="other" name="test_d"><failure/></testcase>
    </testsuites>"""
    php = (
        '<testsuites><testcase name="testA" class="ATest" file="tests/ATest.php" line="8">'
        "<failure>Other::name\nFailed.\n\n"
        "vendor/phpunit/phpunit/src/Framework/Assert.php:12</failure>"
        "</testcase></testsuites>"
    )

    assert commands(junit(report, root, annotate.PYTEST)) == [
        "::error file=tests/test_a.py,line=5,title=pytest%3A "
        'tests/test_a.py%3A%3ATestA%3A%3Atest_b::failed on setup with "KeyError"',
        "::error title=pytest%3A tests.test_a%3A%3Atest_c::boom",
        "::error title=pytest%3A other%3A%3Atest_d::The test failed.",
    ]
    assert commands(junit(php, root, annotate.PHPUNIT)) == [
        # The trace in vendor/ is no line of the project, and the first line names
        # another test.
        "::error file=tests/ATest.php,line=8,title=PHPUnit%3A ATest%3A%3AtestA::"
        "Other::name%0AFailed.",
    ]


def test_only_a_file_of_the_repository_gets_the_annotation(tmp_path: Path) -> None:
    root = files(tmp_path / "repository", "a.py", "vendor/b.php", "node_modules/c.js")
    (tmp_path / "outside.py").write_text("x\n", encoding="utf-8")

    assert located("a.py", root) == "a.py"
    assert located(str(root / "a.py"), root) == "a.py"
    assert located("./x/../a.py", root) == "a.py"
    for name in (
        "../outside.py",
        str(tmp_path / "outside.py"),
        "gone.py",
        ".",
        "a\0.py",
    ):
        assert located(name, root) == "", name
    # Nor one of the packages that the tools install.
    assert located("vendor/b.php", root) == ""
    assert located("node_modules/c.js", root) == ""


def test_no_text_of_a_tool_ends_its_command_early() -> None:
    found = Annotation(
        title="a: b, c",
        message="100 %\r\n::error::forged\x1b[31m",
        path="x,y:z%\n.py",
        line=3,
        column=2,
        end_line=4,
        end_column=5,
    )

    assert found.command() == (
        "::error file=x%2Cy%3Az%25%0A.py,line=3,endLine=4,col=2,endColumn=5,title=a%3A "
        "b%2C c::100 %25%0D%0A::error::forged"
    )
    # Without a file there is no line, and a long message is cut.
    long = Annotation(title="t", message="x" * (MESSAGE_LENGTH + 5), line=3)
    assert long.command() == f"::error title=t::{'x' * (MESSAGE_LENGTH - 1)}…"


def test_the_output_of_a_tool_passes_on_as_it_is(tmp_path: Path) -> None:
    root = files(tmp_path, "demo.sh")
    written = b"".join(f"{line}\r\n".encode() for line in SHELLCHECK) + b"\xff no UTF-8"
    sink = io.BytesIO()

    found = annotations_of("shellcheck", "", root, io.BytesIO(written), sink)

    assert sink.getvalue() == written
    assert found[0] == "::group::Annotations"
    assert found[1].startswith("::error file=demo.sh,line=2,col=6,")
    assert found[-1] == "::endgroup::"
    assert len(found) == len(SHELLCHECK) + 2
    # Nothing found, nothing to group.
    assert (
        annotations_of("mypy", "", root, io.BytesIO(b"Success\n"), io.BytesIO()) == []
    )


def test_a_parser_that_stumbles_passes_the_rest_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def broken(lines: Iterator[str], root: Path) -> Iterator[Annotation]:
        next(iter(lines))
        raise ValueError("unexpected")

    monkeypatch.setitem(annotate.STREAMS, "mypy", broken)
    sink = io.BytesIO()

    found = annotations_of("mypy", "", tmp_path, io.BytesIO(b"one\ntwo\n"), sink)

    assert (found, sink.getvalue()) == ([], b"one\ntwo\n")
    assert "no annotations of mypy: ValueError('unexpected')" in capsys.readouterr().err


def test_a_report_that_is_missing_or_no_xml_has_no_annotations(tmp_path: Path) -> None:
    (tmp_path / "broken.xml").write_text("<testsuites>", encoding="utf-8")

    for report in ("missing.xml", str(tmp_path / "broken.xml")):
        assert (
            annotations_of("pytest", report, tmp_path, io.BytesIO(), io.BytesIO()) == []
        )


def test_the_command_annotates_what_comes_in(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsysbinary: pytest.CaptureFixture[bytes],
) -> None:
    files(tmp_path, "demo.sh")
    monkeypatch.chdir(tmp_path)
    written = "\n".join(SHELLCHECK).encode() + b"\n"
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(written)))

    assert cli.main(["annotate", "shellcheck"]) == 0
    output = capsysbinary.readouterr().out.decode()
    assert output.startswith(
        written.decode() + "::group::Annotations\n::error file=demo.sh,"
    )
    assert output.endswith("::endgroup::\n")

    report = DATA / "phpunit.xml"
    assert cli.main(["annotate", "phpunit", str(report)]) == 0
    # The files of the report are those of another folder.
    assert capsysbinary.readouterr().out.decode().count("::error title=PHPUnit") == 2


@given(st.lists(st.text(max_size=80), max_size=30))
def test_no_output_of_a_tool_breaks_a_parser(lines: list[str]) -> None:
    root = Path.cwd()
    for parse in annotate.STREAMS.values():
        for found in parse(lines, root):
            assert found.command().startswith("::error ")
            assert "\n" not in found.command()
