#!/usr/bin/env python3
"""The reference pages of the blueprint's website, written from what they describe.

docs/reference/questions.md shows every question of copier.yml: its help, its type,
its choices, its default, when Copier asks it and the answers that Copier refuses,
then the values that Copier works out from the answers and the files that belong to
a project. docs/reference/variables.md shows every variable and secret that a
workflow of .github/workflows/ reads or that the settings as code of the template
set: what it does, who sets it, the workflows that read it and what their comments
say of it. ABOUT below says what each one is for, since many have no comment.
.github/fleet.toml names the repositories that follow the blueprint, and from it come
the showcase of README.md and README.de.md, the section "A real repository" of each
page of docs/kinds/, the order of the Rollout and the canaries of the Variants.
template/.github/blueprint/owned.txt.jinja lists the files of template/ that belong to
the blueprint in the repository that it makes, with the condition of each.

    python3 reference.py           writes the pages and the parts of the files
    python3 reference.py --check   names each one that differs from its sources;
                                   tests/test_reference.py fails on it as well

So a change of copier.yml, of a workflow, of template/.github/repository.toml.jinja, of
.github/fleet.toml or of the files of template/ runs the first and commits the files
with it, and neither the website nor a workflow can drift from them.
https://github.com/Dennis-Otto/repo-blueprint
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

import yaml

COPIER = Path("copier.yml")
WORKFLOWS = Path(".github/workflows")
TEMPLATE_WORKFLOWS = Path("template/.github/workflows")
SETTINGS = Path("template/.github/repository.toml.jinja")
QUESTIONS = Path("docs/reference/questions.md")
VARIABLES = Path("docs/reference/variables.md")
TEMPLATE = Path("template")
OWNED = TEMPLATE / ".github/blueprint/owned.txt.jinja"
# What a name of a file or a folder of the template renders to, when its condition holds.
CONDITIONAL = re.compile(r"\[% if (?P<condition>[^%]+) %\](?P<name>.*?)\[% endif %\]")
OWNED_HEAD = """\
# The files that the blueprint keeps current in this repository: all that it renders,
# other than those that belong to the project. A pull request that changes one gets a
# notice from the check lint and in the report of the PR coach, because the next update
# that changes the same lines conflicts with it. reference.py of the blueprint writes
# this list: https://github.com/Dennis-Otto/repo-blueprint
"""
# A file of the blueprint that says in its first lines that a project changes it there,
# which AGENTS.md of a project names as the exception, so it gets no notice.
OWNED_EXCEPTIONS = frozenset({".vale.ini"})
# The address of a file of the blueprint on GitHub, which the website links.
BLOB = "https://github.com/Dennis-Otto/repo-blueprint/blob/main/"
# The token that GitHub gives every run, which nobody sets.
GITHUB_TOKEN = "GITHUB_TOKEN"

# What each variable and secret is for, in the words of a user. A name that a workflow
# or the settings as code use without an entry here stops both commands, and so does
# an entry whose name nothing uses any more, except for the names of the issue
# assistant below.
ABOUT: dict[str, str] = {
    "ANTHROPIC_API_KEY": (
        "An API key of Anthropic, which the issue assistant takes in place of"
        " `CLAUDE_CODE_OAUTH_TOKEN` to analyze each new issue with Claude, at the"
        " prices of Anthropic's API. Set one of the two; without either, the assistant"
        " works without AI, as with `ISSUE_ASSISTANT_AI` set to `off`."
    ),
    "APP_PRIVATE_KEY": (
        "The private key of the certificate of a Nextcloud app, with which the release"
        " signs the package for the App Store and the workflow *Register app* proves"
        " the id of the app. Only a Nextcloud app needs it."
    ),
    "APPSTORE_TOKEN": (
        "The API token of the account of the Nextcloud App Store, with which the"
        " release submits the signed package and the workflow *Register app* registers"
        " the id of the app. Only a Nextcloud app needs it."
    ),
    "CWS_CLIENT_ID": (
        "The client ID of the OAuth client of a Google Cloud project, with which the"
        " workflow *Chrome Web Store* of a Chrome extension signs in with the refresh"
        " token, until the sign-in without a stored secret is set up. A secret of the"
        " environment `chrome-web-store`; `docs/releases.md` of the extension says how"
        " to get it."
    ),
    "CWS_CLIENT_SECRET": (
        "The client secret of the same OAuth client, a secret of the environment"
        " `chrome-web-store` for the sign-in with the refresh token. Delete it once the"
        " sign-in without a stored secret works."
    ),
    "CWS_EXTENSION_ID": (
        "The ID of the item of a Chrome extension in the Chrome Web Store, from the"
        " address of the item in the Developer Dashboard, to which the workflow"
        " *Chrome Web Store* delivers every release."
    ),
    "CWS_PUBLISHER_ID": (
        "The ID of the publisher of a Chrome extension, under *Account* in the"
        " Developer Dashboard of the Chrome Web Store; the API of the store names the"
        " item by it and `CWS_EXTENSION_ID`."
    ),
    "CWS_REFRESH_TOKEN": (
        "The refresh token of the developer account, with the scope of the Chrome Web"
        " Store, a secret of the environment `chrome-web-store` for the sign-in with"
        " the refresh token. The daily run keeps it in use; delete it once the sign-in"
        " without a stored secret works."
    ),
    "CWS_SERVICE_ACCOUNT": (
        "The address of the service account of Google, such as"
        " `chrome-web-store@PROJECT.iam.gserviceaccount.com`, which the Developer"
        " Dashboard admits to the item and as which the workflow *Chrome Web Store*"
        " signs in, with the OIDC token of GitHub and no stored secret."
    ),
    "CWS_WORKLOAD_IDENTITY_PROVIDER": (
        "The provider of the workload identity pool of Google that takes the OIDC"
        " token of GitHub, such as"
        " `projects/123456789/locations/global/workloadIdentityPools/github/providers/NAME`"
        " with the number of the project: set with `CWS_SERVICE_ACCOUNT`, the"
        " workflow *Chrome Web Store* signs in without a stored secret."
    ),
    "BETA_CHANNEL": (
        "`true` makes every change for users that reaches `main`, a `feat`, `fix` or"
        " `perf`, a beta of the next release, such as `1.3.0-beta.2`, which the release"
        " publishes as a prerelease for the testers who take prereleases. Without it,"
        " or with any other value, no betas are published."
    ),
    "BLUEPRINT_AUTOMERGE": (
        "`off` makes every update of the blueprint wait for the maintainer, where its"
        " pull request would merge itself once every check passes; an update with"
        " conflicts waits either way. Set it to `on`, or delete it with `gh variable"
        " delete BLUEPRINT_AUTOMERGE`, and the updates merge themselves again: the"
        " settings bot never deletes a variable, so removing its line from"
        " `.github/repository.project.toml` leaves `off` in place."
    ),
    "BLUEPRINT_OWNERSHIP": (
        "`fail` makes the check *lint* fail on a pull request of a person that changes"
        " a file of the blueprint, where it leaves a notice with any other value or"
        " none. The report of the PR coach says where the change belongs instead."
        " Bots stay out of it: the update of the blueprint and the pull requests of"
        " the other bots."
    ),
    "CLAUDE_CODE_OAUTH_TOKEN": (
        "The token of a Claude subscription, which `claude setup-token` of Claude Code"
        " creates, with which the issue assistant analyzes each new issue with Claude."
        " The checklist asks for it while the answer `issue_assistant_ai` is on;"
        " `ANTHROPIC_API_KEY` works in its place."
    ),
    "CODE_SCANNING": (
        "`off` keeps every finding out of code scanning, which GitHub offers a private"
        " repository only with GitHub Code Security: CodeQL doesn't analyze, since its"
        " terms allow it on private code only with GitHub Code Security or Advanced"
        " Security, and its check passes with a notice; zizmor fails on every finding;"
        " OSV-Scanner and the Scorecard keep theirs in their checks. The settings bot"
        " sets it to `off` on such a repository and back to `on` once GitHub offers"
        " code scanning; `[variables]` of `.github/repository.project.toml` decides"
        " instead where it names it."
    ),
    "COPILOT_GITHUB_TOKEN": (
        "A fine-grained token of GitHub with the permission *Copilot Requests* alone"
        " and no access to repositories, with which the issue assistant analyzes each"
        " new issue with Copilot, once `name` under `[engine]` of"
        " `.github/issue-assistant/config.toml` is `copilot`. It counts the premium"
        " requests of the Copilot plan of the token's owner."
    ),
    "DEPENDENCY_REVIEW": (
        "`off` makes the check *dependency-review* leave the vulnerabilities to the"
        " check *osv-scanner (pull request)*, which compares the lock files of a pull"
        " request with those of its base; GitHub offers its dependency review to a"
        " private repository only with GitHub Code Security. The settings bot sets it"
        " to `off` on such a repository and back to `on` once GitHub offers the"
        " review; `[variables]` of `.github/repository.project.toml` decides instead"
        " where it names it."
    ),
    "GEMINI_API_KEY": (
        "An API key of Google AI Studio, with which the issue assistant analyzes each"
        " new issue with Gemini, once `name` under `[engine]` of"
        " `.github/issue-assistant/config.toml` is `gemini`; free within the daily"
        " limits of the free tier of the Gemini API."
    ),
    GITHUB_TOKEN: (
        "The token that GitHub gives every run of a workflow, for its repository alone"
        " and with the permissions that its `permissions:` grant. What a workflow does"
        " with it starts no other workflow, which is why the bots that open, update or"
        " merge pull requests act as the release app."
    ),
    "ISSUE_ASSISTANT_AI": (
        "`off` makes the issue assistant label the issues and answer the commands of"
        " their comments without an AI engine, which then needs no secret; `on` lets"
        " the engine analyze each new issue as well. The reusable workflow of the"
        " issue assistant, which `issue-assistant.yml` calls, reads it."
    ),
    "MUTATION_PARTS": (
        "The number of parts in which the mutation tests run, one job each, in place"
        " of the estimate from the number of mutants: more parts for a project whose"
        " parts run out of the six hours of a job."
    ),
    "OPENAI_API_KEY": (
        "An API key of OpenAI, with which the issue assistant analyzes each new issue"
        " with Codex, once `name` under `[engine]` of"
        " `.github/issue-assistant/config.toml` is `codex`, at the prices of OpenAI's"
        " API."
    ),
    "PUBLISH_TO": (
        "Where the release delivers the package: `pypi`, `npm`, `ghcr`, `hacs`,"
        " `nextcloud-appstore`, `github-action`, `chrome-web-store` or `none`, by the"
        " kind of project."
        " The build, the release and the check of the latest release follow it."
    ),
    "RELEASE_APP": (
        "The name of the release app, as its address says: github.com/apps/NAME. No"
        " workflow reads it; the checklist of `blueprint.py` links the installation of"
        " the app with it."
    ),
    "RELEASE_AUTOMATION_APP_ID": (
        "The App ID of the release app, the number on its settings page. No workflow"
        " reads it; the settings as code let only this app create release tags, in"
        " the ruleset *Release tag creation*."
    ),
    "RELEASE_AUTOMATION_CLIENT_ID": (
        "The Client ID of the release app, with which each bot asks for a token of the"
        " app, together with the private key `RELEASE_AUTOMATION_PRIVATE_KEY`. Without"
        " it, the bots say in their summary what is missing, and the release pull"
        " request starts no checks."
    ),
    "RELEASE_AUTOMATION_PRIVATE_KEY": (
        "The private key of the release app, the file that its settings page"
        " generates. With it and `RELEASE_AUTOMATION_CLIENT_ID`, the bots act as the"
        " app: they open and merge the release and update pull requests, so that their"
        " checks run, create the release tags and apply the settings. The file goes in"
        " with `< key.pem` after the command below."
    ),
    "SETTINGS_APP_CLIENT_ID": (
        "The Client ID of the settings app, an optional second GitHub App of the owner"
        " with only the permissions that the settings need. With it and the private key"
        " `SETTINGS_APP_PRIVATE_KEY`, the settings bot applies the settings as this"
        " app, and the blueprint bot lets the actions of an update start before it"
        " pushes the update, so that the release app needs no *Administration*."
        " Without them, the release app applies the settings, as before."
    ),
    "SETTINGS_APP_PRIVATE_KEY": (
        "The private key of the settings app, the file that its settings page"
        " generates. With it and `SETTINGS_APP_CLIENT_ID`, the settings bot and the"
        " blueprint bot act as the settings app, the only app that writes the"
        " administration of the repository. The file goes in with `< key.pem` after"
        " the command below."
    ),
    "UPSTREAM_AUTOMERGE": (
        "`off` makes the pull request of the upstream bot of a Nextcloud app, which"
        " raises `max-version` to a new major version of Nextcloud, wait for the"
        " maintainer, where it would merge itself once every check passes."
    ),
}

# The names in ABOUT that the workflows of the issue assistant read. The Issue
# assistant sync takes each release of the assistant over by itself and writes these
# pages anew, so a release may drop one of them without a person; a name that is new in
# a release and that only workflows of the assistant read shows with ASSISTANT_NAME
# until ABOUT describes it.
ASSISTANT_NAMES = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "CLAUDE_CODE_OAUTH_TOKEN",
        "COPILOT_GITHUB_TOKEN",
        "GEMINI_API_KEY",
        "OPENAI_API_KEY",
    }
)
ASSISTANT = "https://github.com/Dennis-Otto/issue-assistant"
# A job that calls a reusable workflow of the issue assistant passes it the secrets of
# the engines by name, and its job analyze reads them in the caller's environment
# issue-assistant, which only the default branch may use.
ASSISTANT_REUSABLE = re.compile(
    r"Dennis-Otto/issue-assistant/\.github/workflows/reusable-[\w-]+\.yml@"
)
ASSISTANT_ENVIRONMENT = "issue-assistant"
ASSISTANT_NAME = (
    "A {kind} that the workflows of the [issue assistant]({address}) read, from a"
    " release of the assistant that the Issue assistant sync took over. The README of"
    " the assistant says what it does."
)
# A workflow of the issue assistant names the assistant in the comment at its top,
# which starts at the first column; other workflows name it only inside their jobs.
OF_ASSISTANT = re.compile(rf"^#.*{re.escape(ASSISTANT)}\b", re.M)
# A variable or a secret of a workflow: ${{ vars.NAME }} or ${{ secrets.NAME }}.
USE = re.compile(r"\b(vars|secrets)\.([A-Za-z_][A-Za-z0-9_]*)")
# A value and a block of the delimiters of the template, {= … =} and [% … %].
VALUE = re.compile(r"\{=\s*(.*?)\s*=\}", re.S)
BLOCK = re.compile(r"\[%-?.*?-?%\]", re.S)
# The name of a file of the template with its condition, [% if … %]NAME[% endif %].
CONDITION = re.compile(r"^\[% if (.+?) %\](.+)\[% endif %\]$")
# A table of TOML, also in a line of the template: [name] or [[name]].
TABLE = re.compile(r"^\[{1,2}([a-z][a-z0-9_.-]*)\]{1,2}")
SETTING = re.compile(r"^([A-Z][A-Z0-9_]*) = (.*)$")
KEY = re.compile(r"^(_?[a-z][a-z0-9_]*):")
# Where a sentence of a comment ends: before the capital or the code that starts the next.
SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z`\"(])")
ADDRESS = re.compile(r"https?://\S+")
# The characters that Markdown would read as markup; < would start HTML.
MARKUP = re.compile(r"([\\`*_\[\]|])")
# An address in a text, without the punctuation of the sentence after it.
LINK = re.compile(r"(https?://[^\s<>`]*[^\s<>`.,;:!?)\]])")
TYPES = {"str": "text", "bool": "yes or no", "int": "a number", "yaml": "YAML"}
# A default longer than this shows as a block of code below the facts of its question.
SHORT = 60


class PageError(Exception):
    """What keeps a page from being written, such as a variable without a description."""


# ---------------------------------------------------------------- Markdown


def plain(text: str) -> str:
    """Text that Markdown shows as it is, with each address as code: most are examples,
    such as https://octo-org.github.io/demo/, which the link check would ask for."""
    return "".join(
        code(part) if index % 2 else MARKUP.sub(r"\\\1", part).replace("<", "&lt;")
        for index, part in enumerate(LINK.split(text))
    )


