"""Coverage-guided fuzzing of how blueprint.py reads the answers of GitHub, with Atheris.

Whatever the GitHub CLI prints, reading it either gives a response or raises
GitHubError; no other exception may escape and stop a run of the settings.

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
    import blueprint


def test_one_input(data: bytes) -> None:
    provider = atheris.FuzzedDataProvider(data)
    status = provider.ConsumeIntInRange(100, 599)
    head = provider.ConsumeUnicodeNoSurrogates(200)
    body = provider.ConsumeUnicodeNoSurrogates(2000)
    stdout = provider.PickValueInList(
        [f"HTTP/2.0 {status} X\r\n{head}\r\n\r\n{body}", head + body]
    )

    def runner(
        arguments: Sequence[str], payload: str | None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(arguments, 1, stdout, "error")

    try:
        response = blueprint.Api(runner).request("GET", "repos/owner/name")
    except blueprint.GitHubError:
        return
    if response.status >= 400 and response.status != 404:
        raise AssertionError(f"status {response.status} passed as a response")


def main() -> None:
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
