"""Tests of the comparison of the uploaded social preview with the committed picture."""

from __future__ import annotations

import io
import json
import re
import subprocess
import urllib.error
from collections.abc import Callable, Sequence
from email.message import Message
from pathlib import Path
from types import TracebackType
from typing import Any

import pytest

from blueprint.github import Api, GitHubError
from blueprint.social_preview import (
    HOST,
    LARGEST,
    PAUSE,
    PICTURE,
    PRIVATE,
    TIMEOUT,
    Preview,
    Unreadable,
    digest,
    download,
    preview,
    settings_page,
)

REPO = "Dennis-Otto/demo"
UPLOAD = f"https://{HOST}/1408952044/ffa0a76a-863b-4bfc-8b83-64aaf7c8e8f4"
DRAWN = "https://opengraph.githubassets.com/1/Dennis-Otto/demo"
PNG = b"\x89PNG\r\n\x1a\n the picture"


class Response:
    """An answer of urlopen, which reads at most the bytes that it is asked for."""

    def __init__(self, data: bytes) -> None:
        self.data = data

    def __enter__(self) -> Response:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self.data if size < 0 else self.data[:size]


def serving(data: bytes, seen: list[tuple[str, float]]) -> Callable[..., Any]:
    def opener(url: str, timeout: float) -> Response:
        seen.append((url, timeout))
        return Response(data)

    return opener


def failing(error: OSError) -> Callable[..., Any]:
    def opener(url: str, timeout: float) -> Response:
        raise error

    return opener


def graphql(repository: dict[str, Any], queries: list[str], returncode: int = 0) -> Api:
    """GitHub's GraphQL, which knows the social preview of one repository: a public
    one unless the answer names another."""
    repository = {"isPrivate": False, **repository}

    def runner(
        arguments: Sequence[str], body: str | None
    ) -> subprocess.CompletedProcess[str]:
        assert list(arguments[:3]) == ["api", "graphql", "-f"]
        queries.append(arguments[3])
        answer = json.dumps({"data": {"repository": repository}})
        return subprocess.CompletedProcess(arguments, returncode, answer, "refused")

    return Api(runner)


def committed(root: Path, data: bytes = PNG) -> Path:
    path = root / PICTURE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return root


def test_the_upload_is_current_when_it_is_the_committed_picture_byte_for_byte(
    tmp_path: Path,
) -> None:
    queries: list[str] = []
    seen: list[tuple[str, float]] = []
    api = graphql(
        {"usesCustomOpenGraphImage": True, "openGraphImageUrl": UPLOAD}, queries
    )

    found = preview(api, REPO, committed(tmp_path), serving(PNG, seen))

    assert found == Preview(digest(PNG), True, digest(PNG))
    assert found.current
    assert seen == [(UPLOAD, TIMEOUT)]
    assert queries == [
        'query={ repository(owner: "Dennis-Otto", name: "demo") '
        "{ isPrivate usesCustomOpenGraphImage openGraphImageUrl } }"
    ]


@pytest.mark.parametrize("uploaded", [True, False])
def test_a_private_repository_shows_no_social_preview_to_compare(
    tmp_path: Path, uploaded: bool
) -> None:
    # GitHub shares the upload only from a public repository, and may serve the
    # upload of a private one to nobody without a token: nothing downloads it.
    seen: list[tuple[str, float]] = []
    api = graphql(
        {
            "isPrivate": True,
            "usesCustomOpenGraphImage": uploaded,
            "openGraphImageUrl": UPLOAD,
        },
        [],
    )

    found = preview(api, REPO, committed(tmp_path), serving(PNG, seen))

    assert found == Preview(digest(PNG), uploaded, public=False)
    assert not found.current
    assert seen == []
    assert PRIVATE == (
        "The repository is private, and GitHub shows the social preview only for a"
        " public repository"
    )


def test_an_upload_of_another_picture_is_not_current(tmp_path: Path) -> None:
    api = graphql({"usesCustomOpenGraphImage": True, "openGraphImageUrl": UPLOAD}, [])

    found = preview(api, REPO, committed(tmp_path), serving(b"older", []))

    assert found == Preview(digest(PNG), True, digest(b"older"))
    assert not found.current


def test_without_an_upload_github_draws_a_card_that_nobody_downloads(
    tmp_path: Path,
) -> None:
    seen: list[tuple[str, float]] = []
    api = graphql({"usesCustomOpenGraphImage": False, "openGraphImageUrl": DRAWN}, [])

    found = preview(api, REPO, committed(tmp_path), serving(PNG, seen))

    assert found == Preview(digest(PNG), False)
    assert not found.current
    assert seen == []


