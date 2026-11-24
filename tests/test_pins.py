"""Tests of pins.py, which writes the sha256 of each tool that Renovate moved to a new
release, against repositories of a few files and a download that stays offline."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import re
import subprocess
import urllib.error
from email.message import Message
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from shared import git_environment

import pins

ROOT_HOOKS = Path(__file__).parents[1] / ".github/mkdocs_blueprint.py"


def hooks() -> ModuleType:
    """The hooks of the websites, which download the Mermaid that they pin."""
    spec = importlib.util.spec_from_file_location("mkdocs_blueprint", ROOT_HOOKS)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
        version = re.search(r"tool_([\d.]+)(?:-1)?_linux", url)
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
            "lycheeverse/lychee",
            "gitleaks/gitleaks",
            "mermaid",
        }
    )
    # gitsign in sign-tag.sh and in verify-release.yml, krankerl in the release and in
    # the checks of a Nextcloud app, syft for the SBOMs of the release and the weekly
    # one of the repository, lychee in the script that checks the links of the
    # documents and of the website, gitleaks in the one of the secret scan, and
    # Mermaid in the pins of the websites.
    assert sorted((pin.dep, pin.path) for pin in found) == [
        ("ChristophWurst/krankerl", ".github/workflows/build-release.yml"),
        ("ChristophWurst/krankerl", ".github/workflows/ci-php.yml"),
        ("anchore/syft", ".github/workflows/build-release.yml"),
        ("anchore/syft", ".github/workflows/sbom.yml"),
        ("gitleaks/gitleaks", ".github/gitleaks.sh"),
        ("infection/infection", ".github/workflows/mutation.yml"),
        ("lycheeverse/lychee", ".github/lychee.sh"),
        ("mermaid", ".github/mkdocs-blueprint-pins.toml"),
        ("nextcloud/server", ".github/workflows/build-release.yml"),
        ("sigstore/gitsign", ".github/sign-tag.sh"),
        ("sigstore/gitsign", ".github/workflows/verify-release.yml"),
    ]


def test_every_file_downloads_a_tool_from_the_address_of_the_record() -> None:
    # pins.py downloads from the address of .github/pins.toml, so the workflows and
    # scripts must download the same file, with their variable for {version}: an
    # asset of a release on GitHub through the API, which survives an outage of
    # GitHub's downloads without a token (decision 0133), by its repository, tag and
    # name, with .github/download.sh or gh, and any other file from its address.
    record = pins.load_record(ROOT)
    for pin in pins.find_pins(ROOT):
        if pin.path == ".github/mkdocs-blueprint-pins.toml":
            # The hooks of the websites download it from the address of its version.
            url = record[pin.dep].url.replace("{version}", pin.version)
            assert url == hooks().MERMAID
            continue
        text = (ROOT / pin.path).read_text(encoding="utf-8")
        commands = plain(text)
        url = record[pin.dep].url.replace("{version}", f"${pin.name}")
        # An asset of a release on GitHub, which gh downloads by its parts.
        asset = pins.RELEASE_ASSET.fullmatch(url)
        if not asset:
            assert f'"{url}"' in commands, (pin.path, url)
            continue
        page = f"github.com/{asset['repository']}/releases/download/"
        assert page not in commands, (pin.path, page)
        repository, tag, name = (re.escape(asset[part]) for part in asset.groupdict())
        if pin.asset is not None:
            # A pin that names its file: the file downloads that name, which pins.py
            # writes from the address, and never builds it from the version.
            variable = asset_variable(pin)
            assert re.search(
                rf"^[ \t]*{variable[1:]}(?:: | ?= ?)\"?{re.escape(pin.asset)}\b",
                text,
                re.MULTILINE,
            ), (pin.path, variable)
            assert asset["asset"] not in commands, (pin.path, asset["asset"])
            name = re.escape(variable)
        calls = (
            rf'download\.sh"? {repository} "{tag}" "?{name}"? ',
            rf'gh release download "{tag}" --repo {repository} --pattern "?{name}"? ',
        )
        assert any(re.search(call, commands) for call in calls), (pin.path, url)


def plain(text: str) -> str:
    """The commands of a file, a command a line, with $NAME for ${NAME}."""
    commands = re.sub(r"\$\{(\w+)\}", r"$\1", text.replace("\\\n", " "))
    return re.sub(r" {2,}", " ", commands)


def asset_variable(pin: pins.Pin) -> str:
    """The variable that holds the name of the file that a pin names, KRANKERL_ASSET
    beside KRANKERL_VERSION."""
    return "$" + pin.name.replace("VERSION", "ASSET").replace("version", "asset")


# The files of the blueprint and of its template that may download a tool.
SOURCES = (
    ".github/*.sh",
    ".github/workflows/*.yml",
    "scripts/**/*.sh",
    "template/**/*.jinja",
    "template/**/*.sh",
    "template/**/*.yml",
)
# A download of an asset of a release on GitHub, by .github/download.sh or by gh.
CALLS = (
    r'download\.sh"? (?P<repository>[\w.-]+/[\w.-]+) "?\S+?"? "?(?P<asset>[^\s"]+)"? ',
    r'gh release download "?\S+?"? --repo (?P<repository>[\w.-]+/[\w.-]+)'
    r' --pattern "?(?P<asset>[^\s"]+)"? ',
)


def built_names(root: Path) -> list[str]:
    """Each download of a pinned tool by a file that neither pins it nor takes the
    name of its file from a pin that names it: such a file builds the name from a
    version that it reads elsewhere, and misses the next new name of the release."""
    record = pins.load_record(root)
    found = pins.find_pins(root)
    pinned = {(pin.path, pin.dep) for pin in found}
    variables = {asset_variable(pin) for pin in found if pin.asset is not None}
    repositories = {
        address["repository"]: dep
        for dep, download in record.items()
        if (address := pins.RELEASE_ASSET.fullmatch(download.url))
    }
    built = []
    for pattern in SOURCES:
        for path in sorted(root.glob(pattern)):
            name = path.relative_to(root).as_posix()
            # Without the comments, such as the example of .github/download.sh.
            text = re.sub(
                r"^[ \t]*#.*\n", "", path.read_bytes().decode("utf-8"), flags=re.M
            )
            commands = plain(text)
            for call in (m for c in CALLS for m in re.finditer(c, commands)):
                dep = repositories.get(call["repository"])
                if dep is None or (name, dep) in pinned or call["asset"] in variables:
                    continue
                built.append(f"{name}: {call['repository']} {call['asset']}")
    return built


def test_no_file_builds_the_name_of_a_pinned_download_itself() -> None:
    # A file that downloads a pinned tool pins it too, and the test above holds it to
    # the address of the record, or takes the name from a pin that names the file:
    # the upgrade test of paperless-sync read KRANKERL_VERSION of its CI and built
    # krankerl_${KRANKERL_VERSION}_amd64.deb, a name that krankerl gave up in 0.14.1,
    # and failed on main after the update that moved the pin to 0.14.3 (#994).
    assert built_names(ROOT) == []


def test_a_file_that_builds_the_name_of_a_pinned_download_is_named(
    tmp_path: Path,
) -> None:
    record = RENAMED.replace("tool_{version}_linux", "tool_{version}-1_linux")
    workflow = WORKFLOW.replace(
        f"TOOL_SHA256: {OLD}",
        f"TOOL_SHA256: {OLD}\n      TOOL_ASSET: tool_1.1.0-1_linux",
    )
    root = repository(tmp_path, record=record, workflow=workflow)
    # Two files that read the pin of build.yml: one builds the name, as the upgrade
    # test did, and one takes it from the pin.
    (root / ".github/workflows/upgrade.yml").write_bytes(
        b"jobs:\n  upgrade:\n    steps:\n      - run: |\n"
        b'          bash .github/download.sh owner/tool "v$TOOL_VERSION" \\\n'
        b'            "tool_${TOOL_VERSION}_linux" "$RUNNER_TEMP/tool" "$TOOL_SHA256"\n'
    )
    (root / ".github/workflows/e2e.yml").write_bytes(
        b"jobs:\n  e2e:\n    steps:\n      - run: |\n"
        b'          bash .github/download.sh owner/tool "v$TOOL_VERSION" \\\n'
        b'            "$TOOL_ASSET" "$RUNNER_TEMP/tool" "$TOOL_SHA256"\n'
        # Another release, of a tool that nothing pins.
        b"          gh release download v1 --repo owner/other --pattern other_1 \n"
    )

    assert built_names(root) == [
        ".github/workflows/upgrade.yml: owner/tool tool_$TOOL_VERSION_linux"
    ]


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


def test_a_pin_in_toml_gets_the_sha256_of_its_release(tmp_path: Path) -> None:
    pinned = (
        "[tool]\n"
        "# renovate: datasource=npm depName=owner/tool\n"
        'version = "1.1.0"\n'
        f'sha256 = "{OLD}"\n'
    )
    root = repository(tmp_path)
    (root / ".github/mkdocs-blueprint-pins.toml").write_bytes(pinned.encode())

    pins.update(root, Fetches())

    text = (root / ".github/mkdocs-blueprint-pins.toml").read_bytes().decode()
    assert text == pinned.replace(OLD, NEW)
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


# ------------------------------------------------------- the name of the file of a pin

NAMED = RECORD.replace("tool_{version}_linux", "tool_{version}-1_linux")


def named(text: str, asset: str, *, shell: bool = False) -> str:
    """A pin of a workflow or a script that names its file as well."""
    if shell:
        return text.replace(f'sha256="{OLD}"\n', f'sha256="{OLD}"\nasset="{asset}"\n')
    return text.replace(
        f"TOOL_SHA256: {OLD}\n", f"TOOL_SHA256: {OLD}\n      TOOL_ASSET: {asset}\n"
    )


def test_a_pin_that_names_its_file_gets_the_name_of_its_new_version(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Renovate moves the version alone; pins.py writes the sha256 and the name of the
    # file, so that what downloads it takes the name of the new release from the pin.
    # A second pin in the same file, after a name of another length, keeps its place.
    workflow = named(WORKFLOW, "tool_1.0.0_linux") + (
        "  other:\n"
        "    env:\n"
        "      # renovate: datasource=github-releases depName=owner/tool\n"
        "      OTHER_VERSION: 1.1.0\n"
        f"      OTHER_SHA256: {OLD}\n"
        "      OTHER_ASSET: tool_1.1.0_linux\n"
        "      OTHER_NAME: other\n"
    )
    script = named(SCRIPT, "tool_1.0.0-1_linux", shell=True)
    root = repository(tmp_path, record=NAMED, workflow=workflow, script=script)
    assert pins.check(root) == [
        ".github/sign.sh: owner/tool 1.1.0 has the sha256 of 1.0.0; python3 pins.py "
        "writes the right one",
        ".github/sign.sh: owner/tool 1.1.0 is the file tool_1.1.0-1_linux by its "
        f"address in {pins.RECORD}, not tool_1.0.0-1_linux; python3 pins.py writes "
        "the right one",
        ".github/workflows/build.yml: owner/tool 1.1.0 has the sha256 of 1.0.0; python3 "
        "pins.py writes the right one",
        ".github/workflows/build.yml: owner/tool 1.1.0 is the file tool_1.1.0-1_linux "
        f"by its address in {pins.RECORD}, not tool_1.0.0_linux; python3 pins.py "
        "writes the right one",
        ".github/workflows/build.yml: owner/tool 1.1.0 has the sha256 of 1.0.0; python3 "
        "pins.py writes the right one",
        ".github/workflows/build.yml: owner/tool 1.1.0 is the file tool_1.1.0-1_linux "
        f"by its address in {pins.RECORD}, not tool_1.1.0_linux; python3 pins.py "
        "writes the right one",
    ]

    assert pins.main([], root=root, fetch=Fetches()) == 0

    assert (root / ".github/workflows/build.yml").read_text() == (
        workflow.replace(OLD, NEW)
        .replace("tool_1.0.0_linux", "tool_1.1.0-1_linux")
        .replace("tool_1.1.0_linux", "tool_1.1.0-1_linux")
    )
    assert (root / ".github/sign.sh").read_text() == script.replace(OLD, NEW).replace(
        "tool_1.0.0-1_linux", "tool_1.1.0-1_linux"
    )
    assert capsys.readouterr().out == (
        f"owner/tool 1.1.0: sha256 {NEW}\n"
        ".github/sign.sh: the sha256 of owner/tool 1.1.0\n"
        ".github/sign.sh: the file of owner/tool 1.1.0, tool_1.1.0-1_linux\n"
        ".github/workflows/build.yml: the sha256 of owner/tool 1.1.0\n"
        ".github/workflows/build.yml: the file of owner/tool 1.1.0, tool_1.1.0-1_linux\n"
        ".github/workflows/build.yml: the sha256 of owner/tool 1.1.0\n"
        ".github/workflows/build.yml: the file of owner/tool 1.1.0, tool_1.1.0-1_linux\n"
        ".github/pins.toml: 1 downloads\n"
    )
    assert pins.check(root) == []


def test_a_new_name_in_the_record_is_written_into_each_pin_that_names_the_file(
    tmp_path: Path,
) -> None:
    # A release that names its files anew, as krankerl 0.14.1 did: the address in the
    # record changes, and pins.py writes the new name into the pins without a download.
    record = NAMED.replace('"1.0.0"', '"1.1.0"').replace(OLD, NEW)
    workflow = named(WORKFLOW, "tool_1.1.0_linux").replace(OLD, NEW)
    root = repository(tmp_path, record=record, workflow=workflow)
    fetch = Fetches()

    assert pins.update(root, fetch) == [
        ".github/sign.sh: the sha256 of owner/tool 1.1.0",
        ".github/workflows/build.yml: the file of owner/tool 1.1.0, tool_1.1.0-1_linux",
        f"{pins.RECORD}: 1 downloads",
    ]
    assert fetch.urls == []
    assert (root / ".github/workflows/build.yml").read_text() == workflow.replace(
        "tool_1.1.0_linux", "tool_1.1.0-1_linux"
    )
    assert pins.check(root) == []


def test_only_a_name_that_ends_in_asset_names_the_file_of_a_pin(tmp_path: Path) -> None:
    workflow = WORKFLOW.replace(
        f"TOOL_SHA256: {OLD}\n", f"TOOL_SHA256: {OLD}\n      TOOL_ARCH: amd64\n"
    )
    root = repository(tmp_path, workflow=workflow)

    found = [pin for pin in pins.find_pins(root) if pin.path.endswith("build.yml")]

    assert [(pin.asset, pin.asset_start) for pin in found] == [(None, -1)]


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
        # The bundles of an action and its image left with decision 1111.
        RECORD + '\n[bundle."owner/lint-action"]\ncommit = "' + "1" * 40 + '"\n',
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


RENAMED = f"""\
[download."owner/tool"]
url = "https://github.com/owner/tool/releases/download/v{{version}}/tool_{{version}}_linux"
version = "1.0.0"
sha256 = "{OLD}"
"""


def test_an_asset_that_the_release_names_anew_is_named_by_the_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # krankerl 0.14.1 named its package krankerl_0.14.1-1_amd64.deb, and Renovate's
    # update stopped at a 404 that said nothing more; the error now names the assets
    # that the release has.
    root = repository(tmp_path, record=RENAMED)
    asset = "https://github.com/owner/tool/releases/download/v1.1.0/tool_1.1.0_linux"

    def fetch(url: str) -> str:
        raise pins.PinError([f"{url} could not be downloaded: HTTP Error 404"])

    read = Reads('{"assets": [{"name": "tool"}, {"name": "tool_1.1.0-1_linux"}]}')

    assert pins.main([], root=root, fetch=fetch, read=read) == 2

    assert read.urls == ["https://api.github.com/repos/owner/tool/releases/tags/v1.1.0"]
    assert capsys.readouterr().err == (
        f"pins.py: {asset} could not be downloaded: HTTP Error 404\n"
        "pins.py: The release v1.1.0 of owner/tool has no asset tool_1.1.0_linux, "
        "only tool, tool_1.1.0-1_linux: give the url of owner/tool in "
        ".github/pins.toml the new name, with {version} for the version; python3 "
        "pins.py then writes it into each pin that names the file\n"
    )
    assert (root / ".github/sign.sh").read_text() == SCRIPT
    assert (root / ".github/pins.toml").read_text() == RENAMED


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        # The asset is there: the error passed, and is all there is to say.
        ('{"assets": [{"name": "tool_1.1.0_linux"}]}', ""),
        # A release without assets.
        ('{"assets": []}', "has no asset tool_1.1.0_linux, only none:"),
        # An answer that is no release, or none at all.
        ('{"message": "Not Found"}', ""),
        ('{"assets": ["tool"]}', ""),
        ("not json", ""),
        (None, ""),
    ],
)
def test_the_assets_of_the_release_are_named_only_when_its_own_is_missing(
    answer: str | None, expected: str
) -> None:
    url = "https://github.com/owner/tool/releases/download/v1.1.0/tool_1.1.0_linux"

    def read(address: str) -> str:
        if answer is None:
            raise pins.PinError([f"{address} could not be downloaded: no route"])
        return answer

    found = pins.renamed("owner/tool", url, read)

    assert [expected in line for line in found] == ([True] if expected else [])


# ------------------------------------------------------------- the image of markdownlint

# An image of markdownlint-cli2 by its tag and digest, as Renovate's custom manager
# of the images finds it in the workflows and the scripts.
MARKDOWNLINT = re.compile(
    r"(?<![\w./-])davidanson/markdownlint-cli2:[^@\s\"']+@sha256:[0-9a-f]{64}"
)
MARKDOWNLINT_FILES = (".github/*.sh", ".github/workflows/*.yml", "scripts/*.sh")


def markdownlint_images(root: Path) -> dict[str, list[str]]:
    """Each tag and digest of the image of markdownlint-cli2 that a workflow or a
    script runs, with the files that run it."""
    images: dict[str, list[str]] = {}
    for pattern in MARKDOWNLINT_FILES:
        for path in sorted(root.glob(pattern)):
            for image in MARKDOWNLINT.findall(path.read_text(encoding="utf-8")):
                images.setdefault(image, []).append(path.relative_to(root).as_posix())
    return images


def test_the_markdownlint_of_the_check_lint_is_that_of_its_image() -> None:
    # The check lint, scripts/markdownlint.sh, which scripts/check.sh runs, and the
    # Variants workflow run one image of markdownlint-cli2, by one tag and digest,
    # which Renovate moves in all of them in one pull request (decision 1111).
    images = markdownlint_images(ROOT)
    assert list(images.values()) == [
        [
            ".github/workflows/lint.yml",
            ".github/workflows/variants.yml",
            "scripts/markdownlint.sh",
        ]
    ]
    # No workflow runs the action, whose markdownlint-cli2 moved apart from the image.
    for path in sorted(ROOT.glob(".github/workflows/*.yml")):
        assert "markdownlint-cli2-action" not in path.read_text(encoding="utf-8")


# The tag and the digest of an image of markdownlint-cli2.
MARKDOWNLINT_PARTS = re.compile(r":(?P<tag>[^@]+)@sha256:(?P<digest>[0-9a-f]{64})$")
MARKDOWNLINT_SCRIPTS = (
    ".github/workflows/lint.yml",
    ".github/workflows/variants.yml",
    "scripts/markdownlint.sh",
)


def another_image(image: str, part: str) -> str:
    """The image with one part moved, built from the part that it has, so that the
    test holds for each version that Renovate brings: a later tag, the tag without
    its v (or with one), or another digest."""
    found = MARKDOWNLINT_PARTS.search(image)
    assert found is not None, image
    tag, digest = found["tag"], found["digest"]
    if part == "tag":
        tag = f"{tag}.1"
    elif part == "tag without its v":
        tag = tag.removeprefix("v") if tag.startswith("v") else f"v{tag}"
    else:
        digest = "d" * 64 if digest == "c" * 64 else "c" * 64
    other = f"{image[: found.start()]}:{tag}@sha256:{digest}"
    assert other != image
    return other


@pytest.mark.parametrize("part", ["tag", "digest", "tag without its v"])
@pytest.mark.parametrize("path", MARKDOWNLINT_SCRIPTS)
def test_another_tag_or_digest_of_the_image_in_one_place_is_found(
    tmp_path: Path, path: str, part: str
) -> None:
    # The test reads the image that the files hold, which Renovate moves, and writes
    # no tag or digest of its own (#1149).
    for name in MARKDOWNLINT_SCRIPTS:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(
            (ROOT / name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    [image] = markdownlint_images(tmp_path)
    other = another_image(image, part)
    changed = (tmp_path / path).read_text(encoding="utf-8")
    # The whole image, so that another image with the same tag stays as it is.
    assert image in changed
    (tmp_path / path).write_text(changed.replace(image, other), encoding="utf-8")

    images = markdownlint_images(tmp_path)

    assert len(images) == 2
    assert images[other] == [path]
    # Another image whose name only ends the same is another image.
    (tmp_path / path).write_text(
        changed.replace("davidanson/", "other/davidanson/"), encoding="utf-8"
    )
    assert len(markdownlint_images(tmp_path)) == 1


# An image by its tag and digest, as Renovate pins it in the workflows, the scripts,
# the template and the stacks.
IMAGE = re.compile(r"[\w.-]+(?:/[\w.-]+)*:[^@\s\"'`]+@sha256:(?P<digest>[0-9a-f]{64})")


def tracked_files(root: Path) -> list[str]:
    """The files of the repository as Git sees them, new ones not yet committed
    included, without what .gitignore leaves out."""
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        capture_output=True,
        check=True,
        env=git_environment(root),
    ).stdout.decode("utf-8")
    return [name for name in listed.split("\0") if (root / name).is_file()]


def moving_values(root: Path, names: list[str]) -> dict[str, str]:
    """The start of each value that only Renovate and pins.py write, with where it
    comes from: the digest of each image that a file outside tests/ runs and the
    sha256 of each download of .github/pins.toml."""
    values = {
        download.sha256[:8]: f"{pins.RECORD}: {dep}"
        for dep, download in pins.load_record(root).items()
    }
    for name in names:
        if not name.startswith("tests/"):
            text = (root / name).read_bytes().decode("utf-8", "replace")
            # The pattern is slow on long words, so only a file with a digest is searched.
            for found in IMAGE.finditer(text) if "@sha256:" in text else ():
                values.setdefault(found["digest"][:8], f"{name}: {found[0]}")
    return values


def written_values(root: Path, names: list[str]) -> list[str]:
    """Each file of tests/ that holds the start of a value that Renovate or pins.py
    moves, with the value."""
    values = sorted(moving_values(root, names).items())
    # Each file is read once: the tests hold large files.
    texts = {
        name: (root / name).read_bytes().decode("utf-8", "replace")
        for name in names
        if name.startswith("tests/")
    }
    return [
        f"{name} holds {start}, of {source}"
        for name, text in texts.items()
        for start, source in values
        if start in text
    ]


def test_no_test_writes_a_digest_or_a_checksum_that_renovate_moves() -> None:
    # A test that names the digest of an image or the sha256 of a download fails at
    # the next update, in a pull request of Renovate that can't fix it (#1149): it
    # reads the value from the file that holds it instead. A test that names only a
    # tag or a version gets past this guard.
    assert written_values(ROOT, tracked_files(ROOT)) == []


def test_a_digest_or_a_checksum_in_a_test_is_found(tmp_path: Path) -> None:
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github/pins.toml").write_text(
        f'[download."owner/tool"]\nurl = "https://example.org/{{version}}"\n'
        f'version = "1.0.0"\nsha256 = "{NEW}"\n',
        encoding="utf-8",
    )
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/run.sh").write_text(
        f"docker run owner/image:v1.0.0@sha256:{OLD}\n", encoding="utf-8"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_run.py").write_text(
        f'IMAGE = "owner/image:v1.0.0@sha256:{OLD[:8]}"\nSUM = "{NEW[:12]}"\n',
        encoding="utf-8",
    )
    (tmp_path / "tests/test_other.py").write_text("NO = 1\n", encoding="utf-8")
    names = [
        ".github/pins.toml",
        "scripts/run.sh",
        "tests/test_other.py",
        "tests/test_run.py",
    ]

    assert written_values(tmp_path, names) == sorted(
        [
            f"tests/test_run.py holds {OLD[:8]}, of scripts/run.sh: "
            f"owner/image:v1.0.0@sha256:{OLD}",
            f"tests/test_run.py holds {NEW[:8]}, of .github/pins.toml: owner/tool",
        ]
    )


class Reads:
    """The text of each address, the same for all, and the addresses it was asked."""

    def __init__(self, text: str) -> None:
        self.urls: list[str] = []
        self.text = text

    def __call__(self, url: str) -> str:
        self.urls.append(url)
        return self.text


def test_the_read_gives_the_text_of_the_file(tmp_path: Path) -> None:
    asked: list[Any] = []

    def opener(request: Any, timeout: float) -> Response:
        asked.append(request)
        return Response('{"name": "lint-action", "ü": 1}'.encode())

    assert pins.read("https://example.org/package.json", opener) == (
        '{"name": "lint-action", "ü": 1}'
    )
    assert asked[0].get_header("User-agent") == pins.AGENT
    (tmp_path / "package.json").write_bytes(b"{}")
    assert pins.read((tmp_path / "package.json").as_uri()) == "{}"
