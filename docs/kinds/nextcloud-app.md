---
description: "A template for a Nextcloud app: php-cs-fixer, Psalm with its taint analysis, PHPUnit with every line covered, the oldest PHP checked, an upstream bot for new versions of Nextcloud and signed packages for the App Store."
---

# Nextcloud app template with Psalm taint analysis, PHPUnit and signed App Store releases

An app for Nextcloud in PHP, with the analysis of Psalm that follows the data of a request through the code, and a signed package that the release bot sends to the App Store.

## Start one

```sh
uvx --from copier==9.19.0 copier copy --data project_type=nextcloud-app gh:Dennis-Otto/repo-blueprint my-app
cd my-app
python3 .github/blueprint.py create
```

With [uv](https://docs.astral.sh/uv/) and the GitHub CLI, as [the quick start](../guide.md#start-a-repository) shows. Copier asks for the name, the owner and the other answers, and `create` makes the repository on GitHub, applies the settings as code and prints the checklist.

## What you get

- **The example:** `appinfo/info.xml`, `lib/AppInfo/Application.php`, the PHPUnit tests in `tests/Unit/` with the `tests/bootstrap.php` and the `tests/stubs/` that they load, `psalm.xml`, `phpunit.xml`, `composer.json` with its lock file, and `krankerl.toml`, which builds the package. The license starts as AGPL-3.0-or-later, the license of Nextcloud. Replace it with the real code; its tests show how.
- **The steps of `scripts/check.sh` for this kind,** the same on your machine and in the CI: Composer, the metadata of the app, the syntax of PHP, the code and its packages on the oldest PHP, php-cs-fixer, Psalm, a canary that proves that the taint analysis still sees, the taint analysis itself, PHPUnit in random order with every line covered, and the package.
- **The steps of every kind:** the text files, the diagrams, the pages in one column, the fragments of the changelog, the accepted advisories, the lock files, the version, the Git hooks, ShellCheck for the shell scripts and the strict build of the website.
- **Workflows of this kind:** the mutation tests with Infection every week (`mutation.yml`), the upstream bot, which raises `max-version` when Nextcloud has a new major version (`upstream.yml`), and the registration of the app in the App Store (`register-app.yml`).
- **Everything that every repository gets:** the PR coach and the fix bot, the release bot, Renovate, the settings as code, the issue assistant, the website in English and German, the security checks and the blueprint bot, as [the guide](../guide.md#what-a-new-repository-gets) lists them.

## The checks that a pull request needs

The ruleset *Protect main* of `.github/repository.toml` lets a pull request merge once these checks pass:

- `check (php)`: `scripts/check.sh` with the tools of PHP.
- `lint`, `diagrams`, `docs`, `conventional title`, `codeql`, `dependency-review` and `gitleaks`, which every kind needs: every linter in one job, the pictures of the diagrams, the strict build of the website, the title of the pull request with its entry in the changelog, CodeQL, the review of new dependencies and the secret scan.

## Delivery

Merging the release pull request builds the package with krankerl, signs it with the key of the app and publishes it in the App Store, with its SBOM and the signed provenance of SLSA Build Level 3. The environment `release` holds the secrets `APP_PRIVATE_KEY` and `APPSTORE_TOKEN`.

## Once by hand

`python3 .github/blueprint.py checklist` ticks off each step that it can see and names the rest, each with its link: the release app of the owner with its private key, as [your own account](../own-account.md) shows, the token of the issue assistant unless its AI is off, OpenSSF Best Practices, the REUSE API and the social preview.

This kind adds these steps:

- Request the certificate of the app: <https://nextcloudappstore.readthedocs.io/en/latest/developer.html>.
- Then run *Actions → Register the app* with the id of the app.

## A real repository

[Paperless Sync](https://github.com/Dennis-Otto/paperless-sync) and [Paperless Unified Search](https://github.com/Dennis-Otto/paperless-unified-search) are made from the blueprint: two Nextcloud apps for Paperless-ngx, with end-to-end tests in a real Nextcloud.

How the blueprint compares with other templates: [the comparison](../compare.md).
