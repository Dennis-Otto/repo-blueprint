---
description: "A template for a Home Assistant custom integration: HACS and hassfest in every pull request, Python 3.14 with full coverage, mutation and property tests, and signed releases that HACS installs, kept current by a bot."
---

# Home Assistant integration template with HACS, hassfest and signed releases

A custom integration for Home Assistant, with the checks of Home Assistant itself in every pull request and a release that HACS installs from the first merge on.

## Start one

```sh
uvx --from copier==9.19.1 copier copy --data project_type=home-assistant gh:Dennis-Otto/repo-blueprint my-integration
cd my-integration
python3 .github/blueprint.py create
```

With [uv](https://docs.astral.sh/uv/) and the GitHub CLI, as [the quick start](../guide.md#start-a-repository) shows. Copier asks for the name, the owner and the other answers, and `create` makes the repository on GitHub, applies the settings as code and prints the checklist.

## What you get

- **The example:** `custom_components/<domain>/` with its `manifest.json`, a config flow, translations in English and German and the brand icons, `hacs.json`, and the tests in `tests/` with pytest-homeassistant-custom-component, on Python 3.14. Replace it with the real code; its tests show how.
- **Pictures of the integration:** `scripts/screenshots.sh` starts Home Assistant in Docker with `custom_components/`, sets the integration up through the onboarding and its config flow, and photographs its page, as `docs/images/screenshots/home-assistant.png` and `.dark.png`, beside the home page of the website; the screenshot bot renews them when their pixels change, and Renovate keeps the Home Assistant of the script current.
- **The steps of `scripts/check.sh` for this kind,** the same on your machine and in the CI: Ruff, mypy and the tests with every line and branch covered, on every core.
- **The steps of every kind:** the text files, the diagrams, the pages in one column, the fragments of the changelog, the accepted advisories, the lock files, the version, the Git hooks, ShellCheck for the shell scripts and the strict build of the website.
- **The advisories of the test tools that Home Assistant pins:** `osv-scanner.toml` accepts every advisory of the Pillow and the uv that Home Assistant pins for the tests, with its reason and until a date, so that OSV-Scanner passes from the first commit, and `.github/renovate-accepted.json5` keeps Renovate from a fix that the lock file can't take, as [the troubleshooting](../troubleshooting.md#osv-scanner-reports-a-version-that-another-package-pins) shows.
- **Workflows of this kind:** the property tests with new random inputs every night (`properties.yml`) and the mutation tests with mutmut every week (`mutation.yml`).
- **Everything that every repository gets:** the PR coach and the fix bot, the release bot, Renovate, the settings as code, the issue assistant, the website in English and German, the security checks and the blueprint bot, as [the guide](../guide.md#what-a-new-repository-gets) lists them.

## The checks that a pull request needs

The ruleset *Protect main* of `.github/repository.toml` lets a pull request merge once these checks pass:

- `check (home-assistant)`: `scripts/check.sh` with the tools of Home Assistant.
- `home-assistant`: the HACS action and hassfest, the validation of Home Assistant.
- `lint`, `diagrams`, `docs`, `conventional title`, `codeql`, `dependency-review` and `gitleaks`, which every kind needs: every linter in one job, the pictures of the diagrams, the strict build of the website, the title of the pull request with its entry in the changelog, CodeQL, the review of new dependencies and the secret scan.

## Delivery

Merging the release pull request publishes a release with the zip of the integration, which `hacs.json` names, so HACS installs that zip. The release has its SBOM and the signed provenance of SLSA Build Level 3.

After every release, and every week for the latest one, `verify-release.yml` checks the zip as HACS installs it: the release has the zip that `hacs.json` names, its `manifest.json` lies at the root of the zip, with the domain of the folder in `custom_components/` and the version of the release, and HACS offers it as it should, a release to every user and a beta only to those who show betas. A beta of the beta channel has its own version in the `manifest.json` of its zip, such as 1.3.0-beta.1, which Home Assistant shows to its testers ([decision 0065](../decisions/0065-the-release-verification-checks-the-zip-that-hacs-installs.md)).

## Once by hand

`python3 .github/blueprint.py checklist` ticks off each step that it can see and names the rest, each with its link: the release app of the owner with its private key, as [your own account](../own-account.md) shows, the token of the issue assistant unless its AI is off, OpenSSF Best Practices, the REUSE API and the social preview.

This kind adds these steps:

- Give the repository the description and the topics that HACS lists and its check needs: the answer `topics` names them in `.github/repository.toml`, and `settings apply` sets them.
- Submit the repository to the default repositories of HACS: <https://github.com/hacs/default>.

## A real repository

<!-- --8<-- [start:real-repository] -->

[HomeDarts for Autodarts](https://github.com/Dennis-Otto/homedarts-for-autodarts) is made from the blueprint: local real-time board control, games, tournaments and statistics, without a cloud account.

The Variants workflow tries every pull request of the blueprint that changes what the answers of HomeDarts for Autodarts render on them, before it merges.

<!-- --8<-- [end:real-repository] -->

How the blueprint compares with other templates: [the comparison](../compare.md).
