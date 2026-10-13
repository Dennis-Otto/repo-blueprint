"""Tests of the signed tags of releases: .github/sign-tag.sh and the step of the release
workflow that runs it, in bash, with GitHub as a repository in a folder and stubs of
gitsign, gh and the downloads."""

from __future__ import annotations

import os
import shutil
import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path

import pytest
from shell import BASH, in_bash

ROOT = Path(__file__).parents[1]
GIT = shutil.which("git")
pytestmark = pytest.mark.skipif(
    BASH is None or GIT is None,
    reason="the scripts run in bash, Git Bash on Windows, with git",
)
RELEASE_WORKFLOW = "o/r/.github/workflows/release.yml@refs/heads/main"


# The outcomes that a test plans for a stub, one per call and line; none succeeds.
NEXT = """#!/usr/bin/env bash
next() {
  outcome="$(head -n 1 "$STUBS/$1")"
  tail -n +2 "$STUBS/$1" > "$STUBS/$1.next" && mv "$STUBS/$1.next" "$STUBS/$1"
}
"""
STUBS = {
    # git, with GitHub as the repository in $REMOTE. A push that the plan fails gets
    # GitHub's transient error; one that landed takes the tag and fails all the same.
    "git": NEXT
    + """arguments=()
for argument in "$@"; do
  [[ "$argument" == https://github.com/o/r.git ]] && argument="$REMOTE"
  arguments+=("$argument")
done
case " $* " in
  *" push "*)
    tag="${arguments[-1]#refs/tags/}"
    commit="$("$REAL_GIT" rev-parse "refs/tags/$tag^{commit}")"
    next push
    echo "push ${outcome:-ok}" >> "$CALLS"
    case "$outcome" in
      fail) echo "remote: fatal error in commit_refs" >&2; exit 1 ;;
      landed) "$REAL_GIT" "${arguments[@]}" 2>/dev/null; echo "remote: fatal error in commit_refs" >&2; exit 1 ;;
      # Another tag got there first, at the same commit: one without a signature, or
      # one that the release workflow signed.
      raced) "$REAL_GIT" -C "$REMOTE" tag "$tag" "$commit" ;;
      raced-signed)
        signing=(-c gpg.format=x509 -c "gpg.x509.program=$RUNNER_TEMP/gitsign")
        identity=(-c user.name=Bot -c user.email=bot@example.com)
        "$REAL_GIT" -C "$REMOTE" "${signing[@]}" "${identity[@]}" tag --sign -m earlier "$tag" "$commit"
        ;;
    esac
    ;;
  # GitHub fails for a moment.
  *" ls-remote "* | *" fetch "*)
    command=fetch
    [[ " $* " == *" ls-remote "* ]] && command=ls-remote
    next "$command"
    echo "$command ${outcome:-ok}" >> "$CALLS"
    if [[ "$outcome" == fail ]]; then
      echo "fatal: unable to access 'https://github.com/o/r.git/': The requested URL returned error: 502" >&2
      exit 128
    fi
    ;;
esac
exec "$REAL_GIT" "${arguments[@]}"
""",
    # gitsign, which the stub of curl downloads: it signs for git as the workflow in
    # GITHUB_WORKFLOW_REF, unless the plan fails it, and checks a signed tag's identity.
    "gitsign": NEXT
    + """if [[ "$1" == verify-tag ]]; then
  next verify
  echo "verify-tag $2" >> "$CALLS"
  # Sigstore doesn't answer.
  if [[ "$outcome" == offline ]]; then
    echo "Error: Get \"https://rekor.sigstore.dev/api/v1/log/entries\": dial tcp: lookup rekor.sigstore.dev: no such host" >&2
    exit 1
  fi
  tag="$(git cat-file tag "$2")" || exit 1
  [[ "$tag" == *"identity $4 issuer $6"* ]]
  exit
fi
cat > /dev/null
next sign
echo "sign ${outcome:-ok}" >> "$CALLS"
if [[ "$outcome" == fail ]]; then
  echo "error signing: the transparency log is unavailable" >&2
  exit 1
fi
printf -- '-----BEGIN SIGNED MESSAGE-----\\nidentity https://github.com/%s issuer https://token.actions.githubusercontent.com\\n-----END SIGNED MESSAGE-----\\n' "$GITHUB_WORKFLOW_REF"
printf '\\n[GNUPG:] SIG_CREATED D 1 8 00 0 STUB\\n' >&2
""",
    # The download of gitsign, which fails when the plan says so.
    "curl": NEXT
    + """next download
echo "curl $*" >> "$CALLS"
if [[ "$outcome" == fail ]]; then
  echo "curl: (22) The requested URL returned error: 502" >&2
  exit 22
fi
while (($# > 0)); do
  if [[ "$1" == --output ]]; then cp "$STUBS/gitsign" "$2"; fi
  shift
done
""",
    "sha256sum": NEXT
    + """next checksum
echo "sha256sum $* $(cat)" >> "$CALLS"
if [[ "$outcome" == fail ]]; then
  echo "sha256sum: WARNING: 1 computed checksum did NOT match" >&2
  exit 1
fi
""",
    "sleep": """#!/usr/bin/env bash
echo "sleep $*" >> "$CALLS"
""",
}


