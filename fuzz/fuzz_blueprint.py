"""Coverage-guided fuzzing of how blueprint/github.py reads the answers of GitHub, with Atheris.

Whatever the GitHub CLI prints, reading it either gives a response or raises
GitHubError; no other exception may escape and stop a run of the settings. An answer
with an error, also a 404 to a write, never passes as a response, and the pages of a
list always read as a list.

    pip install --require-hashes -r stacks/fuzz/requirements.txt
    python fuzz/fuzz_blueprint.py -max_total_time=60

The Fuzzing workflow runs it on every change and longer every week.
"""

import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import atheris

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

with atheris.instrument_imports():
    import blueprint.github
    from blueprint.github import Api, GitHubError

# A request that tries again waits first; the fuzzing never waits.
blueprint.github.sleep = lambda seconds: None

METHODS = ["GET", "PUT", "PATCH", "POST", "DELETE"]


def test_one_input(data: bytes) -> None:
    provider = atheris.FuzzedDataProvider(data)
    status = provider.ConsumeIntInRange(100, 599)
    head = provider.ConsumeUnicodeNoSurrogates(200)
    body = provider.ConsumeUnicodeNoSurrogates(2000)
    stdout = provider.PickValueInList(
        [f"HTTP/2.0 {status} X\r\n{head}\r\n\r\n{body}", head + body, body]
    )
    stderr = provider.PickValueInList(["error", f"gh: {head} (HTTP {status})", head])
    code = provider.ConsumeIntInRange(0, 1)
    method = provider.PickValueInList([*METHODS, "every page"])

    def runner(
        arguments: Sequence[str], payload: str | None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(arguments, code, stdout, stderr)

    api = Api(runner)
    try:
        if method == "every page":
            items = api.get_all("repos/owner/name/labels")
            if not isinstance(items, list):
                raise AssertionError(f"{type(items)} passed as the items of a list")
            return
        response = api.request(
            method, "repos/owner/name", None if method == "GET" else {}
        )
    except GitHubError:
        return
    if response.status >= 400:
        raise AssertionError(
            f"status {response.status} of {method} passed as a response"
        )


def main() -> None:
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
