"""What every test of the run shares."""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator

import pytest
from shared import GIT_REPOSITORY_VARIABLES

import blueprint.github


@pytest.fixture(scope="session", autouse=True)
def no_repository_of_the_run() -> Iterator[None]:
    """No test sees the variables that point Git at the repository that runs the
    tests, such as GIT_DIR, which Git sets for the hook before a push in a worktree:
    git init in a test's own repository would rewrite the configuration of that one,
    and the commits of the test would land on its branch. git in the blueprint's own
    checkout gets them back from shared.git_environment()."""
    with pytest.MonkeyPatch.context() as patch:
        for name in GIT_REPOSITORY_VARIABLES:
            patch.delenv(name, raising=False)
        yield


@pytest.fixture(scope="session", autouse=True)
def bytecode_apart(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Each Python that a test starts keeps its bytecode in a folder of the run, not
    next to the code. The processes of pytest-xdist share the projects that the tests
    of the template render, and a test that copies a project would otherwise meet a
    file of __pycache__ that the Python of another test is writing there. The same goes
    for what a test loads into this Python, as a hook of a website."""
    before = os.environ.get("PYTHONPYCACHEPREFIX")
    prefix_before = sys.pycache_prefix
    folder = str(tmp_path_factory.mktemp("pycache"))
    os.environ["PYTHONPYCACHEPREFIX"] = folder
    sys.pycache_prefix = folder
    yield
    sys.pycache_prefix = prefix_before
    if before is None:
        del os.environ["PYTHONPYCACHEPREFIX"]
    else:
        os.environ["PYTHONPYCACHEPREFIX"] = before


@pytest.fixture(scope="session", autouse=True)
def no_settings_of_copier(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Copier renders with a settings file of the run, without defaults: those of the
    machine, such as an owner and a release app that a maintainer set for all of their
    repositories, would answer the questions that the tests leave to the defaults."""
    settings = tmp_path_factory.mktemp("copier") / "settings.yml"
    settings.write_text("defaults: {}\n", encoding="utf-8")
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("COPIER_SETTINGS_PATH", str(settings))
        yield


@pytest.fixture(autouse=True)
def waits(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """A request to GitHub that tries again waits first, as long as this list says;
    no test waits."""
    seconds: list[float] = []
    monkeypatch.setattr(blueprint.github, "sleep", seconds.append)
    return seconds
