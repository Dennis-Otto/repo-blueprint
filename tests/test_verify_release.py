"""Tests of the release verification, the bot of verify-release.yml that only reads: a
changed condition or a typo in one of its calls of gh would otherwise show only when a
real release is verified. Its step runs in bash, as GitHub runs it, with the one fake gh,
tests/fake_gh.py, against a table of releases: a complete one, one that lacks an asset,
one with a wrong checksum or signature, and one that is still a draft. Each case checks
the exit code, the annotation and the job summary. The delivery to HACS has its own
table in tests/test_template.py, next to the build of its zip."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import shutil
import tarfile
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
from shell import BASH
from workflow_steps import (
    Answer,
    StepResult,
    acts_of,
    exact,
    job,
    recording,
    run_step,
    step,
    workflow,
)

pytestmark = pytest.mark.skipif(
    BASH is None, reason="the steps run in bash, Git Bash on Windows"
)
# The step reads the answers of the API with jq, and the fake gh filters them with it;
# the runners of GitHub have it, Git for Windows doesn't.
WITH_JQ = pytest.mark.skipif(shutil.which("jq") is None, reason="needs jq")

WORKFLOW = "verify-release.yml"
STEP = "Verify the release as its users can"
SCRIPT: str = step(WORKFLOW, "verify", STEP)["run"]
TAG = "v1.2.3"
VERSION = TAG.removeprefix("v")
COMMIT = "1" * 40
OTHER_COMMIT = "2" * 40
SIGNED_COMMIT = f"api repos/o/r/commits/{COMMIT} --jq .commit.verification.verified"
# What every check of a provenance demands besides its workflow: a run for main, the
# only branch whose runs make releases, on a runner of GitHub. gh answers only a check
# that demands it, so a check without it fails.
TRUSTED_RUN = " --source-ref refs/heads/main --deny-self-hosted-runners"
GITSIGN_VERSION = step(WORKFLOW, "verify", STEP)["env"]["GITSIGN_VERSION"]
# The download of gitsign through the API, which survives an outage of GitHub's
# downloads without a token (decision 0133).
GITSIGN_DOWNLOAD = (
    re.escape(
        f"release download v{GITSIGN_VERSION} --repo sigstore/gitsign"
        f" --pattern gitsign_{GITSIGN_VERSION}_linux_amd64 --output "
    )
    + r"\S+/gitsign --clobber"
)
GITHUB_504 = (
    "HTTP 504: Gateway Timeout"
    " (https://api.github.com/repos/sigstore/gitsign/releases/assets/1)\n"
)
PYTHON3 = 'exec "$FAKE_GH_PYTHON" "$@"\n'  # The Python of the tests, on every machine.
# The signed statement of the bundle, which provenance.intoto.jsonl repeats.
ENVELOPE = {"payload": "e30=", "signatures": [{"sig": "c2lnbmVk"}]}


def api(arguments: str, answer: object) -> Answer:
    """The answer of the API to a call of gh, through the filter of its --jq."""
    return Answer(re.escape(arguments), json=answer)


def spdx_of(name: str, version: str) -> str:
    """An SPDX document that describes the package, as build-release.yml writes it."""
    return json.dumps(
        {
            "packages": [
                {"SPDXID": "SPDXRef-it", "name": name, "versionInfo": version}
            ],
            "relationships": [
                {
                    "spdxElementId": "SPDXRef-DOCUMENT",
                    "relationshipType": "DESCRIBES",
                    "relatedSpdxElement": "SPDXRef-it",
                }
            ],
        }
    )


def cyclonedx_of(name: str, version: str) -> str:
    """A CycloneDX document that describes the package, as build-release.yml writes it."""
    return json.dumps({"metadata": {"component": {"name": name, "version": version}}})


def zip_of(files: Mapping[str, str]) -> bytes:
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return data.getvalue()


def npm_package_of(package: str | None) -> bytes:
    """An npm package, as npm pack makes it: a tar.gz with a folder named package."""
    data = io.BytesIO()
    manifest = json.dumps({"name": package} if package else {}).encode()
    with tarfile.open(fileobj=data, mode="w:gz") as archive:
        member = tarfile.TarInfo("package/package.json")
        member.size = len(manifest)
        archive.addfile(member, io.BytesIO(manifest))
    return data.getvalue()


def app_package_of(version: str | None) -> bytes:
    """The signed package of the Nextcloud app demo, as the build packs it: a tar.gz
    with the folder of its id, whose appinfo/info.xml has the version, or none."""
    data = io.BytesIO()
    info = (
        f"<info>\n  <id>demo</id>\n  <version>{version}</version>\n</info>\n"
        if version
        else "<info>\n  <id>demo</id>\n</info>\n"
    ).encode()
    with tarfile.open(fileobj=data, mode="w:gz") as archive:
        member = tarfile.TarInfo("demo/appinfo/info.xml")
        member.size = len(info)
        archive.addfile(member, io.BytesIO(info))
    return data.getvalue()


def served_as(url: str) -> str:
    """The name of the file with what the stand-in for curl gets from the URL."""
    return re.sub(r"[^a-zA-Z0-9.]", "_", url)


def write_files(folder: Path, files: Mapping[str, str | bytes | None]) -> None:
    """Writes the files into the folder, other than those whose content is None."""
    folder.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        if content is not None:
            data = content.encode() if isinstance(content, str) else content
            (folder / name).write_bytes(data)


def verify(
    tmp_path: Path,
    *,
    tag: str = TAG,
    repository: str = "o/r",
    named: bool = True,
    weekly: bool = False,
    publish_to: str = "",
    release: Mapping[str, object] | None = None,
    assets: Mapping[str, str | bytes | None] | None = None,
    answers: Sequence[Answer] = (),
    served: Mapping[str, str | bytes | None] | None = None,
    stubs: Mapping[str, str] | None = None,
    signature: int = 0,
    pinned: str | None = None,
    downloads: Sequence[int] = (0,),
    tag_type: str = "tag",
    tag_name: str | None = None,
    fetched: int = 0,
    npm_has: str | None = None,
) -> StepResult:
    """Runs the verification of a release that is complete but for what the test
    changes, with gh, curl, git and npm as stand-ins. The release is named by its tag or
    is the latest, its JSON changes by release, each asset by its name in assets, with
    None for one that is missing, and what curl gets by its URL in served, with None for
    what fails. A planned answer goes before those of a complete release. gitsign ends
    with signature, against the checksum pinned or its own, git cat-file names the type
    of the tag and the name inside it, tag_name or the tag's own, git fetch ends with
    fetched, and npm has the integrity npm_has.
    The downloads of gitsign end with the codes of downloads, one after the other, the
    last for every one after; an error is GitHub's 504."""
    version = tag.removeprefix("v")
    name = repository.partition("/")[2]
    write_files(
        tmp_path / "runner/assets",
        {
            "provenance.sigstore.json": json.dumps({"dsseEnvelope": ENVELOPE}),
            "provenance.intoto.jsonl": json.dumps(ENVELOPE, separators=(",", ":")),
            f"{name}.spdx.json": spdx_of(name, version),
            f"{name}.cdx.json": cyclonedx_of(name, version),
            **(assets or {}),
        },
    )
    gitsign = "#!/usr/bin/env bash\n" + recording("gitsign", f"exit {signature}")
    write_files(
        tmp_path / "served",
        {served_as(url): content for url, content in (served or {}).items()},
    )
    answered = {
        "tag_name": tag,
        "immutable": True,
        "prerelease": False,
        "assets": [{"name": "provenance.sigstore.json"}],
        **(release or {}),
    }
    workflows = f"{re.escape(repository)}/\\.github/workflows"
    return run_step(
        tmp_path,
        WORKFLOW,
        "verify",
        STEP,
        answers=[
            *answers,
            *(
                Answer(
                    GITSIGN_DOWNLOAD,
                    "" if code else gitsign,
                    GITHUB_504 if code else "",
                    code,
                    once=index < len(downloads) - 1,
                )
                for index, code in enumerate(downloads)
            ),
            api("release view --json tagName --jq .tagName", {"tagName": tag}),
            exact(f"api repos/{repository}/releases/tags/{tag}", json.dumps(answered)),
            api(f"api repos/{repository}/commits/{tag} --jq .sha", {"sha": COMMIT}),
            api(
                f"api repos/{repository}/commits/{COMMIT}"
                " --jq .commit.verification.verified",
                {"commit": {"verification": {"verified": True}}},
            ),
            exact(f"release download {tag}"),
            Answer(
                rf"attestation verify (?!oci://)\S+ --repo {re.escape(repository)}"
                rf" --signer-workflow {workflows}/build-release\.yml"
                + re.escape(TRUSTED_RUN)
                + r"( --bundle provenance\.sigstore\.json)?"
            ),
            # The image, which its own isolated build attests, by the lower-case name
            # that GHCR takes.
            exact(
                f"attestation verify oci://ghcr.io/{repository.lower()}:{version}"
                f" --repo {repository} --signer-workflow"
                f" {repository}/.github/workflows/build-image.yml" + TRUSTED_RUN
            ),
        ],
        env={
            "GH_REPO": repository,
            "TAG": tag if named else "",
            "PUBLISH_TO": publish_to,
            "WEEKLY": "true" if weekly else "false",
            "GITSIGN_SHA256": pinned or hashlib.sha256(gitsign.encode()).hexdigest(),
        },
        stubs={
            "curl": recording(
                "curl",
                "while (($#)); do\n"
                '  case "$1" in\n'
                '    --output) output="$2"; shift ;;\n'
                '    https://*) url="$1" ;;\n'
                "  esac\n"
                "  shift\n"
                "done\n"
                f'served="{(tmp_path / "served").as_posix()}/'
                '${url//[^a-zA-Z0-9.]/_}"\n'
                '[[ -f "$served" ]] || exit 22\n'
                'cp "$served" "$output"',
            ),
            # The repository that git init makes, and the tag that it fetches into it.
            "git": recording(
                "git",
                '[[ "$1" != init ]] || mkdir -p "${@: -1}"\n'
                f'[[ "$*" != *" fetch "* ]] || exit {fetched}\n'
                f'[[ "$*" != *" cat-file -t "* ]] || echo {tag_type}\n'
                f'[[ "$*" != *" cat-file tag "* ]] ||'
                f" printf 'object {COMMIT}\\ntype commit\\ntag %s\\n\\nThe release\\n'"
                f" {tag_name or tag}",
            ),
            "npm": recording(
                "npm",
                f"echo '{npm_has}'" if npm_has else "exit 1",
            ),
            "python3": PYTHON3,
            "sleep": recording("sleep"),
            **(stubs or {}),
        },
    )


