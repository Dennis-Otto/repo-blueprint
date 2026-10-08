"""Tests of blueprint.py against a simulated GitHub."""

from __future__ import annotations

import io
import json
import re
import subprocess
import urllib.error
import urllib.parse
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pytest

import blueprint.checklist
from blueprint import cli
from blueprint.checklist import checklist, reuse_compliant
from blueprint.github import Api, GitHubError
from blueprint.settings import (
    MAIN_ONLY,
    Drift,
    Settings,
    apply_pages,
    check_actions,
    check_community,
    check_environments,
    check_pages,
    main_ruleset,
    merge,
    ruleset_differences,
    tag_ruleset,
)

REPO = "Dennis-Otto/demo"
CONFIG = """
[repository]
description = "A demo"
homepage = ""
topics = ["b", "a"]
has_wiki = false
allow_update_branch = true

[security]
immutable_releases = true
private_vulnerability_reporting = true
dependabot_alerts = true
dependabot_security_updates = true
secret_scanning = true
secret_scanning_push_protection = true

[actions]
default_workflow_permissions = "read"
can_approve_pull_request_reviews = false
sha_pinning_required = true
fork_pr_approval = "all_external_contributors"

[branch]
required_checks = ["check (python)", "reuse"]

[variables]
PUBLISH_TO = "pypi"
RELEASE_AUTOMATION_CLIENT_ID = "Iv23client"

[environments.release]
secrets = ["RELEASE_AUTOMATION_PRIVATE_KEY"]

[environments.pypi]
secrets = []

[pages]
build_type = "workflow"
"""


LABELS = """
[[label]]
name = "release"
color = "5319E7"
description = "The release PR"
group = "release"

[[label]]
name = "good first issue"
color = "7057ff"
description = "Good for newcomers"
group = "decision"
"""


