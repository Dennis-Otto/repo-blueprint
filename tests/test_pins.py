"""Tests of pins.py, which writes the sha256 of each tool that Renovate moved to a new
release, against repositories of a few files and a download that stays offline."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import re
import urllib.error
from email.message import Message
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

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
        version = re.search(r"tool_([\d.]+)_linux", url)
        assert version
        return hashlib.sha256(f"tool {version[1]}".encode()).hexdigest()


# --------------------------------------------------------------- the blueprint itself


def test_every_download_of_the_blueprint_has_the_sha256_of_its_version() -> None:
    assert pins.check(ROOT) == []
    record = pins.load_record(ROOT)
    # pins.py keeps the file, so it is in the form that pins.py writes.
    text = (ROOT / pins.RECORD).read_bytes().decode("utf-8")
    assert text == pins.render_record(record, pins.load_bundles(ROOT))
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
        plain = re.sub(r"\$\{(\w+)\}", r"$\1", text.replace("\\\n", " "))
        plain = re.sub(r" {2,}", " ", plain)
        url = record[pin.dep].url.replace("{version}", f"${pin.name}")
        # An asset of a release on GitHub, which gh downloads by its parts.
        asset = pins.RELEASE_ASSET.fullmatch(url)
        if not asset:
            assert f'"{url}"' in plain, (pin.path, url)
            continue
        page = f"github.com/{asset['repository']}/releases/download/"
        assert page not in plain, (pin.path, page)
        repository, tag, name = (re.escape(asset[part]) for part in asset.groupdict())
        calls = (
            rf'download\.sh"? {repository} "{tag}" "?{name}"? ',
            rf'gh release download "{tag}" --repo {repository} --pattern "?{name}"? ',
        )
        assert any(re.search(call, plain) for call in calls), (pin.path, url)


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
        ".github/pins.toml the new name, with {version} for the version, and the "
        "files that download it the same name\n"
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


# ----------------------------------------------------- the package that an action runs

COMMIT = "1" * 40
MOVED = "2" * 40
IMAGE = "b" * 64
ACTION = "owner/lint-action"
LINT = f"""\
jobs:
  lint:
    steps:
      - uses: {ACTION}@{COMMIT} # v2.0.0
      - name: Fix
        uses: {ACTION}@{COMMIT} # v2.0.0
