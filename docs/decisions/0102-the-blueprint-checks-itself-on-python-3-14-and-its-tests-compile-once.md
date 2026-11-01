# The blueprint checks itself on Python 3.14, the tests of a Python project keep their temporary folders in memory on a runner, and the Pythons of the blueprint's tests share their bytecode

- Status: accepted
- Date: 2026-11-01

## Context

[Decision 0070](0070-the-tests-run-on-every-logical-core-at-most-eight.md) left two costs for later, and the goal of 20 seconds from issue #232 was still open. Since that goal was set, the tests of the blueprint have grown from about 1500 to about 4500. In the last four runs on `main` before this decision, `check (python)` took 24 to 32 seconds up to the first test and 185 to 280 seconds for the tests.

A profile on four CPUs in a container of Linux, the size of a runner of GitHub, and runs in the CI found what the time goes to:

- **Coverage with the tracer of C.** On Python 3.12, the tests took 128 seconds without coverage and 194 with it. Coverage measures branches with `sys.monitoring` only from Python 3.14 on, and it takes that by itself there.
- **The disk of the runner.** The tests make hundreds of projects and repositories in temporary folders, 0.8 GB in all. The one run on Python 3.14 with them on the disk took 186 seconds, and the four with them in `/dev/shm` took 134 to 175. The runs of the CI vary a lot, so this is no exact measure.
- **Bytecode that no Python found.** Each process of pytest-xdist had a folder of its own for `PYTHONPYCACHEPREFIX`. In such a folder Python finds none of the bytecode of its standard library and its packages, so that each process compiled them again for the Pythons of its tests. `blueprint.py` writes no bytecode at all, so that it leaves no `__pycache__` in a repository, and compiled the whole tool at each start, 240 instead of 150 milliseconds.
- **YAML in Python.** The tests parsed about 3800 texts with the parser of PyYAML in Python, 23 of the 460 seconds of all processes. The parser of libyaml, which the wheels of PyYAML bring, is ten times as fast.
- **Copier in a Python of its own.** Most tests of the Variants plan rendered a small template a dozen times, each with half a second to import Copier: 3 to 5 seconds a test.

## Options

For the Python of `check (python)`:

1. Stay on Python 3.12 and keep the tracer of C: a third of the time, for good.
2. Stay on Python 3.12 and measure lines only: `sys.monitoring` works there, without the branches, which `scripts/check.sh` requires.
3. Two runs, the tests on Python 3.12 and the coverage on Python 3.14: twice the work in every pull request.
4. Python 3.14 in `.python-version` of the blueprint, and Python 3.12, which the tool of every repository still runs on, where it costs no time in a required check.

For the temporary folders:

1. A `TMPDIR` in each workflow of a Python project: three workflows to keep equal, and nothing for a project that calls the script itself.
2. A `TMPDIR` in the step of the tests of `scripts/check.sh`, where it can see whether it fits.

## Decision

Option 4, and option 2 for the temporary folders.

- **The Python of the blueprint:** `.python-version` says 3.14, the one file in which the blueprint differs from what its template gives a GitHub Action. The template stays as it is, and its projects keep Python 3.12, or 3.14 for Home Assistant.
- **The oldest Python:** the tool keeps to the code of Python 3.12. mypy and Ruff check against that version, as before, the check on Windows runs all tests on it in each pull request that changes the code, and the Variants run the checks of the projects with it. A test keeps these versions equal.
- **The temporary folders:** in the CI on Linux, `scripts/check.sh` of a Python project sets `TMPDIR=/dev/shm` for its tests when at least 4 GB are free there and no `TMPDIR` is set. A job in a container has 64 MB there by default and stays on the disk, and so do Windows and the machine of a contributor.
- **The bytecode:** the Pythons that the tests start share one folder for the whole run, and `blueprint.py` writes bytecode when `PYTHONPYCACHEPREFIX` names such a folder, which is outside of the repository. Without it, the tool writes none, as before.
- **YAML:** `load_yaml()` of `tests/shared.py` takes the parser of libyaml, or the one of Python in a PyYAML without it, and a test fails on a `yaml.safe_load` in the tests.
- **Copier and gh in the tests:** the tests of the Variants plan run the same command of Copier in their own process, and a render that fails goes to the real one, which says why. A test on the real template and one of the plan as a script keep the real one. The fake gh imports `subprocess` and `shutil` only for an answer through `--jq`: it starts about 1600 times in a run.

## Consequences

`check (python)` takes about 160 seconds for 4564 tests, and 18 seconds up to the first test, against 185 to 280 seconds for up to 4549 tests. On four CPUs of a container the same tests take 82 seconds: a runner has two cores with two threads each, and it runs Harden-Runner next to the tests, whose share of the difference nobody measured.

The goal of 20 seconds stays out of reach. What is left is the work that the tests are there for, for each test its own process or project: the bash of the steps of the workflows takes about 97 of the 360 seconds of all processes in that container, Copier about 95, Git about 20, and no test takes more than eight seconds. Fewer seconds would take fewer real renders and steps, or the required check split across several runners, with its coverage brought together afterwards. Neither was worth its price here, and the second is a decision of its own if the time still hurts.

These gained nothing in the measurements, so they are not in: `gc.freeze()` after the collection, `--dist worksteal` and `uv pip install --compile-bytecode`. Each process of pytest-xdist still collects all tests. Rewriting their assertions once in advance would save little, because the processes do it side by side today, and `tests/test_template.py` alone holds a third of the lines.

A project whose tests write several gigabytes to temporary folders now fills its memory instead of its disk: `/dev/shm` holds half of the 16 GB of a runner, and a job fails when it is full. Such a project sets `TMPDIR` itself in the workflow, which the script leaves alone.

A local run on Python 3.12, as in the development container, takes the tracer of C again, which only takes longer. A mistake that shows on Python 3.12 alone at run time, as with a function of the standard library that mypy doesn't know, shows in the check on Windows, which is not required, instead of in `check (python)`.

For the Home Assistant integration homedarts-for-autodarts, the measurement that issue #433 asked for gave 4/4 workers, 153 seconds for 4432 tests and 193 to 345 seconds for the job, against the goal of 130 for the job from when it had 3341 tests. It has Python 3.14 already and gains the temporary folders with its next update, so the goal stays open there.
