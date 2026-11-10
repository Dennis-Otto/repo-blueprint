"""Tests of the downloads that survive an outage of GitHub's downloads without a token,
as on 8 November 2026 (decision 0133): .github/download.sh, which downloads an asset
of a release through the API and tries again after an error of GitHub,
.github/lychee.sh, which runs lychee as its action ran it, and the steps of the
workflows that download with them. Each runs in bash, with stand-ins for gh, sleep
and lychee that write their calls down."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
from shell import BASH, in_bash
from workflow_steps import (
    ROOT,
    SHA,
    Answer,
    StepResult,
    exact,
    job,
    recording,
    run_step,
    step,
)

from blueprint.github import API_VERSION_HEADER

pytestmark = pytest.mark.skipif(
    BASH is None, reason="the scripts run in bash, Git Bash on Windows"
)
WITH_JQ = pytest.mark.skipif(shutil.which("jq") is None, reason="needs jq")

# gh, which answers each call by the next line of the plan in $STUBS/plan: "fail" and
# the error that gh prints, "digest", with the digest of the asset that the API keeps,
# in $DIGEST, or else with the asset in $STUBS/asset, into the file of --output.
GH = r"""#!/usr/bin/env bash
printf '%s\n' "gh $*" >> "$CALLS"
outcome="$(head -n 1 "$STUBS/plan")"
tail -n +2 "$STUBS/plan" > "$STUBS/plan.next" && mv "$STUBS/plan.next" "$STUBS/plan"
case "$outcome" in
  fail\ *)
    echo "${outcome#fail }" >&2
    exit 1
    ;;
  # An error of the API with a body, such as a 502 of GitHub: gh writes the body to
  # its output as it is, even with --jq, and fails.
  bad\ gateway)
    echo '{"message":"Server Error"}'
    echo "gh: Server Error (HTTP 502)" >&2
    exit 1
    ;;
  digest) echo "$DIGEST" ;;
  # A call that stalls, as gh does when GitHub never answers. It writes down the
  # command of timeout that runs it, then gives that timeout the signal of its clock,
  # SIGALRM, which ends the call at once as the limit would after its seconds: the
  # test waits for no limit, and the tries after the stall have the whole limit.
  stall)
    mapfile -t -d '' under <"/proc/$PPID/cmdline"
    printf '%s\n' "under ${under[*]}" >> "$CALLS"
    kill -ALRM "$PPID"
    exec /usr/bin/sleep 30
    ;;
  *)
    while (($# > 0)); do
      [[ "$1" != --output ]] || cp "$STUBS/asset" "$2"
      shift
    done
    ;;
esac
"""
SLEEP = '#!/usr/bin/env bash\nprintf \'%s\\n\' "sleep $*" >> "$CALLS"\n'
# What gh prints when GitHub fails, as it did on 8 November 2026, and when it refuses.
TIMEOUT = "fail HTTP 504: Gateway Timeout (https://api.github.com/repos/o/tool/releases/assets/7)"
BAD_GATEWAY = "bad gateway"
UNREACHABLE = (
    'fail Get "https://api.github.com/repos/o/tool/releases/tags/v1.2.3": i/o timeout'
)
ASSET = b"#!/usr/bin/env bash\necho the tool\n"
SHA256 = hashlib.sha256(ASSET).hexdigest()
ARGUMENTS = ("o/tool", "v1.2.3", "tool_1.2.3_linux_amd64")
OUTAGE = (
    "::error title=GitHub fails::tool_1.2.3_linux_amd64 of o/tool v1.2.3 can't be"
    " downloaded: GitHub failed five times in two and a half minutes, an outage of"
    " GitHub and not a problem of this change (https://www.githubstatus.com). Run the"
    " job again once GitHub works."
)


def stub(folder: Path, name: str, text: str | bytes) -> Path:
    """A file of the stand-ins, executable, with the line ends of Linux."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(text if isinstance(text, bytes) else text.encode())
    path.chmod(0o755)
    return path


def script(
    tmp_path: Path,
    name: str,
    *arguments: str,
    plan: Sequence[str] = (),
    asset: bytes = ASSET,
    env: Mapping[str, str] | None = None,
    root: Path = ROOT,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    """Runs the script of .github in tmp_path, with gh answering by the plan; the
    result and the calls of the stand-ins."""
    stubs = tmp_path / "stubs"
    stub(stubs, "gh", GH)
    stub(stubs, "sleep", SLEEP)
    stub(stubs, "asset", asset)
    (stubs / "plan").write_text("".join(f"{line}\n" for line in plan), "utf-8")
    calls = tmp_path / "calls"
    calls.touch()
    result = subprocess.run(
        in_bash((root / ".github" / name).as_posix(), *arguments),
        cwd=tmp_path,
        env={
            # No token of this machine reaches the scripts.
            **{
                name: value
                for name, value in os.environ.items()
                if name not in ("GH_TOKEN", "GITHUB_TOKEN")
            },
            "STUBS": stubs.as_posix(),
            "CALLS": calls.as_posix(),
            **(env or {}),
        },
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    return result, calls.read_text(encoding="utf-8").splitlines()


def download_call(file: Path) -> str:
    return (
        "gh release download v1.2.3 --repo o/tool --pattern tool_1.2.3_linux_amd64"
        f" --output {file.as_posix()} --clobber"
    )


# .github/download.sh


def test_a_download_that_github_fails_for_a_while_is_tried_again(
    tmp_path: Path,
) -> None:
    file = tmp_path / "tools/tool"

    result, calls = script(
        tmp_path,
        "download.sh",
        *ARGUMENTS,
        file.as_posix(),
        SHA256,
        plan=(TIMEOUT, UNREACHABLE, "asset"),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert file.read_bytes() == ASSET
    # Through the API with gh, which takes the token of GH_TOKEN, and again after a
    # pause that doubles.
    assert calls == [
        download_call(file),
        "sleep 10",
        download_call(file),
        "sleep 20",
        download_call(file),
    ]
    assert (
        "GitHub failed; tool_1.2.3_linux_amd64 of o/tool v1.2.3 is asked for again in"
        " 10 seconds." in result.stderr
    )
    assert "HTTP 504: Gateway Timeout" in result.stderr
    assert "::error" not in result.stdout + result.stderr
    assert result.stdout == (
        "tool_1.2.3_linux_amd64 of o/tool v1.2.3 is downloaded and has its sha256.\n"
    )


def test_a_download_that_github_keeps_failing_names_the_outage(tmp_path: Path) -> None:
    file = tmp_path / "tool"

    result, calls = script(
        tmp_path, "download.sh", *ARGUMENTS, file.as_posix(), SHA256, plan=[TIMEOUT] * 5
    )

    assert result.returncode == 1
    assert OUTAGE in result.stderr
    assert calls.count(download_call(file)) == 5
    assert [call for call in calls if call.startswith("sleep ")] == [
        "sleep 10",
        "sleep 20",
        "sleep 40",
        "sleep 80",
    ]
    assert not file.exists()


@pytest.mark.parametrize(
    ("setting", "limit"),
    [("", "300"), ("45", "45")],
    ids=["by default", "with DOWNLOAD_TIMEOUT"],
)
def test_a_download_that_stalls_is_tried_again(
    tmp_path: Path, setting: str, limit: str
) -> None:
    # gh has no limit of its own: a call that GitHub never answers ends after
    # DOWNLOAD_TIMEOUT seconds and counts as an error of GitHub, so that the job tries
    # again and names the outage instead of running until its own time is up. The
    # stand-in of gh ends its stall by the clock of its timeout, not by a short limit:
    # with a limit of one second, the try after the stall, which has to download the
    # asset within it, failed on a loaded machine (#775).
    file = tmp_path / "tool"

    result, calls = script(
        tmp_path,
        "download.sh",
        *ARGUMENTS,
        file.as_posix(),
        SHA256,
        plan=("stall", "asset"),
        env={"DOWNLOAD_TIMEOUT": setting},
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert file.read_bytes() == ASSET
    assert calls == [
        download_call(file),
        f"under timeout --kill-after=10 {limit} {download_call(file)}",
        "sleep 10",
        download_call(file),
    ]
    assert f"GitHub didn't answer in {limit} seconds." in result.stderr
    assert "::error" not in result.stdout + result.stderr


@pytest.mark.parametrize(
    "error",
    [
        "release not found",
        "no assets match the file pattern",
        "HTTP 404: Not Found (https://api.github.com/repos/o/tool/releases/tags/v1.2.3)",
        "HTTP 401: Bad credentials (https://api.github.com/repos/o/tool/releases)",
        "gh: To use GitHub CLI in a GitHub Actions workflow, set the GH_TOKEN environment variable.",
    ],
)
def test_a_release_that_isnt_there_or_a_refused_token_stops_at_once(
    tmp_path: Path, error: str
) -> None:
    file = tmp_path / "tool"

    result, calls = script(
        tmp_path,
        "download.sh",
        *ARGUMENTS,
        file.as_posix(),
        SHA256,
        plan=[f"fail {error}"],
    )

    assert result.returncode == 1
    assert calls == [download_call(file)]
    assert (
        "::error title=Download::tool_1.2.3_linux_amd64 of o/tool v1.2.3 can't be"
        f" downloaded: {error}\n"
    ) in result.stderr


def test_a_download_with_another_sha256_is_thrown_away(tmp_path: Path) -> None:
    file = tmp_path / "tool"

    result, _ = script(
        tmp_path, "download.sh", *ARGUMENTS, file.as_posix(), "0" * 64, plan=["asset"]
    )

    assert result.returncode == 1
    assert not file.exists()
    assert (
        "::error title=Download::The download of tool_1.2.3_linux_amd64 of o/tool"
        f" v1.2.3 doesn't have the sha256 {'0' * 64}, so it isn't the asset that was"
        " pinned, and nothing runs it.\n"
    ) in result.stdout


# The question for the digest that GitHub keeps of the asset.
DIGEST_CALL = (
    f"gh api --header {API_VERSION_HEADER} repos/o/tool/releases/tags/v1.2.3 --jq"
    ' .assets[] | select(.name == "tool_1.2.3_linux_amd64") | .digest // ""'
)


def test_without_a_pin_the_digest_that_github_keeps_checks_the_download(
    tmp_path: Path,
) -> None:
    file = tmp_path / "tool"

    result, calls = script(
        tmp_path,
        "download.sh",
        *ARGUMENTS,
        file.as_posix(),
        plan=(TIMEOUT, "digest", "asset"),
        env={"DIGEST": f"sha256:{SHA256}"},
    )

    assert result.returncode == 0, result.stdout + result.stderr
    # The version of the API of blueprint/github.py, as every call asks for it.
    assert calls == [DIGEST_CALL, "sleep 10", DIGEST_CALL, download_call(file)]
    assert file.read_bytes() == ASSET


def test_the_answer_of_a_failed_try_never_reaches_the_result(tmp_path: Path) -> None:
    # gh writes the body of an error of the API to its output, even with --jq: only
    # the output of the try that worked is the digest, so that a second try that works
    # downloads the asset, instead of failing on a digest with the error in front.
    file = tmp_path / "tool"

    result, calls = script(
        tmp_path,
        "download.sh",
        *ARGUMENTS,
        file.as_posix(),
        plan=(BAD_GATEWAY, "digest", BAD_GATEWAY, "asset"),
        env={"DIGEST": f"sha256:{SHA256}"},
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert calls == [
        DIGEST_CALL,
        "sleep 10",
        DIGEST_CALL,
        download_call(file),
        "sleep 10",
        download_call(file),
    ]
    assert file.read_bytes() == ASSET
    # The error stays in the log, and the body of the answer leaves the output alone.
    assert result.stderr.count("gh: Server Error (HTTP 502)") == 2
    assert result.stdout == (
        "tool_1.2.3_linux_amd64 of o/tool v1.2.3 is downloaded and has its sha256.\n"
    )


@pytest.mark.parametrize("digest", ["", "sha512:abc", f"sha256:{SHA256[:-1]}"])
def test_an_asset_without_a_sha256_of_github_is_never_downloaded(
    tmp_path: Path, digest: str
) -> None:
    file = tmp_path / "tool"

    result, calls = script(
        tmp_path,
        "download.sh",
        *ARGUMENTS,
        file.as_posix(),
        plan=["digest"],
        env={"DIGEST": digest},
    )

    assert result.returncode == 1
    assert calls == [DIGEST_CALL]
    assert (
        "::error title=Download::GitHub keeps no sha256 of tool_1.2.3_linux_amd64 of"
        " o/tool v1.2.3, so it can't be checked: pin its sha256.\n"
    ) in result.stdout


def test_a_digest_that_github_never_gives_names_the_outage(tmp_path: Path) -> None:
    result, calls = script(
        tmp_path,
        "download.sh",
        *ARGUMENTS,
        (tmp_path / "tool").as_posix(),
        plan=[TIMEOUT] * 5,
    )

    assert result.returncode == 1
    assert OUTAGE in result.stderr
    assert calls.count(DIGEST_CALL) == 5
    assert not any(call.startswith("gh release download") for call in calls)


@WITH_JQ
def test_the_digest_is_the_one_of_the_asset_of_the_release() -> None:
    jq = shutil.which("jq")
    assert jq
    release = {
        "assets": [
            {"name": "tool_1.2.3_linux_arm64", "digest": "sha256:" + "a" * 64},
            {"name": "tool_1.2.3_linux_amd64", "digest": f"sha256:{SHA256}"},
        ]
    }
    selected = DIGEST_CALL.split(" --jq ", 1)[1]
    for answer, digest in (
        (release, f"sha256:{SHA256}"),
        # An asset of before June 2025 has none, and so has a missing asset.
        ({"assets": [{"name": "tool_1.2.3_linux_amd64", "digest": None}]}, ""),
        ({"assets": []}, ""),
    ):
        done = subprocess.run(
            [jq, "-r", selected],
            input=json.dumps(answer),
            capture_output=True,
            encoding="utf-8",
            check=True,
        )
        assert done.stdout.strip() == digest


@pytest.mark.parametrize(
    ("arguments", "error"),
    [
        (("o/tool", "v1.2.3", "tool"), "Usage: bash .github/download.sh"),
        (
            ("o/tool", "v1", "tool", "file", SHA256, "more"),
            "Usage: bash .github/download.sh",
        ),
        # Signs that a filter of jq or a shell would read as code.
        (("o/tool", "v1.2.3", "tool$(id)", "file"), "tool$(id) is no name"),
        (("o/tool;id", "v1.2.3", "tool", "file"), "o/tool;id is no name"),
        (("o/tool", "v1.2.3 x", "tool", "file"), "v1.2.3 x is no name"),
        (("o/tool", "v1.2.3", "tool_*", "file"), "tool_* is no name"),
    ],
)
def test_the_script_takes_only_the_names_of_a_repository_a_release_and_an_asset(
    tmp_path: Path, arguments: tuple[str, ...], error: str
) -> None:
    result, calls = script(tmp_path, "download.sh", *arguments)

    assert result.returncode == 2
    assert error in result.stdout + result.stderr
    assert calls == []


# .github/lychee.sh

LYCHEE_VERSION = re.search(
    r"^version=(\S+)$", (ROOT / ".github/lychee.sh").read_text(encoding="utf-8"), re.M
)
assert LYCHEE_VERSION
# lychee, which writes down its arguments, each in brackets, the folder it runs in and
# its token, writes $STUBS/report as its report, if there is one, and ends with the
# code in $STUBS/code.
FAKE_LYCHEE = r"""#!/usr/bin/env bash
printf 'lychee' >> "$CALLS"
printf ' [%s]' "$@" >> "$CALLS"
printf ' in %s token %s\n' "${PWD##*/}" "${GITHUB_TOKEN:-none}" >> "$CALLS"
while (($# > 0)); do
  [[ "$1" != --output || ! -f "$STUBS/report" ]] || cp "$STUBS/report" "$2"
  shift
done
exit "$(cat "$STUBS/code" 2>/dev/null || echo 0)"
"""


def report_of(total: int) -> str:
    """The report of lychee in Markdown, as lychee 0.24 writes it, for total links."""
    errors = 1 if total else 0
    return (
        "# Summary\n\n| Status         | Count |\n|----------------|-------|\n"
        f"| 🔍 Total       | {total}     |\n| ✅ Successful  | {total - errors}     |\n"
        f"| 🚫 Errors      | {errors}     |\n"
    )


def run_lychee(
    tmp_path: Path,
    *arguments: str,
    report: str | None = None,
    code: int = 0,
    env: Mapping[str, str] | None = None,
    root: Path = ROOT,
) -> tuple[subprocess.CompletedProcess[str], list[str], Path]:
    """Runs .github/lychee.sh with lychee in its folder of $RUNNER_TEMP, as a run
    before installed it; the result, the calls and the folder of the runner."""
    runner = tmp_path / "runner"
    assert LYCHEE_VERSION
    stub(runner / f"lychee-{LYCHEE_VERSION[1]}", "lychee", FAKE_LYCHEE)
    stubs = tmp_path / "stubs"
    if report is not None:
        stub(stubs, "report", report)
    stub(stubs, "code", f"{code}\n")
    for name in ("summary", "output"):
        (runner / name).touch()
    variables = {
        "RUNNER_TEMP": runner.as_posix(),
        "GITHUB_STEP_SUMMARY": (runner / "summary").as_posix(),
        "GITHUB_OUTPUT": (runner / "output").as_posix(),
        "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_REPOSITORY": "o/r",
        "GITHUB_RUN_ID": "5",
        **(env or {}),
    }
    result, calls = script(tmp_path, "lychee.sh", *arguments, env=variables, root=root)
    return result, calls, runner


def test_lychee_runs_as_its_action_ran_it(tmp_path: Path) -> None:
    report = report_of(3)
    target = tmp_path / "runner/reports/links.md"

    result, calls, runner = run_lychee(
        tmp_path,
        target.as_posix(),
        "--offline",
        "--remap",
        "^https://o.github.io/r/(.*)$ file:///site/$1",
        "**/*.html",
        report=report,
        env={"GH_TOKEN": "the-token"},
    )

    assert result.returncode == 0, result.stdout + result.stderr
    # The report in Markdown, with a box for each link that fails, and the token of the
    # job for the links to GitHub; the arguments as they came, one by one.
    assert calls == [
        f"lychee [--mode] [task] [--format] [markdown] [--output] [{target.as_posix()}]"
        " [--offline] [--remap] [^https://o.github.io/r/(.*)$ file:///site/$1]"
        f" [**/*.html] in {tmp_path.name} token the-token"
    ]
    # In the log and the summary, and in the report with the link to the log, which an
    # issue of the Links workflow shows.
    assert report in result.stdout
    assert (runner / "summary").read_text(encoding="utf-8") == report
    assert target.read_text(encoding="utf-8") == (
        f"{report}\n[The log of the check](https://github.com/o/r/actions/runs/5)\n"
    )
    assert (runner / "output").read_text(encoding="utf-8") == "exit_code=0\n"


@pytest.mark.parametrize(
    ("options", "code", "total", "ends"),
    [
        # A broken link fails the check, but the weekly run, which keeps an issue.
        ((), 2, 3, 2),
        (("--no-fail",), 2, 3, 0),
        (("--may-find-none",), 2, 3, 2),
        # No link at all: the check read no document, unless none may be found.
        ((), 0, 0, 1),
        (("--no-fail",), 0, 0, 1),
        (("--may-find-none",), 0, 0, 0),
        (("--no-fail", "--may-find-none"), 2, 0, 0),
        # lychee fails itself, such as for a rule that it can't read.
        ((), 3, 3, 3),
    ],
)
def test_lychee_fails_the_check_as_its_action_did(
    tmp_path: Path, options: tuple[str, ...], code: int, total: int, ends: int
) -> None:
    result, _, runner = run_lychee(
        tmp_path, *options, "links.md", "README.md", report=report_of(total), code=code
    )

    assert result.returncode == ends, result.stdout + result.stderr
    assert (runner / "output").read_text(encoding="utf-8") == f"exit_code={code}\n"
    none = "::error title=No link::lychee found no link: its arguments name no"
    assert (none in result.stdout) is (total == 0 and "--may-find-none" not in options)


def test_lychee_without_a_report_says_where_to_look(tmp_path: Path) -> None:
    result, _, runner = run_lychee(tmp_path, "links.md", "README.md", code=1)

    assert result.returncode == 1
    said = "lychee wrote no report; its log says why.\n"
    assert (runner / "summary").read_text(encoding="utf-8") == said
    assert (tmp_path / "links.md").read_text(encoding="utf-8").startswith(said)


@pytest.mark.parametrize(
    ("env", "token"),
    [
        ({"GH_TOKEN": "of-the-job"}, "of-the-job"),
        ({"GH_TOKEN": "of-the-job", "GITHUB_TOKEN": "its-own"}, "its-own"),
        ({}, "none"),
    ],
)
def test_lychee_takes_the_token_of_the_job_for_the_links_to_github(
    tmp_path: Path, env: dict[str, str], token: str
) -> None:
    result, calls, _ = run_lychee(
        tmp_path, "links.md", "README.md", report=report_of(1), env=env
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert calls[-1].endswith(f" token {token}")


@pytest.mark.parametrize(
    ("arguments", "error"),
    [
        (("--fail-never", "links.md"), "Unknown option --fail-never."),
        ((), "Usage: bash .github/lychee.sh"),
        (("--no-fail",), "Usage: bash .github/lychee.sh"),
    ],
)
def test_lychee_sh_takes_its_options_and_a_report(
    tmp_path: Path, arguments: tuple[str, ...], error: str
) -> None:
    result, calls, _ = run_lychee(tmp_path, *arguments)

    assert result.returncode == 2
    assert error in result.stderr
    assert calls == []


def lychee_release(tmp_path: Path) -> bytes:
    """The archive of a release of lychee, with the stand-in for lychee in its folder."""
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w:gz") as archive:
        for name, content in (
            ("lychee-x86_64-unknown-linux-gnu/README.md", b"lychee\n"),
            ("lychee-x86_64-unknown-linux-gnu/lychee", FAKE_LYCHEE.encode()),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(content)
            info.mode = 0o755
            archive.addfile(info, io.BytesIO(content))
    return data.getvalue()


def test_lychee_comes_from_its_release_once_in_a_job(tmp_path: Path) -> None:
    release = lychee_release(tmp_path)
    # The scripts of a repository whose pin is the sha256 of this release.
    root = tmp_path / "repository"
    (root / ".github").mkdir(parents=True)
    shutil.copy(ROOT / ".github/download.sh", root / ".github/download.sh")
    text = (ROOT / ".github/lychee.sh").read_text(encoding="utf-8")
    pinned = re.sub(
        r"^sha256=[0-9a-f]{64}$",
        f"sha256={hashlib.sha256(release).hexdigest()}",
        text,
        count=1,
        flags=re.M,
    )
    assert pinned != text
    (root / ".github/lychee.sh").write_bytes(pinned.encode())
    runner = tmp_path / "runner"
    runner.mkdir()
    for name in ("summary", "output"):
        (runner / name).touch()
    env = {
        # By its path in the folder of the test, which tar of Git for Windows reads as a
        # path, where it takes C:/… for a host; on the runners it is /home/runner/….
        "RUNNER_TEMP": "runner",
        "GITHUB_STEP_SUMMARY": (runner / "summary").as_posix(),
        "GITHUB_OUTPUT": (runner / "output").as_posix(),
        "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_REPOSITORY": "o/r",
        "GITHUB_RUN_ID": "5",
    }
    stub(tmp_path / "stubs", "report", report_of(2))
    assert LYCHEE_VERSION
    version = LYCHEE_VERSION[1]

    for _ in range(2):
        result, calls = script(
            tmp_path,
            "lychee.sh",
            "links.md",
            "README.md",
            plan=(TIMEOUT, "asset"),
            asset=release,
            env=env,
            root=root,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    # Through the API, once: the second check of the job takes the lychee of the first.
    download = (
        f"gh release download lychee-v{version} --repo lycheeverse/lychee --pattern"
        " lychee-x86_64-unknown-linux-gnu.tar.gz --output runner/lychee.tar.gz --clobber"
    )
    assert [call for call in calls if call.startswith("gh ")] == [download, download]
    assert sum(call.startswith("lychee ") for call in calls) == 2
    assert sorted(path.name for path in (runner / f"lychee-{version}").iterdir()) == [
        "lychee"
    ]
    assert not (runner / "lychee.tar.gz").exists()


# The steps that check the links with .github/lychee.sh.


def run_with_lychee(
    tmp_path: Path,
    workflow: str,
    job_id: str,
    name: str,
    *,
    env: Mapping[str, str],
    report: str,
    code: int = 0,
    files: Mapping[str, str] | None = None,
) -> StepResult:
    """Runs the step with the scripts of .github and a stand-in for the lychee that a
    check before installed, executable, so that nothing is downloaded."""
    assert LYCHEE_VERSION
    stub(tmp_path / "stubs", "report", report)
    stub(tmp_path / "stubs", "code", f"{code}\n")
    stub(tmp_path / f"runner/lychee-{LYCHEE_VERSION[1]}", "lychee", FAKE_LYCHEE)
    return run_step(
        tmp_path,
        workflow,
        job_id,
        name,
        env={"CALLS": (tmp_path / "calls").as_posix(), **env},
        files={
            ".github/lychee.sh": (ROOT / ".github/lychee.sh").read_text("utf-8"),
            ".github/download.sh": (ROOT / ".github/download.sh").read_text("utf-8"),
            **(files or {}),
        },
        # A download, which none of these tests plans, waits for nothing.
        stubs={"sleep": recording("sleep")},
    )


def lychee_calls(tmp_path: Path) -> list[str]:
    return (tmp_path / "calls").read_text(encoding="utf-8").splitlines()


def test_the_website_checks_its_links_and_anchors_in_its_folder(tmp_path: Path) -> None:
    done = run_with_lychee(
        tmp_path,
        "docs.yml",
        "docs",
        "Check the links and anchors of the website",
        env={},
        report=report_of(12),
        files={"site/index.html": "<html></html>\n"},
    )

    assert done.returncode == 0, done.stderr
    runner = done.runner_temp.as_posix()
    assert lychee_calls(tmp_path) == [
        "lychee [--mode] [task] [--format] [markdown] [--output]"
        f" [{runner}/website-links.md] [--offline] [--include-fragments] [--root-dir]"
        f" [{runner}/address] [--no-progress] [**/*.html] in site token the-token"
    ]
    assert done.summary == report_of(12)


def test_the_map_of_the_website_leads_its_addresses_to_its_files(
    tmp_path: Path,
) -> None:
    rule = "^https://o\\.github\\.io/r/(.*)$ file:///home/runner/work/r/r/site/$1"

    done = run_with_lychee(
        tmp_path,
        "docs.yml",
        "docs",
        "Check the links of the map of the website",
        env={"MAP": rule},
        report=report_of(4),
        files={"site/llms.txt": "# r\n"},
    )

    assert done.returncode == 0, done.stderr
    runner = done.runner_temp.as_posix()
    # The rule is one argument, with its space and its $1.
    assert lychee_calls(tmp_path) == [
        "lychee [--mode] [task] [--format] [markdown] [--output]"
        f" [{runner}/website-map-links.md] [--offline] [--no-progress] [--remap]"
        f" [{rule}] [llms.txt] in site token the-token"
    ]


# The patterns of every document, as the Links workflow names them.
EVERY_DOCUMENT = "'./**/*.md' './.github/**/*.md' './docs/**/*.html'"


@pytest.mark.parametrize(
    ("event", "files", "every", "code", "total", "ends"),
    [
        # The weekly run keeps the issue of broken links instead of failing.
        ("schedule", EVERY_DOCUMENT, "true", 2, 3, 0),
        ("push", EVERY_DOCUMENT, "true", 2, 3, 2),
        # Every document without a link: the check read none.
        ("schedule", EVERY_DOCUMENT, "true", 0, 0, 1),
        # A pull request checks the documents it changes, which may have no link.
        ("pull_request", "'./README.md' './docs/a.md' ", "", 0, 0, 0),
        ("pull_request", "'./README.md' ", "", 2, 1, 2),
    ],
)
def test_the_links_of_the_documents_are_checked_by_their_patterns(
    tmp_path: Path, event: str, files: str, every: str, code: int, total: int, ends: int
) -> None:
    done = run_with_lychee(
        tmp_path,
        "links.yml",
        "links",
        "Check the links of the documentation",
        env={"EVENT": event, "FILES": files, "EVERY": every},
        report=report_of(total),
        code=code,
        # Documents that the patterns would find, had bash expanded them.
        files={"README.md": "# r\n", "docs/a.md": "# a\n"},
    )

    assert done.returncode == ends, done.stdout + done.stderr
    assert done.outputs == {"exit_code": str(code)}
    documents = " ".join(f"[{name}]" for name in re.findall(r"'([^']*)'", files))
    assert lychee_calls(tmp_path) == [
        "lychee [--mode] [task] [--format] [markdown] [--output]"
        f" [{done.runner_temp.as_posix()}/links.md] [--config] [lychee.toml]"
        f" [--no-progress] [--cache] [--max-cache-age] [1d] {documents}"
        f" in workspace token the-token"
    ]


# .github/gitleaks.sh

GITLEAKS_VERSION = re.search(
    r"^version=(\S+)$", (ROOT / ".github/gitleaks.sh").read_text(encoding="utf-8"), re.M
)
assert GITLEAKS_VERSION
# gitleaks, which writes down its arguments, each in brackets, the folder it runs in and
# the tokens it sees, writes $STUBS/report as its report, if there is one, and ends with
# the code in $STUBS/code.
FAKE_GITLEAKS = r"""#!/usr/bin/env bash
printf 'gitleaks' >> "$CALLS"
printf ' [%s]' "$@" >> "$CALLS"
printf ' in %s token %s %s\n' "${PWD##*/}" "${GH_TOKEN:-none}" "${GITHUB_TOKEN:-none}" >> "$CALLS"
while (($# > 0)); do
  [[ "$1" != --report-path || ! -f "$STUBS/report" ]] || cp "$STUBS/report" "$2"
  shift
done
exit "$(cat "$STUBS/code" 2>/dev/null || echo 0)"
"""
SCAN = (
    "gitleaks [git] [--redact] [--verbose] [--no-banner] [--exit-code] [2]"
    " [--report-format] [json] [--report-path] [{runner}/gitleaks.json]"
)


def run_gitleaks(
    tmp_path: Path,
    *arguments: str,
    report: object = None,
    code: int = 0,
    env: Mapping[str, str] | None = None,
) -> tuple[subprocess.CompletedProcess[str], list[str], Path]:
    """Runs .github/gitleaks.sh with gitleaks in its folder of $RUNNER_TEMP, as a scan
    before installed it, in tmp_path; the result, the calls and the folder of the
    runner."""
    runner = tmp_path / "runner"
    assert GITLEAKS_VERSION
    stub(runner / f"gitleaks-{GITLEAKS_VERSION[1]}", "gitleaks", FAKE_GITLEAKS)
    stubs = tmp_path / "stubs"
    if report is not None:
        stub(stubs, "report", json.dumps(report))
    stub(stubs, "code", f"{code}\n")
    (runner / "summary").touch()
    variables = {
        "RUNNER_TEMP": runner.as_posix(),
        "GITHUB_STEP_SUMMARY": (runner / "summary").as_posix(),
        "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_REPOSITORY": "o/r",
        **(env or {}),
    }
    result, calls = script(tmp_path, "gitleaks.sh", *arguments, env=variables)
    return result, calls, runner


def git(root: Path, *arguments: str) -> str:
    done = subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.org",
            "-c",
            "commit.gpgsign=false",
            *arguments,
        ],
        cwd=root,
        capture_output=True,
        encoding="utf-8",
        check=True,
    )
    return done.stdout.strip()


def pull_request(root: Path, changed: str) -> tuple[str, str]:
    """A repository in root whose pull request changes the file changed; the commits
    of its base and its head."""
    git(root, "init", "--quiet")
    (root / "README.md").write_text("A project\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "--quiet", "--message", "The base")
    base = git(root, "rev-parse", "HEAD")
    (root / changed).parent.mkdir(parents=True, exist_ok=True)
    (root / changed).write_text("A change\n", encoding="utf-8")
    git(root, "add", changed)
    git(root, "commit", "--quiet", "--message", "The pull request")
    return base, git(root, "rev-parse", "HEAD")


def test_gitleaks_scans_the_commits_of_a_pull_request(tmp_path: Path) -> None:
    base, head = pull_request(tmp_path, "src/app.py")

    result, calls, runner = run_gitleaks(
        tmp_path, base, head, env={"GH_TOKEN": "of-the-job", "GITHUB_TOKEN": "too"}
    )

    assert result.returncode == 0, result.stdout + result.stderr
    # Those after the base up to the head, with every secret redacted, and without
    # the token of the job, which only the download needs.
    assert calls == [
        SCAN.format(runner=runner.as_posix())
        + f" [--log-opts] [{base}..{head}] [.] in {tmp_path.name} token none none"
    ]
    assert GITLEAKS_VERSION
    version = GITLEAKS_VERSION[1]
    assert f"gitleaks {version} scans the commits of the pull request." in result.stdout
    assert (runner / "summary").read_text(encoding="utf-8") == (
        f"gitleaks {version} found no secret in the commits of the pull request.\n"
    )


@pytest.mark.parametrize(
    "rules", [".github/gitleaks.sh", ".gitleaks.toml", ".gitleaksignore"]
)
def test_a_pull_request_that_changes_the_rules_scans_the_whole_history(
    tmp_path: Path, rules: str
) -> None:
    base, head = pull_request(tmp_path, rules)

    result, calls, runner = run_gitleaks(tmp_path, base, head)

    assert result.returncode == 0, result.stdout + result.stderr
    assert calls == [
        SCAN.format(runner=runner.as_posix())
        + f" [.] in {tmp_path.name} token none none"
    ]
    assert (
        "scans the whole history, since the pull request changes gitleaks or its rules."
    ) in result.stdout


def test_gitleaks_scans_the_whole_history_without_a_pull_request(
    tmp_path: Path,
) -> None:
    result, calls, runner = run_gitleaks(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert calls == [
        SCAN.format(runner=runner.as_posix())
        + f" [.] in {tmp_path.name} token none none"
    ]
    assert GITLEAKS_VERSION
    assert (runner / "summary").read_text(encoding="utf-8") == (
        f"gitleaks {GITLEAKS_VERSION[1]} found no secret in the whole history.\n"
    )


COMMIT = "54c2df848f2b9c5e5f010dec7170b38f8365f10e"
# Findings as gitleaks 8.30 reports them in JSON with --redact: one in a file whose
# name a workflow command, a link and HTML each have to escape.
FINDINGS = [
    {
        "RuleID": "generic-api-key",
        "Description": "Detected a Generic API Key.",
        "StartLine": 3,
        "EndLine": 3,
        "Match": "key = REDACTED",
        "Secret": "REDACTED",
        "File": "src/__init__.py",
        "Commit": COMMIT,
        "Author": "Someone",
        "Email": "someone@example.org",
        "Fingerprint": f"{COMMIT}:src/__init__.py:generic-api-key:3",
    },
    {
        "RuleID": "curl-auth-user",
        "Description": "Discovered a token in a curl command & more.",
        "StartLine": 451,
        "EndLine": 452,
        "Match": "curl --user REDACTED",
        "Secret": "REDACTED",
        "File": "docs/a b,c:d%e<f>.md",
        "Commit": COMMIT,
        "Author": "Someone",
        "Email": "someone@example.org",
        "Fingerprint": f"{COMMIT}:docs/a b,c:d%e<f>.md:curl-auth-user:451",
    },
]


@WITH_JQ
def test_each_finding_is_an_annotation_and_a_row_of_the_summary(
    tmp_path: Path,
) -> None:
    result, _, runner = run_gitleaks(tmp_path, report=FINDINGS, code=2)

    assert result.returncode == 1
    # At the line of the file, with the fingerprint that .gitleaksignore takes.
    assert (
        "::error file=src/__init__.py,line=3,endLine=3,title=gitleaks%3A"
        " generic-api-key::Detected a Generic API Key. in commit 54c2df8. Revoke the"
        " secret, or add its fingerprint to .gitleaksignore if it is none:"
        f" {COMMIT}:src/__init__.py:generic-api-key:3\n"
        "::error file=docs/a b%2Cc%3Ad%25e<f>.md,line=451,endLine=452,title=gitleaks%3A"
        " curl-auth-user::Discovered a token in a curl command & more. in commit"
        " 54c2df8. Revoke the secret, or add its fingerprint to .gitleaksignore if it is"
        f" none: {COMMIT}:docs/a b,c:d%25e<f>.md:curl-auth-user:451\n"
    ) in result.stdout
    blob = f"https://github.com/o/r/blob/{COMMIT}"
    assert (runner / "summary").read_text(encoding="utf-8") == (
        "## gitleaks found 2 secrets in the whole history\n\n<table>\n"
        "<tr><th>Rule</th><th>Line</th><th>Commit</th><th>Fingerprint for"
        " <code>.gitleaksignore</code></th></tr>\n"
        "<tr><td>generic-api-key: Detected a Generic API Key.</td>"
        f'<td><a href="{blob}/src/__init__.py#L3">src/__init__.py:3</a></td>'
        f'<td><a href="https://github.com/o/r/commit/{COMMIT}">54c2df8</a></td>'
        f"<td><code>{COMMIT}:src/__init__.py:generic-api-key:3</code></td></tr>\n"
        "<tr><td>curl-auth-user: Discovered a token in a curl command &amp; more.</td>"
        f'<td><a href="{blob}/docs/a%20b%2Cc%3Ad%25e%3Cf%3E.md#L451">'
        "docs/a b,c:d%e&lt;f&gt;.md:451</a></td>"
        f'<td><a href="https://github.com/o/r/commit/{COMMIT}">54c2df8</a></td>'
        f"<td><code>{COMMIT}:docs/a b,c:d%e&lt;f&gt;.md:curl-auth-user:451</code>"
        "</td></tr>\n</table>\n\n"
    )


@WITH_JQ
def test_one_finding_is_one_secret(tmp_path: Path) -> None:
    base, head = pull_request(tmp_path, "src/app.py")

    result, _, runner = run_gitleaks(tmp_path, base, head, report=FINDINGS[:1], code=2)

    assert result.returncode == 1
    assert (
        (runner / "summary")
        .read_text(encoding="utf-8")
        .startswith("## gitleaks found 1 secret in the commits of the pull request\n")
    )


@pytest.mark.parametrize(("code", "report"), [(1, None), (2, None), (126, [])])
def test_gitleaks_that_fails_itself_says_that_it_found_nothing(
    tmp_path: Path, code: int, report: object
) -> None:
    result, _, runner = run_gitleaks(tmp_path, report=report, code=code)

    assert result.returncode == 1
    assert GITLEAKS_VERSION
    version = GITLEAKS_VERSION[1]
    assert (
        f"::error title=gitleaks failed::gitleaks {version} ended with exit code"
        f" {code} before the end of its scan, which is no finding of a secret: its log"
        " says why.\n"
    ) in result.stdout
    assert (runner / "summary").read_text(encoding="utf-8") == (
        f"gitleaks {version} ended with exit code {code} before the end of its scan;"
        " its log says why.\n"
    )


@pytest.mark.parametrize(
    ("arguments", "error"),
    [
        (("a" * 40,), "Usage: bash .github/gitleaks.sh [base head]"),
        (("a" * 40, "b" * 40, "c" * 40), "Usage: bash .github/gitleaks.sh"),
        (("main", "b" * 40), "main is no commit. Usage:"),
        (("a" * 40, "--output=/tmp/x"), "--output=/tmp/x is no commit."),
        (("a" * 39, "b" * 40), f"{'a' * 39} is no commit."),
        (("A" * 40, "b" * 40), f"{'A' * 40} is no commit."),
    ],
)
def test_gitleaks_sh_takes_two_commits_or_none(
    tmp_path: Path, arguments: tuple[str, ...], error: str
) -> None:
    result, calls, _ = run_gitleaks(tmp_path, *arguments)

    assert result.returncode == 2
    assert error in result.stderr
    assert calls == []


def gitleaks_release() -> bytes:
    """The archive of a release of gitleaks, with the stand-in for gitleaks."""
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w:gz") as archive:
        for name, content in (
            ("LICENSE", b"MIT\n"),
            ("README.md", b"gitleaks\n"),
            ("gitleaks", FAKE_GITLEAKS.encode()),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(content)
            info.mode = 0o755
            archive.addfile(info, io.BytesIO(content))
    return data.getvalue()


def test_gitleaks_comes_from_its_release_once_in_a_job(tmp_path: Path) -> None:
    release = gitleaks_release()
    # The scripts of a repository whose pin is the sha256 of this release.
    root = tmp_path / "repository"
    (root / ".github").mkdir(parents=True)
    shutil.copy(ROOT / ".github/download.sh", root / ".github/download.sh")
    text = (ROOT / ".github/gitleaks.sh").read_text(encoding="utf-8")
    pinned = re.sub(
        r"^sha256=[0-9a-f]{64}$",
        f"sha256={hashlib.sha256(release).hexdigest()}",
        text,
        count=1,
        flags=re.M,
    )
    assert pinned != text
    (root / ".github/gitleaks.sh").write_bytes(pinned.encode())
    runner = tmp_path / "runner"
    runner.mkdir()
    (runner / "summary").touch()
    env = {
        # By its path in the folder of the test, which tar of Git for Windows reads as a
        # path, where it takes C:/… for a host; on the runners it is /home/runner/….
        "RUNNER_TEMP": "runner",
        "GITHUB_STEP_SUMMARY": (runner / "summary").as_posix(),
        "GH_TOKEN": "of-the-job",
    }
    assert GITLEAKS_VERSION
    version = GITLEAKS_VERSION[1]

    for _ in range(2):
        result, calls = script(
            tmp_path,
            "gitleaks.sh",
            plan=(TIMEOUT, "asset"),
            asset=release,
            env=env,
            root=root,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    # Through the API, once, and again after an error of GitHub: the second scan of
    # the job takes the gitleaks of the first, which never sees the token.
    download = (
        f"gh release download v{version} --repo gitleaks/gitleaks --pattern"
        f" gitleaks_{version}_linux_x64.tar.gz --output runner/gitleaks.tar.gz --clobber"
    )
    assert [call for call in calls if call.startswith("gh ")] == [download, download]
    scans = [call for call in calls if call.startswith("gitleaks ")]
    assert len(scans) == 2
    assert all(scan.endswith(" token none none") for scan in scans)
    assert sorted(path.name for path in (runner / f"gitleaks-{version}").iterdir()) == [
        "gitleaks"
    ]
    assert not (runner / "gitleaks.tar.gz").exists()


@pytest.mark.parametrize(
    ("base", "head", "arguments"),
    [
        ("a" * 40, "b" * 40, f" [{'a' * 40}] [{'b' * 40}]"),
        # The weekly scan, and one by hand, of the whole history.
        ("", "", ""),
    ],
)
def test_the_secret_scan_hands_the_commits_of_a_pull_request_to_gitleaks(
    tmp_path: Path, base: str, head: str, arguments: str
) -> None:
    done = run_step(
        tmp_path,
        "secret-scan.yml",
        "gitleaks",
        "Scan tracked history for exposed secrets",
        env={"BASE_SHA": base, "HEAD_SHA": head},
        # A stand-in that writes down its arguments, each in brackets.
        files={
            ".github/gitleaks.sh": (
                'line=gitleaks.sh\nfor argument; do line+=" [$argument]"; done\n'
                'echo "$line" >> "$STUB_CALLS"\n'
            )
        },
    )

    assert done.returncode == 0, done.stderr
    assert done.stubbed == [f"gitleaks.sh{arguments}"]


# CodeQL, from the tool cache of the runner or through the API.

CODEQL_STEP = "Download the CodeQL of the action unless the runner has it"


def test_codeql_analyzes_with_the_codeql_of_the_action() -> None:
    init = step("codeql.yml", "codeql", "Initialize the analysis")
    assert init["with"]["tools"] == "${{ steps.bundle.outputs.tools || 'linked' }}"
    bundle = step("codeql.yml", "codeql", CODEQL_STEP)
    assert bundle["id"] == "bundle"
    assert bundle["env"] == {"GH_TOKEN": "${{ github.token }}"}
    assert bundle["if"] == "vars.CODE_SCANNING != 'off'"


def find_codeql(
    tmp_path: Path, cached: Sequence[str], actions: int = 1, downloaded: int = 0
) -> StepResult:
    """Runs the step on a runner whose tool cache has the versions of CodeQL in cached,
    with the codeql-action of the job, in the folder of the actions of the runner,
    actions times, and with a stand-in for .github/download.sh that ends with
    downloaded."""
    work = tmp_path / "work"
    for number in range(actions):
        defaults = work / f"_actions/github/codeql-action/{number}abc/src/defaults.json"
        defaults.parent.mkdir(parents=True)
        defaults.write_text(
            json.dumps(
                {"bundleVersion": "codeql-bundle-v2.27.3", "cliVersion": "2.27.3"}
            ),
            encoding="utf-8",
        )
    tools = tmp_path / "toolcache"
    for version in cached:
        (tools / "CodeQL" / version).mkdir(parents=True)
        (tools / "CodeQL" / version / "x64.complete").touch()
    return run_step(
        tmp_path,
        "codeql.yml",
        "codeql",
        CODEQL_STEP,
        env={
            "RUNNER_WORKSPACE": (work / "r").as_posix(),
            "RUNNER_TOOL_CACHE": tools.as_posix(),
        },
        files={
            ".github/download.sh": recording("download.sh", f"exit {downloaded}"),
        },
    )


@WITH_JQ
def test_codeql_comes_from_the_tool_cache_of_the_runner(tmp_path: Path) -> None:
    done = find_codeql(tmp_path, ["2.27.2", "2.27.3"])

    assert done.returncode == 0, done.stderr
    assert done.stubbed == []
    assert done.outputs == {}
    assert done.summary == (
        "CodeQL 2.27.3 of the action comes from the tool cache of the runner.\n"
    )


@WITH_JQ
def test_codeql_that_the_runner_lacks_comes_through_the_api(tmp_path: Path) -> None:
    # As on 8 November 2026: the runner had 2.27.2, the action brought a newer one.
    done = find_codeql(tmp_path, ["2.27.2"])

    assert done.returncode == 0, done.stderr
    tools = f"{done.runner_temp.as_posix()}/codeql-bundle/codeql-bundle-linux64.tar.zst"
    # Checked by the digest that GitHub keeps, which the call names no pin for.
    assert done.stubbed == [
        "download.sh github/codeql-action codeql-bundle-v2.27.3"
        f" codeql-bundle-linux64.tar.zst {tools}"
    ]
    assert done.outputs == {"tools": tools}


@WITH_JQ
def test_codeql_that_cant_be_downloaded_fails_the_job(tmp_path: Path) -> None:
    done = find_codeql(tmp_path, [], downloaded=1)

    assert done.returncode == 1
    assert done.outputs == {}


@pytest.mark.parametrize("actions", [0, 2])
def test_without_the_one_codeql_action_the_action_looks_itself(
    tmp_path: Path, actions: int
) -> None:
    done = find_codeql(tmp_path, [], actions=actions)

    assert done.returncode == 0, done.stderr
    assert done.stubbed == []
    assert done.outputs == {}
    assert (
        "::notice::The CodeQL of the action is not where the runner keeps it; the action"
        " looks for it itself." in done.stdout
    )


# The other tools of the workflows, through .github/download.sh.


def test_the_tools_of_a_release_come_through_the_api_before_the_checkout(
    tmp_path: Path,
) -> None:
    for publish_to in ("pypi", "nextcloud-appstore"):
        folder = tmp_path / publish_to
        done = run_step(
            folder,
            "build-release.yml",
            "assets",
            "Download the tools of the build",
            answers=[
                exact(
                    "api -H Accept: application/vnd.github.raw+json"
                    f" repos/o/r/contents/.github/download.sh?ref={SHA}",
                    recording("download.sh"),
                )
            ],
            env={"PUBLISH_TO": publish_to},
        )

        assert done.returncode == 0, done.stderr
        runner = done.runner_temp.as_posix()
        build = step("build-release.yml", "assets", "Download the tools of the build")
        assert build["env"] == {"GH_TOKEN": "${{ github.token }}"}
        job_env = job("build-release.yml", "assets")["env"]
        syft, krankerl = job_env["SBOM_SYFT_VERSION"], job_env["KRANKERL_VERSION"]
        expected = [
            f"download.sh anchore/syft v{syft} syft_{syft}_linux_amd64.tar.gz"
            f" {runner}/syft.tar.gz {job_env['SBOM_SYFT_SHA256']}"
        ]
        if publish_to == "nextcloud-appstore":
            expected.append(
                f"download.sh ChristophWurst/krankerl v{krankerl}"
                f" krankerl_{krankerl}_amd64.deb {runner}/krankerl.deb"
                f" {job_env['KRANKERL_SHA256']}"
            )
        assert done.stubbed == expected


def test_no_step_that_builds_the_project_holds_the_token_of_the_release() -> None:
    # The token of the job may write the release: the steps that build the project or
    # run a tool on it don't have it, and the tools come in a step of their own before
    # the checkout.
    found = job("build-release.yml", "assets")
    names = [each.get("name") for each in found["steps"]]
    checkout = next(
        index
        for index, each in enumerate(found["steps"])
        if each.get("uses", "").startswith("actions/checkout@")
    )
    assert names.index("Download the tools of the build") == checkout - 1
    for name in (
        "Take the assets of the project",
        "Build the Nextcloud app",
        "Describe it in the SBOMs, as SPDX and as CycloneDX",
    ):
        each = step("build-release.yml", "assets", name)
        assert "github.token" not in json.dumps(each.get("env", {})), name


def test_infection_comes_through_the_api(tmp_path: Path) -> None:
    done = run_step(
        tmp_path,
        "mutation.yml",
        "mutation",
        "Download Infection",
        files={".github/download.sh": recording("download.sh")},
    )

    assert done.returncode == 0, done.stderr
    variables = job("mutation.yml", "mutation")["env"]
    version, sha256 = variables["INFECTION_VERSION"], variables["INFECTION_SHA256"]
    assert done.stubbed == [
        f"download.sh infection/infection {version} infection.phar"
        f" {done.runner_temp.as_posix()}/infection.phar {sha256}",
    ]
    infection = step("mutation.yml", "mutation", "Download Infection")
    assert infection["env"] == {"GH_TOKEN": "${{ github.token }}"}


def test_no_step_that_installs_the_project_for_the_mutants_holds_the_token() -> None:
    # composer install runs the Composer scripts and plugins of the project: Infection
    # comes before it, in a step of its own, and the steps that run the project's code
    # don't get the token of the job.
    found = job("mutation.yml", "mutation")
    names = [each.get("name") for each in found["steps"]]
    assert names.index("Download Infection") < names.index("Install the locked tools")
    for name in ("Install the locked tools", "Run the mutants against the tests"):
        each = step("mutation.yml", "mutation", name)
        assert "github.token" not in json.dumps(each.get("env", {})), name
        assert "GITHUB_TOKEN" not in json.dumps(each.get("env", {})), name


def test_the_fake_gh_writes_a_downloaded_asset_into_its_file(tmp_path: Path) -> None:
    (tmp_path / "root/.github/workflows").mkdir(parents=True)
    (tmp_path / "root/.github/workflows/demo.yml").write_text(
        "on: push\njobs:\n  demo:\n    runs-on: ubuntu-24.04\n    steps:\n"
        "      - name: Download\n        run: |\n"
        "          gh release download v1 --repo o/tool --pattern tool --output tool\n"
        "          gh release download v1 --repo o/tool --pattern tool --output - > out\n"
        "          gh release download v2 --repo o/tool --pattern tool --output gone"
        " || true\n",
        encoding="utf-8",
    )

    done = run_step(
        tmp_path,
        "demo.yml",
        "demo",
        "Download",
        answers=[
            Answer(r"release download v1 .*", "the tool\n"),
            Answer(r"release download v2 .*", "an error page\n", code=1),
        ],
        root=tmp_path / "root",
    )

    assert done.returncode == 0, done.stderr
    assert (done.workspace / "tool").read_text(encoding="utf-8") == "the tool\n"
    assert (done.workspace / "out").read_text(encoding="utf-8") == "the tool\n"
    assert not (done.workspace / "gone").exists()
