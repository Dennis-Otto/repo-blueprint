# Run the tests of Python projects on every core, with the same coverage gate

- Status: accepted, amended by [0069](0069-the-tests-run-on-every-logical-core-at-most-eight.md), with which the tests run on every logical core, at most eight
- Date: 2026-10-14

## Context

`scripts/check.sh` ran the tests of every Python project with `coverage run -m pytest`, one test after the other, on one core of the four that a runner of GitHub has:

- **Home Assistant integrations:** the test tools of Home Assistant pin pytest-xdist and pytest-cov, which no step used. ha-autodarts runs 1702 tests; with coverage, they took 152 seconds of its required check in the CI, and 89 instead of 304 seconds on four cores in a container. Once its end-to-end tests run only when they can change a result, this check is the longest one of a pull request.
- **The blueprint:** its 1400 tests took 92 seconds with coverage on four cores in a container of Linux, and 18 minutes on a Windows machine with other work, where Copier spends seconds on each project that it renders: it clones the blueprint with Git and asks Git about each file that it writes. `pytest -n 8` alone gave little, because each process rendered all seven kinds of projects again.
- **No time limit:** a test that hung held the check until the job ran out of its time.

## Options

1. Keep the tests serial, and make the slow ones faster one by one.
2. `pytest -n auto` with pytest-xdist and pytest-cov in `scripts/check.sh` where both are installed, else the serial run as before; the plugins and pytest-timeout in the lock files of new Python projects; the rendered projects of the tests of the blueprint made once for the whole run.
3. Option 2 with `-n auto` in `addopts` of `pyproject.toml`, so that a plain `pytest` runs in parallel too.

## Decision

Option 2.

- **The step:** when the Python of the project imports pytest, pytest-cov and xdist, `python -m pytest -n auto --cov --cov-report= --cov-fail-under=0` runs the tests in a process for each core, and pytest-cov measures each process and brings their coverage together in `.coverage`, which the CI shows as before. `coverage report` then applies `[tool.coverage]` of `pyproject.toml`, `fail_under` among them, and lists the lines that no test runs, as it did after `coverage run`. Without the plugins, the step runs `coverage run -m pytest` as before, so a project that keeps its own lock file without them keeps working. `PYTEST_XDIST_AUTO_NUM_WORKERS` sets the number of processes.
- **Not in `addopts`:** mutmut runs pytest inside its own process with the settings of `pyproject.toml`, and a project without the plugins would fail on an option that it doesn't know; `-n` belongs to the step.
- **New projects:** `requirements-dev.txt` of the Python stack pins pytest-xdist, pytest-cov and pytest-timeout, as the test tools of Home Assistant do already, and `pyproject.toml` gives each test 30 seconds, `timeout = 30`, where only Home Assistant had it. Both files belong to the project, so an existing one adds them itself, as the changelog says.
- **The tests of the blueprint** render from a copy of its files as Git sees them, without Git, so Copier doesn't clone it for each project; they don't ask Git about the index of a destination that is no repository. Each kind is rendered when a test first asks for it, once for the whole run: the first process that needs it renders it, and the others wait for it (`tests/shared.py`). The tests only read these projects, and one that changes a project works on a copy; the Python that a test starts keeps its bytecode in a folder of the run. Each test of the blueprint gets five minutes.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/how-the-tests-run-on-every-core.dark.svg">
  <img src="../images/diagrams/how-the-tests-run-on-every-core.svg" alt="How the tests run on every core: scripts/check.sh asks the Python of the project for pytest-xdist and pytest-cov. With both, pytest starts a process for each logical core, at most eight unless PYTEST_XDIST_AUTO_NUM_WORKERS sets another number, which share the tests between them, and pytest-cov brings the coverage of every process together. Without them, coverage runs the tests one after the other. Either way, coverage report applies the settings of the project, such as fail_under, and lists every line that no test runs.">
</picture>

## Consequences

The tests of the blueprint take 41 instead of 92 seconds on four cores in a container of Linux, and 27 on sixteen; ha-autodarts' take about a third of their time once it has the release. Each test stands on its own: a test that relies on the state or the order of another one fails now and then, and the flaky-test bot reports it. A test that hangs fails after its time limit instead of holding the check. Each process imports the tests and their tools once more, which costs memory: on a machine with many cores and little free memory, `PYTEST_XDIST_AUTO_NUM_WORKERS=4 bash scripts/check.sh` runs fewer processes. A project without the plugins sees no change until it adds them.
