"""The bash that the tests run the scripts and the steps of the workflows in."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


# By its full path. Windows looks for a bare "bash" in System32 before the PATH, and
# has the launcher of WSL as bash.exe there and in WindowsApps, which runs the step in
# Linux without the variables of the test. So the search leaves out these two folders
# and ends with the bash of Git for Windows next to its git: the PATH of Git Bash,
# which scripts/check.sh runs in, has that bash first, while the PATH of PowerShell or
# of the test runner of an IDE has only its git.
def find_bash() -> str | None:
    path = [
        entry
        for entry in os.environ.get("PATH", os.defpath).split(os.pathsep)
        if Path(entry).name.casefold() not in {"system32", "windowsapps"}
    ]
    git = shutil.which("git")
    if git:
        path.append(str(Path(git).parents[1] / "bin"))
    return shutil.which("bash", path=os.pathsep.join(path))


BASH = find_bash()
