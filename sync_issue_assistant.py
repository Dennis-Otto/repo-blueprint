#!/usr/bin/env python3
"""The templates of the issue assistant in the blueprint, from a verified release.

The four workflows of the issue assistant and its firewall policy are templates of a
release of https://github.com/Dennis-Otto/issue-assistant, with which the check
issue-assistant compares every repository. The blueprint keeps copies of them in
.github/, which every repository made from it renders. Once the Issue assistant sync
workflow has verified the latest release, it takes the release over with this script:

    python3 sync_issue_assistant.py pinned
    python3 sync_issue_assistant.py adopt RELEASE --ref COMMIT --version TAG --out FOLDER
    python3 sync_issue_assistant.py commit FOLDER --repo OWNER/NAME --branch BRANCH \\
        --head SHA --headline TEXT --body TEXT
    python3 sync_issue_assistant.py report FOLDER --version TAG --url URL

pinned prints each release that the workflows of the blueprint pin, as its commit and
its tag. adopt runs install of the release, a checkout of its commit, in the root of
the blueprint, takes over the firewall policy of its templates, moves every pin of the
action to it, gives each workflow of the templates the file that renders it in every
repository, and keeps what changed in FOLDER. commit prints the request to GitHub's
GraphQL API that commits what adopt kept, and report the description of the pull
request.
https://github.com/Dennis-Otto/repo-blueprint
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ACTION = "Dennis-Otto/issue-assistant"
# A pin of the action, as install writes it: the commit of the release, and its tag
# in the comment.
PIN = re.compile(rf"{re.escape(ACTION)}@(?P<ref>[0-9a-f]{{40}}) # (?P<version>\S+)")
SHA = re.compile(r"[0-9a-f]{40}")
# A tag of a release, such as v1.3.1, which the commit names and the pins carry.
VERSION = re.compile(r"v\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?")
WORKFLOWS = Path(".github/workflows")
FIREWALL = Path(".github/egress-firewall.yaml")
# The files of the template that render the workflows of the root in every repository.
INCLUDES = Path("template/.github/workflows")
# The templates of a release, in the checkout of its commit.
TEMPLATES = Path("templates/.github")
# What the sync may write, by paths of plain names: a workflow, the firewall policy and
# the file of the template that renders a workflow. Anything else that install of a
# release writes is new, and a maintainer takes it over by hand.
NAME = r"[A-Za-z0-9][A-Za-z0-9._-]*"
TAKEABLE = re.compile(
    rf"\.github/workflows/{NAME}\.yml"
    r"|\.github/egress-firewall\.yaml"
    rf"|template/\.github/workflows/{NAME}\.yml\.jinja"
)
COMMIT = (
    "mutation($input: CreateCommitOnBranchInput!) "
    "{ createCommitOnBranch(input: $input) { commit { oid } } }"
)


class SyncError(Exception):
    """A release that the sync can't take over by itself, with what to do."""


def include(name: str) -> str:
    """The file of the template that renders the workflow name of the root."""
    return f'[% include ".github/workflows/{name}" -%]\n'


def pinned(root: Path) -> list[str]:
    """Each release of the action that the workflows of root pin, as its commit and
    its tag, once: one line when every pin names the same release."""
    found = {
        f"{match['ref']} {match['version']}"
        for path in (root / WORKFLOWS).glob("*.yml")
        for match in PIN.finditer(path.read_text(encoding="utf-8"))
    }
    return sorted(found)


def changed_files(root: Path) -> list[str]:
    """The files of the work tree of root that differ from its commit, new ones too."""
    status = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "status",
            "--porcelain=v1",
            "-z",
            "--no-renames",
            "--untracked-files=all",
        ],
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8")
    return sorted(entry[3:] for entry in status.split("\0") if entry)


