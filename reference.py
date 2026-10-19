#!/usr/bin/env python3
"""The reference pages of the blueprint's website, written from what they describe.

docs/reference/questions.md shows every question of copier.yml: its help, its type,
its choices, its default, when Copier asks it and the answers that Copier refuses,
then the values that Copier works out from the answers and the files that belong to
a project. docs/reference/variables.md shows every variable and secret that a
workflow of .github/workflows/ reads or that the settings as code of the template
set: what it does, who sets it, the workflows that read it and what their comments
say of it. ABOUT below says what each one is for, since many have no comment.

    python3 reference.py           writes both pages
    python3 reference.py --check   names each page that differs from its sources;
                                   tests/test_reference.py fails on it as well

So a change of copier.yml, of a workflow or of template/.github/repository.toml.jinja
runs the first and commits the pages with it, and the website can't drift from them.
https://github.com/Dennis-Otto/repo-blueprint
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

COPIER = Path("copier.yml")
WORKFLOWS = Path(".github/workflows")
TEMPLATE_WORKFLOWS = Path("template/.github/workflows")
SETTINGS = Path("template/.github/repository.toml.jinja")
QUESTIONS = Path("docs/reference/questions.md")
VARIABLES = Path("docs/reference/variables.md")
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
    "CLAUDE_CODE_OAUTH_TOKEN": (
        "The token of a Claude subscription, which `claude setup-token` of Claude Code"
        " creates, with which the issue assistant analyzes each new issue with Claude."
        " The checklist asks for it while the answer `issue_assistant_ai` is on;"
        " `ANTHROPIC_API_KEY` works in its place."
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
        " the engine analyze each new issue as well."
    ),
    "MUTATION_PARTS": (
        "The number of parts in which the mutation tests run, one job each, in place"
        " of the estimate from the number of mutants: more parts for a project whose"
        " parts run out of the six hours of a job."
    ),
    "PUBLISH_TO": (
        "Where the release delivers the package: `pypi`, `npm`, `ghcr`, `hacs`,"
        " `nextcloud-appstore`, `github-action` or `none`, by the kind of project."
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
    {"ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "ISSUE_ASSISTANT_AI"}
)
ASSISTANT = "https://github.com/Dennis-Otto/issue-assistant"
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
        name for name, entry in found.items() if name not in ABOUT and not entry.of_assistant
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


# ---------------------------------------------------------------- the files


def pages(root: Path) -> dict[Path, str]:
    """Each reference page as its sources in root make it."""
    copier = (root / COPIER).read_text(encoding="utf-8")
    flows = [
        workflow(path.name, path.read_text(encoding="utf-8"))
        for path in sorted((root / WORKFLOWS).glob("*.yml"))
    ]
    answers = [question.name for question in questions(copier)]
    template_files = [path.name for path in (root / TEMPLATE_WORKFLOWS).glob("*.jinja")]
    settings = (root / SETTINGS).read_text(encoding="utf-8")
    return {
        QUESTIONS: questions_page(copier),
        VARIABLES: variables_page(flows, settings, template_files, answers),
    }


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
