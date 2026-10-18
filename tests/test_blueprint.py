"""Tests of blueprint.py against a simulated GitHub."""

from __future__ import annotations

import base64
import io
import json
import re
import subprocess
import time
import urllib.error
import urllib.parse
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pytest

import blueprint.checklist
from blueprint import cli
from blueprint.checklist import best_practices, checklist, reuse_compliant
from blueprint.github import Api, GitHubError
from blueprint.settings import (
    MAIN_ONLY,
    ConfigError,
    Drift,
    Settings,
    allows,
    apply_labels,
    apply_pages,
    check_actions,
    check_community,
    check_environments,
    check_labels,
    check_pages,
    check_security,
    code_scanning_tools,
    load_labels,
    main_ruleset,
    merge,
    references,
    ruleset_differences,
    tag_creation_ruleset,
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


# The rules of a ruleset that GitHub knows, each with the parameters it may have.
RULES: dict[str, set[str]] = {
    "creation": set(),
    "update": {"update_allows_fetch_and_merge"},
    "deletion": set(),
    "non_fast_forward": set(),
    "required_linear_history": set(),
    "required_signatures": set(),
    "required_deployments": {"required_deployment_environments"},
    "pull_request": {
        "allowed_merge_methods",
        "automatic_copilot_code_review_enabled",
        "dismiss_stale_reviews_on_push",
        "require_code_owner_review",
        "require_last_push_approval",
        "required_approving_review_count",
        "required_review_thread_resolution",
        "required_reviewers",
    },
    "required_status_checks": {
        "do_not_enforce_on_create",
        "required_status_checks",
        "strict_required_status_checks_policy",
    },
    "code_scanning": {"code_scanning_tools"},
}
# The thresholds of a tool of code scanning that GitHub knows.
ALERTS = {"none", "errors", "errors_and_warnings", "all"}
SECURITY_ALERTS = {"none", "critical", "high_or_higher", "medium_or_higher", "all"}
CODEQL = {
    "tool": "CodeQL",
    "alerts_threshold": "errors",
    "security_alerts_threshold": "high_or_higher",
}
ACTOR_TYPES = {
    "Integration",
    "OrganizationAdmin",
    "RepositoryRole",
    "Team",
    "DeployKey",
}


def ruleset_problems(body: Any) -> list[str]:
    """What GitHub would refuse in a ruleset that blueprint.py sends, as its 422 says."""
    problems = []
    extra = set(body) - {
        "name",
        "target",
        "enforcement",
        "bypass_actors",
        "conditions",
        "rules",
    }
    if extra:
        problems.append(f"unknown fields {sorted(extra)}")
    if not isinstance(body.get("name"), str) or not body["name"]:
        problems.append("a ruleset needs a name")
    if body.get("target") not in ("branch", "tag", "push"):
        problems.append(f"target {body.get('target')!r}")
    if body.get("enforcement") not in ("active", "evaluate", "disabled"):
        problems.append(f"enforcement {body.get('enforcement')!r}")
    for actor in body.get("bypass_actors", []):
        if (
            not isinstance(actor.get("actor_id"), int)
            or actor.get("actor_type") not in ACTOR_TYPES
            or actor.get("bypass_mode") not in ("always", "pull_request", "exempt")
        ):
            problems.append(f"bypass actor {actor}")
    ref_name = body.get("conditions", {}).get("ref_name", {})
    prefix = {"branch": "refs/heads/", "tag": "refs/tags/"}.get(body.get("target"), "")
    for key in ("include", "exclude"):
        patterns = ref_name.get(key)
        if not isinstance(patterns, list) or not all(
            isinstance(pattern, str)
            and (pattern in ("~DEFAULT_BRANCH", "~ALL") or pattern.startswith(prefix))
            for pattern in patterns
        ):
            problems.append(f"conditions.ref_name.{key} {patterns!r}")
    types = [rule.get("type") for rule in body.get("rules", [])]
    if len(types) != len(set(types)):
        problems.append(f"a rule twice in {types}")
    for rule in body.get("rules", []):
        known = RULES.get(rule.get("type"))
        parameters = rule.get("parameters", {})
        if known is None:
            problems.append(f"rule {rule.get('type')!r}")
        elif set(rule) - {"type", "parameters"} or set(parameters) - known:
            problems.append(f"the parameters of {rule['type']}: {sorted(parameters)}")
        elif known and "parameters" not in rule and rule["type"] != "update":
            problems.append(f"rule {rule['type']} without its parameters")
    for rule in body.get("rules", []):
        parameters = rule.get("parameters", {})
        if rule.get("type") == "pull_request":
            methods = parameters.get("allowed_merge_methods", [])
            count = parameters.get("required_approving_review_count", 0)
            if not methods or set(methods) - {"merge", "squash", "rebase"}:
                problems.append(f"allowed_merge_methods {methods!r}")
            if not isinstance(count, int) or not 0 <= count <= 10:
                problems.append(f"required_approving_review_count {count!r}")
        if rule.get("type") == "code_scanning":
            for tool in parameters.get("code_scanning_tools", []):
                if (
                    not isinstance(tool.get("tool"), str)
                    or tool.get("alerts_threshold") not in ALERTS
                    or tool.get("security_alerts_threshold") not in SECURITY_ALERTS
                ):
                    problems.append(f"code scanning tool {tool}")
        if rule.get("type") == "required_status_checks":
            for check in parameters.get("required_status_checks", []):
                if not isinstance(check.get("context"), str) or not isinstance(
                    check.get("integration_id", 0), int
                ):
                    problems.append(f"required status check {check}")
        for key, value in parameters.items():
            if key.startswith(("dismiss_", "require_", "do_not_", "strict_")) and not (
                isinstance(value, bool)
            ):
                problems.append(f"{rule['type']}.{key} is no boolean: {value!r}")
    return problems


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
                "secret_scanning_non_provider_patterns": {"status": "disabled"},
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
        # The list of the selected actions, which GitHub keeps while they are allowed.
        self.selected: dict[str, Any] = {
            "github_owned_allowed": False,
            "verified_allowed": True,
            "patterns_allowed": [],
        }
        # The files of other repositories, such as actions: by owner/repo/path@ref.
        self.contents: dict[str, str] = {}
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
        # Labels that another workflow creates right before blueprint.py does.
        self.racing: dict[str, dict[str, str]] = {}
        self.next_id = 1
        self.calls: list[tuple[str, str]] = []
        # The requests that fail: with their status, or their status and message.
        self.fail: dict[tuple[str, str], int | tuple[int, str]] = {}

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
        if "--paginate" in arguments:
            return self.all_pages(arguments)
        method, path = arguments[3], arguments[4]
        self.calls.append((method, path))
        payload = json.loads(body) if body else None
        status, data = self.answer(method, path, payload)
        if method == "GET" and status < 400 and isinstance(data, list):
            # One page, as GitHub answers a request without --paginate.
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(path).query)
            size = int(query.get("per_page", ["30"])[0])
            page = int(query.get("page", ["1"])[0])
            data = data[(page - 1) * size : page * size]
        text = "" if data is None else json.dumps(data)
        return subprocess.CompletedProcess(
            arguments,
            0 if status < 400 else 1,
            f"HTTP/2.0 {status} X\r\nA: b\r\n\r\n{text}",
            "",
        )

    def answer(self, method: str, path: str, payload: Any) -> tuple[int, Any]:
        failure = self.fail.get((method, path))
        if failure is not None:
            status, message = (
                failure
                if isinstance(failure, tuple)
                else (failure, "simulated failure")
            )
            return status, {"message": message}
        content = re.fullmatch(
            r"repos/([\w.-]+/[\w.-]+)/contents/([^?]+)\?ref=(.*)", path
        )
        if content and content[1] != REPO:
            return self.content(*content.groups())
        return self.route(
            method, path.split("?")[0].removeprefix(f"repos/{REPO}"), payload
        )

    def all_pages(self, arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
        """gh api --paginate --slurp: every page of a list, in one list."""
        path = arguments[-1]
        self.calls.append(("GET", path))
        status, data = self.answer("GET", path, None)
        if status >= 400:
            return subprocess.CompletedProcess(
                arguments,
                1,
                json.dumps([data]),
                f"gh: {data['message']} (HTTP {status})",
            )
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(path).query)
        size = int(query["per_page"][0])
        if isinstance(data, list):
            pages = [data[start : start + size] for start in range(0, len(data), size)]
        else:
            pages = [data]
        return subprocess.CompletedProcess(arguments, 0, json.dumps(pages or [[]]), "")

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
            (r"/actions/permissions/selected-actions", self.selected_actions),
            (r"/actions/permissions", self.actions_permissions),
            (r"/rulesets(?:/(\d+))?", self.ruleset),
            (r"/actions/variables(?:/(\w+))?", self.variable),
            (r"/environments/([\w-]+)", self.environment),
            (r"/labels(?:/(.+))?", self.label),
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

    def selected_actions(self, method: str, body: Any) -> tuple[int, Any]:
        if self.permissions["allowed_actions"] != "selected":
            return 409, {"message": "The policy for allowed actions isn't selected"}
        if method == "PUT":
            self.selected.update(body)
            return 204, None
        return 200, self.selected

    def content(self, repo: str, path: str, ref: str) -> tuple[int, Any]:
        """A file of another repository, as the contents API answers it."""
        key = f"{repo}/{urllib.parse.unquote(path)}@{urllib.parse.unquote(ref)}"
        if key not in self.contents:
            return 404, {"message": "Not Found"}
        text = base64.b64encode(self.contents[key].encode()).decode()
        return 200, {"type": "file", "encoding": "base64", "content": text}

    def ruleset(self, method: str, body: Any, number: str | None) -> tuple[int, Any]:
        if method == "GET" and number is None:
            return 200, [
                {"id": key, "name": value["name"]}
                for key, value in self.rulesets.items()
            ]
        if method == "GET":
            return 200, self.rulesets[int(number or 0)]
        if method == "DELETE":
            del self.rulesets[int(number or 0)]
            return 204, None
        problems = ruleset_problems(body)
        if problems:
            return 422, {"message": "Invalid request.", "errors": problems}
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
        """GitHub ignores the case of the name of a label, also in its path."""
        if method == "GET":
            return 200, [{"name": name, **label} for name, label in self.labels.items()]
        if method == "POST":
            # The Labels workflow, which the same push started, was a moment quicker.
            if body["name"] in self.racing:
                self.labels[body["name"]] = self.racing.pop(body["name"])
            if self.named(body["name"]) is not None:
                return 422, {
                    "message": "Validation Failed",
                    "errors": [
                        {"resource": "Label", "code": "already_exists", "field": "name"}
                    ],
                }
        else:
            # The name in the path is encoded: a slash would make it another path.
            assert quoted is not None
            assert "/" not in quoted, quoted
            current = self.named(urllib.parse.unquote(quoted))
            if current is None:
                return 404, {"message": "Not Found"}
            del self.labels[current]
            # GitHub renames a label only through new_name, and ignores name.
            assert "name" not in body, body
            body = {**body, "name": body.get("new_name", current)}
        self.labels[body["name"]] = {
            "color": body["color"],
            "description": body["description"],
        }
        return 200, body

    def named(self, name: str) -> str | None:
        """The name of the label of that name, in the case that GitHub has."""
        return next(
            (label for label in self.labels if label.casefold() == name.casefold()),
            None,
        )

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