def prose(text: str) -> str:
    """Text whose spans in backticks stay code, and whose rest Markdown shows as it is."""
    parts = re.split(r"(`[^`]+`)", text)
    return "".join(
        part if index % 2 else plain(part) for index, part in enumerate(parts)
    )


def code(text: str) -> str:
    """Text as code inline, with as many backticks around it as it needs."""
    fence = "`" * (max((len(run) for run in re.findall("`+", text)), default=0) + 1)
    padded = f" {text} " if text.startswith("`") or text.endswith("`") else text
    return f"{fence}{padded}{fence}"


def anchor(name: str) -> str:
    """The anchor of a heading that is only a name in code, as the website and GitHub
    make it."""
    return name.lower()


def sentence(text: str) -> str:
    """Text that ends as a sentence does."""
    return text if text.endswith((".", "!", "?", "…")) else f"{text}."


def listed(items: Sequence[str]) -> str:
    """Items in a sentence: a, b and c."""
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


# ---------------------------------------------------------------- comments


def paragraphs(comment: Iterable[str]) -> list[str]:
    """The paragraphs of lines of a comment, each joined into one line: a line of only
    # parts them, and a line of only an address is left out."""
    found: list[str] = []
    words: list[str] = []
    for line in comment:
        text = line.strip().removeprefix("#").strip()
        if ADDRESS.fullmatch(text):
            continue
        if text:
            words.append(text)
        elif words:
            found.append(" ".join(words))
            words = []
    if words:
        found.append(" ".join(words))
    return found