@pytest.mark.parametrize("uploaded", [True, False])
def test_without_a_picture_there_is_nothing_to_compare(
    tmp_path: Path, uploaded: bool
) -> None:
    seen: list[tuple[str, float]] = []
    api = graphql(
        {"usesCustomOpenGraphImage": uploaded, "openGraphImageUrl": UPLOAD}, []
    )

    found = preview(api, REPO, tmp_path, serving(PNG, seen))

    assert found == Preview("", uploaded)
    # No picture is never current, even next to an upload that is empty too.
    assert not found.current
    assert not Preview("", True, "").current
    assert seen == []


def test_a_refused_query_is_an_error_of_github(tmp_path: Path) -> None:
    api = graphql({}, [], returncode=1)

    with pytest.raises(GitHubError, match="refused"):
        preview(api, REPO, committed(tmp_path))


def test_the_download_reads_at_most_more_than_github_takes() -> None:
    seen: list[tuple[str, float]] = []
    big = b"x" * (LARGEST + 10)

    data = download(UPLOAD, serving(big, seen))

    # One byte more than GitHub takes, so that a larger answer differs all the same.
    assert len(data) == LARGEST + 1
    assert seen == [(UPLOAD, TIMEOUT)]


@pytest.mark.parametrize(
    "url",
    [
        DRAWN,
        f"http://{HOST}/1/2",
        f"https://{HOST}.example.com/1/2",
        "https://example.com/?u=https://repository-images.githubusercontent.com/1",
    ],
)
def test_the_download_reaches_only_the_host_of_uploads(url: str) -> None:
    seen: list[tuple[str, float]] = []

    with pytest.raises(
        Unreadable, match=re.escape(f"GitHub names {url}, not a picture on {HOST}")
    ):
        download(url, serving(PNG, seen))

    assert seen == []


def test_an_answer_with_an_error_is_closed_and_unreadable() -> None:
    body = io.BytesIO(b"Not Found")
    error = urllib.error.HTTPError(UPLOAD, 404, "Not Found", Message(), body)

    with pytest.raises(Unreadable, match="HTTP Error 404: Not Found") as raised:
        download(UPLOAD, failing(error))

    assert body.closed
    assert raised.value.__cause__ is error


def test_a_host_that_does_not_answer_twice_is_unreadable(waits: list[float]) -> None:
    with pytest.raises(Unreadable, match=re.escape(f"{UPLOAD}: timed out")):
        download(UPLOAD, failing(TimeoutError("timed out")))

    # One more try after a pause, as the requests to GitHub's API make.
    assert waits == [PAUSE]


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError("timed out"),
        urllib.error.URLError("connection reset"),
        urllib.error.HTTPError(UPLOAD, 503, "Unavailable", Message(), io.BytesIO()),
    ],
)
def test_one_bad_answer_of_the_host_gets_one_more_try(
    error: OSError, waits: list[float], tmp_path: Path
) -> None:
    seen: list[tuple[str, float]] = []
    good = serving(PNG, seen)

    def opener(url: str, timeout: float) -> Response:
        if not waits:
            raise error
        response: Response = good(url, timeout)
        return response

    queries: list[str] = []
    api = graphql(
        {"usesCustomOpenGraphImage": True, "openGraphImageUrl": UPLOAD}, queries
    )

    assert preview(api, REPO, committed(tmp_path), opener).current
    assert waits == [PAUSE]
    assert seen == [(UPLOAD, TIMEOUT)]


def test_a_refusal_of_the_host_gets_no_second_try(waits: list[float]) -> None:
    error = urllib.error.HTTPError(UPLOAD, 403, "Forbidden", Message(), io.BytesIO())

    with pytest.raises(Unreadable, match="HTTP Error 403: Forbidden"):
        download(UPLOAD, failing(error))

    assert waits == []


def test_a_picture_larger_than_github_takes_does_not_fit(tmp_path: Path) -> None:
    queries: list[str] = []
    api = graphql(
        {"usesCustomOpenGraphImage": False, "openGraphImageUrl": DRAWN}, queries
    )

    assert preview(api, REPO, committed(tmp_path, b"x" * LARGEST)).fits
    assert not preview(api, REPO, committed(tmp_path, b"x" * (LARGEST + 1))).fits


def test_the_settings_page_holds_the_social_preview() -> None:
    assert settings_page(REPO) == "https://github.com/Dennis-Otto/demo/settings"


def test_the_digest_is_the_sha256_of_the_file() -> None:
    assert digest(b"") == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )
