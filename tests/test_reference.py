"""Tests of reference.py, which writes the reference pages of the website from
copier.yml, the workflows and the settings as code of the template, against the
blueprint itself and against repositories of a few files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import reference
from reference import Name, Question

ROOT = Path(__file__).parents[1]

COPIER = """\
_subdirectory: template

# After the first copy, these belong to the project.
_skip_if_exists:
  - /README.md
  - "/*.py"

# The name stands as it is in a docstring.
project_name:
  type: str
  help: The name of the project, such as "Demo"
  validator: >-
    [% if not project_name.strip() %]Name the project.[% elif '*/' in project_name %]Write it without */.[% endif %]

project_type:
  type: str
  help: The kind of project.
  choices:
    Python package (PyPI): python-package
    Repository without a build: generic

owner_of:
  type: yaml
  when: false
  default:
    account: Octo-Org

owner:
  type: str
  help: The owner
  default: "{= owner_of.account =}"
  validator: >-
    [% if owner != owner_of.account %]Only {= owner_of.account =} or {= owner =}.[% endif %]

python_package:
  type: str
  help: The package
  default: "{= project_name | lower | regex_replace('[^a-z0-9]+', '_') | trim('_') =}"
  when: "{= project_type == 'python-package' =}"

discussions:
  type: bool
  help: Use discussions
  default: true

# Derived from the answers.

stack:
  type: str
  when: false
  default: >-
    [%- if project_type == 'python-package' -%]python
    [%- else -%]generic[%- endif -%]
"""

RELEASE = """\
name: Release

# The release. It delivers where the repository variable PUBLISH_TO says. Nothing else.
# https://github.com/Dennis-Otto/repo-blueprint

on: push

env:
  WHERE: ${{ vars.PUBLISH_TO }}

jobs:
  release:
    environment:
      name: release
    steps:
      - env:
          KEY: ${{ secrets.APP_KEY }}
          TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: echo
  report:
    environment: reports
    steps:
      - run: echo ${{ secrets.APP_KEY }}
"""

LINT = """\
name: Lint

on: pull_request

jobs:
  lint:
    steps:
      - run: echo ${{ secrets.LOOSE_KEY }} ${{ vars.EXTRA }}
"""

SETTINGS = """\
[repository]
name = "demo"

[variables]
PUBLISH_TO = "{= publish_to =}"
[%- if release_app %]
APP_NAME = "{= release_app =}"
[%- endif %]
OTHER = "fixed"

[[rulesets]]
NOT_A_VARIABLE = "x"

[environments.release]
secrets = [{= (["APP_KEY"] if release_app else []) | map('to_json') | join(', ') =}]

[environments.issue-assistant]
secrets = ["AI_TOKEN"]
"""

ABOUT = {
    "PUBLISH_TO": "Where the release delivers. It follows the kind.",
    "APP_NAME": "The name of the app.",
    "OTHER": "Another variable.",
    "EXTRA": "A variable of your own.",
    "APP_KEY": "The key of the app.",
    "AI_TOKEN": "The token of the AI.",
    "LOOSE_KEY": "A secret of the repository.",
    "GITHUB_TOKEN": "The token of GitHub.",
}


def write(root: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")


@pytest.fixture
def repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A blueprint of a few files, with the descriptions of its names."""
    write(
        tmp_path,
        {
            "copier.yml": COPIER,
            ".github/workflows/release.yml": RELEASE,
            ".github/workflows/lint.yml": LINT,
            ".github/workflows/ci-python.yml": "name: CI (python)\n",
            "template/.github/workflows/release.yml.jinja": "",
            "template/.github/workflows/ci.yml.jinja": "",
            "template/.github/workflows/[% if stack == 'python' %]lint.yml[% endif %].jinja": "",
            "template/.github/repository.toml.jinja": SETTINGS,
        },
    )
    monkeypatch.setattr(reference, "ABOUT", ABOUT)
    return tmp_path


# ---------------------------------------------------------------- the blueprint


def test_the_committed_pages_say_what_their_sources_say() -> None:
    written = reference.pages(ROOT)
    assert set(written) == {reference.QUESTIONS, reference.VARIABLES}
    assert reference.stale(ROOT, written) == [], (
        "python3 reference.py writes the reference pages anew"
    )


