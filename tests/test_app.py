"""Tests of blueprint.py app, against a simulated git, gh and Copier and a fake browser,
whose requests reach the local server of the command over a real socket."""

from __future__ import annotations

import codecs
import json
import re
import shlex
import subprocess
import sys
import threading
import urllib.error
import urllib.request
import webbrowser
from collections.abc import Callable, Sequence
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from blueprint import app as app_module
from blueprint import cli
from blueprint.app import (
    APP_ID,
    BRANCH,
    CALLBACK,
    CLIENT_ID,
    COPIERS,
    KEY_FILE,
    KEY_NAME,
    MESSAGE,
    NAME,
    PINNED,
    SLICE,
    App,
    AppError,
    Made,
    Waiting,
    answered_app,
    connect,
    manifest,
    read_key,
    register,
    run_command,
    wait_for_code,
)
from blueprint.bootstrap import PUSH_AS_GH, CreateError
from blueprint.checklist import RELEASE_APP_PERMISSIONS, release_app
from blueprint.github import Api, GitHubError
from blueprint.settings import Settings

ROOT = Path(__file__).parents[1]
REPO = "octo-org/demo"
ANSWERS = """\
# Changes here will be overwritten by Copier; NEVER EDIT MANUALLY
_commit: v1.0.0
_src_path: gh:Dennis-Otto/repo-blueprint
owner: octo-org
project_slug: demo
"""
NAMED = (
    ANSWERS + "release_app: octo-org-release-automation\n"
    "release_app_client_id: Iv23liExample\n"
    "release_app_id: '4242'\n"
)
# Made of parts, so that no scanner takes it for a key: it is none.
PEM = (
    "-----BEGIN RSA " + "PRIVATE KEY-----\nnot-a-real-key-7f3a\n-----END RSA KEY-----\n"
)
CLIENT_SECRET = "client-secret-9c1e"
WEBHOOK_SECRET = "webhook-secret-44d2"
CODE = "code-a1b2"
EXCHANGE = f"gh api --method POST app-manifests/{CODE}/conversions"
APP = App("octo-org-release-automation", "Iv23liExample", "4242")
SECRET_SET = f"gh secret set {KEY_NAME} --env release --repo {REPO}"
DATA = (
    "--data release_app=octo-org-release-automation"
    " --data release_app_client_id=Iv23liExample --data release_app_id=4242"
)
COPIER_UPDATE = f"{COPIERS[0]} --defaults --vcs-ref=:current: {DATA}"
PUSH = shlex.join([*PUSH_AS_GH, "push", "--set-upstream", "origin", "HEAD"])
NAMING = [
    f"git switch --create {BRANCH}",
    COPIER_UPDATE,
    "git add --all",
    f"git commit --signoff --message {shlex.quote(MESSAGE)}",
    PUSH,
    "gh pr create --fill",
]
PULL = "https://github.com/octo-org/demo/pull/7"
INSTALL = "https://github.com/apps/octo-org-release-automation/installations/new"


def done(stdout: str = "", code: int = 0, stderr: str = "") -> Any:
    return subprocess.CompletedProcess([], code, stdout, stderr)


def conversion(**changes: Any) -> str:
    """What GitHub answers for the code, with a secret that nothing may use but the key."""
    data = {
        "id": 4242,
        "slug": APP.name,
        "client_id": APP.client_id,
        "client_secret": CLIENT_SECRET,
        "webhook_secret": WEBHOOK_SECRET,
        "pem": PEM,
        "owner": {"login": "octo-org"},
        **changes,
    }
    return json.dumps(data)


class Shell:
    """A simulated git, gh and Copier, which answer each command as the test plans it
    and write it down, with what it got on its stdin."""

    def __init__(self, account: str = "Organization") -> None:
        self.calls: list[str] = []
        self.stdin: dict[str, str] = {}
        self.answers: dict[str, Any] = {
            "gh api user": done(json.dumps({"login": "octocat"})),
            "gh api users/octo-org": done(json.dumps({"type": account})),
            "gh api user/memberships/orgs/octo-org": done(
                json.dumps({"role": "admin"})
            ),
            f"gh api repos/{REPO}/environments/release": done("{}"),
            EXCHANGE: done(conversion()),
            "gh pr create --fill": done(PULL + "\n"),
            "git branch --show-current": done("main\n"),
            f"git rev-parse --verify --quiet refs/heads/{BRANCH}": done(code=1),
        }

    def __call__(
        self, arguments: Sequence[str], folder: Path, stdin: str = ""
    ) -> subprocess.CompletedProcess[str]:
        line = shlex.join(arguments)
        self.calls.append(line)
        if stdin:
            self.stdin[line] = stdin
        answer = self.answers.get(line, done())
        if isinstance(answer, Exception):
            raise answer
        result: subprocess.CompletedProcess[str] = answer
        return result

    def gone(self, program: str) -> None:
        self.answers[f"{program} --version"] = FileNotFoundError(program)


class Form(HTMLParser):
    """The form of a page, as a browser reads it."""

    def __init__(self) -> None:
        super().__init__()
        self.action = ""
        self.method = ""
        self.fields: dict[str, str] = {}
        self.script = ""
        self.in_script = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        found = {key: value or "" for key, value in attrs}
        if tag == "form":
            self.action = found["action"]
            self.method = found["method"]
        elif tag == "input":
            self.fields[found["name"]] = found["value"]
        self.in_script = tag == "script"

    def handle_data(self, data: str) -> None:
        if self.in_script:
            self.script += data