# The deliveries of PUBLISH_TO, each as a complete release has it.
WHEEL = b"the wheel"
SDIST = b"the source archive"
PYPI_URL = f"https://pypi.org/pypi/r/{VERSION}/json"
PYPI_FILES = {
    "urls": [
        {"digests": {"sha256": hashlib.sha256(content).hexdigest()}}
        for content in (WHEEL, SDIST)
    ]
}
PYPI: dict[str, Any] = {
    "publish_to": "pypi",
    "assets": {f"r-{VERSION}-py3-none-any.whl": WHEEL, f"r-{VERSION}.tar.gz": SDIST},
    "served": {PYPI_URL: json.dumps(PYPI_FILES)},
}
TARBALL = npm_package_of("demo")
INTEGRITY = f"sha512-{base64.b64encode(hashlib.sha512(TARBALL).digest()).decode()}"
NPM: dict[str, Any] = {
    "publish_to": "npm",
    "assets": {f"r-{VERSION}.tgz": TARBALL},
    "npm_has": INTEGRITY,
}
IMAGE = f"ghcr.io/o/r:{VERSION}"
ATTESTED_IMAGE = (
    f"attestation verify oci://{IMAGE} --repo o/r"
    " --signer-workflow o/r/.github/workflows/build-image.yml" + TRUSTED_RUN
)
# The provenance of an image made before its isolated build, which the release
# workflow attested in the job that pushed it.
IMAGE_OF_THE_RELEASE_WORKFLOW = (
    f"attestation verify oci://{IMAGE} --repo o/r"
    " --signer-workflow o/r/.github/workflows/release.yml" + TRUSTED_RUN
)
EXTENSION = f"r-{VERSION}.zip"
MANIFEST_V3 = {"manifest_version": 3, "version": VERSION}
CHROME: dict[str, Any] = {
    "publish_to": "chrome-web-store",
    "assets": {EXTENSION: zip_of({"manifest.json": json.dumps(MANIFEST_V3)})},
}


