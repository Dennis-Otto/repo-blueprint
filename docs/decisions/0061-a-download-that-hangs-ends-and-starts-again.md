# A download that hangs ends within its step and starts again

- Status: accepted
- Date: 2026-10-24

## Context

Since every step that installs, builds or downloads ends after five minutes ([0021](0021-install-with-uv-and-bound-every-step.md)), a download that hangs no longer holds a pull request for half an hour, but it still fails its job. The flaky-test bot runs such a job once more ([0014](0014-recover-from-a-stalled-check-without-a-person.md)) and writes it into [issue 179](https://github.com/Dennis-Otto/repo-blueprint/issues/179). From 2026-10-14 to 2026-10-23, it wrote down eight such jobs of the Variants, seven of them in three kinds:

- **The build of the website hung** four times until its step ran out of its five minutes, after the last font that the privacy plugin of Material downloaded. The privacy plugin gives each download 5 seconds, but the social plugin downloads the fonts of the preview cards from Google Fonts with no time limit at all. `.github/mkdocs_blueprint.py` already tried a download of both plugins again after an error of the network ([0011](0011-downloads-try-again-and-checks-cache-their-tools.md)), but a server that stops answering raises no error: the attempt waits without end. The Docs workflow of every repository builds its website with the same plugins.
- **The download of uv hung** in two legs at once, on `releases.astral.sh`, which `astral-sh/setup-uv` downloads uv from, with no time limit of its own; the step usually takes three seconds.
- **Docker Hub answered the pull of an image with a 502**, and `docker run` exited with 125 before the lint of the workflows ran.

The eighth job hung in the pre-step of harden-runner, before any step of the workflow ran, which no setting of a step bounds.

## Options

1. Leave it to the flaky-test bot. Every hang costs a job of up to ten minutes again, and the pull request waits for it.
2. Run the whole step again when it fails, in a loop around each command. A loop around `mkdocs build` builds everything again for one font; GitHub has no setting to run a step of an action, such as `setup-uv`, again.
3. A time limit for each download, well within its step, and a second attempt of that download alone: in the hooks of the website for every download of the plugins, a second `setup-uv` from another server when the first doesn't end within two minutes, and a `docker` in front of the runner's that starts a container again when the pull of its image failed.

## Decision

Option 3.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/how-a-download-that-hangs-starts-again.dark.svg">
  <img src="../images/diagrams/how-a-download-that-hangs-starts-again.svg" alt="How a download that hangs starts again: Each download gets a limit of its own, well within the five minutes of its step, and a second or third attempt when it fails or hangs. A download of the website ends after 10 seconds without a connection or 30 without the next part of the file, and the hooks try it again after a second and then two. The setup of uv in the Variants gives way after two minutes to a second one from the releases of uv on GitHub. A container whose image failed to download starts again after 10 and then 20 seconds. Only what fails every attempt fails its step, and the flaky-test bot runs that job once more.">
</picture>

- **The website:** a download of the privacy or the social plugin that names no time limit gets 10 seconds to connect and 30 for each next part of the file (`TIMEOUT` of `.github/mkdocs_blueprint.py`); the privacy plugin keeps its own 5 seconds. A download that runs out of its time is tried again like one that failed, three times in all, which ends within about two minutes for a server that no longer answers. It reaches the website of every repository with the next release.
- **uv:** the Variants set uv up with `continue-on-error` and two minutes; only when that attempt fails or runs out of its time, a second one sets the same uv up with `download-from-astral-mirror: false`, from the releases of uv on GitHub. The job passes with either, and Renovate moves the version of both.
- **Images:** a step of the Variants puts a `docker` in front of the runner's on the `PATH`, for every step after it and for `scripts/check.sh`. When `docker run` exits with 125, Docker's own code for a container that it couldn't start, it starts the container again after 10 and then 20 seconds, with a warning; every other exit code, that of a check in the container among them, and every other command it passes on at once.

## Consequences

A font server that stops answering costs a build of the website about two minutes at most instead of its step, and what fails all its attempts still fails the step, with the error of the last one, for the flaky-test bot. A hang of the download of uv costs two minutes instead of the job. A container that Docker couldn't start for another reason, such as a wrong option, also starts three times before its step fails, 30 seconds later. The other workflows that set uv up keep one attempt; they adopt the second one when a hang of uv shows up there as well. The pre-step of harden-runner stays bounded only by the time limit of its job.