def comment_above(lines: Sequence[str], index: int) -> list[str]:
    """The paragraphs of the comment directly above a line."""
    start = index
    while start > 0 and lines[start - 1].lstrip().startswith("#"):
        start -= 1
    return paragraphs(lines[start:index])


def comments(text: str) -> list[str]:
    """The paragraphs of every comment of a file of YAML."""
    found: list[str] = []
    block: list[str] = []
    for line in [*text.splitlines(), ""]:
        if line.lstrip().startswith("#"):
            block.append(line)
        elif block:
            found += paragraphs(block)
            block = []
    return found


def quoted(sentence: str, name: str) -> str:
    """A sentence of a comment as Markdown, with the name that it explains as code."""
    parts = re.split(rf"\b{re.escape(name)}\b", sentence)
    return code(name).join(prose(part) for part in parts)


def sentences_naming(name: str, said: Iterable[str]) -> list[str]:
    """The sentences of paragraphs that name a variable or a secret."""
    word = re.compile(rf"\b{re.escape(name)}\b")
    return [
        sentence
        for paragraph in said
        for sentence in SENTENCE.split(paragraph)
        if word.search(sentence)
    ]


# ---------------------------------------------------------------- the questions


@dataclass(frozen=True)
class Question:
    """A question of copier.yml, or a value that Copier works out from the answers."""

    name: str
    spec: Mapping[str, Any]
    comment: list[str]

    @property
    def asked(self) -> bool:
        return self.spec.get("when", True) is not False


def keys(text: str) -> dict[str, list[str]]:
    """The paragraphs of the comment above each key of the top of a file of YAML."""
    lines = text.splitlines()
    return {
        found.group(1): comment_above(lines, index)
        for index, line in enumerate(lines)
        if (found := KEY.match(line))
    }


def questions(text: str) -> list[Question]:
    """The questions of copier.yml and the values that Copier works out, in its order;
    the names of its settings start with _."""
    data: dict[str, Any] = yaml.safe_load(text)
    above = keys(text)
    return [
        Question(name, spec, above[name])
        for name, spec in data.items()
        if not name.startswith("_")
    ]