def info_xml_at(tag: str) -> str:
    """The call of gh for the appinfo/info.xml of the Nextcloud app at the tag."""
    return (
        "api -H Accept: application/vnd.github.raw+json"
        f" repos/o/r/contents/appinfo/info.xml?ref={tag}"
    )


INFO_XML = info_xml_at(TAG)
APP_PAGE = "https://apps.nextcloud.com/apps/demo"
# The page of every release of the app, which shows a beta among the unstable ones.
RELEASES_PAGE = f"{APP_PAGE}/releases"
OFFERED = f'<a href="https://github.com/o/r/releases/download/{TAG}/demo.tar.gz">'
NOT_YET_OFFERED = (
    '<a href="https://github.com/o/r/releases/download/v1.2.2/demo.tar.gz">'
)
NEXTCLOUD: dict[str, Any] = {
    "publish_to": "nextcloud-appstore",
    "answers": [exact(INFO_XML, "<info><id>demo</id></info>\n")],
    "assets": {"demo.tar.gz": app_package_of(VERSION)},
    "served": {APP_PAGE: OFFERED},
}
# A beta of the app, whose info.xml at its tag on main still says the last release.
APP_BETA = "v1.3.0-beta.1"
NEXTCLOUD_BETA: dict[str, Any] = {
    "publish_to": "nextcloud-appstore",
    "tag": APP_BETA,
    "answers": [
        exact(
            info_xml_at(APP_BETA),
            "<info><id>demo</id><version>1.2.3</version></info>\n",
        )
    ],
    "assets": {"demo.tar.gz": app_package_of(APP_BETA.removeprefix("v"))},
    "served": {
        RELEASES_PAGE: (
            f'<a href="https://github.com/o/r/releases/download/{APP_BETA}/demo.tar.gz">'
        )
    },
}
MAJOR_TAG = "api repos/o/r/commits/v1 --jq .sha"
ACTION: dict[str, Any] = {
    "publish_to": "github-action",
    "answers": [api(MAJOR_TAG, {"sha": COMMIT})],
}

# What a release can deliver or attach, each with the line that it adds to the summary.
PASSES: dict[str, tuple[dict[str, Any], str]] = {
    "a statement of OpenVEX": (
        {
            "assets": {
                "r.openvex.json": json.dumps(
                    {
                        "@context": "https://openvex.dev/ns/v0.2.0",
                        "statements": [{"status": "not_affected"}],
                    }
                )
            }
        },
        "r.openvex.json states the advisories that don't affect the release.",
    ),
    "the files on PyPI": (PYPI, f"PyPI has the same files of {VERSION}."),
    "only a wheel, on PyPI too": (
        {
            **PYPI,
            "assets": {f"r-{VERSION}-py3-none-any.whl": WHEEL},
            "served": {PYPI_URL: json.dumps({"urls": PYPI_FILES["urls"][:1]})},
        },
        f"PyPI has the same files of {VERSION}.",
    ),
    "the package on npm": (NPM, f"npm has the same package demo@{VERSION}."),
    "the image in GHCR": (
        {"publish_to": "ghcr"},
        f"{IMAGE} carries the signed provenance of its isolated build.",
    ),
    "the zip of the extension": (
        CHROME,
        f"./{EXTENSION} holds the manifest.json of Manifest V3 and the version"
        f" {VERSION} at its root, as the Chrome Web Store takes it.",
    ),
    "a beta of the extension, whose manifest has the numbers of its version": (
        {
            **CHROME,
            "tag": "v1.3.0-beta.2",
            "assets": {
                "r.zip": zip_of(
                    {
                        "manifest.json": json.dumps(
                            {"manifest_version": 3, "version": "1.3.0"}
                        )
                    }
                )
            },
        },
        "./r.zip holds the manifest.json of Manifest V3 and the version 1.3.0 at its"
        " root, as the Chrome Web Store takes it.",
    ),
    "the app in the Nextcloud App Store": (
        NEXTCLOUD,
        f"The Nextcloud App Store offers the package of demo {VERSION}.",
    ),
    "the version of the package of the Nextcloud app": (
        NEXTCLOUD,
        f"The appinfo/info.xml in demo.tar.gz has the version {VERSION}, which the"
        " App Store takes for its release.",
    ),
    "a beta of the Nextcloud app, for the beta channel alone": (
        NEXTCLOUD_BETA,
        "The Nextcloud App Store offers the package of demo 1.3.0-beta.1 only to"
        " servers on the beta channel of Nextcloud.",
    ),
    "the version of the beta in its package of the Nextcloud app": (
        NEXTCLOUD_BETA,
        "The appinfo/info.xml in demo.tar.gz has the version 1.3.0-beta.1, which the"
        " App Store takes for its release.",
    ),
    "the major tag of an action": (ACTION, "The major tag v1 points at the release."),
    "a prerelease of an action": (
        {"publish_to": "github-action", "tag": "v1.3.0-beta.1"},
        "A prerelease leaves the major tag where it is.",
    ),
}

