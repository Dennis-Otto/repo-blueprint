"""What git and gh answer to the preflight of blueprint.py create when nothing in it
stops create: a Git with an identity, a GitHub CLI after 2.48, signed in as octocat
with the scopes of gh auth login and workflow, an organization that octocat owns,
and a name that GitHub doesn't have yet. The tests of create and of the command line
start from these and change the one answer that they are about."""

from __future__ import annotations

import json

LOGIN = "octocat"
IDENTITY = "Test <test@example.com> 1760000000 +0200\n"
SIGNED_IN = (
    "HTTP/2.0 200 OK\n"
    "Content-Type: application/json; charset=utf-8\n"
    "X-Oauth-Scopes: gist, read:org, repo, workflow\n"
    "\n" + json.dumps({"login": LOGIN, "type": "User"})
)
NOT_FOUND = "gh: Not Found (HTTP 404)"


def answers(repo: str) -> dict[str, tuple[int, str]]:
    """Each command of the preflight, joined by spaces, with its exit code and what
    it prints."""
    owner = repo.split("/")[0]
    return {
        "git --version": (0, "git version 2.47.1\n"),
        "git var GIT_AUTHOR_IDENT": (0, IDENTITY),
        "git var GIT_COMMITTER_IDENT": (0, IDENTITY),
        "gh --version": (
            0,
            "gh version 2.62.0 (2024-11-14)\n"
            "https://github.com/cli/cli/releases/tag/v2.62.0\n",
        ),
        "gh api --include user": (0, SIGNED_IN),
        "gh config get git_protocol --host github.com": (0, "https\n"),
        f"gh api users/{owner}": (
            0,
            json.dumps({"login": owner, "type": "Organization"}),
        ),
        f"gh api user/memberships/orgs/{owner}": (
            0,
            json.dumps({"state": "active", "role": "admin"}),
        ),
        f"gh api repos/{repo}": (1, NOT_FOUND),
    }