def adopt(root: Path, release: Path, ref: str, version: str) -> list[str]:
    """Takes the release in the folder release over into root, the work tree of the
    blueprint, and returns the paths that changed. install of the release writes the
    workflows of its templates; the firewall policy becomes that of its templates,
    which install keeps once a repository has one; every pin of the action names the
    release, also that of the check in the Lint workflow; and each workflow of the
    templates gets the file of the template that renders it, for a workflow that is
    new in the release. Raises SyncError when the release is no release of the issue
    assistant, when install fails, and when it changed a file that the sync doesn't
    take over."""
    if not SHA.fullmatch(ref):
        raise SyncError(f"{ref} is no commit hash; give the commit of the release.")
    if not VERSION.fullmatch(version):
        raise SyncError(f"{version} is no tag of a release, such as v1.3.1.")
    templates = release / TEMPLATES
    names = sorted(path.name for path in (templates / "workflows").glob("*.yml"))
    if not names or not (templates / FIREWALL.name).is_file():
        raise SyncError(
            f"{version} has no workflows and no firewall policy in {TEMPLATES}/; it "
            "is no release of the issue assistant that the sync knows."
        )
    installed = subprocess.run(
        [
            sys.executable,
            str(release / "issue_assistant.py"),
            "install",
            "--ref",
            ref,
            "--version",
            version,
        ],
        env={**os.environ, "ISSUE_ASSISTANT_ROOT": str(root)},
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    # The log of the run says what install did.
    print(installed.stdout + installed.stderr, end="", file=sys.stderr)
    if installed.returncode != 0:
        raise SyncError(f"install of {version} failed; its log above says why.")
    shutil.copyfile(templates / FIREWALL.name, root / FIREWALL)
    pin = f"{ACTION}@{ref} # {version}"
    for path in sorted((root / WORKFLOWS).glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        moved = PIN.sub(lambda _: pin, text)
        if moved != text:
            path.write_text(moved, encoding="utf-8", newline="\n")
    for name in names:
        rendered = root / INCLUDES / f"{name}.jinja"
        if not rendered.is_file():
            rendered.parent.mkdir(parents=True, exist_ok=True)
            rendered.write_text(include(name), encoding="utf-8", newline="\n")
    changed = changed_files(root)
    others = [
        path
        for path in changed
        if not TAKEABLE.fullmatch(path) or not (root / path).is_file()
    ]
    if others:
        raise SyncError(
            f"install of {version} changed {', '.join(others)}, which the sync doesn't "
            "take over by itself: take the release over by hand, with install of the "
            "release in the root of the blueprint, and add what is new to the template."
        )
    return changed


def keep(root: Path, folder: Path, paths: Sequence[str]) -> None:
    """Copies the files at paths of root into folder, at their paths under files/,
    for the job of the pull request."""
    for path in paths:
        target = folder / "files" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((root / path).read_bytes())


def kept(folder: Path) -> list[str]:
    """The paths that adopt kept in folder, once they are checked: the job of the pull
    request writes nothing but what the sync takes over. Raises SyncError for anything
    else."""
    files = folder / "files"
    found = []
    for directory, folders, names in os.walk(files):
        links = [name for name in folders if Path(directory, name).is_symlink()]
        for name in names + links:
            path = Path(directory, name)
            relative = path.relative_to(files).as_posix()
            if path.is_symlink() or not TAKEABLE.fullmatch(relative):
                raise SyncError(
                    f"The sync kept {relative}, which is no workflow, firewall policy "
                    "or file of the template that renders a workflow."
                )
            found.append(relative)
    if not found:
        raise SyncError("The sync kept nothing to commit.")
    return sorted(found)


def commit_request(
    folder: Path, repository: str, branch: str, head: str, headline: str, body: str
) -> dict[str, Any]:
    """The request to GitHub's GraphQL API that commits what adopt kept in folder onto
    a branch, as whoever sends it, and only while the branch is still at head."""
    additions = [
        {
            "path": path,
            "contents": base64.b64encode(
                (folder / "files" / path).read_bytes()
            ).decode(),
        }
        for path in kept(folder)
    ]
    return {
        "query": COMMIT,
        "variables": {
            "input": {
                "branch": {"repositoryNameWithOwner": repository, "branchName": branch},
                "expectedHeadOid": head,
                "message": {"headline": headline, "body": body},
                "fileChanges": {"additions": additions},
            }
        },
    }


def committed(root: Path, path: str) -> str | None:
    """The file at path as the commit of the work tree root has it, or None when the
    commit has none."""
    shown = subprocess.run(
        ["git", "-C", str(root), "show", f"HEAD:{path}"],
        capture_output=True,
        check=False,
    )
    return shown.stdout.decode("utf-8") if shown.returncode == 0 else None


def what(root: Path, folder: Path, path: str) -> str:
    """What happened to the file at path, for the description: a workflow in which
    only the pins of the action changed, as in the Lint workflow, or a template of
    the release."""
    if path == FIREWALL.as_posix():
        return "the firewall policy of the release"
    if path.startswith(f"{INCLUDES.as_posix()}/"):
        name = path.removeprefix(f"{INCLUDES.as_posix()}/").removesuffix(".jinja")
        return f"new, renders `{WORKFLOWS.as_posix()}/{name}` in every repository"
    new = (folder / "files" / path).read_text(encoding="utf-8")
    old = committed(root, path)
    if old is None:
        return "a new workflow of the release"
    pin = PIN.search(new)
    if pin and PIN.sub(lambda _: pin[0], old) == new:
        return "every pin of the action moves to the release"
    return "the template of the release"


def listing(root: Path, folder: Path) -> str:
    """The files that adopt kept in folder, each with what happened to it."""
    return "".join(f"- `{path}`: {what(root, folder, path)}\n" for path in kept(folder))


def report(root: Path, folder: Path, version: str, url: str) -> str:
    """The description of the pull request of the sync bot."""
    return (
        f"The issue assistant [{version}]({url}) is out, and the sync bot verified it: "
        "the release is immutable, GitHub's attestation of it holds, its tag points at "
        "a commit of its `main`, and its release workflow signed the tag. `install` of "
        "the release in the root of the blueprint changes these files:\n\n"
        + listing(root, folder)
        + "\nThe notes of the release say what changed. The next release of the "
        "blueprint brings these files to every repository made from it, with the "
        "update pull request of its blueprint bot.\n\n"
        "This pull request merges itself once every required check passes. The sync "
        "bot moves it on to a newer release of the issue assistant, and closes it when "
        "`main` has the release without it; once someone else commits to its branch, "
        "the bot leaves the branch alone.\n"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sync_issue_assistant.py",
        description="Take a verified release of the issue assistant over into the "
        "blueprint.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "pinned", help="print each release that the workflows pin, as commit and tag"
    )
    adopt_parser = commands.add_parser(
        "adopt", help="install a release in the root and keep what changed"
    )
    adopt_parser.add_argument(
        "release", type=Path, help="the checkout of the release's commit"
    )
    adopt_parser.add_argument(
        "--ref", required=True, help="the commit hash of the release"
    )
    adopt_parser.add_argument(
        "--version", required=True, help="the tag of the release, such as v1.3.1"
    )
    adopt_parser.add_argument(
        "--out", type=Path, required=True, help="the folder to keep the changes in"
    )
    commit_parser = commands.add_parser(
        "commit", help="print the GraphQL request that commits what adopt kept"
    )
    commit_parser.add_argument("folder", type=Path, help="the folder of adopt")
    commit_parser.add_argument("--repo", required=True, help="OWNER/NAME")
    commit_parser.add_argument(
        "--branch", required=True, help="the branch to commit to"
    )
    commit_parser.add_argument(
        "--head", required=True, help="the commit that the branch is at"
    )
    commit_parser.add_argument(
        "--headline", required=True, help="the first line of the message"
    )
    commit_parser.add_argument("--body", default="", help="the rest of the message")
    report_parser = commands.add_parser(
        "report", help="print the description of the pull request"
    )
    report_parser.add_argument("folder", type=Path, help="the folder of adopt")
    report_parser.add_argument(
        "--version", required=True, help="the tag of the release"
    )
    report_parser.add_argument("--url", required=True, help="the page of the release")
    arguments = parser.parse_args(argv)
    root = Path.cwd()
    try:
        if arguments.command == "pinned":
            for line in pinned(root):
                print(line)
        elif arguments.command == "adopt":
            changed = adopt(root, arguments.release, arguments.ref, arguments.version)
            if changed:
                keep(root, arguments.out, changed)
                print(listing(root, arguments.out), end="")
        elif arguments.command == "commit":
            request = commit_request(
                arguments.folder,
                arguments.repo,
                arguments.branch,
                arguments.head,
                arguments.headline,
                arguments.body,
            )
            print(json.dumps(request))
        else:
            print(
                report(root, arguments.folder, arguments.version, arguments.url), end=""
            )
    except SyncError as error:
        print(f"::error::{error}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