def fetch(address: str, host: str = "") -> tuple[int, str]:
    """A request as a browser makes it on this machine, past any proxy."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(address)
    if host:
        request.add_header("Host", host)
    try:
        with opener.open(request, timeout=10) as response:
            return int(response.status), response.read().decode()
    except urllib.error.HTTPError as error:
        with error:
            return error.code, error.read().decode()


class Browser:
    """A browser whose owner confirms the page on GitHub, or does what the test says."""

    def __init__(
        self,
        code: str | None = CODE,
        state: str | None = None,
        after: Callable[[], None] | None = None,
        opened: bool = True,
    ) -> None:
        self.code = code
        self.state = state
        self.after = after
        self.opened = opened
        self.form = Form()
        self.manifest: dict[str, Any] = {}
        self.addresses: list[str] = []
        self.answers: list[tuple[int, str]] = []

    @property
    def action(self) -> Any:
        return urlsplit(self.form.action)

    def __call__(self, address: str) -> bool:
        self.addresses.append(address)
        status, page = fetch(address)
        assert status == 200
        self.form.feed(page)
        self.manifest = json.loads(self.form.fields["manifest"])
        state = parse_qs(self.action.query)["state"][0]
        query = "&".join(
            [
                *([f"code={self.code}"] if self.code is not None else []),
                f"state={self.state or state}",
            ]
        )
        self.answers.append(fetch(f"{self.manifest['redirect_url']}?{query}"))
        if self.after:
            self.after()
        return self.opened


@pytest.fixture
def copy(tmp_path: Path) -> Path:
    (tmp_path / ".copier-answers.yml").write_text(ANSWERS, encoding="utf-8")
    return tmp_path


@pytest.fixture
def shell() -> Shell:
    return Shell()


def everything(folder: Path) -> str:
    """The text of each file below the folder."""
    return "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in folder.rglob("*")
        if path.is_file()
    )


# ------------------------------------------------------------------- the whole command


def test_register_goes_from_the_manifest_to_the_pull_request_for_an_organization(
    copy: Path, shell: Shell, capsys: pytest.CaptureFixture[str]
) -> None:
    browser = Browser()

    assert register(copy, run=shell, browser=browser, timeout=5) == APP

    # The page of the organization, with a state that only this run knows.
    assert browser.form.method == "post"
    assert (
        f"{browser.action.scheme}://{browser.action.netloc}{browser.action.path}"
        == "https://github.com/organizations/octo-org/settings/apps/new"
    )
    assert len(parse_qs(browser.action.query)["state"][0]) >= 40
    assert "submit()" in browser.form.script
    assert browser.answers[0][0] == 200
    # Only the private key of the answer goes on, on the stdin of gh.
    assert shell.stdin == {SECRET_SET: PEM}
    # The key is set first: it comes once, and the answers can be written again.
    start = shell.calls.index(EXCHANGE)
    assert shell.calls[start:] == [EXCHANGE, SECRET_SET, *NAMING]
    out = capsys.readouterr().out
    assert (
        "Registered octo-org-release-automation on octo-org: https://github.com/"
        "organizations/octo-org/settings/apps/octo-org-release-automation"
    ) in out
    assert f"The pull request that names it: {PULL}" in out
    assert f"Install the app on {REPO}: {INSTALL}" in out
    assert "2. Merge the pull request" in out
    # The further repository starts from these lines, without copying them by hand.
    for line in (
        "release_app: octo-org-release-automation",
        "release_app_client_id: Iv23liExample",
        'release_app_id: "4242"',
        f"app connect --key-file {KEY_FILE}",
    ):
        assert line in out


def test_register_uses_the_page_of_the_user_for_an_account_of_its_own(
    copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (copy / ".copier-answers.yml").write_text(
        ANSWERS.replace("octo-org", "octocat"), encoding="utf-8"
    )
    shell = Shell("User")
    shell.answers["gh api users/octocat"] = done(json.dumps({"type": "User"}))
    shell.answers["gh api repos/octocat/demo/environments/release"] = done("{}")
    shell.answers[EXCHANGE] = done(conversion(owner={"login": "OctoCat"}))
    browser = Browser()

    register(copy, run=shell, browser=browser, timeout=5)

    assert browser.action.netloc == "github.com"
    assert browser.action.path == "/settings/apps/new"
    assert "gh api user/memberships/orgs/octocat" not in shell.calls
    out = capsys.readouterr().out
    assert "octocat is the account that gh is signed in as" in out
    assert "https://github.com/settings/apps/octo-org-release-automation" in out


def test_the_manifest_asks_for_every_permission_without_a_webhook(
    copy: Path, shell: Shell
) -> None:
    browser = Browser()

    register(copy, run=shell, browser=browser, timeout=5)

    sent = browser.manifest
    assert sent["name"] == "octo-org-release-automation"
    assert sent["url"] == "https://github.com/octo-org"
    assert "Repo Blueprint" in sent["description"]
    assert sent["public"] is False
    assert sent["hook_attributes"] == {
        "url": "https://github.com/octo-org",
        "active": False,
    }
    assert re.fullmatch(r"http://127\.0\.0\.1:\d+/callback", sent["redirect_url"])
    assert sent["default_permissions"] == {
        "actions": "write",
        "actions_variables": "write",
        "administration": "write",
        "checks": "write",
        "statuses": "write",
        "contents": "write",
        "vulnerability_alerts": "write",
        "issues": "write",
        "pages": "write",
        "pull_requests": "write",
        "workflows": "write",
        "environments": "read",
        "secrets": "read",
    }
    # Every permission of the checklist, which the old link couldn't do for Variables.
    assert all(key for _, key, _ in RELEASE_APP_PERMISSIONS)


def test_the_private_key_reaches_neither_a_file_nor_the_terminal(
    copy: Path, shell: Shell, capsys: pytest.CaptureFixture[str]
) -> None:
    before = {path for path in copy.rglob("*")}

    register(copy, run=shell, browser=Browser(), timeout=5)

    assert {path for path in copy.rglob("*")} == before
    captured = capsys.readouterr()
    for secret in ("not-a-real-key", CLIENT_SECRET, WEBHOOK_SECRET, CODE):
        assert secret not in captured.out
        assert secret not in captured.err
        assert secret not in everything(copy)
    # Nor the arguments of a command, which any process of the machine can read.
    assert not [line for line in shell.calls if "not-a-real-key" in line]


def test_no_repr_shows_the_private_key() -> None:
    assert "not-a-real-key" not in repr(Made(APP, "octo-org", PEM))


def test_the_state_of_the_page_stays_on_no_disk_and_no_terminal(
    copy: Path, shell: Shell, capsys: pytest.CaptureFixture[str]
) -> None:
    browser = Browser()

    register(copy, run=shell, browser=browser, timeout=5)

    state = parse_qs(browser.action.query)["state"][0]
    captured = capsys.readouterr()
    assert state not in captured.out
    assert state not in captured.err
    assert state not in everything(copy)


def test_each_run_has_a_state_and_a_port_of_its_own() -> None:
    with Waiting("octo-org", True) as first, Waiting("octo-org", True) as second:
        assert first.state != second.state
        assert first.address != second.address
        assert first.address.startswith("http://127.0.0.1:")


def test_no_update_prints_the_commands_and_runs_none_of_them(
    copy: Path, shell: Shell, capsys: pytest.CaptureFixture[str]
) -> None:
    # With it, neither changes in the folder nor a missing Copier stop the command.
    shell.answers["git status --porcelain"] = done(" M README.md\n")
    shell.gone("uvx")
    shell.gone("pipx")
    shell.gone("copier")

    register(copy, update=False, run=shell, browser=Browser(), timeout=5)

    assert shell.stdin == {SECRET_SET: PEM}
    for line in NAMING:
        assert line not in shell.calls
    out = capsys.readouterr().out
    for line in NAMING:
        assert f"  {line}\n" in out
    assert INSTALL in out


# ------------------------------------------------------------------- the way back


def test_a_wrong_state_trades_no_code_and_ends_at_the_timeout(
    copy: Path, shell: Shell, capsys: pytest.CaptureFixture[str]
) -> None:
    browser = Browser(state="not-the-state-of-this-run")

    with pytest.raises(AppError, match=r"didn't come back within 0\.2 seconds"):
        register(copy, run=shell, browser=browser, timeout=0.2)

    assert browser.answers[0][0] == 400
    assert "refused" in browser.answers[0][1]
    assert EXCHANGE not in shell.calls
    assert not shell.stdin
    assert "Refused an answer" in capsys.readouterr().err


def test_a_wrong_state_doesnt_end_the_wait_of_the_owner(
    copy: Path, shell: Shell
) -> None:
    """Any page can call the address; the answer of GitHub still comes through."""
    browser = Browser(state="not-the-state-of-this-run")

    def confirmed() -> None:
        state = parse_qs(browser.action.query)["state"][0]
        fetch(f"{browser.manifest['redirect_url']}?code={CODE}&state={state}")

    browser.after = confirmed

    assert register(copy, run=shell, browser=browser, timeout=5) == APP
    assert shell.calls.count(EXCHANGE) == 1


def test_a_state_of_no_value_is_refused(copy: Path, shell: Shell) -> None:
    server = Waiting("octo-org", True)
    results: list[int] = []

    def strange(address: str) -> bool:
        results.append(fetch(f"{address}{CALLBACK}?code={CODE}")[0])
        results.append(fetch(f"{address}{CALLBACK}?code={CODE}&state=%C3%BF")[0])
        return True

    with server, pytest.raises(AppError, match="didn't come back"):
        wait_for_code(server, strange, 0.1)

    assert results == [400, 400]


def test_a_timeout_sets_nothing(
    copy: Path, shell: Shell, capsys: pytest.CaptureFixture[str]
) -> None:
    shown: list[str] = []

    def closed(address: str) -> bool:
        shown.append(address)
        return True

    with pytest.raises(AppError, match="closed or wasn't confirmed"):
        register(copy, run=shell, browser=closed, timeout=0.1)

    assert EXCHANGE not in shell.calls
    assert not [
        line for line in shell.calls if "secret" in line or "git switch" in line
    ]
    assert shown[0] in capsys.readouterr().out


def test_a_cancelled_page_sets_nothing(copy: Path, shell: Shell) -> None:
    browser = Browser(code=None)

    with pytest.raises(AppError, match="The page was cancelled"):
        register(copy, run=shell, browser=browser, timeout=5)

    assert "GitHub sent no app" in browser.answers[0][1]
    assert EXCHANGE not in shell.calls


def test_stopping_the_command_sets_nothing(copy: Path, shell: Shell) -> None:
    def interrupted(address: str) -> bool:
        raise KeyboardInterrupt

    with pytest.raises(AppError, match="Stopped before GitHub came back"):
        register(copy, run=shell, browser=interrupted, timeout=5)

    assert EXCHANGE not in shell.calls


def test_the_wait_comes_in_slices_so_that_stopping_reaches_it() -> None:
    """On Windows before Python 3.14, Ctrl+C reaches a long wait only at its end."""
    waits: list[float] = []

    class Stopped(threading.Event):
        def wait(self, timeout: float | None = None) -> bool:
            assert timeout is not None
            waits.append(timeout)
            if len(waits) == 3:
                raise KeyboardInterrupt
            return False

    server = Waiting("octo-org", True)
    server.arrived = Stopped()

    with server, pytest.raises(AppError, match="Stopped before GitHub came back"):
        wait_for_code(server, lambda address: True, 600)

    assert len(waits) == 3
    assert all(wait <= SLICE for wait in waits)


@pytest.mark.parametrize("browser", [None, lambda address: False])
def test_without_a_browser_the_command_says_where_to_go(
    copy: Path,
    shell: Shell,
    capsys: pytest.CaptureFixture[str],
    browser: Callable[[str], bool] | None,
) -> None:
    with pytest.raises(AppError, match="didn't come back"):
        register(copy, run=shell, browser=browser, timeout=0.05)

    out = capsys.readouterr().out
    assert "http://127.0.0.1:" in out
    assert "forward the port" in out


def test_a_browser_that_python_cant_find_only_leaves_the_address(
    copy: Path, shell: Shell, capsys: pytest.CaptureFixture[str]
) -> None:
    def broken(address: str) -> bool:
        raise webbrowser.Error("could not locate runnable browser")

    with pytest.raises(AppError, match="didn't come back"):
        register(copy, run=shell, browser=broken, timeout=0.05)

    assert "forward the port" in capsys.readouterr().out


def test_a_browser_that_opened_gets_no_hint_about_forwarding(
    copy: Path, shell: Shell, capsys: pytest.CaptureFixture[str]
) -> None:
    register(copy, run=shell, browser=Browser(), timeout=5)

    assert "forward the port" not in capsys.readouterr().out


def test_the_server_answers_only_for_its_own_address_and_pages() -> None:
    with Waiting("octo-org", True) as server:
        thread = threading.Thread(target=server.serve_forever, args=(0.01,))
        thread.start()
        try:
            # A stranger's page under a name that points here reads no state.
            status, page = fetch(server.address, host="evil.example")
            assert status == 403
            assert server.state not in page
            assert fetch(f"{server.address}/favicon.ico")[0] == 404
            assert fetch(server.address)[0] == 200
        finally:
            server.shutdown()
            thread.join()
    assert not server.arrived.is_set()


def test_the_form_escapes_what_it_sends() -> None:
    with Waiting("octo-org", True) as server:
        form = Form()
        form.feed(server.form)
    # The JSON has quotes, which end an attribute unless they are escaped.
    assert '"name"' not in server.form
    assert json.loads(form.fields["manifest"]) == manifest("octo-org", server.address)
    assert form.action == (
        "https://github.com/organizations/octo-org/settings/apps/new"
        f"?state={server.state}"
    )


def test_a_browser_that_goes_away_is_no_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with Waiting("octo-org", True) as server:
        server.handle_error(None, (app_module.LOCAL, 1))
    assert capsys.readouterr().err == ""


# ------------------------------------------------------------------- what comes back


def test_a_refused_trade_says_what_gh_said(copy: Path, shell: Shell) -> None:
    shell.answers[EXCHANGE] = done(code=1, stderr="gh: Not Found (HTTP 404)")

    with pytest.raises(AppError) as error:
        register(copy, run=shell, browser=Browser(), timeout=5)

    assert "gh: Not Found (HTTP 404)" in str(error.value)
    assert "https://github.com/organizations/octo-org/settings/apps/" in str(
        error.value
    )
    assert CODE not in str(error.value)
    assert SECRET_SET not in shell.calls


@pytest.mark.parametrize(
    "answer",
    [
        "not json",
        "[]",
        conversion(slug=""),
        conversion(client_id=""),
        conversion(id=""),
        conversion(pem=""),
        conversion(owner={}),
        conversion(owner="octo-org"),
    ],
)
def test_an_answer_without_a_whole_app_shows_nothing_of_it(
    copy: Path, shell: Shell, answer: str
) -> None:
    shell.answers[EXCHANGE] = done(answer)

    with pytest.raises(AppError, match="names no complete app") as error:
        register(copy, run=shell, browser=Browser(), timeout=5)

    for secret in ("not-a-real-key", CLIENT_SECRET, WEBHOOK_SECRET):
        assert secret not in str(error.value)
    assert SECRET_SET not in shell.calls


def test_an_app_on_another_account_stops_before_its_key_is_set(
    copy: Path, shell: Shell
) -> None:
    """The browser is signed in as someone other than the owner of the repository."""
    shell.answers[EXCHANGE] = done(conversion(owner={"login": "someone"}))

    with pytest.raises(AppError) as error:
        register(copy, run=shell, browser=Browser(), timeout=5)

    message = str(error.value)
    assert "on someone" in message
    assert (
        "https://github.com/settings/apps/octo-org-release-automation/advanced"
        in message
    )
    assert not shell.stdin
    assert not [line for line in shell.calls if line.startswith("git switch")]


def test_a_refused_key_says_how_to_go_on_without_showing_it(
    copy: Path, shell: Shell
) -> None:
    shell.answers[SECRET_SET] = done(code=1, stderr="HTTP 403: Resource not accessible")

    with pytest.raises(AppError) as error:
        register(copy, run=shell, browser=Browser(), timeout=5)

    message = str(error.value)
    assert "HTTP 403: Resource not accessible" in message
    assert "not-a-real-key" not in message
    assert (
        "https://github.com/organizations/octo-org/settings/apps/"
        "octo-org-release-automation, on the tab Credentials" in message
    )
    # The values it would have named are not lost.
    assert (
        "python3 .github/blueprint.py app connect --name octo-org-release-automation"
        " --client-id Iv23liExample --app-id 4242 --key-file private-key.pem" in message
    )
    assert not [line for line in shell.calls if line.startswith("git switch")]


@pytest.mark.parametrize(
    ("step", "place"),
    [(COPIER_UPDATE, 1), (PUSH, 4), ("gh pr create --fill", 5)],
)
def test_a_step_that_fails_leaves_the_steps_to_run_by_hand(
    copy: Path, shell: Shell, step: str, place: int
) -> None:
    shell.answers[step] = done(code=1, stderr="it failed")

    with pytest.raises(AppError) as error:
        register(copy, run=shell, browser=Browser(), timeout=5)

    message = str(error.value)
    assert f"{step} failed: it failed" in message
    assert "The private key is set" in message
    for line in NAMING[place:]:
        assert f"  {line}" in message
    for line in NAMING[:place]:
        assert f"  {line}" not in message
    # Its key is set already, and nothing runs after the step that failed.
    assert shell.stdin == {SECRET_SET: PEM}
    assert shell.calls[-1] == step


# ------------------------------------------------------------------- the preflight


def stopped(
    copy: Path, shell: Shell, capsys: pytest.CaptureFixture[str], **options: Any
) -> str:
    """What the preflight shows when it stops the command before the browser."""

    def never(address: str) -> bool:
        raise AssertionError("the browser opened")

    with pytest.raises(AppError, match="nothing is changed"):
        register(copy, run=shell, browser=never, timeout=0.01, **options)
    assert EXCHANGE not in shell.calls
    return capsys.readouterr().out


def test_the_preflight_shows_what_it_checked(
    copy: Path, shell: Shell, capsys: pytest.CaptureFixture[str]
) -> None:
    register(copy, run=shell, browser=Browser(), timeout=5)

    out = capsys.readouterr().out.splitlines()
    assert out[:8] == [
        f"The preflight of {REPO}:",
        "  ✔ gh is signed in to github.com as octocat",
        "  ✔ octo-org is an organization that octocat owns",
        f"  ✔ {REPO} has the environment release",
        "  ✔ This folder has no changes that a commit doesn't hold",
        "  ✔ This folder is on main, where the pull request starts",
        f"  ✔ No branch {BRANCH} is left of an earlier attempt",
        "  ✔ Copier runs with uvx",
    ]


def test_gh_has_to_be_installed(
    copy: Path, shell: Shell, capsys: pytest.CaptureFixture[str]
) -> None:
    shell.gone("gh")
    out = stopped(copy, shell, capsys)
    assert "✘ GitHub CLI is not installed" in out
    assert "https://github.com/cli/cli#installation" in out


@pytest.mark.parametrize(
    ("answer", "said"),
    [
        (done(code=1, stderr="To get started, run: gh auth login"), "run: gh auth"),
        (done(code=1), "gh said nothing"),
        (done("{}"), "{}"),
    ],
)
def test_gh_has_to_be_signed_in(
    copy: Path,
    shell: Shell,
    capsys: pytest.CaptureFixture[str],
    answer: Any,
    said: str,
) -> None:
    shell.answers["gh api user"] = answer
    out = stopped(copy, shell, capsys)
    assert "✘ gh is not signed in to github.com:" in out
    assert said in out
    assert "gh auth login --hostname github.com --scopes workflow" in out


def test_the_app_goes_on_the_owner_of_the_repository_alone(
    copy: Path, shell: Shell, capsys: pytest.CaptureFixture[str]
) -> None:
    out = stopped(copy, shell, capsys, org="another-org")
    assert "✘ An app of another-org can't be installed on octo-org/demo" in out
    assert "--org octo-org" in out


def test_org_names_the_organization_even_when_github_doesnt_say(
    copy: Path, shell: Shell
) -> None:
    shell.answers["gh api users/octo-org"] = done(code=1, stderr="gh: HTTP 502")
    browser = Browser()

    register(copy, org="OCTO-ORG", run=shell, browser=browser, timeout=5)

    assert browser.action.path == "/organizations/octo-org/settings/apps/new"


def test_the_owner_has_to_exist(
    copy: Path, shell: Shell, capsys: pytest.CaptureFixture[str]
) -> None:
    shell.answers["gh api users/octo-org"] = done(
        code=1, stderr="gh: Not Found (HTTP 404)"
    )
    out = stopped(copy, shell, capsys)
    assert "✘ GitHub has no account or organization octo-org" in out


def test_an_owner_that_github_doesnt_tell_stops_nothing(
    copy: Path, shell: Shell, capsys: pytest.CaptureFixture[str]
) -> None:
    shell.answers["gh api users/octo-org"] = done(code=1, stderr="gh: HTTP 502")
    browser = Browser()

    register(copy, run=shell, browser=browser, timeout=5)

    assert (
        "· GitHub didn't say who octo-org is: gh: HTTP 502" in capsys.readouterr().out
    )
    # The page of the user: on an organization, GitHub would show it as its own error.
    assert browser.action.path == "/settings/apps/new"


def test_the_account_of_a_user_has_to_be_the_one_of_gh(
    copy: Path, shell: Shell, capsys: pytest.CaptureFixture[str]
) -> None:
    shell.answers["gh api users/octo-org"] = done(json.dumps({"type": "User"}))
    out = stopped(copy, shell, capsys)
    assert "✘ octo-org is an account of its own, and gh is signed in as octocat" in out
    assert "gh auth switch --user octo-org" in out


def test_a_stranger_to_the_organization_stops(
    copy: Path, shell: Shell, capsys: pytest.CaptureFixture[str]
) -> None:
    shell.answers["gh api user/memberships/orgs/octo-org"] = done(
        code=1, stderr="gh: Not Found (HTTP 404)"
    )
    out = stopped(copy, shell, capsys)
    assert "✘ octocat is no member of the organization octo-org" in out


@pytest.mark.parametrize(
    "answer",
    [
        done(json.dumps({"role": "member"})),
        done(code=1, stderr="gh: must have read:org (HTTP 403)"),
    ],
)
def test_a_member_of_the_organization_may_manage_its_apps(
    copy: Path, shell: Shell, capsys: pytest.CaptureFixture[str], answer: Any
) -> None:
    shell.answers["gh api user/memberships/orgs/octo-org"] = answer

    register(copy, run=shell, browser=Browser(), timeout=5)

    assert "· octo-org is an organization, and only its owners" in (
        capsys.readouterr().out
    )


def test_the_environment_has_to_exist_before_the_key_comes_once(
    copy: Path, shell: Shell, capsys: pytest.CaptureFixture[str]
) -> None:
    shell.answers[f"gh api repos/{REPO}/environments/release"] = done(
        code=1, stderr="gh: Not Found (HTTP 404)"
    )
    out = stopped(copy, shell, capsys)
    assert f"✘ {REPO} has no environment release" in out
    assert "python3 .github/blueprint.py settings apply" in out


def test_an_environment_that_github_doesnt_tell_stops_nothing(
    copy: Path, shell: Shell, capsys: pytest.CaptureFixture[str]
) -> None:
    shell.answers[f"gh api repos/{REPO}/environments/release"] = done(
        code=1, stderr="gh: HTTP 502"
    )

    register(copy, run=shell, browser=Browser(), timeout=5)

    assert (
        f"· GitHub didn't say whether {REPO} has release: gh: HTTP 502"
        in capsys.readouterr().out
    )


def test_changes_in_the_folder_stop_it_as_they_would_stop_copier(
    copy: Path, shell: Shell, capsys: pytest.CaptureFixture[str]
) -> None:
    shell.answers["git status --porcelain"] = done(" M README.md\n")
    out = stopped(copy, shell, capsys)
    assert "✘ This folder has changes that no commit holds" in out
    assert "--no-update" in out


def test_another_branch_stops_it_as_it_would_come_along_in_the_pull_request(
    copy: Path, shell: Shell, capsys: pytest.CaptureFixture[str]
) -> None:
    shell.answers["git branch --show-current"] = done("feature\n")
    out = stopped(copy, shell, capsys)
    assert "✘ This folder isn't on main" in out
    assert "git switch main" in out


def test_the_branch_of_an_earlier_attempt_stops_it_before_the_browser(
    copy: Path, shell: Shell, capsys: pytest.CaptureFixture[str]
) -> None:
    shell.answers[f"git rev-parse --verify --quiet refs/heads/{BRANCH}"] = done("abc\n")
    out = stopped(copy, shell, capsys)
    assert f"✘ The branch {BRANCH} is left of an earlier attempt" in out
    assert f"git branch -D {BRANCH}" in out


def test_a_folder_that_git_cant_read_stops_it(
    copy: Path, shell: Shell, capsys: pytest.CaptureFixture[str]
) -> None:
    shell.answers["git status --porcelain"] = done(code=128, stderr="not a repository")
    out = stopped(copy, shell, capsys)
    assert "✘ Git can't read this folder" in out


def test_copier_runs_with_the_first_program_that_is_there(
    copy: Path, shell: Shell, capsys: pytest.CaptureFixture[str]
) -> None:
    shell.gone("uvx")

    register(copy, run=shell, browser=Browser(), timeout=5)

    assert "✔ Copier runs with pipx" in capsys.readouterr().out
    assert f"{COPIERS[1]} --defaults --vcs-ref=:current: {DATA}" in shell.calls
    assert COPIER_UPDATE not in shell.calls


def test_a_copier_of_the_owner_runs_last(copy: Path, shell: Shell) -> None:
    shell.gone("uvx")
    shell.answers["pipx --version"] = done(code=1)

    register(copy, run=shell, browser=Browser(), timeout=5)

    assert f"copier update --defaults --vcs-ref=:current: {DATA}" in shell.calls


def test_no_copier_stops_it_before_the_browser(
    copy: Path, shell: Shell, capsys: pytest.CaptureFixture[str]
) -> None:
    shell.gone("uvx")
    shell.gone("pipx")
    shell.gone("copier")
    out = stopped(copy, shell, capsys)
    assert "✘ Neither uv, pipx nor Copier is installed" in out
    assert "https://docs.astral.sh/uv/" in out


def test_register_makes_no_second_app(
    copy: Path, shell: Shell, capsys: pytest.CaptureFixture[str]
) -> None:
    (copy / ".copier-answers.yml").write_text(NAMED, encoding="utf-8")
    out = stopped(copy, shell, capsys)
    assert "✘ .copier-answers.yml names the release app" in out
    assert f"app connect --key-file {KEY_FILE}" in out


def test_several_problems_are_counted(
    copy: Path, shell: Shell, capsys: pytest.CaptureFixture[str]
) -> None:
    shell.answers["git status --porcelain"] = done(" M README.md\n")
    shell.gone("uvx")
    shell.gone("pipx")
    shell.gone("copier")

    with pytest.raises(AppError, match="found 2 problems"):
        register(copy, run=shell, browser=None, timeout=0.01)


def test_a_folder_without_answers_needs_the_repository_named(
    tmp_path: Path, shell: Shell
) -> None:
    with pytest.raises(CreateError, match="names no owner"):
        register(tmp_path, run=shell, browser=None, timeout=0.01)


# ------------------------------------------------------------------- app connect


def key_file(folder: Path, text: str = PEM) -> Path:
    # Outside the copy, as in the folder of the downloads.
    path = folder.parent / f"{folder.name}-key.pem"
    path.write_text(text, encoding="utf-8")
    return path


def test_connect_sets_the_key_and_names_the_app_from_the_command_line(
    copy: Path, shell: Shell, capsys: pytest.CaptureFixture[str]
) -> None:
    key = key_file(copy)

    connected = connect(
        copy,
        key,
        name=APP.name,
        client_id=APP.client_id,
        app_id=APP.app_id,
        run=shell,
    )

    assert connected == APP
    assert shell.stdin == {SECRET_SET: PEM}
    assert shell.calls[shell.calls.index(SECRET_SET) :] == [SECRET_SET, *NAMING]
    # An app that exists registers nothing, so its owner is no question.
    assert "gh api users/octo-org" not in shell.calls
    captured = capsys.readouterr()
    assert PEM.splitlines()[1] not in captured.out + captured.err
    assert f"The pull request that names it: {PULL}" in captured.out
    assert INSTALL in captured.out
    assert f"delete {key}" in captured.out
    # The file is the owner's, and only they say that it is no longer needed.
    assert key.read_text(encoding="utf-8") == PEM


def test_connect_with_the_answers_only_sets_the_key(
    copy: Path, shell: Shell, capsys: pytest.CaptureFixture[str]
) -> None:
    """A further repository, whose copy took the app from Copier's settings file."""
    (copy / ".copier-answers.yml").write_text(NAMED, encoding="utf-8")
    # Its answers won't change, so changes in the folder are in nobody's way.
    shell.answers["git status --porcelain"] = done(" M README.md\n")

    assert connect(copy, key_file(copy), run=shell) == APP

    assert shell.stdin == {SECRET_SET: PEM}
    assert not [line for line in shell.calls if line.startswith("git switch")]
    assert "git status --porcelain" not in shell.calls
    out = capsys.readouterr().out
    assert INSTALL in out
    assert "Merge the pull request" not in out
    assert "2. Apply the settings: python3 .github/blueprint.py settings apply" in out


