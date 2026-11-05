"""Tests of blueprint.py workflows register, and of the look of create and the step of
the checklist, against a simulated GitHub that registers a workflow when a merge
changes its file (#652)."""

from __future__ import annotations

import base64
import json
import re
import subprocess
from collections.abc import Iterable, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

import pytest

from blueprint import cli, workflows
from blueprint.checklist import workflows_step
from blueprint.github import Api, GitHubError
from blueprint.update import CREATE_COMMIT
from blueprint.workflows import (
    NOTE,
    PULL_BRANCH,
    REGISTER_TITLE,
    UNMARK_TITLE,
    known_text,
    local_workflows,
    register_workflows,
    signer,
    wait_until_known,
)

REPO = "octo-org/demo"
OWNER = "octo-org"
HEAD = f"{0xA1:040x}"
FOLDER = ".github/workflows"
CI = f"{FOLDER}/ci.yml"
BOT = f"{FOLDER}/blueprint-update.yml"
SBOM = f"{FOLDER}/sbom.yaml"
TEXTS = {
    CI: "on: push\n",
    BOT: "on:\n  schedule:\n    - cron: '56 4 * * 4'\n",
    SBOM: "on: workflow_dispatch\n",
}
ADDRESS = "583231+octocat@users.noreply.github.com"
SIGN_OFF = f"Signed-off-by: Mona Octocat <{ADDRESS}>"


class FakeGitHub:
    """main with its workflows and the ones that GitHub knows, the branch of the pull
    requests, the commits that createCommitOnBranch makes and the open pull requests;
    merge() squashes the open one into main, a push that registers what it changes."""

    def __init__(self, texts: dict[str, str], known: Iterable[str] = ()) -> None:
        self.texts = dict(texts)
        self.head = HEAD
        self.known = set(known)
        self.refs: dict[str, str] = {}
        self.commits: dict[str, dict[str, Any]] = {}
        self.pulls: list[dict[str, Any]] = []
        self.made: list[dict[str, Any]] = []
        self.user: dict[str, Any] = {
            "login": "octocat",
            "name": "Mona Octocat",
            "id": 583231,
        }
        # The address that GitHub gives the commits of the account.
        self.email = ADDRESS
        # What the query of the files answers instead of main, when a test sets it.
        self.repository: Any = None
        # The lists of the known workflows that the next looks answer, before
        # self.known.
        self.looks: list[set[str]] = []
        self.calls: list[str] = []
        self.fail: dict[str, int] = {}

    def __call__(
        self, arguments: Sequence[str], body: str | None
    ) -> subprocess.CompletedProcess[str]:
        if "--slurp" in arguments:
            path = arguments[-1]
            self.calls.append(f"GET {path}")
            assert path == f"repos/{REPO}/actions/workflows?per_page=100"
            known = self.looks.pop(0) if self.looks else self.known
            page = {
                "total_count": len(known),
                "workflows": [{"path": path} for path in sorted(known)],
            }
            return subprocess.CompletedProcess(arguments, 0, json.dumps([page]), "")
        method, path = arguments[3], arguments[4]
        self.calls.append(f"{method} {path}")
        status, data = self.route(method, path, json.loads(body) if body else None)
        text = f"HTTP/2.0 {status} X\r\nA: b\r\n\r\n{json.dumps(data)}"
        return subprocess.CompletedProcess(
            arguments, 0 if status < 400 else 1, text, ""
        )

    def route(self, method: str, path: str, body: Any) -> tuple[int, Any]:
        key = f"{method} {path}"
        if key in self.fail:
            return self.fail[key], {"message": "simulated failure"}
        ref = f"repos/{REPO}/git/ref/heads/{PULL_BRANCH}"
        if key == "POST graphql":
            return 200, self.graphql(body["query"], body["variables"])
        if key == f"GET repos/{REPO}/pulls?state=open&head={OWNER}:{PULL_BRANCH}":
            return 200, self.pulls
        if key == f"GET {ref}":
            if PULL_BRANCH not in self.refs:
                return 404, {"message": "Not Found"}
            return 200, {"object": {"sha": self.refs[PULL_BRANCH]}}
        if key == f"PATCH {ref.replace('/ref/', '/refs/')}":
            assert body["force"] is True
            self.refs[PULL_BRANCH] = body["sha"]
            return 200, {}
        if key == f"POST repos/{REPO}/git/refs":
            assert PULL_BRANCH not in self.refs
            assert body["ref"] == f"refs/heads/{PULL_BRANCH}"
            self.refs[PULL_BRANCH] = body["sha"]
            return 201, {}
        if key == "GET user":
            return 200, self.user
        if key.startswith(f"GET repos/{REPO}/git/commits/"):
            assert path.rsplit("/", 1)[1] in self.commits
            return 200, {"author": {"name": "Mona Octocat", "email": self.email}}
        assert key == f"POST repos/{REPO}/pulls", f"unexpected request {key}"
        pull = {"html_url": f"https://github.com/{REPO}/pull/{len(self.made) + 1}"}
        pull |= body
        self.pulls.append(pull)
        self.made.append(pull)
        return 201, pull

    def graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        if query == workflows.FILES:
            assert variables == {
                "owner": OWNER,
                "name": "demo",
                "branch": "refs/heads/main",
                "folder": FOLDER,
            }
            if self.repository is not None:
                return {"data": {"repository": self.repository}}
            entries = [
                {
                    "name": PurePosixPath(path).name,
                    "type": "blob",
                    "object": {"text": text, "isTruncated": False},
                }
                for path, text in sorted(self.texts.items())
            ]
            folder = {"object": {"entries": entries}} if entries else None
            target = {"oid": self.head, "file": folder}
            return {"data": {"repository": {"ref": {"target": target}}}}
        assert query == CREATE_COMMIT
        change = variables["input"]
        branch = change["branch"]["branchName"]
        assert change["branch"]["repositoryNameWithOwner"] == REPO
        if self.refs.get(branch) != change["expectedHeadOid"]:
            return {"errors": [{"message": "the branch moved"}]}
        oid = f"{0xB0 + len(self.commits):040x}"
        self.commits[oid] = {
            "message": change["message"],
            "files": {
                item["path"]: base64.b64decode(item["contents"]).decode()
                for item in change["fileChanges"]["additions"]
            },
        }
        self.refs[branch] = oid
        return {"data": {"createCommitOnBranch": {"commit": {"oid": oid}}}}

    @property
    def proposed(self) -> dict[str, Any]:
        """The commit at the head of the branch."""
        return self.commits[self.refs[PULL_BRANCH]]

    def merge(self) -> None:
        """The squash merge of the open pull request: a push to main that changes its
        files, which registers them; the branch stays."""
        files = self.proposed["files"]
        self.texts.update(files)
        self.known |= set(files)
        self.head = f"{int(self.head, 16) + 1:040x}"
        self.pulls = []


