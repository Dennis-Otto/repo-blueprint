"""Tests of blueprint.py against a simulated GitHub."""

from __future__ import annotations

import io
import json
import re
import runpy
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from email.message import Message
from pathlib import Path
from typing import Any

import preflight
import pytest
from shared import without_the_version

import blueprint.bootstrap
import blueprint.checklist
import blueprint.github
from blueprint import cli
from blueprint.checklist import (
    APP_NAME_LIMIT,
    BOT_TOOLS,
    RELEASE_APP_PERMISSIONS,
    Step,
    best_practices,
    bot_tools_allowed,
    change_answer,
    checklist,
    release_app_name,
    renovate,
    reuse_compliant,
    social_preview,
    social_preview_uploaded,
)
from blueprint.github import Api, GitHubError, Response
from blueprint.settings import (
    BATCH,
    MAIN_ONLY,
    ConfigError,
    Drift,
    Plan,
    Settings,
    actions_that_run,
    allows,
    apply_environments,
    apply_labels,
    apply_pages,
    apply_policies,
    check_actions,
    check_classic_protection,
    check_community,
    check_environments,
    check_labels,
    check_pages,
    check_security,
    code_scanning_tools,
    fitted,
    line_of,
    load_labels,
    main_ruleset,
    merge,
    read_plan,
    references,
    ruleset_differences,
    run_by,
    tag_creation_ruleset,
    tag_ruleset,
    workflow_events,
)

REPO = "Dennis-Otto/demo"
# The blueprint itself, whose workflows and README the tests read.
ROOT = Path(__file__).parents[1]
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
ZIZMOR = {
    "tool": "zizmor",
    "alerts_threshold": "all",
    "security_alerts_threshold": "all",
}
ACTOR_TYPES = {
    "Integration",
    "OrganizationAdmin",
    "RepositoryRole",
    "Team",
    "DeployKey",
}


# The events that an event rule of an Actions policy may allow, as GitHub's REST API
# names them (https://docs.github.com/en/rest/actions/policies).
POLICY_EVENTS = {
    "branch_protection_rule",
    "check_run",
    "check_suite",
    "create",
    "delete",
    "deployment",
    "deployment_status",
    "discussion",
    "discussion_comment",
    "fork",
    "gollum",
    "image_version",
    "issue_comment",
    "issues",
    "label",
    "merge_group",
    "milestone",
    "page_build",
    "project",
    "project_card",
    "project_column",
    "public",
    "pull_request",
    "pull_request_review",
    "pull_request_review_comment",
    "pull_request_target",
    "push",
    "registry_package",
    "release",
    "repository_dispatch",
    "schedule",
    "status",
    "watch",
    "workflow_call",
    "workflow_dispatch",
    "workflow_run",
}
# How GitHub answers a request of the policies of a private repository on GitHub Free,
# as it answered Dennis-Otto/pull-request-target-probe on 9 November 2026.
POLICIES_REFUSAL = (
    "Upgrade to GitHub Pro or make this repository public to enable this feature."
)


def policy_problems(body: Any, create: bool) -> list[str]:
    """What GitHub would refuse in an Actions policy that blueprint.py sends: a
    create needs its name and its enforcement, and every part has the form of the
    REST API."""
    problems = []
    if set(body) - {"name", "enforcement", "conditions", "rules"}:
        problems.append(f"the fields {sorted(body)}")
    if create and not isinstance(body.get("name"), str):
        problems.append(f"name {body.get('name')!r}")
    if (create or "enforcement" in body) and body.get("enforcement") not in (
        "disabled",
        "active",
        "evaluate",
    ):
        problems.append(f"enforcement {body.get('enforcement')!r}")
    # GitHub offers evaluate only with GitHub Enterprise.
    if body.get("enforcement") == "evaluate":
        problems.append("evaluate without GitHub Enterprise")
    path = body.get("conditions", {}).get("workflow_path")
    if "conditions" in body and (
        set(body["conditions"]) != {"workflow_path"}
        or set(path) != {"include", "exclude"}
        or not all(isinstance(item, str) for item in path["include"] + path["exclude"])
        or not path["include"] + path["exclude"]
        or "~ALL" in path["exclude"]
    ):
        problems.append(f"conditions {body['conditions']!r}")
    for rule in body.get("rules", []):
        events = rule.get("parameters", {}).get("allowed_events")
        if (
            rule.get("type") != "restrict_action_events"
            or set(rule) != {"type", "parameters"}
            or not isinstance(events, list)
            or set(events) - POLICY_EVENTS
        ):
            problems.append(f"rule {rule!r}")
    return problems


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
            "default_branch": "main",
            "has_wiki": True,
            "allow_update_branch": False,
            "security_and_analysis": {
                "secret_scanning": {"status": "disabled"},
                "secret_scanning_push_protection": {"status": "disabled"},
                "secret_scanning_non_provider_patterns": {"status": "disabled"},
            },
        }
        # The switches of security_and_analysis that the plan of the repository lacks:
        # GitHub answers their write with success and keeps them as they are.
        self.kept_off: set[str] = set()
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
        # The repositories whose files GraphQL refuses, with the type of its error;
        # "" refuses the whole query, as for its rate limit.
        self.refused_files: dict[str, str] = {}
        # The queries of GraphQL of the files of actions, by their variables.
        self.file_queries: list[dict[str, str]] = []
        self.fork_approval = "first_time_contributors"
        self.rulesets: dict[int, dict[str, Any]] = {}
        # The Actions policies of the repository, and one of its organization, which
        # the list names only with has_parents.
        self.policies: dict[int, dict[str, Any]] = {}
        self.parent_policies: list[dict[str, Any]] = []
        self.variables: dict[str, str] = {"RELEASE_AUTOMATION_CLIENT_ID": "outdated"}
        self.environments: dict[str, dict[str, Any]] = {}
        # The status with which GitHub refuses a write of an environment that names
        # the bypass of administrators, as a private repository without Enterprise
        # may answer 422; 0 when it doesn't.
        self.refuses_bypass = 0
        self.og_image = False
        # Where GitHub serves the social preview: the upload, or a card of its own.
        self.og_url = "https://opengraph.githubassets.com/1/Dennis-Otto/demo"
        # The kind of account of the owner: "User" or "Organization".
        self.account = "User"
        self.community: dict[str, Any] = {
            "health_percentage": 100,
            "description": "A demo",
            "files": {"readme": {"url": "x"}, "contributing": {"url": "x"}},
        }
        # Off, as in a new repository.
        self.pages: dict[str, Any] | None = None
        # A classic branch protection of main; none, as in a new repository.
        self.protection: dict[str, Any] | None = None
        # The open issues and pull requests, and the numbers of the bot users of apps.
        self.issues: list[dict[str, Any]] = []
        # The pull requests of every state, newest first, as GitHub answers them,
        # which a test may break.
        self.pulls: list[Any] = []
        # The paths of the workflows that GitHub has registered.
        self.workflows: list[str] = []
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
            repository = {
                "isPrivate": bool(self.repo.get("private")),
                "usesCustomOpenGraphImage": self.og_image,
                "openGraphImageUrl": self.og_url,
            }
            answer = {"data": {"repository": repository}}
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
        if (method, path) == ("POST", "graphql"):
            return self.files_of_actions(payload["query"], payload["variables"])
        if path == f"users/{REPO.split('/')[0]}":
            return 200, {"login": REPO.split("/")[0], "type": self.account}
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
            (r"/actions/policies(?:/(\d+))?", self.policy),
            (r"/actions/variables(?:/(\w+))?", self.variable),
            (r"/environments/([\w-]+)", self.environment),
            (r"/labels(?:/(.+))?", self.label),
            (
                r"/environments/([\w-]+)/deployment-branch-policies(?:/(\d+))?",
                self.branch_policy,
            ),
            (r"/environments/([\w-]+)/secrets", self.secrets),
            (r"/community/profile", self.community_profile),
            (r"/branches/main/protection", self.branch_protection),
            (r"/pages", self.pages_site),
            (r"/issues", self.issue_list),
            (r"/pulls", self.pull_list),
            (r"/actions/workflows", self.workflow_list),
        ):
            match = re.fullmatch(pattern, path)
            if match:
                result: tuple[int, Any] = handler(method, body, *match.groups())
                return result
        raise AssertionError(f"unexpected request {method} {path}")

    def issue_list(self, method: str, body: Any) -> tuple[int, Any]:
        return 200, self.issues

    def workflow_list(self, method: str, body: Any) -> tuple[int, Any]:
        known = [{"path": path} for path in self.workflows]
        return 200, {"total_count": len(known), "workflows": known}

    def pull_list(self, method: str, body: Any) -> tuple[int, Any]:
        return 200, self.pulls

    def community_profile(self, method: str, body: Any) -> tuple[int, Any]:
        return 200, self.community

    def branch_protection(self, method: str, body: Any) -> tuple[int, Any]:
        if self.protection is None:
            return 404, {"message": "Branch not protected"}
        return 200, self.protection

    def repository(self, method: str, body: Any) -> tuple[int, Any]:
        if method == "PATCH":
            for key, value in body.items():
                if key == "security_and_analysis":
                    self.repo[key].update(
                        (name, status)
                        for name, status in value.items()
                        if name not in self.kept_off
                    )
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

    def files_of_actions(
        self, query: str, variables: dict[str, str]
    ) -> tuple[int, Any]:
        """The files of other repositories, such as actions, that a query of GraphQL
        asks for by its variables, as GitHub answers it: a repository that it doesn't
        know is null, with an error of the type NOT_FOUND, and so is a file."""
        self.file_queries.append(variables)
        if "" in self.refused_files:
            error = {"type": self.refused_files[""], "message": "API rate limit"}
            return 200, {"data": None, "errors": [error]}
        data: dict[str, Any] = {}
        errors = []
        for key, owner in variables.items():
            if not (index := re.fullmatch(r"o(\d+)", key)):
                continue
            alias = f"r{index[1]}"
            # Every name of the query comes as a variable.
            assert f"{alias}: repository(owner: ${key}, name: $n{index[1]})" in query
            repo = f"{owner}/{variables[f'n{index[1]}']}"
            known = any(name.startswith(f"{repo}/") for name in self.contents)
            kind = self.refused_files.get(repo) or ("" if known else "NOT_FOUND")
            if kind:
                data[alias] = None
                message = f"{kind} for {repo}"
                errors.append({"type": kind, "path": [alias], "message": message})
                continue
            data[alias] = {}
            for name, place in variables.items():
                if file := re.fullmatch(rf"e{index[1]}_(\d+)", name):
                    ref, _, path = place.partition(":")
                    text = self.contents.get(f"{repo}/{path}@{ref}")
                    data[alias][f"f{file[1]}"] = (
                        None if text is None else {"text": text}
                    )
        return 200, {"data": data, **({"errors": errors} if errors else {})}

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

    def policy(self, method: str, body: Any, number: str | None) -> tuple[int, Any]:
        """The Actions policies, which GitHub offers a private repository only on a
        paid plan. The list names each policy by its id and name alone, and a policy
        that GitHub answers by its id has the fields of its own as well, as a public
        repository showed on 9 November 2026 (decision 0138)."""
        if self.repo.get("private"):
            return 403, {"message": POLICIES_REFUSAL}
        if method == "GET" and number is None:
            parents = "has_parents=false" not in self.calls[-1][1]
            own = [
                {"id": key, "name": value["name"]}
                for key, value in self.policies.items()
            ]
            listed = own + (self.parent_policies if parents else [])
            return 200, {"total_count": len(listed), "policies": listed}
        if number is not None and int(number) not in self.policies:
            return 404, {"message": "Not Found"}
        if method == "GET":
            return 200, {
                "id": int(number or 0),
                "target": "actions",
                "source_type": "Repository",
                **self.policies[int(number or 0)],
            }
        if method == "DELETE":
            del self.policies[int(number or 0)]
            return 204, None
        problems = policy_problems(body, create=method == "POST")
        if problems:
            return 422, {"message": "Invalid request.", "errors": problems}
        if method == "POST":
            self.policies[self.next_id] = body
            self.next_id += 1
            return 201, body
        self.policies[int(number or 0)].update(body)
        return 200, body

    def variable(self, method: str, body: Any, name: str | None) -> tuple[int, Any]:
        if method == "GET":
            if name in self.variables:
                return 200, {"name": name, "value": self.variables[name]}
            return 404, {"message": "Not Found"}
        self.variables[body["name"]] = body["value"]
        return 201, None

    def environment(self, method: str, body: Any, name: str) -> tuple[int, Any]:
        if method == "PUT" and self.refuses_bypass and "can_admins_bypass" in body:
            return self.refuses_bypass, {"message": "Invalid request."}
        if method == "PUT":
            environment = self.environments.setdefault(
                name, {"branches": [], "secrets": []}
            )
            environment["policy"] = body["deployment_branch_policy"]
            # GitHub lets administrators bypass the rules unless the write says no.
            environment["bypass"] = body.get("can_admins_bypass", True)
        if name not in self.environments:
            return 404, {"message": "Not Found"}
        answer = {
            "name": name,
            "deployment_branch_policy": self.environments[name]["policy"],
        }
        if "bypass" in self.environments[name]:
            answer["can_admins_bypass"] = self.environments[name]["bypass"]
        return 200, answer

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
    assert "python3 .github/blueprint.py app connect --key-file FILE" in out
    assert "gh secret set RELEASE_AUTOMATION_PRIVATE_KEY" not in out
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


