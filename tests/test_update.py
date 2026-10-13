"""Tests of the pull request of the blueprint bot against a simulated GitHub.

The checkout is a real Git repository, and the simulated GitHub keeps its objects in
it, as GitHub has those of main after a fetch: trees, modes and commits are Git's own.
"""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import urllib.parse
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

import blueprint.update
from blueprint import cli
from blueprint.github import Api, GitHubError
from blueprint.update import (
    ANSWERS,
    BRANCH,
    LABEL,
    NOTICE,
    Change,
    Outdated,
    answered_release,
    lost_modes,
    mode_command,
    update_pull_request,
)

REPO = "Dennis-Otto/demo"
APP = "release-app[bot]"
MAINTAINER = "Dennis-Otto"
CONFLICT = (
    "<<<<<<< before updating\n# Demo\n=======\n# Demo 2\n>>>>>>> after updating\n"
)


@pytest.fixture(autouse=True)
def plain_git(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Git without the configuration of the machine, which may sign every commit."""
    config = tmp_path_factory.mktemp("home") / "gitconfig"
    config.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "Test")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "test@example.com")


def git(
    root: Path, *arguments: str, data: bytes | None = None, index: Path | None = None
) -> str:
    environment = None
    if index is not None:
        environment = {**os.environ, "GIT_INDEX_FILE": str(index)}
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        input=data,
        capture_output=True,
        check=True,
        env=environment,
    )
    return result.stdout.decode().strip()


def answers(release: str) -> str:
    return (
        "# The answers of the blueprint\n"
        f"_commit: {release}\n"
        "_src_path: https://github.com/Dennis-Otto/repo-blueprint.git\n"
    )


def write(root: Path, files: Mapping[str, str | bytes | None]) -> None:
    for name, content in files.items():
        path = root / name
        if content is None:
            path.unlink()
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8", newline="\n")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """The checkout of main, at the blueprint's v1.0.0."""
    root = tmp_path / "checkout"
    root.mkdir()
    git(root, "init", "--quiet", "--initial-branch=main")
    # The same modes and line endings on every system: the tests set the modes.
    git(root, "config", "core.autocrlf", "false")
    git(root, "config", "core.fileMode", "false")
    write(
        root,
        {
            ANSWERS: answers("v1.0.0"),
            "README.md": "# Demo\n",
            "scripts/check.sh": "#!/bin/sh\n",
            # Lines like a conflict that the project has on purpose.
            "docs/merging.md": "<<<<<<< ours\n",
            "old.txt": "old\n",
        },
    )
    git(root, "add", "--all")
    git(root, "update-index", "--chmod=+x", "scripts/check.sh")
    git(root, "commit", "--quiet", "-m", "The start")
    return root


def stage(
    root: Path,
    release: str,
    files: dict[str, str | bytes | None] | None = None,
    *,
    executable: Sequence[str] = (),
    regular: Sequence[str] = (),
) -> None:
    """What `copier update` and `git add --all` of the workflow leave."""
    write(root, {ANSWERS: answers(release), **(files or {})})
    git(root, "add", "--all")
    for path in executable:
        git(root, "update-index", "--chmod=+x", path)
    for path in regular:
        git(root, "update-index", "--chmod=-x", path)


def tree(root: Path, commit: str) -> dict[str, str]:
    """The files of a commit with their modes."""
    lines = git(root, "ls-tree", "-r", commit).splitlines()
    return {line.split("\t")[1]: line.split(" ")[0] for line in lines}


class FakeGitHub:
    """The parts of GitHub that the blueprint bot uses, on the objects of the checkout."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.index = root.parent / "github-index"
        self.refs = {"main": git(root, "rev-parse", "HEAD")}
        # The login of the author of each commit; a commit not in it has an author
        # without an account.
        self.authors: dict[str, str] = {}
        self.pulls: dict[int, dict[str, Any]] = {}
        self.comments: dict[int, list[dict[str, Any]]] = {}
        self.next_id = 1
        self.signed = True
        self.tree_differs = False
        self.graphql_fails = False
        self.merge_fails = False
        self.fail: dict[tuple[str, str], int] = {}
        # Runs when the Git Data API made a commit, as a push of someone else would.
        self.on_commit: Callable[[], None] | None = None
        self.calls: list[tuple[str, str]] = []

    # ------------------------------------------------------------------ plumbing

    def __call__(
        self, arguments: Sequence[str], body: str | None
    ) -> subprocess.CompletedProcess[str]:
        if arguments[0] == "pr":
            self.calls.append(("gh", " ".join(arguments)))
            if self.merge_fails:
                return subprocess.CompletedProcess(arguments, 1, "", "no auto-merge")
            pull = self.pulls[int(arguments[2])]
            enable = "--auto" in arguments
            pull["auto_merge"] = {"merge_method": "squash"} if enable else None
            return subprocess.CompletedProcess(arguments, 0, "", "")
        method, path = arguments[3], arguments[4]
        self.calls.append((method, path))
        payload = json.loads(body) if body else None
        local = path.removeprefix(f"repos/{REPO}/")
        status: int = self.fail.get((method, local), 0)
        data: Any = {"message": "Not Found"}
        if not status:
            status, data = self.route(method, local, payload)
        text = "" if data is None else json.dumps(data)
        return subprocess.CompletedProcess(
            arguments,
            0 if status < 400 else 1,
            f"HTTP/2.0 {status} X\r\nA: b\r\n\r\n{text}",
            "",
        )

    def route(self, method: str, path: str, body: Any) -> tuple[int, Any]:
        for pattern, handler in (
            (r"pulls\?state=open&head=([^&]+)", self.list_pulls),
            (r"pulls(?:/(\d+))?", self.pull),
            (r"pulls/(\d+)/commits\?per_page=(\d+)&page=(\d+)", self.pull_commits),
            (r"git/commits(?:/(\w+))?", self.commit),
            (r"git/blobs", self.blob),
            (r"git/trees", self.tree),
            (r"git/ref/heads/(.+)", self.get_ref),
            (r"git/refs(?:/heads/(.+))?", self.ref),
            (r"contents/([^?]+)\?ref=(\w+)", self.contents),
            (r"issues/(\d+)/comments\?per_page=(\d+)&page=(\d+)", self.list_comments),
            (r"issues/(\d+)/comments", self.add_comment),
            (r"issues/comments/(\d+)", self.edit_comment),
            (r"issues/(\d+)/labels(?:/(.+))?", self.label),
            (r"graphql", self.graphql),
        ):
            match = re.fullmatch(pattern, path)
            if match:
                result: tuple[int, Any] = handler(method, body, *match.groups())
                return result
        raise AssertionError(f"unexpected request {method} {path}")

    def git(self, *arguments: str, data: bytes | None = None) -> str:
        return git(self.root, *arguments, data=data, index=self.index)

    def page(self, items: list[Any], size: str, number: str) -> tuple[int, Any]:
        start = (int(number) - 1) * int(size)
        return 200, items[start : start + int(size)]

    def make_commit(self, tree: str, parents: Sequence[str], message: str) -> str:
        options = [option for parent in parents for option in ("-p", parent)]
        sha = self.git("commit-tree", tree, *options, "-m", message)
        self.authors[sha] = APP
        return sha

    def write_tree(self, base: str, changes: Callable[[], None]) -> str:
        self.git("read-tree", base)
        changes()
        return self.git("write-tree")

    def set_ref(self, name: str, sha: str | None) -> None:
        if sha is None:
            del self.refs[name]
        else:
            self.refs[name] = sha
        # GitHub closes a pull request whose branch is gone or has nothing over main.
        for pull in self.pulls.values():
            if pull["head"] == name and (
                sha is None
                or subprocess.run(
                    ["git", "merge-base", "--is-ancestor", sha, self.refs["main"]],
                    cwd=self.root,
                    check=False,
                ).returncode
                == 0
            ):
                pull["state"] = "closed"

    # ------------------------------------------------------------------ pull requests

    def pull_json(self, number: int) -> dict[str, Any]:
        pull = self.pulls[number]
        return {
            "number": number,
            "title": pull["title"],
            "state": pull["state"],
            "head": {"ref": pull["head"], "sha": self.refs.get(pull["head"])},
            "labels": [{"name": name} for name in pull["labels"]],
            "auto_merge": pull["auto_merge"],
        }

    def list_pulls(self, method: str, body: Any, head: str) -> tuple[int, Any]:
        owner, branch = head.split(":", 1)
        assert owner == REPO.split("/")[0]
        return 200, [
            self.pull_json(number)
            for number, pull in self.pulls.items()
            if pull["head"] == branch and pull["state"] == "open"
        ]

    def pull(self, method: str, body: Any, number: str | None) -> tuple[int, Any]:
        if method == "POST":
            assert body["base"] == "main"
            created = self.next_id
            self.next_id += 1
            self.pulls[created] = {
                "title": body["title"],
                "body": body["body"],
                "head": body["head"],
                "state": "open",
                "labels": [],
                "auto_merge": None,
            }
            return 201, self.pull_json(created)
        if method == "GET":
            return 200, self.pull_json(int(number or 0))
        assert method == "PATCH"
        self.pulls[int(number or 0)].update(body)
        return 200, self.pull_json(int(number or 0))

    def pull_commits(
        self, method: str, body: Any, number: str, size: str, page: str
    ) -> tuple[int, Any]:
        head = self.refs[self.pulls[int(number)]["head"]]
        lines = self.git(
            "rev-list", "--reverse", "--parents", f"{self.refs['main']}..{head}"
        ).splitlines()
        commits = [
            {
                "sha": sha,
                "author": {"login": self.authors[sha]} if sha in self.authors else None,
                "parents": [{"sha": parent} for parent in parents],
            }
            for sha, *parents in (line.split() for line in lines)
        ]
        return self.page(commits, size, page)

    # ------------------------------------------------------------------ git data

    def commit(self, method: str, body: Any, sha: str | None) -> tuple[int, Any]:
        if method == "GET":
            return 200, {
                "sha": sha,
                "tree": {"sha": self.git("rev-parse", f"{sha}^{{tree}}")},
            }
        created = self.make_commit(body["tree"], body["parents"], body["message"])
        if self.on_commit is not None:
            self.on_commit()
        verified = {
            "verified": self.signed,
            "reason": "valid" if self.signed else "unsigned",
        }
        return 201, {
            "sha": created,
            "tree": {"sha": body["tree"]},
            "verification": verified,
        }

    def blob(self, method: str, body: Any) -> tuple[int, Any]:
        assert body["encoding"] == "base64"
        content = base64.b64decode(body["content"])
        return 201, {"sha": self.git("hash-object", "-w", "--stdin", data=content)}

    def tree(self, method: str, body: Any) -> tuple[int, Any]:
        def apply() -> None:
            for entry in body["tree"]:
                assert entry["type"] == "blob"
                if "content" not in entry and entry["sha"] is None:
                    self.git("update-index", "--force-remove", "--", entry["path"])
                    continue
                sha = entry.get("sha") or self.git(
                    "hash-object", "-w", "--stdin", data=entry["content"].encode()
                )
                info = f"{entry['mode']},{sha},{entry['path']}"
                self.git("update-index", "--add", "--cacheinfo", info)

        made = self.write_tree(body["base_tree"], apply)
        return 201, {"sha": "0" * 40 if self.tree_differs else made}

    def get_ref(self, method: str, body: Any, name: str) -> tuple[int, Any]:
        if name not in self.refs:
            return 404, {"message": "Not Found"}
        return 200, {"ref": f"refs/heads/{name}", "object": {"sha": self.refs[name]}}

    def ref(self, method: str, body: Any, name: str | None) -> tuple[int, Any]:
        if method == "POST":
            name = body["ref"].removeprefix("refs/heads/")
            if name in self.refs:
                return 422, {"message": "Reference already exists"}
            self.set_ref(name, body["sha"])
            return 201, {"ref": body["ref"]}
        assert name is not None
        if method == "DELETE":
            self.set_ref(name, None)
            return 204, None
        assert body["force"] is True
        self.set_ref(name, body["sha"])
        return 200, {"ref": f"refs/heads/{name}"}

    def contents(self, method: str, body: Any, path: str, ref: str) -> tuple[int, Any]:
        text = self.git("show", f"{self.refs.get(ref, ref)}:{path}") + "\n"
        # GitHub breaks its Base64 into lines.
        encoded = base64.encodebytes(text.encode()).decode()
        return 200, {"content": encoded, "encoding": "base64"}

    def graphql(self, method: str, body: Any) -> tuple[int, Any]:
        assert "createCommitOnBranch" in body["query"]
        if self.graphql_fails:
            return 200, {"data": None, "errors": [{"message": "Something went wrong"}]}
        change = body["variables"]["input"]
        name = change["branch"]["branchName"]
        head = self.refs[name]
        assert change["expectedHeadOid"] == head
        modes = tree(self.root, head)

        def apply() -> None:
            # A changed file keeps its mode, and a new one gets 100644.
            for addition in change["fileChanges"]["additions"]:
                content = base64.b64decode(addition["contents"])
                sha = self.git("hash-object", "-w", "--stdin", data=content)
                mode = modes.get(addition["path"], "100644")
                info = f"{mode},{sha},{addition['path']}"
                self.git("update-index", "--add", "--cacheinfo", info)
            for deletion in change["fileChanges"]["deletions"]:
                self.git("update-index", "--force-remove", "--", deletion["path"])

        message = change["message"]
        created = self.make_commit(
            self.write_tree(head, apply),
            [head],
            f"{message['headline']}\n\n{message['body']}",
        )
        self.set_ref(name, created)
        return 200, {"data": {"createCommitOnBranch": {"commit": {"oid": created}}}}

    # ------------------------------------------------------------------ issues

    def list_comments(
        self, method: str, body: Any, number: str, size: str, page: str
    ) -> tuple[int, Any]:
        return self.page(self.comments.get(int(number), []), size, page)

    def add_comment(self, method: str, body: Any, number: str) -> tuple[int, Any]:
        comment = {"id": self.next_id, "body": body["body"]}
        self.next_id += 1
        self.comments.setdefault(int(number), []).append(comment)
        return 201, comment

    def edit_comment(self, method: str, body: Any, number: str) -> tuple[int, Any]:
        for comments in self.comments.values():
            for comment in comments:
                if comment["id"] == int(number):
                    comment["body"] = body["body"]
                    return 200, comment
        return 404, {"message": "Not Found"}

    def label(
        self, method: str, body: Any, number: str, name: str | None
    ) -> tuple[int, Any]:
        labels = self.pulls[int(number)]["labels"]
        if method == "POST":
            labels.extend(body["labels"])
        else:
            labels.remove(urllib.parse.unquote(name or ""))
        return 200, [{"name": label} for label in labels]


@pytest.fixture
def github(root: Path) -> FakeGitHub:
    return FakeGitHub(root)


def run(github: FakeGitHub, *, automerge: bool = True) -> str:
    return update_pull_request(
        Api(github), REPO, github.root, app=APP, automerge=automerge, run_id="42"
    )


def fresh_checkout(github: FakeGitHub, files: dict[str, str] | None = None) -> None:
    """A new run checks out main, which may have moved on."""
    git(github.root, "reset", "--quiet", "--hard", github.refs["main"])
    if files:
        write(github.root, files)
        git(github.root, "add", "--all")
        git(github.root, "commit", "--quiet", "-m", "A change of the project")
        github.refs["main"] = git(github.root, "rev-parse", "HEAD")


def push(github: FakeGitHub, author: str | None, *, release: str = "") -> str:
    """A commit on the branch of the update, by the author's account or none."""
    head = github.refs[BRANCH]
    content = github.git("show", f"{head}:{ANSWERS}")
    if release:
        content = answers(release).rstrip("\n")
    sha = github.git("hash-object", "-w", "--stdin", data=(content + "\n").encode())

    def apply() -> None:
        github.git("update-index", "--add", "--cacheinfo", f"100644,{sha},{ANSWERS}")

    commit = github.git(
        "commit-tree", github.write_tree(head, apply), "-p", head, "-m", "By hand"
    )
    if author is not None:
        github.authors[commit] = author
    github.refs[BRANCH] = commit
    return commit


def merge_main(
    github: FakeGitHub, author: str, files: Mapping[str, str] | None = None
) -> str:
    """A merge of main into the branch of the update by the author's account, as the
    button *Update branch* makes one, with the files changed in the merge."""
    head = github.refs[BRANCH]
    main = github.refs["main"]
    # The tree that Git merges, with markers where the two conflict.
    merged = subprocess.run(
        ["git", "merge-tree", "--write-tree", head, main],
        cwd=github.root,
        capture_output=True,
        check=False,
    ).stdout.split()[0]

    def apply() -> None:
        for name, content in (files or {}).items():
            sha = github.git("hash-object", "-w", "--stdin", data=content.encode())
            github.git("update-index", "--add", "--cacheinfo", f"100644,{sha},{name}")

    tree = github.write_tree(merged.decode(), apply)
    commit = github.git(
        "commit-tree", tree, "-p", head, "-p", main, "-m", "Merge branch 'main'"
    )
    github.authors[commit] = author
    github.refs[BRANCH] = commit
    return commit


def requests(github: FakeGitHub, method: str, path: str) -> int:
    return github.calls.count((method, f"repos/{REPO}/{path}"))


def gh_calls(github: FakeGitHub) -> list[str]:
    return [call for kind, call in github.calls if kind == "gh"]


# --------------------------------------------------------------------------- one pull request


def test_an_update_opens_its_pull_request_as_the_release_app(
    github: FakeGitHub,
) -> None:
    stage(github.root, "v1.1.0", {"README.md": "# Demo, updated\n"})

    assert run(github) == "Opened #1: the blueprint's v1.0.0 to v1.1.0."

    pull = github.pulls[1]
    assert pull["title"] == "chore: update to the blueprint v1.1.0"
    assert pull["body"].startswith(
        "Brings the repository from the blueprint's v1.0.0 to [v1.1.0]"
        "(https://github.com/Dennis-Otto/repo-blueprint/releases/tag/v1.1.0)"
        " with `copier update`.\n"
    )
    assert "conflicts" not in pull["body"]
    assert pull["auto_merge"] == {"merge_method": "squash"}
    # The commit is the release app's, on main, with the tree of the checkout.
    head = github.refs[BRANCH]
    assert github.authors[head] == APP
    assert git(github.root, "rev-parse", f"{head}^") == github.refs["main"]
    assert git(github.root, "rev-parse", f"{head}^{{tree}}") == git(
        github.root, "write-tree"
    )
    assert git(github.root, "log", "-1", "--format=%B", head).startswith(
        "chore: update to the blueprint v1.1.0\n\nThe changes of the blueprint from"
        " v1.0.0 to v1.1.0: https://github.com/Dennis-Otto/repo-blueprint/releases/tag/v1.1.0"
    )
    assert set(github.refs) == {"main", BRANCH}
    assert ("POST", "graphql") not in github.calls


def test_a_newer_release_moves_the_open_pull_request_on(github: FakeGitHub) -> None:
    stage(github.root, "v1.1.0", {"README.md": "# Demo, updated\n"})
    run(github)
    first = github.refs[BRANCH]
    fresh_checkout(github, {"src.py": "print('new on main')\n"})
    stage(github.root, "v1.2.0", {"README.md": "# Demo, updated again\n"})

    assert run(github) == "Moved on #1: the blueprint's v1.0.0 to v1.2.0."

    # The same pull request, open, with the new commit on the new main.
    assert list(github.pulls) == [1]
    pull = github.pulls[1]
    assert pull["state"] == "open"
    assert pull["title"] == "chore: update to the blueprint v1.2.0"
    head = github.refs[BRANCH]
    assert head != first
    assert git(github.root, "rev-parse", f"{head}^") == github.refs["main"]
    # Auto-merge stays on, without being switched on again.
    assert pull["auto_merge"] == {"merge_method": "squash"}
    assert [call for call in github.calls if call[0] == "gh"] == [
        ("gh", f"pr merge 1 --repo {REPO} --auto --squash")
    ]
    assert requests(github, "POST", "pulls") == 1


def test_the_same_update_again_leaves_the_branch_as_it_is(github: FakeGitHub) -> None:
    stage(github.root, "v1.1.0", {"README.md": "# Demo, updated\n"})
    run(github)
    head = github.refs[BRANCH]
    fresh_checkout(github)
    stage(github.root, "v1.1.0", {"README.md": "# Demo, updated\n"})
    github.calls.clear()

    assert run(github) == "Kept #1: the blueprint's v1.0.0 to v1.1.0."

    assert github.refs[BRANCH] == head
    assert requests(github, "POST", "git/trees") == 0
    assert requests(github, "PATCH", f"git/refs/heads/{BRANCH}") == 0


def test_a_branch_left_without_a_pull_request_is_used_again(
    github: FakeGitHub,
) -> None:
    github.refs[BRANCH] = github.refs["main"]
    stage(github.root, "v1.1.0", {"README.md": "# Demo, updated\n"})

    assert run(github) == "Opened #1: the blueprint's v1.0.0 to v1.1.0."

    assert requests(github, "PATCH", f"git/refs/heads/{BRANCH}") == 1
    assert github.pulls[1]["state"] == "open"


def test_an_update_of_the_answers_alone_lands(github: FakeGitHub) -> None:
    # Without it, the repository would stay at the release before, and the
    # dashboard would count it as behind.
    stage(github.root, "v1.1.0")

    assert run(github) == "Opened #1: the blueprint's v1.0.0 to v1.1.0."

    head = github.refs[BRANCH]
    assert git(github.root, "diff", "--name-only", "main", head) == ANSWERS
    assert "changes no other file of this repository" in github.pulls[1]["body"]
    assert github.pulls[1]["auto_merge"] is not None


def test_an_update_that_changes_nothing(github: FakeGitHub) -> None:
    assert run(github) == "The blueprint's v1.0.0 changes nothing in this repository."
    assert github.calls == []


# --------------------------------------------------------------------------- the maintainer's commits


def test_commits_of_the_maintainer_are_never_overwritten(
    github: FakeGitHub, monkeypatch: pytest.MonkeyPatch
) -> None:
    # One item per page, so that every list of GitHub takes several pages.
    monkeypatch.setattr(blueprint.update, "PAGE", 1)
    stage(github.root, "v1.1.0", {"README.md": "# Demo, updated\n"})
    run(github)
    mine = push(github, MAINTAINER)
    fresh_checkout(github)
    stage(github.root, "v1.2.0", {"README.md": "# Demo, updated again\n"})
    github.calls.clear()

    assert run(github) == (
        "#1 has commits of its own; the bot leaves its branch as it is and says that"
        " v1.2.0 is out."
    )

    assert github.refs[BRANCH] == mine
    assert requests(github, "POST", "git/trees") == 0
    [comment] = github.comments[1]
    assert comment["body"].startswith(
        f"{NOTICE}\nThe blueprint's [v1.2.0]"
        "(https://github.com/Dennis-Otto/repo-blueprint/releases/tag/v1.2.0) is out."
    )
    assert "merge or close it, and the bot brings the rest" in comment["body"]

    # A newer release changes the one comment instead of adding another.
    fresh_checkout(github)
    stage(github.root, "v1.3.0", {"README.md": "# Demo, updated again\n"})
    run(github)
    fresh_checkout(github)
    stage(github.root, "v1.3.0", {"README.md": "# Demo, updated again\n"})
    run(github)

    [comment] = github.comments[1]
    assert "[v1.3.0]" in comment["body"]
    assert requests(github, "PATCH", f"issues/comments/{comment['id']}") == 1
    assert github.refs[BRANCH] == mine
    assert github.pulls[1]["title"] == "chore: update to the blueprint v1.1.0"


def test_a_commit_without_an_account_is_a_maintainers_too(github: FakeGitHub) -> None:
    stage(github.root, "v1.1.0", {"README.md": "# Demo, updated\n"})
    run(github)
    mine = push(github, None)
    fresh_checkout(github)
    stage(github.root, "v1.2.0", {"README.md": "# Demo, updated again\n"})

    run(github)

    assert github.refs[BRANCH] == mine
    assert len(github.comments[1]) == 1


def test_a_maintainer_who_brought_the_release_already_hears_nothing(
    github: FakeGitHub,
) -> None:
    stage(github.root, "v1.1.0", {"README.md": "# Demo, updated\n"})
    run(github)
    push(github, MAINTAINER, release="v1.2.0")
    fresh_checkout(github)
    stage(github.root, "v1.2.0", {"README.md": "# Demo, updated again\n"})

    assert run(github) == (
        "#1 brings v1.2.0 already, with commits of its own; the bot leaves it as it is."
    )
    assert 1 not in github.comments


def test_a_push_while_the_bot_works_is_kept(github: FakeGitHub) -> None:
    stage(github.root, "v1.1.0", {"README.md": "# Demo, updated\n"})
    run(github)
    fresh_checkout(github)
    stage(github.root, "v1.2.0", {"README.md": "# Demo, updated again\n"})
    pushed: list[str] = []
    github.on_commit = lambda: pushed.append(push(github, MAINTAINER))

    assert run(github).startswith("#1 has commits of its own")

    assert github.refs[BRANCH] == pushed[0]
    assert len(github.comments[1]) == 1


def test_a_merge_of_the_branch_bot_while_the_bot_works_is_replaced(
    github: FakeGitHub,
) -> None:
    stage(github.root, "v1.1.0", {"README.md": "# Demo, updated\n"})
    run(github)
    fresh_checkout(github, {"src.py": "print('new on main')\n"})
    stage(github.root, "v1.2.0", {"README.md": "# Demo, updated again\n"})

    merged: list[str] = []

    def merge_main() -> None:
        head = github.refs[BRANCH]
        merged.append(
            github.make_commit(
                github.git("rev-parse", f"{head}^{{tree}}"),
                [head, github.refs["main"]],
                "Merge branch 'main' into blueprint/update",
            )
        )
        github.refs[BRANCH] = merged[0]

    github.on_commit = merge_main

    assert run(github) == "Moved on #1: the blueprint's v1.0.0 to v1.2.0."

    head = github.refs[BRANCH]
    assert head != merged[0]
    assert git(github.root, "rev-parse", f"{head}^") == github.refs["main"]
    assert 1 not in github.comments


def test_a_merge_of_main_by_the_maintainer_holds_nothing_to_keep(
    github: FakeGitHub,
) -> None:
    # With BLUEPRINT_AUTOMERGE set to off, the branch bot leaves the pull request
    # alone, and the maintainer brings it up to date with the button *Update branch*.
    stage(github.root, "v1.1.0", {"README.md": "# Demo, updated\n"})
    run(github, automerge=False)
    fresh_checkout(github, {"src.py": "print('new on main')\n"})
    merged = merge_main(github, MAINTAINER)
    stage(github.root, "v1.2.0", {"README.md": "# Demo, updated again\n"})

    assert run(github, automerge=False) == (
        "Moved on #1: the blueprint's v1.0.0 to v1.2.0."
    )

    assert github.refs[BRANCH] != merged
    assert 1 not in github.comments


@pytest.mark.parametrize(
    ("main", "merge"),
    [
        # A change of its own in the merge.
        ({"src.py": "print('new on main')\n"}, {"src.py": "print('by hand')\n"}),
        # The resolution of a conflict with main.
        ({"README.md": "# Demo of main\n"}, {"README.md": "# Demo of main, updated\n"}),
    ],
)
def test_a_merge_with_changes_of_the_maintainer_is_theirs(
    github: FakeGitHub, main: dict[str, str], merge: dict[str, str]
) -> None:
    stage(github.root, "v1.1.0", {"README.md": "# Demo, updated\n"})
    run(github)
    fresh_checkout(github, main)
    merged = merge_main(github, MAINTAINER, merge)
    stage(github.root, "v1.2.0", {"README.md": "# Demo, updated again\n"})

    assert run(github).startswith("#1 has commits of its own")

    assert github.refs[BRANCH] == merged


def test_a_pull_request_that_merges_while_the_bot_works_stays_merged(
    github: FakeGitHub,
) -> None:
    stage(github.root, "v1.1.0", {"README.md": "# Demo, updated\n"})
    run(github)
    fresh_checkout(github)
    stage(github.root, "v1.2.0", {"README.md": "# Demo, updated again\n"})

    def merge() -> None:
        # Auto-merge squashes the update before, and GitHub deletes its branch.
        head = github.refs[BRANCH]
        github.refs["main"] = github.make_commit(
            github.git("rev-parse", f"{head}^{{tree}}"),
            [github.refs["main"]],
            "chore: update to the blueprint v1.1.0 (#1)",
        )
        github.set_ref(BRANCH, None)

    github.on_commit = merge

    # The commit, made on the main before, would bring v1.1.0 a second time.
    with pytest.raises(Outdated) as stopped:
        run(github)

    assert str(stopped.value) == (
        "main moved from the blueprint's v1.0.0 to v1.1.0 while the bot worked; start"
        " it again to bring v1.2.0."
    )

    assert BRANCH not in github.refs
    assert github.pulls[1]["title"] == "chore: update to the blueprint v1.1.0"
    assert list(github.pulls) == [1]


def test_a_pull_request_closed_while_the_bot_works_stays_closed(
    github: FakeGitHub,
) -> None:
    stage(github.root, "v1.1.0", {"README.md": "# Demo, updated\n"})
    run(github)
    first = github.refs[BRANCH]
    fresh_checkout(github)
    stage(github.root, "v1.2.0", {"README.md": "# Demo, updated again\n"})
    github.on_commit = lambda: github.pulls[1].update(state="closed")

    with pytest.raises(Outdated, match="#1 closed while the bot worked"):
        run(github)

    assert github.refs[BRANCH] == first
    assert github.pulls[1]["title"] == "chore: update to the blueprint v1.1.0"


# --------------------------------------------------------------------------- conflicts


def test_conflicts_turn_auto_merge_off_and_label_the_pull_request(
    github: FakeGitHub,
) -> None:
    stage(github.root, "v1.1.0", {"README.md": "# Demo, updated\n"})
    run(github)
    assert github.pulls[1]["auto_merge"] is not None
    fresh_checkout(github)
    stage(github.root, "v1.2.0", {"README.md": CONFLICT})

    assert run(github) == (
        "Moved on #1: the blueprint's v1.0.0 to v1.2.0, with conflicts in 1 file(s),"
        " auto-merge off."
    )

    pull = github.pulls[1]
    assert pull["auto_merge"] is None
    assert pull["labels"] == [LABEL]
    # Only the files of the update: the project's own lines like markers stay out.
    assert "\n- `README.md`\n" in pull["body"]
    assert "docs/merging.md" not in pull["body"]

    # Still conflicts with the next release: one label, and nothing to switch off.
    fresh_checkout(github)
    stage(github.root, "v1.3.0", {"README.md": CONFLICT})
    run(github)
    assert pull["labels"] == [LABEL]
    assert [call for call in github.calls if call[0] == "gh"] == [
        ("gh", f"pr merge 1 --repo {REPO} --auto --squash"),
        ("gh", f"pr merge 1 --repo {REPO} --disable-auto"),
    ]

    # A release without conflicts takes the label off and merges itself again.
    fresh_checkout(github)
    stage(github.root, "v1.4.0", {"README.md": "# Demo, resolved\n"})
    run(github)
    assert pull["labels"] == []
    assert pull["auto_merge"] is not None


def test_markers_left_in_the_pull_request_never_merge(github: FakeGitHub) -> None:
    stage(github.root, "v1.1.0", {"README.md": CONFLICT})
    run(github)
    # Switched on again by hand, with the markers still in the files.
    github.pulls[1]["auto_merge"] = {"merge_method": "squash"}
    fresh_checkout(github)
    stage(github.root, "v1.1.0", {"README.md": CONFLICT})

    assert run(github).startswith("Kept #1")

    assert github.pulls[1]["auto_merge"] is None
    assert github.pulls[1]["labels"] == [LABEL]
    assert gh_calls(github) == [f"pr merge 1 --repo {REPO} --disable-auto"]


def test_a_new_pull_request_with_conflicts_waits(github: FakeGitHub) -> None:
    stage(github.root, "v1.1.0", {"README.md": CONFLICT, "old.txt": None})

    run(github)

    assert github.pulls[1]["labels"] == [LABEL]
    assert github.pulls[1]["auto_merge"] is None
    assert not [call for call in github.calls if call[0] == "gh"]


def test_automerge_off_leaves_the_merge_to_the_maintainer(github: FakeGitHub) -> None:
    stage(github.root, "v1.1.0", {"README.md": "# Demo, updated\n"})

    run(github, automerge=False)

    assert github.pulls[1]["auto_merge"] is None
    assert not [call for call in github.calls if call[0] == "gh"]


def test_automerge_off_holds_the_open_pull_request_too(github: FakeGitHub) -> None:
    # Opened while BLUEPRINT_AUTOMERGE was on; the maintainer has set it to off since.
    stage(github.root, "v1.1.0", {"README.md": "# Demo, updated\n"})
    run(github)
    fresh_checkout(github)
    stage(github.root, "v1.2.0", {"README.md": "# Demo, updated again\n"})
    github.calls.clear()

    assert run(github, automerge=False) == (
        "Moved on #1: the blueprint's v1.0.0 to v1.2.0."
    )

    assert github.pulls[1]["auto_merge"] is None
    # Before the branch moves, so that the new changes can't merge on their own.
    assert github.calls.index(
        ("gh", f"pr merge 1 --repo {REPO} --disable-auto")
    ) < github.calls.index(("PATCH", f"repos/{REPO}/git/refs/heads/{BRANCH}"))

    # The weekly run with the same release leaves auto-merge to the maintainer, who
    # may switch it on for this update.
    github.pulls[1]["auto_merge"] = {"merge_method": "squash"}
    fresh_checkout(github)
    stage(github.root, "v1.2.0", {"README.md": "# Demo, updated again\n"})

    assert run(github, automerge=False).startswith("Kept #1")

    assert github.pulls[1]["auto_merge"] is not None
    assert gh_calls(github) == [f"pr merge 1 --repo {REPO} --disable-auto"]


def test_auto_merge_that_the_maintainer_turned_off_stays_off(
    github: FakeGitHub,
) -> None:
    stage(github.root, "v1.1.0", {"README.md": "# Demo, updated\n"})
    run(github)
    github.pulls[1]["auto_merge"] = None
    fresh_checkout(github)
    stage(github.root, "v1.2.0", {"README.md": "# Demo, updated again\n"})

    assert run(github) == "Moved on #1: the blueprint's v1.0.0 to v1.2.0."

    assert github.pulls[1]["auto_merge"] is None
    assert gh_calls(github) == [f"pr merge 1 --repo {REPO} --auto --squash"]


def test_conflicts_never_merge_when_the_bot_stops_after_the_move(
    github: FakeGitHub,
) -> None:
    stage(github.root, "v1.1.0", {"README.md": "# Demo, updated\n"})
    run(github)
    fresh_checkout(github)
    stage(github.root, "v1.2.0", {"README.md": CONFLICT})
    github.fail[("PATCH", "pulls/1")] = 500

    with pytest.raises(GitHubError, match="GitHub answered 500"):
        run(github)

    # The markers are on the branch, but auto-merge went before them.
    assert git(github.root, "show", f"{github.refs[BRANCH]}:README.md") == (
        CONFLICT.rstrip("\n")
    )
    assert github.pulls[1]["auto_merge"] is None


# --------------------------------------------------------------------------- modes


def stage_modes(github: FakeGitHub) -> None:
    stage(
        github.root,
        "v1.1.0",
        {
            "README.md": "# Demo, updated\n",
            "scripts/new.sh": "#!/bin/sh\n",
            "scripts/check.sh": "#!/bin/sh\nexit 0\n",
            "img/logo.png": b"\x89PNG\r\n\x1a\n\x00\xff\xfe",
            "old.txt": None,
        },
        executable=["scripts/new.sh"],
        regular=["scripts/check.sh"],
    )
    target = git(github.root, "hash-object", "-w", "--stdin", data=b"README.md")
    git(github.root, "update-index", "--add", "--cacheinfo", f"120000,{target},link")


def test_the_modes_of_the_files_reach_the_repository(github: FakeGitHub) -> None:
    stage_modes(github)

    run(github)

    head = github.refs[BRANCH]
    assert git(github.root, "rev-parse", f"{head}^{{tree}}") == git(
        github.root, "write-tree"
    )
    files = tree(github.root, head)
    assert files["scripts/new.sh"] == "100755"
    assert files["scripts/check.sh"] == "100644"
    assert files["link"] == "120000"
    assert "old.txt" not in files
    # Only what isn't text goes as a blob of its own.
    assert requests(github, "POST", "git/blobs") == 1
    assert "mode" not in github.pulls[1]["body"]


def test_without_a_signed_commit_the_lost_modes_are_listed(
    github: FakeGitHub, capsys: pytest.CaptureFixture[str]
) -> None:
    github.signed = False
    stage_modes(github)

    run(github)

    assert "::warning::GitHub didn't sign the commit" in capsys.readouterr().out
    # The commit of createCommitOnBranch, on a branch of its own that is gone again.
    assert github.calls.count(("POST", "graphql")) == 1
    assert set(github.refs) == {"main", BRANCH}
    assert requests(github, "DELETE", f"git/refs/heads/{BRANCH}-42") == 1
    head = github.refs[BRANCH]
    files = tree(github.root, head)
    assert files["scripts/new.sh"] == "100644"
    assert files["scripts/check.sh"] == "100755"
    assert git(github.root, "rev-parse", f"{head}:img/logo.png") == git(
        github.root, "rev-parse", ":img/logo.png"
    )
    body = github.pulls[1]["body"]
    assert (
        "```sh\n"
        "# link needs the mode 120000\n"
        "git update-index --chmod=-x -- scripts/check.sh\n"
        "git update-index --chmod=+x -- scripts/new.sh\n"
        "```\n"
    ) in body


def test_a_tree_unlike_the_checkout_is_not_committed(
    github: FakeGitHub, capsys: pytest.CaptureFixture[str]
) -> None:
    github.tree_differs = True
    stage_modes(github)

    run(github)

    assert "::warning::GitHub made the tree" in capsys.readouterr().out
    assert requests(github, "POST", "git/commits") == 0
    assert github.calls.count(("POST", "graphql")) == 1


def test_a_failed_commit_takes_its_branch_away(github: FakeGitHub) -> None:
    github.signed = False
    github.graphql_fails = True
    stage(github.root, "v1.1.0", {"README.md": "# Demo, updated\n"})

    with pytest.raises(GitHubError, match="Something went wrong"):
        run(github)

    assert set(github.refs) == {"main"}
    assert github.pulls == {}


def test_the_modes_that_create_commit_on_branch_loses() -> None:
    changes = [
        Change("new.sh", "000000", "100755", "a"),
        Change("new.txt", "000000", "100644", "b"),
        Change("same.sh", "100755", "100755", "c"),
        Change("check.sh", "100755", "100644", "d"),
        Change("gone.sh", "100755", "000000", "0"),
    ]

    assert [change.path for change in lost_modes(changes)] == ["new.sh", "check.sh"]
    assert mode_command(Change("a b", "000000", "100755", "a")) == (
        "git update-index --chmod=+x -- 'a b'"
    )


def test_the_release_of_answers_without_one() -> None:
    assert answered_release("project_name: Demo\n") == ""


# --------------------------------------------------------------------------- errors and the command line


def test_a_refused_request_stops_the_bot(github: FakeGitHub) -> None:
    github.fail[("POST", "pulls")] = 404
    stage(github.root, "v1.1.0", {"README.md": "# Demo, updated\n"})

    with pytest.raises(GitHubError, match="no answer to POST"):
        run(github)


def test_auto_merge_that_github_refuses_stops_the_bot(github: FakeGitHub) -> None:
    github.merge_fails = True
    stage(github.root, "v1.1.0", {"README.md": "# Demo, updated\n"})

    with pytest.raises(GitHubError, match="no auto-merge"):
        run(github)


def test_the_command_line(
    github: FakeGitHub, capsys: pytest.CaptureFixture[str]
) -> None:
    stage(github.root, "v1.1.0", {"README.md": "# Demo, updated\n"})
    arguments = ["--repo", REPO, "update-commit", "--app", APP, "--automerge", "off"]
    # A repository made from a fork of the blueprint links the fork's release.
    arguments += ["--source", "Someone/blueprint"]

    assert cli.main(arguments, api=Api(github), root=github.root) == 0

    assert capsys.readouterr().out == "Opened #1: the blueprint's v1.0.0 to v1.1.0.\n"
    assert github.pulls[1]["auto_merge"] is None
    assert (
        "[v1.1.0](https://github.com/Someone/blueprint/releases/tag/v1.1.0)"
        in github.pulls[1]["body"]
    )


def test_an_update_of_main_meanwhile_needs_a_new_run(
    github: FakeGitHub, capsys: pytest.CaptureFixture[str]
) -> None:
    stage(github.root, "v1.2.0", {"README.md": "# Demo, updated\n"})

    def update_by_hand() -> None:
        main = github.refs["main"]
        sha = github.git(
            "hash-object", "-w", "--stdin", data=answers("v1.1.0").encode()
        )

        def apply() -> None:
            github.git(
                "update-index", "--add", "--cacheinfo", f"100644,{sha},{ANSWERS}"
            )

        github.refs["main"] = github.make_commit(
            github.write_tree(main, apply), [main], "Update by hand"
        )

    github.on_commit = update_by_hand
    arguments = ["--repo", REPO, "update-commit", "--app", APP]

    assert cli.main(arguments, api=Api(github), root=github.root) == 2

    assert capsys.readouterr().err == (
        "blueprint.py: main moved from the blueprint's v1.0.0 to v1.1.0 while the bot"
        " worked; start it again to bring v1.2.0.\n"
    )
    assert BRANCH not in github.refs
    assert github.pulls == {}


def test_the_command_line_names_what_failed(
    tmp_path: Path,
    github: FakeGitHub,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A folder outside of every repository.
    folder = tmp_path / "folder"
    folder.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    arguments = ["--repo", REPO, "update-commit", "--app", APP]

    assert cli.main(arguments, api=Api(github), root=folder) == 2

    error = capsys.readouterr().err
    assert error.startswith("blueprint.py: git diff-index: ")
    assert "not a git repository" in error
