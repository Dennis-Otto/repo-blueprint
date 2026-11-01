# The tests run on every logical core, at most eight, and the tests of the blueprint compile each template once

- Status: accepted, amended by [0102](0102-the-blueprint-checks-itself-on-python-3-14-and-its-tests-compile-once.md), which takes on the two costs that this record leaves for later
- Date: 2026-10-25

## Context

[Decision 0025](0025-run-the-tests-on-every-core.md) runs the tests of every Python project with `pytest -n auto`, a process for each core. Two weeks later, the tests are still the longest part of the required checks:

- **Home Assistant integrations run on half the cores.** `-n auto` counts the physical cores once psutil is installed, and the test tools of Home Assistant install it. A runner of GitHub has two physical cores with four logical ones, so the check of homedarts-for-autodarts started two processes (`created: 2/2 workers`) for its 3341 tests, which took 118 seconds; the whole job took between 180 and 293 seconds in the last six runs on `main`, against the goal of 130.
- **No limit on a large machine.** On a computer with 32 logical cores, `-n auto` starts 32 processes, each of which imports and collects every test once more and keeps it in its memory. Coding agents that run the checks of several repositories at once can run out of memory, and `PYTEST_XDIST_AUTO_NUM_WORKERS` helped only those who knew of it. In a container limited to fewer cores, pytest-xdist still counts those of the host.
- **The tests of the blueprint render about a hundred projects.** Copier makes a new environment of Jinja for each project and compiles every template anew, the names of the files among them: about 1400 for each project, two thirds of the time of a render. The step of the tests took 189 seconds for 3105 tests in the CI.

## Options

1. Keep `-n auto`, and set `PYTEST_XDIST_AUTO_NUM_WORKERS` in the workflow of each kind of project: one more place for each kind, and nothing for a machine of a maintainer.
2. `-n logical`, a process for each logical core, with or without psutil, and at most eight with `--maxprocesses`, which `PYTEST_XDIST_AUTO_NUM_WORKERS` raises or lowers.
3. `-n logical` without a limit.

For the tests of the blueprint:

1. Share more rendered projects: each test that changes an answer needs a project of its own, so few renders go.
2. Compile each template once for the whole process, with the settings of its environment and its source as the key, and leave Copier as it is.

## Decision

Option 2, and for the tests of the blueprint option 2.

- **The step:** `python -m pytest -n logical --maxprocesses="${PYTEST_XDIST_AUTO_NUM_WORKERS:-8}" --cov --cov-report= --cov-fail-under=0`. `-n logical` counts the logical cores with psutil and falls back to the cores that the process may use without it, as `-n auto` does then. Beyond eight processes, each one more mostly collects the tests again; `PYTEST_XDIST_AUTO_NUM_WORKERS` sets the number, eight or more alike, because the limit takes the same number.
- **The tests of the blueprint:** `render()` of `tests/test_template.py` lets Jinja compile each template once in each process of the tests, `compile_once()`. The key is the source and what its code depends on, `settings_of()`: the syntax, the extensions, the names of the filters and tests and the options of the code. The code of a template runs in each environment apart with its own values, as Jinja runs it from its own cache, and a test renders a project twice to show that the second render compiles nothing and writes the same files.

## Consequences

Home Assistant integrations run their tests on the four logical cores of a runner instead of two, once their update brings the step. A machine with many cores runs at most eight processes unless its maintainer sets more, and a container that sees the cores of its host no longer starts one for each.

A render of the tests of the blueprint takes 0.3 instead of 0.95 seconds once its templates are compiled, and the tests of the template took 62 instead of 88 seconds on four cores in a container of Linux. Two costs are left for later: each process of pytest-xdist still collects all 3100 tests anew and rewrites their assertions, 9 seconds at the start of each process there, and the coverage of the blueprint, measured with the tracer of C on Python 3.12, takes about a third of the time. On Python 3.14, where coverage measures with `sys.monitoring`, the tests of the template, of Downstream and of the diagrams took 82 instead of 142 seconds with their coverage.