# What a release can have wrong, each with the one problem that it makes of a release
# that is complete but for it, whichever run looks at it.
PROBLEMS: dict[str, tuple[dict[str, Any], str]] = {
    # A release that isn't there yet.
    "a draft": (
        {
            # GitHub answers for a tag only with a published release.
            "answers": [
                exact(
                    f"api repos/o/r/releases/tags/{TAG}",
                    '{"message":"Not Found","status":"404"}',
                    code=1,
                    err="gh: Not Found (HTTP 404)\n",
                )
            ]
        },
        f"GitHub shows no published release with the tag {TAG}: it is still a draft,"
        " there is none, or GitHub didn't answer.",
    ),
    "a release that isn't immutable": (
        {"release": {"immutable": False}},
        "The release is not immutable.",
    ),
    # A wrong checksum or signature.
    "an unsigned commit": (
        {
            "answers": [
                api(SIGNED_COMMIT, {"commit": {"verification": {"verified": False}}})
            ]
        },
        f"Its commit {COMMIT} is not signed.",
    ),
    "a tag without a commit": (
        {"answers": [exact(f"api repos/o/r/commits/{TAG} --jq .sha", code=1)]},
        f"GitHub doesn't show the commit of the tag {TAG}.",
    ),
    "a tag that another signed": (
        {"signature": 1},
        f"The signature of the tag {TAG} isn't one of the release workflow.",
    ),
    # A new ref at the signed tag of an older release, whose signature holds.
    "a signed tag of another version": (
        {"tag_name": "v1.2.2"},
        f"The tag {TAG} is the signed tag v1.2.2 of another version.",
    ),
    "a gitsign with another checksum": (
        {"pinned": "0" * 64},
        f"The download of gitsign {GITSIGN_VERSION} doesn't have its sha256, so the"
        f" tag {TAG} can't be checked.",
    ),
    "a gitsign that can't be downloaded": (
        {"downloads": (1,)},
        f"gitsign {GITSIGN_VERSION} can't be downloaded: GitHub failed five times in two"
        " and a half minutes (https://www.githubstatus.com), so the tag"
        f" {TAG} can't be checked. Run the check again once GitHub works.",
    ),
    "a tag that can't be fetched": (
        {"fetched": 1},
        f"The tag {TAG} can't be fetched from the repository.",
    ),
    "a statement that isn't the one of the bundle": (
        {"assets": {"provenance.intoto.jsonl": "{}\n"}},
        "provenance.intoto.jsonl differs from the signed statement of the bundle.",
    ),
    "an asset without a provenance": (
        {"answers": [Answer(r"attestation verify r\.spdx\.json .*", code=1)]},
        "r.spdx.json has no valid provenance of the isolated build.",
    ),
    "an asset that the bundle doesn't sign": (
        {
            "answers": [
                Answer(r"attestation verify r\.cdx\.json .* --bundle .*", code=1)
            ]
        },
        "r.cdx.json has no valid provenance of the isolated build.",
    ),
    # A missing asset.
    "assets that can't be downloaded": (
        {"answers": [exact(f"release download {TAG}", code=1)]},
        f"The assets of the release {TAG} can't be downloaded.",
    ),
    "no bundle of the provenance": (
        {
            "assets": {
                "provenance.sigstore.json": None,
                "provenance.intoto.jsonl": None,
            }
        },
        "The release has no provenance.sigstore.json.",
    ),
    "no SBOM": ({"assets": {"r.spdx.json": None}}, "The release has no SBOM."),
    "a statement of OpenVEX without statements": (
        {
            "assets": {
                "r.openvex.json": json.dumps(
                    {"@context": "https://openvex.dev/ns/v0.2.0", "statements": []}
                )
            }
        },
        "r.openvex.json is no OpenVEX document with statements.",
    ),
    # A delivery that doesn't have the release.
    "other files on PyPI": (
        {
            **PYPI,
            "served": {
                PYPI_URL: json.dumps({"urls": [{"digests": {"sha256": "0" * 64}}]})
            },
        },
        f"PyPI doesn't have the files of the release {VERSION}.",
    ),
    "a version that PyPI doesn't have": (
        {**PYPI, "served": {PYPI_URL: None}},
        f"PyPI doesn't have the files of the release {VERSION}.",
    ),
    "an answer of PyPI that isn't its JSON": (
        {**PYPI, "served": {PYPI_URL: "<html>Bad gateway</html>"}},
        f"PyPI doesn't have the files of the release {VERSION}.",
    ),
    "no wheel and no source archive": (
        {"publish_to": "pypi", "served": PYPI["served"]},
        "The release has no wheel and no source archive to compare with PyPI.",
    ),
    "only a wheel of the two files on PyPI": (
        {**PYPI, "assets": {f"r-{VERSION}-py3-none-any.whl": WHEEL}},
        f"PyPI doesn't have the files of the release {VERSION}.",
    ),
    "another package on npm": (
        {**NPM, "npm_has": "sha512-other"},
        f"npm doesn't have the package of the release {VERSION}.",
    ),
    "a version that npm doesn't have": (
        {**NPM, "npm_has": None},
        f"npm doesn't have the package of the release {VERSION}.",
    ),
    "no npm package": (
        {"publish_to": "npm"},
        "The release has no single npm package, a .tgz.",
    ),
    "two npm packages": (
        {**NPM, "assets": {"r.tgz": TARBALL, "s.tgz": TARBALL}},
        "The release has no single npm package, a .tgz.",
    ),
    "an npm package without a name": (
        {**NPM, "assets": {"r.tgz": npm_package_of(None)}},
        "r.tgz has no package.json with a name, so npm can't be asked for it.",
    ),
    "a .tgz that is no npm package": (
        {**NPM, "assets": {"r.tgz": b"no archive"}},
        "r.tgz has no package.json with a name, so npm can't be asked for it.",
    ),
    "an image without a provenance": (
        {"publish_to": "ghcr", "answers": [exact(ATTESTED_IMAGE, code=1)]},
        f"{IMAGE} has no valid provenance of its isolated build.",
    ),
    "two zips of the extension": (
        {**CHROME, "assets": {"r.zip": zip_of({}), "s.zip": zip_of({})}},
        "The release has no single zip of the extension for the Chrome Web Store.",
    ),
    "a zip with another version": (
        {
            **CHROME,
            "assets": {
                EXTENSION: zip_of(
                    {"manifest.json": json.dumps({**MANIFEST_V3, "version": "1.2.2"})}
                )
            },
        },
        f"./{EXTENSION} has no manifest.json of Manifest V3 and the version {VERSION}"
        " at its root.",
    ),
    "a zip of Manifest V2": (
        {
            **CHROME,
            "assets": {
                EXTENSION: zip_of(
                    {
                        "manifest.json": json.dumps(
                            {**MANIFEST_V3, "manifest_version": 2}
                        )
                    }
                )
            },
        },
        f"./{EXTENSION} has no manifest.json of Manifest V3 and the version {VERSION}"
        " at its root.",
    ),
    "a zip without a manifest": (
        {**CHROME, "assets": {EXTENSION: zip_of({"demo/manifest.json": "{}"})}},
        f"./{EXTENSION} has no manifest.json of Manifest V3 and the version {VERSION}"
        " at its root.",
    ),
    "a tag without the numbers of a version": (
        {**CHROME, "tag": "nightly"},
        f"./{EXTENSION} has no manifest.json of Manifest V3 and the version nightly at"
        " its root.",
    ),
    "a tag without the file of the Nextcloud app": (
        {**NEXTCLOUD, "answers": [exact(INFO_XML, code=1)]},
        f"appinfo/info.xml at {TAG} names no app, so the Nextcloud App Store can't be"
        " checked.",
    ),
    "a file of the Nextcloud app without its id": (
        {**NEXTCLOUD, "answers": [exact(INFO_XML, "<info/>\n")]},
        f"appinfo/info.xml at {TAG} names no app, so the Nextcloud App Store can't be"
        " checked.",
    ),
    "a page of the app store with an older package": (
        {**NEXTCLOUD, "served": {APP_PAGE: NOT_YET_OFFERED}},
        f"The Nextcloud App Store doesn't offer the package of demo {VERSION}.",
    ),
    "an app store that doesn't answer": (
        {**NEXTCLOUD, "served": {APP_PAGE: None}},
        f"The Nextcloud App Store doesn't offer the package of demo {VERSION}.",
    ),
    # The package of a beta that still says the last release, which the App Store
    # would have taken for that release, replacing its package for every user.
    "a package of the Nextcloud app with the version of the last release": (
        {**NEXTCLOUD_BETA, "assets": {"demo.tar.gz": app_package_of(VERSION)}},
        f"The appinfo/info.xml in demo.tar.gz has the version {VERSION}, not"
        " 1.3.0-beta.1, so the App Store takes the package for another release.",
    ),
    "a package of the Nextcloud app without its version": (
        {**NEXTCLOUD, "assets": {"demo.tar.gz": app_package_of(None)}},
        f"The appinfo/info.xml in demo.tar.gz has the version none, not {VERSION},"
        " so the App Store takes the package for another release.",
    ),
    "no package of the Nextcloud app": (
        {**NEXTCLOUD, "assets": {"demo.tar.gz": None}},
        f"The appinfo/info.xml in demo.tar.gz has the version none, not {VERSION},"
        " so the App Store takes the package for another release.",
    ),
    "a beta that the App Store doesn't list among the unstable releases": (
        {**NEXTCLOUD_BETA, "served": {RELEASES_PAGE: NOT_YET_OFFERED}},
        "The Nextcloud App Store doesn't offer the package of demo 1.3.0-beta.1.",
    ),
    "a major tag at another commit": (
        {**ACTION, "answers": [api(MAJOR_TAG, {"sha": OTHER_COMMIT})]},
        f"The major tag v1 points at {OTHER_COMMIT}, not at the release.",
    ),
    "no major tag": (
        {**ACTION, "answers": [exact(MAJOR_TAG, code=1)]},
        "The major tag v1 points at nothing, not at the release.",
    ),
}

