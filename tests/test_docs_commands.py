"""Tests of the commands in the pages. A new owner follows them on a first run, and
nothing else runs them: no page may need a checkout of the blueprint, which the quick
start no longer has, or leave the first branch to the configuration of Git, which makes
it `master` on many machines, while every workflow runs on `main`. No page may run a
copier that the quick start doesn't put on the PATH either, or tell the reader to commit
an update, which `main` refuses, since it takes pull requests only."""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

import pytest

from blueprint.app import BRANCH as APP_BRANCH
from blueprint.app import MESSAGE as APP_MESSAGE
from blueprint.app import App, naming_steps
from blueprint.bootstrap import PUSH_AS_GH
from blueprint.checklist import (
    ANSWER_MESSAGE,
    PINNED,
    answer_commands,
    answer_steps,
    change_answer,
)

ROOT = Path(__file__).parents[1]
CHECKOUT = "../repo-blueprint/blueprint.py"
# A fenced block, also one indented in a list, or inline code.
CODE = re.compile(
    r"^[ \t]*(?P<fence>`{3,})[^\n]*\n(?P<block>.*?)^[ \t]*(?P=fence)[ \t]*$"
    r"|`(?P<span>[^`\n]+)`",
    re.DOTALL | re.MULTILINE,
)
# One git init, up to the next command of its line.
GIT_INIT = re.compile(r"\bgit init\b[^;&|\n]*")
ON_MAIN = re.compile(r"(?:--initial-branch[= ]|-b )main\b")
# The copier of the quick start, by its version, and one that a line runs without it.
# The path of an environment of its own and the name of the step as a word don't count.
PINNED_COPIER = re.compile(
    r"(?:uvx --from|pipx run --spec) copier==\d+\.\d+\.\d+ copier (?:copy|update)\b"
)
BARE_COPIER = re.compile(r"(?<![\w/\\.=-])copier (?:copy|update) +\S[^;&|\n]*")
# A version of Copier in a command, as the manager of Renovate reads it, and any other.
VERSION = re.compile(r"copier==(\d+\.\d+\.\d+) copier (?:copy|update)")
ANY_VERSION = re.compile(r"copier==\d")
TO_MAIN = re.compile(r"commit the update|committe das Update")
# What a page names without that copier on purpose: a copier of the reader's own, which
# the quick start offers, and what the blueprint bot runs, not the reader.
OWN_COPIERS = {
    "copier copy gh:Dennis-Otto/repo-blueprint my-project",
    "copier copy gh:Dennis-Otto/repo-blueprint mein-projekt",
    "copier update --defaults --conflict inline",
}
WALKTHROUGHS = [
    ("README.md", "docs/own-account.md"),
    ("README.de.md", "docs/own-account.de.md"),
]
# The walkthrough as it was before blueprint.py create.
OLD_WALKTHROUGH = """\
## 2. Create the repository

```sh
cd my-project
git init && git add --all && git commit --signoff --message "chore: start"
gh repo create octo-org/my-project --public --source . --push
python3 ../repo-blueprint/blueprint.py checklist
```
"""
# How an answer changed before it went through a pull request.
OLD_ANSWER = """\
## How do I change an answer later?

Run `copier update` with the new answer and commit the update, such as for the topics:

```sh
copier update --defaults --vcs-ref=:current: --data "topics=python, pypi, cli"
```
"""


def blocks(text: str) -> list[str]:
    """The fenced blocks of a page."""
    return [match["block"] for match in CODE.finditer(text) if match["block"]]


def commands(text: str) -> list[str]:
    """Each line of the fenced blocks of a page, and its inline code; not its prose,
    where the description of a diagram may name git init in words."""
    return [
        line.strip()
        for match in CODE.finditer(text)
        for line in (match["block"] or match["span"]).splitlines()
    ]


def findings(text: str) -> list[str]:
    """What in a page leads a new owner to a broken repository, a command that isn't
    there or a push that `main` refuses."""
    lines = commands(text)
    inits = (found for line in lines for found in GIT_INIT.findall(line))
    bare = (
        found
        for line in lines
        for found in BARE_COPIER.findall(PINNED_COPIER.sub("", line))
    )
    return [
        *[CHECKOUT] * text.count(CHECKOUT),
        *(found for found in inits if not ON_MAIN.search(found)),
        *bare,
        *TO_MAIN.findall(text),
    ]


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def quick_start(readme: str) -> list[str]:
    """The commands of the quick start: the first fenced block of its section."""
    (_, section) = read(readme).split("[start:quick-start]")
    return blocks(section)[0].splitlines()


def pages() -> list[str]:
    """The READMEs and the pages of the website. The records of the decisions say how
    things were, the old commands included, and stay as they are."""
    records = ROOT / "docs/decisions"
    return [
        path.relative_to(ROOT).as_posix()
        for path in (*ROOT.glob("README*.md"), *(ROOT / "docs").rglob("*.md"))
        if records not in path.parents
    ]


def test_the_pages_are_found() -> None:
    found = pages()
    assert {"README.md", "README.de.md", "docs/guide.md", "docs/own-account.de.md"} <= (
        set(found)
    )
    assert not [page for page in found if page.startswith("docs/decisions/")]


