"""Tests of what the processes of one run of the tests share."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import time
import tomllib
from importlib.util import cache_from_source
from pathlib import Path, PurePosixPath

import pytest
import shared
import yaml
from shared import INTERVAL, copy_of, load_yaml, once, run_folder


def made_elsewhere(folder: Path) -> None:
    pytest.fail(f"{folder} is another process's to make")


def test_the_folder_of_the_run_holds_that_of_each_process(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
    alone = run_folder(tmp_path_factory)
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw3")
    shared_by_all = run_folder(tmp_path_factory)

    assert alone == tmp_path_factory.getbasetemp()
    assert shared_by_all == tmp_path_factory.getbasetemp().parent


def test_the_processes_of_the_run_share_one_folder_for_their_bytecode(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    # A folder for each process compiles the standard library and Copier once in each.
    folder = str(run_folder(tmp_path_factory) / "pycache")

    assert sys.pycache_prefix == folder
    assert os.environ["PYTHONPYCACHEPREFIX"] == folder


def test_a_python_of_a_test_reads_the_bytecode_that_another_one_wrote(
    tmp_path: Path,
) -> None:
    module = tmp_path / "written_once.py"
    module.write_text("VALUE = 1\n", encoding="utf-8")
    command = [sys.executable, "-c", "import written_once"]
    # A machine may set the variable that writes no bytecode at all.
    environment = {
        name: value
        for name, value in os.environ.items()
        if name != "PYTHONDONTWRITEBYTECODE"
    }

    subprocess.run(command, cwd=tmp_path, env=environment, check=True)
    written = Path(cache_from_source(str(module)))
    before = written.stat().st_mtime_ns
    subprocess.run(command, cwd=tmp_path, env=environment, check=True)

    assert written.stat().st_mtime_ns == before
    assert not (tmp_path / "__pycache__").exists()


@pytest.mark.parametrize(
    "text",
    [
        "on: push\nyes: [1, 1.5, 0x10, ~, 2026-11-01]\n",
        "base: &base {a: 1}\nderived:\n  <<: *base\n  b: |\n    text\n",
        '"quoted: key": "\u00dcmlaut"\n',
    ],
)
def test_the_fast_parser_reads_what_the_safe_one_reads(text: str) -> None:
    assert load_yaml(text) == yaml.safe_load(text)


def test_the_fast_parser_reads_the_workflows_as_the_safe_one_does() -> None:
    for workflow in (shared.ROOT / ".github/workflows").glob("*.yml"):
        text = workflow.read_text(encoding="utf-8")
        assert load_yaml(text) == yaml.safe_load(text), workflow.name


def test_no_test_parses_yaml_with_the_slow_parser() -> None:
    # The parser of Python took 23 of 460 seconds of all the processes of a run.
    slow = "yaml." + "safe_load("
    found = [
        path.name
        for path in Path(__file__).parent.glob("*.py")
        if path != Path(__file__) and slow in path.read_text(encoding="utf-8")
    ]

    assert not found


def measured_name(path: str, packages: list[str]) -> str | None:
    """The name under which coverage measures the file at path from the root, by the
    source_pkgs of pyproject.toml, such as blueprint.website for blueprint/website.py
    and mkdocs_blueprint for .github/mkdocs_blueprint.py; None for a file it doesn't."""
    parts = PurePosixPath(path).with_suffix("").parts
    if parts[0] in packages:
        return ".".join(parts)
    if parts[-1] in packages:
        return parts[-1]
    return None


def test_the_name_of_a_file_coverage_measures_is_that_of_its_module() -> None:
    assert measured_name("blueprint/website.py", ["blueprint"]) == "blueprint.website"
    assert measured_name(".github/mkdocs_blueprint.py", ["mkdocs_blueprint"]) == (
        "mkdocs_blueprint"
    )
    assert measured_name(".github/mkdocs_project.py", ["mkdocs_blueprint"]) is None


def blueprint_path(node: ast.expr, names: dict[str, ast.expr]) -> str | None:
    """The path from the root of the blueprint that an expression of a test names, such
    as .github/x.py for ROOT / ".github" / "x.py", through the names that its module
    assigns and with {name} for a value of an f-string; None for a path that does not
    start at the root, such as tmp_path / "x.py"."""
    match node:
        case (
            ast.Name(id="ROOT")
            | ast.Subscript(
                value=ast.Attribute(attr="parents"), slice=ast.Constant(value=1)
            )
        ):
            # ROOT, or Path(__file__).parents[1] of a test in tests/.
            return "."
        case ast.Name(id=name) if name in names:
            return blueprint_path(names[name], names)
        case ast.BinOp(left=left, op=ast.Div(), right=right):
            base = blueprint_path(left, names)
            return (
                None if base is None else (PurePosixPath(base) / part(right)).as_posix()
            )
        case _:
            return None


def part(node: ast.expr) -> str:
    """The text of one part of a path, with {name} for a value of an f-string and {?}
    for any other expression."""
    match node:
        case ast.Constant(value=str(text)):
            return text
        case ast.JoinedStr(values=values):
            return "".join(part(value) for value in values)
        case ast.FormattedValue(value=ast.Name(id=name)):
            return "{" + name + "}"
        case _:
            return "{?}"