# What only a release older than the release workflow of the blueprint may lack: the
# weekly run accepts it, by what it writes, and a run that names a tag finds the problem.
OLDER_RELEASE: dict[str, tuple[dict[str, Any], str, str]] = {
    "a tag without a signature": (
        {"tag_type": "commit"},
        f"::notice::The tag {TAG} is older than the signed tags.",
        f"The tag {TAG} is not a signed tag.",
    ),
    "no SBOM as CycloneDX": (
        {"assets": {"r.cdx.json": None}},
        "::notice::The release is older than the SBOM as CycloneDX.",
        "The release has no SBOM as CycloneDX.",
    ),
    "an SPDX SBOM of the folder of the repository": (
        {"assets": {"r.spdx.json": spdx_of("workspace", "")}},
        "::notice::r.spdx.json is older than the SBOMs of what a release ships.",
        f"r.spdx.json doesn't describe r {VERSION}, what the release ships.",
    ),
    "an SPDX SBOM of another version": (
        {"assets": {"r.spdx.json": spdx_of("r", "1.2.2")}},
        "::notice::r.spdx.json is older than the SBOMs of what a release ships.",
        f"r.spdx.json doesn't describe r {VERSION}, what the release ships.",
    ),
    "a CycloneDX SBOM of the folder of the repository": (
        {"assets": {"r.cdx.json": cyclonedx_of("workspace", "")}},
        "::notice::r.cdx.json is older than the SBOMs of what a release ships.",
        f"r.cdx.json doesn't describe r {VERSION}, what the release ships.",
    ),
    "the provenance of the release workflow": (
        {
            "answers": [
                Answer(
                    r"attestation verify r\.spdx\.json --repo o/r --signer-workflow"
                    r" o/r/\.github/workflows/build-release\.yml .*",
                    code=1,
                ),
                Answer(
                    r"attestation verify r\.spdx\.json --repo o/r --signer-workflow"
                    r" o/r/\.github/workflows/release\.yml"
                    + re.escape(TRUSTED_RUN)
                    + r"( --bundle provenance\.sigstore\.json)?"
                ),
            ]
        },
        "r.spdx.json carries the signed provenance of the release workflow, from"
        " before the isolated build.",
        "r.spdx.json has no valid provenance of the isolated build.",
    ),
    "the provenance of the release workflow for the image": (
        {
            "publish_to": "ghcr",
            "answers": [
                exact(ATTESTED_IMAGE, code=1),
                exact(IMAGE_OF_THE_RELEASE_WORKFLOW),
            ],
        },
        f"{IMAGE} carries the signed provenance of the release workflow, from before"
        " its isolated build.",
        f"{IMAGE} has no valid provenance of its isolated build.",
    ),
    "no zip of the extension": (
        {"publish_to": "chrome-web-store"},
        "::notice::The release is older than the zip of the extension for the Chrome"
        " Web Store.",
        "The release has no single zip of the extension for the Chrome Web Store.",
    ),
}

