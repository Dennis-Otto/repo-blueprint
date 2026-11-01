"""Tests of the sync bot of the issue assistant: sync_issue_assistant.py against a
release whose install imitates that of the issue assistant, and the steps of
.github/workflows/sync-issue-assistant.yml in bash, with a gh that answers as GitHub
does, after the filters of jq."""

from __future__ import annotations

import ast
import base64
import dataclasses
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import workflow_steps
from shell import BASH
from workflow_steps import Answer, StepResult, condition_of, exact, step_in

import sync_issue_assistant as sync
from blueprint.bot_health import ONE_TRY, OWN_ISSUE

ROOT = Path(__file__).parents[1]
WORKFLOW = ROOT / ".github/workflows/sync-issue-assistant.yml"
GIT = shutil.which("git")
needs_git = pytest.mark.skipif(
    GIT is None, reason="the sync reads the work tree with git"
)
needs_bash = pytest.mark.skipif(
    BASH is None or GIT is None, reason="the steps run in bash, Git Bash on Windows"
)
# The steps run sync_issue_assistant.py, copied into a repository of their own. In the
# copy of the mutation tests, that is the code with the mutants, which runs only where
# mutmut set it up, so the Mutation workflow leaves them out.
runs_the_script = pytest.mark.mutation_unsafe

OLD = "a12fb7227ff7d966809cad4e043e159977fccfcd"
NEW = "c61378e2e2fb454402774a2d3bb75296739ce2d0"
URL = "https://github.com/Dennis-Otto/issue-assistant/releases/tag/v1.3.1"


def pin(ref: str, version: str) -> str:
    return f"Dennis-Otto/issue-assistant@{ref} # {version}"


def workflow(ref: str = OLD, version: str = "v1.2.2", extra: str = "") -> str:
    """A workflow of the issue assistant, pinned to a release."""
    return (
        "name: Issue assistant\n"
        "on: issues\n"
        "jobs:\n"
        "  apply:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        f"      - uses: {pin(ref, version)}\n"
        f"{extra}"
    )


LINT = (
    "name: Lint\n"
    "on: pull_request\n"
    "jobs:\n"
    "  issue-assistant:\n"
    "    runs-on: ubuntu-24.04\n"
    "    steps:\n"
    f"      - uses: {pin(OLD, 'v1.2.2')}\n"
    "        with:\n"
    "          command: check\n"
)
FIREWALL = "mode: enforce\nallow:\n  - api.anthropic.com\n"
# The blueprint as it is before a release: the four templates of v1.2.2, the Lint
# workflow with the pin of the check, a workflow without the action, the firewall
# policy and the files of the template that render the workflows.
BLUEPRINT = {
    ".github/workflows/issue-assistant.yml": workflow(),
    ".github/workflows/issue-lifecycle.yml": workflow(),
    ".github/workflows/labels.yml": workflow(),
    ".github/workflows/findings.yml": workflow(),
    ".github/workflows/lint.yml": LINT,
    ".github/workflows/ci.yml": "name: CI\non: push\n",
    ".github/egress-firewall.yaml": FIREWALL,
    ".gitignore": "/.issue-assistant/\n",
    **{
        f"template/.github/workflows/{name}.jinja": sync.include(name)
        for name in (
            "issue-assistant.yml",
            "issue-lifecycle.yml",
            "labels.yml",
            "findings.yml",
            "lint.yml",
            "ci.yml",
        )
    },
}
# The templates of the release v1.3.1: a queue in issue-assistant.yml, a new workflow,
# and a firewall policy with one more host.
QUEUED = workflow(extra="concurrency:\n  group: issue\n  queue: max\n")
TEMPLATES = {
    "templates/.github/workflows/issue-assistant.yml": QUEUED,
    "templates/.github/workflows/issue-lifecycle.yml": workflow(),
    "templates/.github/workflows/labels.yml": workflow(),
    "templates/.github/workflows/findings.yml": workflow(),
    "templates/.github/workflows/triage.yml": workflow(),
    "templates/.github/egress-firewall.yaml": FIREWALL + "  - example.com\n",
}
# install as the issue assistant does it: the workflows of its templates with every
# pin of the action moved to the release, but those that a test names in LEAVE (as
# install leaves out the workflow of the discussions while config.toml names no
# category of them), and what a test adds in WRITE (paths to write) and DELETE (paths
# to delete), or a failure.
INSTALL = """\
import os
import re
import sys
from pathlib import Path

tool = Path(__file__).resolve().parent
root = Path(os.environ["ISSUE_ASSISTANT_ROOT"])
command, _, ref, _, version = sys.argv[1:]
assert command == "install"
if os.environ.get("INSTALL_FAILS"):
    print("Give the commit hash of the issue assistant's release.")
    sys.exit(1)
for template in sorted((tool / "templates/.github/workflows").glob("*.yml")):
    if template.name in os.environ.get("LEAVE", "").split():
        continue
    text = re.sub(
        r"Dennis-Otto/issue-assistant@[0-9a-f]{40} # \\S+",
        f"Dennis-Otto/issue-assistant@{ref} # {version}",
        template.read_text(encoding="utf-8"),
    )
    (root / ".github/workflows" / template.name).write_text(
        text, encoding="utf-8", newline="\\n"
    )
    print(f"wrote .github/workflows/{template.name}")
print("kept .github/egress-firewall.yaml; check that it allows the template's hosts")
for name in os.environ.get("WRITE", "").split():
    (root / name).parent.mkdir(parents=True, exist_ok=True)
    (root / name).write_text("new\\n", encoding="utf-8", newline="\\n")
for name in os.environ.get("DELETE", "").split():
    (root / name).unlink()
"""


def git_in(root: Path, *arguments: str) -> str:
    assert GIT
    return subprocess.run(
        [GIT, "-c", "user.name=T", "-c", "user.email=t@example.com", *arguments],
        cwd=root,
        check=True,
        capture_output=True,
        encoding="utf-8",
    ).stdout.strip()