def api(github: FakeGitHub) -> Api:
    return Api(github)


def test_github_registers_the_workflows_that_it_does_not_know_by_two_pull_requests(
    waits: list[float],
) -> None:
    github = FakeGitHub(TEXTS, known=[CI])

    said = register_workflows(api(github), REPO)

    # One commit on a branch of a bot at main, which adds the comment to the end of
    # each workflow that GitHub doesn't know, and is signed off by its author.
    assert github.proposed["files"] == {
        BOT: TEXTS[BOT] + NOTE,
        SBOM: TEXTS[SBOM] + NOTE,
    }
    message = github.proposed["message"]
    assert message["headline"] == REGISTER_TITLE
    assert message["body"].endswith(f"\n\n{SIGN_OFF}")
    assert len(github.commits) == 1
    [pull] = github.made
    assert pull["head"] == PULL_BRANCH
    assert pull["base"] == "main"
    assert pull["title"] == REGISTER_TITLE
    assert "- `blueprint-update.yml`\n- `sbom.yaml`\n" in pull["body"]
    assert "Refs Dennis-Otto/repo-blueprint#652" in pull["body"]
    assert said == (
        "GitHub hasn't registered blueprint-update.yml, sbom.yaml. The pull request"
        f" that registers them: https://github.com/{REPO}/pull/1\n"
        f"Once it has merged, run {workflows.COMMAND} again: it opens the one that"
        " takes the comments out."
    )

    # While it is open, the command names it, and changes nothing.
    calls = len(github.calls)
    said = register_workflows(api(github), REPO)
    assert said == (
        f"The pull request of {PULL_BRANCH} is open: https://github.com/{REPO}/pull/1"
        f"\nMerge it, then run {workflows.COMMAND} again."
    )
    assert github.calls[calls:] == [
        f"GET repos/{REPO}/pulls?state=open&head={OWNER}:{PULL_BRANCH}"
    ]

    # Its merge registers them; the next one takes the comments out again, on the
    # branch that the first one left.
    github.merge()
    assert github.known == set(TEXTS)
    said = register_workflows(api(github), REPO)
    assert github.proposed["files"] == {BOT: TEXTS[BOT], SBOM: TEXTS[SBOM]}
    assert github.proposed["message"]["headline"] == UNMARK_TITLE
    assert github.made[-1]["title"] == UNMARK_TITLE
    assert "- `blueprint-update.yml`\n- `sbom.yaml`\n" in github.made[-1]["body"]
    assert said == (
        "The comments that registered blueprint-update.yml, sbom.yaml are still in"
        f" them. The pull request that takes them out again: https://github.com/{REPO}"
        "/pull/2"
    )
    assert f"PATCH repos/{REPO}/git/refs/heads/{PULL_BRANCH}" in github.calls

    # After that merge, the files are the blueprint's again, and GitHub knows each.
    github.merge()
    assert github.texts == TEXTS
    assert register_workflows(api(github), REPO) == (
        f"GitHub knows every workflow of {FOLDER}/ on main of {REPO}."
    )
    assert len(github.made) == 2
    assert waits == []


