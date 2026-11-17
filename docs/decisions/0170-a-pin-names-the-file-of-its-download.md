# A pin names the file of its download

- Status: accepted
- Date: 2026-11-17

## Context

The workflows pin krankerl by its version and sha256 below a line `# renovate:` ([0029](0029-a-dependency-dashboard-the-whole-monday-and-pins-with-their-checksum.md)), and each step that downloads it built the name of its package from the version, as `.github/pins.toml` has it in its address. krankerl 0.14.1 added the revision `-1` to that name, and the blueprint 1.20.4 changed the address, `ci-php.yml` and `build-release.yml` together. The upgrade test of paperless-sync, a workflow of the project, reads the pin of its `ci.yml` and built the old name `krankerl_${KRANKERL_VERSION}_amd64.deb` itself: after the update to 1.20.4 moved the pin to 0.14.3, its download found no such file, and *Docker E2E* failed on `main` ([issue 994](https://github.com/Dennis-Otto/repo-blueprint/issues/994)). Nothing of the blueprint could see that copy of the name.

## Options

1. **Each file builds the name, as before:** every new name of a release needs a change of each file that downloads it, also of the files of the projects, which no update reaches.
2. **A variable with `{version}` in it, beside the pin:** one place, but each step must replace `{version}` itself, in Bash, and gets it wrong in its own way.
3. **The pin names its file:** a third line, `KRANKERL_ASSET: krankerl_0.14.3-1_amd64.deb`, which `pins.py` writes from the address of `.github/pins.toml`, as it writes the sha256.

## Decision

Option 3. A pin may name its file on the line after its sha256, by a name that ends in `ASSET` or `asset`. `python3 pins.py` writes it from the end of the address in `.github/pins.toml` with the version of the pin, after Renovate moved the version and after a change of the address, and `python3 pins.py --check`, which `tests/test_pins.py` runs, names each pin whose file differs. The pins of krankerl in `ci-php.yml` and `build-release.yml` name their file, and their steps download `"$KRANKERL_ASSET"`. `tests/test_pins.py` fails when a file that pins a tool with the name of its file builds that name anyway, and when a workflow or a script of the blueprint or of its template downloads a pinned tool without a pin of its own and without the name from a pin.

## Consequences

A new name of krankerl's package is one change of the address in `.github/pins.toml`: `python3 pins.py` writes it into both workflows, and the next release brings it to every Nextcloud app. A workflow of a project that downloads krankerl reads `KRANKERL_ASSET` from its `ci.yml` with the version and the sha256, and passes it to `.github/download.sh`; the projects that built the name themselves change that once, after the update that brings `KRANKERL_ASSET`. The other pins keep building their names from the version, which the test of the addresses holds to `.github/pins.toml`, since no file of a project reads them; a pin that another file reads gets the line of its file as well.
