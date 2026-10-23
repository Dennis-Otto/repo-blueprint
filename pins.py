#!/usr/bin/env python3
"""The tools that the workflows of the blueprint download, pinned by version and sha256.

The workflows and .github/sign-tag.sh download gitsign, Infection, krankerl,
Nextcloud and syft at the version below a line "# renovate:", and check each
download against the sha256 on the line after the version. Renovate moves the
version, but can't know the checksum of the new release. .github/pins.toml records the address of each
download and the version and sha256 that the files pin; after Renovate moved a
version, it runs

    python3 pins.py           download each version that moved, and write its sha256
                              beside the version and into .github/pins.toml
    python3 pins.py --check   the pins that differ from .github/pins.toml, without a
                              download; tests/test_pins.py fails on them

so that the update merges on its own like any other, and the blueprint bot brings it
to every repository.
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
FILES = (".github/*.sh", ".github/workflows/*.yml")
# A download, pinned below its line "# renovate:": the version as in YAML (NAME: 1.2.3)
# or in the shell (name=1.2.3), and the sha256 on the next line in the same form.
PIN = re.compile(
    r"# renovate: datasource=\S+ depName=(?P<dep>\S+)[^\n]*\n"
    r"[ \t]*(?P<name>[\w-]+)(?:: |=)\"?(?P<version>[^\"\s]+)\"?[ \t]*\n"
    r"[ \t]*[\w-]+(?:: |=)\"?(?P<sha256>[0-9a-f]{64})\"?[ \t]*$",
    re.MULTILINE,
)
SHA256 = re.compile(r"[0-9a-f]{64}")
HEADER = """\
# The tools that the workflows and .github/sign-tag.sh download and check by their
# sha256, each pinned below a line "# renovate:": the address of the download, in which
# {version} stands for the version, and the version and sha256 that the files pin.
# Renovate moves a version, and python3 pins.py then writes the sha256 of the new
# release beside it and here. pins.py keeps this file; add a new download by hand.
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
class Pin:
    """A download that a file pins, and where its sha256 is in the file."""

    path: str
    dep: str
    name: str
    version: str
    sha256: str
    start: int


def load_record(root: Path) -> dict[str, Download]:
    """The downloads of .github/pins.toml, by the name of the dependency."""
    data: dict[str, Any] = tomllib.loads((root / RECORD).read_bytes().decode("utf-8"))
    if set(data) != {"download"} or not isinstance(data["download"], dict):
        raise PinError([f'{RECORD} has only tables [download."OWNER/NAME"]'])
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


def render_record(record: dict[str, Download]) -> str:
    """The text of .github/pins.toml."""
    tables = [
        f"\n[download.{json.dumps(dep)}]\n"
        f"url = {json.dumps(download.url)}\n"
        f"version = {json.dumps(download.version)}\n"
        f"sha256 = {json.dumps(download.sha256)}\n"
        for dep, download in record.items()
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
    return problems


def download(
    url: str,
    opener: Callable[..., Any] = urllib.request.urlopen,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """The sha256 of the file at url."""
    attempt = 1
    while True:
        digest = hashlib.sha256()
        try:
            request = urllib.request.Request(url, headers={"User-Agent": AGENT})
            with opener(request, timeout=300) as response:
                while chunk := response.read(1 << 20):
                    digest.update(chunk)
            return digest.hexdigest()
        except OSError as error:
            if isinstance(error, urllib.error.HTTPError):
                # The error is the answer too, and holds its body until it is closed.
                error.close()
            if attempt == TRIES:
                raise PinError([f"{url} could not be downloaded: {error}"]) from error
            sleep(attempt * 10)
            attempt += 1


def update(root: Path, fetch: Fetch = download) -> list[str]:
    """Write the sha256 of each version that moved; what it wrote, a line each."""
    record = load_record(root)
    pins = find_pins(root)
    problems = mismatches(record, pins)
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
    for path, text in texts.items():
        (root / path).write_bytes(text.encode("utf-8"))
    text = render_record(record)
    if (root / RECORD).read_bytes().decode("utf-8") != text:
        (root / RECORD).write_bytes(text.encode("utf-8"))
        done.append(f"{RECORD}: {len(record)} downloads")
    return done


def main(
    argv: Sequence[str] | None = None, root: Path = Path(), fetch: Fetch = download
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
        done = update(root, fetch)
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