def test_every_variable_and_secret_of_the_blueprint_has_a_description() -> None:
    flows = [
        reference.workflow(path.name, path.read_text(encoding="utf-8"))
        for path in sorted((ROOT / reference.WORKFLOWS).glob("*.yml"))
    ]
    settings = (ROOT / reference.SETTINGS).read_text(encoding="utf-8")
    found = reference.names_of(flows, settings)
    assert set(found) == set(reference.ABOUT)
    # The variables that the issue and the workflow comments name, and the release app.
    for name in (
        "ISSUE_ASSISTANT_AI",
        "UPSTREAM_AUTOMERGE",
        "ANTHROPIC_API_KEY",
        "CLAUDE_CODE_OAUTH_TOKEN",
        "RELEASE_AUTOMATION_CLIENT_ID",
        "RELEASE_AUTOMATION_PRIVATE_KEY",
    ):
        assert name in found
    assert found["RELEASE_AUTOMATION_PRIVATE_KEY"].environments >= {"release"}
    assert found["CLAUDE_CODE_OAUTH_TOKEN"].listed


def test_every_question_of_the_blueprint_is_on_its_page() -> None:
    page = (ROOT / reference.QUESTIONS).read_text(encoding="utf-8")
    for question in reference.questions(
        (ROOT / reference.COPIER).read_text(encoding="utf-8")
    ):
        assert f"### `{question.name}`\n" in page
    assert "- `/README.md`\n" in page


def test_the_website_shows_the_reference_pages() -> None:
    config = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    for path in (reference.QUESTIONS, reference.VARIABLES):
        assert path.relative_to("docs").as_posix() in config


# ---------------------------------------------------------------- Markdown


def test_text_shows_as_it_is() -> None:
    assert reference.plain("a_b *c* [d] `e` | <f> \\") == (
        "a\\_b \\*c\\* \\[d\\] \\`e\\` \\| &lt;f> \\\\"
    )
    # An address is code, without the punctuation of the sentence after it.
    assert reference.plain("Such as https://octo.example/a_b/, or none.") == (
        "Such as `https://octo.example/a_b/`, or none."
    )
    assert reference.prose("run `copier update` for *all*") == (
        "run `copier update` for \\*all\\*"
    )
    assert reference.code("a`b") == "``a`b``"
    assert reference.code("`a") == "`` `a ``"
    assert reference.code("plain") == "`plain`"
    assert reference.anchor("PUBLISH_TO") == "publish_to"
    assert reference.sentence("The kind") == "The kind."
    assert reference.sentence("Iv23li…") == "Iv23li…"
    assert reference.listed(["a"]) == "a"
    assert reference.listed(["a", "b", "c"]) == "a, b and c"


# ---------------------------------------------------------------- comments


def test_comments_become_paragraphs_without_their_addresses() -> None:
    lines = [
        "name: X",
        "",
        "# One line",
        "# and the next.",
        "#",
        "# A second one.",
        "# https://github.com/Dennis-Otto/repo-blueprint",
        "key: value",
        "  # Inside, about BETA. Not this one.",
        "  other: 1",
    ]
    assert reference.comment_above(lines, 7) == [
        "One line and the next.",
        "A second one.",
    ]
    assert reference.comment_above(lines, 0) == []
    assert reference.comment_above(lines, 1) == []
    assert reference.comments("\n".join(lines)) == [
        "One line and the next.",
        "A second one.",
        "Inside, about BETA. Not this one.",
    ]
    assert reference.paragraphs(["#", "# Text", "#"]) == ["Text"]


def test_the_sentences_that_name_a_variable() -> None:
    said = [
        "Where the variable BETA is true, betas come. BETAS are no BETA_X.",
        "Without `BETA`, none come. Other text.",
    ]
    assert reference.sentences_naming("BETA", said) == [
        "Where the variable BETA is true, betas come.",
        "Without `BETA`, none come.",
    ]
    assert reference.quoted("With BETA_X and BETA set to *on*.", "BETA") == (
        "With BETA\\_X and `BETA` set to \\*on\\*."
    )


# ---------------------------------------------------------------- the questions


