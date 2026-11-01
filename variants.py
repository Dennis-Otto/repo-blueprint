#!/usr/bin/env python3
"""The legs of the Variants workflow that a pull request needs.

Each leg of the workflow makes a project from the template and runs its checks with
their real tools, for minutes. A leg can show nothing new when its project stays the
same to the byte: the commit that the pull request merges into passed it already. So

    python3 variants.py --base REF [--head REF]
        renders the project of each leg from both commits, from a plain copy of each,
        without a release and without --trust, in about a second each, and names the
        legs whose project differs and why, and the others and why not. Every leg
        runs when REF changes what every leg runs with, the files of EVERY_LEG, and
        when a project fails to render, since nothing then shows which ones it
        concerns; an adopted leg runs when its answers change.
    python3 variants.py
        names every leg, for a run on a schedule, by hand or of the Next runner
        workflow, since the tools and the runners move on their own.

$GITHUB_OUTPUT gets the matrix of the job variant as `matrix`, and `run`, whether any
leg runs: GitHub stops at a matrix without a leg. The Variants workflow runs it in its
job *variants plan*, in every pull request.
https://github.com/Dennis-Otto/repo-blueprint
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

from downstream import (
    ANSWERS,
    ANSWERS_FILE,
    Failed,
    commits,
    environment,
    git,
    read,
    run,
    short,
)

ROOT = Path(__file__).resolve().parent
OWNER = "Dennis-Otto"
# What a leg runs with beside the project that it renders, each with what it is for
# every leg: no render shows a change of them. copier.yml renders, but it also says
# what an update of a repository keeps, which only the leg of an update tries.
EVERY_LEG = {
    ".github/workflows/variants.yml": "the steps of every leg",
    "requirements-dev.txt": "the Copier of every leg",
    ".python-version": "the Python of the Copier of every leg",
    "copier.yml": "the questions of every leg and what an update keeps",
    "variants.py": "this plan, which doesn't decide on a change of itself",
    "downstream.py": "part of this plan, which doesn't decide on a change of itself",
}
EVERY_RUN = (
    "a run without a pull request tries every leg, since the tools and the runners "
    "move on their own"
)
SAME = "their project stays the same to the byte"
# Copier's own line, which names the folder of the copy of each commit here.
SOURCE_LINE = b"_src_path: "
# The file of a project: whether it is executable, and a hash of its content.
Files = dict[str, tuple[bool, str]]
# The answers on the command line of Copier, relative to a copy of the blueprint.
Answers = tuple[str, ...]


@dataclass(frozen=True)
class Leg:
    """A leg of the job variant, by the fields of its matrix."""

    kind: str
    # new, update, or adopted with the name of a file of tests/answers/.
    start: str
    answers: str = ""
    owner: str = ""
    ai: str = ""

    @property
    def name(self) -> str:
        """The name of its check, as the job makes it."""
        start = "variant" if self.start == "new" else self.start
        return f"{start} ({self.answers or self.kind})"

    @property
    def matrix(self) -> dict[str, str]:
        return {key: value for key, value in asdict(self).items() if value}

    @property
    def answers_path(self) -> str:
        return f"{ANSWERS.as_posix()}/{self.answers}.yml" if self.answers else ""


@dataclass(frozen=True)
class Decision:
    """Whether a leg runs, and why."""

    leg: Leg
    why: str
    runs: bool = True


def kinds_of(tree: Path) -> list[str]:
    """The kinds of project of the copier.yml in tree, in its order."""
    question = read(tree / "copier.yml").get("project_type")
    choices = question.get("choices") if isinstance(question, dict) else None
    if not choices or not isinstance(choices, dict):
        raise Failed("copier.yml offers no kind of project under project_type")
    return [str(kind) for kind in choices.values()]


def legs_of(tree: Path) -> list[Leg]:
    """Every leg of the job variant: a new repository and an update of each kind, and
    an update with the answers of each repository of tests/answers/."""
    legs = []
    for kind in kinds_of(tree):
        if kind == "generic":
            # The new generic repository of an owner other than the blueprint's,
            # without a release app yet: it gets nothing of the blueprint owner's app
            # or person, but a Renovate workflow of its own; and without the AI of
            # the issue assistant, whose check then asks no file to name an engine.
            legs.append(Leg(kind, "new", owner="octo-org", ai="false"))
        else:
            legs.append(Leg(kind, "new"))
        legs.append(Leg(kind, "update"))
    for path in sorted((tree / ANSWERS).glob("*.yml")):
        adopted = read(path).get("project_type")
        if not adopted:
            raise Failed(f"{ANSWERS.as_posix()}/{path.name} names no project_type")
        legs.append(Leg(str(adopted), "adopted", answers=path.stem))
    return legs


def answers_of(leg: Leg) -> Answers:
    """What Copier gets for the project of a leg, as the job renders it. The update of
    a kind takes the default of issue_assistant_ai, true, as its new repository names
    it: a change of the default is a change of copier.yml, for which every leg runs."""
    if leg.answers:
        return ("--data-file", leg.answers_path)
    description = f'A {leg.kind} of the blueprint\'s tests, with "quotes" and Ümlauts.'
    return (
        "--data",
        "project_name=Demo Project",
        "--data",
        f"description={description}",
        "--data",
        f"project_type={leg.kind}",
        "--data",
        f"owner={leg.owner or OWNER}",
        "--data",
        f"issue_assistant_ai={leg.ai or 'true'}",
    )


def extract(root: Path, ref: str, folder: Path) -> None:
    """The files of a commit in folder, without its history: Copier renders a plain
    folder as it is, whatever tags a checkout has."""
    done = subprocess.run(
        ["git", "archive", "--format=tar", ref],
        cwd=root,
        env=environment(),
        capture_output=True,
        check=False,
    )
    if done.returncode:
        error = done.stderr.decode(errors="replace").strip()
        raise Failed(f"{ref} could not be read: {error}")
    folder.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(done.stdout)) as archive:
        archive.extractall(folder, filter="data")


def files_of(project: Path) -> Files:
    """Each file of a project, but the place that its answers name for the template."""
    found: Files = {}
    for path in project.rglob("*"):
        if path.is_file():
            data = path.read_bytes()
            name = path.relative_to(project).as_posix()
            if name == ANSWERS_FILE:
                data = b"\n".join(
                    line
                    for line in data.split(b"\n")
                    if not line.startswith(SOURCE_LINE)
                )
            executable = bool(path.stat().st_mode & 0o100)
            found[name] = (executable, hashlib.sha256(data).hexdigest())
    return found


def render(tree: Path, answers: Answers, folder: Path) -> Files:
    """The project with these answers from the copy of the blueprint in tree, in a
    folder of the name that the job gives it. Without --trust: it runs no code."""
    project = folder / "variant"
    try:
        run(
            tree,
            sys.executable,
            "-m",
            "copier",
            "copy",
            "--quiet",
            "--defaults",
            *answers,
            tree.as_posix(),
            project.as_posix(),
        )
    except Failed as error:
        # The last line of Copier's error names neither: the log has to place it.
        names = [
            answer
            for answer in answers
            if answer.endswith(".yml") or answer.startswith("project_type=")
        ]
        raise Failed(f"{names[0]} from the {tree.name} commit: {error}") from error
    return files_of(project)


def projects(
    tree: Path, renders: Sequence[Answers], work: Path
) -> dict[Answers, Files]:
    """Each project from the copy in tree, side by side: each one is a process of its
    own, which mostly reads files. The first one that fails stops the plan."""
    with ThreadPoolExecutor(max_workers=os.cpu_count()) as pool:
        made = pool.map(
            lambda item: render(tree, item[1], work / str(item[0])),
            enumerate(renders),
        )
        return dict(zip(renders, made, strict=True))


def changed_in(project_before: Files, project_after: Files) -> list[str]:
    names = project_before.keys() | project_after.keys()
    return sorted(
        name for name in names if project_before.get(name) != project_after.get(name)
    )


def listing(names: Sequence[str]) -> str:
    """Up to three names, and how many more: a change of many files fills no page."""
    shown = ", ".join(f"`{name}`" for name in names[:3])
    more = len(names) - 3
    return f"{shown} and {more} more" if more > 0 else shown


def everything(legs: Iterable[Leg], why: str) -> list[Decision]:
    return [Decision(leg, why) for leg in legs]


def decide(root: Path, head: str, base: str | None, work: Path) -> list[Decision]:
    """Whether each leg of head runs, compared with base."""
    tree = work / "head"
    extract(root, head, tree)
    legs = legs_of(tree)
    if base is None:
        return everything(legs, EVERY_RUN)
    names = git(root, "diff", "--name-only", "--no-renames", "-z", base, head)
    changed = set(names.split("\0")[:-1])
    for name, what in EVERY_LEG.items():
        if name in changed:
            return everything(legs, f"`{name}` changes, {what}")
    # An adopted leg whose answers change runs whatever they render.
    rendered = [leg for leg in legs if leg.answers_path not in changed]
    renders = list(dict.fromkeys(answers_of(leg) for leg in rendered))
    try:
        extract(root, base, work / "base")
        after = projects(tree, renders, work / "projects-head")
        before = projects(work / "base", renders, work / "projects-base")
    except Failed as error:
        why = (
            "a project failed to render, so nothing shows which legs a change "
            f"concerns: {error}"
        )
        print(f"::warning title=Variants plan::Every leg runs: {why}")
        return everything(legs, why)
    decisions = []
    for leg in legs:
        if leg.answers_path in changed:
            decisions.append(Decision(leg, f"`{leg.answers_path}` changes"))
            continue
        files = changed_in(before[answers_of(leg)], after[answers_of(leg)])
        if files:
            why = f"their project changes in {listing(files)}"
            decisions.append(Decision(leg, why))
        else:
            decisions.append(Decision(leg, SAME, runs=False))
    return decisions


def outputs(decisions: Iterable[Decision]) -> str:
    """The outputs of the step: a matrix for the job variant, and whether it has a leg."""
    include = [decision.leg.matrix for decision in decisions if decision.runs]
    matrix = json.dumps({"include": include}, separators=(",", ":"))
    return f"matrix={matrix}\nrun={'true' if include else 'false'}\n"


def grouped(decisions: Iterable[Decision]) -> list[str]:
    """A line for each reason, with the legs that it holds for."""
    legs: dict[str, list[str]] = {}
    for decision in decisions:
        legs.setdefault(decision.why, []).append(f"`{decision.leg.name}`")
    return [f"- {', '.join(names)}: {why}." for why, names in legs.items()]


def summary(decisions: Sequence[Decision], base: str | None) -> str:
    """Which legs run and which don't, and why, for the summary of the job."""
    running = [decision for decision in decisions if decision.runs]
    skipped = [decision for decision in decisions if not decision.runs]
    compared = f" against `{short(base)}`" if base else ""
    lines = [
        "## The legs of the Variants",
        "",
        f"{len(running)} of {len(decisions)} legs run{compared}.",
    ]
    if running:
        lines += ["", "They run:", "", *grouped(running)]
    if skipped:
        lines += ["", "They don't run:", "", *grouped(skipped)]
    return "\n".join(lines) + "\n"


