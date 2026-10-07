# Keep the settings of every repository as code, applied by a bot

- Status: accepted
- Date: 2026-10-07

## Context

Rulesets, required checks, security settings, environments and labels are clicked together in the web interface. They drift, and a new required check of the blueprint needs someone to add it in every repository.

## Options

1. Settings by hand, with a checklist.
2. A third-party settings app.
3. `.github/repository.toml` with `blueprint.py`, which compares and applies them through the API of GitHub, as the release app of the owner.

## Decision

Option 3. The settings bot applies the settings after every change of them and every week. What the API can't set, such as the value of a secret, fails its run with the command that sets it.

## Consequences

The release app needs the permission *Administration* (read and write). A setting changed in the web interface is put back within a week; a change belongs in the file.