def looked_up(expression: str, values: Mapping[str, Any]) -> str | None:
    """The field of a value that Copier works out as a mapping, such as
    blueprint_owner.account; None for any other expression."""
    name, dot, rest = expression.partition(".")
    value: Any = values.get(name)
    if not dot or not isinstance(value, Mapping):
        return None
    for part in rest.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return None
        value = value[part]
    return value if isinstance(value, str) else None


def rendered(text: str, values: Mapping[str, Any]) -> str:
    """Text of the template as Markdown: a value that the defaults know as it is, any
    other value as code."""
    parts = []
    last = 0
    for found in VALUE.finditer(text):
        parts.append(prose(text[last : found.start()]))
        value = looked_up(found.group(1), values)
        parts.append(code(found.group(1)) if value is None else plain(value))
        last = found.end()
    parts.append(prose(text[last:]))
    return "".join(parts)


def refusals(validator: str, values: Mapping[str, Any]) -> str:
    """What Copier says of an answer that it refuses: the text between the blocks of
    the validator."""
    said = (part.strip() for part in BLOCK.split(validator))
    return " ".join(rendered(part, values) for part in said if part)


def kind_of(spec: Mapping[str, Any]) -> str:
    if "choices" in spec:
        return (
            "several of the choices"
            if spec.get("multiselect")
            else "one of the choices"
        )
    kind = str(spec.get("type", "str"))
    return TYPES.get(kind, kind)


def template_code(value: str) -> str:
    """A default of the template with a line for each block, as a block of code."""
    lines = (part.strip() for part in re.split(r"(?=\[%)", value))
    return "```text\n" + "\n".join(line for line in lines if line) + "\n```"


def default_of(spec: Mapping[str, Any]) -> tuple[str, str | None]:
    """The default as a fact of the list, and a block of code below it for a long one."""
    if "default" not in spec:
        return "none: Copier asks for it", None
    value = spec["default"]
    if isinstance(value, bool):
        return ("yes" if value else "no"), None
    if isinstance(value, Mapping):
        dumped = yaml.safe_dump(dict(value), sort_keys=False, allow_unicode=True)
        return "these values, as YAML:", f"```yaml\n{dumped}```"
    text = str(value)
    if not text:
        return "empty", None
    if "{=" not in text and "[%" not in text:
        return code(text), None
    if len(text) <= SHORT and "\n" not in text:
        return f"{code(text)}, a template of Copier", None
    return "a template of Copier, from the answers before it:", template_code(text)


def when_of(spec: Mapping[str, Any]) -> str:
    when = spec.get("when", True)
    if when is True:
        return "always"
    found = VALUE.fullmatch(str(when).strip())
    condition = found.group(1) if found else str(when)
    return f"only when {code(condition)}"


def question_section(question: Question, values: Mapping[str, Any]) -> list[str]:
    spec = question.spec
    lines = [f"### {code(question.name)}", ""]
    if "help" in spec:
        lines += [sentence(prose(" ".join(str(spec["help"]).split()))), ""]
    for paragraph in question.comment:
        lines += [rendered(paragraph, values), ""]
    default, block = default_of(spec)
    lines.append(f"- **Type:** {kind_of(spec)}")
    if question.asked:
        lines.append(f"- **Asked:** {when_of(spec)}")
    if "validator" in spec:
        said = refusals(spec["validator"], values)
        lines.append(f"- **When Copier refuses an answer, it says:** {said}")
    # Last, so that a default in a block of code follows it.
    lines += [f"- **Default:** {default}", ""]
    if block:
        lines += [block, ""]
    if "choices" in spec:
        lines += ["| Answer | What Copier shows |", "| --- | --- |"]
        lines += [
            f"| {code(str(value))} | {plain(label)} |"
            for label, value in spec["choices"].items()
        ]
        lines.append("")
    return lines


def questions_page(text: str) -> str:
    """docs/reference/questions.md from the text of copier.yml."""
    found = questions(text)
    settings = yaml.safe_load(text)
    values = {question.name: question.spec.get("default") for question in found}
    asked = [question for question in found if question.asked]
    worked_out = [question for question in found if not question.asked]
    lines = [
        "---",
        "description: Every question of the Copier template of Repo Blueprint, with its"
        " default, when Copier asks it and the answers it refuses, the values worked"
        " out from the answers and the files that belong to a project.",
        "---",
        "",
        "# The questions of Copier",
        "",
        "<!-- reference.py writes this page from copier.yml: change copier.yml and run"
        " python3 reference.py. -->",
        "",
        f"Copier asks these {len(asked)} questions when it copies the blueprint, in this"
        " order, and keeps the answers in `.copier-answers.yml`, so that `copier update`"
        " asks only a new question. `--data name=value` gives an answer without the"
        " question, also later: `copier update --defaults --vcs-ref=:current: --data"
        " name=value` changes an answer of an existing repository, and the defaults of"
        " Copier's [settings file](https://copier.readthedocs.io/en/stable/settings/)"
        " answer the questions that stay the same for all of your repositories, as"
        " [your own account](../own-account.md) shows. A default that is a template of"
        " Copier comes from the answers before it, in the delimiters of the blueprint:"
        " `{= … =}` for a value and `[% … %]` for a block.",
        "",
        *(
            f"- [{code(question.name)}](#{anchor(question.name)}):"
            f" {prose(' '.join(str(question.spec.get('help', '')).split()))}"
            for question in asked
        ),
        "",
        "## The questions",
        "",
    ]
    for question in asked:
        lines += question_section(question, values)
    lines += [
        "## The values that Copier works out",
        "",
        "Copier never asks these and doesn't keep them in `.copier-answers.yml`: the"
        " files of the template read them, and Copier works them out from the answers"
        " at every copy and update.",
        "",
    ]
    for question in worked_out:
        lines += question_section(question, values)
    patterns = settings["_skip_if_exists"]
    lines += ["## The files of a project", ""]
    for paragraph in keys(text)["_skip_if_exists"]:
        lines += [prose(paragraph), ""]
    lines += [
        "<details markdown>",
        f"<summary>The {len(patterns)} patterns of the files of a project</summary>",
        "",
        *(f"- {code(pattern)}" for pattern in patterns),
        "",
        "</details>",
    ]
    return "\n".join([*lines, ""])


# ---------------------------------------------------------------- the variables