def add_to(path: Path | None, text: str) -> None:
    """Add to the file of a step, or print on a machine without one."""
    if path:
        with path.open("a", encoding="utf-8") as file:
            file.write(text)
    else:
        print(text, end="")


def main(argv: Sequence[str] | None = None, root: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(
        prog="variants.py", description=__doc__.split("\n\n")[0]
    )
    parser.add_argument(
        "--head", default="HEAD", help="the commit of the legs (default: HEAD)"
    )
    parser.add_argument(
        "--base", help="the commit to compare with (default: none, every leg runs)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=os.environ.get("GITHUB_OUTPUT") or None,
        help="the file of the outputs of the step (default: $GITHUB_OUTPUT, or print them)",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=os.environ.get("GITHUB_STEP_SUMMARY") or None,
        help="the file to add the summary to (default: $GITHUB_STEP_SUMMARY, or print it)",
    )
    arguments = parser.parse_args(argv)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
        try:
            head, base = commits(root, arguments.head, arguments.base)
            # The long path: Copier compares the folder with the path that Git names,
            # which a short name of Windows, as TEMP has it, doesn't match.
            decisions = decide(root, head, base, Path(temporary).resolve())
        except Failed as error:
            print(f"variants.py: {error}", file=sys.stderr)
            return 2
    add_to(arguments.summary, summary(decisions, base))
    add_to(arguments.output, outputs(decisions))
    return 0


if __name__ == "__main__":
    sys.exit(main())