def test_connect_names_another_app_than_the_answers(
    copy: Path, shell: Shell, capsys: pytest.CaptureFixture[str]
) -> None:
    (copy / ".copier-answers.yml").write_text(
        NAMED.replace("'4242'", "'1'"), encoding="utf-8"
    )

    assert connect(copy, key_file(copy), app_id="4242", run=shell) == APP

    assert COPIER_UPDATE in shell.calls


def test_connect_without_update_prints_the_commands(
    copy: Path, shell: Shell, capsys: pytest.CaptureFixture[str]
) -> None:
    shell.answers["git status --porcelain"] = done(" M README.md\n")

    connect(
        copy,
        key_file(copy),
        name=APP.name,
        client_id=APP.client_id,
        app_id=APP.app_id,
        update=False,
        run=shell,
    )

    assert shell.stdin == {SECRET_SET: PEM}
    assert COPIER_UPDATE not in shell.calls
    out = capsys.readouterr().out
    assert f"  {COPIER_UPDATE}\n" in out
    assert "Merge the pull request" in out


@pytest.mark.parametrize(
    ("values", "named"),
    [
        ({}, ["--name", "--client-id", "--app-id"]),
        ({"name": APP.name}, ["--client-id", "--app-id"]),
        ({"name": "Not A Name", "client_id": "Iv23", "app_id": "1"}, ["--name"]),
        # The two values of its settings page, swapped.
        (
            {"name": "app", "client_id": "4242", "app_id": "Iv23"},
            ["--client-id", "--app-id"],
        ),
    ],
)
def test_connect_refuses_a_name_that_cant_be_right(
    copy: Path, shell: Shell, values: dict[str, Any], named: list[str]
) -> None:
    with pytest.raises(AppError) as error:
        connect(copy, key_file(copy), run=shell, **values)

    for option in ("--name", "--client-id", "--app-id"):
        assert (option in str(error.value)) == (option in named)
    assert not shell.calls


