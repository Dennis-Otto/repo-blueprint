#!/usr/bin/env python3
"""The tools that the workflows of the blueprint download, pinned by version and sha256.

The workflows and the scripts of .github download gitsign, gitleaks, Infection,
krankerl, lychee, Nextcloud and syft, and the hooks of every website Mermaid, at the
version below a line "# renovate:", and check each download against the sha256 on the
line after the version. Renovate moves the
version, but can't know the checksum of the new release. .github/pins.toml records the address of each
download and the version and sha256 that the files pin; after Renovate moved a
version, it runs

    python3 pins.py           download each version that moved, and write its sha256
                              beside the version and into .github/pins.toml
    python3 pins.py --check   the pins that differ from .github/pins.toml, without a
                              download; tests/test_pins.py fails on them

so that the update merges on its own like any other, and the blueprint bot brings it
to every repository.

The record also keeps the version of the package of npm that an action runs, such as
markdownlint-cli2 of DavidAnson/markdownlint-cli2-action, from the package.json of the
action at the commit that the workflows pin, and the image of that package, which the
scripts and the workflows run: pins.py reads the version anew once Renovate moved the
commit, and --check names each image that runs another version than the action, so
that the check lint and scripts/check.sh can't come to disagree on a rule.
https://github.com/Dennis-Otto/repo-blueprint
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import tomllib
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

RECORD = ".github/pins.toml"
# The files of Renovate's custom manager that pin a download.
FILES = (
    ".github/*.sh",
    ".github/workflows/*.yml",
    ".github/mkdocs-blueprint-pins.toml",
)
# A download, pinned below its line "# renovate:": the version as in YAML (NAME: 1.2.3),
# in the shell (name=1.2.3) or in TOML (name = "1.2.3"), and the sha256 on the next
# line in the same form.
PIN = re.compile(
    r"# renovate: datasource=\S+ depName=(?P<dep>\S+)[^\n]*\n"
    r"[ \t]*(?P<name>[\w-]+)(?:: | ?= ?)\"?(?P<version>[^\"\s]+)\"?[ \t]*\n"
    r"[ \t]*[\w-]+(?:: | ?= ?)\"?(?P<sha256>[0-9a-f]{64})\"?[ \t]*$",
    re.MULTILINE,
)
SHA256 = re.compile(r"[0-9a-f]{64}")
COMMIT = re.compile(r"[0-9a-f]{40}")
# The version of a package that an action runs, exact, as the action bundles it.
EXACT = re.compile(r"\d+\.\d+\.\d+(?:-[\w.]+)?")
# An action that a workflow pins to a commit.
USES = re.compile(r"uses: (?P<dep>[\w.-]+/[\w.-]+)@(?P<commit>[0-9a-f]{40})\b")
# The files that run an image by tag and digest, as Renovate's custom manager finds it.
IMAGE_FILES = (".github/*.sh", ".github/workflows/*.yml", "scripts/*.sh")
# The package.json of an action at a commit, from which pins.py reads its version.
PACKAGE_JSON = "https://raw.githubusercontent.com/{dep}/{commit}/package.json"
HEADER = """\
# The tools that the workflows, the scripts and the websites of .github download and
# check by their sha256, each pinned below a line "# renovate:": the address of the
# download, in which {version} stands for the version, and the version and sha256
# that the files pin. Renovate moves a version, and python3 pins.py then writes the
# sha256 of the new release beside it and here. pins.py keeps this file; add a new
# download by hand.
# Each bundle is an action that the workflows pin to a commit and the package of npm
# that it runs, with the version that its package.json names at that commit, which
# python3 pins.py reads anew once Renovate moved the commit; the image of the package
# that the scripts and the workflows run must have the same version.
# https://github.com/Dennis-Otto/repo-blueprint
"""
# Each download tries three times, 10 and 20 seconds apart, as the workflows do.
TRIES = 3
AGENT = "pins.py of https://github.com/Dennis-Otto/repo-blueprint"

Fetch = Callable[[str], str]


class PinError(Exception):
    """What keeps pins.py from writing the checksums, one problem a line."""

    def __init__(self, problems: Sequence[str]) -> None:
        super().__init__("\n".join(problems))
        self.problems = list(problems)


@dataclass(frozen=True)
class Download:
    """The address of a download, and the version and sha256 that the files pin."""

    url: str
    version: str
    sha256: str


@dataclass(frozen=True)
class Bundle:
    """An action pinned to a commit, the package of npm that it runs there with its
    version, and the image of that package, which must run the same version."""

    commit: str
    package: str
    version: str
    image: str


@dataclass(frozen=True)
class Use:
    """An action that a workflow pins to a commit."""

    path: str
    dep: str
    commit: str


@dataclass(frozen=True)
class Image:
    """An image that a script or a workflow runs, by its tag without a v."""

    path: str
    name: str
    version: str


@dataclass(frozen=True)
class Pin:
    """A download that a file pins, and where its sha256 is in the file."""

    path: str
    dep: str
    name: str
    version: str
    sha256: str
    start: int


def read_record(root: Path) -> dict[str, Any]:
    """The tables of .github/pins.toml."""
    data: dict[str, Any] = tomllib.loads((root / RECORD).read_bytes().decode("utf-8"))
    if (
        "download" not in data
        or set(data) - {"download", "bundle"}
        or not all(isinstance(table, dict) for table in data.values())
    ):
        raise PinError(
            [
                f'{RECORD} has only tables [download."OWNER/NAME"] and '
                '[bundle."OWNER/ACTION"]'
            ]
        )
    return data


def load_record(root: Path) -> dict[str, Download]:
    """The downloads of .github/pins.toml, by the name of the dependency."""
    data = read_record(root)
    record = {}
    for dep, entry in data["download"].items():
        if not (
            isinstance(entry, dict)
            and set(entry) == {"url", "version", "sha256"}
            and all(isinstance(value, str) for value in entry.values())
            and entry["url"].startswith("https://")
            and "{version}" in entry["url"]
            and SHA256.fullmatch(entry["sha256"])
        ):
            raise PinError(
                [
                    f"{RECORD}: {dep} needs a url of https:// with {{version}} in it, "
                    "a version and a sha256 of 64 hex digits, and nothing else"
                ]
            )
        record[dep] = Download(entry["url"], entry["version"], entry["sha256"])
    return record


def load_bundles(root: Path) -> dict[str, Bundle]:
    """The bundles of .github/pins.toml, by the name of the action."""
    bundles = {}
    for dep, entry in read_record(root).get("bundle", {}).items():
        if not (
            isinstance(entry, dict)
            and set(entry) == {"commit", "package", "version", "image"}
            and all(isinstance(value, str) and value for value in entry.values())
            and COMMIT.fullmatch(entry["commit"])
            and EXACT.fullmatch(entry["version"])
        ):
            raise PinError(
                [
                    f"{RECORD}: {dep} needs a commit of 40 hex digits, the package "
                    "that it runs, its exact version and the image of that package, "
                    "and nothing else"
                ]
            )
        bundles[dep] = Bundle(
            entry["commit"], entry["package"], entry["version"], entry["image"]
        )
    return bundles


def render_record(
    record: dict[str, Download], bundles: dict[str, Bundle] | None = None
) -> str:
    """The text of .github/pins.toml."""
    tables = [
        f"\n[download.{json.dumps(dep)}]\n"
        f"url = {json.dumps(download.url)}\n"
        f"version = {json.dumps(download.version)}\n"
        f"sha256 = {json.dumps(download.sha256)}\n"
        for dep, download in record.items()
    ]
    tables += [
        f"\n[bundle.{json.dumps(dep)}]\n"
        f"commit = {json.dumps(bundle.commit)}\n"
        f"package = {json.dumps(bundle.package)}\n"
        f"version = {json.dumps(bundle.version)}\n"
        f"image = {json.dumps(bundle.image)}\n"
        for dep, bundle in (bundles or {}).items()
    ]
    return HEADER + "".join(tables)


def find_pins(root: Path) -> list[Pin]:
    """Every download that the workflows and the scripts pin, file by file."""
    pins = []
    for pattern in FILES:
        for path in sorted(root.glob(pattern)):
            text = path.read_bytes().decode("utf-8")
            for found in PIN.finditer(text):
                pins.append(
                    Pin(
                        path.relative_to(root).as_posix(),
                        found["dep"],
                        found["name"],
                        found["version"],
                        found["sha256"],
                        found.start("sha256"),
                    )
                )
    return pins


def find_uses(root: Path, deps: set[str]) -> list[Use]:
    """Every commit to which the workflows pin one of the actions, file by file."""
    uses = []
    for path in sorted(root.glob(".github/workflows/*.yml")):
        text = path.read_bytes().decode("utf-8")
        for found in USES.finditer(text):
            if found["dep"] in deps:
                uses.append(
                    Use(
                        path.relative_to(root).as_posix(), found["dep"], found["commit"]
                    )
                )
    return uses


def find_images(root: Path, names: set[str]) -> list[Image]:
    """Every tag of one of the images that the scripts and the workflows run."""
    images = []
    for pattern in IMAGE_FILES:
        for path in sorted(root.glob(pattern)):
            text = path.read_bytes().decode("utf-8")
            for name in sorted(names):
                tag = re.compile(
                    rf"(?<![\w./-]){re.escape(name)}:v?(?P<version>[^@\s\"']+)"
                    r"@sha256:[0-9a-f]{64}"
                )
                images += [
                    Image(path.relative_to(root).as_posix(), name, found["version"])
                    for found in tag.finditer(text)
                ]
    return images


def commits(uses: Sequence[Use]) -> dict[str, list[str]]:
    """The commits to which the workflows pin each action, in the order of the files."""
    pinned: dict[str, list[str]] = {}
    for use in uses:
        if use.commit not in pinned.setdefault(use.dep, []):
            pinned[use.dep].append(use.commit)
    return pinned


def bundle_mismatches(bundles: dict[str, Bundle], uses: Sequence[Use]) -> list[str]:
    """What a bundle needs before pins.py can read the version of its package."""
    pinned = commits(uses)
    problems = []
    for dep in bundles:
        found = pinned.get(dep, [])
        if not found:
            problems.append(f"{RECORD}: no workflow pins the action {dep}; remove it")
        elif len(found) > 1:
            problems.append(
                f"The workflows pin {dep} at {' and '.join(found)}: give each the "
                "same commit"
            )
    return problems


def bundle_problems(root: Path, bundles: dict[str, Bundle]) -> list[str]:
    """Each action whose commit moved, and each image that runs another version of
    its package than the action, without a download."""
    uses = find_uses(root, set(bundles))
    problems = bundle_mismatches(bundles, uses)
    pinned = commits(uses)
    images = find_images(root, {bundle.image for bundle in bundles.values()})
    for dep, bundle in bundles.items():
        if len(pinned.get(dep, [])) != 1:
            continue
        if pinned[dep][0] != bundle.commit:
            problems.append(
                f"{RECORD}: the workflows pin {dep} at {pinned[dep][0]}, the record "
                f"at {bundle.commit}; python3 pins.py reads the version of "
                f"{bundle.package} that it runs"
            )
            continue
        runs = [image for image in images if image.name == bundle.image]
        if not runs:
            problems.append(
                f"{RECORD}: no script or workflow runs the image {bundle.image} of "
                f"{dep}; remove it"
            )
        problems += [
            f"{image.path}: the image {bundle.image} runs {bundle.package} "
            f"{image.version}, the action {dep} {bundle.version}: give the image the "
            f"tag of {bundle.version} and its digest, which Renovate brings in the "
            "pull request that moves the action"
            for image in runs
            if image.version != bundle.version
        ]
    return problems


def versions(pins: Sequence[Pin]) -> dict[str, list[str]]:
    """The versions that the files pin, by dependency, in the order of the files."""
    pinned: dict[str, list[str]] = {}
    for pin in pins:
        if pin.version not in pinned.setdefault(pin.dep, []):
            pinned[pin.dep].append(pin.version)
    return pinned


def mismatches(record: dict[str, Download], pins: Sequence[Pin]) -> list[str]:
    """What a download needs before pins.py can write its checksum."""
    pinned = versions(pins)
    problems = [
        f"{RECORD}: no file pins {dep}; remove it"
        for dep in record
        if dep not in pinned
    ]
    for dep, found in pinned.items():
        if dep not in record:
            problems.append(
                f"{RECORD} has no download {dep}: add its url, version and sha256"
            )
        elif len(found) > 1:
            problems.append(
                f"The files pin {dep} at {' and '.join(found)}: give each the same version"
            )
    return problems


def check(root: Path) -> list[str]:
    """The pins that differ from .github/pins.toml, without a download."""
    record = load_record(root)
    pins = find_pins(root)
    problems = mismatches(record, pins)
    pinned = versions(pins)
    for pin in pins:
        download = record.get(pin.dep)
        if download is None or len(pinned[pin.dep]) > 1:
            continue
        if pin.version != download.version:
            problems.append(
                f"{pin.path}: {pin.dep} {pin.version} has the sha256 of "
                f"{download.version}; python3 pins.py writes the right one"
            )
        elif pin.sha256 != download.sha256:
            problems.append(
                f"{pin.path}: the sha256 of {pin.dep} {pin.version} differs from "
                f"{RECORD}; python3 pins.py writes the right one"
            )
    return problems + bundle_problems(root, load_bundles(root))


def get[T](
    url: str,
    consume: Callable[[Any], T],
    opener: Callable[..., Any] = urllib.request.urlopen,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """What consume makes of the answer for url."""
    attempt = 1
    while True:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": AGENT})
            with opener(request, timeout=300) as response:
                return consume(response)
        except OSError as error:
            if isinstance(error, urllib.error.HTTPError):
                # The error is the answer too, and holds its body until it is closed.
                error.close()
            if attempt == TRIES:
                raise PinError([f"{url} could not be downloaded: {error}"]) from error
            sleep(attempt * 10)
            attempt += 1


def download(
    url: str,
    opener: Callable[..., Any] = urllib.request.urlopen,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """The sha256 of the file at url."""

    def hashed(response: Any) -> str:
        digest = hashlib.sha256()
        while chunk := response.read(1 << 20):
            digest.update(chunk)
        return digest.hexdigest()

    return get(url, hashed, opener, sleep)


def read(
    url: str,
    opener: Callable[..., Any] = urllib.request.urlopen,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """The text of the file at url, of at most a MiB."""
    data: bytes = get(url, lambda response: response.read(1 << 20), opener, sleep)
    return data.decode("utf-8", errors="replace")


def bundled(url: str, package: str, read: Fetch) -> str:
    """The exact version of package among the dependencies of the package.json at url."""
    try:
        version = json.loads(read(url))["dependencies"][package]
    except (ValueError, KeyError, TypeError):
        version = None
    if not (isinstance(version, str) and EXACT.fullmatch(version)):
        raise PinError([f"{url} names no exact version of {package} that it runs"])
    return version


def update(root: Path, fetch: Fetch = download, read: Fetch = read) -> list[str]:
    """Write the sha256 of each version that moved, and the version of the package of
    each action whose commit moved; what it wrote, a line each."""
    record = load_record(root)
    bundles = load_bundles(root)
    pins = find_pins(root)
    uses = find_uses(root, set(bundles))
    problems = mismatches(record, pins) + bundle_mismatches(bundles, uses)
    if problems:
        raise PinError(problems)
    done = []
    pinned = versions(pins)
    for dep, entry in record.items():
        version = pinned[dep][0]
        if version != entry.version:
            sha256 = fetch(entry.url.replace("{version}", version))
            record[dep] = replace(entry, version=version, sha256=sha256)
            done.append(f"{dep} {version}: sha256 {sha256}")
    texts: dict[str, str] = {}
    for pin in pins:
        sha256 = record[pin.dep].sha256
        if pin.sha256 != sha256:
            if pin.path not in texts:
                texts[pin.path] = (root / pin.path).read_bytes().decode("utf-8")
            text = texts[pin.path]
            texts[pin.path] = text[: pin.start] + sha256 + text[pin.start + 64 :]
            done.append(f"{pin.path}: the sha256 of {pin.dep} {pin.version}")
    pinned = commits(uses)
    for dep, bundle in bundles.items():
        commit = pinned[dep][0]
        if commit != bundle.commit:
            url = PACKAGE_JSON.format(dep=dep, commit=commit)
            version = bundled(url, bundle.package, read)
            bundles[dep] = replace(bundle, commit=commit, version=version)
            done.append(f"{dep} {commit}: {bundle.package} {version}")
    for path, text in texts.items():
        (root / path).write_bytes(text.encode("utf-8"))
    text = render_record(record, bundles)
    if (root / RECORD).read_bytes().decode("utf-8") != text:
        (root / RECORD).write_bytes(text.encode("utf-8"))
        actions = f" and {len(bundles)} actions" if bundles else ""
        done.append(f"{RECORD}: {len(record)} downloads{actions}")
    return done


def main(
    argv: Sequence[str] | None = None,
    root: Path = Path(),
    fetch: Fetch = download,
    read: Fetch = read,
) -> int:
    parser = argparse.ArgumentParser(
        prog="pins.py",
        description="Write the sha256 of each tool whose version Renovate moved.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=f"only list the pins that differ from {RECORD}, without a download",
    )
    arguments = parser.parse_args(argv)
    try:
        if arguments.check:
            problems = check(root)
            for problem in problems:
                print(f"pins.py: {problem}", file=sys.stderr)
            if not problems:
                print(
                    f"Every pinned download has the sha256 of its version in {RECORD}."
                )
            return 1 if problems else 0
        done = update(root, fetch, read)
    except PinError as error:
        for problem in error.problems:
            print(f"pins.py: {problem}", file=sys.stderr)
        return 2
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        print(f"pins.py: {error}", file=sys.stderr)
        return 2
    print("\n".join(done) or "Every pinned download has the sha256 of its version.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
