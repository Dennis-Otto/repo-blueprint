"""What every test of the run shares."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest


@pytest.fixture(scope="session", autouse=True)
def bytecode_apart(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Each Python that a test starts keeps its bytecode in a folder of the run, not
    next to the code. The processes of pytest-xdist share the projects that the tests
    of the template render, and a test that copies a project would otherwise meet a
    file of __pycache__ that the Python of another test is writing there."""
    before = os.environ.get("PYTHONPYCACHEPREFIX")
    os.environ["PYTHONPYCACHEPREFIX"] = str(tmp_path_factory.mktemp("pycache"))
    yield
    if before is None:
        del os.environ["PYTHONPYCACHEPREFIX"]
    else:
        os.environ["PYTHONPYCACHEPREFIX"] = before
