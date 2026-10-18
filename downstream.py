#!/usr/bin/env python3
"""The update of every repository that takes the blueprint, tried before a release.

The Rollout brings each release to the repositories that take the blueprint within
minutes, where the blueprint bot runs `copier update`: a conflict, or a workflow that
the update breaks, showed there only after the release. tests/answers/ holds the
answers of each of these repositories, and

    python3 downstream.py [--head REF] [--base REF]
        clones each repository, read-only, and updates it as its blueprint bot does,
        without --trust, from the version that it has to REF of this checkout: HEAD
        by default, with the changes that aren't committed yet. It lists the files
        that the update changes and those that it leaves a conflict in, and with
        --base the files whose update REF changes against BASE, such as the commit of
        main that a pull request merges into. An update that fails fails it, and so
        does a conflict in a file that runs, such as a workflow or a script, that REF
        brings. It warns of answers in tests/answers/ that differ from those of the
        repository.
    python3 downstream.py --answers
        writes tests/answers/ anew from the answers of each repository on GitHub.

The Downstream workflow runs it in each pull request that changes what the
repositories get from the blueprint, and every week.
https://github.com/Dennis-Otto/repo-blueprint
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from blueprint.update import MARKERS

ROOT = Path(__file__).resolve().parent
ANSWERS = Path("tests/answers")
ANSWERS_FILE = ".copier-answers.yml"
# Copier's own answers: the version of the blueprint that a repository has, and where
# the blueprint comes from, which every repository has of its own.
OWN = ("_commit", "_src_path")
SOURCE = "https://github.com/{repository}.git"
RAW = "https://raw.githubusercontent.com/{repository}/HEAD/" + ANSWERS_FILE
HEADER = """\
# The answers of https://github.com/{repository},
# as its .copier-answers.yml has them, without _commit and _src_path. The Variants
# workflow makes a repository with them and updates one from the latest release,
# and the Downstream workflow warns when they differ from those of the repository:
# change them with the repository.
"""
# The files that run, whose conflict breaks the checks or the bots of a repository,
# not only a page of its text: workflows, hooks, scripts and code.
RUNS = re.compile(r"^(?:\.github/workflows/|\.githooks/|scripts/)|\.(?:sh|py)$")
# Each clone and download tries three times, 10 and 20 seconds apart, as the
# workflows do.
TRIES = 3
AGENT = "downstream.py of https://github.com/Dennis-Otto/repo-blueprint"
# The commit that points a clone at this checkout, which nobody pushes.
COMMITTER = (
    "-c",
    "user.name=Downstream",
    "-c",
    "user.email=downstream@users.noreply.github.com",
    "-c",
    "commit.gpgsign=false",
)

Fetch = Callable[[str], str]
Sleep = Callable[[float], None]


class Failed(Exception):
    """What went wrong with one repository."""


@dataclass
class Update:
    """The update of one repository to REF."""

    repository: str
    answers: Path
    version: str = ""
    # The status of each file that the update changes, as git diff names it: A, M or D.
    changed: list[tuple[str, str]] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    # With a base: the files whose update REF changes, and the conflicts of BASE.
    touched: list[str] | None = None
    before: list[str] = field(default_factory=list)
    drift: list[str] = field(default_factory=list)
    error: str = ""

    def ours(self, path: str) -> bool:
        """Whether REF brings the conflict in path: every conflict without a base."""
        return self.touched is None or path in self.touched

    @property
    def breaking(self) -> list[str]:
        """The conflicts that REF brings into files that run."""
        return [
            path for path in self.conflicts if self.ours(path) and RUNS.search(path)
        ]


def environment() -> dict[str, str]:
    """Git and Copier as the blueprint bot runs them: without the maintenance that Git
    starts in the background after a commit, which Copier's update collides with."""
    return {
        **os.environ,
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "maintenance.auto",
        "GIT_CONFIG_VALUE_0": "false",
    }


