# A version that another package pins is accepted with every advisory, and Renovate is told

- Status: accepted
- Date: 2026-10-23

## Context

The test plugin of Home Assistant, pytest-homeassistant-custom-component, pins Home Assistant, which pins the Pillow and the uv that the tests of every integration install. From 2026-10-20, OSV-Scanner reported their advisories in `stacks/home-assistant/requirements-test.txt` of the blueprint, 10 at first and 40 three days later, so OSV-Scanner and Findings failed on `main` ([issue 381](https://github.com/Dennis-Otto/repo-blueprint/issues/381), [issue 382](https://github.com/Dennis-Otto/repo-blueprint/issues/382)), and every new Home Assistant integration would have failed them from its first commit. No update could fix them: the newest Home Assistant pins the same versions. Renovate doesn't read `osv-scanner.toml`, so in every run it tried a fix of each of the two packages in the blueprint and in homedarts-for-autodarts, which the lock file couldn't take, and logged "Detected empty commit - aborting git push" ([issue 247](https://github.com/Dennis-Otto/repo-blueprint/issues/247), [issue 384](https://github.com/Dennis-Otto/repo-blueprint/issues/384)).

OSV-Scanner reads the `osv-scanner.toml` in the folder of each lock file, not one in a folder above it, and ignores a whole file with a key that it doesn't know, with no more than a line in its log. An entry of `[[IgnoredVulns]]` names an advisory by its id, not the package or the version that it affects; an entry of `[[PackageOverrides]]` names a package, its version and its ecosystem, and accepts every advisory of that version with `vulnerability.ignore`, until `effectiveUntil`.

## Options

1. Accept each advisory in `[[IgnoredVulns]]`, and write the rules of Renovate by hand.
2. Accept each version with every advisory in `[[PackageOverrides]]`, with its reason and `effectiveUntil`, and let `blueprint.py` write a rule of Renovate for each, which a step of `scripts/check.sh` keeps in step.
3. Switch the vulnerability alerts of Renovate off for the lock files of the tests.

## Decision

Option 2. The advisories of a version that another package pins wait for the same update, also those that are published tomorrow, and the version is what Renovate matches. `stacks/home-assistant/osv-scanner.toml` accepts the Pillow 12.3.0 and the uv 0.12.23 of Home Assistant 2026.10 until 2026-11-22, and a new Home Assistant integration gets the same file in its root, beside its `requirements-test.txt`. `blueprint.py advisories` reads every `osv-scanner.toml` that git knows and writes `.github/renovate-accepted.json5`, which `.github/renovate-blueprint.json5` extends: for each such version, a rule with `enabled: false` for that package, that version and the lock files of that folder, which also keeps Renovate from the fix of a vulnerability that it switches on for an indirect dependency otherwise. The step *Accepted advisories* of `scripts/check.sh` fails while the two disagree, and for a file that OSV-Scanner couldn't use, or an entry without its package, version, ecosystem, reason or `effectiveUntil`; its fix, `advisories --fix`, writes the rules. Both files belong to the project after its first copy. An advisory that doesn't affect a version that an update could move stays in `[[IgnoredVulns]]`, which gets no rule.

## Consequences

- OSV-Scanner passes on `main` again; GitHub closes the alerts of the accepted advisories with the next analysis, and Findings passes after it.
- Renovate tries no fix of an accepted version; the update of the package that pins it, here the test plugin of Home Assistant, still comes, moves the version, and the rule no longer matches.
- After `effectiveUntil`, OSV-Scanner reports the advisories again, and a person looks at them: the update that moved them, or a new date with its reason.
- The OpenVEX document of a release still states the `[[IgnoredVulns]]` of the `osv-scanner.toml` in the root alone; an accepted version names no advisory, and the test tools are no part of a release.
- A repository that takes the blueprint gets `.github/renovate-accepted.json5` with its next update, with the rules of the template; a repository with an `osv-scanner.toml` of its own keeps it, and the step and its fix write the rules from that file instead.