@dataclass
class GitHub:
    """A repository on GitHub, in a folder, and the shallow checkout of a run."""

    remote: Path
    work: Path
    stubs: Path
    calls: Path
    environment: dict[str, str]
    # The merge of the release pull request, and the later commit of the run.
    release: str = ""
    head: str = ""

    def git(self, *arguments: str, cwd: Path | None = None) -> str:
        assert GIT
        return subprocess.run(
            [GIT, *arguments],
            cwd=cwd or self.remote,
            env=self.environment,
            capture_output=True,
            encoding="utf-8",
            check=True,
        ).stdout.strip()

    def plan(self, stub: str, *outcomes: str) -> None:
        (self.stubs / stub).write_text(
            "".join(f"{outcome}\n" for outcome in outcomes),
            encoding="utf-8",
            newline="\n",
        )

    def sign_tag(
        self, *arguments: str, workflow: str = RELEASE_WORKFLOW
    ) -> subprocess.CompletedProcess[str]:
        self.calls.write_text("", encoding="utf-8")
        return subprocess.run(
            in_bash((ROOT / ".github/sign-tag.sh").as_posix(), *arguments),
            cwd=self.work,
            env={**self.environment, "GITHUB_WORKFLOW_REF": workflow},
            capture_output=True,
            encoding="utf-8",
            check=False,
        )

    def signs(self, *arguments: str, workflow: str = RELEASE_WORKFLOW) -> None:
        result = self.sign_tag(*arguments, workflow=workflow)
        assert result.returncode == 0, result.stdout + result.stderr

    def tag(self, name: str) -> tuple[str, str]:
        """The type of the tag on GitHub and the commit it points at."""
        return (
            self.git("cat-file", "-t", f"refs/tags/{name}"),
            self.git("rev-parse", f"refs/tags/{name}^{{commit}}"),
        )


@pytest.fixture
def github(tmp_path: Path) -> GitHub:
    assert GIT
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    for name, text in STUBS.items():
        (stubs / name).write_text(text, encoding="utf-8", newline="\n")
        (stubs / name).chmod(0o755)
    for plan in (
        "push",
        "sign",
        "ls-remote",
        "fetch",
        "download",
        "checksum",
        "verify",
    ):
        (stubs / plan).touch()
    (tmp_path / "runner").mkdir()
    (tmp_path / "gitconfig").touch()
    calls = tmp_path / "calls"
    environment = {
        **os.environ,
        # No configuration of this machine, such as signed commits, gets in the way.
        "GIT_CONFIG_GLOBAL": (tmp_path / "gitconfig").as_posix(),
        "GIT_CONFIG_NOSYSTEM": "1",
        "PATH": f"{stubs}{os.pathsep}{os.environ['PATH']}",
        "REAL_GIT": Path(GIT).as_posix(),
        "REMOTE": (tmp_path / "remote.git").as_posix(),
        "STUBS": stubs.as_posix(),
        "CALLS": calls.as_posix(),
        "RUNNER_TEMP": (tmp_path / "runner").as_posix(),
        "GITHUB_REPOSITORY": "o/r",
    }
    world = GitHub(
        tmp_path / "remote.git", tmp_path / "work", stubs, calls, environment
    )
    world.git("init", "--quiet", "--bare", str(world.remote), cwd=tmp_path)
    seed = tmp_path / "seed"
    world.git("init", "--quiet", str(seed), cwd=tmp_path)
    author = ("-c", "user.name=Dev", "-c", "user.email=dev@example.com")
    world.git(*author, "commit", "--quiet", "--allow-empty", "-m", "v1", cwd=seed)
    world.release = world.git("rev-parse", "HEAD", cwd=seed)
    world.git(*author, "commit", "--quiet", "--allow-empty", "-m", "later", cwd=seed)
    world.head = world.git("rev-parse", "HEAD", cwd=seed)
    world.git("push", "--quiet", str(world.remote), "HEAD:refs/heads/main", cwd=seed)
    # As actions/checkout leaves it: the commit of the run alone.
    world.git(
        "clone",
        "--quiet",
        "--depth=1",
        "--branch=main",
        f"file://{world.remote.as_posix()}",
        str(world.work),
        cwd=tmp_path,
    )
    world.environment["GITHUB_SHA"] = world.head
    return world


