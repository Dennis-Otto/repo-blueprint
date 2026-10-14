"""What the processes of one run of the tests share.

pytest-xdist runs the tests in a process for each core. A folder that is slow to make
and that many tests read, such as the blueprint rendered as a project of a kind, is
made once for the whole run: by the first process that asks for it, while the others
wait until it is done.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

import pytest

# How long a process waits for a folder that another one makes; a render takes
# seconds, and pytest-timeout ends the test long before.
PATIENCE = 600.0
# How often a process that waits looks whether the folder is done.
INTERVAL = 0.05


def run_folder(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The temporary folder of the whole run: with pytest-xdist, the folder that holds
    the one of each process, else the one of pytest itself."""
    folder = tmp_path_factory.getbasetemp()
    return folder.parent if "PYTEST_XDIST_WORKER" in os.environ else folder


def once(folder: Path, make: Callable[[Path], object]) -> Path:
    """The folder, which make fills in the first process that asks for it. The others
    wait until it is done, and a folder whose making failed fails for each of them."""
    claim = folder.with_name(f"{folder.name}.claim")
    done = folder.with_name(f"{folder.name}.done")
    failed = folder.with_name(f"{folder.name}.failed")
    try:
        # Making a folder is atomic: of the processes that try at once, one succeeds.
        claim.mkdir(parents=True)
    except FileExistsError:
        deadline = time.monotonic() + PATIENCE
        while not done.exists():
            if failed.exists():
                raise RuntimeError(
                    f"Making {folder} failed in another process of the tests: "
                    + failed.read_text(encoding="utf-8")
                ) from None
            if time.monotonic() > deadline:
                raise TimeoutError(
                    f"Another process of the tests didn't make {folder} within"
                    f" {PATIENCE:.0f} seconds."
                ) from None
            time.sleep(INTERVAL)
        return folder
    try:
        make(folder)
    except BaseException as error:
        failed.write_text(f"{type(error).__name__}: {error}", encoding="utf-8")
        raise
    done.touch()
    return folder


def copy_of(repository: Path, folder: Path) -> None:
    """The files of a Git repository as Git sees them, changes not yet committed
    included, without what .gitignore leaves out: Copier renders such a folder as it
    is, where it clones a repository and runs Git a hundred times for each render."""
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=repository,
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8")
    folder.mkdir(parents=True, exist_ok=True)
    for name in filter(None, listed.split("\0")):
        source = repository / name
        # A file deleted but not yet committed is listed, and is no more.
        if source.is_file():
            (folder / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, folder / name)
