# A Home Assistant integration tests with Home Assistant's own test plugin

- Status: accepted
- Date: 2026-11-15

## Context

The tests of a Home Assistant integration need a Home Assistant and the fixtures of its own tests, such as `hass` and `MockConfigEntry`. The Home Assistant kind took them from pytest-homeassistant-custom-component, which a person published by copying them out of Home Assistant. Its maintainer retired it on 2026-11-03: its README calls it broken and points to `pytest-homeassistant`, which Home Assistant publishes itself with each of its releases, at the same version. The last release of the old plugin, 0.13.375, pins Home Assistant 2026.10.4, and with it Pillow 12.3.0, whose advisories `stacks/home-assistant/osv-scanner.toml` accepted until 2026-12-20, "until the next update of pytest-homeassistant-custom-component that brings Pillow 13", an update that won't come ([#933](https://github.com/Dennis-Otto/repo-blueprint/issues/933)). homedarts-for-autodarts made the move first, in its decision 0031 ([homedarts-for-autodarts#736](https://github.com/Dennis-Otto/homedarts-for-autodarts/pull/736)).

## Options

1. **Keep the old plugin and move the date again.** Its reason no longer holds: no update of the old plugin brings a new Home Assistant, and every new integration would start with an acceptance that only grows.
2. **Pin a newer Home Assistant beside the old plugin.** The old plugin pins its Home Assistant exactly, so pip can't resolve both.
3. **Home Assistant's own test plugin,** `pytest-homeassistant`, pinned to the version of the newest Home Assistant.

## Decision

Option 3.

- **The plugin:** `stacks/home-assistant/requirements-test.in` pins `pytest-homeassistant`, without an extra: the sample integration needs no Bluetooth, and an integration that does asks for `pytest-homeassistant[bluetooth]`. The pin stays exact, so that a Home Assistant that needs a newer Python fails its update instead of an older one being chosen. `pytest-cov`, `pytest-timeout` and `pytest-github-actions-annotate-failures`, which the old plugin brought and `scripts/check.sh` and `pyproject.toml` use, get lines of their own; `pytest-xdist` still comes with the plugin.
- **respx stays off as a plugin of pytest:** `-p no:respx` in `addopts` of `pyproject.toml`, as the README of the plugin asks, so that Home Assistant puts its own httpx in place before anything imports httpx.
- **The sample tests** import from `pytest_homeassistant.common`, and `tests/conftest.py` drops the fixture that asked for `enable_custom_integrations`: the `hass` of the plugin enables the integrations of `custom_components` by itself.
- **No acceptance:** Home Assistant 2026.11.1 pins Pillow 13.0.0, so `stacks/home-assistant/osv-scanner.toml` keeps its explanation and accepts nothing, and `.github/renovate-accepted.json5` has no rule. Its template gives every kind the empty file while the blueprint accepts nothing there: `replaced()` stops a render whose text it doesn't find, and a test fails once the blueprint accepts a version again, until the template takes its rules again.
- **Renovate:** the rule *the Home Assistant test base* matches `pytest-homeassistant`, so that each new Home Assistant still comes as a pull request of its own.
- **An existing integration** keeps its `requirements-test.in`, `requirements-test.txt`, `pyproject.toml`, `osv-scanner.toml` and `tests/`, which belong to the project. The changelog says how to move them, as a note ([decision 0143](0143-a-step-that-the-changelog-asks-of-an-existing-repository-is-a-migration-a-line-of-the-checklist-or-a-note.md)): a migration may commit none of them, since they run as code, and homedarts-for-autodarts, the only integration of `.github/fleet.toml`, has made the move.

## Consequences

The test base of an integration follows Home Assistant on the day of each release, without waiting for a person to copy its fixtures, and the advisories that a release of Home Assistant fixes leave the tests with its update. Two things behave differently in the tests of an integration: the `hass` of the plugin names `tests/testing_config` as its configuration, without creating it, so a test that writes there takes `hass_tmp_config_dir` for `hass_config_dir`; and its `freezer` moves the clock of the event loop too, so a poll that a coordinator schedules comes due on `freezer.tick`.
