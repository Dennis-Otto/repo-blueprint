"""Tests of downstream.py, which tries a commit of the blueprint on the repositories
that take it, with a template of a few files, a repository made from its first
release and Copier as the blueprint bot runs it, all offline."""

from __future__ import annotations

import io
import subprocess
import sys
import urllib.error
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest

import downstream

ROOT = Path(__file__).parents[1]
ANSWERS = {"owner": "Dennis-Otto", "project_name": "Demo", "project_slug": "demo"}
COPIER = """\
_subdirectory: template
_answers_file: .copier-answers.yml
project_name:
  type: str
owner:
  type: str
  default: Dennis-Otto
project_slug:
  type: str
  default: demo
"""
FILES = {
    "copier.yml": COPIER,
    "template/{{ _copier_conf.answers_file }}.jinja": (
        "# The answers of the blueprint\n{{ _copier_answers | to_nice_yaml -}}\n"
    ),
    "template/.github/workflows/ci.yml.jinja": "name: CI\n# {{ project_name }}\n",
    "template/CONTRIBUTING.md.jinja": "# {{ project_name }}\n\nAsk first.\n",
    "template/README.md": "# Readme\n",
    "tests/answers/demo.yml": downstream.text_of("Dennis-Otto/demo", ANSWERS),
}
# What the repository changed in the files of the blueprint, as repositories do.
OWN_CHANGES = {
    ".github/workflows/ci.yml": "name: CI\n# Demo, as we run it\n",
    "CONTRIBUTING.md": "# Demo\n\nAsk us first.\n",
}