class FakeGitHub:
    """The parts of GitHub's API that blueprint.py uses, kept in memory."""

    def __init__(self) -> None:
        self.repo: dict[str, Any] = {
            "description": None,
            "homepage": None,
            "topics": ["old"],
            "has_wiki": True,
            "allow_update_branch": False,
            "security_and_analysis": {
                "secret_scanning": {"status": "disabled"},
                "secret_scanning_push_protection": {"status": "disabled"},
            },
        }
        self.switches = {
            "immutable-releases": False,
            "private-vulnerability-reporting": False,
            "vulnerability-alerts": False,
            "automated-security-fixes": False,
        }
        self.workflow = {
            "default_workflow_permissions": "write",
            "can_approve_pull_request_reviews": True,
        }
        self.permissions = {
            "enabled": True,
            "allowed_actions": "selected",
            "sha_pinning_required": False,
        }
        self.fork_approval = "first_time_contributors"
        self.rulesets: dict[int, dict[str, Any]] = {}
        self.variables: dict[str, str] = {"RELEASE_AUTOMATION_CLIENT_ID": "outdated"}
        self.environments: dict[str, dict[str, Any]] = {}
        self.og_image = False
        self.community: dict[str, Any] = {
            "health_percentage": 100,
            "description": "A demo",
            "files": {"readme": {"url": "x"}, "contributing": {"url": "x"}},
        }
        # Off, as in a new repository.
        self.pages: dict[str, Any] | None = None
        self.labels: dict[str, dict[str, str]] = {
            "good first issue": {"color": "000000", "description": "Old"},
            "spare": {"color": "ffffff", "description": "Not in the configuration"},
        }
        self.next_id = 1
        self.calls: list[tuple[str, str]] = []
        self.fail: dict[tuple[str, str], int] = {}

    # ------------------------------------------------------------------ plumbing

    def __call__(
        self, arguments: Sequence[str], body: str | None
    ) -> subprocess.CompletedProcess[str]:
        if arguments[0] == "repo":
            return subprocess.CompletedProcess(arguments, 0, f"{REPO}\n", "")
        if arguments[1] == "graphql":
            answer = {
                "data": {"repository": {"usesCustomOpenGraphImage": self.og_image}}
            }
            return subprocess.CompletedProcess(arguments, 0, json.dumps(answer), "")
        method, path = arguments[3], arguments[4]
        self.calls.append((method, path))
        payload = json.loads(body) if body else None
        status: int = self.fail.get((method, path), 0)
        data: Any = None
        if not status:
            status, data = self.route(
                method, path.removeprefix(f"repos/{REPO}"), payload
            )
        text = "" if data is None else json.dumps(data)
        return subprocess.CompletedProcess(
            arguments,
            0 if status < 400 else 1,
            f"HTTP/2.0 {status} X\r\nA: b\r\n\r\n{text}",
            "",
        )

    def route(self, method: str, path: str, body: Any) -> tuple[int, Any]:
        for pattern, handler in (
            (r"", self.repository),
            (r"/topics", self.topics),
            (
                r"/(immutable-releases|private-vulnerability-reporting|vulnerability-alerts|automated-security-fixes)",
                self.switch,
            ),
            (
                r"/actions/permissions/fork-pr-contributor-approval",
                self.fork_pr_approval,
            ),
            (r"/actions/permissions/workflow", self.workflow_permissions),
            (r"/actions/permissions", self.actions_permissions),
            (r"/rulesets(?:/(\d+))?", self.ruleset),
            (r"/actions/variables(?:/(\w+))?", self.variable),
            (r"/environments/([\w-]+)", self.environment),
            (r"/labels(?:/([^?]+))?(?:\?per_page=100)?", self.label),
            (
                r"/environments/([\w-]+)/deployment-branch-policies(?:/(\d+))?",
                self.branch_policy,
            ),
            (r"/environments/([\w-]+)/secrets", self.secrets),
            (r"/community/profile", self.community_profile),
            (r"/pages", self.pages_site),
        ):
            match = re.fullmatch(pattern, path)
            if match:
                result: tuple[int, Any] = handler(method, body, *match.groups())
                return result
        raise AssertionError(f"unexpected request {method} {path}")

    def community_profile(self, method: str, body: Any) -> tuple[int, Any]:
        return 200, self.community

    def repository(self, method: str, body: Any) -> tuple[int, Any]:
        if method == "PATCH":
            for key, value in body.items():
                if key == "security_and_analysis":
                    self.repo[key].update(value)
                else:
                    self.repo[key] = value
        return 200, self.repo

    def topics(self, method: str, body: Any) -> tuple[int, Any]:
        self.repo["topics"] = body["names"]
        return 200, {"names": body["names"]}

    def switch(self, method: str, body: Any, name: str) -> tuple[int, Any]:
        if method == "GET":
            if name == "vulnerability-alerts":
                return (
                    (204, None)
                    if self.switches[name]
                    else (404, {"message": "Not Found"})
                )
            return 200, {"enabled": self.switches[name]}
        self.switches[name] = method == "PUT"
        return 204, None

    def workflow_permissions(self, method: str, body: Any) -> tuple[int, Any]:
        if method == "PUT":
            self.workflow = body
            return 204, None
        return 200, self.workflow

    def fork_pr_approval(self, method: str, body: Any) -> tuple[int, Any]:
        if method == "PUT":
            self.fork_approval = body["approval_policy"]
            return 204, None
        return 200, {"approval_policy": self.fork_approval}

    def actions_permissions(self, method: str, body: Any) -> tuple[int, Any]:
        if method == "PUT":
            self.permissions = body
            return 204, None
        return 200, self.permissions

    def ruleset(self, method: str, body: Any, number: str | None) -> tuple[int, Any]:
        if method == "GET" and number is None:
            return 200, [
                {"id": key, "name": value["name"]}
                for key, value in self.rulesets.items()
            ]
        if method == "GET":
            return 200, self.rulesets[int(number or 0)]
        if method == "POST":
            self.rulesets[self.next_id] = body
            self.next_id += 1
            return 201, body
        self.rulesets[int(number or 0)] = body
        return 200, body

    def variable(self, method: str, body: Any, name: str | None) -> tuple[int, Any]:
        if method == "GET":
            if name in self.variables:
                return 200, {"name": name, "value": self.variables[name]}
            return 404, {"message": "Not Found"}
        self.variables[body["name"]] = body["value"]
        return 201, None

    def environment(self, method: str, body: Any, name: str) -> tuple[int, Any]:
        if method == "PUT":
            environment = self.environments.setdefault(
                name, {"branches": [], "secrets": []}
            )
            environment["policy"] = body["deployment_branch_policy"]
        if name not in self.environments:
            return 404, {"message": "Not Found"}
        return 200, {
            "name": name,
            "deployment_branch_policy": self.environments[name]["policy"],
        }

    def branch_policy(
        self, method: str, body: Any, name: str, number: str | None
    ) -> tuple[int, Any]:
        branches = self.environments[name]["branches"]
        if method == "GET":
            return 200, {"branch_policies": branches}
        if method == "DELETE":
            branches[:] = [item for item in branches if item["id"] != int(number or 0)]
            return 204, None
        branches.append(
            {"id": self.next_id, "name": body["name"], "type": body["type"]}
        )
        self.next_id += 1
        return 200, None

    def label(self, method: str, body: Any, quoted: str | None) -> tuple[int, Any]:
        if method == "GET":
            return 200, [{"name": name, **label} for name, label in self.labels.items()]
        if method == "PATCH":
            assert quoted == urllib.parse.quote(body["name"], safe="")
        self.labels[body["name"]] = {
            "color": body["color"],
            "description": body["description"],
        }
        return 200, body

    def pages_site(self, method: str, body: Any) -> tuple[int, Any]:
        if method == "POST":
            assert self.pages is None
            self.pages = {"build_type": body["build_type"], "html_url": "https://x/"}
            return 201, self.pages
        if self.pages is None:
            return 404, {"message": "Not Found"}
        if method == "PUT":
            self.pages.update(body)
            return 204, None
        return 200, self.pages

    def secrets(self, method: str, body: Any, name: str) -> tuple[int, Any]:
        if name not in self.environments:
            return 404, {"message": "Not Found"}
        return 200, {
            "secrets": [
                {"name": secret} for secret in self.environments[name]["secrets"]
            ]
        }


