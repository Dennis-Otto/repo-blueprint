"""The checklist of a repository: the steps outside the API, and which are done."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from blueprint.github import Api
from blueprint.settings import Settings, check

RELEASE_APP = "dennis-otto-release-automation"
REUSE_API = "https://api.reuse.software/status/github.com/"
BEST_PRACTICES = "https://www.bestpractices.dev"
# A badge of OpenSSF Best Practices in a README: of the metal series, "badge", or of
# the OSPS Baseline, "baseline", with the number of the project.
BADGE = re.compile(r"bestpractices\.dev/projects/(\d+)/(badge|baseline)")
# The button of each form of bestpractices.dev that reads .bestpractices.json anew.
SAVE = "Save (and continue) 🤖"


@dataclass(frozen=True)
class Step:
    """A step of the set-up; done is None when no API can tell."""

    text: str
    done: bool | None
    how: str = ""


def reuse_compliant(
    repo: str, opener: Callable[[str], Any] = urllib.request.urlopen
) -> bool:
    try:
        with opener(REUSE_API + repo) as response:
            return bool(json.load(response).get("status") == "compliant")
    except (urllib.error.URLError, ValueError, OSError):
        return False


def best_practices(readme: str) -> list[Step]:
    """The badges of OpenSSF Best Practices and of the OSPS Baseline in the README.
    The form of each level proposes the answers of .bestpractices.json, and a project
    that shows one badge has its number for the other."""
    badges = {series: number for number, series in BADGE.findall(readme)}
    number = badges.get("badge") or badges.get("baseline")
    take = (
        f"On each level, press '{SAVE}' to take in the answers that"
        " .bestpractices.json proposes, and answer the rest."
    )
    steps: list[Step] = []
    for series, name, level in (
        ("badge", "Best Practices", "passing"),
        ("baseline", "Baseline", "baseline-1"),
    ):
        if number:
            how = (
                f"{BEST_PRACTICES}/en/projects/{number}/{level}/edit\n{take}\n"
                f"Then add its badge to the README: [![OpenSSF {name}]"
                f"({BEST_PRACTICES}/projects/{number}/{series})]"
                f"({BEST_PRACTICES}/projects/{number})"
            )
        else:
            how = (
                "Add the project with the URL of the repository: "
                f"{BEST_PRACTICES}/en/projects/new\n{take}\n"
                "Then add its badges to the README, as the project page shows them."
            )
        steps.append(Step(f"OpenSSF {name} badge in the README", series in badges, how))
    return steps


def checklist(
    api: Api,
    repo: str,
    settings: Settings,
    root: Path,
    reuse: Callable[[str], bool] | None = None,
) -> list[Step]:
    owner, name = repo.split("/", 1)
    data = api.graphql(
        f'{{ repository(owner: "{owner}", name: "{name}") {{ usesCustomOpenGraphImage }} }}'
    )
    readme = (
        (root / "README.md").read_text(encoding="utf-8")
        if (root / "README.md").exists()
        else ""
    )
    drift = check(api, repo, settings)
    # What a person sets, which the API can't: the secrets and the files that the
    # community profile counts, each a step of its own.
    secrets_missing = [item for item in drift if item.setting.startswith("secret ")]
    community = [item for item in drift if item.setting == "community profile"]
    target = settings.variables.get("PUBLISH_TO", "none")
    steps = [
        Step(
            "Settings as code applied",
            all(item.manual for item in drift),
            "python3 blueprint.py settings apply",
        ),
        Step(
            "Secrets of the environments set",
            not secrets_missing,
            "\n".join(item.manual for item in secrets_missing),
        ),
        Step(
            "Community profile complete (100 %)",
            not community,
            "\n".join(item.manual for item in community),
        ),
        Step(
            "Release app installed on the repository",
            None,
            f"https://github.com/apps/{RELEASE_APP}/installations/new",
        ),
        Step(
            "Settings → General → Issues: 'Auto-close issues with merged linked pull requests' off "
            "(the issue assistant closes them with the release)",
            None,
            f"https://github.com/{repo}/settings",
        ),
    ]
    if (root / ".github/FUNDING.yml").exists():
        steps.append(
            Step(
                "Settings → General → Features: Sponsorships on",
                None,
                f"https://github.com/{repo}/settings",
            )
        )
    steps += [
        Step(
            "Social preview uploaded (bash scripts/social-preview.sh renders it)",
            bool(data["repository"]["usesCustomOpenGraphImage"]),
            f"https://github.com/{repo}/settings",
        ),
        *best_practices(readme),
        Step(
            "Registered with the REUSE API, for its badge",
            (reuse or reuse_compliant)(repo),
            "https://api.reuse.software/register",
        ),
    ]
    delivery = {
        "pypi": (
            "Trusted publisher on PyPI: workflow release.yml, environment pypi",
            "https://pypi.org/manage/account/publishing/",
        ),
        "npm": (
            "Trusted publisher on npm: workflow release.yml, environment npm",
            "https://www.npmjs.com/settings/~/packages",
        ),
        "ghcr": (
            "After the first release: the package of the image is public",
            f"https://github.com/{repo}/pkgs/container/{name}",
        ),
        "hacs": (
            "Submitted to the HACS default repositories",
            "https://github.com/hacs/default",
        ),
        "nextcloud-appstore": (
            "App certificate requested and the app registered in the App Store",
            "Request the certificate: "
            "https://nextcloudappstore.readthedocs.io/en/latest/developer.html\n"
            "then run Actions -> Register the app with the id of the app.",
        ),
    }
    if target in delivery:
        text, how = delivery[target]
        steps.append(Step(text, None, how))
    return steps


def describe_steps(steps: list[Step]) -> str:
    marks = {True: "✔", False: "✘", None: "·"}
    lines = []
    for step in steps:
        lines.append(f"  {marks[step.done]} {step.text}")
        if step.done is not True and step.how:
            lines += [f"      {line}" for line in step.how.splitlines()]
    return "\n".join(lines)
