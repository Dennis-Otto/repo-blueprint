"""Tests of pins.py, which writes the sha256 of each tool that Renovate moved to a new
release, against repositories of a few files and a download that stays offline."""

from __future__ import annotations

import hashlib
import io
import re
import urllib.error
from email.message import Message
from pathlib import Path
from typing import Any

import pytest

import pins

ROOT = Path(__file__).parents[1]
OLD = "a" * 64
NEW = hashlib.sha256(b"tool 1.1.0").hexdigest()
WORKFLOW = f"""\
jobs:
  build:
    env:
      # renovate: datasource=github-releases depName=owner/tool extractVersion=^v(?<version>.+)$
      TOOL_VERSION: 1.1.0
      TOOL_SHA256: {OLD}
      # renovate: datasource=pypi depName=uv
      UV_VERSION: 0.12.18
"""
SCRIPT = f"""\
#!/usr/bin/env bash
# renovate: datasource=github-releases depName=owner/tool extractVersion=^v(?<version>.+)$
version=1.1.0
sha256="{OLD}"
"""
RECORD = f"""\
[download."owner/tool"]
url = "https://example.org/tool/v{{version}}/tool_{{version}}_linux"
version = "1.0.0"
sha256 = "{OLD}"
"""


def repository(
    root: Path, record: str = RECORD, workflow: str = WORKFLOW, script: str = SCRIPT
) -> Path:
    (root / ".github/workflows").mkdir(parents=True)
    (root / ".github/pins.toml").write_bytes(record.encode())
    (root / ".github/workflows/build.yml").write_bytes(workflow.encode())
    (root / ".github/sign.sh").write_bytes(script.encode())
    return root


class Fetches:
    """A download that remembers its addresses: the sha256 of the text "tool X.Y.Z"."""

    def __init__(self) -> None:
        self.urls: list[str] = []

    def __call__(self, url: str) -> str:
        self.urls.append(url)
        version = re.search(r"tool_([\d.]+)_linux", url)
        assert version
        return hashlib.sha256(f"tool {version[1]}".encode()).hexdigest()


# --------------------------------------------------------------- the blueprint itself


def test_every_download_of_the_blueprint_has_the_sha256_of_its_version() -> None:
    assert pins.check(ROOT) == []
    record = pins.load_record(ROOT)
    # pins.py keeps the file, so it is in the form that pins.py writes.
    text = (ROOT / pins.RECORD).read_bytes().decode("utf-8")
    assert text == pins.render_record(record)
    found = pins.find_pins(ROOT)
    assert (
        {pin.dep for pin in found}
        == set(record)
        == {
            "sigstore/gitsign",
            "infection/infection",
            "ChristophWurst/krankerl",
            "nextcloud/server",
            "anchore/syft",
        }
    )
    # gitsign in sign-tag.sh and in verify-release.yml, krankerl in the release and in
    # the checks of a Nextcloud app, and syft for the SBOMs of the release.
    assert sorted((pin.dep, pin.path) for pin in found) == [
        ("ChristophWurst/krankerl", ".github/workflows/build-release.yml"),
        ("ChristophWurst/krankerl", ".github/workflows/ci-php.yml"),
        ("anchore/syft", ".github/workflows/build-release.yml"),
        ("infection/infection", ".github/workflows/mutation.yml"),
        ("nextcloud/server", ".github/workflows/build-release.yml"),
        ("sigstore/gitsign", ".github/sign-tag.sh"),
        ("sigstore/gitsign", ".github/workflows/verify-release.yml"),
    ]


def test_every_file_downloads_a_tool_from_the_address_of_the_record() -> None:
    # pins.py downloads from the address of .github/pins.toml, so the workflows and
    # scripts must download from the same one, with their variable for {version}.
    record = pins.load_record(ROOT)
    for pin in pins.find_pins(ROOT):
        text = (ROOT / pin.path).read_text(encoding="utf-8")
        plain = re.sub(r"\$\{(\w+)\}", r"$\1", text)
        url = record[pin.dep].url.replace("{version}", f"${pin.name}")
        assert f'"{url}"' in plain, (pin.path, url)


# ----------------------------------------------------------------- writing the sha256


