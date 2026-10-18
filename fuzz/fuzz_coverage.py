"""Coverage-guided fuzzing of the coverage bot of blueprint/coverage_comment.py, with Atheris.

The coverage.xml or lcov.info of a pull request is its own, also from a fork.
Whatever it holds, reading it either gives a report or raises ParseError, and the
comment of the bot keeps every name of a file as code in its cell: no row of its
tables gets another cell or a line break, and the comment fits into one comment of
GitHub.

    pip install --require-hashes -r stacks/fuzz/requirements.txt
    python fuzz/fuzz_coverage.py -max_total_time=60

The Fuzzing workflow runs it on every change and longer every week.
"""

import re
import sys
from pathlib import Path
from xml.etree.ElementTree import ParseError
from xml.sax.saxutils import escape, quoteattr

import atheris

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

with atheris.instrument_imports():
    from blueprint.coverage_comment import MOST_FILES, Coverage, coverage_comment

# The cells of a row, at every pipe that no backslash escapes, as GitHub splits it.
CELL = re.compile(r"(?<!\\)\|")
# One span of code: it ends only at a run of backticks as long as its first one.
CODE = re.compile(r"(`+)( ?)(.*)\2\1", re.S)


def report(provider: atheris.FuzzedDataProvider) -> str:
    """A Cobertura report: any text, or classes with any names and hits."""
    if provider.ConsumeBool():
        return provider.ConsumeUnicodeNoSurrogates(4000)
    classes = []
    # Now and then more files than the table shows, so that its cap and the length
    # of the comment are fuzzed too.
    files = (
        provider.ConsumeIntInRange(0, 8)
        if provider.ConsumeBool()
        else provider.ConsumeIntInRange(MOST_FILES, 2 * MOST_FILES)
    )
    for _ in range(files):
        name = quoteattr(provider.ConsumeUnicodeNoSurrogates(300))
        lines = "".join(
            f"<line number='1' hits={quoteattr(provider.ConsumeUnicodeNoSurrogates(8))}/>"
            for _ in range(provider.ConsumeIntInRange(0, 3))
        )
        classes.append(f"<class filename={name}><lines>{lines}</lines></class>")
    source = escape(provider.ConsumeUnicodeNoSurrogates(40))
    return (
        f"<coverage><sources><source>{source}</source></sources><packages><package>"
        f"<classes>{''.join(classes)}</classes></package></packages></coverage>"
    )


def lcov_report(provider: atheris.FuzzedDataProvider) -> str:
    """An LCOV report, as the test runner of Node writes it: any text, or records
    with any names and hits."""
    if provider.ConsumeBool():
        return provider.ConsumeUnicodeNoSurrogates(4000)
    files = (
        provider.ConsumeIntInRange(0, 8)
        if provider.ConsumeBool()
        else provider.ConsumeIntInRange(MOST_FILES, 2 * MOST_FILES)
    )
    records = []
    for _ in range(files):
        # A name on one line, as a line break would start the next entry.
        name = provider.ConsumeUnicodeNoSurrogates(300).splitlines() or [""]
        lines = "".join(
            f"DA:1,{provider.ConsumeUnicodeNoSurrogates(8)}\n"
            for _ in range(provider.ConsumeIntInRange(0, 3))
        )
        records.append(f"SF:{name[0]}\n{lines}end_of_record\n")
    return "".join(records)


def parsed(provider: atheris.FuzzedDataProvider) -> Coverage:
    """A report of either kind, as the coach reads it."""
    if provider.ConsumeBool():
        return Coverage.parse_lcov(lcov_report(provider), Path("/work"))
    return Coverage.parse(report(provider), Path("/work"))


def check(comment: str) -> None:
    if len(comment) >= 65536:
        raise AssertionError(f"a comment of {len(comment)} characters")
    rows = comment.splitlines()
    heading = "| File | main | This pull request |"
    for row in rows[rows.index(heading) + 2 :] if heading in rows else []:
        if not row.startswith("| "):
            continue
        cells = CELL.split(row)
        if len(cells) != 5 or cells[0] or cells[-1].strip():
            raise AssertionError(f"a row of {len(cells) - 2} cells: {row!r}")
        name = cells[1].strip()
        found = CODE.fullmatch(name)
        if name != "(unnamed file)" and not (
            found
            and len(found[1]) not in {len(run) for run in re.findall(r"`+", found[3])}
        ):
            raise AssertionError(f"a name that isn't one span of code: {name!r}")


def test_one_input(data: bytes) -> None:
    provider = atheris.FuzzedDataProvider(data)
    try:
        head = parsed(provider)
        base = parsed(provider)
    except ParseError:
        return
    check(coverage_comment(head, base))


def main() -> None:
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
