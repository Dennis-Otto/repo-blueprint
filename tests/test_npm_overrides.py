"""Tests of blueprint/npm_overrides.py, which removes an override of npm that an update
has made needless, as Renovate runs it after an update of npm, and of its command
blueprint.py npm-overrides."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from blueprint import npm_overrides
from blueprint.cli import main
from blueprint.npm_overrides import (
    INSTALL,
    ZERO,
    Override,
    Version,
    caps,
    floor_of,
    judge,
    manifests,
    needless,
    npm_in,
    overrides_of,
    package_name,
    version_of,
    without,
    written,
)

GIT = shutil.which("git")
needs_git = pytest.mark.skipif(
    GIT is None, reason="the command looks at the files that git keeps"
)

# The package.json of homedarts-for-autodarts in its pull request #783, in which
# ESLint 10.15.0 asks for minimatch ^11.0.5 itself.
HOMEDARTS = (
    "{\n"
    '  "name": "hacs-homedarts-development",\n'
    '  "private": true,\n'
    '  "devDependencies": {\n'
    '    "eslint": "10.15.0"\n'
    "  },\n"
    '  "overrides": {\n'
    '    "minimatch": "11.0.8"\n'
    "  }\n"
    "}\n"
)
WITHOUT_THE_OVERRIDE = (
    "{\n"
    '  "name": "hacs-homedarts-development",\n'
    '  "private": true,\n'
    '  "devDependencies": {\n'
    '    "eslint": "10.15.0"\n'
    "  }\n"
    "}\n"
)
# The nested override of player-switch-for-autodarts: multimatch 6.0.0 asks for
# minimatch ^3.0.4, which no override reaches.
PLAYER_SWITCH = {
    "name": "player-switch-for-autodarts",
    "devDependencies": {"web-ext": "10.8.0"},
    "overrides": {"addons-linter": {"minimatch": "^11.0.3"}},
}


def lock(**copies: str) -> dict[str, Any]:
    """A package-lock.json of version 3 with these packages, by their folder below
    node_modules/ with / for each node_modules/ between, as in eslint/minimatch."""
    packages: dict[str, Any] = {"": {"name": "project"}}
    for folder, version in copies.items():
        path = "node_modules/" + folder.replace("__", "/node_modules/")
        packages[path] = {"version": version}
    return {
        "name": "project",
        "lockfileVersion": 3,
        "requires": True,
        "packages": packages,
    }


def dumped(content: dict[str, Any]) -> str:
    return json.dumps(content, indent=2) + "\n"


class FakeNpm:
    """npm, which writes the lock files that a test gives it and keeps what it was
    asked: the folder of each call and the package.json that it found there."""

    def __init__(self, *locks: dict[str, Any], returncode: int = 0) -> None:
        self.locks = list(locks)
        self.returncode = returncode
        self.folders: list[Path] = []
        self.manifests: list[dict[str, Any]] = []
        self.stderr = ""

    def __call__(self, folder: Path) -> subprocess.CompletedProcess[str]:
        self.folders.append(folder)
        self.manifests.append(
            json.loads((folder / "package.json").read_text(encoding="utf-8"))
        )
        if self.locks:
            (folder / "package-lock.json").write_text(
                dumped(self.locks.pop(0)), encoding="utf-8", newline="\n"
            )
        return subprocess.CompletedProcess(["npm"], self.returncode, "", self.stderr)


def project(root: Path, files: dict[str, str]) -> Path:
    """A git repository with these files, which git keeps."""
    assert GIT
    subprocess.run([GIT, "init", "--quiet", str(root)], check=True)
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(text.encode("utf-8"))
    subprocess.run([GIT, "-C", str(root), "add", "--all"], check=True)
    return root


def contents(root: Path, *names: str) -> list[bytes]:
    return [(root / name).read_bytes() for name in names]


# ------------------------------------------------------------- what npm still needs


@needs_git
def test_an_override_that_every_copy_reaches_without_it_leaves(tmp_path: Path) -> None:
    old = lock(eslint="10.15.0", minimatch="11.0.8")
    root = project(
        tmp_path, {"package.json": HOMEDARTS, "package-lock.json": dumped(old)}
    )
    # Without the override, npm keeps the lock file as it is: ESLint asks for ^11.0.5.
    npm = FakeNpm(old)

    (outcome,) = needless(root, "package.json", npm, fix=True)

    assert outcome.needless
    assert outcome.reason == "without it npm takes minimatch 11.0.8"
    assert not outcome.note
    # npm wrote the lock file without the override, which leaves package.json alone:
    # the rest of it, its indent, the order of its keys and its last newline stay.
    assert npm.manifests[0] == json.loads(WITHOUT_THE_OVERRIDE)
    assert npm.folders == [root]
    assert contents(root, "package.json", "package-lock.json") == [
        WITHOUT_THE_OVERRIDE.encode(),
        dumped(old).encode(),
    ]


@needs_git
def test_an_override_that_npm_still_needs_stays_byte_for_byte(tmp_path: Path) -> None:
    # The files of homedarts' main: without the override, npm puts minimatch 10.2.6
    # below ESLint and its config array again. The package.json has its own form,
    # with tabs, the line ends of Windows and no last newline, which stays as well.
    manifest = HOMEDARTS.replace("  ", "\t").replace("\n", "\r\n").rstrip()
    old = lock(eslint="10.14.0", minimatch="11.0.5")
    root = project(
        tmp_path, {"package.json": manifest, "package-lock.json": dumped(old) + " "}
    )
    before = contents(root, "package.json", "package-lock.json")
    npm = FakeNpm(
        lock(
            eslint="10.14.0",
            eslint__minimatch="10.2.6",
            **{"@eslint/config-array__minimatch": "10.2.6"},
            minimatch="11.0.5",
        )
    )

    (outcome,) = needless(root, "package.json", npm, fix=True)

    assert not outcome.needless
    assert outcome.reason == (
        "without it npm takes minimatch 10.2.6 at "
        "node_modules/@eslint/config-array/node_modules/minimatch, below 11.0.8"
    )
    assert contents(root, "package.json", "package-lock.json") == before


@needs_git
def test_an_override_whose_lock_file_brings_a_new_version_stays(tmp_path: Path) -> None:
    # Renovate gives npm --before= only on its own call, so a version that the lock
    # file didn't have may be younger than a week: the override stays.
    old = lock(eslint="10.15.0", minimatch="11.0.8", **{"brace-expansion": "5.0.0"})
    root = project(
        tmp_path, {"package.json": HOMEDARTS, "package-lock.json": dumped(old)}
    )
    before = contents(root, "package.json", "package-lock.json")
    npm = FakeNpm(
        lock(eslint="10.15.0", minimatch="11.0.8", **{"brace-expansion": "5.0.1"})
    )

    (outcome,) = needless(root, "package.json", npm, fix=True)

    assert not outcome.needless
    assert outcome.reason == (
        "without it npm brings brace-expansion@5.0.1, which the lock file doesn't "
        "have, and only Renovate's own call of npm keeps to versions a week old"
    )
    assert contents(root, "package.json", "package-lock.json") == before


@needs_git
def test_a_nested_range_leaves_while_a_copy_outside_its_reach_stays_below(
    tmp_path: Path,
) -> None:
    # minimatch 3.1.5 below multimatch is below the floor 11.0.3 of the range with
    # the override and without it: it doesn't hold the removal back.
    old = lock(
        **{"addons-linter": "10.4.0"},
        minimatch="11.0.5",
        multimatch="6.0.0",
        multimatch__minimatch="3.1.5",
    )
    root = project(
        tmp_path,
        {"package.json": dumped(PLAYER_SWITCH), "package-lock.json": dumped(old)},
    )
    npm = FakeNpm(old)

    (outcome,) = needless(root, "package.json", npm, fix=True)

    assert outcome.override == Override(
        ("addons-linter", "minimatch"), "minimatch", "^11.0.3"
    )
    assert outcome.override.label() == "minimatch ^11.0.3 below addons-linter"
    assert outcome.needless
    assert outcome.reason == "without it npm takes minimatch 11.0.5, 3.1.5"
    # The package.json leaves without overrides, which the removal left empty.
    expected = {
        key: value for key, value in PLAYER_SWITCH.items() if key != "overrides"
    }
    assert (root / "package.json").read_text(encoding="utf-8") == dumped(expected)


@needs_git
def test_a_nested_range_stays_when_a_copy_in_its_reach_goes_below(
    tmp_path: Path,
) -> None:
    # minimatch 3.1.5 is in the lock file already, so it brings no new version, but
    # without the override it comes below addons-linter as well, at a path that held
    # minimatch 11.0.5: the override stays.
    old = lock(
        **{"addons-linter": "10.4.0", "addons-linter__minimatch": "11.0.5"},
        multimatch="6.0.0",
        minimatch="3.1.5",
    )
    root = project(
        tmp_path,
        {"package.json": dumped(PLAYER_SWITCH), "package-lock.json": dumped(old)},
    )
    npm = FakeNpm(
        lock(
            **{"addons-linter": "10.4.0", "addons-linter__minimatch": "3.1.5"},
            multimatch="6.0.0",
            minimatch="3.1.5",
        )
    )

    (outcome,) = needless(root, "package.json", npm, fix=True)

    assert not outcome.needless
    assert outcome.reason == (
        "without it npm takes minimatch 3.1.5 at "
        "node_modules/addons-linter/node_modules/minimatch, below ^11.0.3"
    )
    assert (root / "package.json").read_text(encoding="utf-8") == dumped(PLAYER_SWITCH)


@needs_git
def test_a_new_copy_below_the_floor_holds_the_override_too(tmp_path: Path) -> None:
    # A copy at a path that the old lock file didn't have counts as well, even of a
    # version that the old one had elsewhere.
    old = lock(minimatch="11.0.8", other__minimatch="3.1.5")
    root = project(
        tmp_path, {"package.json": HOMEDARTS, "package-lock.json": dumped(old)}
    )
    npm = FakeNpm(
        lock(minimatch="11.0.8", other__minimatch="3.1.5", eslint__minimatch="3.1.5")
    )

    (outcome,) = needless(root, "package.json", npm, fix=True)

    assert not outcome.needless
    assert "at node_modules/eslint/node_modules/minimatch" in outcome.reason


@needs_git
def test_a_copy_below_the_floor_that_changes_its_version_holds_the_override(
    tmp_path: Path,
) -> None:
    # node_modules/minimatch sat below the floor at 3.1.5; without the override npm
    # hoists 10.2.6 there, which the old lock file had elsewhere: still below, but
    # another version, so it may be the copy that the override reached.
    old = lock(
        **{"addons-linter": "10.4.0", "addons-linter__minimatch": "11.0.5"},
        minimatch="3.1.5",
        other__minimatch="10.2.6",
    )
    root = project(
        tmp_path,
        {"package.json": dumped(PLAYER_SWITCH), "package-lock.json": dumped(old)},
    )
    npm = FakeNpm(
        lock(
            **{"addons-linter": "10.4.0"},
            minimatch="10.2.6",
            other__minimatch="10.2.6",
        )
    )

    (outcome,) = needless(root, "package.json", npm, fix=True)

    assert not outcome.needless
    assert outcome.reason == (
        "without it npm takes minimatch 10.2.6 at node_modules/minimatch, below ^11.0.3"
    )
    assert (root / "package.json").read_text(encoding="utf-8") == dumped(PLAYER_SWITCH)


@needs_git
def test_each_override_is_tried_on_what_the_one_before_left(tmp_path: Path) -> None:
    # Two overrides below one package: the first leaves, the second stays, and so does
    # the package around it, which the second still fills.
    manifest = {
        "name": "project",
        "//": "Drop the overrides once ESLint asks for the fixed versions.",
        "overrides": {"eslint": {"minimatch": "11.0.8", "ajv": "6.14.0"}},
    }
    old = lock(eslint="10.15.0", minimatch="11.0.8", ajv="6.14.0")
    root = project(
        tmp_path, {"package.json": dumped(manifest), "package-lock.json": dumped(old)}
    )
    npm = FakeNpm(old, lock(eslint="10.15.0", minimatch="11.0.8", ajv="6.12.6"))

    first, second = needless(root, "package.json", npm, fix=True)

    assert (first.needless, first.note) == (True, True)
    assert (second.needless, second.note) == (False, False)
    # The second try leaves no override at all, and no empty object of one.
    assert "overrides" not in npm.manifests[1]
    assert json.loads((root / "package.json").read_text(encoding="utf-8")) == {
        "name": "project",
        "//": manifest["//"],
        "overrides": {"eslint": {"ajv": "6.14.0"}},
    }


@needs_git
def test_without_fix_the_command_puts_back_what_npm_no_longer_needs(
    tmp_path: Path,
) -> None:
    old = lock(eslint="10.15.0", minimatch="11.0.8")
    root = project(
        tmp_path, {"package.json": HOMEDARTS, "package-lock.json": dumped(old)}
    )
    npm = FakeNpm(old)
    before = contents(root, "package.json", "package-lock.json")

    (outcome,) = needless(root, "package.json", npm, fix=False)

    assert outcome.needless
    assert contents(root, "package.json", "package-lock.json") == before


@needs_git
def test_an_override_that_names_no_version_stays_without_npm(tmp_path: Path) -> None:
    manifest = {
        "overrides": {
            "eslint": {".": "10.15.0"},
            "ajv": "$ajv",
            "minimatch@^3": "npm:@other/minimatch@1.0.0",
        }
    }
    old = lock(eslint="10.15.0")
    root = project(
        tmp_path, {"package.json": dumped(manifest), "package-lock.json": dumped(old)}
    )
    npm = FakeNpm(old)

    first, second, third = needless(root, "package.json", npm, fix=True)

    assert first.override.name == "eslint"
    assert first.override.label() == "eslint 10.15.0"
    assert first.needless
    assert [second.override.name, third.override.name] == ["ajv", "minimatch"]
    assert [second.reason, third.reason] == ["it names no version, so it stays"] * 2
    assert len(npm.folders) == 1


@needs_git
@pytest.mark.parametrize("spec", ["<2", "1.2.3 - 1.4.0"])
def test_an_override_that_caps_its_package_stays_without_npm(
    tmp_path: Path, spec: str
) -> None:
    # The lock file holds foo 1.5.0 with the cap and would without it, but the cap
    # keeps the next refresh of the lock file from foo 2: it stays.
    manifest = {"dependencies": {"bar": "1.0.0"}, "overrides": {"foo": spec}}
    old = lock(bar="1.0.0", foo="1.5.0")
    root = project(
        tmp_path, {"package.json": dumped(manifest), "package-lock.json": dumped(old)}
    )
    before = contents(root, "package.json", "package-lock.json")
    npm = FakeNpm(old)

    (outcome,) = needless(root, "package.json", npm, fix=True)

    assert not outcome.needless
    assert outcome.reason == "it caps the package, so it stays"
    assert npm.folders == []
    assert contents(root, "package.json", "package-lock.json") == before


@needs_git
@pytest.mark.parametrize(
    ("stderr", "message"),
    [("one\nnpm error E404\n", "npm error E404"), ("", "no message")],
)
def test_a_failure_of_npm_keeps_the_override(
    tmp_path: Path, stderr: str, message: str
) -> None:
    old = lock(minimatch="11.0.8")
    root = project(
        tmp_path, {"package.json": HOMEDARTS, "package-lock.json": dumped(old)}
    )
    before = contents(root, "package.json", "package-lock.json")
    npm = FakeNpm(lock(), returncode=1)
    npm.stderr = stderr

    (outcome,) = needless(root, "package.json", npm, fix=True)

    assert not outcome.needless
    assert outcome.reason == f"npm failed without it: {message}"
    assert contents(root, "package.json", "package-lock.json") == before


@needs_git
def test_an_error_of_npm_puts_both_files_back(tmp_path: Path) -> None:
    root = project(
        tmp_path,
        {"package.json": HOMEDARTS, "package-lock.json": dumped(lock(minimatch="1"))},
    )
    before = contents(root, "package.json", "package-lock.json")

    def broken(folder: Path) -> subprocess.CompletedProcess[str]:
        (folder / "package-lock.json").write_text("{", encoding="utf-8")
        raise OSError("npm went away")

    with pytest.raises(OSError, match="npm went away"):
        needless(root, "package.json", broken, fix=True)
    assert contents(root, "package.json", "package-lock.json") == before


@needs_git
def test_a_package_json_with_a_key_twice_is_left_alone(tmp_path: Path) -> None:
    text = '{"//": "one", "//": "two", "overrides": {"minimatch": "11.0.8"}}\n'
    root = project(
        tmp_path, {"package.json": text, "package-lock.json": dumped(lock())}
    )

    with pytest.raises(ValueError, match="isn't JSON that it can write back"):
        needless(root, "package.json", FakeNpm(), fix=True)
    assert (root / "package.json").read_text(encoding="utf-8") == text


@needs_git
def test_overrides_that_are_no_object_are_nothing_to_try(tmp_path: Path) -> None:
    text = '{"description": "the \\"overrides\\" come later", "overrides": []}\n'
    root = project(
        tmp_path, {"package.json": text, "package-lock.json": dumped(lock())}
    )

    assert needless(root, "package.json", FakeNpm(), fix=True) == []


# ------------------------------------------------------------------- the files


@needs_git
def test_the_command_finds_each_package_json_with_overrides_and_a_lock_file(
    tmp_path: Path,
) -> None:
    with_overrides = dumped({"overrides": {"minimatch": "11.0.8"}})
    root = project(
        tmp_path,
        {
            # paperless-sync keeps its ESLint in a folder of its own.
            "scripts/eslint/package.json": with_overrides,
            "scripts/eslint/package-lock.json": dumped(lock()),
            "package.json": dumped({"name": "project"}),
            "package-lock.json": dumped(lock()),
            "no-lock/package.json": with_overrides,
            "node_modules/minimatch/package.json": with_overrides,
            "node_modules/minimatch/package-lock.json": dumped(lock()),
            "other/package.json.orig": with_overrides,
        },
    )

    assert manifests(root) == ["scripts/eslint/package.json"]


@needs_git
def test_an_untracked_package_json_of_another_tool_is_left_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Renovate's Composer update installs into stacks/php/vendor/, and its checkout
    # keeps that folder for the next branch; no .gitignore names it here.
    old = lock(eslint="10.15.0", minimatch="11.0.8")
    root = project(
        tmp_path, {"package.json": HOMEDARTS, "package-lock.json": dumped(old)}
    )
    vendored = {
        "stacks/php/vendor/acme/tool/package.json": HOMEDARTS,
        "stacks/php/vendor/acme/tool/package-lock.json": dumped(old),
    }
    for name, text in vendored.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(text.encode("utf-8"))
    npm = FakeNpm(old, old)
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(npm_overrides, "npm_in", lambda path: npm)

    assert main(["npm-overrides", "--fix"], root=root) == 0

    assert npm.folders == [root]
    assert contents(root, "package.json") == [WITHOUT_THE_OVERRIDE.encode()]
    assert contents(root, *vendored) == [text.encode() for text in vendored.values()]


@needs_git
def test_the_command_removes_an_override_in_a_folder_and_names_its_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = {
        "name": "paperless-sync-eslint",
        "//": "Drop the override when ESLint asks for a fixed minimatch itself.",
        "overrides": {"minimatch": "11.0.8"},
    }
    old = lock(eslint="10.15.0", minimatch="11.0.8")
    root = project(
        tmp_path,
        {
            "package.json": dumped({"name": "project"}),
            "package-lock.json": dumped(lock()),
            "scripts/eslint/package.json": dumped(manifest),
            "scripts/eslint/package-lock.json": dumped(old),
        },
    )
    npm = FakeNpm(old)
    asked = []

    def npm_in(path: str) -> FakeNpm:
        asked.append(path)
        return npm

    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(npm_overrides, "npm_in", npm_in)

    assert main(["npm-overrides", "--fix"], root=root) == 0

    assert asked == ["/usr/bin/npm"]
    assert npm.folders == [root / "scripts/eslint"]
    assert "overrides" not in json.loads(
        (root / "scripts/eslint/package.json").read_text(encoding="utf-8")
    )
    assert capsys.readouterr().out == (
        "scripts/eslint/package.json: removed the override of minimatch 11.0.8: "
        "without it npm takes minimatch 11.0.8.\n"
        'scripts/eslint/package.json: the note "//" beside overrides may speak of '
        "it and stays as it is; remove it if it does.\n"
    )


@needs_git
def test_the_command_without_fix_names_what_npm_no_longer_needs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = {"overrides": {"minimatch": "11.0.8", "ajv": "6.14.0"}}
    old = lock(minimatch="11.0.8", ajv="6.14.0")
    root = project(
        tmp_path,
        {"package.json": dumped(manifest), "package-lock.json": dumped(old)},
    )
    before = contents(root, "package.json", "package-lock.json")
    npm = FakeNpm(old, lock(minimatch="11.0.8", ajv="6.12.6"))
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(npm_overrides, "npm_in", lambda path: npm)

    assert main(["npm-overrides"], root=root) == 1

    assert contents(root, "package.json", "package-lock.json") == before
    assert capsys.readouterr().out == (
        "package.json: npm no longer needs the override of minimatch 11.0.8: without "
        "it npm takes minimatch 11.0.8.\n"
        "package.json: kept the override of ajv 6.14.0: without it npm takes ajv "
        "6.12.6 at node_modules/ajv, below 6.14.0.\n"
        "python3 blueprint.py npm-overrides --fix removes each override that npm no "
        "longer needs, as Renovate does after an update of npm.\n"
    )


@needs_git
def test_the_command_passes_when_npm_needs_every_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = lock(minimatch="11.0.5")
    root = project(
        tmp_path, {"package.json": HOMEDARTS, "package-lock.json": dumped(old)}
    )
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        npm_overrides, "npm_in", lambda path: FakeNpm(lock(minimatch="10.2.6"))
    )

    assert main(["npm-overrides"], root=root) == 0


@needs_git
def test_the_command_needs_npm_only_for_an_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = project(
        tmp_path,
        {"package.json": dumped({"name": "x"}), "package-lock.json": dumped(lock())},
    )
    monkeypatch.setattr(shutil, "which", lambda name: None)

    assert main(["npm-overrides", "--fix"], root=root) == 0
    assert capsys.readouterr().out == (
        "No package.json here has overrides and a package-lock.json beside it.\n"
    )

    (root / "package.json").write_text(HOMEDARTS, encoding="utf-8")
    assert main(["npm-overrides", "--fix"], root=root) == 1
    assert "npm is not installed here" in capsys.readouterr().out


@needs_git
def test_the_command_says_what_it_cant_write_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The broken package.json is left alone; the next one still loses its override.
    root = project(
        tmp_path,
        {
            "a/package.json": '{"overrides": {}, "overrides": {"a": "1"}}',
            "a/package-lock.json": dumped(lock()),
            "b/package.json": HOMEDARTS,
            "b/package-lock.json": dumped(lock(eslint="10.15.0", minimatch="11.0.8")),
        },
    )
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        npm_overrides,
        "npm_in",
        lambda npm: FakeNpm(lock(eslint="10.15.0", minimatch="11.0.8")),
    )

    assert main(["npm-overrides", "--fix"], root=root) == 0
    captured = capsys.readouterr()
    assert captured.err.startswith(
        "a/package.json: left alone: a/package.json isn't JSON that it can write back"
    )
    assert "b/package.json: removed the override of minimatch 11.0.8" in captured.out
    assert (root / "b/package.json").read_text(encoding="utf-8") == WITHOUT_THE_OVERRIDE


def test_npm_writes_only_the_lock_file_and_runs_no_script(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []

    def run(command: list[str], **options: Any) -> subprocess.CompletedProcess[str]:
        calls.append((command, options["cwd"], options["check"]))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", run)

    npm_in("/usr/bin/npm")(tmp_path)

    assert calls == [
        (
            [
                "/usr/bin/npm",
                "install",
                "--package-lock-only",
                "--ignore-scripts",
                "--no-audit",
                "--no-fund",
            ],
            tmp_path,
            False,
        )
    ]
    assert {"--package-lock-only", "--ignore-scripts"} <= set(INSTALL)


# ------------------------------------------------------------------ the pieces


@pytest.mark.parametrize(
    ("spec", "floor"),
    [
        ("11.0.8", (11, 0, 8, 1, ())),
        ("^11.0.3", (11, 0, 3, 1, ())),
        ("~1.2", (1, 2, 0, 1, ())),
        ("1.x", (1, 0, 0, 1, ())),
        ("*", (0, 0, 0, 1, ())),
        ("", ZERO),
        ("<2", None),
        (">=1.2.3 <=2", None),
        ("1.2.3 - 2.0.0", None),
        ("^2 || <1", None),
        (">=1.2.3", (1, 2, 3, 1, ())),
        ("^2.1 || ^1", (1, 0, 0, 1, ())),
        ("v3.0.0-rc.1", (3, 0, 0, 0, ((1, "rc"), (0, 1)))),
        ("latest", None),
        ("$minimatch", None),
        ("npm:other@1", None),
        ("github:isaacs/minimatch", None),
    ],
)
def test_the_floor_of_an_override_is_the_lowest_version_it_allows(
    spec: str, floor: tuple[Any, ...] | None
) -> None:
    assert floor_of(spec) == floor


@pytest.mark.parametrize(
    ("spec", "capped"),
    [
        ("<2", True),
        ("<=1.4.0", True),
        (">=1.2.3 <2", True),
        ("1.2.3 - 1.4.0", True),
        ("^11.0.3 || <1", True),
        ("^11.0.3", False),
        (">=1.2.3", False),
        ("$minimatch", False),
    ],
)
def test_an_override_with_a_ceiling_caps_its_package(spec: str, capped: bool) -> None:
    assert caps(spec) is capped


def known(text: str) -> Version:
    version = version_of(text)
    assert version is not None
    return version


def test_a_prerelease_comes_before_its_release() -> None:
    assert known("1.0.0-rc.1") < known("1.0.0-rc.2") < known("1.0.0")
    assert known("1.0.0-alpha.beta") > known("1.0.0-alpha.1")
    assert version_of("^1.0.0") is None
    assert version_of("git+https://github.com/isaacs/minimatch.git") is None


def test_a_key_of_overrides_names_its_package_without_its_range() -> None:
    assert package_name("minimatch") == "minimatch"
    assert package_name("minimatch@^3") == "minimatch"
    assert package_name("@eslint/config-array") == "@eslint/config-array"
    assert package_name("@eslint/config-array@0.23") == "@eslint/config-array"
    nested = Override(("a", "b@1", "."), "b", "2.0.0")
    assert nested.label() == "b 2.0.0 below a"
    assert overrides_of({"a": {"b": 1, "c": "2"}}) == [Override(("a", "c"), "c", "2")]


def test_the_package_json_without_an_override_keeps_the_rest_and_its_form() -> None:
    manifest = {"name": "x", "overrides": {"a": {"b": "1", "c": "2"}, "d": "3"}}
    assert without(manifest, Override(("a", "b"), "b", "1")) == {
        "name": "x",
        "overrides": {"a": {"c": "2"}, "d": "3"},
    }
    assert without(manifest, Override(("d",), "d", "3"))["overrides"] == {
        "a": {"b": "1", "c": "2"}
    }
    assert manifest["overrides"] == {"a": {"b": "1", "c": "2"}, "d": "3"}
    assert written({"a": ["ü"]}, '{\r\n\t"a": []\r\n}\r\n') == (
        '{\r\n\t"a": [\r\n\t\t"ü"\r\n\t]\r\n}\r\n'
    )
    assert written({"a": 1}, '{"a": 1, "b": 2}') == '{\n  "a": 1\n}'


def test_a_copy_without_a_version_that_compares_counts_as_below() -> None:
    override = Override(("minimatch",), "minimatch", "11.0.8")
    floor = floor_of("11.0.8")
    assert floor is not None
    old = lock(minimatch="11.0.8")
    new = lock(minimatch="11.0.8")
    new["packages"]["node_modules/alias"] = {
        "name": "minimatch",
        "version": "github:isaacs/minimatch",
    }
    new["packages"]["node_modules/linked"] = {"link": True, "resolved": "packages/x"}
    assert judge(old, new, override, floor) == (
        False,
        "without it npm takes minimatch github:isaacs/minimatch at node_modules/alias, "
        "below 11.0.8",
    )
    assert judge(lock(), lock(), override, floor) == (
        True,
        "without it npm takes no minimatch",
    )