@pytest.mark.parametrize("page", pages())
def test_every_command_of_a_page_works_for_a_new_owner(page: str) -> None:
    assert [found for found in findings(read(page)) if found not in OWN_COPIERS] == []


@pytest.mark.parametrize("page", ["docs/faq.md", "docs/faq.de.md"])
def test_the_faq_changes_an_answer_as_the_checklist_says(page: str) -> None:
    """Both tell a new owner the same way, so a change of one can't leave the other
    behind: the steps of app register, with the copier of the quick start."""
    steps = "\n".join(answer_commands("topics=python, pypi, cli")) + "\n"
    assert steps in blocks(read(page))


def test_the_checklist_changes_an_answer_on_a_branch_with_the_quick_start() -> None:
    copier = f"uvx --from {PINNED} --defaults --vcs-ref=:current: --data a=b"
    assert answer_commands("a=b") == [
        "git fetch origin main",
        "git switch --force-create change-the-answers FETCH_HEAD",
        copier,
        "git add --all",
        "git commit --signoff --message 'chore: change the answers of the blueprint'",
        shlex.join([*PUSH_AS_GH, "push", "--set-upstream", "origin", "HEAD"]),
        "gh pr create --fill",
    ]
    # The title of the pull request comes from the commit, and what it says is checked.
    assert re.match(r"chore: ", ANSWER_MESSAGE)
    # The reader learns before the commit that main takes signed commits only.
    (why, *rest, other) = change_answer("a=b")
    assert rest == answer_commands("a=b")
    # The quick start offers pipx and a Copier of your own too, so the line fits them.
    assert f"pipx run --spec {PINNED}" in other
    assert "--gpg-sign" in why
    assert "pull requests" in why


def test_the_steps_are_those_of_app_register() -> None:
    app = App("octo-app", "Iv23client", "123")
    copier = shlex.split(f"uvx --from {PINNED}")
    assert naming_steps(copier, app) == answer_steps(
        copier, app.data(), APP_BRANCH, APP_MESSAGE
    )


def test_the_old_walkthrough_fails() -> None:
    assert findings(OLD_WALKTHROUGH) == [CHECKOUT, "git init "]


def test_the_old_way_to_change_an_answer_fails() -> None:
    assert findings(OLD_ANSWER) == [
        'copier update --defaults --vcs-ref=:current: --data "topics=python, pypi, cli"',
        "commit the update",
    ]


def test_every_pin_of_copier_moves_with_the_quick_start() -> None:
    """The manager of Renovate moves a version only in the files that it lists, so a
    command outside them stays behind the quick start for good."""
    renovate = read(".github/renovate.json5")
    (block, _) = renovate.split('"(?<depName>copier)==')
    listed = re.findall(
        r'^\s*("/\^.+/"),$', block.rsplit("managerFilePatterns", 1)[1], re.M
    )
    patterns = [re.compile(json.loads(item).strip("/")) for item in listed]
    names = [
        *pages(),
        "reference.py",
        *(f"blueprint/{path.name}" for path in (ROOT / "blueprint").glob("*.py")),
    ]
    versions = {name: VERSION.findall(read(name)) for name in names}
    pinned = [name for name in names if versions[name]]
    assert {"blueprint/checklist.py", "docs/faq.de.md", "docs/guide.md"} <= set(pinned)
    # Each is listed, and each entry of the list still has a command to move.
    assert not [
        name for name in pinned if not any(item.match(name) for item in patterns)
    ]
    assert not [
        item.pattern
        for item in patterns
        if not any(item.match(name) for name in pinned)
    ]
    # One release everywhere, and none in a form that the manager can't read.
    assert len({version for found in versions.values() for version in found}) == 1
    assert not [
        name
        for name in names
        if len(ANY_VERSION.findall(read(name))) != len(versions[name])
    ]


@pytest.mark.parametrize(
    ("text", "found"),
    [
        ("Run `git init --initial-branch=main`.", []),
        ("Run `git init --initial-branch main`.", []),
        ("Run `git init -b main`.", []),
        ("Run `git init`.", ["git init"]),
        ("Run `git init -b trunk`.", ["git init -b trunk"]),
        # Only the options of git init itself count.
        ("Run `git init && git switch -c main`.", ["git init "]),
        ("```sh\ngit init\n```\n", ["git init"]),
        ("1. Run:\n\n    ```sh\n    git init\n    ```\n", ["git init"]),
        ("````md\n```\ngit init\n```\n````\n", ["git init"]),
        # Words of a page, such as the description of a diagram, are no command.
        ('<img alt="A new copy gets git init and its first commit">', []),
        ("A checkout at ../repo-blueprint/blueprint.py", [CHECKOUT]),
        ("`python3 .github/blueprint.py create`", []),
        # A copier that the quick start doesn't install, and the ones that need none.
        ("Run `copier update --defaults`.", ["copier update --defaults"]),
        ("```sh\ncopier update --data a=b\n```\n", ["copier update --data a=b"]),
        ("`copier copy gh:octo/repo .`", ["copier copy gh:octo/repo ."]),
        ("`uvx --from copier==9.19.1 copier update --defaults`", []),
        ("`pipx run --spec copier==9.19.1 copier copy gh:octo/repo .`", []),
        ("The bot runs `copier update` every week.", []),
        ("`~/.venvs/copier/bin/copier update --defaults`", []),
        # A commit that main refuses, in both languages.
        ("Change it and commit the update:", ["commit the update"]),
        ("Ändere es und committe das Update:", ["committe das Update"]),
    ],
)
def test_what_counts_as_a_finding(text: str, found: list[str]) -> None:
    assert findings(text) == found