# What the weekly run finds in every release, however old.
WEEKLY_PROBLEMS = (
    "a release that isn't immutable",
    "an unsigned commit",
    "a tag that another signed",
    "a signed tag of another version",
    "an asset without a provenance",
    "no SBOM",
)


def assert_one_problem(done: StepResult, problem: str, tag: str = TAG) -> None:
    """The step fails, and names the problem in an annotation and in the summary."""
    assert done.returncode == 1, done.stdout + done.stderr
    assert f"::error::{problem}\n" in done.stdout
    assert f"- ✘ {problem}\n" in done.summary, done.summary
    assert done.summary.count("✘") == 1, done.summary
    assert done.stdout.count("::error::") == 1, done.stdout
    assert f"The release {tag} has 1 problem(s).\n" in done.summary, done.summary
    assert f"The release {tag} verifies." not in done.summary


def assert_verified(done: StepResult, tag: str = TAG) -> None:
    """The step passes without a single problem."""
    assert done.returncode == 0, done.stdout + done.stderr
    assert "::error::" not in done.stdout
    assert "✘" not in done.summary, done.summary
    assert done.summary.endswith(f"The release {tag} verifies.\n"), done.summary


def test_the_bot_only_reads_and_this_file_runs_its_one_step_that_calls_gh() -> None:
    verification = workflow(WORKFLOW)
    calling_gh = [
        (job_id, found.get("name"))
        for job_id, settings in verification["jobs"].items()
        for found in settings["steps"]
        if re.search(r"^[^#\n]*\bgh\b", found.get("run", ""), re.MULTILINE)
    ]
    assert calling_gh == [("verify", STEP)]
    # Read-only by its script and by the rights of its token.
    assert acts_of(SCRIPT) == []
    assert verification["permissions"] == {}
    assert job(WORKFLOW, "verify")["permissions"] == {
        "attestations": "read",
        "contents": "read",
    }


def test_every_delivery_of_the_step_has_a_case_that_passes_and_one_that_fails() -> None:
    deliveries = set(re.findall(r"^ {2}([a-z-]+)\)$", SCRIPT, re.MULTILINE))
    assert "pypi" in deliveries
    for table in (PASSES, PROBLEMS):
        tested = {change.get("publish_to") for change, _ in table.values()}
        # HACS has its cases in tests/test_template.py, with the build of its zip.
        assert tested - {None} == deliveries - {"hacs"}