def written(root: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8", newline="\n")
    return root


def blueprint(root: Path, files: dict[str, str] | None = None) -> Path:
    """A git repository of the blueprint, with these files committed."""
    root.mkdir(parents=True)
    git_in(root, "init", "--quiet")
    # The files as they are, also where Git for Windows changes their line breaks.
    git_in(root, "config", "core.autocrlf", "false")
    written(root, BLUEPRINT if files is None else files)
    git_in(root, "add", "--all")
    git_in(root, "commit", "--quiet", "-m", "main")
    return root


def release(root: Path, templates: dict[str, str] | None = None) -> Path:
    """The checkout of a release of the issue assistant, with its install."""
    written(root, {"issue_assistant.py": INSTALL, **(templates or TEMPLATES)})
    return root


def text(root: Path, name: str) -> str:
    return (root / name).read_text(encoding="utf-8")


# pinned


@needs_git
def test_pinned_names_each_release_once(tmp_path: Path) -> None:
    root = blueprint(tmp_path / "blueprint")

    assert sync.pinned(root) == [f"{OLD} v1.2.2"]

    written(root, {".github/workflows/lint.yml": LINT.replace(OLD, NEW)})
    # A pin that moved alone, as Renovate would have moved it.
    assert sync.pinned(root) == [f"{OLD} v1.2.2", f"{NEW} v1.2.2"]


def test_pinned_is_empty_without_the_action(tmp_path: Path) -> None:
    root = written(tmp_path, {".github/workflows/ci.yml": "name: CI\n"})

    assert sync.pinned(root) == []


# adopt


@needs_git
def test_adopt_takes_the_release_over(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = blueprint(tmp_path / "blueprint")
    tool = release(tmp_path / "release")

    changed = sync.adopt(root, tool, NEW, "v1.3.1")

    assert changed == [
        ".github/egress-firewall.yaml",
        ".github/workflows/findings.yml",
        ".github/workflows/issue-assistant.yml",
        ".github/workflows/issue-lifecycle.yml",
        ".github/workflows/labels.yml",
        ".github/workflows/lint.yml",
        ".github/workflows/triage.yml",
        "template/.github/workflows/triage.yml.jinja",
    ]
    # Every pin names the release, that of the check in the Lint workflow too.
    assert sync.pinned(root) == [f"{NEW} v1.3.1"]
    assert text(root, ".github/workflows/lint.yml") == LINT.replace(
        pin(OLD, "v1.2.2"), pin(NEW, "v1.3.1")
    )
    assert text(root, ".github/workflows/issue-assistant.yml") == QUEUED.replace(
        pin(OLD, "v1.2.2"), pin(NEW, "v1.3.1")
    )
    # install keeps a firewall policy that a repository has; the sync takes the
    # release's.
    assert (
        text(root, ".github/egress-firewall.yaml")
        == TEMPLATES["templates/.github/egress-firewall.yaml"]
    )
    # A new workflow is rendered in every repository, the others as before.
    assert text(root, "template/.github/workflows/triage.yml.jinja") == (
        '[% include ".github/workflows/triage.yml" -%]\n'
    )
    assert (
        text(root, "template/.github/workflows/lint.yml.jinja")
        == BLUEPRINT["template/.github/workflows/lint.yml.jinja"]
    )
    assert text(root, ".github/workflows/ci.yml") == "name: CI\non: push\n"
    # The log says what install did.
    assert "wrote .github/workflows/triage.yml\n" in capsys.readouterr().err


@needs_git
def test_adopt_renders_no_workflow_that_install_left_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = blueprint(tmp_path / "blueprint")
    tool = release(tmp_path / "release")
    # install writes the workflow of the discussions only once config.toml names a
    # category of them; an include of a workflow that the root lacks would fail every
    # rendering of the template.
    monkeypatch.setenv("LEAVE", "triage.yml")

    changed = sync.adopt(root, tool, NEW, "v1.3.1")

    assert ".github/workflows/triage.yml" not in changed
    assert "template/.github/workflows/triage.yml.jinja" not in changed
    assert not (root / "template/.github/workflows/triage.yml.jinja").exists()
    assert sync.pinned(root) == [f"{NEW} v1.3.1"]


# A reference.py that writes the page of the variables from the workflows, as the
# blueprint's does, or that fails.
OWNED_LIST = sync.OWNED.as_posix()
REFERENCE = """\
import pathlib, sys
if pathlib.Path("fail").exists():
    sys.exit("reference.py: describe NEW in ABOUT")
names = sorted(p.name for p in pathlib.Path(".github/workflows").glob("*.yml"))
page = pathlib.Path("docs/reference/variables.md")
page.parent.mkdir(parents=True, exist_ok=True)
page.write_text("\\n".join(names) + "\\n", encoding="utf-8", newline="\\n")
print("reference.py: wrote docs/reference/variables.md")
owned = pathlib.Path("template/.github/blueprint/owned.txt.jinja")
owned.write_text(
    "".join(f".github/workflows/{name}\\n" for name in names),
    encoding="utf-8",
    newline="\\n",
)
"""


@needs_git
def test_adopt_writes_the_reference_pages_anew(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = blueprint(
        tmp_path / "blueprint",
        {**BLUEPRINT, "reference.py": REFERENCE, OWNED_LIST: "old\n"},
    )

    changed = sync.adopt(root, release(tmp_path / "release"), NEW, "v1.3.1")

    assert "docs/reference/variables.md" in changed
    # A new workflow joins the list of the files of the blueprint.
    assert OWNED_LIST in changed
    assert ".github/workflows/triage.yml\n" in text(root, OWNED_LIST)
    assert "triage.yml\n" in text(root, "docs/reference/variables.md")
    assert "reference.py: wrote docs/reference/variables.md\n" in (
        capsys.readouterr().err
    )
    # The job of the pull request commits the page.
    folder = tmp_path / "kept"
    sync.keep(root, folder, changed)
    assert "docs/reference/variables.md" in sync.kept(folder)
    assert OWNED_LIST in sync.kept(folder)
    assert (
        f"- `{OWNED_LIST}`: the list of the files of the blueprint, written anew\n"
        in sync.listing(root, folder)
    )


def test_the_job_of_the_sync_can_import_what_the_real_reference_script_needs() -> None:
    # The job adopt runs reference.py on the Python of the runner, with nothing installed
    # but PyYAML of its image; the fake script of the tests above can't show that.
    tree = ast.parse((ROOT / sync.REFERENCE).read_text(encoding="utf-8"))
    imported = {
        (alias.name if isinstance(node, ast.Import) else str(node.module)).split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in node.names
    }
    assert imported - sys.stdlib_module_names == {"yaml"}


@needs_git
def test_adopt_stops_when_the_reference_pages_cant_be_written(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = blueprint(
        tmp_path / "blueprint", {**BLUEPRINT, "reference.py": REFERENCE, "fail": ""}
    )

    with pytest.raises(sync.SyncError) as raised:
        sync.adopt(root, release(tmp_path / "release"), NEW, "v1.3.1")

    assert str(raised.value) == (
        "reference.py could not write the reference pages for v1.3.1; its log above"
        " says why."
    )
    assert "describe NEW in ABOUT" in capsys.readouterr().err


def test_the_files_of_the_template_are_those_of_the_blueprint() -> None:
    for name in (
        "issue-assistant.yml",
        "issue-lifecycle.yml",
        "labels.yml",
        "findings.yml",
    ):
        assert text(ROOT, f"template/.github/workflows/{name}.jinja") == sync.include(
            name
        )


@needs_git
def test_adopt_changes_nothing_when_the_blueprint_has_the_release(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = blueprint(tmp_path / "blueprint")
    tool = release(tmp_path / "release")
    sync.adopt(root, tool, NEW, "v1.3.1")
    git_in(root, "add", "--all")
    git_in(root, "commit", "--quiet", "-m", "the release")
    monkeypatch.chdir(root)

    assert (
        sync.main(
            [
                "adopt",
                str(tool),
                "--ref",
                NEW,
                "--version",
                "v1.3.1",
                "--out",
                str(tmp_path / "out"),
            ]
        )
        == 0
    )

    assert capsys.readouterr().out == ""
    assert not (tmp_path / "out").exists()


@needs_git
def test_adopt_keeps_what_changed_and_lists_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = blueprint(tmp_path / "blueprint")
    tool = release(tmp_path / "release")
    monkeypatch.chdir(root)
    out = tmp_path / "out"

    assert (
        sync.main(
            ["adopt", str(tool), "--ref", NEW, "--version", "v1.3.1", "--out", str(out)]
        )
        == 0
    )

    assert capsys.readouterr().out == (
        "- `.github/egress-firewall.yaml`: the firewall policy of the release\n"
        "- `.github/workflows/findings.yml`: every pin of the action moves to the release\n"
        "- `.github/workflows/issue-assistant.yml`: the template of the release\n"
        "- `.github/workflows/issue-lifecycle.yml`: every pin of the action moves to the release\n"
        "- `.github/workflows/labels.yml`: every pin of the action moves to the release\n"
        "- `.github/workflows/lint.yml`: every pin of the action moves to the release\n"
        "- `.github/workflows/triage.yml`: a new workflow of the release\n"
        "- `template/.github/workflows/triage.yml.jinja`: new, renders"
        " `.github/workflows/triage.yml` in every repository\n"
    )
    assert sync.kept(out) == sync.changed_files(root)
    for name in sync.kept(out):
        assert (out / "files" / name).read_bytes() == (root / name).read_bytes()


@pytest.mark.parametrize(
    ("ref", "version", "error"),
    [
        (
            "v1.3.1",
            "v1.3.1",
            "v1.3.1 is no commit hash; give the commit of the release.",
        ),
        (NEW[:7], "v1.3.1", f"{NEW[:7]} is no commit hash"),
        (NEW, "main", "main is no tag of a release, such as v1.3.1."),
        (NEW, "v1.3.1 --force", "v1.3.1 --force is no tag of a release"),
    ],
)
def test_adopt_needs_the_commit_and_the_tag_of_a_release(
    tmp_path: Path, ref: str, version: str, error: str
) -> None:
    with pytest.raises(sync.SyncError, match=re.escape(error)):
        sync.adopt(tmp_path, release(tmp_path / "release"), ref, version)


@pytest.mark.parametrize(
    "missing",
    ["templates/.github/workflows", "templates/.github/egress-firewall.yaml"],
)
def test_adopt_refuses_what_is_no_release_of_the_issue_assistant(
    tmp_path: Path, missing: str
) -> None:
    templates = {
        name: content
        for name, content in TEMPLATES.items()
        if not name.startswith(missing)
    }
    tool = release(tmp_path / "release", templates)

    with pytest.raises(sync.SyncError, match="has no workflows and no firewall policy"):
        sync.adopt(tmp_path, tool, NEW, "v1.3.1")


@needs_git
def test_a_failed_install_changes_nothing_that_is_kept(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = blueprint(tmp_path / "blueprint")
    monkeypatch.setenv("INSTALL_FAILS", "1")
    monkeypatch.chdir(root)
    out = tmp_path / "out"

    code = sync.main(
        [
            "adopt",
            str(release(tmp_path / "release")),
            "--ref",
            NEW,
            "--version",
            "v1.3.1",
            "--out",
            str(out),
        ]
    )

    assert code == 1
    captured = capsys.readouterr()
    assert (
        captured.out == "::error::install of v1.3.1 failed; its log above says why.\n"
    )
    assert "Give the commit hash" in captured.err
    assert not out.exists()


@needs_git
@pytest.mark.parametrize(
    ("variable", "paths", "named"),
    [
        # A starter that is new in a release, which the blueprint renders from a
        # template of its own.
        (
            "WRITE",
            ".github/issue-assistant/lifecycle.toml",
            ".github/issue-assistant/lifecycle.toml",
        ),
        # Paths that are no plain names, or outside the workflows.
        ("WRITE", ".github/workflows/sub/x.yml", ".github/workflows/sub/x.yml"),
        ("WRITE", ".github/workflows/.hidden.yml", ".github/workflows/.hidden.yml"),
        ("WRITE", "scripts/check.sh .gitignore", ".gitignore, scripts/check.sh"),
        # The sync writes, it never deletes.
        ("DELETE", ".github/workflows/ci.yml", ".github/workflows/ci.yml"),
    ],
)
def test_adopt_takes_over_nothing_but_workflows_and_the_firewall_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    variable: str,
    paths: str,
    named: str,
) -> None:
    root = blueprint(tmp_path / "blueprint")
    monkeypatch.setenv(variable, paths)

    with pytest.raises(sync.SyncError) as raised:
        sync.adopt(root, release(tmp_path / "release"), NEW, "v1.3.1")

    assert str(raised.value) == (
        f"install of v1.3.1 changed {named}, which the sync doesn't take over by"
        " itself: take the release over by hand, with install of the release in the"
        " root of the blueprint, and add what is new to the template."
    )


# What the job of the pull request takes from the artifact


def folder_with(root: Path, files: dict[str, str]) -> Path:
    return written(root / "files", files).parent


@pytest.mark.parametrize(
    "name",
    [
        "README.md",
        ".github/sign-tag.sh",
        ".github/workflows/x.yaml",
        ".github/workflows/sub/x.yml",
        ".github/workflows/-x.yml",
        "template/.github/workflows/x.yml",
        "template/copier.yml.jinja",
        "docs/reference/other.md",
        "docs/faq.md",
        ".git/config",
    ],
)
def test_the_pull_request_takes_nothing_else(tmp_path: Path, name: str) -> None:
    folder = folder_with(tmp_path, {".github/workflows/lint.yml": LINT, name: "x\n"})

    with pytest.raises(
        sync.SyncError, match=re.escape(f"The sync kept {name}, which is no workflow")
    ):
        sync.kept(folder)


def test_the_pull_request_refuses_a_link(tmp_path: Path) -> None:
    folder = folder_with(tmp_path / "kept", {".github/workflows/lint.yml": LINT})
    (tmp_path / "secret.yml").write_text("x\n", encoding="utf-8")
    (tmp_path / "secrets").mkdir()
    for name, target in (
        (".github/workflows/ci.yml", tmp_path / "secret.yml"),
        ("template/.github/workflows/x.yml.jinja", tmp_path / "secrets"),
    ):
        link = folder / "files" / name
        link.parent.mkdir(parents=True, exist_ok=True)
        try:
            link.symlink_to(target, target.is_dir())
        except OSError:
            pytest.skip("this system makes no symbolic links without privileges")
        with pytest.raises(
            sync.SyncError, match=f"kept {re.escape(name)}, which is no"
        ):
            sync.kept(folder)
        link.unlink()


def test_the_pull_request_needs_something_to_commit(tmp_path: Path) -> None:
    (tmp_path / "files").mkdir()

    with pytest.raises(
        sync.SyncError, match=re.escape("The sync kept nothing to commit.")
    ):
        sync.kept(tmp_path)


def test_the_request_commits_what_adopt_kept(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = folder_with(
        tmp_path,
        {
            ".github/workflows/lint.yml": LINT,
            ".github/egress-firewall.yaml": FIREWALL,
            "template/.github/workflows/triage.yml.jinja": sync.include("triage.yml"),
        },
    )

    assert (
        sync.main(
            [
                "commit",
                str(folder),
                "--repo",
                "Dennis-Otto/repo-blueprint",
                "--branch",
                "bot/issue-assistant-next",
                "--head",
                "abc1234",
                "--headline",
                "fix(deps): update the issue assistant to v1.3.1",
                "--body",
                "Signed-off-by: app[bot]",
            ]
        )
        == 0
    )

    request: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert request["query"] == sync.COMMIT
    commit = request["variables"]["input"]
    assert commit["branch"] == {
        "repositoryNameWithOwner": "Dennis-Otto/repo-blueprint",
        "branchName": "bot/issue-assistant-next",
    }
    # Only while the branch is still at the commit that was adopted.
    assert commit["expectedHeadOid"] == "abc1234"
    assert commit["message"] == {
        "headline": "fix(deps): update the issue assistant to v1.3.1",
        "body": "Signed-off-by: app[bot]",
    }
    # It writes, and deletes nothing.
    assert list(commit["fileChanges"]) == ["additions"]
    assert {
        addition["path"]: base64.b64decode(addition["contents"]).decode()
        for addition in commit["fileChanges"]["additions"]
    } == {
        ".github/egress-firewall.yaml": FIREWALL,
        ".github/workflows/lint.yml": LINT,
        "template/.github/workflows/triage.yml.jinja": sync.include("triage.yml"),
    }


def test_the_commit_of_a_folder_that_holds_more_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = folder_with(tmp_path, {".github/sign-tag.sh": "x\n"})

    assert (
        sync.main(
            [
                "commit",
                str(folder),
                "--repo",
                "o/r",
                "--branch",
                "b",
                "--head",
                "abc",
                "--headline",
                "x",
            ]
        )
        == 1
    )

    assert capsys.readouterr().out.startswith(
        "::error::The sync kept .github/sign-tag.sh"
    )


@needs_git
def test_the_description_says_what_changed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = blueprint(tmp_path / "blueprint")
    out = tmp_path / "out"
    sync.keep(root, out, sync.adopt(root, release(tmp_path / "release"), NEW, "v1.3.1"))
    # The job of the pull request compares with main, which the job adopt changed.
    git_in(root, "checkout", "--quiet", "--", ".")
    monkeypatch.chdir(root)

    assert sync.main(["report", str(out), "--version", "v1.3.1", "--url", URL]) == 0

    report = capsys.readouterr().out
    assert report.startswith(
        f"The issue assistant [v1.3.1]({URL}) is out, and the sync bot verified it: the"
        " release is immutable, GitHub's attestation of it holds, its tag points at a"
        " commit of its `main`, and its release workflow signed the tag."
    )
    assert (
        "- `.github/workflows/issue-assistant.yml`: the template of the release\n"
        "- `.github/workflows/issue-lifecycle.yml`: every pin of the action moves to the"
        " release\n"
    ) in report
    assert "- `.github/workflows/triage.yml`: a new workflow of the release\n" in report
    assert "brings these files to every repository made from it" in report
    assert "This pull request merges itself once every required check passes." in report


@needs_git
def test_pinned_prints_each_release(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(blueprint(tmp_path / "blueprint"))

    assert sync.main(["pinned"]) == 0

    assert capsys.readouterr().out == f"{OLD} v1.2.2\n"


def test_the_blueprint_pins_one_release_of_the_issue_assistant() -> None:
    # The workflows of the issue assistant and the check in the Lint workflow, all of
    # them at the same release, which the sync moves together.
    pins = sync.pinned(ROOT)
    assert len(pins) == 1
    for name in ("issue-assistant", "issue-lifecycle", "labels", "findings", "lint"):
        assert pins[0].replace(" ", " # ") in text(
            ROOT, f".github/workflows/{name}.yml"
        )


# In the copy of the mutation tests, the script that the test copies is the code with
# the mutants, which runs only where mutmut set it up.
@pytest.mark.mutation_unsafe
@needs_git
def test_the_script_runs_as_the_workflow_runs_it(tmp_path: Path) -> None:
    root = blueprint(tmp_path / "blueprint")
    shutil.copy(ROOT / "sync_issue_assistant.py", root)

    result = subprocess.run(
        [sys.executable, "sync_issue_assistant.py", "pinned"],
        cwd=root,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )

    assert (result.returncode, result.stdout) == (0, f"{OLD} v1.2.2\n")


# The workflow


def adopt_job() -> dict[str, Any]:
    return workflow_steps.job(WORKFLOW.name, "adopt")


def test_the_sync_runs_every_morning_by_hand_and_for_its_pull_requests() -> None:
    parsed = workflow_steps.workflow(WORKFLOW.name)
    events = parsed["on"]
    assert events["schedule"] == [{"cron": "20 5 * * *"}]
    assert "dry_run" in events["workflow_dispatch"]["inputs"]
    # A pull request that changes the bot runs it as a dry run.
    assert events["pull_request"]["paths"][:3] == [
        ".github/workflows/sync-issue-assistant.yml",
        ".github/sign-tag.sh",
        "sync_issue_assistant.py",
    ]
    assert parsed["env"]["DRY_RUN"] == (
        "${{ github.event_name == 'pull_request' || inputs.dry_run == true }}"
    )
    assert parsed["permissions"] == {}


def test_the_sync_verifies_the_release_before_it_installs() -> None:
    adopt = adopt_job()
    steps = adopt["steps"]
    names = [step.get("name") for step in steps]
    find = names.index("Find the latest published release of the issue assistant")
    verify = names.index("Verify the release before taking it over")
    install = names.index("Install the release in the root of the blueprint")
    assert find < verify < install
    # Nothing of the release runs before it is verified, and only after a verification
    # that passed, since a step that fails stops the job.
    assert not any(
        "$RUNNER_TEMP/issue-assistant" in step.get("run", "")
        for step in steps[: verify + 1]
    )
    assert "$RUNNER_TEMP/issue-assistant" in steps[install]["run"]
    # The job holds no secret and can only read.
    assert "secrets." not in json.dumps(adopt)
    assert "environment" not in adopt
    assert adopt["permissions"] == {"contents": "read"}
    # Both run for a release that the blueprint doesn't have yet, and in a dry run.
    condition = "steps.release.outputs.current != 'true' || env.DRY_RUN == 'true'"
    assert condition_of(steps[verify]) == condition
    assert condition_of(steps[install]) == condition
    # Exactly the verified commit is installed.
    assert '"https://github.com/$SOURCE.git" "$COMMIT"' in steps[install]["run"]
    assert (
        'adopt "$release" --ref "$COMMIT" --version "$TAG"' in (steps[install]["run"])
    )
    assert workflow_steps.workflow(WORKFLOW.name)["env"]["SOURCE"] == (
        "Dennis-Otto/issue-assistant"
    )


def test_the_job_of_the_pull_request_runs_nothing_of_the_release() -> None:
    pull = workflow_steps.job(WORKFLOW.name, "pull-request")
    assert pull["needs"] == "adopt"
    # The release app, in the environment that only main may use, and never in a pull
    # request or a dry run.
    assert pull["environment"]["name"] == "release"
    assert condition_of(pull) == (
        "vars.RELEASE_AUTOMATION_CLIENT_ID != '' && github.event_name != 'pull_request'"
        " && inputs.dry_run != true"
    )
    token = step_in(pull, "Create a token of the release app")
    assert token["with"]["permission-workflows"] == "write"
    # No code of the release: only sync_issue_assistant.py of main and the artifact.
    assert "issue_assistant.py install" not in json.dumps(pull)
    assert "$RUNNER_TEMP/issue-assistant" not in json.dumps(pull)
    [checkout] = [
        step
        for step in pull["steps"]
        if step.get("uses", "").startswith("actions/checkout@")
    ]
    assert checkout["with"]["sparse-checkout"].startswith(
        ".github/workflows\ntemplate/.github/workflows\n"
    )


def test_the_bot_health_bot_keeps_the_issue_of_a_failed_run() -> None:
    # One issue per failing bot, from the bot-health bot, with the reason of a refusal
    # from its annotation: the sync keeps no issue of its own, which would be a second.
    assert "issues: write" not in WORKFLOW.read_text(encoding="utf-8")
    jobs = workflow_steps.workflow(WORKFLOW.name)["jobs"]
    assert [key for key, job in jobs.items() if "name" in job] == [
        "adopt",
        "pull-request",
    ]
    assert (
        'echo "::error::$1"'
        in (step_in(adopt_job(), "Verify the release before taking it over")["run"])
    )
    health = workflow_steps.workflow("bot-health.yml")
    assert "Issue assistant sync" in health["on"]["workflow_run"]["workflows"]
    assert "Issue assistant sync" not in OWN_ISSUE | ONE_TRY


SOURCE = "Dennis-Otto/issue-assistant"
# As gh fails: the body of the error on stdout, even with --jq.
BODY_OF_ERROR = '{"message":"Bad Gateway","status":"502"}\n'


def bad_gateway(pattern: str) -> Answer:
    return Answer(pattern, BODY_OF_ERROR, "gh: Bad Gateway (HTTP 502)\n", 1)


def planned(kind: str, outcome: str, tag: str) -> Answer:
    """The answer of gh for an outcome that the test planned for a kind of call: the
    latest release, its attestation, or whether it is immutable."""
    if kind == "release":
        assert outcome == "fail", outcome
        return bad_gateway(r"release view .*")
    if kind == "immutable":
        assert outcome == "fail", outcome
        return bad_gateway(rf"api repos/{SOURCE}/releases/tags/v1\.3\.1 .*")
    assert kind == "attestation", kind
    verify = r"release verify .*"
    if outcome == "fail":
        return Answer(verify, f"No attestations for tag {tag}\n", code=1)
    assert outcome == "down", outcome
    return Answer(verify, "gh: Bad Gateway (HTTP 502)\n", code=1)


def github(
    plans: dict[str, list[str]],
    *,
    tag: str = "v1.3.1",
    commit: str = NEW,
    immutable: str = "true",
    status: str = "ahead",
    open_pulls: str = "",
    others: str = "",
    branches: tuple[str, ...] = (),
) -> list[Answer]:
    """How gh answers the steps of the sync: first the outcomes that the test planned,
    one call each, then the usual ones. GitHub has the latest release tag at commit,
    immutable or not, status against the main of the issue assistant, the open pull
    requests of the bot, each as its number and its title, the commits of others on
    its branch, and of the branches of the blueprint those named."""
    once = [
        dataclasses.replace(planned(kind, outcome, tag), once=True)
        for kind, outcomes in plans.items()
        for outcome in outcomes
    ]
    return [
        *once,
        Answer(r"release view .*", f"{tag}\n"),
        Answer(r"release verify .*", f"Release {tag} verified!\n"),
        Answer(rf"api repos/{SOURCE}/commits/.*", f"{commit}\n"),
        Answer(rf"api repos/{SOURCE}/releases/tags/v1\.3\.1 .*", f"{immutable}\n"),
        Answer(rf"api repos/{SOURCE}/compare/.*", f"{status}\n"),
        Answer(r"pr list .*", open_pulls),
        Answer(r"pr (?:close|merge|edit|create) .*"),
        exact("api users/app[bot] --jq .id", "42\n"),
        Answer(r"api graphql .*", "c0ffee\n"),
        Answer(r"api repos/o/r/pulls/12/commits .*", others),
        *(exact(f"api repos/o/r/git/ref/heads/{branch}") for branch in branches),
        Answer(r"api repos/o/r/git/ref/heads/.*", code=1),
        Answer(r"api --method .*"),
    ]


# The Python of the tests as python3, not one that the PATH of Windows names.
PYTHON3 = f'exec "{Path(sys.executable).as_posix()}" "$@"\n'


def run_step(
    tmp_path: Path,
    step: tuple[str, str],
    *,
    plans: dict[str, list[str]] | None = None,
    answers: dict[str, Any] | None = None,
    stubs: dict[str, str] | None = None,
    env: dict[str, str] | None = None,
) -> StepResult:
    """A step of the sync as GitHub runs it, in the workspace tmp_path/workspace, with
    the fake gh, which answers as github() does with plans and answers, a sleep that
    notes its seconds, python3 the Python of the tests, and the variables of env."""
    job, name = step
    return workflow_steps.run_step(
        tmp_path,
        WORKFLOW.name,
        job,
        name,
        answers=github(plans or {}, **(answers or {})),
        env={"TAG": "v1.3.1", "COMMIT": NEW, **(env or {})},
        stubs={
            "sleep": workflow_steps.recording("sleep"),
            "python3": PYTHON3,
            **(stubs or {}),
        },
    )


def slept(result: StepResult) -> list[str]:
    return [call for call in result.stubbed if call.startswith("sleep ")]


FIND = ("adopt", "Find the latest published release of the issue assistant")
VERIFY = ("adopt", "Verify the release before taking it over")
INSTALL_STEP = ("adopt", "Install the release in the root of the blueprint")
PULL_REQUEST = ("pull-request", "Open, update or close the pull request of the release")


def workspace(tmp_path: Path) -> Path:
    """The checkout of the blueprint, where the steps run."""
    return tmp_path / "workspace"


def with_script(root: Path) -> Path:
    shutil.copy(ROOT / "sync_issue_assistant.py", root)
    return root


def blueprint_with_script(root: Path) -> Path:
    """The blueprint with sync_issue_assistant.py committed, as the jobs check it out."""
    script = (ROOT / "sync_issue_assistant.py").read_text(encoding="utf-8")
    return blueprint(root, {**BLUEPRINT, "sync_issue_assistant.py": script})


RELEASE_VIEW = f"release view --repo {SOURCE} --json tagName --jq .tagName"


@runs_the_script
@needs_bash
@pytest.mark.parametrize(
    ("lint", "current"),
    [
        (LINT, False),
        (LINT.replace(pin(OLD, "v1.2.2"), pin(NEW, "v1.3.1")), True),
    ],
)
def test_the_sync_finds_the_latest_release(
    tmp_path: Path, lint: str, current: bool
) -> None:
    with_script(written(workspace(tmp_path), {".github/workflows/lint.yml": lint}))

    result = run_step(tmp_path, FIND, plans={"release": ["fail"]})

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.outputs == {
        "tag": "v1.3.1",
        "commit": NEW,
        "url": URL,
        **({"current": "true"} if current else {}),
    }
    assert result.summary == (
        "The blueprint has the issue assistant v1.3.1, the latest release.\n"
        if current
        else ""
    )
    # Not the newest tag: the latest published release, asked again after a failure.
    assert result.commands[:3] == [
        RELEASE_VIEW,
        RELEASE_VIEW,
        f"api repos/{SOURCE}/commits/v1.3.1 --jq .sha",
    ]
    assert slept(result) == ["sleep 10"]


@runs_the_script
@needs_bash
def test_the_sync_needs_a_published_release(tmp_path: Path) -> None:
    with_script(written(workspace(tmp_path), {".github/workflows/lint.yml": LINT}))

    result = run_step(tmp_path, FIND, answers={"tag": ""})

    assert result.returncode == 1
    assert (
        "::error::The issue assistant has no published release to take over."
        in result.stdout
    )
    assert result.outputs == {}


def verify(
    tmp_path: Path,
    signed: int = 0,
    plans: dict[str, list[str]] | None = None,
    **answers: str,
) -> StepResult:
    """The step that verifies the release, with a sign-tag.sh that only records how it
    is called and exits with signed: 1 for a tag that isn't signed, 2 for one it could
    not check."""
    written(
        workspace(tmp_path),
        {
            ".github/sign-tag.sh": (
                f'echo "sign-tag.sh $*" >> "$STUB_CALLS"\nexit {signed}\n'
            )
        },
    )
    return run_step(tmp_path, VERIFY, plans=plans, answers=answers)


@runs_the_script
@needs_bash
@pytest.mark.parametrize("status", ["identical", "ahead"])
def test_a_signed_attested_immutable_release_on_main_passes(
    tmp_path: Path, status: str
) -> None:
    result = verify(tmp_path, status=status)

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.commands == [
        f"api repos/{SOURCE}/releases/tags/v1.3.1 --jq .immutable",
        f"api repos/{SOURCE}/compare/{NEW}...main --jq .status",
        f"release verify v1.3.1 --repo {SOURCE}",
    ]
    assert result.stubbed == [f"sign-tag.sh verify v1.3.1 {NEW} {SOURCE}"]
    assert "Release v1.3.1 verified!" in result.stdout
    assert result.summary == (
        "The release v1.3.1 of Dennis-Otto/issue-assistant is immutable, attested by"
        " GitHub, on its main and signed by its release workflow.\n"
    )


@runs_the_script
@needs_bash
def test_the_sync_asks_github_again(tmp_path: Path) -> None:
    result = verify(
        tmp_path, plans={"immutable": ["fail", "fail"], "attestation": ["fail"]}
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert slept(result) == ["sleep 10", "sleep 20", "sleep 10"]


@runs_the_script
@needs_bash
@pytest.mark.parametrize(
    ("answers", "plans", "signed", "error"),
    [
        (
            {"immutable": "false"},
            {},
            0,
            "The release v1.3.1 of Dennis-Otto/issue-assistant is not immutable; the bot"
            " takes over only an immutable release.",
        ),
        # The tag of a commit that main never had, or one past main.
        (
            {"status": "diverged"},
            {},
            0,
            f"The tag v1.3.1 of Dennis-Otto/issue-assistant points at {NEW}, which is not"
            " on its main (diverged).",
        ),
        (
            {"status": "behind"},
            {},
            0,
            f"The tag v1.3.1 of Dennis-Otto/issue-assistant points at {NEW}, which is not"
            " on its main (behind).",
        ),
        # A release without GitHub's attestation, such as one from before immutable
        # releases, three times.
        (
            {},
            {"attestation": ["fail", "fail", "fail"]},
            0,
            "GitHub's attestation of the release v1.3.1 of Dennis-Otto/issue-assistant"
            " doesn't hold; the log of the run shows what gh release verify says.",
        ),
        # A lightweight tag, as v1.2.2 has, one at another commit, or one that another
        # workflow signed: sign-tag.sh says which, in tests/test_sign_tag.py.
        (
            {},
            {},
            1,
            "The tag v1.3.1 of Dennis-Otto/issue-assistant is not one that its release"
            f" workflow signed at {NEW}.",
        ),
    ],
)
def test_any_other_release_of_the_issue_assistant_stops_the_sync(
    tmp_path: Path,
    answers: dict[str, str],
    plans: dict[str, list[str]],
    signed: int,
    error: str,
) -> None:
    result = verify(tmp_path, signed, plans, **answers)

    assert result.returncode == 1
    assert f"::error::{error}" in result.stdout.splitlines()
    # The summary says why, what it means and what to do.
    assert result.summary.startswith(
        "### The sync bot refused the release v1.3.1 of Dennis-Otto/issue-assistant\n\n"
        f"{error}\n\n"
    )
    assert "Nothing has changed here." in result.summary
    assert (
        "(https://github.com/Dennis-Otto/issue-assistant/blob/main/SECURITY.md#verify-a-release)"
        in result.summary
    )


@runs_the_script
@needs_bash
def test_a_signature_that_could_not_be_checked_refuses_nothing(tmp_path: Path) -> None:
    result = verify(tmp_path, signed=2)

    assert result.returncode == 1
    assert (
        "::error::The signature of the release v1.3.1 of Dennis-Otto/issue-assistant"
        " could not be checked; nothing has changed, and the next run checks it again."
    ) in result.stdout.splitlines()
    assert result.summary == ""


@runs_the_script
@needs_bash
def test_a_question_without_an_answer_refuses_nothing(tmp_path: Path) -> None:
    result = verify(tmp_path, plans={"immutable": ["fail", "fail", "fail"]})

    assert result.returncode == 1
    assert result.summary == ""


@runs_the_script
@needs_bash
def test_an_attestation_that_github_could_not_check_refuses_nothing(
    tmp_path: Path,
) -> None:
    result = verify(tmp_path, plans={"attestation": ["down", "down", "down"]})

    assert result.returncode == 1
    assert (
        "::error::GitHub's attestation of the release v1.3.1 of"
        " Dennis-Otto/issue-assistant could not be checked; nothing has changed, and"
        " the next run checks it again."
    ) in result.stdout.splitlines()
    assert result.summary == ""


@runs_the_script
@needs_bash
@pytest.mark.parametrize(
    ("have", "latest", "older"),
    [
        ("v1.3.1", "v1.2.2", True),
        ("v1.10.0", "v1.9.3", True),
        ("v1.9.3", "v1.10.0", False),
        ("v1.2.2", "v1.3.1", False),
    ],
)
def test_the_sync_never_goes_back_to_an_older_release(
    tmp_path: Path, have: str, latest: str, older: bool
) -> None:
    lint = LINT.replace(pin(OLD, "v1.2.2"), pin(OLD, have))
    with_script(written(workspace(tmp_path), {".github/workflows/lint.yml": lint}))

    result = run_step(tmp_path, FIND, answers={"tag": latest})

    if older:
        assert result.returncode == 1
        assert (
            f"::error::The latest release {latest} of Dennis-Otto/issue-assistant is"
            f" older than {have}, which the blueprint has; the bot never goes back to"
            " an older release."
        ) in result.stdout.splitlines()
        assert result.summary.startswith(
            f"### The sync bot refused the release {latest} of"
            " Dennis-Otto/issue-assistant\n"
        )
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.summary == ""
    assert "current" not in result.outputs


# git for the step that installs the release: the fetch of the verified commit and its
# checkout bring the release that the test made; anything else is git itself.
GIT_STUB = """#!/usr/bin/env bash
if [[ "$1" == -C && "$3" == fetch ]]; then
  echo "git fetch ${*:4}" >> "$STUB_CALLS"
  failures=$(grep -c "^git fetch failed" "$STUB_CALLS" || true)
  if ((failures < ${FETCH_FAILURES:-0})); then
    echo "git fetch failed" >> "$STUB_CALLS"
    exit 128
  fi
  exit 0
fi
if [[ "$1" == -C && "$3" == checkout ]]; then
  echo "git checkout ${*:4}" >> "$STUB_CALLS"
  cp -R "$RELEASE/." "$2/"
  exit 0
fi
exec "$REAL_GIT" "$@"
"""


def install(tmp_path: Path, **variables: str) -> StepResult:
    """The step that installs the release, which the test made, in the blueprint of
    the workspace."""
    assert GIT
    return run_step(
        tmp_path,
        INSTALL_STEP,
        stubs={"git": GIT_STUB},
        env={
            "RELEASE": release(tmp_path / "release").as_posix(),
            "REAL_GIT": Path(GIT).as_posix(),
            **variables,
        },
    )


@runs_the_script
@needs_bash
def test_the_sync_installs_the_verified_commit(tmp_path: Path) -> None:
    root = blueprint_with_script(workspace(tmp_path))

    result = install(tmp_path, FETCH_FAILURES="1")

    assert result.returncode == 0, result.stdout + result.stderr
    fetch = f"git fetch --quiet --depth=1 https://github.com/{SOURCE}.git {NEW}"
    assert result.stubbed == [
        fetch,
        "git fetch failed",
        "sleep 10",
        fetch,
        "git checkout --quiet --detach FETCH_HEAD",
    ]
    assert result.outputs == {"changed": "true"}
    assert result.summary.startswith(
        "### The issue assistant v1.3.1\n\n"
        "`install` of the release in the root of the blueprint changes these files:\n\n"
        "- `.github/egress-firewall.yaml`: the firewall policy of the release\n"
    )
    assert "+  queue: max\n" in result.summary
    # The new workflow shows in the changes too.
    assert "+++ b/.github/workflows/triage.yml\n" in result.summary
    kept = tmp_path / "runner/sync"
    assert sync.kept(kept) == sync.changed_files(root)


@runs_the_script
@needs_bash
def test_the_sync_without_changes_says_so(tmp_path: Path) -> None:
    root = blueprint_with_script(workspace(tmp_path))
    sync.adopt(root, release(tmp_path / "first"), NEW, "v1.3.1")
    git_in(root, "add", "--all")
    git_in(root, "commit", "--quiet", "-m", "the release")

    result = install(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.outputs == {}
    assert result.summary == (
        "The blueprint has every template of the issue assistant v1.3.1.\n"
    )


@runs_the_script
@needs_bash
def test_the_sync_stops_when_the_commit_cant_be_fetched(tmp_path: Path) -> None:
    blueprint_with_script(workspace(tmp_path))

    result = install(tmp_path, FETCH_FAILURES="3")

    assert result.returncode == 1
    assert (
        f"::error::The commit {NEW} of Dennis-Otto/issue-assistant could not be fetched;"
        " nothing has changed, and the next run tries again."
    ) in result.stdout
    assert "git checkout --quiet --detach FETCH_HEAD" not in result.stubbed
    assert result.outputs == {}


def pull_request(tmp_path: Path, changed: bool = True, **answers: Any) -> StepResult:
    """The step of the pull request, on main as the job adopt found it, with what that
    job kept, and gh answering as github() does with answers."""
    root = blueprint_with_script(workspace(tmp_path))
    if changed:
        sync.keep(
            root,
            tmp_path / "runner/sync",
            sync.adopt(root, release(tmp_path / "release"), NEW, "v1.3.1"),
        )
        git_in(root, "checkout", "--quiet", "--", ".")
        git_in(root, "clean", "--quiet", "--force")
    return run_step(
        tmp_path,
        PULL_REQUEST,
        answers=answers,
        env={
            "APP_SLUG": "app",
            "CHANGED": "true" if changed else "",
            "URL": URL,
            "SHA": "abc1234",
        },
    )


HEADLINE = "fix(deps): update the issue assistant to v1.3.1"


@runs_the_script
@needs_bash
def test_the_sync_opens_a_pull_request_that_merges_itself(tmp_path: Path) -> None:
    result = pull_request(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.commands[1:] == [
        "api repos/o/r/git/ref/heads/bot/issue-assistant-next",
        "api --method POST repos/o/r/git/refs -f ref=refs/heads/bot/issue-assistant-next -f sha=abc1234",
        "api users/app[bot] --jq .id",
        f"api graphql --input {(tmp_path / 'runner/commit.json').as_posix()} --jq .data.createCommitOnBranch.commit.oid",
        "api repos/o/r/git/ref/heads/bot/issue-assistant",
        "api --method POST repos/o/r/git/refs -f ref=refs/heads/bot/issue-assistant -f sha=c0ffee",
        "api --method DELETE repos/o/r/git/refs/heads/bot/issue-assistant-next",
        f"pr create --base main --head bot/issue-assistant --title {HEADLINE} --body-file {(tmp_path / 'runner/body.md').as_posix()}",
        "pr merge bot/issue-assistant --auto --squash",
    ]
    [request] = result.read_by("api graphql", "--input")
    commit = json.loads(request)["variables"]["input"]
    assert commit["expectedHeadOid"] == "abc1234"
    assert commit["message"]["headline"] == HEADLINE
    # The sign-off names the app's account, the author of the commit.
    assert commit["message"]["body"].endswith(
        "\n\nSigned-off-by: app[bot] <42+app[bot]@users.noreply.github.com>"
    )
    assert f"the verified release {URL}" in commit["message"]["body"]
    [body] = result.read_by("pr create", "--body-file")
    assert body.startswith(f"The issue assistant [v1.3.1]({URL}) is out")
    assert (
        "- `.github/workflows/lint.yml`: every pin of the action moves to the release\n"
        in body
    )
    assert result.summary == (
        "The pull request of the issue assistant v1.3.1 from bot/issue-assistant has the"
        " commit c0ffee, and merges itself once every check passes.\n"
    )


@runs_the_script
@needs_bash
def test_the_sync_moves_its_pull_request_on_to_a_newer_release(tmp_path: Path) -> None:
    result = pull_request(
        tmp_path,
        open_pulls="12\tfix(deps): update the issue assistant to v1.3.0",
        # The merges of main by the branch bot are the app's.
        others="",
        branches=("bot/issue-assistant",),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    calls = result.commands
    assert (
        "api --method PATCH repos/o/r/git/refs/heads/bot/issue-assistant -f sha=c0ffee -F force=true"
        in calls
    )
    assert (
        f"pr edit 12 --title {HEADLINE} --body-file {(tmp_path / 'runner/body.md').as_posix()}"
        in calls
    )
    assert not result.called("pr create")
    assert calls[-1] == "pr merge bot/issue-assistant --auto --squash"


@runs_the_script
@needs_bash
def test_the_sync_keeps_a_pull_request_of_the_same_release(tmp_path: Path) -> None:
    result = pull_request(tmp_path, open_pulls=f"12\t{HEADLINE}")

    assert result.returncode == 0, result.stdout + result.stderr
    # The branch bot keeps it current with main; nothing is committed again.
    calls = result.commands
    assert calls[-1] == "pr merge 12 --auto --squash"
    assert not any("graphql" in call or "--method" in call for call in calls)
    assert result.summary == (
        "#12 brings the issue assistant v1.3.1 already, and merges itself once every"
        " check passes.\n"
    )


@runs_the_script
@needs_bash
def test_the_sync_leaves_a_branch_with_someone_elses_commit_alone(
    tmp_path: Path,
) -> None:
    result = pull_request(
        tmp_path,
        open_pulls="12\tfix(deps): update the issue assistant to v1.3.0",
        others="f00ba4\n",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.commands[-1] == (
        "api repos/o/r/pulls/12/commits --paginate --jq .[] | select((.parents |"
        ' length) == 1 and .author.login != "app[bot]") | .sha'
    )
    assert result.summary == (
        "Someone else committed to bot/issue-assistant, so the bot leaves #12 as it is:"
        " merge or close it, and the next run brings the latest release.\n"
    )


@runs_the_script
@needs_bash
def test_the_sync_closes_its_pull_request_when_main_has_the_release(
    tmp_path: Path,
) -> None:
    result = pull_request(tmp_path, changed=False, open_pulls=f"12\t{HEADLINE}")

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.commands[-1] == (
        "pr close 12 --delete-branch --comment `main` has the issue assistant v1.3.1"
        " without this pull request: https://github.com/o/r/actions/runs/5"
    )
    assert result.summary == "main has the issue assistant v1.3.1; closed #12.\n"


@runs_the_script
@needs_bash
def test_the_sync_without_a_pull_request_has_nothing_to_do(tmp_path: Path) -> None:
    result = pull_request(tmp_path, changed=False)

    assert result.returncode == 0, result.stdout + result.stderr
    assert len(result.commands) == 1
    assert result.summary == ""