@pytest.fixture
def github() -> FakeGitHub:
    return FakeGitHub()


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """The checklist asks the REUSE API; the tests stay offline."""
    monkeypatch.setattr(blueprint.checklist, "reuse_compliant", lambda repo: False)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github/repository.toml").write_text(CONFIG, encoding="utf-8")
    (tmp_path / ".github/labels.toml").write_text(LABELS, encoding="utf-8")
    return tmp_path


def run(github: FakeGitHub, root: Path, *arguments: str) -> int:
    return cli.main(list(arguments), api=Api(github), root=root)


def set_secrets(github: FakeGitHub) -> None:
    github.environments["release"]["secrets"] = ["RELEASE_AUTOMATION_PRIVATE_KEY"]


# --------------------------------------------------------------------------- settings


def test_check_reports_every_difference(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(github, root, "settings", "check") == 1

    out = capsys.readouterr().out
    for setting in (
        "repository.description",
        "repository.topics",
        "security.dependabot_alerts",
        "security.secret_scanning_push_protection",
        "actions.sha_pinning_required",
        "actions.fork_pr_approval",
        "security.immutable_releases",
        "ruleset Protect main",
        "ruleset Release tags",
        "variable PUBLISH_TO",
        "variable RELEASE_AUTOMATION_CLIENT_ID",
        "environment release",
        "secret RELEASE_AUTOMATION_PRIVATE_KEY of release",
        "label release",
        "label good first issue",
    ):
        assert setting in out
    assert 'pages: GitHub has "off", the configuration wants "on"' in out
    assert (
        "gh secret set RELEASE_AUTOMATION_PRIVATE_KEY --env release --repo Dennis-Otto/demo"
        in out
    )
    assert "settings apply" in out
    assert not any(method != "GET" for method, _ in github.calls)


def test_apply_sets_everything_but_the_secrets(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(github, root, "settings", "apply") == 1

    out = capsys.readouterr().out
    assert "secret RELEASE_AUTOMATION_PRIVATE_KEY of release" in out
    assert "repository.description" not in out
    assert "settings apply sets" not in out
    # Sorted, as GitHub shows them.
    assert github.repo["topics"] == ["a", "b"]
    assert github.switches == dict.fromkeys(github.switches, True)
    assert github.permissions == {
        "enabled": True,
        "allowed_actions": "selected",
        "sha_pinning_required": True,
    }
    assert github.fork_approval == "all_external_contributors"
    assert github.labels["release"] == {
        "color": "5319e7",
        "description": "The release PR",
    }
    assert github.labels["good first issue"] == {
        "color": "7057ff",
        "description": "Good for newcomers",
    }
    # A label of GitHub that the configuration doesn't name stays.
    assert "spare" in github.labels
    assert [
        (item["name"], item["type"]) for item in github.environments["pypi"]["branches"]
    ] == [("main", "branch")]
    assert github.pages is not None
    assert github.pages["build_type"] == "workflow"
    # Alerts before the security updates, which need them.
    puts = [path for method, path in github.calls if method == "PUT"]
    assert puts.index(f"repos/{REPO}/vulnerability-alerts") < puts.index(
        f"repos/{REPO}/automated-security-fixes"
    )

    set_secrets(github)
    assert run(github, root, "settings", "check") == 0
    assert "match .github/repository.toml" in capsys.readouterr().out


def test_a_refused_part_does_not_stop_the_others(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    variable = f"repos/{REPO}/actions/variables/RELEASE_AUTOMATION_CLIENT_ID"
    github.fail[("PATCH", variable)] = 403

    assert run(github, root, "settings", "apply") == 2

    # The parts after the refused one are applied all the same.
    assert github.pages is not None
    assert github.labels["release"]["color"] == "5319e7"
    err = capsys.readouterr().err
    assert "the variables could not be applied: GitHub answered 403" in err
    assert "the permission Variables (read and write)" in err


def test_a_refused_part_without_a_permission_hint(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    github.fail[("POST", f"repos/{REPO}/pages")] = 422

    assert run(github, root, "settings", "apply") == 2

    err = capsys.readouterr().err
    assert "the pages could not be applied: GitHub answered 422" in err
    assert "permission" not in err


def test_apply_without_drift_changes_nothing(github: FakeGitHub, root: Path) -> None:
    run(github, root, "settings", "apply")
    set_secrets(github)
    github.calls.clear()

    assert run(github, root, "settings", "apply") == 0
    assert all(method == "GET" for method, _ in github.calls)


def test_apply_updates_existing_rulesets_and_environments(
    github: FakeGitHub, root: Path
) -> None:
    run(github, root, "settings", "apply")
    set_secrets(github)
    main_id = next(
        key for key, value in github.rulesets.items() if value["name"] == "Protect main"
    )
    github.rulesets[main_id]["rules"] = [
        rule for rule in github.rulesets[main_id]["rules"] if rule["type"] != "deletion"
    ]
    github.rulesets[main_id]["rules"].append({"type": "creation"})
    github.environments["release"]["branches"].append(
        {"id": 99, "name": "v*", "type": "tag"}
    )

    assert run(github, root, "settings", "check") == 1
    assert run(github, root, "settings", "apply") == 0
    assert {"type": "deletion"} in github.rulesets[main_id]["rules"]
    assert [item["name"] for item in github.environments["release"]["branches"]] == [
        "main"
    ]


def test_settings_can_be_switched_off(github: FakeGitHub, root: Path) -> None:
    config = CONFIG.replace(
        "dependabot_alerts = true", "dependabot_alerts = false"
    ).replace("secret_scanning = true", "secret_scanning = false")
    (root / ".github/repository.toml").write_text(config, encoding="utf-8")
    github.switches["vulnerability-alerts"] = True
    github.repo["security_and_analysis"]["secret_scanning"] = {"status": "enabled"}

    run(github, root, "settings", "apply")

    assert github.switches["vulnerability-alerts"] is False
    assert github.repo["security_and_analysis"]["secret_scanning"] == {
        "status": "disabled"
    }


def test_only_the_workflow_permissions_change(github: FakeGitHub, root: Path) -> None:
    github.permissions["sha_pinning_required"] = True
    run(github, root, "settings", "apply")

    assert ("PUT", f"repos/{REPO}/actions/permissions") not in github.calls
    assert github.workflow == {
        "default_workflow_permissions": "read",
        "can_approve_pull_request_reviews": False,
    }


def test_only_sha_pinning_changes(github: FakeGitHub, root: Path) -> None:
    github.workflow = {
        "default_workflow_permissions": "read",
        "can_approve_pull_request_reviews": False,
    }
    run(github, root, "settings", "apply")

    assert ("PUT", f"repos/{REPO}/actions/permissions/workflow") not in github.calls


def test_a_repository_without_permissions_data(github: FakeGitHub, root: Path) -> None:
    github.fail[("GET", f"repos/{REPO}/actions/permissions")] = 404
    drift = check_actions(Api(github), REPO, {"sha_pinning_required": True})

    assert drift == [Drift("actions.sha_pinning_required", True, False)]


def test_ruleset_differences_name_each_part() -> None:
    want = main_ruleset(["a", "b"])
    have = json.loads(json.dumps(want))
    have["enforcement"] = "evaluate"
    rules = {rule["type"]: rule for rule in have["rules"]}
    rules["pull_request"]["parameters"]["required_approving_review_count"] = 1
    rules["required_status_checks"]["parameters"]["required_status_checks"] = [
        {"context": "a"}
    ]
    del have["rules"][0]
    have["rules"].append({"type": "update"})

    assert ruleset_differences(want, have) == [
        "enforcement",
        "rule deletion is missing",
        "pull_request.required_approving_review_count",
        "required_status_checks.required_status_checks",
        "rule update is extra",
    ]


def test_a_ruleset_without_its_bypass_list_matches() -> None:
    # A token without the administration write permission, such as the release
    # app's in the Settings workflow, gets the rulesets without bypass_actors.
    want = main_ruleset(["a"])
    have = json.loads(json.dumps(want))
    del have["bypass_actors"]
    assert ruleset_differences(want, have) == []

    have["bypass_actors"] = [{"actor_type": "OrganizationAdmin"}]
    assert ruleset_differences(want, have) == ["bypass_actors"]


def test_the_tag_ruleset_leaves_major_tags_free() -> None:
    ruleset = tag_ruleset()

    assert ruleset["conditions"]["ref_name"]["include"] == ["refs/tags/v*.*.*"]


def test_an_environment_without_main_drifts(github: FakeGitHub) -> None:
    github.environments["release"] = {
        "policy": MAIN_ONLY,
        "branches": [{"id": 5, "name": "main"}],
        "secrets": [],
    }
    api = Api(github)

    assert check_environments(api, REPO, {"release": {}}) == []
    github.environments["release"]["policy"] = {
        "protected_branches": True,
        "custom_branch_policies": False,
    }
    github.environments["release"]["branches"] = []
    assert check_environments(api, REPO, {"release": {}}) == [
        Drift(
            "environment release",
            "main only",
            {"protected_branches": True, "custom_branch_policies": False},
        )
    ]


def test_pages_that_build_from_a_branch_switch_to_the_workflow(
    github: FakeGitHub, root: Path
) -> None:
    # A site of the old kind, built by GitHub from a branch, publishes no website of
    # the Docs workflow.
    github.pages = {"build_type": "legacy", "source": {"branch": "gh-pages"}}

    assert run(github, root, "settings", "check") == 1
    run(github, root, "settings", "apply")

    assert github.pages["build_type"] == "workflow"
    assert ("PUT", f"repos/{REPO}/pages") in github.calls
    assert ("POST", f"repos/{REPO}/pages") not in github.calls


def test_pages_that_match_stay_as_they_are(github: FakeGitHub) -> None:
    github.pages = {"build_type": "workflow", "html_url": "https://x/"}
    api = Api(github)

    assert check_pages(api, REPO, {"build_type": "workflow"}) == []
    apply_pages(api, REPO, {"build_type": "workflow"}, [])
    assert all(method == "GET" for method, _ in github.calls)


def test_a_repository_without_pages_settings_leaves_them_alone(
    github: FakeGitHub,
) -> None:
    assert check_pages(Api(github), REPO, {}) == []
    assert github.calls == []


# --------------------------------------------------------------------------- the API


def test_errors_of_github_stop_the_run(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    github.fail[("GET", f"repos/{REPO}")] = 403

    assert run(github, root, "settings", "check") == 2
    assert "GitHub answered 403" in capsys.readouterr().err


def test_an_error_without_json() -> None:
    def runner(
        arguments: Sequence[str], body: str | None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            arguments, 1, "HTTP/2.0 502 Bad Gateway\n\n<html>", ""
        )

    with pytest.raises(GitHubError, match="502"):
        Api(runner).get("repos/x")


def test_output_without_a_status_line() -> None:
    def runner(
        arguments: Sequence[str], body: str | None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(arguments, 1, "", "gh: not logged in")

    with pytest.raises(GitHubError, match="not logged in"):
        Api(runner).get("repos/x")


def test_a_deeply_nested_answer_is_text() -> None:
    def runner(
        arguments: Sequence[str], body: str | None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            arguments, 0, "HTTP/2.0 200 OK\n\n" + "[" * 100_000, ""
        )

    response = Api(runner).request("GET", "repos/x")

    assert response.status == 200
    assert response.data.startswith("[[[")


def test_a_failing_graphql_query() -> None:
    def runner(
        arguments: Sequence[str], body: str | None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            arguments, 1, "", "GraphQL: Could not resolve"
        )

    with pytest.raises(GitHubError, match="Could not resolve"):
        Api(runner).graphql("{ viewer { login } }")


def test_a_folder_without_a_repository(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def runner(
        arguments: Sequence[str], body: str | None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(arguments, 1, "", "no git remotes")

    assert cli.main(["settings", "check"], api=Api(runner), root=root) == 2
    assert "--repo OWNER/NAME" in capsys.readouterr().err


def test_a_missing_configuration(
    github: FakeGitHub, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(github, tmp_path, "--repo", REPO, "settings", "check") == 2
    assert "repository.toml" in capsys.readouterr().err


# --------------------------------------------------------------------------- checklist


def test_the_checklist_of_a_new_repository(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (root / ".github/FUNDING.yml").write_text(
        "github: [Dennis-Otto]\n", encoding="utf-8"
    )

    assert run(github, root, "checklist") == 1

    out = capsys.readouterr().out
    assert "✘ Settings as code applied" in out
    assert "✘ Secrets of the environments set" in out
    assert "gh secret set RELEASE_AUTOMATION_PRIVATE_KEY" in out
    assert "· Settings → General → Features: Sponsorships on" in out
    assert "✘ Social preview uploaded" in out
    assert "✘ OpenSSF Best Practices badge" in out
    assert "Trusted publisher on PyPI" in out


def test_the_checklist_of_a_finished_repository(
    github: FakeGitHub,
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run(github, root, "settings", "apply")
    set_secrets(github)
    github.og_image = True
    (root / "README.md").write_text(
        "[![Best](https://www.bestpractices.dev/projects/1/badge)]\n", encoding="utf-8"
    )
    monkeypatch.setattr(blueprint.checklist, "reuse_compliant", lambda repo: True)
    capsys.readouterr()

    assert run(github, root, "checklist") == 0

    out = capsys.readouterr().out
    assert "✔ Settings as code applied" in out
    assert "Sponsorships" not in out
    assert "✔ Registered with the REUSE API" in out


@pytest.mark.parametrize(
    ("target", "text"),
    [
        ("npm", "Trusted publisher on npm"),
        ("ghcr", "package of the image is public"),
        ("hacs", "HACS default repositories"),
        ("nextcloud-appstore", "App certificate"),
        ("none", None),
    ],
)
def test_the_checklist_names_the_delivery(
    github: FakeGitHub, root: Path, target: str, text: str | None
) -> None:
    settings = Settings.load(root / ".github/repository.toml")
    settings.variables["PUBLISH_TO"] = target

    steps = checklist(Api(github), REPO, settings, root, reuse=lambda repo: False)

    texts = [step.text for step in steps]
    if text is None:
        assert len(texts) == 7
    else:
        assert any(text in step for step in texts)


def opener(body: bytes | Exception) -> Callable[[str], Any]:
    def open_url(url: str) -> Any:
        assert url == "https://api.reuse.software/status/github.com/Dennis-Otto/demo"
        if isinstance(body, Exception):
            raise body
        return io.BytesIO(body)

    return open_url


def test_the_reuse_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.undo()
    assert reuse_compliant(REPO, opener(b'{"status": "compliant"}'))
    assert not reuse_compliant(REPO, opener(b'{"status": "non-compliant"}'))
    assert not reuse_compliant(REPO, opener(b"<html>"))
    assert not reuse_compliant(REPO, opener(urllib.error.URLError("offline")))


def test_a_repository_without_labels_toml(tmp_path: Path) -> None:
    (tmp_path / "repository.toml").write_text(CONFIG, encoding="utf-8")

    assert Settings.load(tmp_path / "repository.toml").labels == {}


def test_merge_adds_the_settings_of_the_project() -> None:
    base: dict[str, Any] = {
        "branch": {"required_checks": ["a", "b"]},
        "variables": {"X": "1"},
    }
    extra = {
        "branch": {"required_checks": ["b", "c"]},
        "variables": {"X": "2", "Y": "3"},
        "environments": {"deploy": {"secrets": ["KEY"]}},
    }

    assert merge(base, extra) == {
        "branch": {"required_checks": ["a", "b", "c"]},
        "variables": {"X": "2", "Y": "3"},
        "environments": {"deploy": {"secrets": ["KEY"]}},
    }
    assert base["branch"]["required_checks"] == ["a", "b"]


def test_the_settings_of_the_project_join_the_checks(root: Path) -> None:
    (root / ".github/repository.project.toml").write_text(
        '[branch]\nrequired_checks = ["e2e"]\n', encoding="utf-8"
    )

    settings = Settings.load(root / ".github/repository.toml")

    main = settings.rulesets[0]["rules"]
    checks = next(rule for rule in main if rule["type"] == "required_status_checks")
    contexts = [
        item["context"] for item in checks["parameters"]["required_status_checks"]
    ]
    assert contexts == ["check (python)", "reuse", "e2e"]


def test_the_output_is_utf8_where_it_can_be(monkeypatch: pytest.MonkeyPatch) -> None:
    # A StringIO has no reconfigure; a console of Windows gets UTF-8 for the marks.
    monkeypatch.setattr("sys.stdout", io.StringIO())
    monkeypatch.setattr("sys.stderr", io.StringIO())
    cli.utf8_output()


def test_a_gap_in_the_community_profile_is_reported(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    github.community = {
        "health_percentage": 71,
        "description": None,
        "files": {
            "readme": {"url": "x"},
            "code_of_conduct": None,
            "issue_template": None,
        },
    }

    assert run(github, root, "settings", "apply") == 1

    out = capsys.readouterr().out
    assert "community profile: GitHub has 71, the configuration wants 100" in out
    assert (
        "add code_of_conduct, issue_template, description: "
        "https://github.com/Dennis-Otto/demo/community" in out
    )


def test_a_profile_without_its_files_names_what_it_counts(github: FakeGitHub) -> None:
    github.community = {"health_percentage": 85, "description": "A demo"}

    (drift,) = check_community(Api(github), REPO)

    assert drift.manual == (
        "add what the profile counts: https://github.com/Dennis-Otto/demo/community"
    )