def test_a_write_that_github_answers_with_404_is_refused_with_the_hint(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # GitHub answers 404, not 403, to a token that lacks the permission for some writes.
    github.fail[("POST", f"repos/{REPO}/actions/variables")] = 404

    assert run(github, root, "settings", "apply") == 2

    err = capsys.readouterr().err
    assert "the variables could not be applied: GitHub answered 404" in err
    assert "the permission Variables (read and write)" in err


def test_a_rate_limit_is_no_missing_permission(
    github: FakeGitHub,
    root: Path,
    capsys: pytest.CaptureFixture[str],
    waits: list[float],
) -> None:
    variable = f"repos/{REPO}/actions/variables/RELEASE_AUTOMATION_CLIENT_ID"
    github.fail[("PATCH", variable)] = (403, "API rate limit exceeded for user ID 1.")

    assert run(github, root, "settings", "apply") == 2

    err = capsys.readouterr().err
    assert "the variables could not be applied: GitHub answered 403" in err
    assert "rate limit of GitHub; the next run tries again" in err
    assert "permission" not in err
    # It waited once, for a minute, and tried again.
    assert github.calls.count(("PATCH", variable)) == 2
    assert waits == [60]


def test_labels_beyond_the_first_page_are_found(github: FakeGitHub, root: Path) -> None:
    github.labels = {
        f"spare {number}": {"color": "ffffff", "description": ""}
        for number in range(150)
    }
    # Last in the list, on the second page.
    github.labels["release"] = {"color": "5319E7", "description": "The release PR"}
    want = load_labels(root / ".github/labels.toml")

    assert check_labels(Api(github), REPO, {"release": want["release"]}) == []


def test_a_label_in_another_case_is_renamed(github: FakeGitHub, root: Path) -> None:
    # GitHub ignores the case: creating release next to Release would fail.
    github.labels = {"Release": {"color": "5319e7", "description": "The release PR"}}
    want = {"release": load_labels(root / ".github/labels.toml")["release"]}
    api = Api(github)

    drift = check_labels(api, REPO, want)
    apply_labels(api, REPO, want, drift)

    assert drift == [
        Drift(
            "label release",
            "release #5319e7 The release PR",
            "Release #5319e7 The release PR",
        )
    ]
    assert github.labels == {
        "release": {"color": "5319e7", "description": "The release PR"}
    }
    assert ("PATCH", f"repos/{REPO}/labels/Release") in github.calls
    assert not any(method == "POST" for method, _ in github.calls)


def test_the_name_of_a_label_is_encoded_in_its_path(github: FakeGitHub) -> None:
    github.labels = {"area/docs": {"color": "000000", "description": "Old"}}
    want = {"area/docs": {"color": "0E8A16", "description": "The documentation"}}
    api = Api(github)

    apply_labels(api, REPO, want, check_labels(api, REPO, want))

    assert ("PATCH", f"repos/{REPO}/labels/area%2Fdocs") in github.calls
    assert github.labels["area/docs"] == {
        "color": "0e8a16",
        "description": "The documentation",
    }


def test_a_label_that_the_labels_workflow_created_a_moment_ago_is_updated(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The same push starts the Labels workflow, which creates the label first.
    github.racing["release"] = {"color": "5319E7", "description": "Older"}

    assert run(github, root, "settings", "apply") == 1

    assert "labels could not be applied" not in capsys.readouterr().err
    assert github.labels["release"] == {
        "color": "5319e7",
        "description": "The release PR",
    }
    assert ("PATCH", f"repos/{REPO}/labels/release") in github.calls


def test_a_label_that_github_refuses_is_reported(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    github.fail[("POST", f"repos/{REPO}/labels")] = 422

    assert run(github, root, "settings", "apply") == 2

    err = capsys.readouterr().err
    assert "the labels could not be applied: GitHub answered 422" in err
    assert "permission" not in err


def test_rulesets_beyond_the_first_page_are_found(
    github: FakeGitHub, root: Path
) -> None:
    run(github, root, "settings", "apply")
    set_secrets(github)
    # GitHub lists 30 rulesets on a page unless asked for more.
    managed = dict(github.rulesets)
    github.rulesets = {
        1000 + number: {"name": f"Other {number}"} for number in range(140)
    }
    github.rulesets.update(managed)
    github.calls.clear()

    assert run(github, root, "settings", "apply") == 0
    assert all(method == "GET" for method, _ in github.calls)


def test_the_order_of_the_rules_and_the_checks_is_no_difference() -> None:
    want = main_ruleset(["b", "a"])
    have = json.loads(json.dumps(main_ruleset(["a", "b"])))
    have["rules"].reverse()

    assert ruleset_differences(want, have) == []


RULESETS = Path(__file__).parent / "data/rulesets"


@pytest.mark.parametrize(
    ("fixture", "ruleset"),
    [
        ("protect-main.json", main_ruleset(["check (python)", "reuse"], [CODEQL])),
        ("release-tags.json", tag_ruleset()),
        ("release-tag-creation.json", tag_creation_ruleset(4739928)),
    ],
)
def test_the_rulesets_are_those_of_their_fixtures(
    fixture: str, ruleset: dict[str, Any]
) -> None:
    """The rulesets protect main and the release tags of every repository: a change of
    one changes its fixture in tests/data/rulesets/ too, on purpose."""
    expected = json.loads((RULESETS / fixture).read_text(encoding="utf-8"))

    assert ruleset == expected, f"change tests/data/rulesets/{fixture} on purpose"
    assert ruleset_problems(ruleset) == []


def test_the_simulated_github_refuses_rulesets_as_github_does() -> None:
    ruleset = main_ruleset(["a"])
    ruleset.update(target="ref", enforcement="on", name="", extra=1)
    ruleset["bypass_actors"] = [{"actor_id": "4", "actor_type": "App"}]
    ruleset["conditions"]["ref_name"] = {"include": ["main"], "exclude": "x"}
    rules = {rule["type"]: rule for rule in ruleset["rules"]}
    rules["pull_request"]["parameters"].update(
        allowed_merge_methods=["fast-forward"],
        required_approving_review_count=11,
        dismiss_stale_reviews_on_push="yes",
        unknown=True,
    )
    rules["required_status_checks"]["parameters"]["required_status_checks"] = [
        {"context": 1}
    ]
    ruleset["rules"] += [
        {"type": "deletion"},
        {"type": "squash"},
        {"type": "update", "x": 1},
    ]
    tag = tag_ruleset()
    tag["rules"].append({"type": "required_deployments"})

    assert len(ruleset_problems(ruleset)) == 14
    assert ruleset_problems(tag) == ["rule required_deployments without its parameters"]


def test_github_refuses_an_invalid_ruleset(github: FakeGitHub, root: Path) -> None:
    api = Api(github)

    with pytest.raises(GitHubError, match="422"):
        api.post(f"repos/{REPO}/rulesets", {**tag_ruleset(), "target": "release"})


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


# --------------------------------------------------------------------------- merge gates

SELECTED = """
allowed_actions = "selected"

[actions.selected]
github_owned_allowed = true
verified_allowed = false
patterns_allowed = ["step-security/harden-runner@*", "vendor/composite@*"]
"""
WORKFLOW = """
jobs:
  check:
    steps:
      - uses: step-security/harden-runner@0123 # v2
      - name: Check out
        uses: actions/checkout@4567
      - uses: ./.github/actions/local
      - uses: 'docker://alpine:3@sha256:00'
"""


def with_selected_actions(root: Path, workflow: str = WORKFLOW) -> None:
    """The configuration with the selected actions, and a workflow that runs some."""
    config = CONFIG.replace(
        'fork_pr_approval = "all_external_contributors"\n',
        'fork_pr_approval = "all_external_contributors"\n' + SELECTED,
    )
    (root / ".github/repository.toml").write_text(config, encoding="utf-8")
    (root / ".github/workflows").mkdir(exist_ok=True)
    (root / ".github/workflows/ci.yml").write_text(workflow, encoding="utf-8")


def test_a_new_alert_of_code_scanning_stops_the_merge() -> None:
    ruleset = main_ruleset(["a"], [CODEQL])

    assert ruleset["rules"][-1] == {
        "type": "code_scanning",
        "parameters": {"code_scanning_tools": [CODEQL]},
    }
    assert ruleset_problems(ruleset) == []
    # Without a tool, no rule.
    assert "code_scanning" not in [
        rule["type"] for rule in main_ruleset(["a"])["rules"]
    ]


def test_the_order_of_the_tools_of_code_scanning_is_no_difference() -> None:
    zizmor = {**CODEQL, "tool": "zizmor"}
    want = main_ruleset(["a"], [CODEQL, zizmor])
    have = json.loads(json.dumps(main_ruleset(["a"], [zizmor, CODEQL])))
    assert ruleset_differences(want, have) == []

    have["rules"][-1]["parameters"]["code_scanning_tools"][0]["alerts_threshold"] = (
        "all"
    )
    assert ruleset_differences(want, have) == ["code_scanning.code_scanning_tools"]
    have["rules"].pop()
    assert ruleset_differences(want, have) == ["rule code_scanning is missing"]


def test_a_tool_of_the_project_replaces_that_of_the_blueprint(root: Path) -> None:
    config = CONFIG.replace(
        'required_checks = ["check (python)", "reuse"]\n',
        'required_checks = ["check (python)", "reuse"]\ncode_scanning_tools = [\n'
        '  { tool = "CodeQL", alerts_threshold = "errors",'
        ' security_alerts_threshold = "high_or_higher" },\n]\n',
    )
    (root / ".github/repository.toml").write_text(config, encoding="utf-8")
    # While main still has alerts to fix, CodeQL stops no merge; zizmor joins.
    (root / ".github/repository.project.toml").write_text(
        "[branch]\ncode_scanning_tools = [\n"
        '  { tool = "CodeQL", alerts_threshold = "none",'
        ' security_alerts_threshold = "none" },\n'
        '  { tool = "zizmor", alerts_threshold = "errors",'
        ' security_alerts_threshold = "medium_or_higher" },\n]\n',
        encoding="utf-8",
    )

    settings = Settings.load(root / ".github/repository.toml")

    assert settings.rulesets[0]["rules"][-1]["parameters"]["code_scanning_tools"] == [
        {
            "tool": "CodeQL",
            "alerts_threshold": "none",
            "security_alerts_threshold": "none",
        },
        {
            "tool": "zizmor",
            "alerts_threshold": "errors",
            "security_alerts_threshold": "medium_or_higher",
        },
    ]


def test_apply_sets_the_rule_of_code_scanning(github: FakeGitHub, root: Path) -> None:
    config = CONFIG.replace(
        'required_checks = ["check (python)", "reuse"]\n',
        'required_checks = ["check (python)", "reuse"]\ncode_scanning_tools = [\n'
        '  { tool = "CodeQL", alerts_threshold = "errors",'
        ' security_alerts_threshold = "high_or_higher" },\n]\n',
    )
    (root / ".github/repository.toml").write_text(config, encoding="utf-8")

    run(github, root, "settings", "apply")

    main = next(
        item for item in github.rulesets.values() if item["name"] == "Protect main"
    )
    assert main["rules"][-1] == {
        "type": "code_scanning",
        "parameters": {"code_scanning_tools": [CODEQL]},
    }


@pytest.mark.parametrize(
    "tool",
    [
        "CodeQL",
        {"tool": "CodeQL"},
        {**CODEQL, "tool": ""},
        {**CODEQL, "security_alerts_threshold": "high"},
        {**CODEQL, "alerts_threshold": "warnings"},
        {**CODEQL, "extra": True},
    ],
)
def test_a_tool_of_code_scanning_without_its_thresholds_stops_the_run(
    tool: Any,
) -> None:
    with pytest.raises(ConfigError, match="names a tool and its thresholds") as error:
        code_scanning_tools([tool])

    assert "high_or_higher, medium_or_higher" in str(error.value)
    assert repr(tool) in str(error.value)


def test_generic_secret_patterns_are_switched_on(
    github: FakeGitHub, root: Path
) -> None:
    config = CONFIG.replace(
        "secret_scanning_push_protection = true\n",
        "secret_scanning_push_protection = true\n"
        "secret_scanning_non_provider_patterns = true\n",
    )
    (root / ".github/repository.toml").write_text(config, encoding="utf-8")

    run(github, root, "settings", "apply")

    analysis = github.repo["security_and_analysis"]
    assert analysis["secret_scanning_non_provider_patterns"] == {"status": "enabled"}
    assert analysis["secret_scanning"] == {"status": "enabled"}


def test_a_switch_that_github_does_not_offer_is_named_and_left_alone(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = CONFIG.replace(
        "secret_scanning_push_protection = true\n",
        "secret_scanning_push_protection = true\n"
        "secret_scanning_non_provider_patterns = true\n",
    )
    (root / ".github/repository.toml").write_text(config, encoding="utf-8")
    del github.repo["security_and_analysis"]["secret_scanning_non_provider_patterns"]

    assert run(github, root, "settings", "apply") == 1

    out = capsys.readouterr().out
    assert (
        "security.secret_scanning_non_provider_patterns: GitHub has"
        ' "not offered", the configuration wants true'
    ) in out
    assert (
        f"GitHub doesn't offer secret_scanning_non_provider_patterns for {REPO}; set"
        " secret_scanning_non_provider_patterns = false in"
        " .github/repository.project.toml"
    ) in out
    # The other switches come on all the same, and the one that isn't offered stays out.
    analysis = github.repo["security_and_analysis"]
    assert analysis["secret_scanning"] == {"status": "enabled"}
    assert "secret_scanning_non_provider_patterns" not in analysis

    # Switched off in the configuration, it is no difference.
    (root / ".github/repository.toml").write_text(
        config.replace("patterns = true", "patterns = false"), encoding="utf-8"
    )
    capsys.readouterr()
    run(github, root, "settings", "check")
    assert "non_provider_patterns" not in capsys.readouterr().out


def test_switches_that_the_token_cannot_read_are_off(github: FakeGitHub) -> None:
    del github.repo["security_and_analysis"]

    drift = check_security(Api(github), REPO, {"secret_scanning": True})

    assert drift == [Drift("security.secret_scanning", True, False)]


def test_only_the_selected_actions_may_run(github: FakeGitHub, root: Path) -> None:
    with_selected_actions(root)
    github.permissions["allowed_actions"] = "all"

    drift = check_actions(
        Api(github),
        REPO,
        Settings.load(root / ".github/repository.toml").actions,
    )
    assert [
        item.setting
        for item in drift
        if item.setting.startswith(("actions.allowed", "actions.selected"))
    ] == [
        "actions.allowed_actions",
        "actions.selected.github_owned_allowed",
        "actions.selected.verified_allowed",
        "actions.selected.patterns_allowed",
    ]

    run(github, root, "settings", "apply")

    assert github.permissions == {
        "enabled": True,
        "allowed_actions": "selected",
        "sha_pinning_required": True,
    }
    assert github.selected == {
        "github_owned_allowed": True,
        "verified_allowed": False,
        "patterns_allowed": ["step-security/harden-runner@*", "vendor/composite@*"],
    }
    # The list after the switch to the selected actions, which it needs.
    puts = [path for method, path in github.calls if method == "PUT"]
    assert puts.index(f"repos/{REPO}/actions/permissions") < puts.index(
        f"repos/{REPO}/actions/permissions/selected-actions"
    )
    settings = Settings.load(root / ".github/repository.toml")
    assert check_actions(Api(github), REPO, settings.actions, settings.workflows) == []


def test_the_order_of_the_patterns_is_no_difference(github: FakeGitHub) -> None:
    # GitHub ignores the case of owners and repositories, too.
    github.selected = {"patterns_allowed": ["B@*", "a@*"]}

    drift = check_actions(
        Api(github),
        REPO,
        {
            "allowed_actions": "selected",
            "selected": {"patterns_allowed": ["a@*", "b@*"]},
        },
    )

    assert drift == []


def test_an_action_that_the_list_lacks_keeps_the_list_as_it_is(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with_selected_actions(root, WORKFLOW + "      - uses: Rogue/Action@89ab\n")
    github.permissions["allowed_actions"] = "all"

    assert run(github, root, "settings", "apply") == 1

    out = capsys.readouterr().out
    assert "actions.selected.patterns_allowed lacks Rogue/Action@*" in out
    assert (
        '.github/workflows/ci.yml runs it: add "Rogue/Action@*" to patterns_allowed of'
        " [actions.selected] in .github/repository.project.toml; until then the list"
        " of the allowed actions on GitHub only grows"
    ) in out
    # Every action may still run, and the other settings of the actions are applied.
    assert github.permissions == {
        "enabled": True,
        "allowed_actions": "all",
        "sha_pinning_required": True,
    }
    assert ("PUT", f"repos/{REPO}/actions/permissions/selected-actions") not in (
        github.calls
    )

    # Once the project lists it, the list comes.
    (root / ".github/repository.project.toml").write_text(
        '[actions.selected]\npatterns_allowed = ["rogue/action@*"]\n', encoding="utf-8"
    )
    assert run(github, root, "settings", "apply") == 1
    assert github.permissions["allowed_actions"] == "selected"
    assert "rogue/action@*" in github.selected["patterns_allowed"]


def test_an_action_that_the_list_lacks_still_lets_the_active_list_grow(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with_selected_actions(root, WORKFLOW + "      - uses: Rogue/Action@89ab\n")
    github.selected = {
        "github_owned_allowed": True,
        "verified_allowed": False,
        "patterns_allowed": ["Old/Action@*", "actions/checkout@*"],
    }

    assert run(github, root, "settings", "apply") == 1

    assert "lacks Rogue/Action@*" in capsys.readouterr().out
    # The configured patterns come in addition, and none that GitHub had goes away.
    assert github.selected == {
        "github_owned_allowed": True,
        "verified_allowed": False,
        "patterns_allowed": [
            "Old/Action@*",
            "actions/checkout@*",
            "step-security/harden-runner@*",
            "vendor/composite@*",
        ],
    }
    assert github.permissions["allowed_actions"] == "selected"

    # Nothing new to add: no write.
    github.calls.clear()
    assert run(github, root, "settings", "apply") == 1
    assert ("PUT", f"repos/{REPO}/actions/permissions/selected-actions") not in (
        github.calls
    )


def test_an_action_that_an_action_runs_in_turn_needs_its_pattern(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with_selected_actions(
        root,
        WORKFLOW
        + "      - uses: vendor/composite@abc\n"
        + "  reuse:\n    uses: vendor/flows/.github/workflows/scan.yml@def\n",
    )
    (root / "action.yml").write_text("runs:\n  using: node24\n", encoding="utf-8")
    (root / ".github/actions/local").mkdir(parents=True)
    (root / ".github/actions/local/action.yml").write_text(
        "runs:\n  steps:\n    - uses: vendor/composite@abc\n", encoding="utf-8"
    )
    github.contents = {
        # A composite action that runs another, a local one, one of GitHub and one
        # that the workflow names already.
        "vendor/composite/action.yml@abc": (
            "runs:\n  using: composite\n  steps:\n"
            "    - uses: helper/setup/sub@1\n    - uses: ./x\n"
            "    - uses: actions/cache@2\n"
            "    - uses: step-security/harden-runner@0123\n"
        ),
        # An action whose file is action.yaml.
        "helper/setup/sub/action.yaml@1": "runs:\n  using: node24\n",
        # A reusable workflow, whose job runs an action that may not run.
        "vendor/flows/.github/workflows/scan.yml@def": (
            "jobs:\n  scan:\n    steps:\n      - uses: vendor/scanner@3\n"
        ),
    }

    assert run(github, root, "settings", "check") == 1

    out = capsys.readouterr().out
    assert "lacks helper/setup/sub@*" in out
    assert "vendor/composite runs it" in out
    assert "lacks vendor/flows/.github/workflows/scan.yml@*" in out
    assert "lacks vendor/scanner@*" in out
    assert "vendor/flows/.github/workflows/scan.yml runs it" in out
    # Those of GitHub, the listed ones and the local ones are no difference.
    assert "actions/cache" not in out
    assert "lacks vendor/composite" not in out
    assert "./x" not in out


def test_a_reference_is_read_in_the_characters_of_a_name() -> None:
    # The file of an action comes from GitHub; no Markdown of it reaches the summary.
    text = (
        'steps:\n  - uses: a/b@1`<img src=x>`\n  - uses: "c/d/e.yml@2" # v2\n'
        "    with:\n      uses: f/g@3\n  - run: echo uses: h/i@4\n"
    )

    assert references(text) == ["a/b@1", "c/d/e.yml@2", "f/g@3"]


def test_an_action_whose_file_github_refuses_keeps_the_list_as_it_is(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with_selected_actions(root, WORKFLOW + "      - uses: vendor/composite@abc\n")
    github.permissions["allowed_actions"] = "all"
    github.fail[("GET", "repos/vendor/composite/contents/action.yml?ref=abc")] = 403

    assert run(github, root, "settings", "apply") == 1

    out = capsys.readouterr().out
    assert "actions.selected.patterns_allowed unknown for vendor/composite@abc" in out
    assert "GitHub refused the file of vendor/composite@abc: GitHub answered 403" in out
    assert github.permissions["allowed_actions"] == "all"
    # The other settings are applied all the same.
    assert github.permissions["sha_pinning_required"] is True


@pytest.mark.parametrize(
    ("reference", "allowed"),
    [
        ("actions/checkout@1", True),
        ("GitHub/codeql-action/init@1", True),
        ("Docker/login-action@1", True),
        ("step-security/harden-runner@2", True),
        ("step-security/harden-runner-fork@2", False),
        ("actions/cache@3", False),
        ("anyone/else@4", False),
    ],
)
def test_the_patterns_follow_those_of_github(reference: str, allowed: bool) -> None:
    selected = {
        "github_owned_allowed": True,
        "patterns_allowed": [
            "docker/*",
            "step-security/harden-runner@*",
            "!actions/cache@*",
        ],
    }

    assert allows(selected, reference) is allowed
    # Without the actions of GitHub, only the patterns.
    assert not allows({"patterns_allowed": []}, "actions/checkout@1")


@pytest.mark.parametrize(
    ("actions", "message"),
    [
        ('allowed_actions = "some"\n', "allowed_actions of [actions] is one of all"),
        ('allowed_actions = "selected"\n', "needs the table [actions.selected]"),
    ],
)
def test_actions_that_may_run_as_github_knows_them(
    github: FakeGitHub,
    root: Path,
    capsys: pytest.CaptureFixture[str],
    actions: str,
    message: str,
) -> None:
    config = CONFIG.replace(
        'fork_pr_approval = "all_external_contributors"\n',
        'fork_pr_approval = "all_external_contributors"\n' + actions,
    )
    (root / ".github/repository.toml").write_text(config, encoding="utf-8")

    assert run(github, root, "settings", "check") == 2

    assert message in capsys.readouterr().err
    assert not github.calls


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


def test_only_the_release_app_creates_release_tags() -> None:
    creation = tag_creation_ruleset(4739928)

    assert creation["target"] == "tag"
    assert creation["enforcement"] == "active"
    assert creation["conditions"] == tag_ruleset()["conditions"]
    assert creation["rules"] == [{"type": "creation"}]
    assert creation["bypass_actors"] == [
        {"actor_id": 4739928, "actor_type": "Integration", "bypass_mode": "always"}
    ]
    # Release tags never move, not even for the app, which only creates them.
    tags = tag_ruleset()
    assert tags["bypass_actors"] == []
    assert [rule["type"] for rule in tags["rules"]] == [
        "deletion",
        "non_fast_forward",
        "update",
    ]


def with_app_id(root: Path, value: str = "4739928") -> Settings:
    """The settings with the App ID of the release app next to its Client ID."""
    path = root / ".github/repository.toml"
    path.write_text(
        CONFIG.replace(
            "[variables]\n", f'[variables]\nRELEASE_AUTOMATION_APP_ID = "{value}"\n'
        ),
        encoding="utf-8",
    )
    return Settings.load(path)


def test_the_settings_name_the_app_that_creates_release_tags(root: Path) -> None:
    # Without the App ID, the rulesets stay as they were: anyone who may push creates
    # release tags.
    without = Settings.load(root / ".github/repository.toml")
    assert [ruleset["name"] for ruleset in without.rulesets] == [
        "Protect main",
        "Release tags",
    ]

    settings = with_app_id(root)

    assert settings.rulesets == [*without.rulesets, tag_creation_ruleset(4739928)]
    assert settings.variables["RELEASE_AUTOMATION_APP_ID"] == "4739928"


def test_a_project_names_its_own_release_app(root: Path) -> None:
    (root / ".github/repository.project.toml").write_text(
        '[variables]\nRELEASE_AUTOMATION_APP_ID = " 12345 "\n', encoding="utf-8"
    )

    settings = with_app_id(root)

    assert settings.rulesets[-1] == tag_creation_ruleset(12345)


@pytest.mark.parametrize(
    ("own", "accepted"),
    [
        # The blueprint's app, named again: nothing of its own.
        ('RELEASE_AUTOMATION_CLIENT_ID = "Iv23client"', True),
        # An app of its own, with both of its IDs.
        (
            'RELEASE_AUTOMATION_CLIENT_ID = "Iv23own"\nRELEASE_AUTOMATION_APP_ID = "12345"',
            True,
        ),
        # An app of its own, as the README described it before the App ID.
        ('RELEASE_AUTOMATION_CLIENT_ID = "Iv23own"', False),
    ],
)
def test_a_release_app_of_its_own_needs_its_app_id(
    github: FakeGitHub,
    root: Path,
    capsys: pytest.CaptureFixture[str],
    own: str,
    accepted: bool,
) -> None:
    (root / ".github/repository.project.toml").write_text(
        f"[variables]\n{own}\n", encoding="utf-8"
    )

    if accepted:
        assert with_app_id(root).rulesets[-1]["name"] == "Release tag creation"
        return
    with pytest.raises(ConfigError):
        with_app_id(root)
    assert run(github, root, "settings", "check") == 2
    err = capsys.readouterr().err
    assert "set RELEASE_AUTOMATION_APP_ID there too" in err
    assert not github.calls


def creation_rulesets(github: FakeGitHub) -> list[dict[str, Any]]:
    return [
        ruleset
        for ruleset in github.rulesets.values()
        if ruleset["name"] == "Release tag creation"
    ]


def test_apply_lets_only_the_release_app_create_release_tags(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with_app_id(root)

    assert run(github, root, "settings", "check") == 1
    assert "ruleset Release tag creation" in capsys.readouterr().out
    run(github, root, "settings", "apply")

    assert creation_rulesets(github) == [tag_creation_ruleset(4739928)]
    assert github.variables["RELEASE_AUTOMATION_APP_ID"] == "4739928"

    # Another app among the exceptions is drift, which apply sets right.
    creation_rulesets(github)[0]["bypass_actors"][0]["actor_id"] = 1
    set_secrets(github)
    capsys.readouterr()
    assert run(github, root, "settings", "check") == 1
    out = capsys.readouterr().out
    assert 'ruleset Release tag creation: GitHub has "bypass_actors"' in out
    assert run(github, root, "settings", "apply") == 0
    assert creation_rulesets(github) == [tag_creation_ruleset(4739928)]


def test_without_the_app_id_the_rule_of_creation_goes(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with_app_id(root)
    run(github, root, "settings", "apply")
    set_secrets(github)
    # A ruleset of the maintainer's own, which the settings as code don't know.
    github.rulesets[99] = {"name": "Release branches", "target": "branch"}
    # A pull request takes the App ID out again.
    (root / ".github/repository.toml").write_text(CONFIG, encoding="utf-8")
    capsys.readouterr()

    assert run(github, root, "settings", "check") == 1
    out = capsys.readouterr().out
    assert (
        'ruleset Release tag creation: GitHub has "present", the configuration wants'
        ' "absent"'
    ) in out
    assert run(github, root, "settings", "apply") == 0

    assert creation_rulesets(github) == []
    assert sorted(ruleset["name"] for ruleset in github.rulesets.values()) == [
        "Protect main",
        "Release branches",
        "Release tags",
    ]


@pytest.mark.parametrize("value", ["Iv23client", "-1", "47 39"])
def test_an_app_id_that_is_no_number_stops_the_run(
    github: FakeGitHub,
    root: Path,
    capsys: pytest.CaptureFixture[str],
    value: str,
) -> None:
    with pytest.raises(ConfigError):
        with_app_id(root, value)

    assert run(github, root, "settings", "check") == 2

    err = capsys.readouterr().err
    assert "RELEASE_AUTOMATION_APP_ID must be the number of the release app" in err
    assert repr(value) in err
    assert not github.calls


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


def answers(
    *outputs: str, codes: Sequence[int] = ()
) -> tuple[Callable[..., subprocess.CompletedProcess[str]], list[list[str]]]:
    """A GitHub CLI that prints these outputs, one for each call, and the calls."""
    calls: list[list[str]] = []
    exits = list(codes) or [0] * len(outputs)

    def runner(
        arguments: Sequence[str], body: str | None
    ) -> subprocess.CompletedProcess[str]:
        index = len(calls)
        calls.append(list(arguments))
        stdout, _, stderr = outputs[index].partition("\x00")
        return subprocess.CompletedProcess(arguments, exits[index], stdout, stderr)

    return runner, calls


def http(status: int, body: Any = None, **headers: str) -> str:
    lines = [f"HTTP/2.0 {status} X"]
    lines += [f"{name.replace('_', '-')}: {value}" for name, value in headers.items()]
    return "\r\n".join(lines) + "\r\n\r\n" + ("" if body is None else json.dumps(body))


@pytest.mark.parametrize("method", ["PUT", "PATCH", "POST", "DELETE"])
def test_a_write_that_github_answers_with_404_failed(method: str) -> None:
    runner, _ = answers(http(404, {"message": "Not Found"}))

    with pytest.raises(GitHubError) as error:
        Api(runner).request(method, "repos/x/labels", {})

    assert error.value.status == 404
    assert str(error.value) == "GitHub answered 404: Not Found"


def test_a_read_or_a_delete_may_find_nothing() -> None:
    runner, calls = answers(*[http(404, {"message": "Not Found"})] * 3)
    api = Api(runner)

    assert api.get("repos/x/environments/pypi") is None
    assert api.exists("repos/x/vulnerability-alerts") is False
    api.delete("repos/x/issues/1/labels/merge-conflict", missing_ok=True)
    assert [call[3] for call in calls] == ["GET", "GET", "DELETE"]


def test_github_names_why_it_refused_the_fields() -> None:
    refusal = {
        "message": "Validation Failed",
        "errors": [{"resource": "Label", "code": "already_exists"}, "a text", {}],
    }
    runner, _ = answers(http(422, refusal))

    with pytest.raises(GitHubError) as error:
        Api(runner).post("repos/x/labels", {"name": "bug"})

    assert error.value.codes == ("already_exists",)


@pytest.mark.parametrize("status", [502, 503, 504])
def test_a_gateway_that_timed_out_is_asked_once_more(
    status: int, waits: list[float]
) -> None:
    runner, calls = answers(
        http(status, {"message": "Bad Gateway"}), http(200, {"id": 1})
    )

    assert Api(runner).get("repos/x") == {"id": 1}
    assert len(calls) == 2
    assert waits == [5]


def test_a_gateway_that_fails_twice_stops_the_request(waits: list[float]) -> None:
    runner, calls = answers(*[http(502, {"message": "Bad Gateway"})] * 2)

    with pytest.raises(GitHubError, match="502: Bad Gateway"):
        Api(runner).put("repos/x/topics", {"names": []})
    assert len(calls) == 2
    assert waits == [5]


def test_a_post_that_a_gateway_timed_out_is_not_sent_twice(
    waits: list[float],
) -> None:
    # GitHub has often opened the issue all the same: a second try would open two.
    runner, calls = answers(http(502, {"message": "Bad Gateway"}), http(201, {}))

    with pytest.raises(GitHubError, match="502: Bad Gateway"):
        Api(runner).post("repos/x/issues", {"title": "t"})
    assert len(calls) == 1
    assert waits == []


def test_a_run_stops_waiting_once_its_budget_is_spent(waits: list[float]) -> None:
    # A rate limit that outlasts the waits: each workflow of a sweep fails fast.
    limited = http(403, {"message": "You have exceeded a secondary rate limit."})
    runner, calls = answers(*[limited] * 5)
    api = Api(runner)

    for workflow in range(3):
        with pytest.raises(GitHubError, match="403"):
            api.get(f"repos/x/actions/workflows/{workflow}")
    assert waits == [60, 60]
    assert len(calls) == 5


@pytest.mark.parametrize(
    ("headers", "wait"),
    [
        # A secondary rate limit: at least a minute, or the time that GitHub names.
        ({}, 60),
        ({"retry_after": "17"}, 17),
        # The primary rate limit, used up: until it resets.
        ({"x_ratelimit_remaining": "0", "x_ratelimit_reset": "{soon}"}, 11),
        ({"x_ratelimit_remaining": "0", "x_ratelimit_reset": "0"}, 1),
    ],
)
def test_a_rate_limit_waits_before_the_one_more_try(
    headers: dict[str, str], wait: float, waits: list[float]
) -> None:
    soon = str(int(time.time()) + 10)
    headers = {key: value.format(soon=soon) for key, value in headers.items()}
    limited = http(
        403, {"message": "You have exceeded a secondary rate limit."}, **headers
    )
    runner, calls = answers(limited, http(201, {"id": 7}))

    Api(runner).post("repos/x/issues", {"title": "t"})

    assert len(calls) == 2
    assert waits == [pytest.approx(wait, abs=1)]


def test_a_line_of_the_headers_without_a_name_is_no_header(waits: list[float]) -> None:
    limited = http(429, {"message": "Rate limit"}).replace(
        "\r\n\r\n", "\r\nretry-after 3\r\n\r\n"
    )
    runner, _ = answers(limited, http(200, {}))

    Api(runner).get("repos/x")

    assert waits == [60]


@pytest.mark.parametrize(
    ("status", "message", "headers"),
    [
        # A permission that the token lacks: another try changes nothing.
        (403, "Resource not accessible by integration", {}),
        (429, "Too many requests", {}),
        # A rate limit that resets in an hour: not worth the wait.
        (
            403,
            "API rate limit exceeded for installation ID 1.",
            {"x_ratelimit_remaining": "0", "x_ratelimit_reset": "9999999999"},
        ),
        (429, "API rate limit exceeded", {"retry_after": "3600"}),
    ],
)
def test_an_answer_that_waiting_cannot_change_fails_at_once(
    status: int, message: str, headers: dict[str, str], waits: list[float]
) -> None:
    runner, calls = answers(http(status, {"message": message}, **headers))

    with pytest.raises(GitHubError, match=str(status)):
        Api(runner).patch("repos/x", {})
    assert len(calls) == 1
    assert waits == []


def test_every_page_of_a_list() -> None:
    pages = [[{"name": "a"}, {"name": "b"}], [{"name": "c"}]]
    runner, calls = answers(json.dumps(pages))

    assert Api(runner).get_all("repos/x/labels") == pages[0] + pages[1]
    assert calls == [
        [
            "api",
            "--method",
            "GET",
            "--paginate",
            "--slurp",
            "repos/x/labels?per_page=100",
        ]
    ]


def test_the_pages_of_a_list_in_a_field() -> None:
    pages = [
        {"total_count": 3, "workflow_runs": [{"id": 1}, {"id": 2}]},
        {"total_count": 3, "workflow_runs": [{"id": 3}]},
        "no page",
    ]
    runner, calls = answers(json.dumps(pages))

    found = Api(runner).get_all("repos/x/actions/runs?branch=main&per_page=50")

    assert found == [{"id": 1}, {"id": 2}, {"id": 3}]
    assert calls[0][-1] == "repos/x/actions/runs?branch=main&per_page=50"


def test_a_list_that_github_does_not_know_is_empty() -> None:
    runner, _ = answers(
        '[{"message": "Not Found", "status": "404"}]\x00gh: Not Found (HTTP 404)',
        codes=[1],
    )

    assert Api(runner).get_all("repos/x/environments/pypi/secrets") == []


def test_a_list_that_fails_on_a_gateway_is_read_once_more(waits: list[float]) -> None:
    runner, calls = answers(
        "\x00gh: Bad Gateway (HTTP 502)", json.dumps([[{"id": 1}]]), codes=[1, 0]
    )

    assert Api(runner).get_all("repos/x/rulesets") == [{"id": 1}]
    assert len(calls) == 2
    assert waits == [5]


@pytest.mark.parametrize(
    ("stdout", "stderr", "code", "error"),
    [
        ("", "gh: Resource not accessible by integration (HTTP 403)", 1, "403"),
        ("", "gh: not logged in", 1, "0: gh: not logged in"),
        # A GitHub CLI before 2.48.
        ("", "unknown flag: --slurp", 1, "needs GitHub CLI 2.48 or later"),
        # gh failed, whatever its message says.
        ("[]", "gh: unexpected end (HTTP 200)", 1, "200: gh: unexpected end"),
        ("not JSON", "", 0, "no list of pages"),
        ('{"a": 1}', "", 0, "no list of pages"),
        ("[" * 100_000, "", 0, "no list of pages"),
    ],
    ids=["refused", "no status", "old gh", "failed", "no JSON", "no list", "too deep"],
)
def test_a_list_that_can_not_be_read(
    stdout: str, stderr: str, code: int, error: str
) -> None:
    runner, _ = answers(f"{stdout}\x00{stderr}", codes=[code])

    with pytest.raises(GitHubError, match=re.escape(error)):
        Api(runner).get_all("repos/x/labels")


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
    assert "✔ Community profile complete (100 %)" in out
    assert "gh secret set RELEASE_AUTOMATION_PRIVATE_KEY" in out
    assert "· Settings → General → Features: Sponsorships on" in out
    assert "✘ Social preview uploaded" in out
    assert "✘ OpenSSF Best Practices badge" in out
    assert "✘ OpenSSF Baseline badge" in out
    # Without a project, the form of a new one, which reads .bestpractices.json.
    assert out.count("https://www.bestpractices.dev/en/projects/new") == 2
    assert "press 'Save (and continue) 🤖'" in out
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
        "[![Best](https://www.bestpractices.dev/projects/1/badge)]\n"
        "[![Baseline](https://www.bestpractices.dev/projects/1/baseline)]\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(blueprint.checklist, "reuse_compliant", lambda repo: True)
    capsys.readouterr()

    assert run(github, root, "checklist") == 0

    out = capsys.readouterr().out
    assert "✔ Settings as code applied" in out
    assert "✔ Secrets of the environments set" in out
    assert "✔ Community profile complete (100 %)" in out
    assert "Sponsorships" not in out
    assert "✔ Registered with the REUSE API" in out
    assert "✔ OpenSSF Best Practices badge in the README" in out
    assert "✔ OpenSSF Baseline badge in the README" in out


@pytest.mark.parametrize(
    ("readme", "done", "edit", "badge"),
    [
        (
            "[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/15284/badge)]",
            "Best Practices",
            "https://www.bestpractices.dev/en/projects/15284/baseline-1/edit",
            "[![OpenSSF Baseline](https://www.bestpractices.dev/projects/15284/baseline)]"
            "(https://www.bestpractices.dev/projects/15284)",
        ),
        (
            '<img src="https://www.bestpractices.dev/projects/7/baseline">',
            "Baseline",
            "https://www.bestpractices.dev/en/projects/7/passing/edit",
            "[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/7/badge)]"
            "(https://www.bestpractices.dev/projects/7)",
        ),
    ],
    ids=["metal", "baseline"],
)
def test_one_badge_of_openssf_best_practices_leads_to_the_other(
    readme: str, done: str, edit: str, badge: str
) -> None:
    steps = best_practices(f"# Demo\n\n{readme}\n")

    assert [step.done for step in steps] == [
        done == "Best Practices",
        done == "Baseline",
    ]
    # The project has its number: the form of the other series, and its badge.
    missing = next(step for step in steps if not step.done)
    assert missing.how.splitlines() == [
        edit,
        "On each level, press 'Save (and continue) 🤖' to take in the answers that"
        " .bestpractices.json proposes, and answer the rest.",
        f"Then add its badge to the README: {badge}",
    ]


def test_the_checklist_tells_secrets_and_the_community_profile_apart(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run(github, root, "settings", "apply")
    github.community = {
        "health_percentage": 85,
        "description": "A demo",
        "files": {"readme": {"url": "x"}, "license": None},
    }
    capsys.readouterr()

    assert run(github, root, "checklist") == 1

    lines = capsys.readouterr().out.splitlines()
    # Only what a person sets is left, which the API can't.
    assert "  ✔ Settings as code applied" in lines
    secrets = lines.index("  ✘ Secrets of the environments set")
    assert lines[secrets + 1].strip().startswith("gh secret set RELEASE_AUTOMATION")
    community = lines.index("  ✘ Community profile complete (100 %)")
    assert lines[community + 1].strip() == (
        "add license: https://github.com/Dennis-Otto/demo/community"
    )
    assert community == secrets + 2

    set_secrets(github)
    assert run(github, root, "checklist") == 1
    out = capsys.readouterr().out
    assert "✔ Secrets of the environments set" in out
    assert "✘ Community profile complete (100 %)" in out


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
        assert len(texts) == 9
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


def test_the_output_has_lf_line_endings_also_on_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A release section redirected into a file keeps the LF of the repository.
    raw = io.BytesIO()
    stdout = io.TextIOWrapper(raw, encoding="cp1252", newline="\r\n")
    monkeypatch.setattr("sys.stdout", stdout)
    monkeypatch.setattr("sys.stderr", io.StringIO())
    cli.utf8_output()
    stdout.write("## 1.0.0 ✓\n")
    stdout.flush()
    assert raw.getvalue() == "## 1.0.0 ✓\n".encode()


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