def test_a_version_that_renovate_moved_gets_the_sha256_of_its_release(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repository(tmp_path)
    fetch = Fetches()

    assert pins.main([], root=root, fetch=fetch) == 0

    # One download per version, for every file that pins it.
    assert fetch.urls == ["https://example.org/tool/v1.1.0/tool_1.1.0_linux"]
    assert (root / ".github/workflows/build.yml").read_text() == WORKFLOW.replace(
        OLD, NEW
    )
    assert (root / ".github/sign.sh").read_text() == SCRIPT.replace(OLD, NEW)
    assert pins.load_record(root) == {
        "owner/tool": pins.Download(
            "https://example.org/tool/v{version}/tool_{version}_linux", "1.1.0", NEW
        )
    }
    assert capsys.readouterr().out == (
        f"owner/tool 1.1.0: sha256 {NEW}\n"
        ".github/sign.sh: the sha256 of owner/tool 1.1.0\n"
        ".github/workflows/build.yml: the sha256 of owner/tool 1.1.0\n"
        ".github/pins.toml: 1 downloads\n"
    )
    assert pins.check(root) == []

    # The next run has nothing to do.
    assert pins.main([], root=root, fetch=fetch) == 0
    assert len(fetch.urls) == 1
    assert capsys.readouterr().out == (
        "Every pinned download has the sha256 of its version.\n"
    )


def test_a_file_whose_sha256_was_changed_by_hand_gets_that_of_the_record(
    tmp_path: Path,
) -> None:
    record = RECORD.replace('"1.0.0"', '"1.1.0"').replace(OLD, NEW)
    root = repository(tmp_path, record=record)
    fetch = Fetches()

    assert pins.check(root) == [
        f".github/sign.sh: the sha256 of owner/tool 1.1.0 differs from {pins.RECORD}; "
        "python3 pins.py writes the right one",
        ".github/workflows/build.yml: the sha256 of owner/tool 1.1.0 differs from "
        f"{pins.RECORD}; python3 pins.py writes the right one",
    ]
    assert pins.update(root, fetch) == [
        ".github/sign.sh: the sha256 of owner/tool 1.1.0",
        ".github/workflows/build.yml: the sha256 of owner/tool 1.1.0",
        f"{pins.RECORD}: 1 downloads",
    ]
    # Without a download: the record holds the sha256 of the version.
    assert fetch.urls == []
    assert pins.check(root) == []


def test_two_pins_in_one_file_keep_their_places(tmp_path: Path) -> None:
    workflow = WORKFLOW + (
        "  other:\n"
        "    env:\n"
        "      # renovate: datasource=github-releases depName=owner/tool\n"
        "      OTHER_VERSION: 1.1.0\n"
        f"      OTHER_SHA256: {OLD}\n"
    )
    root = repository(tmp_path, workflow=workflow)

    pins.update(root, Fetches())

    assert (root / ".github/workflows/build.yml").read_text() == workflow.replace(
        OLD, NEW
    )


# --------------------------------------------------------- what keeps it from writing


@pytest.mark.parametrize(
    ("record", "workflow", "problem"),
    [
        (
            RECORD.replace("owner/tool", "owner/gone"),
            WORKFLOW,
            f"{pins.RECORD}: no file pins owner/gone; remove it",
        ),
        (
            RECORD.replace("owner/tool", "owner/gone"),
            WORKFLOW,
            f"{pins.RECORD} has no download owner/tool: add its url, version and sha256",
        ),
        (
            RECORD,
            WORKFLOW.replace("TOOL_VERSION: 1.1.0", "TOOL_VERSION: 1.2.0"),
            "The files pin owner/tool at 1.1.0 and 1.2.0: give each the same version",
        ),
    ],
)
def test_a_download_that_the_record_and_the_files_disagree_on_stops_it(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    record: str,
    workflow: str,
    problem: str,
) -> None:
    root = repository(tmp_path, record=record, workflow=workflow)
    fetch = Fetches()

    assert problem in pins.check(root)
    assert pins.main([], root=root, fetch=fetch) == 2
    assert f"pins.py: {problem}\n" in capsys.readouterr().err
    # Nothing downloaded, nothing written.
    assert fetch.urls == []
    assert (root / ".github/pins.toml").read_text() == record


def test_check_names_each_version_that_renovate_moved(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repository(tmp_path)

    assert pins.main(["--check"], root=root) == 1

    assert capsys.readouterr().err == (
        "pins.py: .github/sign.sh: owner/tool 1.1.0 has the sha256 of 1.0.0; "
        "python3 pins.py writes the right one\n"
        "pins.py: .github/workflows/build.yml: owner/tool 1.1.0 has the sha256 of "
        "1.0.0; python3 pins.py writes the right one\n"
    )


def test_check_passes_when_every_pin_has_the_sha256_of_its_version(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    record = RECORD.replace('"1.0.0"', '"1.1.0"')
    root = repository(tmp_path, record=record)

    assert pins.main(["--check"], root=root) == 0

    assert capsys.readouterr().out == (
        f"Every pinned download has the sha256 of its version in {pins.RECORD}.\n"
    )


@pytest.mark.parametrize(
    "record",
    [
        "[other]\nkey = 1\n",
        'download = "owner/tool"\n',
        '[download]\n"owner/tool" = "https://example.org"\n',
        RECORD.replace("https://", "http://"),
        RECORD.replace("v{version}", "latest").replace("_{version}", ""),
        RECORD.replace(f'"{OLD}"', '"abc"'),
        RECORD.replace('version = "1.0.0"', "version = 1"),
        RECORD + 'note = "more"\n',
        RECORD.replace(f'sha256 = "{OLD}"\n', ""),
    ],
)
def test_a_record_that_pins_py_cannot_read_stops_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], record: str
) -> None:
    root = repository(tmp_path, record=record)

    assert pins.main([], root=root, fetch=Fetches()) == 2

    assert capsys.readouterr().err.startswith(f"pins.py: {pins.RECORD}")


@pytest.mark.parametrize("record", [None, "[download\n", b"\xff"])
def test_a_record_that_is_missing_or_broken_stops_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], record: str | bytes | None
) -> None:
    root = repository(tmp_path)
    if record is None:
        (root / pins.RECORD).unlink()
    else:
        data = record if isinstance(record, bytes) else record.encode()
        (root / pins.RECORD).write_bytes(data)

    assert pins.main(["--check"], root=root) == 2

    assert capsys.readouterr().err.startswith("pins.py: ")