def wrong_loads(source: str, packages: list[str]) -> tuple[list[str], list[str]]:
    """The loads of a file of the blueprint by its path in the source of a test: those
    under the name that coverage measures, and those under another name or under one
    that this can't tell, by line."""
    tree = ast.parse(source)
    names = {
        target.id: statement.value
        for statement in tree.body
        if isinstance(statement, ast.Assign)
        for target in statement.targets
        if isinstance(target, ast.Name)
    }
    checked: list[str] = []
    found: list[str] = []
    for call in ast.walk(tree):
        if not (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "spec_from_file_location"
        ):
            continue
        name, where = call.args[:2]
        # Not a file of a project that a test renders, which coverage never measures.
        path = blueprint_path(where, names)
        if path is None:
            continue
        file = PurePosixPath(path)
        match name:
            case ast.Constant(value=str(loaded)) if "{" not in path:
                expected = measured_name(path, packages)
                if expected is not None:
                    checked.append(expected)
                    if loaded != expected:
                        found.append(f"{call.lineno} {loaded}")
            case ast.Name(id=variable) if (
                file.name == f"{{{variable}}}.py"
                and "{" not in file.parent.as_posix()
                and file.parts[0] not in packages
            ):
                # A file named after the module that it holds, outside a package, such
                # as module(name) of .github/docs-pictures/{name}.py: its name is the
                # one coverage measures.
                checked.append(path)
            case _:
                found.append(f"{call.lineno} can't tell")
    return checked, found


def test_a_load_is_checked_whatever_way_its_path_is_written() -> None:
    packages = ["blueprint", "hooks", "pictures"]
    source = """
HOOKS = Path(__file__).parents[1] / ".github/hooks.py"
a = importlib.util.spec_from_file_location("hooks", ROOT / ".github" / "hooks.py")
b = importlib.util.spec_from_file_location("hooks_of_tests", HOOKS)
c = importlib.util.spec_from_file_location(name, ROOT / f".github/pictures/{name}.py")
d = importlib.util.spec_from_file_location(name, ROOT / f".github/{kind}/{name}.py")
e = importlib.util.spec_from_file_location(name, ROOT / ".github" / name)
f = importlib.util.spec_from_file_location(f"x_{name}", ROOT / "blueprint/cli.py")
g = importlib.util.spec_from_file_location("website", ROOT / "blueprint/website.py")
h = importlib.util.spec_from_file_location("other", ROOT / ".github/other.py")
i = importlib.util.spec_from_file_location("hooks", project / ".github/hooks.py")
j = importlib.util.spec_from_file_location(name, ROOT / f"blueprint/{name}.py")
"""
    checked, found = wrong_loads(source, packages)

    assert checked == [
        "hooks",
        "hooks",
        ".github/pictures/{name}.py",
        "blueprint.website",
    ]
    assert found == [
        "4 hooks_of_tests",
        "6 can't tell",
        "7 can't tell",
        "8 can't tell",
        "9 website",
        "12 can't tell",
    ]


