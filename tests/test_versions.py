"""Tests of the fix of the step Version: the version of the manifest of the release
bot, written back into each file of the release bot where a hand changed it, and
nothing else of the file."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from blueprint import cli, versions
from blueprint.versions import Versioned


def write(root: Path, name: str, text: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path


def released(root: Path, release_type: str = "simple", extras: object = None) -> Path:
    """A repository whose release bot has the version 1.2.3, this type and these
    extra-files."""
    write(root, versions.MANIFEST, json.dumps({".": "1.2.3"}))
    package: dict[str, object] = {"release-type": release_type}
    if extras is not None:
        package["extra-files"] = extras
    write(root, versions.CONFIG, json.dumps({"packages": {".": package}}, indent=2))
    return root


def test_the_files_of_the_release_bot(tmp_path: Path) -> None:
    released(
        tmp_path,
        release_type="node",
        extras=[
            {"type": "json", "path": "custom_components/demo/manifest.json"},
            {"type": "xml", "path": "appinfo/info.xml", "xpath": "//version"},
            # The same file for another updater, a plain path, and files whose
            # version the step Version doesn't read.
            {"type": "generic", "path": "appinfo/info.xml"},
            "Dockerfile",
            {"type": "generic", "path": "README.md"},
            {"type": "generic"},
            3,
        ],
    )

    assert versions.files(tmp_path) == [
        "package.json",
        "package-lock.json",
        "custom_components/demo/manifest.json",
        "appinfo/info.xml",
        "Dockerfile",
    ]


@pytest.mark.parametrize(
    ("release_type", "expected"),
    [
        ("simple", ["version.txt"]),
        ("python", ["pyproject.toml"]),
        # A type that the template never sets writes no file that the step reads.
        ("go", []),
    ],
)
@pytest.mark.parametrize("extras", [None, "Dockerfile"])
def test_the_files_of_each_release_type(
    tmp_path: Path, release_type: str, expected: list[str], extras: str | None
) -> None:
    # Extra files that are no list are none.
    released(tmp_path, release_type, extras)

    assert versions.files(tmp_path) == expected


@pytest.mark.parametrize(
    "config",
    [None, "[]", "{}", '{"packages": []}', '{"packages": {".": "simple"}}'],
)
def test_a_repository_without_a_package_of_the_release_bot_has_no_files(
    tmp_path: Path, config: str | None
) -> None:
    if config is not None:
        write(tmp_path, versions.CONFIG, config)

    assert versions.files(tmp_path) == []


@pytest.mark.parametrize(
    ("manifest", "expected"),
    [
        (None, None),
        ('{".": "2.0.0-rc.1"}', "2.0.0-rc.1"),
        ('{".": 2}', None),
        ("{}", None),
        ('["1.0.0"]', None),
    ],
)
def test_the_version_of_the_last_release(
    tmp_path: Path, manifest: str | None, expected: str | None
) -> None:
    if manifest is not None:
        write(tmp_path, versions.MANIFEST, manifest)

    assert versions.release(tmp_path) == expected


@pytest.mark.parametrize(
    ("name", "text", "found"),
    [
        ("version.txt", "1.0.0\n", "1.0.0"),
        ("pyproject.toml", '[project]\nname = "x"\nversion = "1.0.0"\n', "1.0.0"),
        (
            "package.json",
            '{\n  "name": "x",\n  "version": "1.0.0-beta.2"\n}\n',
            "1.0.0-beta.2",
        ),
        ("manifest.json", '{"domain": "x", "version": "1.0.0"}', "1.0.0"),
        ("info.xml", "<info>\n  <version>1.0.0</version>\n</info>\n", "1.0.0"),
        (
            "Dockerfile",
            'FROM x\nLABEL org.opencontainers.image.version="1.0.0"\n',
            "1.0.0",
        ),
        # The first place only, as grep -m 1 reads it: the version of a dependency
        # further down is none of the release bot's.
        ("package-lock.json", '"version": "1.0.0",\n"version": "7.7.7"', "1.0.0"),
    ],
)
def test_the_version_where_the_step_reads_it(
    tmp_path: Path, name: str, text: str, found: str
) -> None:
    write(tmp_path, name, text)

    read = versions.read(tmp_path, name)

    assert read.found == found
    assert text[read.start : read.end] == found


@pytest.mark.parametrize(
    "text",
    [
        None,
        "",
        'version = "dev"\n',
        # A version that the step finds only on a line of its own.
        'version = "\n1.0.0"\n',
        "[project]\n  version = '1.0.0'\n",
    ],
)
def test_a_file_without_a_version_at_the_place_of_the_step(
    tmp_path: Path, text: str | None
) -> None:
    if text is not None:
        write(tmp_path, "pyproject.toml", text)

    assert versions.read(tmp_path, "pyproject.toml") == Versioned(
        "pyproject.toml", None
    )


def test_the_fix_writes_the_version_back_and_nothing_else(tmp_path: Path) -> None:
    released(
        tmp_path,
        release_type="node",
        extras=["appinfo/info.xml", "Dockerfile", "version.txt"],
    )
    # CRLF line endings, letters beyond ASCII and other versions stay as they are.
    manifest = (
        '{\r\n  "description": "Ümlauts",\r\n  "version": "1.2.4",\r\n'
        '  "devDependencies": {"x": "1.2.4"}\r\n}\r\n'
    )
    write(tmp_path, "package.json", manifest)
    write(tmp_path, "package-lock.json", '{"version": "1.2.3"}\n')
    write(tmp_path, "appinfo/info.xml", "<version>0.9.0-rc.1</version>\n")
    write(tmp_path, "Dockerfile", "FROM x\n")

    done = versions.fix(tmp_path)

    assert done == versions.Fixed(
        "1.2.3",
        [
            Versioned(
                "package.json",
                "1.2.4",
                manifest.index("1.2.4"),
                manifest.index("1.2.4") + len("1.2.4"),
            ),
            Versioned("appinfo/info.xml", "0.9.0-rc.1", 9, 19),
        ],
        [Versioned("Dockerfile", None), Versioned("version.txt", None)],
    )
    assert (tmp_path / "package.json").read_bytes() == (
        manifest.replace("1.2.4", "1.2.3", 1).encode()
    )
    assert (tmp_path / "package-lock.json").read_text(encoding="utf-8") == (
        '{"version": "1.2.3"}\n'
    )
    assert (tmp_path / "appinfo/info.xml").read_text(encoding="utf-8") == (
        "<version>1.2.3</version>\n"
    )
    # Once fixed, only the files without a version are left.
    again = versions.fix(tmp_path)
    assert (again.fixed, again.left) == ([], done.left)


def test_without_a_manifest_the_fix_writes_nothing(tmp_path: Path) -> None:
    write(tmp_path, versions.CONFIG, '{"packages": {".": {"release-type": "simple"}}}')
    write(tmp_path, "version.txt", "1.0.0\n")

    assert versions.fix(tmp_path) == versions.Fixed(None, [], [])
    assert (tmp_path / "version.txt").read_text(encoding="utf-8") == "1.0.0\n"


# ---------------------------------------------------------------- the command line


def test_fix_version_from_the_command_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    released(tmp_path, extras=["Dockerfile"])
    write(tmp_path, "version.txt", "1.2.4\n")
    write(tmp_path, "Dockerfile", 'LABEL org.opencontainers.image.version="1.2.3"\n')

    assert cli.main(["fix", "version"], root=tmp_path) == 0
    assert capsys.readouterr().out == (
        "version.txt: version 1.2.3 of the release bot, in place of 1.2.4\n"
        "1 file(s) have the version of the release bot again.\n"
    )
    assert cli.main(["fix", "version"], root=tmp_path) == 0
    assert capsys.readouterr().out == (
        "Every file has the version of the release bot, 1.2.3.\n"
    )


def test_fix_version_leaves_a_file_without_a_version_to_a_person(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    released(tmp_path, extras=["Dockerfile"])
    write(tmp_path, "version.txt", "1.2.4\n")
    write(tmp_path, "Dockerfile", "FROM x\n")

    assert cli.main(["fix", "version"], root=tmp_path) == 1
    assert capsys.readouterr().out == (
        "version.txt: version 1.2.3 of the release bot, in place of 1.2.4\n"
        "Dockerfile: has no version where the step Version reads it; give it "
        "version 1.2.3\n"
        "1 file(s) have the version of the release bot again.\n"
    )
    assert cli.main(["fix", "version"], root=tmp_path) == 1
    assert capsys.readouterr().out == (
        "Dockerfile: has no version where the step Version reads it; give it "
        "version 1.2.3\n"
    )


def test_fix_version_without_a_manifest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["fix", "version"], root=tmp_path) == 0
    assert capsys.readouterr().out == (
        ".release-please-manifest.json names no version, so there is none to write.\n"
    )


@pytest.mark.parametrize(
    ("name", "data"),
    [(versions.MANIFEST, b"{"), (versions.CONFIG, b"["), ("version.txt", b"\xff\n")],
)
def test_fix_version_of_a_broken_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str, data: bytes
) -> None:
    released(tmp_path)
    write(tmp_path, "version.txt", "1.2.3\n")
    (tmp_path / name).write_bytes(data)

    assert cli.main(["fix", "version"], root=tmp_path) == 2
    assert capsys.readouterr().err.startswith("blueprint.py: ")