def test_connect_refuses_a_file_without_a_key(copy: Path, shell: Shell) -> None:
    key = key_file(copy, "a secret that is no key")

    with pytest.raises(AppError, match="holds no private key") as error:
        connect(
            copy,
            key,
            name=APP.name,
            client_id=APP.client_id,
            app_id=APP.app_id,
            run=shell,
        )

    assert "a secret" not in str(error.value)
    assert not shell.calls


def test_a_key_file_that_an_editor_marked_as_unicode_loses_the_mark(
    tmp_path: Path,
) -> None:
    path = tmp_path / "key.pem"
    path.write_bytes(codecs.BOM_UTF8 + PEM.encode())

    assert read_key(path) == PEM


def test_a_key_file_that_is_no_text_is_no_key(tmp_path: Path) -> None:
    path = tmp_path / "key.pem"
    path.write_bytes(b"\xff\xfe\x00secret")

    with pytest.raises(AppError, match="holds no private key") as error:
        read_key(path)

    assert "secret" not in str(error.value)


def test_connect_stops_at_the_preflight_with_the_key_unused(
    copy: Path, shell: Shell
) -> None:
    (copy / ".copier-answers.yml").write_text(NAMED, encoding="utf-8")
    shell.answers[f"gh api repos/{REPO}/environments/release"] = done(
        code=1, stderr="gh: Not Found (HTTP 404)"
    )

    with pytest.raises(AppError, match="found 1 problem,"):
        connect(copy, key_file(copy), run=shell)

    assert not shell.stdin