# ------------------------------------------------------------------------ the download


class Response(io.BytesIO):
    def __enter__(self) -> Response:
        return self

    def __exit__(self, *details: object) -> None:
        self.close()


def test_the_download_hashes_what_it_reads(tmp_path: Path) -> None:
    data = b"x" * (3 << 20)
    asked: list[tuple[Any, float]] = []

    def opener(request: Any, timeout: float) -> Response:
        asked.append((request, timeout))
        return Response(data)

    assert pins.download("https://example.org/tool", opener) == (
        hashlib.sha256(data).hexdigest()
    )
    request, timeout = asked[0]
    assert request.full_url == "https://example.org/tool"
    assert request.get_header("User-agent") == pins.AGENT
    assert timeout == 300
    # The real one, from a file.
    (tmp_path / "tool").write_bytes(data)
    assert pins.download((tmp_path / "tool").as_uri()) == (
        hashlib.sha256(data).hexdigest()
    )


def test_the_download_tries_three_times(tmp_path: Path) -> None:
    waits: list[float] = []
    answers: list[Exception | bytes] = [
        urllib.error.URLError("no route"),
        TimeoutError("timed out"),
        b"tool",
    ]

    def opener(request: Any, timeout: float) -> Response:
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return Response(answer)

    assert pins.download("https://example.org/tool", opener, waits.append) == (
        hashlib.sha256(b"tool").hexdigest()
    )
    assert waits == [10, 20]

    errors: list[urllib.error.HTTPError] = []

    def broken(request: Any, timeout: float) -> Response:
        # An error as urlopen raises it: the answer of the server too, with its body.
        errors.append(
            urllib.error.HTTPError(
                request.full_url, 404, "Not Found", Message(), io.BytesIO(b"gone")
            )
        )
        raise errors[-1]

    waits.clear()
    with pytest.raises(pins.PinError) as raised:
        pins.download("https://example.org/tool", broken, waits.append)
    assert raised.value.problems == [
        "https://example.org/tool could not be downloaded: HTTP Error 404: Not Found"
    ]
    assert waits == [10, 20]
    # Each answer is closed, as the newest Python warns of one left open.
    assert len(errors) == 3
    assert all(error.closed for error in errors)


def test_a_download_that_fails_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repository(tmp_path)

    def fetch(url: str) -> str:
        raise pins.PinError([f"{url} could not be downloaded: no route"])

    assert pins.main([], root=root, fetch=fetch) == 2

    assert capsys.readouterr().err == (
        "pins.py: https://example.org/tool/v1.1.0/tool_1.1.0_linux could not be "
        "downloaded: no route\n"
    )
    assert (root / ".github/sign.sh").read_text() == SCRIPT
    assert (root / ".github/pins.toml").read_text() == RECORD
