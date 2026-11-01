# A Node package lints and formats with Biome, reports its coverage as LCOV and installs without the scripts of its packages

- Status: accepted
- Date: 2026-10-18

## Context

The Node package was the weakest kind of the blueprint ([#293](https://github.com/Dennis-Otto/repo-blueprint/issues/293)):

- **No lint and no format.** `scripts/check.sh` checked the types, the tests and the package, while a Python project had Ruff and a Nextcloud app php-cs-fixer: an unused variable, a promise that nobody awaits or a file in another format passed every check.
- **No coverage in the report of the PR coach.** The CI kept no artifact `coverage`, and the coach read only Cobertura, while the test runner of Node writes LCOV.
- **Install scripts on the computers of the contributors.** The CI installs with `npm ci --ignore-scripts`, but the dev container, `CONTRIBUTING.md` and `AGENTS.md` ran a plain `npm ci`, which runs the `preinstall`, `install` and `postinstall` scripts of every package: the way in of a package that was taken over, such as the worm that spread through npm in September 2025.

## Options

1. **ESLint with typescript-eslint, and Prettier.** The most common pair, with the most rules, but two tools with two settings, a few hundred packages in the lock and a run that takes seconds; type-aware rules need a program of TypeScript of their own.
2. **Biome.** One tool for the lint, the format and the order of the imports, one package with a native binary for each platform and no install script, one settings file, and a run of milliseconds. Its rules cover most of ESLint's recommended ones and of typescript-eslint's that need no types.
3. **Only the format,** with Prettier or Biome, and no lint.

## Decision

Option 2:

1. `@biomejs/biome` is a devDependency of the Node packages, locked with its hash in `stacks/node/package-lock.json`, which Renovate keeps current. The new step *Lint and format* of `scripts/check.sh` runs `npx --no -- biome ci --error-on-warnings .`: a warning fails as well, so none piles up, and in the CI Biome writes each finding as an annotation at its line. `npx --no` never fetches a Biome that the lock didn't install.
2. `biome.jsonc` belongs to the blueprint: the recommended rules, sorted imports and the indentation of `.editorconfig`, for the files that git doesn't ignore, other than `.github/`, whose tools and settings keep the format of the blueprint, and other than Markdown and YAML, which Biome formats since 2.6: markdownlint already checks the Markdown, and the blueprint renders both in the format they keep, and other than the pictures that `scripts/diagrams.sh` draws into `docs/images/diagrams`, whose code Mermaid writes and the next drawing writes again. Biome leaves the format of `extension/manifest.json` alone: release-please writes the version into it on every release pull request and puts each item of an array on a line of its own, and a blueprint update keeps the manifest a project has, in either format, so forcing one of them would fail the other. Its linter still runs on the file, and `scripts/check-manifest.mjs` checks the content. `.editorconfig` indents JSONC files with two spaces, as they are written, and CSS and HTML too, as the stylesheets of the blueprint and the scripts beside them have it. The fix bot runs `npx --no -- biome check --write .`, which makes the format and the fixes that Biome calls safe.
3. `npm test` writes, beside its usual output, the LCOV report `lcov.info`, which git and the package leave out; the CI keeps it as the artifact `coverage`. The coach and the dashboard read a report by its name: LCOV in a file that ends in `.info`, Cobertura in any other. The test runner names each file from where it ran; a tool that names it by its absolute path, such as c8, gets it named from the root of the checkout, as one source of a Cobertura report does.
4. Every install of a Node project runs without the scripts of its packages: the CI, the dev container and the commands of the documentation are `npm ci --ignore-scripts`, which a test checks in every rendered file.

## Consequences

- `package.json` belongs to the project, so a package made before keeps its own until it adds Biome with `npm install --save-dev --ignore-scripts @biomejs/biome`: until then the step says so and passes, so that the update of the blueprint fails no check. The same holds for the reporter of the script `test`; without it the CI keeps no report, and the coach reports without coverage, as before.
- A package that needs an install script, such as one that builds a native module, runs it on purpose, with `npm rebuild NAME`, in a script of its own.
- Mutation tests for Node, with Stryker, are a step of their own still to take; the Mutation workflow covers Python and PHP.
