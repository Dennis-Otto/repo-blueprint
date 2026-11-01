"""Tests of the commands in the pages. A new owner follows them on a first run, and
nothing else runs them: no page may need a checkout of the blueprint, which the quick
start no longer has, or leave the first branch to the configuration of Git, which makes
it `master` on many machines, while every workflow runs on `main`."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

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
    """What in a page leads a new owner to a broken repository."""
    inits = (found for line in commands(text) for found in GIT_INIT.findall(line))
    return [CHECKOUT] * text.count(CHECKOUT) + [
        found for found in inits if not ON_MAIN.search(found)
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
def test_no_page_needs_a_checkout_or_leaves_the_branch_to_git(page: str) -> None:
    assert findings(read(page)) == []


def test_the_old_walkthrough_fails() -> None:
    assert findings(OLD_WALKTHROUGH) == [CHECKOUT, "git init "]


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
