# The tools of a Nextcloud app run on a newer PHP than its code, which is checked on the oldest

- Status: accepted
- Date: 2026-10-18

## Context

A Nextcloud app of the blueprint runs on PHP 8.2 and newer, as `<php min-version="8.2"/>` of `appinfo/info.xml` and `require.php` of `composer.json` say; Nextcloud 33 and 34 accept PHP 8.2 to 8.5. Its tools ran on PHP 8.2 too: the CI set up PHP 8.2, and `config.platform.php` of `composer.json`, for which Composer locks the tools, was `8.2.27`.

- **PHPUnit stayed at an end of its life.** PHPUnit 10.5 has had no bug fixes since February 2025 and 11.5 none since February 2026; PHPUnit 12 needs PHP 8.3 and 13 PHP 8.4. paperless-sync and paperless-unified-search still ran PHPUnit 10.5.
- **Renovate proposed what could never pass.** Its filter by the PHP of the platform, `constraintsFiltering: "strict"`, let PHPUnit 13 through: the pull requests Dennis-Otto/paperless-sync#80 and Dennis-Otto/paperless-unified-search#87 replaced `^10.5` with `^13.0`, failed twice and closed themselves unseen, and with them went the step to PHPUnit 11 or 12.
- **The order of the tests was always the same.** `phpunit.xml` ran them in the order of their files, so a test that needs what another one left behind, such as a stream wrapper or the static server of Nextcloud, passed by luck. With the `phpunit.xml` of this decision, the 1124 tests of paperless-sync and the 387 of paperless-unified-search passed with their PHPUnit 10.5 on PHP 8.3, in a random order with five seeds and in reverse.

## Options

1. **Raise the oldest PHP of the apps to 8.3.** Simple, and allowed in this rebuild, but it drops the servers that still run PHP 8.2, for nothing that the code needs.
2. **Run the tools on PHP 8.3 and check the code on PHP 8.2 as well.** The tools can move on, and what the app ships keeps running where it ran.
3. **Keep PHP 8.2 and PHPUnit 11.5,** and only stop Renovate from proposing PHPUnit 13.

## Decision

Option 2:

1. The tools run on the PHP of `config.platform.php` in `composer.json`, `8.3.16` for a new app, the oldest PHP 8.3 that Psalm 6 accepts, with PHPUnit 12. The CI and the Variants read that PHP and the oldest PHP of `appinfo/info.xml` from the files of the app, set up the oldest one first and the PHP of the tools last, so that `php` runs the tools, and set up only one when both are the same. An app made before keeps its tools on PHP 8.2 until its own `composer.json` moves them.
2. The new step *Oldest PHP* of `scripts/check.sh` parses what the app ships, `appinfo/`, `lib/` and `templates/`, with that PHP, as `php8.2` or the like, and runs `composer check-platform-reqs --lock --no-dev` with it, so that a package of the run time that needs a newer PHP fails as well. The CI fails without that PHP; on a computer without it, the step says that the CI checks it. Psalm checks the code for PHP 8.2, as `phpVersion` of `psalm.xml` says, so a function or class of a newer PHP fails there.
3. Renovate filters the Composer packages by PHP 8.3, proposes each major version in a pull request of its own, `separateMultipleMajor`, so that one that needs a newer PHP holds back none that the app can take, and holds PHPUnit below 13 until the tools run on PHP 8.4.
4. `phpunit.xml` runs the tests in a new random order each time, each after the tests that it depends on (`executionOrder="depends,random"`, `resolveDependencies="true"`), and fails a test that prints (`beStrictAboutOutputDuringTests`) or that uses what PHPUnit deprecates (`failOnPhpunitDeprecation`): attributes that PHPUnit 10.5, 11.5, 12 and 13 all know, so that the file of the blueprint fits every app, whichever major version its `composer.json` installs.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/which-php-checks-a-nextcloud-app.dark.svg">
  <img src="../images/diagrams/which-php-checks-a-nextcloud-app.svg" alt="Which PHP checks a Nextcloud app: Renovate keeps the tools of composer.json current, with only the releases that run on the PHP of the tools, each major version on its own and PHPUnit below 13. The CI reads two versions of PHP from the files of the app: config.platform.php of composer.json, for which Composer locks the tools, and the min-version of the PHP in appinfo/info.xml, the oldest PHP that the app runs on. It sets up the oldest PHP first and the PHP of the tools last, so that php runs the tools. php-cs-fixer, Psalm for PHP 8.2 and PHPUnit in a new random order run on the PHP of the tools; then the step Oldest PHP parses the code that the app ships with php8.2 and checks that its packages install there.">
</picture>

## Consequences

- A new app starts on PHPUnit 12. An app made before moves its tools in its own `composer.json`, which the update never touches: `config.platform.php` to `8.3.16`, then `composer update --lock`, and Renovate brings PHPUnit 11 and 12 in pull requests of their own. Until the app moves, Renovate already looks for releases for PHP 8.3, the PHP of its filter: its pull request for PHPUnit 12 fails, because Composer cannot install PHPUnit 12 for `config.platform.php` 8.2. The move, not that pull request, brings PHPUnit 12, so it follows the update of the blueprint soon, which keeps that time short.
- The dev container runs PHP 8.3, the PHP of the tools, without PHP 8.2: there, the step *Oldest PHP* leaves the oldest PHP to the CI.
- A test that depends on the order of the tests fails now and then, with the seed of its order in the log; `vendor/bin/phpunit --random-order-seed SEED` runs that order again, as `CONTRIBUTING.md` of the app says.
- When the tools move to PHP 8.4, the platform of `stacks/php/composer.json`, the PHP of Renovate's filter and the limit of PHPUnit move together; a test of the template fails until they agree.