"""
LINT_SCRIPT = f"""\
#!/usr/bin/env bash
image="owner/lint:v1.2.0@sha256:{IMAGE}"
"""
BUNDLE = f"""
[bundle."{ACTION}"]
commit = "{COMMIT}"
package = "lint"
version = "1.2.0"
image = "owner/lint"
"""
STALE = (
    "scripts/lint.sh: the image owner/lint runs lint {found}, the action "
    f"{ACTION} {{version}}: give the image the tag of {{version}} and its digest, "
    "which Renovate brings in the pull request that moves the action"
)


def bundled_repository(
    root: Path, bundle: str = BUNDLE, lint: str = LINT, script: str = LINT_SCRIPT
) -> Path:
    """A repository with a download in step with its record, and an action that runs
    the package of an image that a script runs."""
    repository(root, record=RECORD.replace('"1.0.0"', '"1.1.0"') + bundle)
    (root / ".github/workflows/lint.yml").write_bytes(lint.encode())
    (root / "scripts").mkdir()
    (root / "scripts/lint.sh").write_bytes(script.encode())
    return root


class Reads:
    """The package.json of the action, which runs lint 1.3.0, and its addresses."""

    def __init__(self, text: str = '{"dependencies": {"lint": "1.3.0"}}') -> None:
        self.urls: list[str] = []
        self.text = text

    def __call__(self, url: str) -> str:
        self.urls.append(url)
        return self.text


def test_the_markdownlint_of_the_check_lint_is_that_of_its_image() -> None:
    # The check lint runs the markdownlint-cli2 of its action, scripts/markdownlint.sh
    # and the Variants workflow that of its image: pins.check fails while the two
    # differ, or while the record keeps the version of another commit of the action.
    action = "DavidAnson/markdownlint-cli2-action"
    bundles = pins.load_bundles(ROOT)
    assert set(bundles) == {action}
    uses = pins.find_uses(ROOT, {action})
    assert [use.path for use in uses] == [".github/workflows/lint.yml"] * 2
    assert pins.commits(uses) == {action: [bundles[action].commit]}
    assert bundles[action].package == "markdownlint-cli2"
    assert bundles[action].image == "davidanson/markdownlint-cli2"
    images = pins.find_images(ROOT, {bundles[action].image})
    assert [image.path for image in images] == [
        ".github/workflows/variants.yml",
        "scripts/markdownlint.sh",
    ]
    assert {image.version for image in images} == {bundles[action].version}
    assert pins.bundle_problems(ROOT, bundles) == []
    # pins.py keeps the file, bundles too, in the form that it writes.
    text = (ROOT / pins.RECORD).read_bytes().decode("utf-8")
    assert text == pins.render_record(pins.load_record(ROOT), bundles)


def test_an_image_that_runs_another_version_than_the_action_fails_the_check(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = bundled_repository(tmp_path, script=LINT_SCRIPT.replace("v1.2.0", "v1.1.0"))

    assert pins.main(["--check"], root=root) == 1

    stale = STALE.format(found="1.1.0", version="1.2.0")
    assert capsys.readouterr().err == f"pins.py: {stale}\n"
    # Also without the v of its tag, in a workflow.
    (root / ".github/workflows/lint.yml").write_bytes(
        (LINT + f"      - run: docker run owner/lint:1.2.0@sha256:{IMAGE} .\n").encode()
    )
    assert pins.check(root) == [stale]
    # Another image whose name ends in the same is another image.
    (root / "scripts/lint.sh").write_bytes(
        LINT_SCRIPT.replace("owner/lint:v1.2.0", "other/owner/lint:v1.1.0").encode()
    )
    assert pins.check(root) == []


def test_an_action_that_renovate_moved_gets_the_version_of_its_package(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = bundled_repository(tmp_path, lint=LINT.replace(COMMIT, MOVED))
    reads = Reads()

    assert pins.check(root) == [
        f"{pins.RECORD}: the workflows pin {ACTION} at {MOVED}, the record at "
        f"{COMMIT}; python3 pins.py reads the version of lint that it runs"
    ]
    assert pins.main([], root=root, fetch=Fetches(), read=reads) == 0

    assert reads.urls == [
        f"https://raw.githubusercontent.com/{ACTION}/{MOVED}/package.json"
    ]
    assert pins.load_bundles(root) == {
        ACTION: pins.Bundle(MOVED, "lint", "1.3.0", "owner/lint")
    }
    assert capsys.readouterr().out == (
        f"{ACTION} {MOVED}: lint 1.3.0\n{pins.RECORD}: 1 downloads and 1 actions\n"
    )
    text = (root / pins.RECORD).read_bytes().decode("utf-8")
    assert text == pins.render_record(pins.load_record(root), pins.load_bundles(root))
    # Until Renovate moves the image as well.
    assert pins.check(root) == [STALE.format(found="1.2.0", version="1.3.0")]
    (root / "scripts/lint.sh").write_bytes(
        LINT_SCRIPT.replace("v1.2.0", "v1.3.0").encode()
    )
    assert pins.check(root) == []
    # The next run has nothing to read.
    assert pins.main([], root=root, fetch=Fetches(), read=reads) == 0
    assert len(reads.urls) == 1


@pytest.mark.parametrize(
    ("lint", "problem"),
    [
        (
            "jobs: {}\n",
            f"{pins.RECORD}: no workflow pins the action {ACTION}; remove it",
        ),
        (
            LINT.replace(f"{COMMIT} # v2.0.0\n", f"{MOVED} # v2.1.0\n", 1),
            f"The workflows pin {ACTION} at {MOVED} and {COMMIT}: give each the same "
            "commit",
        ),
    ],
)
def test_an_action_that_the_workflows_pin_unclearly_stops_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], lint: str, problem: str
) -> None:
    root = bundled_repository(tmp_path, lint=lint)
    reads = Reads()

    assert pins.check(root) == [problem]
    assert pins.main([], root=root, fetch=Fetches(), read=reads) == 2
    assert capsys.readouterr().err == f"pins.py: {problem}\n"
    assert reads.urls == []


def test_an_action_whose_image_no_file_runs_fails_the_check(tmp_path: Path) -> None:
    root = bundled_repository(tmp_path, script="#!/usr/bin/env bash\n")

    assert pins.check(root) == [
        f"{pins.RECORD}: no script or workflow runs the image owner/lint of {ACTION}; "
        "remove it"
    ]


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "[]",
        '{"dependencies": {"other": "1.3.0"}}',
        '{"dependencies": {"lint": "^1.3.0"}}',
        '{"dependencies": {"lint": 1}}',
    ],
)
def test_a_package_json_without_the_exact_version_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], text: str
) -> None:
    root = bundled_repository(tmp_path, lint=LINT.replace(COMMIT, MOVED))
    record = (root / pins.RECORD).read_bytes()

    assert pins.main([], root=root, fetch=Fetches(), read=Reads(text)) == 2

    assert capsys.readouterr().err == (
        f"pins.py: https://raw.githubusercontent.com/{ACTION}/{MOVED}/package.json "
        "names no exact version of lint that it runs\n"
    )
    assert (root / pins.RECORD).read_bytes() == record


@pytest.mark.parametrize(
    "bundle",
    [
        BUNDLE.replace(COMMIT, "abc"),
        BUNDLE.replace('"1.2.0"', '"^1.2.0"'),
        BUNDLE.replace('"owner/lint"', '""'),
        BUNDLE.replace('"lint"', "1"),
        BUNDLE + 'note = "more"\n',
        BUNDLE.replace('image = "owner/lint"\n', ""),
        f'\n[bundle]\n"{ACTION}" = "{COMMIT}"\n',
    ],
)
def test_a_bundle_that_pins_py_cannot_read_stops_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], bundle: str
) -> None:
    root = bundled_repository(tmp_path, bundle=bundle)

    assert pins.main(["--check"], root=root) == 2

    assert capsys.readouterr().err.startswith(f"pins.py: {pins.RECORD}")


def test_a_record_of_bundles_alone_or_without_tables_stops_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = bundled_repository(tmp_path)
    for record in (BUNDLE, 'bundle = "owner/lint-action"\n' + RECORD):
        (root / pins.RECORD).write_bytes(record.encode())

        assert pins.main(["--check"], root=root) == 2

        assert capsys.readouterr().err == (
            f'pins.py: {pins.RECORD} has only tables [download."OWNER/NAME"] and '
            '[bundle."OWNER/ACTION"]\n'
        )


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