@WITH_JQ
def test_a_complete_release_verifies_with_every_check_of_the_step(
    tmp_path: Path,
) -> None:
    done = verify(tmp_path)

    assert_verified(done)
    assert done.summary == (
        f"### The release {TAG}\n"
        "- ✔ The release is immutable.\n"
        f"- ✔ Its commit {COMMIT} is signed.\n"
        f"- ✔ The tag {TAG} is signed by the release workflow.\n"
        "- ✔ The bundle of the provenance is attached.\n"
        "- ✔ provenance.intoto.jsonl holds the signed statement of the bundle.\n"
        "- ✔ The SBOM is attached.\n"
        "- ✔ The SBOM as CycloneDX is attached.\n"
        f"- ✔ r.spdx.json describes r {VERSION}, what the release ships.\n"
        f"- ✔ r.cdx.json describes r {VERSION}, what the release ships.\n"
        "- ✔ r.cdx.json carries the signed provenance of the isolated build.\n"
        "- ✔ r.spdx.json carries the signed provenance of the isolated build.\n"
        f"The release {TAG} verifies.\n"
    )
    # The bundle and the statement are what the others are checked with. Each asset is
    # checked twice: in GitHub, and with the bundle that a user gets with the release.
    signer = "--signer-workflow o/r/.github/workflows/build-release.yml"
    assert re.fullmatch(GITSIGN_DOWNLOAD, done.commands[3])
    assert done.commands[:3] + done.commands[4:] == [
        f"api repos/o/r/releases/tags/{TAG}",
        f"api repos/o/r/commits/{TAG} --jq .sha",
        SIGNED_COMMIT,
        f"release download {TAG}",
        *[
            f"attestation verify {asset} --repo o/r {signer}{TRUSTED_RUN}{bundle}"
            for asset in ("r.cdx.json", "r.spdx.json")
            for bundle in ("", " --bundle provenance.sigstore.json")
        ],
    ]
    # The tag is checked as a user would, against the identity of the release workflow.
    assert (
        f"gitsign verify-tag {TAG} --certificate-identity"
        " https://github.com/o/r/.github/workflows/release.yml@refs/heads/main"
        " --certificate-oidc-issuer https://token.actions.githubusercontent.com"
    ) in done.stubbed


@WITH_JQ
def test_the_verification_takes_the_latest_release_when_no_tag_is_named(
    tmp_path: Path,
) -> None:
    done = verify(tmp_path, named=False)

    assert_verified(done)
    assert done.commands[:2] == [
        "release view --json tagName --jq .tagName",
        f"api repos/o/r/releases/tags/{TAG}",
    ]


@WITH_JQ
def test_a_repository_without_a_release_has_nothing_to_verify(tmp_path: Path) -> None:
    done = verify(
        tmp_path,
        named=False,
        answers=[
            exact(
                "release view --json tagName --jq .tagName",
                code=1,
                err="release not found\n",
            )
        ],
    )

    assert done.returncode == 0, done.stdout + done.stderr
    assert "The repository has no release yet.\n" in done.stdout
    assert done.summary == "The repository has no release yet.\n"
    assert len(done.commands) == 1


@WITH_JQ
@pytest.mark.parametrize(("change", "line"), PASSES.values(), ids=list(PASSES))
def test_what_a_complete_release_attaches_and_delivers_verifies(
    tmp_path: Path, change: dict[str, Any], line: str
) -> None:
    done = verify(tmp_path, **change)

    assert_verified(done, change.get("tag", TAG))
    assert f"- ✔ {line}\n" in done.summary, done.summary


@WITH_JQ
@pytest.mark.parametrize(("change", "problem"), PROBLEMS.values(), ids=list(PROBLEMS))
def test_a_release_with_a_problem_fails_and_names_it(
    tmp_path: Path, change: dict[str, Any], problem: str
) -> None:
    assert_one_problem(verify(tmp_path, **change), problem, change.get("tag", TAG))


@WITH_JQ
def test_a_draft_ends_the_verification_before_anything_is_downloaded(
    tmp_path: Path,
) -> None:
    done = verify(tmp_path, **PROBLEMS["a draft"][0])

    assert done.commands == [f"api repos/o/r/releases/tags/{TAG}"]
    assert done.stubbed == []


@WITH_JQ
def test_a_gitsign_with_another_checksum_never_runs(tmp_path: Path) -> None:
    done = verify(tmp_path, pinned="0" * 64)

    assert [call for call in done.stubbed if call.startswith("gitsign ")] == []
    # And nothing comes after it: the run has already failed for what it can't check.
    assert not done.called(f"release download {TAG}")


@WITH_JQ
def test_a_download_of_gitsign_that_github_fails_for_a_while_is_tried_again(
    tmp_path: Path,
) -> None:
    # GitHub answered 504 for a while on 8 November 2026.
    done = verify(tmp_path, downloads=(1, 1, 1, 0))

    assert done.returncode == 0, done.stdout + done.stderr
    assert len(done.called(GITSIGN_DOWNLOAD)) == 4
    assert [call for call in done.stubbed if call.startswith("sleep ")][:3] == [
        "sleep 10",
        "sleep 20",
        "sleep 40",
    ]
    assert any(call.startswith("gitsign verify-tag ") for call in done.stubbed)


@WITH_JQ
def test_a_problem_that_ends_the_verification_counts_those_found_before_it(
    tmp_path: Path,
) -> None:
    done = verify(tmp_path, release={"immutable": False}, fetched=1)

    assert done.returncode == 1, done.stdout + done.stderr
    assert done.stdout.count("::error::") == 2, done.stdout
    assert f"The release {TAG} has 2 problem(s).\n" in done.summary, done.summary


@WITH_JQ
def test_a_release_without_the_bundle_is_still_checked_in_github(
    tmp_path: Path,
) -> None:
    done = verify(tmp_path, **PROBLEMS["no bundle of the provenance"][0])

    # Once for each asset, without the bundle that the release doesn't have.
    checks = done.called("attestation verify ")
    assert len(checks) == 2, checks
    assert not [check for check in checks if "--bundle" in check]


