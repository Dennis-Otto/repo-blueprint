---
description: "A template for a Home Assistant custom integration: HACS and hassfest in every pull request, Python 3.14 with full coverage, mutation and property tests, and signed releases that HACS installs, kept current by a bot."
---

# Home Assistant integration template with HACS, hassfest and signed releases

A custom integration for Home Assistant, with the checks of Home Assistant itself in every pull request and a release that HACS installs from the first merge on.

## Start one

```sh
uvx copier copy --data project_type=home-assistant gh:Dennis-Otto/repo-blueprint my-integration
cd my-integration
python3 .github/blueprint.py create
```

With [uv](https://docs.astral.sh/uv/) and the GitHub CLI, as [the quick start](../guide.md#start-a-repository) shows. Copier asks for the name, the owner and the other answers, and `create` makes the repository on GitHub, applies the settings as code and prints the checklist.

## What you get

- **The example:** `custom_components/<domain>/` with its `manifest.json`, a config flow, translations in English and German and the brand icons, `hacs.json`, and the tests in `tests/` with pytest-homeassistant-custom-component, on Python 3.14. Replace it with the real code; its tests show how.
- **The steps of `scripts/check.sh` for this kind,** the same on your machine and in the CI: Ruff, mypy and the tests with every line and branch covered, on every core.
- **The steps of every kind:** the text files, the diagrams, the pages in one column, the fragments of the changelog, the version, the Git hooks, ShellCheck for the shell scripts and the strict build of the website.
- **Workflows of this kind:** the property tests with new random inputs every night (`properties.yml`) and the mutation tests with mutmut every week (`mutation.yml`).
- **Everything that every repository gets:** the PR coach and the fix bot, the release bot, Renovate, the settings as code, the issue assistant, the website in English and German, the security checks and the blueprint bot, as [the guide](../guide.md#what-a-new-repository-gets) lists them.

## The checks that a pull request needs

The ruleset *Protect main* of `.github/repository.toml` lets a pull request merge once these checks pass:

- `check (home-assistant)`: `scripts/check.sh` with the tools of Home Assistant.
- `home-assistant`: the HACS action and hassfest, the validation of Home Assistant.
- `lint`, `diagrams`, `docs`, `conventional title`, `codeql`, `dependency-review` and `gitleaks`, which every kind needs: every linter in one job, the pictures of the diagrams, the strict build of the website, the title of the pull request with its entry in the changelog, CodeQL, the review of new dependencies and the secret scan.

## Delivery

Merging the release pull request publishes a release with the zip of the integration, which `hacs.json` names, so HACS installs that zip. The release has its SBOM and the signed provenance of SLSA Build Level 3.

## Once by hand

`python3 .github/blueprint.py checklist` ticks off each step that it can see and names the rest, each with its link: the release app of the owner with its private key, as [your own account](../own-account.md) shows, the token of the issue assistant unless its AI is off, OpenSSF Best Practices, the REUSE API and the social preview.

This kind adds these steps:

- Submit the repository to the default repositories of HACS: <https://github.com/hacs/default>.

## A real repository

[Autodarts for Home Assistant](https://github.com/Dennis-Otto/ha-autodarts) is made from the blueprint: local real-time board control, games, tournaments and statistics, with dashboard cards, end-to-end tests in a real Home Assistant and screenshots that renew themselves.

How the blueprint compares with other templates: [the comparison](../compare.md).