@pytest.mark.parametrize(("readme", "page"), WALKTHROUGHS)
def test_the_walkthrough_has_the_commands_of_the_quick_start(
    readme: str, page: str
) -> None:
    quick = quick_start(readme)
    assert quick[2] == "python3 .github/blueprint.py create"
    lines = commands(read(page))
    places = [lines.index(command) for command in quick]
    assert places == sorted(places)


@pytest.mark.parametrize(("readme", "page"), WALKTHROUGHS)
def test_the_walkthrough_takes_the_copier_of_the_quick_start(
    readme: str, page: str
) -> None:
    pinned = re.fullmatch(
        r"(uvx --from copier==\S+ copier) copy .+", quick_start(readme)[0]
    )
    assert pinned is not None
    runs = [
        line
        for line in commands(read(page))
        if re.search(r"\bcopier (?:copy|update)\b", line)
    ]
    # Copying, and the two answers to change later: app register names the release app.
    assert len(runs) == 3
    assert not [line for line in runs if not line.startswith(f"{pinned[1]} ")]


@pytest.mark.parametrize(("_", "page"), WALKTHROUGHS)
def test_the_walkthrough_uses_only_the_tool_of_the_copy(_: str, page: str) -> None:
    text = read(page)
    assert set(re.findall(r"[^\s`\"]*blueprint\.py", text)) == {".github/blueprint.py"}
    tool = [line for line in commands(text) if "blueprint.py" in line]
    assert tool == [
        "python3 .github/blueprint.py create",
        "python3 .github/blueprint.py app register",
        "python3 .github/blueprint.py app connect --key-file private-key.pem",
        "python3 .github/blueprint.py settings apply",
        "python3 .github/blueprint.py checklist",
    ]
    # create makes the first commit and the repository, not the reader.
    assert not [
        line
        for line in commands(text)
        if "git init" in line or "gh repo create" in line
    ]


@pytest.mark.parametrize(("_", "page"), WALKTHROUGHS)
def test_a_private_key_comes_from_where_github_has_it(_: str, page: str) -> None:
    text = read(page)
    assert "Generate a private key" not in text
    # Step 3, for the release app, and step 8, for the settings app.
    for label in ("*Credentials*", "*Key pairs*", "*New key*"):
        assert text.count(label) == 2, label


@pytest.mark.parametrize(("_", "page"), WALKTHROUGHS)
def test_a_command_that_only_one_shell_takes_comes_for_both(_: str, page: str) -> None:
    text = read(page)
    assert "Git Bash" in text
    assert "PowerShell" in text
    secrets = [block for block in blocks(text) if "gh secret set" in block]
    # The key of the settings app, for Git Bash and for PowerShell; app register and
    # app connect set the key of the release app in every shell.
    assert len(secrets) == 2
    key = "settings-private-key.pem"
    assert sum(f"< {key}" in block for block in secrets) == 1
    assert sum(f"Get-Content -Raw {key} |" in block for block in secrets) == 1
    assert len(re.findall(r"^ *```powershell$", text, re.MULTILINE)) == 1


@pytest.mark.parametrize(("_", "page"), WALKTHROUGHS)
def test_the_walkthrough_keeps_no_step_of_the_old_registration(
    _: str, page: str
) -> None:
    step = read(page).partition("## 3. ")[2].partition("## 4. ")[0]
    # The values that the owner copied, and the file that stayed in the downloads.
    lines = commands(step)
    assert not [line for line in lines if "--data release_app=" in line]
    assert not [line for line in lines if "gh secret set" in line]
    assert "*Variables*" not in step
    assert "python3 .github/blueprint.py app register" in lines


def shape(text: str) -> dict[str, list[str]]:
    """What a translation keeps of a page: its code, literally, the levels and numbers
    of its headings, the numbers of its lists, and how many pictures it has."""
    prose = CODE.sub("", text)
    return {
        "code": blocks(text),
        "headings": re.findall(r"^#+ \d*", prose, re.MULTILINE),
        "lists": re.findall(r"^ *\d+\. ", prose, re.MULTILINE),
        "pictures": re.findall(r"<picture>", prose),
    }


def test_both_languages_of_the_walkthrough_have_the_same_shape() -> None:
    # The German quick start names its folder in German, and the page follows it.
    german = read("docs/own-account.de.md").replace("mein-projekt", "my-project")
    assert shape(german) == shape(read("docs/own-account.md"))