@dataclass
class Name:
    """A variable or a secret, with the workflows that read it and what they say of it."""

    name: str
    kind: str
    workflows: list[str] = field(default_factory=list)
    environments: set[str | None] = field(default_factory=set)
    said: list[tuple[str, str]] = field(default_factory=list)
    setting: str | None = None
    # Whether the settings as code name the secret, so that the checklist asks for it.
    listed: bool = False
    # Whether only workflows of the issue assistant read it.
    of_assistant: bool = False


@dataclass(frozen=True)
class Workflow:
    file: str
    title: str
    text: str
    jobs: Mapping[str, Any]

    @property
    def of_assistant(self) -> bool:
        return bool(OF_ASSISTANT.search(self.text))


def workflow(file: str, text: str) -> Workflow:
    data = yaml.safe_load(text) or {}
    return Workflow(file, str(data.get("name", file)), text, data.get("jobs") or {})


def strings_of(value: Any) -> Iterable[str]:
    """Every text in a value of YAML, its keys too."""
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield str(key)
            yield from strings_of(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings_of(item)
    else:
        yield str(value)


def environment_of(job: Mapping[str, Any]) -> str | None:
    if ASSISTANT_REUSABLE.match(str(job.get("uses", ""))):
        return ASSISTANT_ENVIRONMENT
    environment = job.get("environment")
    if isinstance(environment, Mapping):
        return str(environment.get("name"))
    return None if environment is None else str(environment)


def scopes(template_files: Iterable[str]) -> dict[str, str | None]:
    """The workflows that the template renders, each with the condition of its file,
    or None for every repository."""
    found: dict[str, str | None] = {}
    for file in template_files:
        name = file.removesuffix(".jinja")
        condition = CONDITION.match(name)
        if condition:
            found[condition.group(2)] = condition.group(1)
        else:
            found[name] = None
    return found


def scope_of(file: str, scope: Mapping[str, str | None]) -> str:
    """Which repositories have a workflow of the blueprint."""
    condition: str | None
    if file in scope:
        condition = scope[file]
    elif file.startswith("ci-") and "ci.yml" in scope:
        # The CI of each kind of project, which the template renders as ci.yml.
        condition = f"ci_workflow == '{file.removeprefix('ci-').removesuffix('.yml')}'"
    else:
        return "the blueprint alone"
    return "every repository" if condition is None else f"where {code(condition)}"


def settings_of(text: str) -> tuple[dict[str, str], dict[str, list[str]]]:
    """The variables that the settings as code of the template set, each with its
    value, and the environments whose secrets they name."""
    table = ""
    variables: dict[str, str] = {}
    secrets: dict[str, list[str]] = {}
    for line in text.splitlines():
        found = TABLE.match(line)
        if found:
            table = found.group(1)
            continue
        setting = SETTING.match(line)
        if table == "variables" and setting:
            variables[setting.group(1)] = setting.group(2)
        elif table.startswith("environments.") and line.startswith("secrets ="):
            for secret in re.findall(r'"([A-Z][A-Z0-9_]*)"', line):
                secrets.setdefault(secret, []).append(table.partition(".")[2])
    return variables, secrets


def names_of(workflows: Sequence[Workflow], settings: str) -> dict[str, Name]:
    """Every variable and secret of the workflows and of the settings as code."""
    found: dict[str, Name] = {}
    variables, secrets = settings_of(settings)
    for flow in workflows:
        said = comments(flow.text)
        for kind, name in sorted(set(USE.findall(flow.text))):
            entry = found.setdefault(name, Name(name, kind, of_assistant=True))
            entry.of_assistant = entry.of_assistant and flow.of_assistant
            entry.workflows.append(flow.file)
            entry.said += [(flow.file, s) for s in sentences_naming(name, said)]
            reference = f"{kind}.{name}"
            for job in flow.jobs.values():
                if any(reference in text for text in strings_of(job)):
                    entry.environments.add(environment_of(job))
    for name, value in variables.items():
        entry = found.setdefault(name, Name(name, "vars"))
        entry.setting = value
        entry.of_assistant = False
    for name, environments in secrets.items():
        entry = found.setdefault(name, Name(name, "secrets"))
        entry.of_assistant = False
        entry.environments.update(environments)
        entry.listed = True
    return found


def set_by(entry: Name, answers: Sequence[str]) -> str:
    if entry.name == GITHUB_TOKEN:
        return "GitHub, for every run of a workflow"
    if entry.setting is not None:
        named = [
            f"[{code(answer)}](questions.md#{anchor(answer)})"
            for answer in answers
            if re.search(rf"\b{answer}\b", entry.setting)
        ]
        source = f", from {listed(named)}" if named else ""
        return (
            f"the settings as code: `.github/repository.toml` sets it{source}, and the"
            " settings bot applies it; `.github/repository.project.toml` can set"
            " another value"
        )
    if entry.kind == "vars":
        return (
            "you, where you want it: in `[variables]` of"
            " `.github/repository.project.toml`, which the settings bot applies, or"
            " under *Settings → Secrets and variables → Actions → Variables*"
        )
    environments = sorted(name for name in entry.environments if name)
    if not environments:
        return (
            f"you, as a secret of the repository: {code(f'gh secret set {entry.name}')}"
        )
    named = [code(name) for name in environments]
    word = "environment" if len(named) == 1 else "environments"
    commands = [
        code(f"gh secret set {entry.name} --env {name}") for name in environments
    ]
    shown = ", as the checklist shows" if entry.listed else ""
    return (
        f"you, as a secret of the {word} {listed(named)}, which only `main` may use:"
        f" {listed(commands)}{shown}"
    )


def about(entry: Name) -> str:
    """What a name is for: its entry in ABOUT, or for a name that only workflows of
    the issue assistant read and that ABOUT doesn't know yet, ASSISTANT_NAME."""
    if entry.name in ABOUT:
        return ABOUT[entry.name]
    kind = "variable" if entry.kind == "vars" else "secret"
    return ASSISTANT_NAME.format(kind=kind, address=ASSISTANT)


def name_section(
    entry: Name,
    titles: Mapping[str, str],
    scope: Mapping[str, str | None],
    answers: Sequence[str],
) -> list[str]:
    lines = [f"### {code(entry.name)}", "", about(entry), ""]
    lines.append(f"- **Set by:** {set_by(entry, answers)}")
    read = [
        f"[{code(file)}]({BLOB}{WORKFLOWS.as_posix()}/{file})"
        f" ({plain(titles[file])}, {scope_of(file, scope)})"
        for file in entry.workflows
    ]
    lines.append(f"- **Read by:** {'; '.join(read) if read else 'no workflow'}")
    lines.append("")
    if entry.said:
        lines += ["What the workflows say of it:", ""]
        lines += [
            f"- {code(file)}: {quoted(sentence, entry.name)}"
            for file, sentence in entry.said
        ]
        lines.append("")
    return lines


def variables_page(
    workflows: Sequence[Workflow],
    settings: str,
    template_files: Iterable[str],
    answers: Sequence[str],
) -> str:
    """docs/reference/variables.md from the workflows, the settings as code of the
    template, the names of the template's workflows and the names of the answers."""
    found = names_of(workflows, settings)
    undescribed = sorted(
        name
        for name, entry in found.items()
        if name not in ABOUT and not entry.of_assistant
    )
    unused = sorted(set(ABOUT) - set(found) - ASSISTANT_NAMES)
    problems = [
        f"describe {name} in ABOUT of reference.py, which a workflow or the settings"
        " as code use"
        for name in undescribed
    ] + [
        f"remove {name} from ABOUT of reference.py, which nothing uses"
        for name in unused
    ]
    if problems:
        raise PageError("; ".join(problems))
    titles = {flow.file: flow.title for flow in workflows}
    scope = scopes(template_files)
    lines = [
        "---",
        "description: Every variable and secret that the workflows of Repo Blueprint"
        " read or that its settings as code set: what it does, who sets it and which"
        " workflows read it.",
        "---",
        "",
        "# Variables and secrets",
        "",
        "<!-- reference.py writes this page from .github/workflows/ and"
        " template/.github/repository.toml.jinja: change them and run python3"
        " reference.py. -->",
        "",
        "The workflows read the variables of the repository as `vars.NAME` and its"
        " secrets as `secrets.NAME`. The settings as code set most of the variables"
        " from the answers of Copier, and the checklist of `python3 .github/blueprint.py"
        " checklist` names each secret that is missing, with the command that sets it;"
        " the value goes into the prompt of the GitHub CLI and nowhere else. A variable"
        " that isn't set reads as empty, and so does a secret, which the workflows"
        " check before they use it.",
        "",
    ]
    for kind, title in (("vars", "Variables"), ("secrets", "Secrets")):
        entries = sorted(
            (entry for entry in found.values() if entry.kind == kind),
            key=lambda entry: entry.name,
        )
        lines += [f"## {title}", ""]
        lines += [
            f"- [{code(entry.name)}](#{anchor(entry.name)}):"
            f" {SENTENCE.split(about(entry))[0]}"
            for entry in entries
        ]
        lines.append("")
        for entry in entries:
            lines += name_section(entry, titles, scope, answers)
    return "\n".join(lines).rstrip("\n") + "\n"


# ---------------------------------------------------------------- the fleet

FLEET = Path(".github/fleet.toml")
READMES = {"en": Path("README.md"), "de": Path("README.de.md")}
KINDS = Path("docs/kinds")
ROLLOUT = WORKFLOWS / "rollout.yml"
VARIANTS = WORKFLOWS / "variants.yml"
# Each field of a repository of the registry, with its type.
FIELDS: dict[str, type] = {
    "name": str,
    "kind": str,
    "rollout": int,
    "canary": bool,
    "title": str,
    "what": str,
    "pitch": str,
    "title_de": str,
    "what_de": str,
    "pitch_de": str,
}
NAME = re.compile(r"[A-Za-z0-9._-]+")
# The line of the Rollout that names the repositories in the order of their checks.
ORDER = re.compile(r"^(          ORDER: ).*$", re.M)
# The marks around the legs of the canaries in the Variants workflow.
CANARIES = (
    "          # [start:canaries] reference.py writes these from .github/fleet.toml.\n",
    "          # [end:canaries]\n",
)
# The texts that name the repositories, in each language of the website.
WORDS: dict[str, dict[str, str]] = {
    "en": {
        "one": (
            "One public repository follows the blueprint, with code of its own and the"
            " checks and bots of the blueprint; every release of the blueprint reaches"
            " it as a pull request:"
        ),
        "many": (
            "{count} public repositories follow the blueprint, each with code of its"
            " own and the checks and bots of the blueprint; every release of the"
            " blueprint reaches them as a pull request:"
        ),
        "item": "- **[{title}]({url})**, {what}: {pitch} {badge}",
        "dashboard": (
            "[The dashboard]({url}) shows {which} at a glance: the release of the"
            " blueprint it is on, its checks, its releases and its Scorecard."
        ),
        "it": "it",
        "them": "each of them",
        "none": (
            "No public repository of this kind follows the blueprint yet. The Variants"
            " workflow of the blueprint makes one from every change and runs its checks"
            " with their real tools, and updates one from the latest release as its"
            " blueprint bot would."
        ),
        "kind one": "[{title}]({url}) is made from the blueprint: {pitch}",
        "kind many": "These public repositories of this kind are made from the blueprint:",
        "kind item": "- **[{title}]({url})**: {pitch}",
        "canary": (
            "The Variants workflow tries every pull request of the blueprint on the"
            " answers of {titles}, before it merges."
        ),
        "and": "and",
    },
    "de": {
        "one": (
            "Ein öffentliches Repository folgt dem Blueprint, mit eigenem Code und den"
            " Prüfungen und Bots des Blueprints; jede Version des Blueprints erreicht es"
            " als Pull Request:"
        ),
        "many": (
            "{count} öffentliche Repositories folgen dem Blueprint, jedes mit eigenem"
            " Code und den Prüfungen und Bots des Blueprints; jede Version des"
            " Blueprints erreicht sie als Pull Request:"
        ),
        "item": "- **[{title}]({url})**, {what}: {pitch} {badge}",
        "dashboard": (
            "[Das Dashboard]({url}) zeigt {which} auf einen Blick: die Version des"
            " Blueprints, auf der es ist, seine Prüfungen, seine Releases und seine"
            " Scorecard."
        ),
        "it": "es",
        "them": "jedes davon",
        "none": (
            "Noch folgt kein öffentliches Repository dieser Art dem Blueprint. Der"
            " Workflow Variants des Blueprints macht bei jeder Änderung eines daraus und"
            " führt seine Prüfungen mit ihren echten Werkzeugen aus, und er aktualisiert"
            " eines von der neuesten Version, wie sein Blueprint-Bot es täte."
        ),
        "kind one": "[{title}]({url}) ist aus dem Blueprint entstanden: {pitch}",
        "kind many": (
            "Diese öffentlichen Repositories dieser Art sind aus dem Blueprint"
            " entstanden:"
        ),
        "kind item": "- **[{title}]({url})**: {pitch}",
        "canary": (
            "Der Workflow Variants probiert jeden Pull Request des Blueprints mit den"
            " Antworten von {titles} aus, bevor er merged."
        ),
        "and": "und",
    },
}
# A number of repositories from two on as a word, up to twelve.
NUMBERS = {
    "en": (
        "Two",
        "Three",
        "Four",
        "Five",
        "Six",
        "Seven",
        "Eight",
        "Nine",
        "Ten",
        "Eleven",
        "Twelve",
    ),
    "de": (
        "Zwei",
        "Drei",
        "Vier",
        "Fünf",
        "Sechs",
        "Sieben",
        "Acht",
        "Neun",
        "Zehn",
        "Elf",
        "Zwölf",
    ),
}


@dataclass(frozen=True)
class Member:
    """A repository that follows the blueprint, as the registry names it."""

    name: str
    kind: str
    rollout: int
    canary: bool
    # By language: what the showcase and the pages of the kinds say of it.
    title: Mapping[str, str]
    what: Mapping[str, str]
    pitch: Mapping[str, str]


@dataclass(frozen=True)
class Fleet:
    """The repositories of .github/fleet.toml, in the order of the showcase."""

    owner: str
    members: tuple[Member, ...]

    def url(self, member: Member) -> str:
        return f"https://github.com/{self.owner}/{member.name}"

    def badge(self, member: Member) -> str:
        project = f"github.com/{self.owner}/{member.name}"
        return (
            f"[![OpenSSF Scorecard](https://api.scorecard.dev/projects/{project}/badge)]"
            f"(https://scorecard.dev/viewer/?uri={project})"
        )

    @property
    def dashboard(self) -> str:
        return f"https://{self.owner.lower()}.github.io/repo-blueprint/dashboard/"


def by_language(entry: Mapping[str, Any], key: str) -> dict[str, str]:
    return {"en": entry[key], "de": entry[f"{key}_de"]}


def member(entry: Any, where: str) -> Member:
    """One [[repository]] of the registry, with every field and none other."""
    if not isinstance(entry, dict):
        raise PageError(f"{where} is no table of a repository")
    missing = sorted(FIELDS.keys() - entry.keys())
    unknown = sorted(entry.keys() - FIELDS.keys())
    if missing or unknown:
        raise PageError(
            f"{where} has the fields {', '.join(FIELDS)}:"
            f" missing {missing}, unknown {unknown}"
        )
    for key, kind in FIELDS.items():
        # By type(), since True is an int as well; and never an empty text or 0.
        value = entry[key]
        if type(value) is not kind or (kind is not bool and not value):
            raise PageError(f"{where}: {key} is no {kind.__name__} of its own")
    if not NAME.fullmatch(entry["name"]):
        raise PageError(f"{where}: {entry['name']!r} is no name of a repository")
    if not (entry["pitch"].endswith(".") and entry["pitch_de"].endswith(".")):
        raise PageError(f"{where}: pitch and pitch_de end with a full stop")
    return Member(
        name=entry["name"],
        kind=entry["kind"],
        rollout=entry["rollout"],
        canary=entry["canary"],
        title=by_language(entry, "title"),
        what=by_language(entry, "what"),
        pitch=by_language(entry, "pitch"),
    )


def fleet(text: str) -> Fleet:
    """The registry: an owner, and each of its repositories once in the Rollout."""
    where = FLEET.as_posix()
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise PageError(f"{where}: {error}") from error
    owner = data.get("owner")
    entries = data.get("repository")
    if not isinstance(owner, str) or not NAME.fullmatch(owner):
        raise PageError(f"{where} names no owner")
    if not isinstance(entries, list) or not entries:
        raise PageError(f"{where} names no [[repository]]")
    members = tuple(
        member(entry, f"{where}: repository {index}")
        for index, entry in enumerate(entries, start=1)
    )
    names = [item.name for item in members]
    if len(set(names)) != len(names):
        raise PageError(f"{where} names a repository twice")
    if sorted(item.rollout for item in members) != list(range(1, len(members) + 1)):
        raise PageError(
            f"{where}: the places in the Rollout are 1 to {len(members)}, each once"
        )
    return Fleet(owner, members)


def count(number: int, language: str) -> str:
    """A number from two on, as a word up to twelve."""
    words = NUMBERS[language]
    return words[number - 2] if number - 2 < len(words) else str(number)


def joined(items: Sequence[str], language: str) -> str:
    """Items in a sentence of the language: a, b and c."""
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} {WORDS[language]['and']} {items[-1]}"


