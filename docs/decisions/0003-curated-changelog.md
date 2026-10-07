# Write the changelog in the pull requests, and let the release bot assemble it

- Status: accepted
- Date: 2026-10-07

## Context

release-please writes a changelog from the titles of the commits. Titles are written for developers; users want to read what changed for them. Choosing patch, minor or major by hand at every release is error-prone.

## Options

1. The changelog of release-please alone.
2. A changelog written by hand at every release.
3. Every pull request describes its change under `## Unreleased`; the release bot moves that text into the section of the next release and keeps the version that the titles decide.

## Decision

Option 3. The version follows from the Conventional Commit titles (`fix` a patch, `feat` a minor, `!` a major) and is decided anew with every merge. The text under Unreleased becomes the notes, followed by every pull request. The check *changelog* asks every `feat`, `fix` and `perf` pull request for its entry.

## Consequences

There is one release action: merging the release pull request. The release bot has to rebuild its pull request on every merge, which `release.yml` does.