def test_every_test_loads_a_measured_file_under_the_name_coverage_measures() -> None:
    # Coverage decides by the name of the module whether it measures a file, the first
    # time that a process runs it, and keeps that for the file: a test that loads
    # .github/mkdocs_blueprint.py under another name first hid the file from coverage
    # in its process, so that a line that only a later test of that process ran was
    # missed, depending on the order of the tests (#946).
    settings = tomllib.loads(
        (shared.ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    packages = settings["tool"]["coverage"]["run"]["source_pkgs"]
    checked: list[str] = []
    found: list[str] = []
    for test in sorted(Path(__file__).parent.glob("*.py")):
        seen, wrong = wrong_loads(test.read_text(encoding="utf-8"), packages)
        checked += seen
        found += [f"{test.name}:{line}" for line in wrong]

    assert not found, "loaded under a name that coverage doesn't measure"
    # The check sees the loads in each way that the tests write them: the hooks of the
    # website, which caused #946, by ROOT / "path" and by a name of the module, and the
    # scripts of the pictures by an f-string.
    assert {
        "mkdocs_blueprint",
        "mkdocs_project",
        "difference_picture",
        ".github/docs-pictures/{name}.py",
    } <= set(checked)
    assert checked.count("mkdocs_blueprint") > 4


def test_a_folder_is_made_once(tmp_path: Path) -> None:
    made: list[Path] = []

    def make(folder: Path) -> None:
        made.append(folder)
        folder.mkdir()

    first = once(tmp_path / "project", make)
    again = once(tmp_path / "project", make)

    assert first == again == tmp_path / "project"
    assert made == [tmp_path / "project"]
    assert (tmp_path / "project.done").exists()


def test_a_process_waits_for_the_folder_that_another_one_makes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Another process has claimed the folder, and finishes it while this one waits.
    (tmp_path / "project.claim").mkdir()
    waits: list[float] = []

    def sleep(seconds: float) -> None:
        waits.append(seconds)
        (tmp_path / "project.done").touch()

    monkeypatch.setattr(time, "sleep", sleep)

    assert once(tmp_path / "project", made_elsewhere) == tmp_path / "project"
    assert waits == [INTERVAL]


def test_a_folder_that_failed_fails_for_every_process(tmp_path: Path) -> None:
    def make(folder: Path) -> None:
        raise OSError("No space left on device")

    with pytest.raises(OSError, match="No space left on device"):
        once(tmp_path / "project", make)
    # Another process learns why, instead of waiting for a folder that never comes.
    with pytest.raises(RuntimeError, match="OSError: No space left on device"):
        once(tmp_path / "project", make)


def test_a_process_waits_no_longer_than_its_patience(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "project.claim").mkdir()
    monkeypatch.setattr(shared, "PATIENCE", -1.0)

    with pytest.raises(TimeoutError, match=r"didn't make .*project within"):
        once(tmp_path / "project", made_elsewhere)


def test_the_copy_of_a_repository_has_its_files_as_git_sees_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Git without the configuration of the machine, which may sign every commit.
    config = tmp_path / "gitconfig"
    config.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    repository = tmp_path / "repository"
    (repository / "docs").mkdir(parents=True)
    for name, text in {
        ".gitignore": ".venv/\n",
        "docs/kept.md": "Committed.\n",
        "changed.md": "Committed.\n",
        "deleted.md": "Committed.\n",
    }.items():
        (repository / name).write_text(text, encoding="utf-8")
    identity = ["-c", "user.name=Dev", "-c", "user.email=dev@example.com"]
    for arguments in (
        ["init", "--quiet"],
        ["add", "--all"],
        [*identity, "commit", "--quiet", "--message", "The start"],
    ):
        subprocess.run(["git", *arguments], cwd=repository, check=True)
    (repository / "changed.md").write_text("Not yet committed.\n", encoding="utf-8")
    (repository / "deleted.md").unlink()
    (repository / "new.md").write_text("Not yet added.\n", encoding="utf-8")
    (repository / ".venv").mkdir()
    (repository / ".venv/pyvenv.cfg").write_text("home = /usr\n", encoding="utf-8")

    copy_of(repository, tmp_path / "copy")

    assert sorted(
        path.relative_to(tmp_path / "copy").as_posix()
        for path in (tmp_path / "copy").rglob("*")
        if path.is_file()
    ) == [".gitignore", "changed.md", "docs/kept.md", "new.md"]
    assert (tmp_path / "copy/changed.md").read_text(encoding="utf-8") == (
        "Not yet committed.\n"
    )


def test_no_test_sees_the_repository_that_runs_the_tests() -> None:
    assert "GIT_DIR" in shared.GIT_REPOSITORY_VARIABLES
    assert not set(shared.GIT_REPOSITORY_VARIABLES) & set(os.environ)


# It runs the tests in a copy of the repository again, which the copy of the mutation
# tests has no configuration of pytest for; it tests no code of the blueprint.
@pytest.mark.mutation_unsafe
def test_the_tests_leave_the_repository_that_git_dir_names_alone(
    tmp_path: Path,
) -> None:
    # Git sets GIT_DIR for its hooks in a worktree, such as the one before a push that
    # runs the tests, and an agent sets GIT_DIR and GIT_WORK_TREE for a worktree in a
    # container. A test that makes a repository of its own with git init and commits
    # must still leave that one alone: its commits, branches, configuration and
    # checkout.
    outer = tmp_path / "outer"
    outer.mkdir()
    environment = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": str(tmp_path / "gitconfig"),
        "GIT_CONFIG_NOSYSTEM": "1",
    }

    def git(*arguments: str) -> str:
        return subprocess.run(
            [
                "git",
                "-c",
                "user.name=Dev",
                "-c",
                "user.email=dev@example.com",
                *arguments,
            ],
            cwd=outer,
            capture_output=True,
            encoding="utf-8",
            env=environment,
            check=True,
        ).stdout

    def state() -> str:
        return (
            git("for-each-ref")
            + git("status", "--porcelain", "--untracked-files=all")
            + (outer / ".git/config").read_text(encoding="utf-8")
        )

    (outer / "README.md").write_text(
        "The repository that runs the tests.\n", encoding="utf-8"
    )
    git("init", "--quiet")
    git("add", "README.md")
    git("commit", "--quiet", "--message", "The start")
    # A change not yet committed, which a git add --all of a test would take in.
    (outer / "notes.md").write_text("Not yet committed.\n", encoding="utf-8")
    before = state()
    # A test that commits in a repository of its own.
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "-q",
            f"--basetemp={tmp_path / 'run'}",
            "tests/test_shared.py::"
            "test_the_copy_of_a_repository_has_its_files_as_git_sees_them",
        ],
        cwd=shared.ROOT,
        capture_output=True,
        encoding="utf-8",
        env={
            **environment,
            "GIT_DIR": str(outer / ".git"),
            "GIT_WORK_TREE": str(outer),
            "GIT_INDEX_FILE": str(outer / ".git/index"),
        },
        check=False,
    )

    assert state() == before
    assert run.returncode == 0, run.stdout + run.stderr