def test_the_questions_with_their_comments_in_their_order() -> None:
    found = reference.questions(COPIER)
    assert [question.name for question in found] == [
        "project_name",
        "project_type",
        "owner_of",
        "owner",
        "python_package",
        "discussions",
        "stack",
    ]
    assert found[0].comment == ["The name stands as it is in a docstring."]
    assert found[0].asked
    assert not found[2].asked
    # A blank line parts a comment from the key below it.
    assert found[-1].comment == []
    assert reference.keys(COPIER)["_skip_if_exists"] == [
        "After the first copy, these belong to the project."
    ]


def test_a_value_of_the_template_shows_as_its_default_or_as_code() -> None:
    values: dict[str, Any] = {
        "owner_of": {"account": "Octo-Org", "id": 1},
        "x": "{= y =}",
    }
    assert reference.looked_up("owner_of.account", values) == "Octo-Org"
    assert reference.looked_up("owner_of.missing", values) is None
    assert reference.looked_up("owner_of.account.deeper", values) is None
    assert reference.looked_up("owner_of.id", values) is None
    assert reference.looked_up("x", values) is None
    assert reference.looked_up("x.y", values) is None
    assert reference.rendered(
        "Only {= owner_of.account =} or {= owner | lower =}, not *.", values
    ) == ("Only Octo-Org or `owner | lower`, not \\*.")
    assert reference.refusals(
        "[% if a %]Name it.[% elif b %]Not {= owner_of.account =}.[% endif %]", values
    ) == ("Name it. Not Octo-Org.")


def test_the_facts_of_a_question() -> None:
    assert reference.kind_of({"type": "str"}) == "text"
    assert reference.kind_of({}) == "text"
    assert reference.kind_of({"type": "bool"}) == "yes or no"
    assert reference.kind_of({"type": "float"}) == "float"
    assert reference.kind_of({"choices": {}}) == "one of the choices"
    assert reference.kind_of({"choices": {}, "multiselect": True}) == (
        "several of the choices"
    )
    assert reference.default_of({}) == ("none: Copier asks for it", None)
    assert reference.default_of({"default": True}) == ("yes", None)
    assert reference.default_of({"default": False}) == ("no", None)
    assert reference.default_of({"default": ""}) == ("empty", None)
    assert reference.default_of({"default": "MIT"}) == ("`MIT`", None)
    assert reference.default_of({"default": "{= owner =}"}) == (
        "`{= owner =}`, a template of Copier",
        None,
    )
    long = "[% if a %]" + "x" * 60 + "[% else %]y[% endif %]"
    assert reference.default_of({"default": long}) == (
        "a template of Copier, from the answers before it:",
        f"```text\n[% if a %]{'x' * 60}\n[% else %]y\n[% endif %]\n```",
    )
    assert reference.default_of({"default": {"account": "Octo", "id": "1"}}) == (
        "these values, as YAML:",
        "```yaml\naccount: Octo\nid: '1'\n```",
    )
    assert reference.when_of({}) == "always"
    assert reference.when_of({"when": "{= kind == 'a' =}"}) == (
        "only when `kind == 'a'`"
    )
    assert reference.when_of({"when": "kind"}) == "only when `kind`"


def test_a_section_of_a_question() -> None:
    question = Question(
        "license",
        {
            "type": "str",
            "help": "The license",
            "default": "[% if a %]" + "x" * 60 + "[% endif %]",
            "choices": {"MIT | the short one": "MIT"},
            "validator": "[% if not license %]Name one.[% endif %]",
        },
        ["Why it is asked."],
    )
    assert reference.question_section(question, {}) == [
        "### `license`",
        "",
        "The license.",
        "",
        "Why it is asked.",
        "",
        "- **Type:** one of the choices",
        "- **Asked:** always",
        "- **When Copier refuses an answer, it says:** Name one.",
        "- **Default:** a template of Copier, from the answers before it:",
        "",
        f"```text\n[% if a %]{'x' * 60}\n[% endif %]\n```",
        "",
        "| Answer | What Copier shows |",
        "| --- | --- |",
        "| `MIT` | MIT \\| the short one |",
        "",
    ]
    worked_out = Question("stack", {"type": "str", "when": False, "default": "x"}, [])
    assert reference.question_section(worked_out, {}) == [
        "### `stack`",
        "",
        "- **Type:** text",
        "- **Default:** `x`",
        "",
    ]