def showcase(registry: Fleet, language: str) -> str:
    """The part made-with of a README: every repository, with its Scorecard."""
    words = WORDS[language]
    number = len(registry.members)
    one = number == 1
    lead = words["one"] if one else words["many"].format(count=count(number, language))
    items = [
        words["item"].format(
            title=item.title[language],
            url=registry.url(item),
            what=item.what[language],
            pitch=item.pitch[language],
            badge=registry.badge(item),
        )
        for item in registry.members
    ]
    dashboard = words["dashboard"].format(
        url=registry.dashboard, which=words["it" if one else "them"]
    )
    return f"{lead}\n\n" + "\n".join(items) + f"\n\n{dashboard}\n"


def real_repositories(registry: Fleet, kind: str, language: str) -> str:
    """The part real-repository of the page of a kind: its repositories, if any."""
    words = WORDS[language]
    members = [item for item in registry.members if item.kind == kind]
    if not members:
        return words["none"] + "\n"
    texts = [
        {
            "title": item.title[language],
            "url": registry.url(item),
            "pitch": item.pitch[language],
        }
        for item in members
    ]
    if len(texts) == 1:
        paragraphs = [words["kind one"].format(**texts[0])]
    else:
        items = "\n".join(words["kind item"].format(**text) for text in texts)
        paragraphs = [words["kind many"], items]
    canaries = [item.title[language] for item in members if item.canary]
    if canaries:
        paragraphs.append(words["canary"].format(titles=joined(canaries, language)))
    return "\n\n".join(paragraphs) + "\n"


