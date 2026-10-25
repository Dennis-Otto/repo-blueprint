"""Tests of blueprint.py create against a simulated git and gh, and against a real git."""

from __future__ import annotations

import shlex
import subprocess
from collections.abc import Sequence
from pathlib import Path

import preflight
import pytest

from blueprint import bootstrap
from blueprint.bootstrap import Answer, CreateError, create, doctor

ANSWERS = """\
# Changes here will be overwritten by Copier; NEVER EDIT MANUALLY
_commit: v0.13.0
_src_path: gh:Dennis-Otto/repo-blueprint
description: A demo
owner: octo-org
project_name: Demo
project_slug: demo
"""
REPO = "octo-org/demo"
INIT = "git init --initial-branch=main"
ADD = "git add --all"
COMMIT = "git commit --signoff --message 'chore: start from the blueprint'"
GH = "gh repo create octo-org/demo --public --description 'A demo' --source . --remote origin --push"
PUSH = (
    "git -c credential.helper= -c 'credential.helper=!gh auth git-credential' "
    "push --set-upstream origin main"
)
PYTHON = (3, 13)
# The preflight of a new copy, in the order in which it asks, and what it shows.
ASKED = [
    "git --version",
    "git var GIT_AUTHOR_IDENT",
    "git var GIT_COMMITTER_IDENT",
    "gh --version",
    "gh api --include user",
    "gh config get git_protocol --host github.com",
    "gh api users/octo-org",
    "gh api user/memberships/orgs/octo-org",
    "gh api repos/octo-org/demo",
]
SHOWN = [
    "The preflight of octo-org/demo:",
    "  ✔ Python 3.13",
    "  ✔ Git 2.47.1",
    "  ✔ Git commits as Test <test@example.com>",
    "  ✔ GitHub CLI 2.62.0",
    "  ✔ gh is signed in to github.com as octocat, with the scopes gist, read:org, "
    "repo, workflow",
    "  ✔ octo-org is an organization that octocat owns",
    "  ✔ octo-org/demo is free on GitHub",
]


class Shell:
    """git and gh as create runs them: each command answers as the test planned it,
    by default as the preflight of a new copy that nothing stops, and otherwise with
    success and no output, and every call is written down."""

    def __init__(
        self, answers: dict[str, tuple[int, str]] | None = None, repo: str = REPO
    ) -> None:
        self.asked = preflight.answers(repo)
        self.answers = {**self.asked, **(answers or {})}
        self.calls: list[str] = []

    def __call__(
        self, arguments: Sequence[str], folder: Path
    ) -> subprocess.CompletedProcess[str]:
        command = shlex.join(arguments)
        self.calls.append(command)
        code, text = self.answers.get(command, (0, ""))
        return subprocess.CompletedProcess(
            list(arguments), code, "" if code else text, text if code else ""
        )

    @property
    def steps(self) -> list[str]:
        """The calls other than those of the preflight."""
        return [call for call in self.calls if call not in self.asked]


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / ".copier-answers.yml").write_text(ANSWERS, encoding="utf-8")
    return tmp_path


def a_repository(root: Path) -> None:
    """The folder is a Git repository already, as git init makes it."""
    (root / ".git").mkdir()


def made_before(
    address: str = "https://github.com/octo-org/demo.git",
) -> dict[str, tuple[int, str]]:
    """A folder that create made, and whose origin pushes to the repository that
    GitHub has, with its first commit on main."""
    return {
        "git remote": (0, "origin\n"),
        "git remote get-url origin": (0, f"{address}\n"),
        "git symbolic-ref --short HEAD": (0, "main\n"),
        "gh api repos/octo-org/demo": (0, '{"full_name": "octo-org/demo"}'),
    }