def test_connect_says_what_gh_refused(copy: Path, shell: Shell) -> None:
    (copy / ".copier-answers.yml").write_text(NAMED, encoding="utf-8")
    shell.answers[SECRET_SET] = done(code=1, stderr="HTTP 403")

    with pytest.raises(AppError, match=r"refused the private key of .*HTTP 403"):
        connect(copy, key_file(copy), run=shell)

    assert COPIER_UPDATE not in shell.calls


def test_the_names_of_an_app_come_from_the_answers_as_copier_writes_them(
    tmp_path: Path,
) -> None:
    assert answered_app(tmp_path) == App()
    (tmp_path / ".copier-answers.yml").write_text(NAMED, encoding="utf-8")
    assert answered_app(tmp_path) == APP
    (tmp_path / ".copier-answers.yml").write_text(
        NAMED.replace("'4242'", '"4242"'), encoding="utf-8"
    )
    assert answered_app(tmp_path) == APP
    (tmp_path / ".copier-answers.yml").write_text(ANSWERS, encoding="utf-8")
    assert answered_app(tmp_path) == App()


def test_the_names_take_what_the_questions_of_copier_take() -> None:
    copier = (ROOT / "copier.yml").read_text(encoding="utf-8")
    for pattern in (NAME, CLIENT_ID, APP_ID):
        assert f"'^{pattern.pattern}$'" in copier