def with_part(text: str, marks: tuple[str, str], part: str, where: Path) -> str:
    """The text with part between the two lines that mark it."""
    head, start, rest = text.partition(marks[0])
    _, end, tail = rest.partition(marks[1])
    if not (start and end):
        raise PageError(
            f"{where.as_posix()} has no part between {marks[0].strip()}"
            f" and {marks[1].strip()}"
        )
    return f"{head}{marks[0]}{part}{marks[1]}{tail}"


def snippet(name: str) -> tuple[str, str]:
    """The marks of a part of a page, as the snippets of the website mark it."""
    return f"<!-- --8<-- [start:{name}] -->\n", f"<!-- --8<-- [end:{name}] -->\n"


def rollout_order(text: str, registry: Fleet) -> str:
    """The Rollout, with the repositories in the order of their places."""
    order = " ".join(
        item.name for item in sorted(registry.members, key=lambda item: item.rollout)
    )
    written, found = ORDER.subn(lambda match: match[1] + order, text)
    if found != 1:
        raise PageError(f"{ROLLOUT.as_posix()} has no one line ORDER: of the Rollout")
    return written


def canary_legs(registry: Fleet) -> str:
    """A leg of the Variants for each canary, by name, with its kind."""
    return "".join(
        f"          - {{ kind: {item.kind}, start: adopted, answers: {item.name} }}\n"
        for item in sorted(registry.members, key=lambda item: item.name)
        if item.canary
    )