def test_a_new_copy_becomes_a_repository_on_main(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    shell = Shell()

    assert create(root, "A demo", run=shell, python=PYTHON) == "octo-org/demo"

    # The preflight only asks, and all of it comes before the first step.
    assert shell.calls == [*ASKED, INIT, ADD, COMMIT, GH]
    assert capsys.readouterr().out == "\n".join(
        [
            *SHOWN,
            "Creating octo-org/demo on GitHub, public:",
            f"  {INIT}",
            f"  {ADD}",
            f"  {COMMIT}",
            f"  {GH}",
            "Created https://github.com/octo-org/demo, with the branch main.\n",
        ]
    )


def test_a_private_repository(root: Path) -> None:
    shell = Shell()

    create(root, "A demo", private=True, run=shell)

    assert shell.calls[-1] == GH.replace("--public", "--private")


def test_a_dry_run_shows_the_preflight_and_the_commands(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    shell = Shell()

    assert create(root, "A demo", dry_run=True, run=shell, python=PYTHON) is None

    assert shell.calls == ASKED
    assert capsys.readouterr().out == "\n".join(
        [
            *SHOWN,
            "create would make octo-org/demo on GitHub, public, with:",
            f"  {INIT}",
            f"  {ADD}",
            f"  {COMMIT}",
            f"  {GH}",
            "  python3 .github/blueprint.py settings apply",
            "  python3 .github/blueprint.py checklist",
            "Run it without --dry-run to do it.\n",
        ]
    )


@pytest.mark.parametrize(
    ("changed", "shown"),
    [
        pytest.param(
            {"gh --version": (0, "gh version 2.40.1 (2023-12-13)\n")},
            [
                "  ✘ GitHub CLI 2.40.1: create needs GitHub CLI 2.48 or later",
                "      update GitHub CLI: https://github.com/cli/cli#installation",
            ],
            id="an old GitHub CLI",
        ),
        pytest.param(
            {
                "git var GIT_AUTHOR_IDENT": (
                    128,
                    "Author identity unknown\n\n*** Please tell me who you are.\n\n"
                    '  git config --global user.name "Your Name"\n\n'
                    "fatal: unable to auto-detect email address (got 'me@pc.(none)')",
                )
            },
            [
                "  ✘ Git has no email address to commit with",
                '      git config --global user.email "you@example.com"',
            ],
            id="no email address",
        ),
        pytest.param(
            {
                "git var GIT_COMMITTER_IDENT": (
                    128,
                    "fatal: empty ident name (for <me@email.example>) not allowed",
                )
            },
            [
                "  ✘ Git has no name to commit with",
                '      git config --global user.name "Your Name"',
            ],
            id="no name",
        ),
        pytest.param(
            {
                "gh api --include user": (
                    4,
                    "To get started with GitHub CLI, please run:  gh auth login\n"
                    "Alternatively, populate the GH_TOKEN environment variable.",
                )
            },
            [
                "  ✘ gh is not signed in to github.com: To get started with GitHub "
                "CLI, please run:  gh auth login",
                "      gh auth login --hostname github.com --scopes workflow",
            ],
            id="not signed in",
        ),
        pytest.param(
            {"gh api --include user": (1, "")},
            [
                "  ✘ gh is not signed in to github.com: gh said nothing",
                "      gh auth login --hostname github.com --scopes workflow",
            ],
            id="a sign-in that says nothing",
        ),
        pytest.param(
            {"gh api --include user": (1, "gh: Bad credentials (HTTP 401)")},
            [
                "  ✘ gh is not signed in to github.com: gh: Bad credentials (HTTP 401)",
                "      gh auth login --hostname github.com --scopes workflow",
            ],
            id="a sign-in that GitHub refuses",
        ),
        pytest.param(
            {
                "gh api --include user": (
                    0,
                    preflight.SIGNED_IN.replace(
                        "gist, read:org, repo, workflow", "gist, repo"
                    ),
                )
            },
            [
                "  ✘ gh is signed in to github.com as octocat, without the scopes "
                "workflow, read:org that create needs",
                "      gh auth refresh --hostname github.com --scopes workflow,read:org",
                "  · octo-org is an organization, and whether octocat may create "
                "repositories in it takes the scope read:org",
            ],
            id="missing scopes",
        ),
        pytest.param(
            {"gh api users/octo-org": (1, preflight.NOT_FOUND)},
            [
                "  ✘ GitHub has no account or organization octo-org",
                "      name the repository of an owner on GitHub: "
                "python3 .github/blueprint.py --repo OWNER/NAME create",
            ],
            id="no owner",
        ),
        pytest.param(
            {"gh api users/octo-org": (0, '{"login": "octo-org", "type": "User"}')},
            [
                "  ✘ octo-org is an account of its own, and gh is signed in as octocat",
                "      gh auth switch --user octo-org, or gh auth login as octo-org",
            ],
            id="the account of another user",
        ),
        pytest.param(
            {"gh api user/memberships/orgs/octo-org": (1, preflight.NOT_FOUND)},
            [
                "  ✘ octocat is no member of the organization octo-org",
                "      gh auth login as an owner of octo-org",
            ],
            id="no member",
        ),
        pytest.param(
            {
                "gh api user/memberships/orgs/octo-org": (
                    0,
                    '{"state": "pending", "role": "admin"}',
                )
            },
            [
                "  ✘ octocat is invited to the organization octo-org and hasn't "
                "accepted",
                "      accept the invitation: "
                "https://github.com/orgs/octo-org/invitation",
            ],
            id="an invitation",
        ),
        pytest.param(
            {"gh api repos/octo-org/demo": (0, '{"full_name": "octo-org/demo"}')},
            [
                "  ✘ octo-org/demo is taken on GitHub",
                "      name another: python3 .github/blueprint.py --repo "
                "octo-org/NAME create",
            ],
            id="a name that is taken",
        ),
    ],
)
def test_a_finding_of_the_preflight_stops_create_before_its_first_step(
    root: Path,
    capsys: pytest.CaptureFixture[str],
    changed: dict[str, tuple[int, str]],
    shown: list[str],
) -> None:
    shell = Shell(changed)

    with pytest.raises(CreateError) as error:
        create(root, "A demo", run=shell)

    assert str(error.value) == (
        "the preflight found 1 problem that would stop create, which made nothing: "
        "fix what is marked with ✘, then run it again"
    )
    out = capsys.readouterr().out
    assert "\n".join(shown) in out
    assert out.count("✘") == 1
    assert shell.steps == []


def test_an_old_python_stops_create(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(CreateError, match="found 1 problem"):
        create(root, "A demo", run=Shell(), python=(3, 11, 9))

    assert (
        "  ✘ Python 3.11: the tools of the new repository need Python 3.12 or later\n"
        "      install Python 3.12 or later: https://www.python.org/downloads/\n"
    ) in capsys.readouterr().out


def test_tools_that_are_not_installed_are_named_with_where_to_get_them(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def missing(
        arguments: Sequence[str], folder: Path
    ) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(arguments[0])

    with pytest.raises(CreateError, match=r"^the preflight found 2 problems that"):
        create(root, "A demo", run=missing, python=PYTHON)

    assert capsys.readouterr().out == "\n".join(
        [
            "The preflight of octo-org/demo:",
            "  ✔ Python 3.13",
            "  ✘ Git is not installed",
            "      install Git: https://git-scm.com/downloads",
            "  ✘ GitHub CLI is not installed",
            "      install GitHub CLI 2.48 or later: "
            "https://github.com/cli/cli#installation\n",
        ]
    )


def test_a_tool_that_fails_at_its_version_counts_as_not_installed(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(CreateError, match="found 1 problem"):
        create(root, "A demo", run=Shell({"git --version": (1, "broken")}))

    out = capsys.readouterr().out
    assert "  ✘ Git is not installed\n" in out
    # Without a Git, nothing asks it about the folder or the identity.
    assert "Git commits as" not in out


@pytest.mark.parametrize(
    ("changed", "shown"),
    [
        pytest.param(
            {"gh --version": (0, "gh version DEV\n")},
            "  · GitHub CLI of a version that it doesn't name: gh version DEV",
            id="a version without a number",
        ),
        pytest.param(
            {
                "gh api --include user": (
                    0,
                    preflight.SIGNED_IN.replace(
                        "X-Oauth-Scopes: gist, read:org, repo, workflow\n", ""
                    ),
                )
            },
            "  · gh is signed in to github.com as octocat, with a token that names "
            "no scopes, such as a fine-grained one: it has to create the "
            "repository, push workflows and administer it",
            id="a fine-grained token",
        ),
        pytest.param(
            {
                "gh api --include user": (
                    1,
                    "error connecting to api.github.com\ncheck your internet connection",
                )
            },
            "  · GitHub didn't say who gh is signed in as: error connecting to "
            "api.github.com",
            id="no answer about the sign-in",
        ),
        pytest.param(
            {
                "gh config get git_protocol --host github.com": (0, "ssh\n"),
                "gh api --include user": (
                    0,
                    preflight.SIGNED_IN.replace(
                        "gist, read:org, repo, workflow", "gist, read:org, repo"
                    ),
                ),
            },
            "  ✔ gh is signed in to github.com as octocat, with the scopes gist, "
            "read:org, repo",
            id="no scope workflow over SSH",
        ),
        pytest.param(
            {"gh api users/octo-org": (1, "error connecting to api.github.com")},
            "  · GitHub didn't say who octo-org is: error connecting to api.github.com",
            id="no answer about the owner",
        ),
        pytest.param(
            {
                "gh api user/memberships/orgs/octo-org": (
                    1,
                    "gh: Resource not accessible (HTTP 403)",
                )
            },
            "  · GitHub didn't say whether octocat may create repositories in "
            "octo-org: gh: Resource not accessible (HTTP 403)",
            id="no answer about the membership",
        ),
        pytest.param(
            {
                "gh api user/memberships/orgs/octo-org": (
                    0,
                    '{"state": "active", "role": "member"}',
                )
            },
            "  · octocat is a member of the organization octo-org, not an owner: gh "
            "repo create works only where octo-org lets its members create "
            "repositories",
            id="a member",
        ),
        pytest.param(
            {"gh api repos/octo-org/demo": (1, "gh: Bad Gateway (HTTP 502)")},
            "  · GitHub didn't say whether octo-org/demo is free: "
            "gh: Bad Gateway (HTTP 502)",
            id="no answer about the name",
        ),
    ],
)
def test_what_the_preflight_cannot_tell_stops_nothing(
    root: Path,
    capsys: pytest.CaptureFixture[str],
    changed: dict[str, tuple[int, str]],
    shown: str,
) -> None:
    shell = Shell(changed)

    assert create(root, "A demo", run=shell) == "octo-org/demo"

    assert f"{shown}\n" in capsys.readouterr().out
    assert shell.steps == [INIT, ADD, COMMIT, GH]


def test_a_wider_scope_counts_for_read_org(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    signed_in = preflight.SIGNED_IN.replace("gist, read:org", "admin:org")

    create(root, "A demo", run=Shell({"gh api --include user": (0, signed_in)}))

    assert (
        "  ✔ gh is signed in to github.com as octocat, with the scopes admin:org, "
        "repo, workflow\n"
    ) in capsys.readouterr().out


def test_the_account_that_gh_is_signed_in_as_needs_no_organization(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Without read:org, which only an organization needs, and with the headers of a
    # gh on Windows.
    signed_in = preflight.SIGNED_IN.replace("gist, read:org, ", "").replace(
        "\n", "\r\n"
    )
    shell = Shell(
        {
            "gh api --include user": (0, signed_in),
            "gh api users/OctoCat": (0, '{"login": "OctoCat", "type": "User"}'),
        },
        repo="OctoCat/demo",
    )

    assert create(root, "A demo", repo="OctoCat/demo", run=shell) == "OctoCat/demo"

    out = capsys.readouterr().out
    assert "  ✔ OctoCat is the account that gh is signed in as\n" in out
    assert "with the scopes repo, workflow\n" in out
    assert "gh api user/memberships/orgs/OctoCat" not in shell.calls


@pytest.mark.parametrize(
    ("text", "data"),
    [
        ('{"login": "octocat"}', {"login": "octocat"}),
        ("HTTP/2.0 200 OK\r\nA: b\r\n\r\n{}", {}),
        ("[1, 2]", {}),
        ("<html>", {}),
    ],
)
def test_only_an_object_of_json_is_an_answer(text: str, data: dict[str, str]) -> None:
    assert bootstrap.body(Answer(True, text)) == data


def test_doctor_runs_the_preflight_alone(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    shell = Shell()

    assert doctor(root, run=shell, python=PYTHON)

    assert shell.calls == ASKED
    assert capsys.readouterr().out == "\n".join(
        [*SHOWN, "Nothing stops python3 .github/blueprint.py create.\n"]
    )


def test_doctor_says_what_to_fix(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    shell = Shell({"gh api repos/other/demo": (0, "{}")}, repo="other/demo")

    assert not doctor(root, repo="other/demo", run=shell)

    assert capsys.readouterr().out.endswith(
        "  ✘ other/demo is taken on GitHub\n"
        "      name another: python3 .github/blueprint.py --repo other/NAME create\n"
        "Fix what is marked with ✘, then run python3 .github/blueprint.py create.\n"
    )
    assert shell.steps == []


@pytest.mark.parametrize(
    ("remotes", "address"),
    [
        ("origin\nupstream\n", "https://github.com/other/demo.git"),
        ("origin\n", "https://gitlab.com/octo-org/demo.git"),
        ("upstream\n", None),
    ],
)
def test_a_folder_that_pushes_to_another_repository_is_refused(
    root: Path, remotes: str, address: str | None
) -> None:
    a_repository(root)
    answers = {"git remote": (0, remotes)}
    if address:
        answers["git remote get-url origin"] = (0, address)
    shell = Shell(answers)

    with pytest.raises(
        CreateError, match=r"pushes to .* already, not to octo-org/demo"
    ):
        create(root, "A demo", run=shell)

    assert shell.steps == (
        ["git remote", "git remote get-url origin"] if address else ["git remote"]
    )


@pytest.mark.parametrize(
    "address",
    [
        "https://github.com/octo-org/demo.git",
        "https://x-access-token@github.com/octo-org/demo",
        "git@github.com:Octo-Org/demo.git",
        "ssh://git@github.com/octo-org/demo/",
    ],
)
def test_create_pushes_what_a_run_that_stopped_before_the_push_left(
    root: Path, capsys: pytest.CaptureFixture[str], address: str
) -> None:
    a_repository(root)
    shell = Shell(
        {
            **made_before(address),
            "gh api repos/octo-org/demo/branches/main": (
                1,
                "gh: Branch not found (HTTP 404)",
            ),
        }
    )

    assert create(root, "A demo", run=shell) == "octo-org/demo"

    assert shell.steps == [
        "git remote",
        "git remote get-url origin",
        "git symbolic-ref --short HEAD",
        "git rev-parse --verify --quiet HEAD",
        "git status --porcelain",
        "gh api repos/octo-org/demo/branches/main",
        PUSH,
    ]
    # The first commit is there, so the identity doesn't matter.
    assert "git var GIT_AUTHOR_IDENT" not in shell.calls
    out = capsys.readouterr().out
    assert (
        "  ✔ octo-org/demo is on GitHub, and origin pushes to it: create goes on "
        "from the first step that is left\n"
        "Going on with octo-org/demo on GitHub, from the first step that is left:\n"
        f"  {PUSH}\n"
        "https://github.com/octo-org/demo has the branch main.\n"
    ) in out


def test_create_goes_on_with_the_settings_where_github_has_the_branch(
    root: Path,
) -> None:
    a_repository(root)
    shell = Shell(
        {**made_before(), "gh api repos/octo-org/demo/branches/main": (0, "{}")}
    )

    # The command line applies the settings and shows the checklist then.
    assert create(root, "A demo", run=shell) == "octo-org/demo"

    assert PUSH not in shell.calls
    assert GH not in shell.calls


def test_a_dry_run_shows_where_create_goes_on(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a_repository(root)
    shell = Shell(
        {
            **made_before(),
            "gh api repos/octo-org/demo/branches/main": (
                1,
                "gh: Git Repository is empty. (HTTP 409)",
            ),
        }
    )

    assert create(root, "A demo", dry_run=True, run=shell) is None

    assert PUSH not in shell.calls
    assert capsys.readouterr().out.endswith(
        "create would go on with octo-org/demo on GitHub, with:\n"
        f"  {PUSH}\n"
        "  python3 .github/blueprint.py settings apply\n"
        "  python3 .github/blueprint.py checklist\n"
        "Run it without --dry-run to do it.\n"
    )


def test_a_branch_that_github_does_not_answer_for_stops_create(root: Path) -> None:
    a_repository(root)
    shell = Shell(
        {
            **made_before(),
            "gh api repos/octo-org/demo/branches/main": (1, "gh: HTTP 502"),
        }
    )

    with pytest.raises(
        CreateError, match="didn't say whether octo-org/demo has the branch main"
    ):
        create(root, "A demo", run=shell)

    assert PUSH not in shell.calls


def test_an_origin_that_github_does_not_have_is_named(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a_repository(root)
    shell = Shell(
        {**made_before(), "gh api repos/octo-org/demo": (1, preflight.NOT_FOUND)}
    )

    with pytest.raises(CreateError, match="found 1 problem"):
        create(root, "A demo", run=shell)

    assert (
        "  ✘ origin pushes to octo-org/demo, which GitHub doesn't have\n"
        "      git remote remove origin\n"
    ) in capsys.readouterr().out


def test_a_repository_of_git_init_moves_to_main(root: Path) -> None:
    a_repository(root)
    shell = Shell(
        {
            "git symbolic-ref --short HEAD": (0, "master\n"),
            "git rev-parse --verify --quiet HEAD": (1, ""),
        }
    )

    create(root, "A demo", run=shell)

    assert shell.steps == [
        "git remote",
        "git symbolic-ref --short HEAD",
        "git rev-parse --verify --quiet HEAD",
        "git branch --move main",
        ADD,
        COMMIT,
        GH,
    ]


def test_a_repository_with_its_first_commit_is_pushed_as_it_is(root: Path) -> None:
    a_repository(root)
    shell = Shell({"git symbolic-ref --short HEAD": (0, "main\n")})

    create(root, "A demo", run=shell)

    assert shell.steps == [
        "git remote",
        "git symbolic-ref --short HEAD",
        "git rev-parse --verify --quiet HEAD",
        "git status --porcelain",
        GH,
    ]
    assert "git var GIT_AUTHOR_IDENT" not in shell.calls


def test_changes_that_no_commit_holds_are_refused(root: Path) -> None:
    a_repository(root)
    shell = Shell(
        {
            "git symbolic-ref --short HEAD": (0, "main\n"),
            "git status --porcelain": (0, " M README.md\n"),
        }
    )

    with pytest.raises(CreateError, match="changes that no commit holds"):
        create(root, "A demo", run=shell)

    assert GH not in shell.calls


def test_a_command_that_fails_stops_create_with_its_message(root: Path) -> None:
    shell = Shell({GH: (1, "HTTP 422: Repository creation failed.\n")})

    with pytest.raises(CreateError) as error:
        create(root, "A demo", run=shell)

    assert str(error.value) == f"{GH} failed: HTTP 422: Repository creation failed."
    assert shell.steps == [INIT, ADD, COMMIT, GH]


def test_the_repository_named_by_the_option_wins(root: Path) -> None:
    (root / ".copier-answers.yml").unlink()
    shell = Shell(repo="other/name")

    assert create(root, "A demo", repo="other/name", run=shell) == "other/name"

    assert shell.calls[-1].startswith("gh repo create other/name --public")


@pytest.mark.parametrize("answers", [None, "owner: octo-org\n"])
def test_without_the_answers_of_copier_create_asks_for_the_repository(
    root: Path, answers: str | None
) -> None:
    path = root / ".copier-answers.yml"
    if answers is None:
        path.unlink()
    else:
        path.write_text(answers, encoding="utf-8")

    with pytest.raises(CreateError, match="--repo OWNER/NAME"):
        create(root, "A demo", run=Shell())


def test_a_repository_without_its_owner_is_refused(root: Path) -> None:
    with pytest.raises(CreateError, match="no OWNER/NAME"):
        create(root, "A demo", repo="demo", run=Shell())


@pytest.mark.parametrize("quote", ["'", '"'])
def test_the_answers_that_yaml_quotes_are_read(root: Path, quote: str) -> None:
    # PyYAML quotes an owner or a slug that YAML would read as a number.
    (root / ".copier-answers.yml").write_text(
        f"owner: {quote}1234{quote}\nproject_slug: {quote}2048{quote}\n",
        encoding="utf-8",
    )

    assert bootstrap.answered_repo(root) == "1234/2048"


def test_answers_with_quotes_that_do_not_match_are_not_read(root: Path) -> None:
    (root / ".copier-answers.yml").write_text(
        "owner: 'octo-org\"\nproject_slug: demo\n", encoding="utf-8"
    )

    with pytest.raises(CreateError, match="names no owner"):
        bootstrap.answered_repo(root)


def test_the_answers_of_a_windows_checkout_are_read(root: Path) -> None:
    (root / ".copier-answers.yml").write_bytes(ANSWERS.replace("\n", "\r\n").encode())

    assert bootstrap.answered_repo(root) == "octo-org/demo"


@pytest.fixture
def plain_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Git without the configuration of the machine, which may sign every commit or
    name another first branch."""
    config = tmp_path / "gitconfig"
    config.write_text("[init]\n\tdefaultBranch = master\n", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "Test")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "test@example.com")


@pytest.mark.usefixtures("plain_git")
def test_the_first_commit_is_signed_off_on_main_with_every_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "demo"
    (root / "docs").mkdir(parents=True)
    (root / ".copier-answers.yml").write_text(ANSWERS, encoding="utf-8")
    (root / "docs/index.md").write_text("# Demo\n", encoding="utf-8")
    gh = Shell()

    def git_and_simulated_gh(
        arguments: Sequence[str], folder: Path
    ) -> subprocess.CompletedProcess[str]:
        if arguments[0] == "gh":
            return gh(arguments, folder)
        return bootstrap.run_command(arguments, folder)

    create(root, "A demo", run=git_and_simulated_gh)

    def git(*arguments: str) -> str:
        return bootstrap.run_command(["git", *arguments], root).stdout.strip()

    assert gh.steps == [GH]
    # The real git answers the preflight with the identity of the variables.
    assert "  ✔ Git commits as Test <test@example.com>\n" in capsys.readouterr().out
    # Main, although the configuration of Git names master as the first branch.
    assert git("symbolic-ref", "--short", "HEAD") == "main"
    assert git("log", "--format=%B") == (
        "chore: start from the blueprint\n\nSigned-off-by: Test <test@example.com>"
    )
    assert git("ls-files").split() == [".copier-answers.yml", "docs/index.md"]
    # Once committed, create would push it as it is.
    assert git("status", "--porcelain") == ""


@pytest.mark.usefixtures("plain_git")
def test_the_real_git_names_an_identity_that_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.delenv(f"GIT_{role}_EMAIL")
    # Git falls back to the variable EMAIL, which a machine may set.
    monkeypatch.delenv("EMAIL", raising=False)
    # Git takes the address of the machine where it can make one up, unless told
    # to take only its configuration.
    (tmp_path / "gitconfig").write_text(
        "[user]\n\tuseConfigOnly = true\n", encoding="utf-8"
    )

    finding = bootstrap.identity_finding(bootstrap.run_command, tmp_path)

    assert finding.ok is False
    assert finding.fix == 'git config --global user.email "you@example.com"'