def test_the_tag_of_a_release_is_signed_at_its_commit(github: GitHub) -> None:
    # The merge of the release pull request is older than the commit of the run, and
    # not in its shallow checkout.
    assert github.git("rev-list", "HEAD", cwd=github.work) == github.head

    result = github.sign_tag("v1.0.0", github.release)

    assert result.returncode == 0, result.stdout + result.stderr
    assert github.tag("v1.0.0") == ("tag", github.release)
    message = github.git("cat-file", "tag", "v1.0.0")
    assert f"identity https://github.com/{RELEASE_WORKFLOW} " in message
    calls = github.calls.read_text(encoding="utf-8")
    assert "--retry 5 --retry-all-errors --connect-timeout 15" in calls
    assert "69213a8a0813a151e5a47d0060862952ff833a845d57309dff76f7ba6600abae" in calls
    assert "sleep" not in calls


def test_a_beta_is_signed_at_the_commit_of_the_run(github: GitHub) -> None:
    result = github.sign_tag("v1.1.0-beta.1")

    assert result.returncode == 0, result.stdout + result.stderr
    assert github.tag("v1.1.0-beta.1") == ("tag", github.head)


@pytest.mark.parametrize(
    ("pushes", "pushed", "sleeps"),
    [
        # GitHub fails for a moment; the next attempt goes through.
        (["fail"], ["fail", "ok"], ["10"]),
        (["fail", "fail"], ["fail", "fail", "ok"], ["10", "20"]),
        # GitHub took the tag but reported an error.
        (["landed"], ["landed"], []),
    ],
)
def test_a_push_that_fails_for_a_moment_is_tried_again(
    github: GitHub, pushes: list[str], pushed: list[str], sleeps: list[str]
) -> None:
    github.plan("push", *pushes)

    result = github.sign_tag("v1.0.0", github.release)

    assert result.returncode == 0, result.stdout + result.stderr
    assert github.tag("v1.0.0") == ("tag", github.release)
    calls = github.calls.read_text(encoding="utf-8").splitlines()
    assert [call.split()[1] for call in calls if call.startswith("push ")] == pushed
    assert [call.split()[1] for call in calls if call.startswith("sleep ")] == sleeps
    # Every attempt pushes the same signed tag.
    assert calls.count("sign ok") == 1


def test_a_push_that_keeps_failing_fails(github: GitHub) -> None:
    github.plan("push", "fail", "fail", "fail")

    result = github.sign_tag("v1.0.0", github.release)

    assert result.returncode == 1
    assert "::error::The tag v1.0.0 could not be pushed." in result.stdout
    assert github.git("tag", "--list") == ""
    calls = github.calls.read_text(encoding="utf-8").splitlines()
    assert [call for call in calls if call.startswith(("push ", "sleep "))] == [
        "push fail",
        "sleep 10",
        "push fail",
        "sleep 20",
        "push fail",
    ]


def test_the_tag_of_an_earlier_run_is_kept(github: GitHub) -> None:
    # A run that failed after it pushed the tag, before release-please created the
    # release on it.
    github.signs("v1.0.0", github.release)
    earlier = github.git("rev-parse", "refs/tags/v1.0.0")

    result = github.sign_tag("v1.0.0", github.release)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "The tag v1.0.0 is signed by the release workflow" in result.stdout
    assert github.git("rev-parse", "refs/tags/v1.0.0") == earlier
    calls = github.calls.read_text(encoding="utf-8").splitlines()
    assert not [call for call in calls if call.startswith(("sign ", "push "))]