def test_a_commit_that_github_authors_with_another_address_is_made_again() -> None:
    github = FakeGitHub(TEXTS, known=[CI, SBOM])
    github.email = "mona@example.com"

    register_workflows(api(github), REPO)

    # The branch went back to main for the second commit, whose sign-off names the
    # author that the first one got: the pull request holds only that one.
    assert len(github.commits) == 2
    assert github.proposed["message"]["body"].endswith(
        "\n\nSigned-off-by: Mona Octocat <mona@example.com>"
    )
    assert github.calls.count(f"PATCH repos/{REPO}/git/refs/heads/{PULL_BRANCH}") == 1
    assert len(github.made) == 1


def test_an_account_without_a_name_signs_off_with_its_login() -> None:
    github = FakeGitHub({})
    github.user = {"login": "octocat", "name": None, "id": 1}

    assert signer(api(github)) == "octocat <1+octocat@users.noreply.github.com>"


def test_a_workflow_without_a_last_line_end_gets_one_before_the_comment() -> None:
    github = FakeGitHub({BOT: "on: workflow_dispatch"})

    register_workflows(api(github), REPO)

    assert github.proposed["files"] == {BOT: "on: workflow_dispatch\n" + NOTE}


def test_nothing_happens_when_github_knows_every_workflow() -> None:
    github = FakeGitHub(TEXTS, known=TEXTS)

    said = register_workflows(api(github), REPO)

    assert said == f"GitHub knows every workflow of {FOLDER}/ on main of {REPO}."
    assert not [
        call for call in github.calls if not call.startswith(("GET", "POST graphql"))
    ]
    assert github.commits == {}


def test_a_branch_without_workflows_has_nothing_to_register() -> None:
    github = FakeGitHub({})

    assert "GitHub knows every workflow" in register_workflows(api(github), REPO)


def test_only_the_workflows_of_the_folder_count() -> None:
    github = FakeGitHub({})
    blob = {"text": "on: push\n", "isTruncated": False}
    github.repository = {
        "ref": {
            "target": {
                "oid": HEAD,
                "file": {
                    "object": {
                        "entries": [
                            {"name": "notes.txt", "type": "blob", "object": blob},
                            {"name": "old.yml", "type": "tree", "object": {}},
                            {"name": "ci.yml", "type": "blob", "object": blob},
                        ]
                    }
                },
            }
        }
    }

    register_workflows(api(github), REPO)

    assert github.proposed["files"] == {CI: "on: push\n" + NOTE}


@pytest.mark.parametrize(
    "blob",
    [
        {"text": "on: push\n", "isTruncated": True},
        # GitHub gives no text of a binary file.
        {"text": None, "isTruncated": False},
        None,
    ],
)
def test_a_workflow_whose_whole_text_github_does_not_answer_stops_it(
    blob: dict[str, Any] | None,
) -> None:
    github = FakeGitHub({})
    entry = {"name": "ci.yml", "type": "blob", "object": blob}
    github.repository = {
        "ref": {"target": {"oid": HEAD, "file": {"object": {"entries": [entry]}}}}
    }

    with pytest.raises(GitHubError, match=re.escape(f"whole text of {CI}")):
        register_workflows(api(github), REPO)
    assert github.commits == {}


@pytest.mark.parametrize("repository", [{"ref": None}, {}])
def test_a_repository_without_its_branch_main_is_named(
    repository: dict[str, Any],
) -> None:
    github = FakeGitHub({})
    github.repository = repository

    with pytest.raises(GitHubError, match=f"GitHub has no branch main of {REPO}"):
        register_workflows(api(github), REPO)


def test_a_branch_that_github_does_not_move_opens_no_pull_request() -> None:
    github = FakeGitHub(TEXTS)
    # The branch of an earlier pull request, which GitHub refuses to move.
    github.refs[PULL_BRANCH] = "f" * 40
    github.fail[f"PATCH repos/{REPO}/git/refs/heads/{PULL_BRANCH}"] = 422

    with pytest.raises(GitHubError):
        register_workflows(api(github), REPO)
    assert github.made == []