@WITH_JQ
def test_a_release_may_come_without_the_statement_of_its_bundle(tmp_path: Path) -> None:
    done = verify(tmp_path, assets={"provenance.intoto.jsonl": None})

    assert_verified(done)
    assert "provenance.intoto.jsonl" not in done.summary


@WITH_JQ
def test_an_sbom_that_names_the_release_only_as_a_dependency_fails(
    tmp_path: Path,
) -> None:
    # The document describes the folder of the repository, and the release is one of
    # its packages: not what the release ships.
    done = verify(
        tmp_path,
        assets={
            "r.spdx.json": json.dumps(
                {
                    "packages": [
                        {"SPDXID": "SPDXRef-a", "name": "r", "versionInfo": VERSION},
                        {"SPDXID": "SPDXRef-b", "name": "workspace"},
                    ],
                    "relationships": [
                        {
                            "spdxElementId": "SPDXRef-DOCUMENT",
                            "relationshipType": "DESCRIBES",
                            "relatedSpdxElement": "SPDXRef-b",
                        }
                    ],
                }
            )
        },
    )

    assert_one_problem(
        done, f"r.spdx.json doesn't describe r {VERSION}, what the release ships."
    )


@WITH_JQ
@pytest.mark.parametrize(
    ("change", "accepted", "problem"), OLDER_RELEASE.values(), ids=list(OLDER_RELEASE)
)
def test_only_the_weekly_run_accepts_what_an_older_release_lacks(
    tmp_path: Path, change: dict[str, Any], accepted: str, problem: str
) -> None:
    weekly = verify(tmp_path / "weekly", weekly=True, **change)
    assert_verified(weekly)
    assert accepted in weekly.stdout + weekly.summary

    assert_one_problem(verify(tmp_path / "named", **change), problem)


@WITH_JQ
@pytest.mark.parametrize("case", WEEKLY_PROBLEMS)
def test_the_weekly_run_finds_a_problem_in_a_release_however_old(
    tmp_path: Path, case: str
) -> None:
    change, problem = PROBLEMS[case]
    assert_one_problem(verify(tmp_path, weekly=True, **change), problem)


@WITH_JQ
def test_the_weekly_run_waits_for_the_next_release_after_one_made_before_the_blueprint(
    tmp_path: Path,
) -> None:
    done = verify(tmp_path, weekly=True, release={"assets": [{"name": "r.zip"}]})

    assert done.returncode == 0, done.stdout + done.stderr
    assert done.summary == (
        f"### The release {TAG}\n"
        f"The release {TAG} was made before the release workflow of the blueprint; the"
        " next one is verified in full.\n"
    )
    assert done.commands == [f"api repos/o/r/releases/tags/{TAG}"]


@WITH_JQ
def test_a_run_that_names_the_tag_verifies_such_a_release_in_full(
    tmp_path: Path,
) -> None:
    done = verify(tmp_path, release={"assets": [{"name": "r.zip"}]})

    assert_verified(done)
    assert "- ✔ The release is immutable.\n" in done.summary


@WITH_JQ
def test_the_image_of_a_repository_with_capitals_has_the_lower_case_name_of_ghcr(
    tmp_path: Path,
) -> None:
    done = verify(tmp_path, repository="Dennis-Otto/Demo", publish_to="ghcr")

    assert_verified(done)
    image = f"ghcr.io/dennis-otto/demo:{VERSION}"
    assert (
        f"- ✔ {image} carries the signed provenance of its isolated build.\n"
        in done.summary
    )
    # The SBOMs and the provenance keep the name of the repository as it is.
    assert f"- ✔ Demo.spdx.json describes Demo {VERSION}" in done.summary


@WITH_JQ
def test_the_verification_asks_npm_for_the_package_named_in_the_tarball(
    tmp_path: Path,
) -> None:
    done = verify(tmp_path, **NPM)

    assert f"npm view demo@{VERSION} dist.integrity" in done.stubbed


@WITH_JQ
def test_the_verification_waits_for_the_app_store_to_show_a_new_package(
    tmp_path: Path,
) -> None:
    page = (tmp_path / "served" / served_as(APP_PAGE)).as_posix()
    later = tmp_path / "later"
    later.write_text(OFFERED, encoding="utf-8")

    # The page shows the package after the first wait.
    done = verify(
        tmp_path,
        **{**NEXTCLOUD, "served": {APP_PAGE: NOT_YET_OFFERED}},
        stubs={"sleep": recording("sleep", f'cp "{later.as_posix()}" "{page}"')},
    )

    assert_verified(done)
    assert done.stubbed.count("sleep 30") == 1, done.stubbed


@WITH_JQ
def test_the_verification_gives_the_app_store_six_tries(tmp_path: Path) -> None:
    done = verify(tmp_path, **{**NEXTCLOUD, "served": {APP_PAGE: NOT_YET_OFFERED}})

    assert done.returncode == 1, done.stdout + done.stderr
    # No wait after the last try.
    assert done.stubbed.count("sleep 30") == 5, done.stubbed
    tries = [
        call for call in done.stubbed if call.startswith("curl ") and APP_PAGE in call
    ]
    assert len(tries) == 6, tries


@WITH_JQ
def test_a_prerelease_of_an_action_doesnt_ask_for_the_major_tag(tmp_path: Path) -> None:
    done = verify(tmp_path, publish_to="github-action", tag="v1.3.0-beta.1")

    assert_verified(done, "v1.3.0-beta.1")
    assert not done.called("api repos/o/r/commits/v1 ")