def test_the_page_of_the_questions() -> None:
    page = reference.questions_page(COPIER)
    assert page.startswith("---\ndescription: ")
    assert "Copier asks these 5 questions" in page
    assert "- [`project_name`](#project_name): The name of the project" in page
    assert "- **When Copier refuses an answer, it says:** Name the project." in page
    assert "Write it without \\*/." in page
    assert "Only Octo-Org or `owner`." in page
    assert "- **Asked:** only when `project_type == 'python-package'`" in page
    asked, _, worked_out = page.partition("## The values that Copier works out")
    assert "### `stack`" in worked_out
    assert "### `owner_of`" in worked_out
    assert "### `stack`" not in asked
    assert "account: Octo-Org" in worked_out
    assert page.endswith(
        "## The files of a project\n\n"
        "After the first copy, these belong to the project.\n\n"
        "<details markdown>\n"
        "<summary>The 2 patterns of the files of a project</summary>\n\n"
        "- `/README.md`\n- `/*.py`\n\n</details>\n"
    )


# ---------------------------------------------------------------- the variables


def test_the_parts_of_a_workflow() -> None:
    flow = reference.workflow("release.yml", RELEASE)
    assert flow.title == "Release"
    assert set(flow.jobs) == {"release", "report"}
    empty = reference.workflow("empty.yml", "")
    assert (empty.title, dict(empty.jobs)) == ("empty.yml", {})
    assert list(reference.strings_of({"a": [{"b": 1}, "c"]})) == ["a", "b", "1", "c"]
    assert reference.environment_of({"environment": {"name": "release"}}) == "release"
    assert reference.environment_of({"environment": "pypi"}) == "pypi"
    assert reference.environment_of({}) is None


def test_which_repositories_have_a_workflow() -> None:
    scope = reference.scopes(
        [
            "release.yml.jinja",
            "[% if stack == 'php' %]upstream.yml[% endif %].jinja",
            "ci.yml.jinja",
        ]
    )
    assert scope == {
        "release.yml": None,
        "upstream.yml": "stack == 'php'",
        "ci.yml": None,
    }
    assert reference.scope_of("release.yml", scope) == "every repository"
    assert reference.scope_of("upstream.yml", scope) == "where `stack == 'php'`"
    assert reference.scope_of("ci-python.yml", scope) == (
        "where `ci_workflow == 'python'`"
    )
    assert reference.scope_of("rollout.yml", scope) == "the blueprint alone"
    assert reference.scope_of("ci-python.yml", {}) == "the blueprint alone"


def test_the_settings_as_code_of_the_template() -> None:
    variables, secrets = reference.settings_of(SETTINGS)
    assert variables == {
        "PUBLISH_TO": '"{= publish_to =}"',
        "APP_NAME": '"{= release_app =}"',
        "OTHER": '"fixed"',
    }
    assert secrets == {"APP_KEY": ["release"], "AI_TOKEN": ["issue-assistant"]}


def test_every_name_with_its_workflows_environments_and_comments() -> None:
    flows = [
        reference.workflow("lint.yml", LINT),
        reference.workflow("release.yml", RELEASE),
    ]
    found = reference.names_of(flows, SETTINGS)
    assert set(found) == set(ABOUT)
    assert found["PUBLISH_TO"].kind == "vars"
    assert found["PUBLISH_TO"].workflows == ["release.yml"]
    assert found["PUBLISH_TO"].setting == '"{= publish_to =}"'
    assert found["PUBLISH_TO"].said == [
        ("release.yml", "It delivers where the repository variable PUBLISH_TO says.")
    ]
    # A name of the workflow's env, outside every job, has no environment.
    assert found["PUBLISH_TO"].environments == set()
    assert found["APP_KEY"].environments == {"release", "reports"}
    assert found["APP_KEY"].listed
    assert found["LOOSE_KEY"].environments == {None}
    assert not found["LOOSE_KEY"].listed
    assert found["AI_TOKEN"].workflows == []
    assert found["APP_NAME"].kind == "vars"


