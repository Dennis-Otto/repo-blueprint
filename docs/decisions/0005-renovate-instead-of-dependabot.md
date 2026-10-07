# Keep the dependencies current with a self-hosted Renovate

- Status: accepted
- Date: 2026-10-07

## Context

Dependabot updates the dependency manifests and the actions, but not the images that scripts start by digest, the versions in workflow inputs or the end-to-end tests in subfolders unless each is listed, and every repository configures it on its own.

## Options

1. Dependabot, with its configuration in every repository.
2. The Renovate app of Mend.
3. Renovate, run by a workflow of the blueprint for every repository, as the release app.

## Decision

Option 3. One workflow runs Renovate every two hours for each repository with a `.github/renovate.json5`, with a token that leaves out *Administration*. Commits go through the API, so GitHub signs them. The rules of the blueprint are in `.github/renovate-blueprint.json5`; the project extends them. Dependabot keeps only the Features of the dev container, whose lock file Renovate can't update.

## Consequences

Updates wait a week, security updates come at once, and routine updates merge on their own. The bot depends on the private key of the release app in the blueprint.