# ------------------------------------------------------------------- the command line


def test_the_command_line_registers_with_the_browser_of_the_system(
    copy: Path, shell: Shell, monkeypatch: pytest.MonkeyPatch
) -> None:
    browser = Browser()
    monkeypatch.setattr(app_module, "run_command", shell)
    monkeypatch.setattr(webbrowser, "open", browser)

    assert (
        cli.main(["app", "register", "--org", "octo-org", "--timeout", "5"], root=copy)
        == 0
    )

    assert browser.addresses
    assert shell.stdin == {SECRET_SET: PEM}
    assert COPIER_UPDATE in shell.calls


def test_the_command_line_takes_the_repository_and_no_browser(
    copy: Path,
    shell: Shell,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def never(address: str) -> bool:
        raise AssertionError("the browser opened")

    monkeypatch.setattr(app_module, "run_command", shell)
    monkeypatch.setattr(webbrowser, "open", never)
    shell.answers["gh api repos/octo-org/other/environments/release"] = done("{}")

    code = cli.main(
        [
            "--repo",
            "octo-org/other",
            "app",
            "register",
            "--no-browser",
            "--no-update",
            "--timeout",
            "0",
        ],
        root=copy,
    )

    assert code == 2
    captured = capsys.readouterr()
    assert "The preflight of octo-org/other:" in captured.out
    assert "http://127.0.0.1:" in captured.out
    assert "blueprint.py: GitHub didn't come back" in captured.err


def test_the_command_line_connects(
    copy: Path, shell: Shell, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_module, "run_command", shell)

    code = cli.main(
        [
            "app",
            "connect",
            "--key-file",
            str(key_file(copy)),
            "--name",
            APP.name,
            "--client-id",
            APP.client_id,
            "--app-id",
            APP.app_id,
            "--no-update",
        ],
        root=copy,
    )

    assert code == 0
    assert shell.stdin == {SECRET_SET: PEM}
    assert COPIER_UPDATE not in shell.calls


def test_a_key_file_that_isnt_there_is_a_plain_error(
    copy: Path, shell: Shell, capsys: pytest.CaptureFixture[str]
) -> None:
    (copy / ".copier-answers.yml").write_text(NAMED, encoding="utf-8")

    code = cli.main(
        ["app", "connect", "--key-file", str(copy / "no-such-file.pem")], root=copy
    )

    assert code == 2
    assert "blueprint.py: " in capsys.readouterr().err


# ------------------------------------------------------------------- what runs for real


def test_a_command_gets_its_stdin_byte_for_byte_and_only_a_closed_one_otherwise(
    tmp_path: Path,
) -> None:
    program = "import sys; sys.stdout.write(repr(sys.stdin.buffer.read()))"

    fed = run_command([sys.executable, "-c", program], tmp_path, PEM)
    empty = run_command([sys.executable, "-c", program], tmp_path)
    failed = run_command(
        [sys.executable, "-c", "import sys; sys.exit('it failed')"], tmp_path
    )

    # In text mode, Windows would change the line ends of the key.
    assert fed.stdout == repr(PEM.encode())
    assert empty.stdout == repr(b"")
    assert empty.returncode == 0
    assert failed.returncode == 1
    assert failed.stderr.strip() == "it failed"


def test_the_copier_is_the_one_of_the_quick_start() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"uvx --from {PINNED.removesuffix(' update')} copy gh:" in readme
    assert f"pipx run --spec {PINNED.removesuffix(' update')} copy gh:" in readme
    assert [
        f"uvx --from {PINNED}",
        f"pipx run --spec {PINNED}",
        "copier update",
    ] == list(COPIERS)
    # Renovate moves the version here with those of the pages, by this pattern.
    renovate = (ROOT / ".github/renovate.json5").read_text(encoding="utf-8")
    assert '"/^blueprint/app\\\\.py$/",' in renovate
    assert re.fullmatch(r"copier==\d+\.\d+\.\d+ copier (?:copy|update)", PINNED)


# ------------------------------------------------------------------- the checklist


CONFIG = """
[variables]
RELEASE_APP = "octo-org-release-automation"
RELEASE_AUTOMATION_CLIENT_ID = "Iv23liExample"
RELEASE_AUTOMATION_APP_ID = "4242"
"""


def fitting_api(found: int | None = 1, error: bool = False) -> Any:
    class Fake(Api):
        def __init__(self) -> None:
            self.asked: list[str] = []

        def get(self, path: str) -> Any:
            self.asked.append(path)
            if error:
                raise GitHubError(403, "Resource not accessible")
            return None if found is None else {"total_count": found}

    return Fake()


def settings_after_the_update(root: Path) -> Settings:
    """What the answers wrote into the repository once the pull request merged."""
    path = root / ".github/repository.toml"
    path.parent.mkdir(exist_ok=True)
    path.write_text(CONFIG, encoding="utf-8")
    return Settings.load(path)


def test_the_checklist_ticks_the_app_after_register_and_the_installation(
    copy: Path, shell: Shell, capsys: pytest.CaptureFixture[str]
) -> None:
    app = register(copy, run=shell, browser=Browser(), timeout=5)
    assert app == APP
    api = fitting_api()

    named, installed = release_app(api, REPO, settings_after_the_update(copy))

    assert named.done is True
    assert named.text == (
        "Release app octo-org-release-automation named in .github/repository.toml"
    )
    # GitHub opens a check suite of an installed app with Checks for each push.
    assert installed.done is True
    assert installed.how == INSTALL
    assert api.asked == [f"repos/{REPO}/commits/main/check-suites?app_id=4242"]


@pytest.mark.parametrize(
    "api", [fitting_api(0), fitting_api(None), fitting_api(error=True)]
)
def test_the_checklist_leaves_an_installation_that_it_cant_see_open(
    copy: Path, api: Any
) -> None:
    _, installed = release_app(api, REPO, settings_after_the_update(copy))

    # Never a cross: the installation may have come after the last push.
    assert installed.done is None
    assert installed.how == INSTALL