def test_create_waits_until_github_knows_the_workflows_of_its_push(
    waits: list[float],
) -> None:
    github = FakeGitHub(TEXTS)
    # A workflow is registered as its first run starts, a moment after the push.
    github.looks = [set(), {CI}]
    github.known = {CI, BOT, SBOM}

    assert wait_until_known(api(github), REPO, TEXTS) == []
    assert waits == [10.0, 10.0]


def test_create_names_what_github_still_does_not_know_after_a_minute(
    waits: list[float],
) -> None:
    github = FakeGitHub(TEXTS, known=[CI])

    missing = wait_until_known(api(github), REPO, TEXTS)

    assert missing == [BOT, SBOM]
    assert waits == [10.0] * 5
    assert known_text(TEXTS, missing) == (
        "GitHub hasn't registered 2 of the 3 workflows of .github/workflows/:"
        " blueprint-update.yml, sbom.yaml. It starts none of them, not even on a"
        " schedule, until a push changes their files"
        " (https://github.com/Dennis-Otto/repo-blueprint/issues/652)."
    )
    assert (
        known_text(TEXTS, []) == "GitHub knows all 3 workflows of .github/workflows/."
    )


def test_a_copy_without_workflows_asks_github_nothing() -> None:
    github = FakeGitHub({})

    assert wait_until_known(api(github), REPO, {}) == []
    assert github.calls == []


def test_the_workflows_of_a_checkout_are_its_files_with_the_line_ends_of_git(
    tmp_path: Path,
) -> None:
    assert local_workflows(tmp_path) == {}
    folder = tmp_path / FOLDER
    (folder / "nested.yml").mkdir(parents=True)
    (folder / "ci.yml").write_bytes(b"on: push\r\njobs: {}\r\n")
    (folder / "README.md").write_text("Not a workflow\n", encoding="utf-8")

    assert local_workflows(tmp_path) == {CI: "on: push\njobs: {}\n"}


def a_checkout(root: Path, texts: dict[str, str]) -> Path:
    for path, text in texts.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text, encoding="utf-8")
    return root


def test_the_checklist_names_the_workflows_that_github_does_not_know(
    tmp_path: Path,
) -> None:
    root = a_checkout(tmp_path, TEXTS)

    [step] = workflows_step(api(FakeGitHub(TEXTS, known=[CI])), REPO, root)

    assert step.done is False
    assert step.text.startswith("GitHub knows every workflow of .github/workflows/")
    assert step.how.startswith(
        "GitHub hasn't registered blueprint-update.yml, sbom.yaml: it starts none of"
        " them, not even on a schedule, and gh workflow run answers 404"
    )
    assert f"{workflows.COMMAND} opens the pull request that registers them" in step.how


def test_the_checklist_asks_for_the_comments_to_come_out_again(tmp_path: Path) -> None:
    root = a_checkout(tmp_path, {**TEXTS, BOT: TEXTS[BOT] + NOTE})

    [step] = workflows_step(api(FakeGitHub(TEXTS, known=TEXTS)), REPO, root)

    assert step.done is False
    assert step.how == (
        "The comments that registered blueprint-update.yml are still in them:"
        f" {workflows.COMMAND} opens the pull request that takes them out, or names"
        " the one that is open."
    )


def test_the_checklist_ticks_a_repository_whose_workflows_github_knows(
    tmp_path: Path,
) -> None:
    root = a_checkout(tmp_path, TEXTS)

    [step] = workflows_step(api(FakeGitHub(TEXTS, known=TEXTS)), REPO, root)

    assert step.done is True
    assert step.how == ""
    # Without workflows, the step isn't there, and GitHub isn't asked.
    github = FakeGitHub({})
    assert workflows_step(api(github), REPO, tmp_path / "elsewhere") == []
    assert github.calls == []


def test_the_command_line_runs_the_next_step(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    github = FakeGitHub(TEXTS, known=[CI])

    assert (
        cli.main(["--repo", REPO, "workflows", "register"], api(github), tmp_path) == 0
    )

    assert capsys.readouterr().out.startswith(
        "GitHub hasn't registered blueprint-update.yml, sbom.yaml."
    )
    github.fail[f"POST repos/{REPO}/pulls"] = 422
    github.pulls = []
    assert (
        cli.main(["--repo", REPO, "workflows", "register"], api(github), tmp_path) == 2
    )
    assert "simulated failure" in capsys.readouterr().err