def kinds_of(root: Path, registry: Fleet) -> list[str]:
    """The kinds that have a page, which the kind of each repository must be."""
    kinds = sorted(
        path.name.removesuffix(".md")
        for path in (root / KINDS).glob("*.md")
        if not path.name.endswith(".de.md")
    )
    for item in registry.members:
        if item.kind not in kinds:
            raise PageError(
                f"{FLEET.as_posix()}: the kind {item.kind} of {item.name} has no page"
                f" {(KINDS / item.kind).as_posix()}.md"
            )
    return kinds


def fleet_pages(root: Path) -> dict[Path, str]:
    """Each file that names the repositories of the registry, as the registry makes
    it; none in a copy of the blueprint without a registry, such as a fork that no
    repository follows yet."""
    if not (root / FLEET).is_file():
        return {}
    registry = fleet((root / FLEET).read_text(encoding="utf-8"))

    def read(path: Path) -> str:
        return (root / path).read_text(encoding="utf-8")

    written = {
        path: with_part(
            read(path), snippet("made-with"), f"\n{showcase(registry, lang)}\n", path
        )
        for lang, path in READMES.items()
    }
    for kind in kinds_of(root, registry):
        for lang, suffix in (("en", ".md"), ("de", ".de.md")):
            path = KINDS / f"{kind}{suffix}"
            part = f"\n{real_repositories(registry, kind, lang)}\n"
            written[path] = with_part(
                read(path), snippet("real-repository"), part, path
            )
    written[ROLLOUT] = rollout_order(read(ROLLOUT), registry)
    written[VARIANTS] = with_part(
        read(VARIANTS), CANARIES, canary_legs(registry), VARIANTS
    )
    return written


# ---------------------------------------------------------------- the files


def pages(root: Path) -> dict[Path, str]:
    """Each reference page as its sources in root make it."""
    copier = (root / COPIER).read_text(encoding="utf-8")
    flows = [
        workflow(path.name, path.read_text(encoding="utf-8"))
        for path in sorted((root / WORKFLOWS).glob("*.yml"))
    ]
    answers = [question.name for question in questions(copier)]
    template_flows = [path.name for path in (root / TEMPLATE_WORKFLOWS).glob("*.jinja")]
    settings = (root / SETTINGS).read_text(encoding="utf-8")
    return {
        QUESTIONS: questions_page(copier),
        VARIABLES: variables_page(flows, settings, template_flows, answers),
        OWNED: owned_list(copier, template_files(root)),
        **fleet_pages(root),
    }


def owned_line(template_file: str) -> tuple[str, str]:
    """The path that a file of the template renders to, as far as its conditions
    leave it to Copier, and the lines of the list that name it: within its conditions,
    whose tags take the line break before them, so that a file that the project doesn't
    get leaves no empty line."""
    conditions: list[str] = []

    def name_of(match: re.Match[str]) -> str:
        conditions.append(match["condition"])
        return str(match["name"])

    path = CONDITIONAL.sub(name_of, template_file.removesuffix(".jinja"))
    if not conditions:
        return path, f"{path}\n"
    opening = "".join(f"[% if {condition} %]" for condition in conditions)
    closing = "[% endif %]" * len(conditions)
    return (
        path,
        f"[%-{opening.removeprefix('[%')}\n{path}\n[%-{closing.removeprefix('[%')}\n",
    )


def left_to_project(path: str, patterns: Iterable[str]) -> bool:
    """Whether a pattern of _skip_if_exists holds path. Copier reads them like .gitignore
    with a library that the Issue assistant sync doesn't have, as it runs this script on
    the Python of the runner. Every pattern of the blueprint has a slash, so it counts
    from the root, its * stays within a name, and a folder holds all that is below it;
    tests/test_template.py compares the result with that library for each kind."""
    parts = path.split("/")
    for pattern in patterns:
        wanted = pattern.removeprefix("/").split("/")
        if len(parts) >= len(wanted) and all(map(fnmatchcase, parts, wanted)):
            return True
    return False


def owned_list(copier: str, template_files: Iterable[str]) -> str:
    """The template of .github/blueprint/owned.txt: each file of the template, other
    than those that _skip_if_exists leaves to the project, its answers, which belong to
    a command rather than to the blueprint or a person, and the files that say that a
    project changes them."""
    settings = yaml.safe_load(copier)
    project = settings["_skip_if_exists"]
    left_out = {settings.get("_answers_file", ".copier-answers.yml"), *OWNED_EXCEPTIONS}
    lines = sorted(owned_line(name) for name in template_files)
    return OWNED_HEAD + "".join(
        line
        for path, line in lines
        if path not in left_out and not left_to_project(path, project)
    )


def template_files(root: Path) -> list[str]:
    """Every file of the template, by its path in the template, and the list itself,
    which the first run is about to write."""
    folder = root / TEMPLATE
    found = {
        path.relative_to(folder).as_posix()
        for path in folder.rglob("*")
        if path.is_file()
    }
    return sorted({*found, OWNED.relative_to(TEMPLATE).as_posix()})


def stale(root: Path, written: Mapping[Path, str]) -> list[Path]:
    """The pages whose file differs from what their sources make."""
    return [
        path
        for path, text in written.items()
        if not (root / path).is_file()
        or (root / path).read_text(encoding="utf-8") != text
    ]


def main(argv: Sequence[str] | None = None, root: Path = Path()) -> int:
    parser = argparse.ArgumentParser(
        prog="reference.py",
        description="Write the reference pages of the website from their sources.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="only name the pages that differ from their sources",
    )
    arguments = parser.parse_args(argv)
    try:
        written = pages(root)
    except (OSError, PageError, yaml.YAMLError) as error:
        print(f"reference.py: {error}", file=sys.stderr)
        return 2
    changed = stale(root, written)
    if arguments.check:
        for path in changed:
            print(
                f"reference.py: {path.as_posix()} differs from its sources;"
                " python3 reference.py writes it anew",
                file=sys.stderr,
            )
        if not changed:
            print("Every reference page says what its sources say.")
        return 1 if changed else 0
    for path in changed:
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(written[path], encoding="utf-8", newline="\n")
        print(f"reference.py: wrote {path.as_posix()}")
    if not changed:
        print("Every reference page says what its sources say.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