@pytest.fixture(autouse=True)
def plain_git(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Git without the configuration of the machine, which may sign every commit."""
    config = tmp_path_factory.mktemp("home") / "gitconfig"
    config.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "Test")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "test@example.com")


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=root, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def write(root: Path, files: Mapping[str, str | None]) -> None:
    for name, content in files.items():
        path = root / name
        if content is None:
            path.unlink()
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")


def commit(root: Path, files: Mapping[str, str | None]) -> str:
    write(root, files)
    git(root, "add", "--all")
    git(root, "commit", "--quiet", "--message", "A change")
    return git(root, "rev-parse", "HEAD")


@pytest.fixture
def blueprint(tmp_path: Path) -> Path:
    """The template at its first release, v1.0.0."""
    root = tmp_path / "blueprint"
    root.mkdir()
    git(root, "init", "--quiet")
    commit(root, FILES)
    git(root, "tag", "v1.0.0")
    return root


@pytest.fixture
def remote(tmp_path: Path, blueprint: Path) -> Path:
    """The folder of the repositories on GitHub, with Dennis-Otto/demo, made from
    v1.0.0 and changed in two files of the blueprint since."""
    remote = tmp_path / "remote"
    project = remote / "Dennis-Otto" / "demo"
    # Copier in a process of its own, as downstream.py runs it: in this one, its Git
    # keeps the environment that it found at its import, before plain_git, and would
    # check the template out with the line endings of the machine.
    data = [f"--data={key}={value}" for key, value in ANSWERS.items()]
    downstream.run(
        tmp_path,
        sys.executable,
        "-m",
        "copier",
        "copy",
        "--quiet",
        "--defaults",
        "--vcs-ref=v1.0.0",
        *data,
        str(blueprint),
        str(project),
    )
    git(project, "init", "--quiet")
    commit(project, OWN_CHANGES)
    return remote


class Run:
    """downstream.py against the remote, with each run in a folder of its own."""

    def __init__(self, blueprint: Path, remote: Path, tmp_path: Path) -> None:
        self.blueprint, self.remote, self.tmp_path = blueprint, remote, tmp_path
        self.runs = 0
        self.sleeps: list[float] = []
        self.on_sleep: Callable[[], None] = lambda: None
        self.summary = ""

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.on_sleep()

    def __call__(self, *arguments: str, source: str = "") -> int:
        self.runs += 1
        summary = self.tmp_path / f"summary-{self.runs}.md"
        code = downstream.main(
            [
                *arguments,
                "--source",
                source or f"{self.remote.as_posix()}/{{repository}}",
                "--work",
                str(self.tmp_path / f"work-{self.runs}"),
                "--summary",
                str(summary),
            ],
            root=self.blueprint,
            sleep=self.sleep,
        )
        self.summary = summary.read_text(encoding="utf-8")
        return code


@pytest.fixture
def run(blueprint: Path, remote: Path, tmp_path: Path) -> Run:
    return Run(blueprint, remote, tmp_path)


def test_a_conflict_in_a_workflow_that_the_commit_brings_fails(
    blueprint: Path, run: Run, capsys: pytest.CaptureFixture[str]
) -> None:
    base = commit(blueprint, {"template/README.md": "# Readme\n\nMore.\n"})
    head = commit(
        blueprint,
        {"template/.github/workflows/ci.yml.jinja": "name: CI\n# The CI\n"},
    )

    assert run("--head", head, "--base", base) == 1
    out = capsys.readouterr().out
    assert (
        "::error title=A conflict in Dennis-Otto/demo::The update leaves a conflict"
        " in .github/workflows/ci.yml of Dennis-Otto/demo.\n"
    ) in out
    # The log shows the conflict.
    assert "::group::Dennis-Otto/demo: .github/workflows/ci.yml\n" in out
    assert "+<<<<<<< before updating\n" in out
    # The summary: the version that it has, the files of the update and those of the
    # commit, and the conflict.
    row = (
        "| [Dennis-Otto/demo](https://github.com/Dennis-Otto/demo) | v1.0.0 | 3 | 1 |"
        " `.github/workflows/ci.yml` |"
    )
    assert row in run.summary
    assert "| Repository | Has | Files of the update | Files of this commit |" in (
        run.summary
    )
    assert f"to {head[:7]}, and against {base[:7]}." in run.summary
    assert (
        "The files whose update this commit changes:\n\n- `.github/workflows/ci.yml`\n"
        in (run.summary)
    )
    assert "- `README.md` (M)\n" in run.summary


def test_a_conflict_in_a_page_warns(
    blueprint: Path, run: Run, capsys: pytest.CaptureFixture[str]
) -> None:
    base = git(blueprint, "rev-parse", "HEAD")
    head = commit(
        blueprint,
        {"template/CONTRIBUTING.md.jinja": "# {{ project_name }}\n\nOpen one.\n"},
    )

    assert run("--head", head, "--base", base) == 0
    assert (
        "::warning title=A conflict in Dennis-Otto/demo::The update leaves a conflict"
        " in CONTRIBUTING.md of Dennis-Otto/demo.\n"
    ) in capsys.readouterr().out
    assert "| `CONTRIBUTING.md` |" in run.summary


def test_a_conflict_that_the_base_has_already_is_not_the_commits(
    blueprint: Path, run: Run, capsys: pytest.CaptureFixture[str]
) -> None:
    base = commit(
        blueprint,
        {"template/.github/workflows/ci.yml.jinja": "name: CI\n# The CI\n"},
    )
    head = commit(blueprint, {"template/README.md": "# Readme\n\nMore.\n"})

    assert run("--head", head, "--base", base) == 0
    out = capsys.readouterr().out
    assert "::error" not in out
    assert "::warning" not in out
    assert "::group::" not in out
    assert "| 1 | `.github/workflows/ci.yml` (base) |" in run.summary
    assert "- `.github/workflows/ci.yml`, as the base leaves it already\n" in (
        run.summary
    )
    assert "The files whose update this commit changes:\n\n- `README.md`\n" in (
        run.summary
    )


def test_without_a_base_every_conflict_counts(
    blueprint: Path, run: Run, capsys: pytest.CaptureFixture[str]
) -> None:
    commit(
        blueprint,
        {"template/.github/workflows/ci.yml.jinja": "name: CI\n# The CI\n"},
    )

    # HEAD by default, as a person runs it.
    assert run() == 1
    assert "::error title=A conflict in Dennis-Otto/demo::" in capsys.readouterr().out
    assert "| Repository | Has | Files of the update | Conflicts |\n" in run.summary
    assert "| --- | --- | ---: | --- |\n" in run.summary
    assert "to HEAD. A conflict" in run.summary
    assert "| 2 | `.github/workflows/ci.yml` |" in run.summary
    assert "this commit changes" not in run.summary


def test_an_update_without_a_conflict_passes(
    blueprint: Path, run: Run, capsys: pytest.CaptureFixture[str]
) -> None:
    head = commit(blueprint, {"template/README.md": "# Readme\n\nMore.\n"})

    assert run("--head", head) == 0
    assert "::" not in capsys.readouterr().out
    assert "| v1.0.0 | 2 | none |" in run.summary
    assert "- `.copier-answers.yml` (M)\n- `README.md` (M)\n" in run.summary


def test_answers_that_differ_from_those_of_the_repository_warn(
    blueprint: Path, run: Run, capsys: pytest.CaptureFixture[str]
) -> None:
    write(
        blueprint,
        {
            "tests/answers/demo.yml": downstream.text_of(
                "Dennis-Otto/demo", {**ANSWERS, "project_name": "Other", "extra": 1}
            )
        },
    )

    assert run() == 0
    assert (
        "::warning file=tests/answers/demo.yml,title=The answers of Dennis-Otto/demo::"
        "extra, project_name differ from the answers of Dennis-Otto/demo; python3"
        " downstream.py --answers writes them anew.\n"
    ) in capsys.readouterr().out
    assert "- `tests/answers/demo.yml`: extra, project_name\n" in run.summary


def test_a_repository_that_cannot_be_cloned_fails(
    run: Run, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = f"{(tmp_path / 'nowhere').as_posix()}/{{repository}}"

    assert run(source=source) == 1
    # Three tries, 10 and 20 seconds apart.
    assert run.sleeps == [10, 20]
    out = capsys.readouterr().out
    assert (
        "::error title=The update of Dennis-Otto/demo::Dennis-Otto/demo could not"
        in out
    )
    assert (
        "| [Dennis-Otto/demo](https://github.com/Dennis-Otto/demo) | ? | could not"
        in (run.summary)
    )
    assert "<details>" not in run.summary


def test_a_clone_that_fails_once_is_tried_again(
    run: Run, remote: Path, tmp_path: Path
) -> None:
    later = tmp_path / "later"

    def appear() -> None:
        (later / "Dennis-Otto").mkdir(parents=True)
        (remote / "Dennis-Otto" / "demo").rename(later / "Dennis-Otto" / "demo")

    run.on_sleep = appear

    assert run(source=f"{later.as_posix()}/{{repository}}") == 0
    assert run.sleeps == [10]


@pytest.mark.parametrize(
    ("answers", "error"),
    [
        (None, "has no .copier-answers.yml"),
        (
            "_commit: v1.0.0\nproject_name: Demo\n",
            ".copier-answers.yml names no _src_path",
        ),
        ("_src_path: here\nowner: [\n", ".copier-answers.yml can't be read as YAML"),
    ],
)
def test_a_repository_without_its_answers_fails(
    remote: Path, run: Run, answers: str | None, error: str
) -> None:
    commit(remote / "Dennis-Otto" / "demo", {".copier-answers.yml": answers})

    assert run() == 1
    assert f"| ? | {error} |" in run.summary


def test_an_update_that_fails_fails(blueprint: Path, run: Run) -> None:
    head = commit(blueprint, {"copier.yml": '_min_copier_version: "99.0"\n' + COPIER})

    assert run("--head", head) == 1
    assert f"| v1.0.0 | could not be updated to {head[:7]}: " in run.summary


def test_a_ref_that_is_no_commit_stops_before_any_update(
    run: Run, capsys: pytest.CaptureFixture[str]
) -> None:
    assert downstream.main(["--base", "v9.9.9"], root=run.blueprint) == 2
    assert capsys.readouterr().err.startswith("downstream.py: v9.9.9 is no commit of ")


def test_a_remote_branch_is_the_commit_of_the_checkout_not_of_the_clone(
    blueprint: Path, run: Run, capsys: pytest.CaptureFixture[str]
) -> None:
    first = git(blueprint, "rev-parse", "HEAD")
    main = commit(
        blueprint,
        {"template/.github/workflows/ci.yml.jinja": "name: CI\n# The CI\n"},
    )
    commit(blueprint, {"template/README.md": "# Readme\n\nMore.\n"})
    # origin/main is ahead of the local main, which Copier's clone of the checkout
    # would take for origin/main.
    git(blueprint, "checkout", "--quiet", "-b", "feature")
    git(blueprint, "branch", "--force", "main", first)
    git(blueprint, "update-ref", "refs/remotes/origin/main", main)

    assert run("--base", "origin/main") == 0
    assert "::error" not in capsys.readouterr().out
    assert f"to HEAD, and against {main[:7]}." in run.summary
    assert "| 1 | `.github/workflows/ci.yml` (base) |" in run.summary


def test_a_folder_of_the_clones_with_another_spelling_of_its_path_works(
    blueprint: Path, remote: Path, tmp_path: Path
) -> None:
    # As a short name of Windows in TEMP: a path that isn't the one Git names.
    work = tmp_path / "elsewhere" / ".." / "work"
    source = f"{remote.as_posix()}/{{repository}}"

    assert (
        downstream.main(
            ["--source", source, "--work", str(work), "--summary", str(tmp_path / "s")],
            root=blueprint,
        )
        == 0
    )


def test_a_conflict_in_a_configuration_fails(
    blueprint: Path, remote: Path, run: Run, capsys: pytest.CaptureFixture[str]
) -> None:
    write(blueprint, {"template/.github/repository.toml": 'name = "blueprint"\n'})
    base = commit(blueprint, {})
    git(blueprint, "tag", "v1.1.0")
    project = remote / "Dennis-Otto" / "demo"
    downstream.run(
        project, sys.executable, "-m", "copier", "update", "--quiet", "--defaults"
    )
    commit(project, {".github/repository.toml": 'name = "ours"\n'})
    head = commit(blueprint, {"template/.github/repository.toml": 'name = "new"\n'})

    assert run("--head", head, "--base", base) == 1
    assert (
        "::error title=A conflict in Dennis-Otto/demo::The update leaves a conflict"
        " in .github/repository.toml of Dennis-Otto/demo.\n"
    ) in capsys.readouterr().out


@pytest.mark.parametrize(
    ("path", "page"),
    [
        ("CONTRIBUTING.md", True),
        ("docs/notes.txt", True),
        ("LICENSE", True),
        ("LICENSES/LICENSE.md", True),
        (".github/workflows/ci.yml", False),
        (".github/issue-assistant/config.toml", False),
        ("mkdocs.yml", False),
        ("Dockerfile", False),
        ("tests/stubs/OC.php", False),
    ],
)
def test_only_a_page_is_no_file_that_breaks(path: str, page: bool) -> None:
    update = downstream.Update("Dennis-Otto/demo", Path("demo.yml"), conflicts=[path])
    assert update.breaking == ([] if page else [path])


def test_the_summary_goes_to_the_summary_of_the_job(
    blueprint: Path,
    remote: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    summary = tmp_path / "summary.md"
    summary.write_text("Before.\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    source = f"{remote.as_posix()}/{{repository}}"

    assert downstream.main(["--source", source], root=blueprint) == 0
    assert summary.read_text(encoding="utf-8").startswith(
        "Before.\n## The update of each repository that takes the blueprint\n"
    )
    # Without one, in the terminal.
    monkeypatch.delenv("GITHUB_STEP_SUMMARY")
    capsys.readouterr()

    assert downstream.main(["--source", source], root=blueprint) == 0
    assert "## The update of each repository" in capsys.readouterr().out


def test_git_starts_no_maintenance_in_the_background() -> None:
    # Since Git 2.47, a commit starts git maintenance in the background, and copier
    # update deletes the repositories it commits to right away, as the bot knows.
    environment = downstream.environment()
    assert environment["GIT_CONFIG_COUNT"] == "1"
    assert environment["GIT_CONFIG_KEY_0"] == "maintenance.auto"
    assert environment["GIT_CONFIG_VALUE_0"] == "false"


class Opener:
    """urlopen offline: the answers of each address, or an error."""

    def __init__(self, pages: Mapping[str, str | OSError]) -> None:
        self.pages = dict(pages)
        self.urls: list[str] = []

    def __call__(self, request: Any, timeout: float) -> io.BytesIO:
        self.urls.append(request.full_url)
        assert request.get_header("User-agent") == downstream.AGENT
        page = self.pages[request.full_url]
        if isinstance(page, OSError):
            raise page
        return io.BytesIO(page.encode())


def test_a_new_question_that_the_repository_has_not_yet_is_no_drift(
    blueprint: Path, run: Run, capsys: pytest.CaptureFixture[str]
) -> None:
    write(
        blueprint,
        {
            "copier.yml": COPIER + "license:\n  type: str\n  default: MIT\n",
            "tests/answers/demo.yml": downstream.text_of(
                "Dennis-Otto/demo", {**ANSWERS, "license": "MIT"}
            ),
        },
    )

    assert run() == 0
    assert "::warning" not in capsys.readouterr().out
    assert "differ from those of a repository" not in run.summary


RAW = "https://raw.githubusercontent.com/Dennis-Otto/demo/HEAD/.copier-answers.yml"
THEIRS = (
    "# The answers of the blueprint\n_commit: v1.2.0\n"
    "_src_path: https://github.com/Dennis-Otto/repo-blueprint.git\n"
    "owner: Dennis-Otto\nproject_name: Demo 2\nproject_slug: demo\n"
)


def test_the_answers_are_written_anew_from_github(
    blueprint: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    opener = Opener({RAW: THEIRS})

    def fetch(url: str) -> str:
        return downstream.download(url, opener)

    assert downstream.main(["--answers"], root=blueprint, fetch=fetch) == 0
    assert capsys.readouterr().out == (
        "tests/answers/demo.yml: the answers of Dennis-Otto/demo\n"
    )
    assert (blueprint / "tests/answers/demo.yml").read_text(encoding="utf-8") == (
        downstream.HEADER.format(repository="Dennis-Otto/demo")
        + "owner: Dennis-Otto\nproject_name: Demo 2\nproject_slug: demo\n"
    )
    # Again, with nothing to write.
    assert downstream.main(["--answers"], root=blueprint, fetch=fetch) == 0
    assert capsys.readouterr().out == "Every answer is that of its repository.\n"
    assert opener.urls == [RAW, RAW]


def test_the_answer_of_a_new_question_stays_until_the_rollout(
    blueprint: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = blueprint / "tests/answers/demo.yml"
    write(
        blueprint,
        {
            "copier.yml": COPIER + "license:\n  type: str\n  default: MIT\n",
            "tests/answers/demo.yml": downstream.text_of(
                "Dennis-Otto/demo", {**ANSWERS, "license": "MIT", "gone": 1}
            ),
        },
    )

    assert downstream.main(["--answers"], root=blueprint, fetch=lambda _: THEIRS) == 0
    capsys.readouterr()
    # The answer that is no question any more goes, that of the new one stays.
    assert path.read_text(encoding="utf-8") == (
        downstream.HEADER.format(repository="Dennis-Otto/demo")
        + "license: MIT\nowner: Dennis-Otto\nproject_name: Demo 2\nproject_slug: demo\n"
    )


def test_a_download_tries_three_times(
    blueprint: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sleeps: list[float] = []
    opener = Opener({RAW: urllib.error.URLError("offline")})

    def fetch(url: str) -> str:
        return downstream.download(url, opener, sleeps.append)

    assert downstream.main(["--answers"], root=blueprint, fetch=fetch) == 2
    assert sleeps == [10, 20]
    assert capsys.readouterr().err == (
        f"downstream.py: {RAW} could not be downloaded: <urlopen error offline>\n"
    )


def test_every_file_of_the_answers_is_written_as_the_script_writes_it() -> None:
    for path in sorted((ROOT / "tests/answers").glob("*.yml")):
        answers = downstream.read(path)
        repository = downstream.repository_of(answers)
        assert path.read_text(encoding="utf-8") == downstream.text_of(
            repository, answers
        ), path


def test_answers_from_github_that_are_none_change_nothing(
    blueprint: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = blueprint / "tests/answers/demo.yml"
    before = path.read_text(encoding="utf-8")

    assert downstream.main(["--answers"], root=blueprint, fetch=lambda _: "Moved.") == 2
    assert capsys.readouterr().err == f"downstream.py: {RAW} holds no answers\n"
    assert path.read_text(encoding="utf-8") == before


def test_a_command_that_fails_without_a_word_names_its_exit_code(
    tmp_path: Path,
) -> None:
    with pytest.raises(downstream.Failed, match=r"^exit code 3$"):
        downstream.run(tmp_path, sys.executable, "-c", "raise SystemExit(3)")