@pytest.mark.parametrize("push", ["", "raced"])
def test_a_tag_that_someone_else_pushed_first_stops_the_signing(
    github: GitHub, push: str
) -> None:
    # Before the run looks, or between its look and its push.
    if push:
        github.plan("push", push)
    else:
        github.git("tag", "v1.0.0", github.release)

    result = github.sign_tag("v1.0.0", github.release)

    assert result.returncode == 1
    assert "::error::The tag v1.0.0 is not a signed tag" in result.stdout
    assert github.tag("v1.0.0") == ("commit", github.release)
    # No attempt changes that.
    assert "sleep" not in github.calls.read_text(encoding="utf-8")


def test_a_tag_of_the_release_workflow_that_came_first_will_do(github: GitHub) -> None:
    github.plan("push", "raced-signed")

    result = github.sign_tag("v1.0.0", github.release)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "The tag v1.0.0 is signed by the release workflow" in result.stdout
    assert github.tag("v1.0.0") == ("tag", github.release)
    assert "earlier" in github.git("cat-file", "tag", "v1.0.0")


@pytest.mark.parametrize(
    ("command", "arguments"),
    [
        # The look for the tag, the fetch of the merge that the shallow checkout
        # lacks, and the fetch of the tag to verify.
        ("ls-remote", ("v1.0.0", "release")),
        ("fetch", ("v1.0.0", "release")),
        ("fetch", ("verify", "v1.0.0", "release")),
    ],
)
def test_github_is_asked_again_when_it_fails_for_a_moment(
    github: GitHub, command: str, arguments: tuple[str, ...]
) -> None:
    if arguments[0] == "verify":
        github.signs("v1.0.0", github.release)
    github.plan(command, "fail", "fail")

    result = github.sign_tag(
        *(
            github.release if argument == "release" else argument
            for argument in arguments
        )
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert github.tag("v1.0.0") == ("tag", github.release)
    calls = github.calls.read_text(encoding="utf-8").splitlines()
    assert [call for call in calls if call.startswith((f"{command} ", "sleep "))][
        :5
    ] == [
        f"{command} fail",
        "sleep 10",
        f"{command} fail",
        "sleep 20",
        f"{command} ok",
    ]


@pytest.mark.parametrize(
    ("command", "arguments", "error", "code"),
    [
        ("ls-remote", ("v1.0.0",), "The tags on GitHub could not be read.", 1),
        # The verification couldn't check the tag, which says nothing about it.
        ("fetch", ("verify", "v1.0.0"), "The tag v1.0.0 could not be fetched", 2),
    ],
)
def test_github_that_keeps_failing_fails(
    github: GitHub, command: str, arguments: tuple[str, ...], error: str, code: int
) -> None:
    github.plan(command, "fail", "fail", "fail")

    result = github.sign_tag(*arguments, github.release)

    assert result.returncode == code
    assert f"::error::{error}" in result.stdout
    assert github.git("tag", "--list") == ""


@pytest.mark.parametrize(
    ("stub", "error"),
    [
        ("download", "gitsign 0.17.1 could not be downloaded."),
        ("checksum", "The download of gitsign 0.17.1 doesn't have the checksum"),
    ],
)
@pytest.mark.parametrize("arguments", [("v1.0.0",), ("verify", "v1.0.0")])
def test_without_gitsign_nothing_is_signed_or_verified(
    github: GitHub, stub: str, error: str, arguments: tuple[str, ...]
) -> None:
    github.plan(stub, "fail")

    result = github.sign_tag(*arguments, github.release)

    # 2, as for a verification that couldn't check the tag.
    assert result.returncode == 2
    assert f"::error::{error}" in result.stdout
    assert github.git("tag", "--list") == ""
    calls = github.calls.read_text(encoding="utf-8").splitlines()
    assert not any(call.startswith(("fetch ", "ls-remote ", "sign ")) for call in calls)


def test_a_signature_that_fails_for_a_moment_is_made_anew(github: GitHub) -> None:
    github.plan("sign", "fail")

    result = github.sign_tag("v1.0.0", github.release)

    assert result.returncode == 0, result.stdout + result.stderr
    calls = github.calls.read_text(encoding="utf-8").splitlines()
    assert [call for call in calls if call.startswith(("sign ", "sleep "))] == [
        "sign fail",
        "sleep 10",
        "sign ok",
    ]
    assert github.tag("v1.0.0") == ("tag", github.release)


def test_a_tag_of_the_release_workflow_at_the_release_verifies(
    github: GitHub,
) -> None:
    github.signs("v1.0.0", github.release)

    result = github.sign_tag("verify", "v1.0.0", github.release)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "The tag v1.0.0 is signed by the release workflow" in result.stdout


def test_sigstore_that_fails_for_a_moment_is_asked_again(github: GitHub) -> None:
    github.signs("v1.0.0", github.release)
    github.plan("verify", "offline", "offline")

    result = github.sign_tag("verify", "v1.0.0", github.release)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "The tag v1.0.0 is signed by the release workflow" in result.stdout
    calls = github.calls.read_text(encoding="utf-8").splitlines()
    assert [call for call in calls if call.startswith(("verify-tag ", "sleep "))] == [
        "verify-tag v1.0.0",
        "sleep 10",
        "verify-tag v1.0.0",
        "sleep 20",
        "verify-tag v1.0.0",
    ]


def test_sigstore_that_keeps_failing_leaves_the_tag_unchecked(github: GitHub) -> None:
    github.signs("v1.0.0", github.release)
    github.plan("verify", "offline", "offline", "offline")

    result = github.sign_tag("verify", "v1.0.0", github.release)

    # 2: the tag may well be signed, which the next run can check.
    assert result.returncode == 2
    assert (
        "::error::The signature of the tag v1.0.0 could not be checked: Sigstore"
        " didn't answer." in result.stdout
    )
    assert "dial tcp: lookup rekor.sigstore.dev: no such host" in result.stdout
    assert "isn't one of the release workflow" not in result.stdout


@pytest.mark.parametrize(
    ("make", "error"),
    [
        ("lightweight", "The tag v1.0.0 is not a signed tag"),
        ("elsewhere", "The tag v1.0.0 points at"),
        ("other workflow", "The signature of the tag v1.0.0 isn't one of the release"),
    ],
)
def test_any_other_tag_fails_the_verification(
    github: GitHub, make: str, error: str
) -> None:
    if make == "lightweight":
        github.git("tag", "v1.0.0", github.release)
    elif make == "elsewhere":
        github.signs("v1.0.0", github.head)
    else:
        workflow = "o/r/.github/workflows/ci.yml@refs/heads/main"
        github.signs("v1.0.0", github.release, workflow=workflow)

    result = github.sign_tag("verify", "v1.0.0", github.release)

    assert result.returncode == 1
    assert f"::error::{error}" in result.stdout


def test_the_signed_tag_of_another_version_fails_the_verification(
    github: GitHub,
) -> None:
    # A new ref at the signed tag of an older release: its commit is on main and the
    # release workflow signed it, but for v1.0.0, so a bot must not take it as v9.9.9.
    github.signs("v1.0.0", github.release)
    signed = github.git("rev-parse", "refs/tags/v1.0.0")
    github.git("update-ref", "refs/tags/v9.9.9", signed)

    result = github.sign_tag("verify", "v9.9.9", github.release)

    assert result.returncode == 1
    assert (
        "::error::The tag v9.9.9 is the signed tag v1.0.0 of another version"
        in result.stdout
    )
    calls = github.calls.read_text(encoding="utf-8").splitlines()
    assert not [call for call in calls if call.startswith("verify-tag ")]


@pytest.mark.parametrize(
    ("workflow", "verified"),
    [
        (RELEASE_WORKFLOW, True),
        # The release workflow of the repository that runs the check, not of o/r.
        ("o/project/.github/workflows/release.yml@refs/heads/main", False),
    ],
)
def test_the_tag_of_another_repository_verifies_against_its_release_workflow(
    github: GitHub, workflow: str, verified: bool
) -> None:
    # As the blueprint bot of o/project checks a release of its blueprint, o/r.
    github.signs("v1.0.0", github.release, workflow=workflow)
    github.environment["GITHUB_REPOSITORY"] = "o/project"

    result = github.sign_tag("verify", "v1.0.0", github.release, "o/r")

    if verified:
        assert result.returncode == 0, result.stdout + result.stderr
        assert "The tag v1.0.0 is signed by the release workflow" in result.stdout
    else:
        assert result.returncode == 1
        assert "::error::The signature of the tag v1.0.0 isn't one" in result.stdout
    calls = github.calls.read_text(encoding="utf-8").splitlines()
    assert "fetch ok" in calls
    assert "verify-tag v1.0.0" in calls


def sign_step() -> str:
    release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    start = release.index("      - name: Sign the tag of a release")
    return release[start : release.index("      - name:", start + 1)]


def run_the_sign_step(
    tmp_path: Path, pending: str, failures: int = 0, status: int = 0
) -> tuple[subprocess.CompletedProcess[str], list[str], str, str]:
    step = sign_step()
    run = "        run: |\n"
    script = textwrap.dedent(step[step.index(run) + len(run) :])
    (tmp_path / "step.sh").write_text(script, encoding="utf-8", newline="\n")
    # gh answers as the API does, after the filters of jq, once it has failed as often
    # as planned; the script of the tags only records how it is called.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stubs = {
        "gh": """#!/usr/bin/env bash
echo "gh $1 $2" >> "$CALLS"
if [[ "$1 $2" != "api graphql" ]]; then
  echo "unexpected: gh $*" >&2
  exit 1
fi
failures="$(cat "$FAILURES")"
if ((failures > 0)); then
  echo $((failures - 1)) > "$FAILURES"
  echo "gh: Bad Gateway (HTTP 502)" >&2
  exit 1
fi
printf '%s\\n' "$PENDING"
""",
        "sleep": '#!/usr/bin/env bash\necho "sleep $*" >> "$CALLS"\n',
    }
    for name, text in stubs.items():
        (bin_dir / name).write_text(text, encoding="utf-8", newline="\n")
        (bin_dir / name).chmod(0o755)
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github/sign-tag.sh").write_text(
        'echo "sign-tag.sh $*" >> "$CALLS"\nexit "$STATUS"\n',
        encoding="utf-8",
        newline="\n",
    )
    calls = tmp_path / "calls"
    summary = tmp_path / "summary"
    output = tmp_path / "output"
    for file in (calls, summary, output):
        file.touch()
    (tmp_path / "failures").write_text(f"{failures}\n", encoding="utf-8")
    environment = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "GITHUB_REPOSITORY": "o/r",
        "GITHUB_STEP_SUMMARY": str(summary),
        "GITHUB_OUTPUT": str(output),
        "STUBS": str(bin_dir),
        "CALLS": str(calls),
        "FAILURES": str(tmp_path / "failures"),
        "PENDING": pending,
        "STATUS": str(status),
    }
    # As GitHub runs a step: bash -e.
    result = subprocess.run(
        in_bash("-e", "step.sh"),
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    recorded = calls.read_text(encoding="utf-8").splitlines()
    signed = [line for line in recorded if line.startswith("sign-tag.sh ")]
    # GitHub is asked three times, 10 and 20 seconds apart.
    sleeps = [line for line in recorded if line.startswith("sleep ")]
    assert sleeps == ["sleep 10", "sleep 20"][: min(failures, 2)]
    return (
        result,
        signed,
        summary.read_text(encoding="utf-8"),
        output.read_text(encoding="utf-8"),
    )


@pytest.mark.parametrize(
    ("pending", "failures", "signed"),
    [
        # No release pull request was merged, or its release exists.
        ("", 0, []),
        # The run of the merge, or the next one when that run was lost; sign-tag.sh
        # keeps the tag of a run that failed after it pushed the tag.
        ("abc123 1.2.0", 0, ["sign-tag.sh v1.2.0 abc123"]),
        (
            "abc123 1.2.0\ndef456 1.1.0",
            0,
            ["sign-tag.sh v1.2.0 abc123", "sign-tag.sh v1.1.0 def456"],
        ),
        # GitHub fails for a moment.
        ("abc123 1.2.0", 2, ["sign-tag.sh v1.2.0 abc123"]),
    ],
)
def test_every_run_signs_the_tag_of_a_merged_release_pull_request(
    tmp_path: Path, pending: str, failures: int, signed: list[str]
) -> None:
    result, calls, summary, output = run_the_sign_step(tmp_path, pending, failures)

    assert result.returncode == 0, result.stdout + result.stderr
    assert calls == signed
    for call in signed:
        assert f"The tag {call.split()[-2]} is signed." in summary
    # release-please creates a release only once the step has signed its tag.
    assert output == ("signed=true\n" if signed else "")


@pytest.mark.parametrize(
    ("failures", "status", "error"),
    [
        (3, 0, "::error::The merged release pull requests could not be read."),
        # A tag that fails the verification.
        (0, 1, ""),
    ],
)
def test_a_step_that_fails_creates_no_release(
    tmp_path: Path, failures: int, status: int, error: str
) -> None:
    result, calls, summary, output = run_the_sign_step(
        tmp_path, "abc123 1.2.0", failures, status
    )

    assert result.returncode == 1
    assert error in result.stdout
    assert calls == ([] if failures else ["sign-tag.sh v1.2.0 abc123"])
    assert summary == ""
    assert output == ""