def test_who_sets_a_name() -> None:
    answers = ["publish_to", "release_app", "release_app_client_id"]
    assert reference.set_by(Name("GITHUB_TOKEN", "secrets"), answers) == (
        "GitHub, for every run of a workflow"
    )
    client = Name("ID", "vars", setting='"{= release_app_client_id =}"')
    assert reference.set_by(client, answers) == (
        "the settings as code: `.github/repository.toml` sets it, from"
        " [`release_app_client_id`](questions.md#release_app_client_id), and the"
        " settings bot applies it; `.github/repository.project.toml` can set another"
        " value"
    )
    fixed = reference.set_by(Name("FIXED", "vars", setting='"x"'), answers)
    assert fixed.startswith("the settings as code: `.github/repository.toml` sets it,")
    assert reference.set_by(Name("MINE", "vars"), answers).startswith(
        "you, where you want it: in `[variables]`"
    )
    assert reference.set_by(Name("KEY", "secrets", environments={None}), answers) == (
        "you, as a secret of the repository: `gh secret set KEY`"
    )
    one = Name("KEY", "secrets", environments={"release", None}, listed=True)
    assert reference.set_by(one, answers) == (
        "you, as a secret of the environment `release`, which only `main` may use:"
        " `gh secret set KEY --env release`, as the checklist shows"
    )
    two = Name("KEY", "secrets", environments={"release", "pypi"})
    assert reference.set_by(two, answers) == (
        "you, as a secret of the environments `pypi` and `release`, which only `main`"
        " may use: `gh secret set KEY --env pypi` and"
        " `gh secret set KEY --env release`"
    )


def test_the_page_of_the_variables(repository: Path) -> None:
    page = reference.pages(repository)[reference.VARIABLES]
    assert page.startswith("---\ndescription: ")
    variables, _, secrets = page.partition("## Secrets")
    assert "- [`PUBLISH_TO`](#publish_to): Where the release delivers." in variables
    assert "### `EXTRA`" in variables
    assert "### `APP_KEY`" in secrets
    assert (
        "- **Read by:** [`release.yml`]"
        "(https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/"
        "release.yml) (Release, every repository)"
    ) in page
    assert "(Lint, where `stack == 'python'`)" in page
    assert "- **Read by:** no workflow" in page
    assert (
        "What the workflows say of it:\n\n- `release.yml`: It delivers where the"
        " repository variable `PUBLISH_TO` says.\n"
    ) in page
    assert page.endswith("\n")
    assert not page.endswith("\n\n")


def test_a_name_without_a_description_or_a_description_without_a_name(
    repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    about = {key: value for key, value in ABOUT.items() if key != "EXTRA"}
    monkeypatch.setattr(reference, "ABOUT", {**about, "GONE": "Nothing uses it."})
    with pytest.raises(reference.PageError) as raised:
        reference.pages(repository)
    assert str(raised.value) == (
        "describe EXTRA in ABOUT of reference.py, which a workflow or the settings as"
        " code use; remove GONE from ABOUT of reference.py, which nothing uses"
    )


# ---------------------------------------------------------------- the command


def test_the_command_writes_the_pages_and_checks_them(
    repository: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert reference.main(["--check"], repository) == 1
    assert capsys.readouterr().err == (
        "reference.py: docs/reference/questions.md differs from its sources;"
        " python3 reference.py writes it anew\n"
        "reference.py: docs/reference/variables.md differs from its sources;"
        " python3 reference.py writes it anew\n"
    )
    assert reference.main([], repository) == 0
    assert capsys.readouterr().out == (
        "reference.py: wrote docs/reference/questions.md\n"
        "reference.py: wrote docs/reference/variables.md\n"
    )
    written = (repository / reference.VARIABLES).read_bytes()
    assert b"\r" not in written
    assert reference.main([], repository) == 0
    assert (
        capsys.readouterr().out == "Every reference page says what its sources say.\n"
    )
    assert reference.main(["--check"], repository) == 0
    assert (
        capsys.readouterr().out == "Every reference page says what its sources say.\n"
    )
    (repository / reference.QUESTIONS).write_text("old\n", encoding="utf-8")
    assert reference.main(["--check"], repository) == 1
    assert "questions.md differs" in capsys.readouterr().err


def test_the_command_names_what_keeps_it_from_writing(
    repository: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (repository / "copier.yml").write_text("a: [\n", encoding="utf-8")
    assert reference.main([], repository) == 2
    assert capsys.readouterr().err.startswith("reference.py: ")
    (repository / "copier.yml").unlink()
    assert reference.main(["--check"], repository) == 2
    assert "copier.yml" in capsys.readouterr().err
