"""Tests of the third-party notices of a release."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import blueprint

ROOT_ID = "SPDXRef-github-Dennis-Otto-demo-main"


def package(
    name: str, version: str, purl: str, license_name: str | None
) -> dict[str, object]:
    return {
        "SPDXID": f"SPDXRef-{name}",
        "name": name,
        "versionInfo": version,
        "licenseConcluded": license_name,
        "externalRefs": [{"referenceType": "purl", "referenceLocator": purl}],
    }


SBOM = {
    "sbom": {
        "packages": [
            {"SPDXID": ROOT_ID, "name": "com.github.Dennis-Otto/demo"},
            package("jinja2", "3.1.6", "pkg:pypi/jinja2@3.1.6", "BSD-3-Clause"),
            package("platformdirs", "4.12.3", "pkg:pypi/platformdirs@4.12.3", "MIT"),
            package(
                "nextcloud/ocp", "33.0.9", "pkg:composer/nextcloud/ocp@33.0.9", None
            ),
            package("checkout", "", "", "NOASSERTION"),
            package("attrs", "26.1.0", "pkg:pypi/attrs@26.1.0", "MIT"),
        ],
        "relationships": [
            {"relationshipType": "DESCRIBES", "relatedSpdxElement": ROOT_ID},
            {"relationshipType": "DEPENDS_ON", "relatedSpdxElement": "SPDXRef-jinja2"},
        ],
    }
}


def test_the_notices_group_the_components_by_license() -> None:
    notices = blueprint.third_party_notices("v1.2.0", SBOM)

    assert notices.startswith("# Third-party components\n\n")
    assert "at v1.2.0" in notices
    assert "com.github.Dennis-Otto/demo" not in notices
    headings = [line for line in notices.splitlines() if line.startswith("## ")]
    assert headings == [
        "## BSD-3-Clause",
        "## MIT",
        f"## {blueprint.UNNAMED}",
    ]
    mit = notices.split("## MIT", 1)[1].split("## ", 1)[0]
    assert mit.index("| attrs | 26.1.0 | pypi |") < mit.index("| platformdirs |")
    assert "| nextcloud/ocp | 33.0.9 | composer |" in notices
    assert "| checkout |  |  |" in notices


def test_a_plain_spdx_document_and_none_at_all() -> None:
    plain = blueprint.third_party_notices("v1.0.0", SBOM["sbom"])
    assert plain == blueprint.third_party_notices("v1.0.0", SBOM)
    assert blueprint.third_party_notices("v0.1.0", {"packages": []}).endswith(
        "The repository uses no third-party components.\n"
    )


def test_the_command_line_writes_the_notices(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sbom = tmp_path / "sbom.json"
    sbom.write_text(json.dumps(SBOM), encoding="utf-8")

    assert blueprint.main(["notices", "v1.2.0", str(sbom)]) == 0
    assert "## MIT" in capsys.readouterr().out