def test_check_reports_a_default_branch_that_the_workflows_never_run_on(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    github.repo["default_branch"] = "master"

    assert run(github, root, "settings", "check") == 1

    out = capsys.readouterr().out
    assert 'default branch: GitHub has "master", the configuration wants "main"' in out
    assert (
        "the workflows expect main: rename master to main at "
        f"https://github.com/{REPO}/branches, then in each clone: "
        "git branch --move master main" in out
    )


def test_apply_leaves_the_renaming_of_the_default_branch_to_a_person(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    github.repo["default_branch"] = "master"
    run(github, root, "settings", "apply")
    set_secrets(github)
    capsys.readouterr()

    # Only the branch is left, which a person renames.
    assert run(github, root, "settings", "apply") == 1

    assert github.repo["default_branch"] == "master"
    out = capsys.readouterr().out.splitlines()
    assert out[1:] == [
        '  default branch: GitHub has "master", the configuration wants "main"',
        "      the workflows expect main: rename master to main at "
        f"https://github.com/{REPO}/branches, then in each clone: "
        "git branch --move master main && git fetch origin && "
        "git branch --set-upstream-to origin/main main",
    ]


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


@pytest.mark.parametrize(
    ("path", "part", "permissions"),
    [
        # GitHub writes an environment with Administration, not with Environments.
        ("environments/release", "environments", "permission Administration"),
        ("pages", "pages", "permissions Administration and Pages"),
    ],
)
def test_the_hint_names_each_permission_that_the_write_needs(
    github: FakeGitHub,
    root: Path,
    capsys: pytest.CaptureFixture[str],
    path: str,
    part: str,
    permissions: str,
) -> None:
    github.fail[("PUT", f"repos/{REPO}/{path}")] = 403
    github.fail[("POST", f"repos/{REPO}/{path}")] = 403

    assert run(github, root, "settings", "apply") == 2

    err = capsys.readouterr().err
    assert f"the {part} could not be applied: GitHub answered 403" in err
    assert f"the token may lack the {permissions} (read and write)" in err


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


@pytest.mark.parametrize("source", [{}, {"integration_id": 99999}])
def test_a_required_check_of_another_source_is_a_difference(
    source: dict[str, int],
) -> None:
    """Each required check of main is pinned to the app of GitHub Actions, so that no
    commit status of its name satisfies it: a check that accepts any source, or the
    checks of another app, differs, and the settings bot writes the pin back."""
    want = main_ruleset(["lint", "codeql"])
    have = json.loads(json.dumps(main_ruleset(["codeql", "lint"])))
    (checks,) = (
        rule["parameters"]["required_status_checks"]
        for rule in have["rules"]
        if rule["type"] == "required_status_checks"
    )
    checks[1] = {"context": checks[1]["context"], **source}

    assert ruleset_differences(want, have) == [
        "required_status_checks.required_status_checks"
    ]


RULESETS = Path(__file__).parent / "data/rulesets"


@pytest.mark.parametrize(
    ("fixture", "ruleset"),
    [
        (
            "protect-main.json",
            main_ruleset(["check (python)", "reuse"], [CODEQL, ZIZMOR]),
        ),
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
"""
# A step that runs an image of Docker, which GitHub counts as an action.
IMAGE = "      - uses: 'docker://alpine:3@sha256:00'\n"


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
    want = main_ruleset(["a"], [CODEQL, ZIZMOR])
    have = json.loads(json.dumps(main_ruleset(["a"], [ZIZMOR, CODEQL])))
    assert ruleset_differences(want, have) == []

    have["rules"][-1]["parameters"]["code_scanning_tools"][0]["alerts_threshold"] = (
        "errors"
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


# --------------------------------------------------------------------------- plan

# How GitHub refuses what the plan of a private repository lacks.
RULESETS_REFUSAL = (
    "Upgrade to GitHub Pro or make this repository public to enable this feature."
)
PAGES_REFUSAL = "Your current plan does not support GitHub Pages for this repository."


def with_code_scanning(root: Path, extra: str = "") -> None:
    """The settings with the rule of code scanning for CodeQL, and extra variables."""
    config = CONFIG.replace(
        'required_checks = ["check (python)", "reuse"]\n',
        'required_checks = ["check (python)", "reuse"]\ncode_scanning_tools = [\n'
        '  { tool = "CodeQL", alerts_threshold = "errors",'
        ' security_alerts_threshold = "high_or_higher" },\n]\n',
    ).replace('PUBLISH_TO = "pypi"\n', f'PUBLISH_TO = "pypi"\n{extra}')
    (root / ".github/repository.toml").write_text(config, encoding="utf-8")


def main_rules(github: FakeGitHub) -> list[str]:
    main = next(
        item for item in github.rulesets.values() if item["name"] == "Protect main"
    )
    return [rule["type"] for rule in main["rules"]]


def test_a_private_repository_without_code_security_switches_the_workflows_over(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with_code_scanning(root)
    github.repo["private"] = True

    run(github, root, "settings", "apply")

    # The workflows keep what they find out of code scanning, which GitHub doesn't
    # offer here, and the rule of main waits for no analysis of it.
    assert github.variables["CODE_SCANNING"] == "off"
    assert github.variables["DEPENDENCY_REVIEW"] == "off"
    assert "code_scanning" not in main_rules(github)
    # Their checks stay required: they still run, and pass without code scanning.
    assert "required_status_checks" in main_rules(github)
    set_secrets(github)
    capsys.readouterr()
    assert run(github, root, "settings", "apply") == 0
    assert f"The settings of {REPO} match" in capsys.readouterr().out


def test_a_public_repository_keeps_code_scanning_and_gets_no_variable_of_the_plan(
    github: FakeGitHub, root: Path
) -> None:
    with_code_scanning(root)
    github.repo["private"] = False

    run(github, root, "settings", "apply")

    assert "CODE_SCANNING" not in github.variables
    assert "DEPENDENCY_REVIEW" not in github.variables
    assert main_rules(github)[-1] == "code_scanning"


@pytest.mark.parametrize("product", ["advanced_security", "code_security"])
def test_a_private_repository_with_code_security_keeps_code_scanning(
    github: FakeGitHub, root: Path, product: str
) -> None:
    with_code_scanning(root)
    github.repo["private"] = True
    github.repo["security_and_analysis"][product] = {"status": "enabled"}

    run(github, root, "settings", "apply")

    assert "CODE_SCANNING" not in github.variables
    assert main_rules(github)[-1] == "code_scanning"


def test_the_variables_of_the_plan_turn_on_again_once_github_offers_it(
    github: FakeGitHub, root: Path
) -> None:
    # A repository that was private on GitHub Free, now public.
    github.variables.update(CODE_SCANNING="off", DEPENDENCY_REVIEW="on")

    run(github, root, "settings", "apply")

    assert github.variables["CODE_SCANNING"] == "on"
    assert github.variables["DEPENDENCY_REVIEW"] == "on"
    written = f"repos/{REPO}/actions/variables/DEPENDENCY_REVIEW"
    assert ("PATCH", written) not in github.calls


def test_a_variable_of_the_settings_as_code_wins_over_the_plan(
    github: FakeGitHub, root: Path
) -> None:
    with_code_scanning(root, 'CODE_SCANNING = "on"\n')
    github.repo["private"] = True

    run(github, root, "settings", "apply")

    assert github.variables["CODE_SCANNING"] == "on"
    assert github.variables["DEPENDENCY_REVIEW"] == "off"
    assert main_rules(github)[-1] == "code_scanning"


def test_a_token_that_may_not_read_the_security_decides_nothing(
    github: FakeGitHub, root: Path
) -> None:
    github.repo.update(private=True, security_and_analysis=None)
    with_code_scanning(root)
    settings = Settings.load(root / ".github/repository.toml", root)

    plan = read_plan(Api(github), REPO)

    assert plan == Plan(private=True, code_security=None)
    assert plan.offers_code_security is None
    assert fitted(Api(github), REPO, settings, plan) == settings
    assert Plan(private=False, code_security=None).offers_code_security is True


def test_what_the_plan_of_a_private_repository_lacks_fails_no_run(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    github.repo["private"] = True
    github.fail[("POST", f"repos/{REPO}/rulesets")] = (403, RULESETS_REFUSAL)
    github.fail[("POST", f"repos/{REPO}/pages")] = (422, PAGES_REFUSAL)
    run(github, root, "settings", "apply")
    set_secrets(github)
    capsys.readouterr()

    assert run(github, root, "settings", "apply") == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    assert f"The settings of {REPO} match .github/repository.toml." in captured.out
    assert "GitHub doesn't do this for the repository, which fails nothing:" in (
        captured.out
    )
    assert (
        'ruleset Protect main: GitHub has "missing", the configuration wants "present"'
    ) in captured.out
    assert 'pages: GitHub has "off", the configuration wants "on"' in captured.out
    assert (
        f"GitHub doesn't offer it to the private repository {REPO} on its plan and"
        f' answered "{PAGES_REFUSAL}"; the next run of the settings sets it once the'
        " repository is public or on a plan that offers it"
    ) in captured.out
    # The other parts are applied all the same.
    assert github.labels["release"]["color"] == "5319e7"


def test_rulesets_that_a_private_repository_cannot_read_are_a_notice(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    github.repo["private"] = True
    listing = f"repos/{REPO}/rulesets?per_page=100"
    github.fail[("GET", listing)] = (403, RULESETS_REFUSAL)
    run(github, root, "settings", "apply")
    set_secrets(github)
    capsys.readouterr()

    assert run(github, root, "settings", "apply") == 0

    out = capsys.readouterr().out
    assert (
        'rulesets: GitHub has "not offered", the configuration wants "present"'
    ) in out
    assert f'answered "{RULESETS_REFUSAL}"' in out


def test_a_refusal_of_the_rulesets_that_is_not_the_plan_still_fails(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    github.repo["private"] = True
    github.fail[("GET", f"repos/{REPO}/rulesets?per_page=100")] = 403

    assert run(github, root, "settings", "check") == 2

    assert "GitHub answered 403: simulated failure" in capsys.readouterr().err


def test_a_public_repository_fails_on_a_refusal_that_names_advanced_security(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Such as a policy of an organization: a public repository has every part.
    refusal = "Advanced Security is disabled by a policy of the enterprise."
    github.fail[("POST", f"repos/{REPO}/rulesets")] = (422, refusal)
    github.fail[("GET", f"repos/{REPO}/rulesets?per_page=100")] = (403, refusal)

    assert run(github, root, "settings", "check") == 2
    assert run(github, root, "settings", "apply") == 2

    assert refusal in capsys.readouterr().err


def test_the_checklist_of_a_private_repository_on_github_free(
    github: FakeGitHub,
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    github.repo["private"] = True
    github.fail[("POST", f"repos/{REPO}/rulesets")] = (403, RULESETS_REFUSAL)
    github.fail[("POST", f"repos/{REPO}/pages")] = (422, PAGES_REFUSAL)
    run(github, root, "settings", "apply")
    set_secrets(github)
    monkeypatch.setattr(blueprint.checklist, "reuse_compliant", lambda repo: True)
    capsys.readouterr()

    run(github, root, "checklist")

    out = capsys.readouterr().out
    # Only a write shows whether the plan lacks the rulesets and the website.
    assert "  · Settings as code applied" in out
    assert "it tells whether GitHub keeps ruleset Protect main, " in out
    assert (
        "  · Private repository: GitHub Code Security on, for code scanning and the"
        " dependency review"
    ) in out
    assert f"https://github.com/{REPO}/settings/security_analysis" in out

    github.repo["security_and_analysis"]["code_security"] = {"status": "enabled"}
    run(github, root, "checklist")
    assert "  ✔ Private repository: GitHub Code Security on" in (
        capsys.readouterr().out
    )


def test_secret_scanning_that_github_keeps_off_a_private_repository_fails_no_run(
    github: FakeGitHub,
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # GitHub offers secret scanning to a private repository only with GitHub Secret
    # Protection, and keeps it off without, as it keeps a public one's on.
    github.repo["private"] = True
    github.kept_off.update({"secret_scanning", "secret_scanning_push_protection"})
    run(github, root, "settings", "apply")
    set_secrets(github)
    capsys.readouterr()

    assert run(github, root, "settings", "apply") == 0

    out = capsys.readouterr().out
    assert (
        "GitHub accepted secret_scanning_push_protection = true for"
        f" {REPO} but keeps it off, likely because the plan of the repository lacks"
    ) in out
    monkeypatch.setattr(blueprint.checklist, "reuse_compliant", lambda repo: True)
    run(github, root, "checklist")
    assert "  · Settings as code applied" in capsys.readouterr().out


def test_secret_scanning_that_github_refuses_a_private_repository_is_a_notice(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    github.repo["private"] = True
    run(github, root, "settings", "apply")
    set_secrets(github)
    github.repo["security_and_analysis"]["secret_scanning"] = {"status": "disabled"}
    refusal = (
        "Advanced Security must be enabled for this repository to use secret scanning."
    )
    github.fail[("PATCH", f"repos/{REPO}")] = (422, refusal)
    capsys.readouterr()

    assert run(github, root, "settings", "apply") == 0

    out = capsys.readouterr().out
    assert (
        "security.secret_scanning: GitHub has false, the configuration wants true"
    ) in out
    assert f'answered "{refusal}"' in out


def test_the_checklist_of_a_public_repository_has_no_step_of_the_plan(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run(github, root, "checklist")

    assert "GitHub Code Security" not in capsys.readouterr().out


def generic_patterns(root: Path) -> str:
    """The configuration of the tests, with the generic patterns of secret scanning."""
    config = CONFIG.replace(
        "secret_scanning_push_protection = true\n",
        "secret_scanning_push_protection = true\n"
        "secret_scanning_non_provider_patterns = true\n",
    )
    (root / ".github/repository.toml").write_text(config, encoding="utf-8")
    return config


def test_generic_secret_patterns_are_switched_on(
    github: FakeGitHub, root: Path
) -> None:
    generic_patterns(root)

    run(github, root, "settings", "apply")

    analysis = github.repo["security_and_analysis"]
    assert analysis["secret_scanning_non_provider_patterns"] == {"status": "enabled"}
    assert analysis["secret_scanning"] == {"status": "enabled"}


def test_a_switch_that_github_does_not_offer_is_named_and_left_alone(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = generic_patterns(root)
    del github.repo["security_and_analysis"]["secret_scanning_non_provider_patterns"]
    run(github, root, "settings", "apply")
    set_secrets(github)
    capsys.readouterr()

    # A notice, which fails nothing.
    assert run(github, root, "settings", "apply") == 0

    out = capsys.readouterr().out
    assert f"The settings of {REPO} match .github/repository.toml." in out
    assert "GitHub doesn't do this for the repository, which fails nothing:" in out
    assert (
        "security.secret_scanning_non_provider_patterns: GitHub has"
        ' "not offered", the configuration wants true'
    ) in out
    assert (
        f"GitHub doesn't offer secret_scanning_non_provider_patterns for {REPO}; set"
        " secret_scanning_non_provider_patterns = false under [security] in"
        " .github/repository.project.toml to stop asking for it"
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


def test_a_switch_that_github_keeps_off_is_a_notice(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    generic_patterns(root)
    # A repository of a user: GitHub accepts the generic patterns and keeps them off.
    github.kept_off.add("secret_scanning_non_provider_patterns")
    run(github, root, "settings", "apply")
    set_secrets(github)
    capsys.readouterr()

    # Every run asks again, and GitHub keeps them off again.
    assert run(github, root, "settings", "apply") == 0

    out = capsys.readouterr().out
    assert f"The settings of {REPO} match .github/repository.toml." in out
    assert "GitHub doesn't do this for the repository, which fails nothing:" in out
    assert (
        "security.secret_scanning_non_provider_patterns: GitHub has false,"
        " the configuration wants true"
    ) in out
    assert (
        f"GitHub accepted secret_scanning_non_provider_patterns = true for {REPO} but"
        " keeps it off, likely because the plan of the repository lacks the switch; set"
        " secret_scanning_non_provider_patterns = false under [security] in"
        " .github/repository.project.toml to stop asking for it"
    ) in out
    # The other switches come on all the same.
    analysis = github.repo["security_and_analysis"]
    assert analysis["secret_scanning"] == {"status": "enabled"}
    assert analysis["secret_scanning_non_provider_patterns"] == {"status": "disabled"}


def test_push_protection_that_github_keeps_off_still_fails_the_run(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Only a switch that depends on the plan becomes a notice; secret scanning and
    its push protection are on every public repository, so GitHub keeping one off is
    a fault that someone has to see."""
    github.kept_off.add("secret_scanning_push_protection")
    run(github, root, "settings", "apply")
    set_secrets(github)
    capsys.readouterr()

    assert run(github, root, "settings", "apply") == 1

    out = capsys.readouterr().out
    differ, _, notices = out.partition("GitHub doesn't do this for the repository")
    assert "security.secret_scanning_push_protection: GitHub has false" in differ
    assert "secret_scanning_push_protection" not in notices


def test_a_switch_that_github_keeps_off_is_named_after_what_differs(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    generic_patterns(root)
    github.kept_off.add("secret_scanning_non_provider_patterns")

    # The secret of the release environment is missing, which only a person can set.
    assert run(github, root, "settings", "apply") == 1

    out = capsys.readouterr().out
    differ, _, notices = out.partition("GitHub doesn't do this for the repository")
    assert f"The settings of {REPO} differ from .github/repository.toml:" in differ
    assert "secret RELEASE_AUTOMATION_PRIVATE_KEY" in differ
    assert "non_provider_patterns" not in differ
    assert "GitHub accepted secret_scanning_non_provider_patterns" in notices


def test_a_switch_that_github_kept_off_still_differs_in_a_check(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Only a write shows that GitHub keeps a switch off; a check can't tell."""
    generic_patterns(root)
    github.kept_off.add("secret_scanning_non_provider_patterns")
    run(github, root, "settings", "apply")
    set_secrets(github)
    capsys.readouterr()

    assert run(github, root, "settings", "check") == 1

    out = capsys.readouterr().out
    assert "security.secret_scanning_non_provider_patterns: GitHub has false" in out
    assert (
        "python3 .github/blueprint.py settings apply sets what the API can set." in out
    )


def test_a_switch_whose_write_github_refused_is_no_notice(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    generic_patterns(root)
    github.fail[("PATCH", f"repos/{REPO}")] = 403

    assert run(github, root, "settings", "apply") == 2

    captured = capsys.readouterr()
    assert "the security could not be applied: GitHub answered 403" in captured.err
    assert "fails nothing" not in captured.out
    assert (
        "security.secret_scanning_non_provider_patterns: GitHub has false"
    ) in captured.out.partition("GitHub doesn't do")[0]


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


def test_widen_adds_only_the_patterns_that_the_list_lacks(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The blueprint bot, before it pushes an update that brings a new action: the
    # list grows by its patterns, and none that GitHub had goes away.
    with_selected_actions(root, WORKFLOW + "      - uses: Rogue/Action@89ab\n")
    github.selected = {
        "github_owned_allowed": True,
        "verified_allowed": False,
        "patterns_allowed": ["Old/Action@*", "STEP-SECURITY/harden-runner@*"],
    }

    assert run(github, root, "settings", "widen") == 0

    assert github.selected == {
        "github_owned_allowed": True,
        "verified_allowed": False,
        "patterns_allowed": [
            "Old/Action@*",
            "STEP-SECURITY/harden-runner@*",
            "vendor/composite@*",
        ],
    }
    assert capsys.readouterr().out == (
        f"GitHub now lets {REPO} start these patterns of .github/repository.toml as"
        " well:\n- vendor/composite@*\n"
    )
    # Only the list of the actions: no other setting, and no switch of the actions.
    writes = [(method, path) for method, path in github.calls if method != "GET"]
    assert writes == [("PUT", f"repos/{REPO}/actions/permissions/selected-actions")]

    # Nothing left to add: no write.
    github.calls.clear()
    assert run(github, root, "settings", "widen") == 0
    assert [method for method, _ in github.calls] == ["GET", "GET"]
    assert capsys.readouterr().out == (
        f"GitHub lets {REPO} start every pattern of [actions.selected] of"
        " .github/repository.toml.\n"
    )


def test_widen_leaves_a_repository_alone_that_lets_every_action_run(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with_selected_actions(root)
    github.permissions["allowed_actions"] = "all"

    assert run(github, root, "settings", "widen") == 0

    assert github.calls == [("GET", f"repos/{REPO}/actions/permissions")]
    assert "start every pattern of [actions.selected]" in capsys.readouterr().out


def test_widen_without_selected_actions_asks_github_nothing(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(github, root, "settings", "widen") == 0

    assert github.calls == []
    assert capsys.readouterr().out == (
        "[actions] of .github/repository.toml lists no selected actions to add to"
        " GitHub's.\n"
    )


def test_widen_fails_on_settings_that_conflict(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # An update whose settings have the markers of a conflict: the bot pushes the
    # update without a wider list, as it did before.
    (root / ".github/repository.toml").write_text(
        "<<<<<<< before updating\n" + CONFIG, encoding="utf-8"
    )

    assert run(github, root, "settings", "widen") == 2

    assert github.calls == []
    assert capsys.readouterr().err.startswith("blueprint.py: ")


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


def test_an_image_of_docker_stops_the_selected_actions(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # GitHub counts a docker:// step as an action and refuses it, whatever the list
    # names: the workflow fails to start (#279).
    with_selected_actions(
        root, WORKFLOW + IMAGE + "      - uses: vendor/composite@abc\n"
    )
    github.contents = {
        "vendor/composite/action.yml@abc": (
            "runs:\n  using: composite\n  steps:\n"
            "    - uses: docker://ghcr.io/vendor/tool:1@sha256:11\n"
        ),
    }
    github.permissions["allowed_actions"] = "all"

    assert run(github, root, "settings", "check") == 1

    out = capsys.readouterr().out
    assert (
        "  actions.allowed_actions refuses docker://alpine:3@sha256:00: GitHub has"
        ' "docker://", the configuration wants "docker run"\n'
        "      .github/workflows/ci.yml runs it, and GitHub refuses a step with"
        " docker:// unless every action may run, whatever [actions.selected] lists:"
        " run the image in a run: step instead, as docker run --rm --volume"
        ' "$PWD:/github/workspace" --workdir /github/workspace alpine:3@sha256:00'
        " with the step's with: args after it and its entrypoint as --entrypoint;"
        " until then the actions that may run on GitHub never narrow"
    ) in out
    # Also the image of a step of an action that a workflow runs.
    assert "refuses docker://ghcr.io/vendor/tool:1@sha256:11" in out
    assert "vendor/composite runs it, and GitHub refuses" in out
    # No pattern names an image, and GitHub has no file of it to read.
    assert "lacks docker" not in out
    assert "unknown for docker" not in out
    assert not [path for _, path in github.calls if "docker:" in path]

    # The switch to the selected actions would stop the workflow, so it waits.
    assert run(github, root, "settings", "apply") == 1
    assert github.permissions["allowed_actions"] == "all"
    assert ("PUT", f"repos/{REPO}/actions/permissions/selected-actions") not in (
        github.calls
    )


def test_an_image_of_docker_stops_the_actions_of_the_repository_alone(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = CONFIG.replace(
        'fork_pr_approval = "all_external_contributors"\n',
        'fork_pr_approval = "all_external_contributors"\n'
        'allowed_actions = "local_only"\n',
    )
    (root / ".github/repository.toml").write_text(config, encoding="utf-8")
    (root / ".github/workflows").mkdir(exist_ok=True)
    (root / ".github/workflows/ci.yml").write_text(WORKFLOW + IMAGE, encoding="utf-8")
    github.permissions["allowed_actions"] = "all"

    assert run(github, root, "settings", "apply") == 1

    out = capsys.readouterr().out
    assert "actions.allowed_actions refuses docker://alpine:3@sha256:00" in out
    assert ".github/workflows/ci.yml runs it" in out
    assert github.permissions["allowed_actions"] == "all"


def test_every_action_may_run_also_an_image_of_docker(
    github: FakeGitHub, root: Path
) -> None:
    (root / ".github/workflows").mkdir(exist_ok=True)
    (root / ".github/workflows/ci.yml").write_text(WORKFLOW + IMAGE, encoding="utf-8")
    settings = Settings.load(root / ".github/repository.toml")
    github.permissions["allowed_actions"] = "all"

    drift = check_actions(Api(github), REPO, settings.actions, settings.workflows)

    assert "docker://alpine:3@sha256:00" in settings.workflows
    assert [item.setting for item in drift if "docker" in item.setting] == []


def test_a_reference_is_read_in_the_characters_of_a_name() -> None:
    # The file of an action comes from GitHub; no Markdown of it reaches the summary.
    text = (
        'steps:\n  - uses: a/b@1`<img src=x>`\n  - uses: "c/d/e.yml@2" # v2\n'
        "    with:\n      uses: f/g@3\n  - run: echo uses: h/i@4\n"
        "  - uses: ./local\n  - uses: docker://alpine:3@sha256:00\n"
    )

    # Not those of the repository, which every policy allows, but every image.
    assert references(text) == [
        "a/b@1",
        "c/d/e.yml@2",
        "f/g@3",
        "docker://alpine:3@sha256:00",
    ]


def test_an_action_whose_file_github_refuses_keeps_the_list_as_it_is(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with_selected_actions(root, WORKFLOW + "      - uses: vendor/composite@abc\n")
    github.permissions["allowed_actions"] = "all"
    github.refused_files["vendor/composite"] = "FORBIDDEN"

    assert run(github, root, "settings", "apply") == 1

    out = capsys.readouterr().out
    assert "actions.selected.patterns_allowed unknown for vendor/composite@abc" in out
    assert (
        "GitHub refused the file of vendor/composite@abc: GitHub answered FORBIDDEN"
        in out
    )
    assert github.permissions["allowed_actions"] == "all"
    # The other settings are applied all the same.
    assert github.permissions["sha_pinning_required"] is True


# A composite action whose update runs an action that the list lacks, in turn.
COMPOSITE = {
    "vendor/composite/action.yml@abc": (
        "runs:\n  using: composite\n  steps:\n    - uses: helper/setup/sub@1\n"
        "    - uses: actions/cache@2\n"
    ),
}


def test_the_lint_finds_an_action_that_an_action_runs_in_turn_and_the_list_lacks(
    github: FakeGitHub,
    root: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    with_selected_actions(root, WORKFLOW + "      - uses: vendor/composite@abc\n")
    github.contents = dict(COMPOSITE)

    assert run(github, root, "settings", "actions") == 1

    out = capsys.readouterr().out
    message = (
        "helper/setup/sub@1: vendor/composite runs it in turn, from"
        " vendor/composite@abc that .github/workflows/ci.yml names; add"
        ' "helper/setup/sub@*" to patterns_allowed of [actions.selected] in'
        " .github/repository.project.toml"
    )
    assert f"- {message}\n" in out
    # At the line of the workflow that names what runs it, for the PR coach.
    assert (
        "::error file=.github/workflows/ci.yml,line=9,title=Allowed actions::"
        "helper/setup/sub@1: vendor/composite runs it in turn"
    ) in out
    # Those of GitHub and the listed ones are allowed.
    assert "actions/cache" not in out
    assert "- vendor/composite" not in out
    # From the files alone, with one query for each level, none of the settings.
    assert github.calls == [("POST", "graphql")] * 2


def test_the_lint_passes_when_the_list_allows_every_action_that_runs(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with_selected_actions(root, WORKFLOW + "      - uses: vendor/composite@abc\n")
    github.contents = dict(COMPOSITE)
    project = '[actions.selected]\npatterns_allowed = ["helper/setup/sub@*"]\n'
    (root / ".github/repository.project.toml").write_text(project, encoding="utf-8")

    assert run(github, root, "settings", "actions") == 0

    assert capsys.readouterr().out == (
        "GitHub starts every action that the workflows run, also those that these"
        " run in turn, by [actions] of .github/repository.toml, and every workflow"
        " that starts on pull_request_target.\n"
    )


def test_the_lint_names_an_unlisted_action_and_an_image_that_a_workflow_runs(
    github: FakeGitHub,
    root: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Outside a workflow, also when the tests themselves run in one.
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    with_selected_actions(root, WORKFLOW + "      - uses: other/tool@9\n" + IMAGE)
    # The blueprint lists the actions of every repository in its template.
    (root / "copier.yml").write_text("{}\n", encoding="utf-8")
    (root / "template").mkdir()

    assert run(github, root, "settings", "actions") == 1

    out = capsys.readouterr().out
    assert (
        "- other/tool@9: .github/workflows/ci.yml names it; add"
        ' "other/tool@*" to patterns_allowed of [actions.selected] in'
        " template/.github/repository.toml.jinja and .github/repository.toml\n"
    ) in out
    assert (
        "- docker://alpine:3@sha256:00: .github/workflows/ci.yml names it; run the"
        " image in a run: step instead, as docker run --rm"
    ) in out
    # Annotations only in a workflow.
    assert "::error" not in out


def test_the_lint_asks_for_the_list_where_only_local_actions_may_run(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with_selected_actions(root)
    config = root / ".github/repository.toml"
    text = config.read_text(encoding="utf-8")
    config.write_text(
        text.replace('allowed_actions = "selected"', 'allowed_actions = "local_only"'),
        encoding="utf-8",
    )

    assert run(github, root, "settings", "actions") == 1

    out = capsys.readouterr().out
    # Not even the actions of GitHub may run then.
    assert (
        "- actions/checkout@4567: .github/workflows/ci.yml names it; set"
        ' allowed_actions = "selected" in [actions] and add "actions/checkout@*"'
    ) in out


def test_the_lint_reads_nothing_when_every_action_may_run(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (root / ".github/workflows").mkdir()
    (root / ".github/workflows/ci.yml").write_text(WORKFLOW + IMAGE, encoding="utf-8")

    assert run(github, root, "settings", "actions") == 0

    assert "GitHub starts every action" in capsys.readouterr().out
    assert github.calls == []


@pytest.mark.parametrize(
    ("refuse", "answer"),
    [
        # GitHub refuses the repository of the action.
        ({"vendor/composite": "FORBIDDEN"}, "GitHub answered FORBIDDEN"),
        # Or the whole query, for its rate limit.
        ({"": "RATE_LIMITED"}, "GitHub answered RATE_LIMITED: API rate limit"),
    ],
    ids=["repository", "query"],
)
def test_the_lint_fails_when_github_refuses_the_file_of_an_action(
    github: FakeGitHub,
    root: Path,
    capsys: pytest.CaptureFixture[str],
    refuse: dict[str, str],
    answer: str,
) -> None:
    with_selected_actions(root, WORKFLOW + "      - uses: vendor/composite@abc\n")
    github.contents = dict(COMPOSITE)
    github.refused_files = refuse

    assert run(github, root, "settings", "actions") == 1

    out = capsys.readouterr().out
    assert "- vendor/composite@abc: .github/workflows/ci.yml names it; GitHub" in out
    assert f"refused its file ({answer}" in out
    assert "so what it runs in turn is unknown: run the check again\n" in out


def test_the_lint_fails_when_github_answers_no_query(
    github: FakeGitHub,
    root: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    with_selected_actions(root, WORKFLOW + "      - uses: vendor/composite@abc\n")
    github.fail[("POST", "graphql")] = 502

    assert run(github, root, "settings", "actions") == 1

    out = capsys.readouterr().out
    # Each action of the query, which a gateway timed out every time: a query only
    # reads, so it is asked again, three times.
    assert out.count("refused its file (GitHub answered 502: simulated failure)") == 3
    assert github.calls == [("POST", "graphql")] * 4


# --------------------------------------------------------------------------- policies

# Workflows of a repository: two that start on pull_request_target, one of them also on
# another event, and one that doesn't.
TITLE = """name: Pull request title
on:
  pull_request_target:
    types: [opened, edited]
  # By hand as well.
  workflow_dispatch:
jobs: {}
"""
WELCOME = "name: Welcome\non: pull_request_target\njobs: {}\n"
CHECKS = "name: CI\non: [push, pull_request]\njobs: {}\n"
LISTED = (
    'pull_request_target = [".github/workflows/title.yml",'
    ' ".github/workflows/welcome.yml"]\n'
)


def with_workflows(root: Path, listed: str = LISTED, **files: str) -> None:
    """The configuration, whose [actions] lists the workflows that may start on
    pull_request_target, and the workflows of the repository by their names."""
    config = CONFIG.replace(
        'fork_pr_approval = "all_external_contributors"\n',
        'fork_pr_approval = "all_external_contributors"\n' + listed,
    )
    (root / ".github/repository.toml").write_text(config, encoding="utf-8")
    folder = root / ".github/workflows"
    folder.mkdir(exist_ok=True)
    for path in folder.iterdir():
        path.unlink()
    workflows = files or {"title": TITLE, "welcome": WELCOME, "ci": CHECKS}
    for name, text in workflows.items():
        (folder / f"{name}.yml").write_text(text, encoding="utf-8")


def wanted_policy() -> dict[str, Any]:
    return {
        "name": "Allow pull_request_target",
        "enforcement": "active",
        "conditions": {
            "workflow_path": {
                "include": [
                    ".github/workflows/title.yml",
                    ".github/workflows/welcome.yml",
                ],
                "exclude": [],
            }
        },
        "rules": [
            {
                "type": "restrict_action_events",
                "parameters": {
                    "allowed_events": ["pull_request_target", "workflow_dispatch"]
                },
            }
        ],
    }


@pytest.mark.parametrize(
    ("text", "events"),
    [
        ("on: push\n", ["push"]),
        ("'on': \"push\" # quoted\n", ["push"]),
        ("on: [push, 'pull_request_target']\n", ["push", "pull_request_target"]),
        ("on: []\n", []),
        # Unfinished, as no workflow is: what stands there.
        ("on: [push, pull_request\n", ["push", "pull_request"]),
        # Over several lines, with a comment between them.
        (
            "on: [\n  push, # the main\n  pull_request_target\n]\njobs: {}\n",
            ["push", "pull_request_target"],
        ),
        (
            "on: {\n  pull_request_target: {},\n  push: {branches: [main]}\n}\n",
            ["pull_request_target", "push"],
        ),
        (
            "on: {push: {branches: [main, 'a,b']}, pull_request_target: }\n",
            ["push", "pull_request_target"],
        ),
        (
            'name: x\n"on": # the events\n  push:\n    branches: [main]\n\n'
            "  # A comment.\n  'pull_request_target':\n    types: [opened]\n"
            "jobs:\n  pull_request:\n",
            ["push", "pull_request_target"],
        ),
        # A list as far in as the keys of the table belongs to the key above it.
        (
            "on:\n  pull_request_target:\n    types: [opened]\n  schedule:\n"
            '  - cron: "5 6 * * 4"\n  push:\n',
            ["pull_request_target", "schedule", "push"],
        ),
        ("on:\n- push\n- schedule\njobs: {}\n", ["push", "schedule"]),
        ("on:\n  - push\n  - workflow_dispatch\n", ["push", "workflow_dispatch"]),
        ("on:\njobs: {}\n", []),
        ("jobs:\n  a:\n    on: push\n", []),
        ("# on: push\nonly: true\n", []),
    ],
)
def test_the_events_of_a_workflow_in_every_style_of_yaml(
    text: str, events: list[str]
) -> None:
    assert workflow_events(text) == events


def test_the_settings_keep_a_policy_for_the_workflows_on_pull_request_target(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with_workflows(root)
    # One of the organization above, of the same name, is none of these settings.
    github.parent_policies = [{"id": 99, "name": "Allow pull_request_target"}]

    assert run(github, root, "settings", "check") == 1
    assert (
        'policy pull_request_target: GitHub has "missing", the configuration wants'
        ' "present"'
    ) in capsys.readouterr().out

    run(github, root, "settings", "apply")
    set_secrets(github)

    # Only the listed workflows, with every event that starts them; CI isn't one.
    assert list(github.policies.values()) == [wanted_policy()]
    assert run(github, root, "settings", "check") == 0
    assert "policy" not in capsys.readouterr().out
    # The repository's own policies, and then the one by its id.
    listing = f"repos/{REPO}/actions/policies?has_parents=false&per_page=100"
    assert ("GET", listing) in github.calls
    assert ("GET", f"repos/{REPO}/actions/policies/1") in github.calls


@pytest.mark.parametrize(
    ("change", "difference"),
    [
        ({"enforcement": "disabled"}, "enforcement disabled"),
        (
            {"conditions": {"workflow_path": {"include": [], "exclude": []}}},
            "workflows []",
        ),
        (
            {
                "conditions": {
                    "workflow_path": {
                        "include": [
                            ".github/workflows/welcome.yml",
                            ".github/workflows/title.yml",
                        ],
                        "exclude": [".github/workflows/ci.yml"],
                    }
                }
            },
            "excluded workflows ['.github/workflows/ci.yml']",
        ),
        ({"rules": []}, "rules []"),
        (
            {
                "rules": [
                    {
                        "type": "restrict_action_events",
                        "parameters": {"allowed_events": ["pull_request_target"]},
                    }
                ]
            },
            "events ['pull_request_target']",
        ),
        (
            {"rules": [{"type": "restrict_actions_actors", "parameters": {}}]},
            "rules ['restrict_actions_actors']",
        ),
    ],
)
def test_a_policy_that_differs_comes_back_to_the_settings(
    github: FakeGitHub,
    root: Path,
    capsys: pytest.CaptureFixture[str],
    change: dict[str, Any],
    difference: str,
) -> None:
    with_workflows(root)
    github.policies[7] = {**wanted_policy(), **change}

    assert run(github, root, "settings", "check") == 1
    assert (
        f'policy pull_request_target: GitHub has "{difference}", the configuration'
        ' wants "as configured"'
    ) in capsys.readouterr().out

    run(github, root, "settings", "apply")

    assert github.policies == {7: wanted_policy()}
    assert ("PUT", f"repos/{REPO}/actions/policies/7") in github.calls


def test_the_policy_goes_once_no_listed_workflow_starts_on_the_event(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The title check moved to pull_request and the welcome went; the list may still
    # name both.
    with_workflows(root, title=TITLE.replace("_target", ""), ci=CHECKS)
    github.policies[7] = wanted_policy()
    github.policies[8] = {**wanted_policy(), "name": "Someone else's"}

    assert run(github, root, "settings", "check") == 1
    assert (
        'policy pull_request_target: GitHub has "present", the configuration wants'
        ' "absent"'
    ) in capsys.readouterr().out

    run(github, root, "settings", "apply")

    assert list(github.policies) == [8]
    run(github, root, "settings", "check")
    assert "policy" not in capsys.readouterr().out


def test_a_policy_that_is_gone_already_is_left_alone(github: FakeGitHub) -> None:
    # Someone deleted it between the check and the apply.
    drift = [Drift("policy pull_request_target", "absent", "present")]

    apply_policies(Api(github), REPO, [], {}, drift)

    assert github.policies == {}
    assert [method for method, _ in github.calls] == ["GET"]


def test_a_workflow_on_pull_request_target_that_the_list_lacks_is_named(
    github: FakeGitHub,
    root: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    with_workflows(root, 'pull_request_target = [".github/workflows/title.yml"]\n')

    assert run(github, root, "settings", "apply") == 1

    # The settings bot names it and leaves it out: a person decides.
    out = capsys.readouterr().out
    assert (
        "policy pull_request_target lacks .github/workflows/welcome.yml:"
        ' GitHub has "missing", the configuration wants "listed"\n'
        "      .github/workflows/welcome.yml starts on pull_request_target, which"
        " GitHub blocks in a public repository from 2 December 2026 unless a policy"
        " allows it: start it on pull_request where it needs neither a token that"
        " writes nor a secret for a pull request of a fork, or add"
        ' ".github/workflows/welcome.yml" to pull_request_target of [actions] in'
        " .github/repository.project.toml\n"
    ) in out
    [policy] = github.policies.values()
    assert policy["conditions"]["workflow_path"]["include"] == [
        ".github/workflows/title.yml"
    ]
    # The check lint of a pull request names it at its event, from the files alone.
    github.calls.clear()

    assert run(github, root, "settings", "actions") == 1

    out = capsys.readouterr().out
    assert out.startswith(
        "GitHub blocks these workflows in a public repository from 2 December 2026,"
        " as pull_request_target of [actions] of .github/repository.toml lacks them:\n"
        "- .github/workflows/welcome.yml starts on pull_request_target, which GitHub"
        " blocks"
    )
    assert (
        "::error file=.github/workflows/welcome.yml,line=2,title=Allowed events::"
        ".github/workflows/welcome.yml starts on pull_request_target"
    ) in out
    assert not github.calls


def test_the_lint_of_the_blueprint_names_both_lists_of_the_policy(
    github: FakeGitHub,
    root: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    # Named in a comment before the event, which isn't where it starts.
    with_workflows(root, "", welcome="# pull_request_target\n" + TITLE)
    (root / "copier.yml").write_text("{}\n", encoding="utf-8")
    (root / "template").mkdir()

    assert run(github, root, "settings", "actions") == 1

    out = capsys.readouterr().out
    assert (
        '".github/workflows/welcome.yml" to pull_request_target of [actions] in'
        " template/.github/repository.toml.jinja and .github/repository.toml\n"
    ) in out
    assert "::error" not in out


def test_a_private_repository_on_github_free_has_no_policies(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    github.repo["private"] = True
    with_workflows(root)
    run(github, root, "settings", "apply")
    set_secrets(github)
    capsys.readouterr()

    # GitHub blocks pull_request_target only in a public repository: a notice.
    assert run(github, root, "settings", "apply") == 0

    out = capsys.readouterr().out
    assert (
        'policy pull_request_target: GitHub has "not offered", the configuration'
        ' wants "present"'
    ) in out
    assert f'answered "{POLICIES_REFUSAL}"' in out
    # Nothing to say where nothing needs the policy.
    with_workflows(root, ci=CHECKS)

    assert run(github, root, "settings", "check") == 0
    assert "policy" not in capsys.readouterr().out


def test_a_refusal_of_the_policies_that_is_not_the_plan_still_fails(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with_workflows(root)
    listing = f"repos/{REPO}/actions/policies?has_parents=false&per_page=100"
    github.fail[("GET", listing)] = 403
    permission = "the token may lack the permission Administration (read and write)"

    # It names the part and the permission.
    assert run(github, root, "settings", "check") == 1

    out = capsys.readouterr().out
    assert (
        'policy pull_request_target: GitHub has "unreadable", the configuration wants'
        ' "present"\n      GitHub refused the policies: GitHub answered 403:'
        f" simulated failure; {permission}"
    ) in out

    # The other parts are applied all the same, and nothing writes over the policy.
    assert run(github, root, "settings", "apply") == 2

    assert "the policies could not be applied: GitHub answered 403" in (
        capsys.readouterr().err
    )
    assert github.variables["RELEASE_AUTOMATION_CLIENT_ID"] != "outdated"
    assert github.rulesets
    assert github.policies == {}
    assert not [
        call for call in github.calls if call[0] != "GET" and "actions/polic" in call[1]
    ]


def test_a_policy_that_github_refuses_to_show_is_named(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with_workflows(root)
    github.policies[7] = wanted_policy()
    github.fail[("GET", f"repos/{REPO}/actions/policies/7")] = 403

    assert run(github, root, "settings", "check") == 1

    assert (
        'policy pull_request_target: GitHub has "unreadable", the configuration wants'
        ' "present"\n      GitHub refused the policies: GitHub answered 403'
    ) in capsys.readouterr().out
    # Nothing needs the policy any more: the refusal is named all the same.
    with_workflows(root, ci=CHECKS)
    github.fail[
        ("GET", f"repos/{REPO}/actions/policies?has_parents=false&per_page=100")
    ] = 403

    assert run(github, root, "settings", "check") == 1

    assert (
        'policy pull_request_target: GitHub has "unreadable", the configuration wants'
        ' "absent"'
    ) in capsys.readouterr().out


def test_a_refused_policy_names_the_permission_of_the_app(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with_workflows(root)
    github.fail[("POST", f"repos/{REPO}/actions/policies")] = 403

    assert run(github, root, "settings", "apply") == 2

    assert (
        "the policies could not be applied: GitHub answered 403: simulated failure;"
        " the token may lack the permission Administration (read and write)"
    ) in capsys.readouterr().err


def test_one_query_reads_the_files_of_many_actions_at_once(github: FakeGitHub) -> None:
    named = {f"vendor/action-{index}@{index}": "ci.yml" for index in range(BATCH + 1)}
    named["vendor/flows/.github/workflows/scan.yml@def"] = "ci.yml"
    github.contents = {
        "vendor/action-0/action.yaml@0": "runs:\n  steps:\n    - uses: x/y@1\n",
        "vendor/flows/.github/workflows/scan.yml@def": "jobs: {}\n",
    }

    runs = actions_that_run(Api(github), named)

    assert runs.found["x/y@1"] == "vendor/action-0"
    assert runs.via["x/y@1"] == "vendor/action-0@0"
    assert runs.refused == {}
    # Two for the actions that the workflows name, one for those that they run.
    assert [len(query) for query in github.file_queries] == [
        BATCH * 4,
        (len(named) - BATCH) * 4 - 1,
        4,
    ]
    # The file of an action may be action.yml or action.yaml, that of a reusable
    # workflow is its path.
    first = github.file_queries[0]
    assert (first["o0"], first["n0"]) == ("vendor", "action-0")
    assert (first["e0_0"], first["e0_1"]) == ("0:action.yml", "0:action.yaml")
    assert github.file_queries[1]["e1_0"] == "def:.github/workflows/scan.yml"


class Answering(Api):
    """An Api that answers every request with the same data."""

    def __init__(self, data: Any) -> None:
        super().__init__()
        self.data = data

    def request(
        self,
        method: str,
        path: str,
        body: Any = None,
        *,
        missing_ok: bool = False,
        retry: bool | None = None,
    ) -> Response:
        return Response(200, self.data)


@pytest.mark.parametrize(
    ("data", "inner", "refused"),
    [
        # An answer that isn't an object, or has no data.
        ([], {"a/b@1": []}, {}),
        ({"data": None}, {"a/b@1": []}, {}),
        # Errors that GraphQL answers in a list, each an object.
        ({"data": {}, "errors": "boom"}, {"a/b@1": []}, {}),
        ({"data": {}, "errors": ["boom"]}, {"a/b@1": []}, {}),
        # An error without a type or a place refuses every part without data.
        ({"data": {}, "errors": [{"message": "m"}]}, {}, {"a/b@1": "an error: m"}),
        # A file that is no text, such as a picture, runs nothing.
        ({"data": {"r0": {"f0": {"text": None}}}}, {"a/b@1": []}, {}),
        ({"data": {"r0": {"f1": {"text": "- uses: c/d@2"}}}}, {"a/b@1": ["c/d@2"]}, {}),
    ],
    ids=["list", "no data", "errors", "error", "untyped", "binary", "yaml"],
)
def test_an_answer_of_graphql_in_any_shape_is_read(
    data: Any, inner: dict[str, list[str]], refused: dict[str, str]
) -> None:
    found, unread = run_by(Answering(data), ["a/b@1"])

    assert found == inner
    assert {
        key: value.removeprefix("GitHub answered ") for key, value in unread.items()
    } == refused


def test_the_line_of_an_action_that_no_step_names_is_none() -> None:
    assert line_of("steps:\n  - uses: a/b@1\n  - uses: c/d@2\n", "c/d@2") == 3
    assert line_of("steps:\n  - run: echo a/b@1\n", "a/b@1") == 0


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
    # No pattern names an image of Docker.
    assert not allows({"patterns_allowed": ["*"]}, "docker://alpine:3@sha256:00")


@pytest.mark.parametrize(
    ("actions", "message"),
    [
        ('allowed_actions = "some"\n', "allowed_actions of [actions] is one of all"),
        ('allowed_actions = "selected"\n', "needs the table [actions.selected]"),
        (
            'pull_request_target = ".github/workflows/welcome.yml"\n',
            "pull_request_target of [actions] lists the workflows that may start on",
        ),
        (
            'pull_request_target = ["welcome.yml"]\n',
            " such as \".github/workflows/welcome.yml\", not ['welcome.yml']",
        ),
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
        "bypass": False,
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


@pytest.mark.parametrize("answer", [{"bypass": True}, {}])
def test_an_environment_that_administrators_may_bypass_drifts(
    github: FakeGitHub, answer: dict[str, bool]
) -> None:
    # GitHub's default, also for an answer that doesn't name it.
    github.environments["release"] = {
        "policy": MAIN_ONLY,
        "branches": [{"id": 5, "name": "main"}],
        "secrets": [],
        **answer,
    }

    assert check_environments(Api(github), REPO, {"release": {}}) == [
        Drift("environment release.can_admins_bypass", False, True)
    ]


def test_apply_turns_off_the_bypass_of_administrators_with_one_write(
    github: FakeGitHub, root: Path
) -> None:
    run(github, root, "settings", "apply")
    set_secrets(github)
    # An environment that a person changed by hand: both its branches and its bypass.
    github.environments["release"]["bypass"] = True
    github.environments["release"]["branches"].append(
        {"id": 99, "name": "v*", "type": "tag"}
    )
    github.calls.clear()

    assert run(github, root, "settings", "check") == 1
    assert run(github, root, "settings", "apply") == 0
    assert github.environments["release"]["bypass"] is False
    assert [item["name"] for item in github.environments["release"]["branches"]] == [
        "main"
    ]
    path = f"repos/{REPO}/environments/release"
    assert github.calls.count(("PUT", path)) == 1


def test_apply_creates_every_environment_without_the_bypass_of_administrators(
    github: FakeGitHub, root: Path
) -> None:
    run(github, root, "settings", "apply")

    assert github.environments
    for name, environment in github.environments.items():
        assert environment["bypass"] is False, name


def test_a_refused_bypass_still_creates_the_environment_for_main_only(
    github: FakeGitHub,
) -> None:
    github.refuses_bypass = 422
    api = Api(github)
    drift = [Drift("environment release", "main only", "missing")]

    apply_environments(api, REPO, drift)

    release = github.environments["release"]
    assert release["policy"] == MAIN_ONLY
    assert [item["name"] for item in release["branches"]] == ["main"]
    # GitHub's default stays, and the next check names it.
    assert check_environments(api, REPO, {"release": {}}) == [
        Drift("environment release.can_admins_bypass", False, True)
    ]


def test_another_refusal_of_an_environment_stops_the_apply(
    github: FakeGitHub,
) -> None:
    github.refuses_bypass = 403

    with pytest.raises(GitHubError, match="403"):
        apply_environments(
            Api(github), REPO, [Drift("environment release", "main only", "missing")]
        )


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


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_an_error_of_github_is_asked_again(status: int, waits: list[float]) -> None:
    # The "Internal server error" of GitHub's outage of 9 November 2026 too.
    runner, calls = answers(
        http(status, {"message": "Internal server error"}), http(200, {"id": 1})
    )

    assert Api(runner).get("repos/x") == {"id": 1}
    assert len(calls) == 2
    assert waits == [10]


def test_an_error_of_github_is_asked_again_three_times_with_longer_waits(
    waits: list[float],
) -> None:
    runner, calls = answers(
        *[http(503, {"message": "Service unavailable"})] * 3, http(200, {"id": 1})
    )

    assert Api(runner).get("repos/x") == {"id": 1}
    assert len(calls) == 4
    assert waits == [10, 20, 40]


def test_an_error_of_github_that_stays_stops_the_request(waits: list[float]) -> None:
    runner, calls = answers(*[http(502, {"message": "Bad Gateway"})] * 4)

    with pytest.raises(GitHubError, match="502: Bad Gateway") as error:
        Api(runner).put("repos/x/topics", {"names": []})
    assert len(calls) == 4
    assert waits == [10, 20, 40]
    assert error.value.unavailable


@pytest.mark.parametrize(
    "error",
    [
        'Get "https://api.github.com/repos/x": net/http: TLS handshake timeout',
        "dial tcp 140.82.112.6:443: i/o timeout",
        'Get "https://api.github.com/repos/x": context deadline exceeded',
        "read tcp: connection reset by peer",
        'Get "https://api.github.com/repos/x": unexpected EOF',
    ],
)
def test_a_call_without_an_answer_is_asked_again(
    error: str, waits: list[float]
) -> None:
    runner, calls = answers(f"\x00{error}", http(200, {"id": 1}), codes=[1, 0])

    assert Api(runner).get("repos/x") == {"id": 1}
    assert len(calls) == 2
    assert waits == [10]


def test_a_call_that_never_gets_an_answer_means_github_is_unavailable(
    waits: list[float],
) -> None:
    runner, calls = answers(*["\x00dial tcp: i/o timeout"] * 4, codes=[1] * 4)

    with pytest.raises(GitHubError) as error:
        Api(runner).get("repos/x")
    assert len(calls) == 4
    assert error.value.status == 0
    assert error.value.unavailable


@pytest.mark.parametrize(
    ("status", "message", "unavailable"),
    [
        (500, "Internal server error", True),
        (504, "Gateway Timeout", True),
        (0, "gh: no answer from GitHub within 90 seconds", True),
        (0, "gh: not logged in", False),
        (403, "Resource not accessible by integration", False),
        (404, "Not Found", False),
        (422, "Validation Failed", False),
    ],
)
def test_only_an_error_of_github_means_that_it_is_unavailable(
    status: int, message: str, unavailable: bool
) -> None:
    assert GitHubError(status, message).unavailable is unavailable


def test_a_call_that_stalls_ends_as_one_without_an_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limits: list[float] = []

    def stalls(command: list[str], **options: Any) -> subprocess.CompletedProcess[str]:
        limits.append(options["timeout"])
        raise subprocess.TimeoutExpired(command, options["timeout"])

    monkeypatch.setattr(subprocess, "run", stalls)

    result = blueprint.github.run_gh(["api", "--include", "repos/x"], None)

    assert limits == [blueprint.github.CALL_TIME_LIMIT]
    assert result.returncode == 1
    assert GitHubError(0, result.stderr).unavailable


def test_the_time_of_a_call_that_stalls_counts_against_the_budget(
    waits: list[float],
) -> None:
    # Four calls of 90 seconds and their waits would outlast the job of a bot.
    stalled = f"\x00gh: no answer from GitHub within {blueprint.github.CALL_TIME_LIMIT} seconds"
    runner, calls = answers(*[stalled] * 4, codes=[1] * 4)

    with pytest.raises(GitHubError) as error:
        Api(runner).get("repos/x")
    assert len(calls) == 2
    assert waits == [10]
    assert error.value.unavailable


def test_a_query_of_graphql_is_asked_again_after_an_error_of_github(
    waits: list[float],
) -> None:
    runner, calls = answers(
        "\x00gh: Something went wrong (HTTP 502)",
        json.dumps({"data": {"viewer": {"login": "a"}}}),
        codes=[1, 0],
    )

    assert Api(runner).graphql("{ viewer { login } }") == {"viewer": {"login": "a"}}
    assert len(calls) == 2
    assert waits == [10]


@pytest.mark.parametrize(
    ("error", "status", "unavailable"),
    [
        ("HTTP 502: Bad Gateway (https://api.github.com/graphql)", 502, True),
        ("gh: Something went wrong (HTTP 500)", 500, True),
        (
            "Post https://api.github.com/graphql: net/http: TLS handshake timeout",
            0,
            True,
        ),
        ("HTTP 401: Bad credentials (https://api.github.com/graphql)", 401, False),
        ("GraphQL: Could not resolve to a Repository", 0, False),
        # GitHub's own failure, which GraphQL answers with 200, and a connection that
        # broke off.
        (
            "GraphQL: Something went wrong while executing your query. Please "
            "include `0400:1A2B` when reporting this issue.",
            0,
            True,
        ),
        ('Post "https://api.github.com/graphql": EOF', 0, True),
    ],
)
def test_a_command_of_gh_that_fails_names_the_status_of_github(
    error: str, status: int, unavailable: bool
) -> None:
    runner, calls = answers(*[f"\x00{error}"] * 4, codes=[1] * 4)

    with pytest.raises(GitHubError) as raised:
        Api(runner).command(["pr", "list", "--json", "number"])
    assert raised.value.status == status
    assert raised.value.unavailable is unavailable
    # Only an error of GitHub is asked again, three times.
    assert len(calls) == (4 if unavailable else 1)


def test_a_post_that_a_gateway_timed_out_is_not_sent_twice(
    waits: list[float],
) -> None:
    # GitHub has often opened the issue all the same: a second try would open two.
    runner, calls = answers(http(502, {"message": "Bad Gateway"}), http(201, {}))

    with pytest.raises(GitHubError, match="502: Bad Gateway"):
        Api(runner).post("repos/x/issues", {"title": "t"})
    assert len(calls) == 1
    assert waits == []


def test_a_post_that_only_reads_is_asked_once_more_after_a_gateway(
    waits: list[float],
) -> None:
    # A query of GraphQL changes nothing: sent twice, it does no harm.
    runner, calls = answers(http(502, {"message": "Bad Gateway"}), http(200, {"a": 1}))

    response = Api(runner).request("POST", "graphql", {"query": "{}"}, retry=True)

    assert response.data == {"a": 1}
    assert len(calls) == 2
    assert waits == [10]


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


def test_too_many_requests_waits_the_time_that_github_names(
    waits: list[float],
) -> None:
    # What the code search answers to the token of a job after a search or two in a
    # minute, as a run of the Dashboard workflow saw it.
    limited = http(429, {"message": "try again in 56.888583718s"}, retry_after="56")
    runner, calls = answers(limited, http(200, {"total_count": 0}))

    assert Api(runner).get("search/code?q=x") == {"total_count": 0}
    assert len(calls) == 2
    assert waits == [56]


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
    assert waits == [10]


def test_a_list_that_a_gateway_keeps_failing_is_an_outage(waits: list[float]) -> None:
    # gh names the status without parentheses when the body of the error is no JSON
    # of GitHub, such as the page of a gateway.
    runner, calls = answers(
        *["<html>Bad Gateway</html>\x00gh: HTTP 502"] * 4, codes=[1] * 4
    )

    with pytest.raises(GitHubError) as error:
        Api(runner).get_all("repos/x/rulesets")
    assert len(calls) == 4
    assert waits == [10, 20, 40]
    assert error.value.status == 502
    assert error.value.unavailable
    assert str(error.value) == "GitHub answered 502: Bad Gateway"


@pytest.mark.parametrize(
    ("stderr", "status", "message"),
    [
        ("gh: HTTP 404", 404, "Not Found"),
        ("gh: Not Found (HTTP 404)", 404, "Not Found"),
        ("gh: HTTP 403", 403, "Forbidden"),
        # A status without a name of its own keeps its number.
        ("gh: HTTP 499", 499, "HTTP 499"),
    ],
    ids=["bare", "in parentheses", "refused", "no name"],
)
def test_a_list_names_the_status_of_github_in_either_form(
    stderr: str, status: int, message: str
) -> None:
    runner, calls = answers(f"\x00{stderr}", codes=[1])

    with pytest.raises(GitHubError) as error:
        Api(runner).get_all("repos/x/rulesets", missing_ok=False)
    assert len(calls) == 1
    assert error.value.status == status
    assert error.value.message == message
    assert not error.value.unavailable


def test_a_bare_404_of_a_list_is_an_empty_list() -> None:
    runner, _ = answers("\x00gh: HTTP 404", codes=[1])

    assert Api(runner).get_all("repos/x/environments/pypi/secrets") == []


def test_a_list_without_an_answer_is_read_again(waits: list[float]) -> None:
    runner, calls = answers(
        "\x00gh: context deadline exceeded", json.dumps([[{"id": 1}]]), codes=[1, 0]
    )

    assert Api(runner).get_all("repos/x/rulesets") == [{"id": 1}]
    assert len(calls) == 2
    assert waits == [10]


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


# --------------------------------------------------------------------------- create


class Shell:
    """git and gh for blueprint.py create, after a preflight that nothing stops: each
    command answers as the test planned it, by default with success and no output,
    and each call is written down with the requests that GitHub had answered before
    it."""

    def __init__(self, github: FakeGitHub) -> None:
        self.github = github
        self.asked = preflight.answers(REPO)
        self.answers = dict(self.asked)
        self.calls: list[tuple[str, int]] = []

    def __call__(
        self, arguments: Sequence[str], folder: Path
    ) -> subprocess.CompletedProcess[str]:
        command = " ".join(without_the_version(arguments))
        self.calls.append((command, len(self.github.calls)))
        code, text = self.answers.get(command, (0, ""))
        return subprocess.CompletedProcess(
            list(arguments), code, "" if code else text, text if code else ""
        )

    @property
    def steps(self) -> list[tuple[str, int]]:
        """The calls other than those of the preflight."""
        return [call for call in self.calls if call[0] not in self.asked]


@pytest.fixture
def shell(github: FakeGitHub, monkeypatch: pytest.MonkeyPatch) -> Shell:
    simulated = Shell(github)
    monkeypatch.setattr(blueprint.bootstrap, "run_command", simulated)
    return simulated


@pytest.fixture
def copy(root: Path) -> Path:
    """A new copy of the blueprint, with the answers that Copier wrote."""
    owner, name = REPO.split("/")
    (root / ".copier-answers.yml").write_text(
        f"_commit: v1.0.0\nowner: {owner}\nproject_slug: {name}\n", encoding="utf-8"
    )
    return root


def test_create_makes_the_repository_then_applies_the_settings_and_shows_the_checklist(
    github: FakeGitHub,
    copy: Path,
    shell: Shell,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # What only a person sets, such as the secrets, the checklist names.
    assert run(github, copy, "create") == 0

    assert shell.steps == [
        ("git init --initial-branch=main", 0),
        ("git add --all", 0),
        ("git commit --signoff --message chore: start from the blueprint", 0),
        (
            f"gh repo create {REPO} --public --description A demo --source . "
            "--remote origin --push",
            0,
        ),
    ]
    # The settings once the repository exists, from .github/repository.toml.
    assert ("PATCH", f"repos/{REPO}") in github.calls
    assert github.repo["description"] == "A demo"
    assert github.pages is not None
    out = capsys.readouterr().out
    assert out.index(f"Created https://github.com/{REPO}") < out.index(
        f"The settings of {REPO} differ"
    )
    assert out.index("secret RELEASE_AUTOMATION_PRIVATE_KEY of release") < out.index(
        f"The set-up of {REPO}:"
    )
    assert "✔ Settings as code applied" in out


def test_create_fails_when_github_refuses_a_part_of_the_settings(
    github: FakeGitHub,
    copy: Path,
    shell: Shell,
    capsys: pytest.CaptureFixture[str],
) -> None:
    github.fail[("POST", f"repos/{REPO}/pages")] = 422

    assert run(github, copy, "create", "--private") == 2

    assert shell.calls[-1][0].startswith(f"gh repo create {REPO} --private")
    assert "the pages could not be applied" in capsys.readouterr().err
    # The checklist all the same, with the rest.
    assert any(path.endswith("/community/profile") for _, path in github.calls)


def test_create_with_dry_run_changes_nothing(
    github: FakeGitHub,
    copy: Path,
    shell: Shell,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run(github, copy, "create", "--dry-run") == 0

    # The preflight asks gh, which changes nothing.
    assert shell.steps == []
    assert github.calls == []
    out = capsys.readouterr().out
    assert out.startswith(f"The preflight of {REPO}:\n")
    assert f"create would make {REPO} on GitHub, public, with:" in out
    assert "  python3 .github/blueprint.py settings apply\n" in out


def workflows_of(copy: Path, *names: str) -> list[str]:
    """The workflows of the copy, by their paths."""
    folder = copy / ".github/workflows"
    folder.mkdir(parents=True, exist_ok=True)
    for name in names:
        (folder / name).write_text("on: workflow_dispatch\n", encoding="utf-8")
    return [f".github/workflows/{name}" for name in names]


class Registering:
    """workflows register as create runs it: what it was asked for, and its answer."""

    def __init__(self, error: GitHubError | None = None) -> None:
        self.asked: list[str] = []
        self.error = error

    def __call__(self, api: Api, repo: str) -> str:
        self.asked.append(repo)
        if self.error:
            raise self.error
        return "The pull request that registers them: https://github.com/o/r/pull/1"


def test_create_checks_that_github_knows_the_workflows_of_its_push(
    github: FakeGitHub,
    copy: Path,
    shell: Shell,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    github.workflows = workflows_of(copy, "ci.yml", "sbom.yml")
    registering = Registering()
    monkeypatch.setattr(cli, "register_workflows", registering)

    assert run(github, copy, "create") == 0

    out = capsys.readouterr().out
    assert out.index(f"Created https://github.com/{REPO}") < out.index(
        "GitHub knows all 2 workflows of .github/workflows/."
    )
    assert registering.asked == []
    assert "✔ GitHub knows every workflow of .github/workflows/" in out


def test_create_opens_the_pull_request_that_registers_what_github_does_not_know(
    github: FakeGitHub,
    copy: Path,
    shell: Shell,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    waits: list[float],
) -> None:
    # The first push registered only the workflow that its run registered (#652).
    github.workflows = workflows_of(copy, "ci.yml", "sbom.yml")[:1]
    registering = Registering()
    monkeypatch.setattr(cli, "register_workflows", registering)

    assert run(github, copy, "create") == 0

    assert registering.asked == [REPO]
    # GitHub had a minute to register the workflows.
    assert waits.count(10.0) == 5
    out = capsys.readouterr().out
    # The look, the pull request, the settings, then the checklist that names it.
    places = [
        out.index("GitHub hasn't registered 1 of the 2 workflows"),
        out.index("The pull request that registers them"),
        out.index(f"The settings of {REPO} differ"),
        out.index(f"The set-up of {REPO}:"),
    ]
    assert places == sorted(places)
    assert "✘ GitHub knows every workflow of .github/workflows/" in out
    assert "GitHub hasn't registered sbom.yml: it starts none of them" in out


def test_create_fails_when_the_pull_request_that_registers_the_workflows_fails(
    github: FakeGitHub,
    copy: Path,
    shell: Shell,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflows_of(copy, "sbom.yml")
    registering = Registering(GitHubError(422, "simulated failure"))
    monkeypatch.setattr(cli, "register_workflows", registering)

    assert run(github, copy, "create") == 2

    captured = capsys.readouterr()
    assert (
        "the pull request that registers the workflows could not be opened: GitHub"
        " answered 422: simulated failure. Run python3 .github/blueprint.py"
        " workflows register once that is fixed." in captured.err
    )
    # The checklist all the same.
    assert f"The set-up of {REPO}:" in captured.out


def test_create_applies_the_settings_when_github_cannot_list_the_workflows(
    github: FakeGitHub,
    copy: Path,
    shell: Shell,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflows_of(copy, "sbom.yml")
    github.fail[("GET", f"repos/{REPO}/actions/workflows?per_page=100")] = 403
    registering = Registering()
    monkeypatch.setattr(cli, "register_workflows", registering)

    assert run(github, copy, "create") == 2

    captured = capsys.readouterr()
    assert (
        "GitHub couldn't be asked which workflows it knows: GitHub answered 403:"
        " simulated failure. Run python3 .github/blueprint.py workflows register"
        " once that is fixed." in captured.err
    )
    assert registering.asked == []
    # The settings and the checklist all the same, so that main is protected.
    assert f"The settings of {REPO} differ" in captured.out
    assert f"The set-up of {REPO}:" in captured.out


def test_create_without_the_answers_names_a_command_that_works(
    github: FakeGitHub,
    copy: Path,
    shell: Shell,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (copy / ".copier-answers.yml").unlink()

    assert run(github, copy, "create", "--dry-run") == 2

    err = capsys.readouterr().err
    named = err.split("python3 .github/blueprint.py ", 1)[1].split()
    assert named == ["--repo", "OWNER/NAME", "create"]
    named[1] = REPO
    assert run(github, copy, *named, "--dry-run") == 0
    assert f"create would make {REPO} on GitHub" in capsys.readouterr().out


def test_create_refuses_a_folder_that_pushes_to_a_remote(
    github: FakeGitHub,
    copy: Path,
    shell: Shell,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (copy / ".git").mkdir()
    shell.answers["git remote"] = (0, "origin\n")
    shell.answers["git remote get-url origin"] = (0, f"https://github.com/{REPO}\n")

    assert run(github, copy, "--repo", "octo-org/demo", "create") == 2

    assert shell.steps == [("git remote", 0), ("git remote get-url origin", 0)]
    assert github.calls == []
    assert capsys.readouterr().err.startswith(
        "blueprint.py: this folder pushes to origin already"
    )


def test_create_goes_on_with_the_settings_after_a_run_that_stopped_there(
    github: FakeGitHub,
    copy: Path,
    shell: Shell,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # A run of create that made the repository and pushed, and then stopped before
    # its settings, such as on a dropped connection.
    (copy / ".git").mkdir()
    shell.answers.update(
        {
            "git remote": (0, "origin\n"),
            "git remote get-url origin": (0, f"git@github.com:{REPO}.git\n"),
            "git symbolic-ref --short HEAD": (0, "main\n"),
            f"gh api repos/{REPO}": (0, json.dumps({"full_name": REPO})),
            f"gh api repos/{REPO}/branches/main": (0, json.dumps({"name": "main"})),
        }
    )

    assert run(github, copy, "create") == 0

    assert not any(command.startswith("gh repo create") for command, _ in shell.calls)
    assert ("PATCH", f"repos/{REPO}") in github.calls
    out = capsys.readouterr().out
    assert out.index(f"Going on with {REPO} on GitHub") < out.index(
        f"The settings of {REPO} differ"
    )


def test_a_python_without_tomllib_is_named_before_the_import(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The import of the package would stop with a traceback on Python 3.10: the
    # script says so first, in words that every Python can write.
    monkeypatch.setattr("sys.version_info", (3, 10, 14, "final", 0))
    monkeypatch.setattr("sys.argv", ["blueprint.py", "doctor"])
    # The script sets it; the setattr puts it back after the test.
    monkeypatch.setattr("sys.dont_write_bytecode", sys.dont_write_bytecode)

    with pytest.raises(SystemExit) as stop:
        runpy.run_path(
            str(Path(__file__).parents[1] / "blueprint.py"), run_name="__main__"
        )

    assert stop.value.code == 1
    assert capsys.readouterr().err == (
        "Python 3.10: the tools of the new repository need Python 3.12 or later\n"
        "    install Python 3.12 or later: https://www.python.org/downloads/"
        " (on Windows, py -3 runs it)\n"
    )


def test_doctor_runs_the_preflight_of_create_and_nothing_else(
    github: FakeGitHub,
    copy: Path,
    shell: Shell,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run(github, copy, "doctor") == 0

    assert shell.steps == []
    assert github.calls == []
    assert capsys.readouterr().out.endswith(
        f"  ✔ {REPO} is free on GitHub\n"
        "Nothing stops python3 .github/blueprint.py create.\n"
    )

    shell.answers[f"gh api repos/{REPO}"] = (0, json.dumps({"full_name": REPO}))
    assert run(github, copy, "doctor") == 1
    assert f"  ✘ {REPO} is taken on GitHub" in capsys.readouterr().out

    (copy / ".git").mkdir()
    shell.answers["git remote"] = (0, "upstream\n")
    assert run(github, copy, "doctor") == 2
    assert capsys.readouterr().err.startswith(
        "blueprint.py: this folder pushes to upstream already"
    )


def test_create_checks_the_settings_before_anything_is_made(
    github: FakeGitHub,
    copy: Path,
    shell: Shell,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (copy / ".github/repository.toml").write_text(
        '[variables]\nRELEASE_AUTOMATION_APP_ID = "x"\n', encoding="utf-8"
    )

    assert run(github, copy, "create") == 2

    assert shell.calls == []
    assert "RELEASE_AUTOMATION_APP_ID" in capsys.readouterr().err


# --------------------------------------------------------------------------- checklist


def test_the_checklist_of_a_new_repository(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (root / ".github/FUNDING.yml").write_text(
        "github: [Dennis-Otto]\n", encoding="utf-8"
    )
    (root / ".github/social-preview.html").write_text(
        '<div class="panel" data-default-panel>\n', encoding="utf-8"
    )

    assert run(github, root, "checklist") == 1

    out = capsys.readouterr().out
    assert "✘ Settings as code applied" in out
    assert "✘ Secrets of the environments set" in out
    assert "✔ Community profile complete (100 %)" in out
    assert "app connect --key-file FILE" in out
    assert "· Settings → General → Features: Sponsorships on" in out
    # The drawing of its kind first, which the project replaces before the upload.
    assert out.index("✘ Social preview shows the project") < out.index(
        "✘ Social preview uploaded"
    )
    assert "a faithful drawing of what it produces, without data-default-panel" in out
    assert "✘ OpenSSF Best Practices badge" in out
    assert "✘ OpenSSF Baseline badge" in out
    # Without a project, the form of a new one, which reads .bestpractices.json.
    assert out.count("https://www.bestpractices.dev/en/projects/new") == 2
    assert "press 'Save (and continue) 🤖'" in out
    assert "Trusted publisher on PyPI" in out
    assert "✘ The dependency review allows the licenses of the blueprint bot's" in out


def test_the_checklist_of_a_finished_repository(
    github: FakeGitHub,
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run(github, root, "settings", "apply")
    set_secrets(github)
    github.og_image = True
    github.pulls = [RENOVATE]
    (root / "README.md").write_text(
        "[![Best](https://www.bestpractices.dev/projects/1/badge)]\n"
        "[![Baseline](https://www.bestpractices.dev/projects/1/baseline)]\n",
        encoding="utf-8",
    )
    (root / ".github/dependency-review.yml").write_text(
        "allow-dependencies-licenses:\n"
        + "".join(f"  - {tool}\n" for tool in BOT_TOOLS),
        encoding="utf-8",
    )
    monkeypatch.setattr(blueprint.checklist, "reuse_compliant", lambda repo: True)
    capsys.readouterr()

    assert run(github, root, "checklist") == 0

    out = capsys.readouterr().out
    assert "✔ Settings as code applied" in out
    assert "✔ Secrets of the environments set" in out
    assert "✔ Community profile complete (100 %)" in out
    assert "✔ Renovate runs: it has opened a pull request" in out
    assert "✔ Social preview shows the project" in out
    assert "Sponsorships" not in out
    assert "✔ Registered with the REUSE API" in out
    assert "✔ OpenSSF Best Practices badge in the README" in out
    assert "✔ OpenSSF Baseline badge in the README" in out


def test_the_checklist_asks_for_the_licenses_of_the_blueprint_bots_tools(
    tmp_path: Path,
) -> None:
    # As the repositories that took release 1.3.0 by an update have the file: the
    # project owns it, so the update didn't add wcwidth.
    review = tmp_path / ".github/dependency-review.yml"
    review.parent.mkdir()
    review.write_text(
        "allow-dependencies-licenses:\n"
        "  - pkg:pypi/jinja2-ansible-filters\n"
        "  - pkg:pypi/typing-extensions # read wrongly\n"
        "  # - pkg:pypi/wcwidth\n",
        encoding="utf-8",
    )

    step = bot_tools_allowed(tmp_path)

    assert step.text == (
        "The dependency review allows the licenses of the blueprint bot's tools"
    )
    assert step.done is False
    assert step.how.startswith(
        "Add pkg:pypi/wcwidth under allow-dependencies-licenses in"
        " .github/dependency-review.yml, as a new repository has them"
    )

    with review.open("a", encoding="utf-8") as file:
        file.write("  - pkg:pypi/wcwidth\n")
    assert bot_tools_allowed(tmp_path) == Step(step.text, True, "")


def test_the_dependency_review_may_quote_or_list_the_tools_in_a_flow(
    tmp_path: Path,
) -> None:
    # The project owns the file, so any spelling of YAML counts.
    review = tmp_path / ".github/dependency-review.yml"
    review.parent.mkdir()
    review.write_text(
        "allow-dependencies-licenses:\n"
        '  - "pkg:pypi/jinja2-ansible-filters"\n'
        "  - 'pkg:pypi/typing-extensions'\n"
        "  - pkg:pypi/wcwidth-extra # another tool\n",
        encoding="utf-8",
    )
    step = bot_tools_allowed(tmp_path)
    assert step.done is False
    assert step.how.startswith("Add pkg:pypi/wcwidth under")

    review.write_text(
        "allow-dependencies-licenses: [pkg:pypi/jinja2-ansible-filters,"
        ' "pkg:pypi/typing-extensions", pkg:pypi/wcwidth]\n',
        encoding="utf-8",
    )
    assert bot_tools_allowed(tmp_path).done is True


def test_without_its_dependency_review_a_repository_lacks_every_tool(
    tmp_path: Path,
) -> None:
    step = bot_tools_allowed(tmp_path)
    assert step.done is False
    assert step.how.startswith(
        "Add pkg:pypi/jinja2-ansible-filters, pkg:pypi/typing-extensions,"
        " pkg:pypi/wcwidth under"
    )


def test_the_checklist_asks_for_a_social_preview_of_the_project(root: Path) -> None:
    # A new repository starts with a drawing of its kind of project, made from its
    # answers; the step is done once the project shows itself.
    page = root / ".github/social-preview.html"
    page.write_text(
        '<!doctype html>\n<div class="panel" data-default-panel>\n', encoding="utf-8"
    )

    step = social_preview(root)

    assert step.text == "Social preview shows the project"
    assert step.done is False
    assert step.how.startswith(
        ".github/social-preview.html still shows the blueprint's default panel"
    )
    assert "bash scripts/social-preview.sh" in step.how

    # A repository made before keeps the card of the blueprint's checks that came
    # first, the same in every repository.
    page.write_text(
        '<div class="panel">\n  <div class="card checks">\n', encoding="utf-8"
    )
    assert social_preview(root).done is False

    page.write_text(
        '<!doctype html>\n<img class="card" src="../docs/images/card.png">\n',
        encoding="utf-8",
    )
    assert social_preview(root).done is True
    # The template's comment, which names the mark, stays once the panel is the
    # project's own.
    page.write_text(
        "<!-- Then take out data-default-panel, render the picture -->\n"
        '<div class="panel"><img class="card" src="card.png"></div>\n',
        encoding="utf-8",
    )
    assert social_preview(root).done is True
    # A project that shows its preview without the page has nothing to replace.
    page.unlink()
    assert social_preview(root).done is True


UPLOAD = "https://repository-images.githubusercontent.com/1/2"


def uploaded_as(data: bytes | OSError) -> Callable[..., Any]:
    """GitHub's host of uploads, which serves the uploaded social preview."""

    def opener(url: str, timeout: float) -> Any:
        assert url == UPLOAD
        if isinstance(data, OSError):
            raise data
        return io.BytesIO(data)

    return opener


def test_without_the_picture_an_upload_of_the_social_preview_is_enough(
    github: FakeGitHub, root: Path
) -> None:
    step = social_preview_uploaded(Api(github), REPO, root, uploaded_as(b"any"))

    assert step == Step(
        "Social preview uploaded (bash scripts/social-preview.sh renders it)",
        False,
        f"https://github.com/{REPO}/settings",
    )
    github.og_image, github.og_url = True, UPLOAD
    assert social_preview_uploaded(Api(github), REPO, root, uploaded_as(b"x")).done


def test_the_uploaded_social_preview_is_the_committed_picture(
    github: FakeGitHub, root: Path
) -> None:
    (root / ".github/social-preview.png").write_bytes(b"the picture")
    upload = (
        "upload .github/social-preview.png under Settings → General → Social"
        f" preview: https://github.com/{REPO}/settings"
    )

    # Nobody uploaded it yet: GitHub shows a card that it draws itself.
    step = social_preview_uploaded(Api(github), REPO, root, uploaded_as(b"x"))
    assert step == Step(
        "Social preview uploaded and current",
        False,
        f"GitHub shows a card of its own: {upload}",
    )
    # An upload of an older picture.
    github.og_image, github.og_url = True, UPLOAD
    step = social_preview_uploaded(Api(github), REPO, root, uploaded_as(b"older"))
    assert step == Step(
        "Social preview uploaded and current",
        False,
        "The uploaded picture is not .github/social-preview.png of this checkout:"
        f" {upload}",
    )
    # The upload of this picture, byte for byte.
    step = social_preview_uploaded(Api(github), REPO, root, uploaded_as(b"the picture"))
    assert step == Step("Social preview uploaded and current", True)
    # An upload that can't be read leaves the step open, with the reason.
    step = social_preview_uploaded(
        Api(github), REPO, root, uploaded_as(TimeoutError("timed out"))
    )
    assert step.done is None
    assert step.how == (
        f"Couldn't read the uploaded picture ({UPLOAD}: timed out). Compare it with"
        f" .github/social-preview.png, or {upload}"
    )


@pytest.mark.parametrize(
    ("picture", "title"),
    [
        (True, "Social preview uploaded and current"),
        (False, "Social preview uploaded (bash scripts/social-preview.sh renders it)"),
    ],
)
def test_a_private_repository_waits_with_the_upload_of_the_social_preview(
    github: FakeGitHub, root: Path, picture: bool, title: str
) -> None:
    # GitHub shows the social preview only for a public repository: an upload, or one
    # that fell behind, makes no difference until the repository is public.
    if picture:
        (root / ".github/social-preview.png").write_bytes(b"the picture")
    github.repo["private"] = True
    github.og_image, github.og_url = True, UPLOAD

    step = social_preview_uploaded(
        Api(github), REPO, root, uploaded_as(TimeoutError("timed out"))
    )

    assert step == Step(
        title,
        None,
        "The repository is private, and GitHub shows the social preview only for a"
        " public repository: once it is public, upload .github/social-preview.png"
        " under Settings → General → Social preview:"
        f" https://github.com/{REPO}/settings",
    )


def test_a_social_preview_larger_than_github_takes_asks_for_a_smaller_one(
    github: FakeGitHub, root: Path
) -> None:
    # GitHub takes an upload of at most 1 MB: this picture can never be uploaded.
    (root / ".github/social-preview.png").write_bytes(b"x" * (1024 * 1024 + 1))
    github.og_image, github.og_url = True, UPLOAD

    step = social_preview_uploaded(Api(github), REPO, root, uploaded_as(b"older"))

    assert step == Step(
        "Social preview uploaded and current",
        False,
        ".github/social-preview.png is larger than the 1 MB that GitHub takes for an"
        " upload: render a smaller one, with fewer colors or a simpler screenshot,"
        " with bash scripts/social-preview.sh, then upload"
        " .github/social-preview.png under Settings → General → Social preview:"
        f" https://github.com/{REPO}/settings",
    )


def test_the_checklist_names_a_social_preview_that_fell_behind(
    github: FakeGitHub,
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (root / ".github/social-preview.png").write_bytes(b"the picture")
    github.og_image, github.og_url = True, UPLOAD
    monkeypatch.setattr(urllib.request, "urlopen", uploaded_as(b"older"))

    run(github, root, "checklist")

    out = capsys.readouterr().out
    assert "✘ Social preview uploaded and current" in out
    assert "The uploaded picture is not .github/social-preview.png" in out


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


def test_the_checklist_leaves_a_switch_that_github_keeps_off_neutral(
    github: FakeGitHub,
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    generic_patterns(root)
    github.kept_off.add("secret_scanning_non_provider_patterns")
    run(github, root, "settings", "apply")
    set_secrets(github)
    monkeypatch.setattr(blueprint.checklist, "reuse_compliant", lambda repo: True)
    capsys.readouterr()

    run(github, root, "checklist")

    out = capsys.readouterr().out
    assert "  · Settings as code applied" in out
    assert (
        "python3 .github/blueprint.py settings apply; it tells whether GitHub keeps"
        " security.secret_scanning_non_provider_patterns off for the plan of the"
        " repository"
    ) in out


def test_the_checklist_counts_push_protection_that_github_keeps_off_as_open(
    github: FakeGitHub,
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    github.kept_off.add("secret_scanning_push_protection")
    run(github, root, "settings", "apply")
    set_secrets(github)
    monkeypatch.setattr(blueprint.checklist, "reuse_compliant", lambda repo: True)
    capsys.readouterr()

    run(github, root, "checklist")

    assert "  ✘ Settings as code applied" in capsys.readouterr().out


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
    assert lines[secrets + 1].strip().endswith("app connect --key-file FILE")
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
        ("cloudflare-workers", "connected with Workers Builds"),
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
        assert len(texts) == 15
    else:
        assert any(text in step for step in texts)


def test_the_checklist_of_an_extension_asks_for_the_item_and_the_sign_in_of_the_store(
    github: FakeGitHub, root: Path
) -> None:
    settings = Settings.load(root / ".github/repository.toml")
    settings.variables["PUBLISH_TO"] = "chrome-web-store"

    def store() -> list[Step]:
        steps = checklist(Api(github), REPO, settings, root, reuse=lambda repo: False)
        return [step for step in steps if step.text.startswith("Chrome Web Store:")]

    item, sign_in = store()
    assert "uploaded by hand" in item.text
    assert "CWS_EXTENSION_ID and CWS_PUBLISHER_ID" in item.text
    assert item.how.endswith("/docs/releases.md#the-first-listing")
    assert "CWS_WORKLOAD_IDENTITY_PROVIDER and CWS_SERVICE_ACCOUNT" in sign_in.text
    assert sign_in.how.endswith("/docs/releases.md#sign-in-without-a-stored-secret")
    assert (item.done, sign_in.done) == (False, False)

    # One of the two variables of a step leaves it open.
    github.variables["CWS_EXTENSION_ID"] = "abcdefghijklmnopabcdefghijklmnop"
    assert [step.done for step in store()] == [False, False]
    github.variables["CWS_PUBLISHER_ID"] = "publisher"
    assert [step.done for step in store()] == [True, False]
    github.variables["CWS_WORKLOAD_IDENTITY_PROVIDER"] = "projects/1/locations/global"
    github.variables["CWS_SERVICE_ACCOUNT"] = "store@demo.iam.gserviceaccount.com"
    assert [step.done for step in store()] == [True, True]


def test_the_checklist_of_an_integration_asks_for_the_topics_that_hacs_lists(
    github: FakeGitHub, root: Path
) -> None:
    def listing() -> Step:
        settings = Settings.load(root / ".github/repository.toml")
        settings.variables["PUBLISH_TO"] = "hacs"
        steps = checklist(Api(github), REPO, settings, root, reuse=lambda repo: False)
        found = [step for step in steps if step.text.startswith("Description and")]
        assert [step.text for step in found] == [
            "Description and topics set (HACS lists them)"
        ]
        # Before the step of the HACS default repositories, which needs it.
        assert "HACS default repositories" in steps[steps.index(found[0]) + 1].text
        return found[0]

    # Named in the settings, but not yet on GitHub.
    step = listing()
    assert step.done is False
    assert step.how == "python3 .github/blueprint.py settings apply"

    run(github, root, "settings", "apply")
    assert listing().done is True

    # Without topics, HACS doesn't list the integration, and its check fails.
    (root / ".github/repository.toml").write_text(
        CONFIG.replace('topics = ["b", "a"]', "topics = []"), encoding="utf-8"
    )
    run(github, root, "settings", "apply")
    step = listing()
    assert step.done is False
    (why, *rest) = step.how.splitlines()
    # A branch and the copier of the quick start: main refuses the push of a commit,
    # and the quick start puts no copier on the PATH.
    assert rest == change_answer("topics=home-assistant, hacs")
    assert "uvx --from copier==" in rest[3]
    assert "python3 .github/blueprint.py settings apply" in why


def without_release_app(root: Path) -> Settings:
    path = root / ".github/repository.toml"
    path.write_text(
        CONFIG.replace('RELEASE_AUTOMATION_CLIENT_ID = "Iv23client"\n', "").replace(
            '["RELEASE_AUTOMATION_PRIVATE_KEY"]', "[]"
        ),
        encoding="utf-8",
    )
    return Settings.load(path)


def test_the_checklist_names_the_command_that_registers_a_release_app(
    github: FakeGitHub, root: Path
) -> None:
    settings = without_release_app(root)
    assert "RELEASE_AUTOMATION_CLIENT_ID" not in settings.variables

    steps = checklist(Api(github), REPO, settings, root, reuse=lambda repo: False)

    # The app comes first: the settings and the secrets that follow name it.
    registered = steps[0]
    assert (
        registered.text == "Release app registered and named in .github/repository.toml"
    )
    assert registered.done is False
    lines = registered.how.splitlines()
    assert "commit.gpgsign" in lines[0]
    # With where a new owner learns to set up a key, which main asks for.
    assert blueprint.bootstrap.SIGNING in lines[0]
    assert lines[1] == "python3 .github/blueprint.py app register"
    assert lines[2] == (
        "The app gets read and write access to Actions, Administration, Checks, Commit"
        " statuses, Contents, Dependabot alerts, Issues, Pages, Pull requests,"
        " Variables and Workflows, read access to Environments and Secrets, and no"
        " webhook. For an app that exists, such as for a further repository:"
        " python3 .github/blueprint.py app connect --key-file FILE"
    )
    # Neither the long link nor a value to copy by hand.
    assert "settings/apps/new" not in registered.how
    assert "copier update" not in registered.how
    installed = next(
        step for step in steps if step.text.endswith("installed on the repository")
    )
    assert installed.how == (
        "Install App on the settings page of the app, for this repository"
    )
    assert installed.done is None


@pytest.mark.parametrize(
    ("owner", "name"),
    [
        ("Dennis-Otto", "dennis-otto-release-automation"),
        # 15 characters still fit with the long suffix: 34 in all.
        ("abcdefghijklmno", "abcdefghijklmno-release-automation"),
        ("my-company-engineering", "my-company-engineering-release"),
        # The longest name GitHub allows, cut so that no hyphen ends it.
        ("a" * 25 + "-" + "b" * 13, "a" * 25 + "-release"),
    ],
)
def test_the_suggested_release_app_name_fits_the_limit_of_github(
    owner: str, name: str
) -> None:
    assert release_app_name(owner) == name
    assert len(name) <= APP_NAME_LIMIT


def test_the_template_asks_for_the_copier_that_knows_the_current_ref() -> None:
    # `--vcs-ref=:current:`, which app register, the checklist and the READMEs name,
    # came with 9.8.
    command = "--vcs-ref=:current:"
    assert command in (ROOT / "blueprint/checklist.py").read_text(encoding="utf-8")
    copier = (ROOT / "copier.yml").read_text(encoding="utf-8")
    minimum = re.search(r'^_min_copier_version: "(\d+)\.(\d+)"$', copier, re.M)
    assert minimum is not None
    assert (int(minimum[1]), int(minimum[2])) >= (9, 8)
    version = f"{minimum[1]}.{minimum[2]}"
    assert f"Copier {version} or later" in (ROOT / "README.md").read_text("utf-8")
    assert f"Copier ab {version}" in (ROOT / "README.de.md").read_text("utf-8")


def test_the_checklist_of_a_named_release_app_links_its_installation(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = root / ".github/repository.toml"
    path.write_text(
        CONFIG.replace(
            "[variables]\n", '[variables]\nRELEASE_APP = "demo-release-automation"\n'
        ),
        encoding="utf-8",
    )

    assert run(github, root, "checklist") == 1

    lines = capsys.readouterr().out.splitlines()
    assert lines.index(
        "  ✔ Release app demo-release-automation named in .github/repository.toml"
    ) < lines.index("  ✘ Settings as code applied")
    installed = lines.index("  · Release app installed on the repository")
    assert lines[installed + 1] == (
        "      https://github.com/apps/demo-release-automation/installations/new"
    )
    # Which app the OSV-Scanner workflow closes the accepted Dependabot alerts as, and
    # the permission that it needs, which no API tells.
    assert lines[installed + 2] == (
        "  · The settings app, or the release app without one, may write the Dependabot"
        " alerts, so that the OSV-Scanner workflow closes those that osv-scanner.toml"
        " accepts"
    )
    assert "set Dependabot alerts to Read and write" in lines[installed + 3]
    # Its owner is no question once it is named.
    assert ("GET", "users/Dennis-Otto") not in github.calls


# A pull request of Renovate, which shows that it runs.
RENOVATE = {
    "number": 7,
    "title": "fix(deps): update the actions",
    "head": {"ref": "renovate/the-actions"},
}
HUB = [
    "The Renovate workflow of the blueprint runs it every two hours for each"
    " repository of its owner on which the release app is installed; its next run"
    " after the installation opens its pull requests."
]


def test_the_checklist_knows_that_renovate_runs_by_its_pull_requests(
    github: FakeGitHub, root: Path
) -> None:
    # Renovate keeps no issue open, so its old dashboard shows nothing; nor does a
    # pull request of someone else with the title of an update, or one that GitHub
    # answers without its branch.
    github.issues = [{"number": 6, "title": "Dependency dashboard"}]
    github.pulls = [
        {
            "number": 9,
            "title": "fix(deps): update the actions",
            "head": {"ref": "fix/deps"},
        },
        {"number": 8, "title": "fix(deps): update uv", "head": None},
        {"number": 5, "title": "chore: a branch without its name", "head": {}},
        "no pull request",
    ]

    waiting = renovate(Api(github), REPO, root)
    github.pulls.append(RENOVATE)
    running = renovate(Api(github), REPO, root)

    assert waiting.text == "Renovate runs: it has opened a pull request"
    assert waiting.done is False
    assert running.done is True
    # The latest pull requests of every state, as Renovate merges most on its own.
    assert ("GET", f"repos/{REPO}/pulls?state=all&per_page=100") in github.calls


def test_the_checklist_waits_for_renovate_when_github_knows_no_pull_requests(
    github: FakeGitHub, root: Path
) -> None:
    github.fail[("GET", f"repos/{REPO}/pulls?state=all&per_page=100")] = 404

    step = renovate(Api(github), REPO, root)

    assert step.done is False


@pytest.mark.parametrize(
    ("answers", "how"),
    [
        # The blueprint itself, which has no answers, runs the hub.
        (None, HUB),
        ("_commit: v0.13.0\nrenovate_runner: hub\n", HUB),
        (
            "renovate_runner: self\n",
            [
                "The Renovate workflow of this repository runs it every two hours as"
                " the release app, once the app is installed; start its first run:",
                f"https://github.com/{REPO}/actions/workflows/renovate.yml",
            ],
        ),
        ("renovate_runner: someone\n", HUB),
    ],
    ids=["no answers", "hub", "self", "unknown"],
)
def test_the_checklist_says_how_renovate_comes_to_run(
    github: FakeGitHub, root: Path, answers: str | None, how: list[str]
) -> None:
    if answers is not None:
        (root / ".copier-answers.yml").write_text(answers, encoding="utf-8")

    step = renovate(Api(github), REPO, root)

    assert step.done is False
    assert step.how.splitlines() == how


def test_the_checklist_links_the_mend_app_and_leaves_its_rule_to_the_blueprint(
    github: FakeGitHub, root: Path
) -> None:
    (root / ".copier-answers.yml").write_text(
        "renovate_runner: mend\n", encoding="utf-8"
    )

    step = renovate(Api(github), REPO, root)

    # The rules of the blueprint take the commits of the release app for those of
    # Renovate, so nothing is left to add by hand, and GitHub isn't asked for a number.
    assert step.how.splitlines() == [
        "Install the Mend Renovate app on this repository; it reads"
        " .github/renovate.json5 and opens its pull requests from its first run:",
        "https://github.com/apps/renovate/installations/new",
    ]
    assert not [path for _, path in github.calls if path.startswith("users/")]


@pytest.mark.parametrize(
    ("app", "answers", "asked"),
    [
        ("", "renovate_runner: mend\n", False),
        ("demo-app", "renovate_runner: mend\nrelease_app: demo-app\n", False),
        ("demo-app", "renovate_runner: mend\nrelease_app: other-app\n", True),
        ("demo-app", "renovate_runner: mend\n", True),
    ],
    ids=["no app", "the answer", "another answer", "no answer"],
)
def test_the_checklist_asks_for_the_answer_of_an_app_that_only_the_settings_name(
    github: FakeGitHub, root: Path, app: str, answers: str, asked: bool
) -> None:
    (root / ".copier-answers.yml").write_text(answers, encoding="utf-8")

    how = renovate(Api(github), REPO, root, app).how

    # The rule of the blueprint comes from the answer alone, so without it Renovate
    # would take the commits of this app for someone editing its branches.
    assert (f"--data release_app={app}" in how) is asked
    if asked:
        # By the steps of a new owner, whom main refuses a push and no copier awaits.
        assert "\n".join(change_answer(f"release_app={app}")) in how


def test_the_release_app_has_every_permission_that_a_workflow_asks_for() -> None:
    granted = {key: access for _, key, access in RELEASE_APP_PERMISSIONS}
    rank = {"read": 1, "write": 2}
    for path in sorted((ROOT / ".github/workflows").glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        # An input of the token action, or the variable that the action reads alike
        # for a permission that it has no input for.
        asked = re.findall(
            r"(?:permission|INPUT_PERMISSION)-([A-Za-z-]+): (read|write)", text
        )
        for name, access in asked:
            key = name.lower().replace("-", "_")
            # Every app may read the metadata.
            if key == "metadata":
                continue
            assert key in granted, (path.name, key)
            assert rank[granted[key]] >= rank[access], (path.name, key)
    # The guide names the same permissions, in the item right after that of the app.
    lines = (ROOT / "docs/guide.md").read_text(encoding="utf-8").splitlines()
    at = next(n for n, line in enumerate(lines) if "**The release app**" in line)
    paragraph = lines[at + 1]
    assert paragraph.startswith("- **Its permissions:**")
    for name, _, _ in RELEASE_APP_PERMISSIONS:
        assert f"*{name}*" in paragraph, name


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
    # An error as urlopen raises it, the answer of the server too: closed, as the
    # newest Python warns of one left open.
    error = urllib.error.HTTPError(
        "https://api.reuse.software", 503, "Unavailable", Message(), io.BytesIO(b"")
    )
    assert not reuse_compliant(REPO, opener(error))
    assert error.closed


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


# A classic branch protection as GitHub answers it, as an existing repository may
# still have it from before the blueprint: the old names of checks and an approval.
CLASSIC = {
    "required_status_checks": {"strict": True, "contexts": ["test", "build"]},
    "required_pull_request_reviews": {
        "required_approving_review_count": 1,
        "require_code_owner_reviews": True,
        "require_last_push_approval": True,
    },
    "restrictions": {"users": [], "teams": [], "apps": []},
    "required_signatures": {"enabled": True},
    "required_linear_history": {"enabled": False},
    "required_conversation_resolution": {"enabled": True},
    "lock_branch": {"enabled": True},
    "enforce_admins": {"enabled": True},
    "allow_force_pushes": {"enabled": False},
}


def test_a_classic_branch_protection_is_reported_and_left_to_a_person(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    github.protection = CLASSIC

    assert run(github, root, "settings", "apply") == 1

    out = capsys.readouterr().out
    assert (
        "branch protection main: GitHub has"
        ' "the checks build, test; a branch that is up to date; 1 approving review;'
        " a review of the code owners; an approval of the last push; pushes only of"
        " the people, teams and apps that it names; signed commits; resolved"
        " conversations; a locked branch, which takes no change at all; all of it of"
        ' the administrators as well", the configuration wants "none"'
    ) in out
    assert (
        "remove it with gh api --method DELETE"
        " repos/Dennis-Otto/demo/branches/main/protection, or under"
        " https://github.com/Dennis-Otto/demo/settings/branches"
    ) in out
    # A person may have set it on purpose: the settings never remove it.
    assert not any(
        method == "DELETE" and path.endswith("/protection")
        for method, path in github.calls
    )


@pytest.mark.parametrize(
    ("protection", "requires"),
    [
        ({}, "present"),
        (
            {"required_pull_request_reviews": {"required_approving_review_count": 0}},
            "a pull request",
        ),
        (
            {
                "required_status_checks": {"strict": False, "contexts": []},
                "required_pull_request_reviews": {"required_approving_review_count": 2},
                "restrictions": None,
                "enforce_admins": {"enabled": False},
            },
            "2 approving reviews",
        ),
    ],
)
def test_a_classic_branch_protection_says_what_it_requires(
    github: FakeGitHub, protection: dict[str, Any], requires: str
) -> None:
    github.protection = protection

    (drift,) = check_classic_protection(Api(github), REPO)

    assert (drift.setting, drift.want, drift.have) == (
        "branch protection main",
        "none",
        requires,
    )


def test_a_branch_without_a_classic_protection_has_nothing_to_report(
    github: FakeGitHub,
) -> None:
    assert check_classic_protection(Api(github), REPO) == []


def test_a_private_repository_on_its_plan_has_no_classic_protection_to_read(
    github: FakeGitHub,
) -> None:
    path = f"repos/{REPO}/branches/main/protection"
    github.fail[("GET", path)] = (403, RULESETS_REFUSAL)

    assert check_classic_protection(Api(github), REPO, private=True) == []
    # A public repository has every part: such an answer there still fails.
    with pytest.raises(GitHubError, match="403"):
        check_classic_protection(Api(github), REPO)


def test_the_checklist_names_a_classic_branch_protection(
    github: FakeGitHub, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run(github, root, "settings", "apply")
    capsys.readouterr()
    run(github, root, "checklist")
    assert "  ✔ No classic branch protection of main, only the rulesets" in (
        capsys.readouterr().out.splitlines()
    )
    github.protection = {
        "required_pull_request_reviews": {"required_approving_review_count": 1}
    }

    assert run(github, root, "checklist") == 1

    lines = capsys.readouterr().out.splitlines()
    step = lines.index("  ✘ No classic branch protection of main, only the rulesets")
    assert (
        lines[step + 1]
        .strip()
        .startswith("it requires 1 approving review: the rulesets protect main")
    )
    # A protection whose switches are all off still exists, and the line says so.
    github.protection = {"required_signatures": {"enabled": False}}

    assert run(github, root, "checklist") == 1

    lines = capsys.readouterr().out.splitlines()
    step = lines.index("  ✘ No classic branch protection of main, only the rulesets")
    assert lines[step + 1].strip().startswith("it exists: the rulesets protect main")
    # Not a part of the settings that settings apply could set.
    assert "  ✔ Settings as code applied" in lines