def run(folder: Path, *command: str) -> str:
    """The output of a command in folder, or its last line of errors as a failure."""
    result = subprocess.run(
        command,
        cwd=folder,
        env=environment(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode:
        lines = (result.stderr or result.stdout).strip().splitlines()
        raise Failed(lines[-1] if lines else f"exit code {result.returncode}")
    return result.stdout


def git(folder: Path, *arguments: str) -> str:
    return run(folder, "git", *arguments)


def mapping(text: str, where: str) -> dict[str, Any]:
    try:
        answers = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise Failed(f"{where} can't be read as YAML") from error
    if not isinstance(answers, dict):
        raise Failed(f"{where} holds no answers")
    return answers


def read(path: Path) -> dict[str, Any]:
    return mapping(path.read_text(encoding="utf-8"), path.as_posix())


def repository_of(answers: Mapping[str, Any]) -> str:
    return f"{answers['owner']}/{answers['project_slug']}"


def text_of(repository: str, answers: Mapping[str, Any]) -> str:
    """A file of tests/answers/: the answers of a repository but Copier's own."""
    kept = {key: value for key, value in answers.items() if key not in OWN}
    text: str = yaml.safe_dump(kept, sort_keys=True, allow_unicode=True, width=80)
    return HEADER.format(repository=repository) + text


def drift(ours: Mapping[str, Any], theirs: Mapping[str, Any]) -> list[str]:
    """The answers that differ, but Copier's own."""
    keys = (ours.keys() | theirs.keys()) - set(OWN)
    return sorted(key for key in keys if ours.get(key) != theirs.get(key))


def clone(source: str, folder: Path, sleep: Sleep) -> None:
    attempt = 1
    while True:
        try:
            git(folder.parent, "clone", "--quiet", "--depth", "1", source, folder.name)
            return
        except Failed as error:
            if attempt == TRIES:
                raise Failed(f"could not be cloned from {source}: {error}") from error
            shutil.rmtree(folder, ignore_errors=True)
            sleep(attempt * 10)
            attempt += 1


def point(folder: Path, template: Path) -> str:
    """Point the clone at the template here, as its only commit of its own, and give
    the text of its answers as the repository has them."""
    path = folder / ANSWERS_FILE
    if not path.is_file():
        raise Failed(f"has no {ANSWERS_FILE}")
    text = path.read_text(encoding="utf-8")
    pointed, found = re.subn(
        r"^_src_path: .*$",
        f"_src_path: {json.dumps(template.as_posix())}",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if not found:
        raise Failed(f"{ANSWERS_FILE} names no _src_path")
    path.write_text(pointed, encoding="utf-8", newline="\n")
    git(folder, *COMMITTER, "commit", "--quiet", "--all", "--message", "Downstream")
    return text


def update(folder: Path, ref: str) -> dict[str, bytes]:
    """Update the clone to ref as the blueprint bot does, and give its files."""
    try:
        run(
            folder,
            sys.executable,
            "-m",
            "copier",
            "update",
            "--quiet",
            "--defaults",
            "--conflict",
            "inline",
            "--vcs-ref",
            ref,
        )
    except Failed as error:
        raise Failed(f"could not be updated to {short(ref)}: {error}") from error
    git(folder, "add", "--all")
    return {
        path.relative_to(folder).as_posix(): path.read_bytes()
        for path in folder.rglob("*")
        if path.relative_to(folder).parts[0] != ".git" and path.is_file()
    }


def comparable(name: str, data: bytes | None) -> bytes | None:
    """The file as REF and BASE can differ in it: in the answers, but the version."""
    if name == ANSWERS_FILE and data is not None:
        return re.sub(rb"^_commit: .*\n", b"", data, flags=re.MULTILINE)
    return data


def conflicted(files: Mapping[str, bytes]) -> list[str]:
    return sorted(name for name, data in files.items() if MARKERS.search(data))


def changes(folder: Path) -> list[tuple[str, str]]:
    fields = git(folder, "diff", "--cached", "--name-status", "--no-renames", "-z")
    parts = fields.split("\0")[:-1]
    return list(zip(parts[::2], parts[1::2], strict=True))


def try_one(
    answers: Path,
    template: Path,
    head: str,
    base: str | None,
    source: str,
    work: Path,
    sleep: Sleep,
) -> Update:
    """Update one repository to head, and to base as well when it is given."""
    ours = read(answers)
    result = Update(repository_of(ours), answers.relative_to(template))
    folder = work / answers.stem
    try:
        clone(source.format(repository=result.repository), folder, sleep)
        theirs = mapping(point(folder, template), ANSWERS_FILE)
        result.version = str(theirs.get("_commit", ""))
        result.drift = drift(ours, theirs)
        before: dict[str, bytes] = {}
        if base is not None:
            other = work / f"{answers.stem}-base"
            shutil.copytree(folder, other, symlinks=True)
            before = update(other, base)
        after = update(folder, head)
        result.changed = changes(folder)
        result.conflicts = conflicted(after)
        if base is not None:
            result.before = conflicted(before)
            result.touched = sorted(
                name
                for name in before.keys() | after.keys()
                if comparable(name, before.get(name))
                != comparable(name, after.get(name))
            )
    except Failed as error:
        result.error = str(error)
    return result


def short(ref: str) -> str:
    return ref[:7] if re.fullmatch(r"[0-9a-f]{40}", ref) else ref


def code(path: str) -> str:
    return f"`{path}`"


def findings(update: Update) -> list[str]:
    """The warnings and errors of an update, as GitHub shows them."""
    name = update.repository
    lines = []
    if update.drift:
        lines.append(
            f"::warning file={update.answers.as_posix()},title=The answers of {name}::"
            f"{', '.join(update.drift)} differ from the answers of {name}; "
            "python3 downstream.py --answers writes them anew."
        )
    if update.error:
        lines.append(f"::error title=The update of {name}::{name} {update.error}")
    for path in update.conflicts:
        if not update.ours(path):
            continue
        level = "error" if path in update.breaking else "warning"
        lines.append(
            f"::{level} title=A conflict in {name}::The update leaves a conflict in "
            f"{path} of {name}."
        )
    return lines


def details(update: Update) -> list[str]:
    """What the update does in one repository, folded away below its name."""
    lines = [f"<details><summary><b>{update.repository}</b></summary>", ""]
    if update.touched is not None:
        lines += ["The files whose update this commit changes:", ""]
        lines += [f"- {code(path)}" for path in update.touched] or ["- none"]
        lines.append("")
    if update.conflicts:
        lines += ["The files that the update leaves a conflict in:", ""]
        for path in update.conflicts:
            note = "" if update.ours(path) else ", as the base leaves it already"
            lines.append(f"- {code(path)}{note}")
        lines.append("")
    lines += ["The files that the update changes:", ""]
    lines += [f"- {code(path)} ({status})" for status, path in update.changed]
    lines += ["", "</details>", ""]
    return lines


def summary(updates: Sequence[Update], head: str, base: str | None) -> str:
    against = f", and against {short(base)}" if base is not None else ""
    lines = [
        "## The update of each repository that takes the blueprint",
        "",
        "Each repository of `tests/answers/`, cloned and updated as its blueprint bot "
        f"does, from the version that it has to {short(head)}{against}. A conflict "
        "that the update leaves needs a change of the template, or a line in the "
        "changelog that says how a repository resolves it.",
        "",
    ]
    columns = ["Repository", "Has", "Files of the update", "Conflicts"]
    if base is not None:
        columns.insert(3, "Files of this commit")
    lines += [
        f"| {' | '.join(columns)} |",
        "| --- | --- | ---: |" + (" ---: |" if base is not None else "") + " --- |",
    ]
    for update in updates:
        link = f"[{update.repository}](https://github.com/{update.repository})"
        if update.error:
            lines.append(f"| {link} | {update.version or '?'} | {update.error} |")
            continue
        conflicts = ", ".join(
            code(path) if update.ours(path) else f"{code(path)} (base)"
            for path in update.conflicts
        )
        cells = [link, update.version, str(len(update.changed)), conflicts or "none"]
        if update.touched is not None:
            cells.insert(3, str(len(update.touched)))
        lines.append(f"| {' | '.join(cells)} |")
    lines.append("")
    for update in updates:
        if not update.error:
            lines += details(update)
    drifted = [update for update in updates if update.drift]
    if drifted:
        lines += [
            "The answers of `tests/answers/` differ from those of a repository, so the "
            "Variants try other answers than its own. `python3 downstream.py "
            "--answers` writes them anew:",
            "",
        ]
        lines += [
            f"- {code(update.answers.as_posix())}: {', '.join(update.drift)}"
            for update in drifted
        ]
        lines.append("")
    return "\n".join(lines)


def show_conflicts(update: Update, folder: Path) -> None:
    """The conflicts that REF brings, in the log."""
    for path in update.conflicts:
        if update.ours(path):
            print(f"::group::{update.repository}: {path}")
            print(git(folder, "diff", "--cached", "--", path), end="")
            print("::endgroup::")


def try_all(
    root: Path,
    head: str,
    base: str | None,
    source: str,
    work: Path,
    sleep: Sleep,
) -> list[Update]:
    updates = []
    for answers in sorted((root / ANSWERS).glob("*.yml")):
        print(f"{answers.stem}: the update to {short(head)}", flush=True)
        update = try_one(answers, root, head, base, source, work, sleep)
        if not update.error:
            show_conflicts(update, work / answers.stem)
        updates.append(update)
    return updates


def download(
    url: str,
    opener: Callable[..., Any] = urllib.request.urlopen,
    sleep: Sleep = time.sleep,
) -> str:
    attempt = 1
    while True:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": AGENT})
            with opener(request, timeout=60) as response:
                text: str = response.read().decode("utf-8")
                return text
        except OSError as error:
            if attempt == TRIES:
                raise Failed(f"{url} could not be downloaded: {error}") from error
            sleep(attempt * 10)
            attempt += 1


def refresh(root: Path, fetch: Fetch) -> list[str]:
    """Write each file of tests/answers/ anew from the answers of its repository."""
    written = []
    for path in sorted((root / ANSWERS).glob("*.yml")):
        repository = repository_of(read(path))
        url = RAW.format(repository=repository)
        text = text_of(repository, mapping(fetch(url), url))
        if text != path.read_text(encoding="utf-8"):
            path.write_text(text, encoding="utf-8", newline="\n")
            written.append(
                f"{path.relative_to(root).as_posix()}: the answers of {repository}"
            )
    return written


def main(
    argv: Sequence[str] | None = None,
    root: Path = ROOT,
    fetch: Fetch = download,
    sleep: Sleep = time.sleep,
) -> int:
    parser = argparse.ArgumentParser(
        prog="downstream.py", description=__doc__.split("\n\n")[0]
    )
    parser.add_argument(
        "--head", default="HEAD", help="the commit to update to (default: HEAD)"
    )
    parser.add_argument("--base", help="the commit to compare the update with")
    parser.add_argument(
        "--source",
        default=SOURCE,
        help="where to clone each repository from, {repository} for OWNER/NAME",
    )
    parser.add_argument(
        "--work", type=Path, help="the folder of the clones (default: a temporary one)"
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=os.environ.get("GITHUB_STEP_SUMMARY") or None,
        help="the file to add the summary to (default: $GITHUB_STEP_SUMMARY, or print it)",
    )
    parser.add_argument(
        "--answers",
        action="store_true",
        help=f"write {ANSWERS.as_posix()}/ anew from the answers on GitHub",
    )
    arguments = parser.parse_args(argv)
    if arguments.answers:
        try:
            written = refresh(root, fetch)
        except Failed as error:
            print(f"downstream.py: {error}", file=sys.stderr)
            return 2
        print("\n".join(written) or "Every answer is that of its repository.")
        return 0
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
        work = arguments.work or Path(temporary)
        work.mkdir(parents=True, exist_ok=True)
        updates = try_all(
            root, arguments.head, arguments.base, arguments.source, work, sleep
        )
    text = summary(updates, arguments.head, arguments.base)
    if arguments.summary:
        with arguments.summary.open("a", encoding="utf-8") as file:
            file.write(text)
    else:
        print(text)
    failed = False
    for update in updates:
        for line in findings(update):
            print(line)
        failed = failed or bool(update.error or update.breaking)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
