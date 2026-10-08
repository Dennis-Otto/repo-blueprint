# Publish a beta of the next release after every change for users, where a project wants it

- Status: accepted
- Date: 2026-10-07

## Context

Testers of a Home Assistant integration want the changes before a release, in HACS, without installing from a branch.

## Options

1. A release candidate by hand, with `Release-As` in a pull request.
2. A beta of the next release after every `feat`, `fix` or `perf` that reaches `main`, as a prerelease.

## Decision

Option 2, switched on by the repository variable `BETA_CHANNEL`. The beta takes the version of the release pull request with `-beta.N`, is built, signed and verified like a release, and is published as a prerelease that announces nothing. release-please finds its last release by the version of its manifest, so the betas change neither the next version nor its notes.

```mermaid
---
config:
  flowchart:
    wrappingWidth: 400
---
flowchart TB
    accTitle: A beta after every change for users
    accDescr: On main, after the release 1.2.0, a feat and a fix each become a beta of 1.3.0, a docs change does not, and merging the release pull request then makes 1.3.0.

    subgraph main ["main"]
        direction TB
        before["<code>chore: release 1.2.0</code><br>the release <b>v1.2.0</b>"]
        feat["<code>feat: a dark mode</code><br>the beta <b>v1.3.0-beta.1</b>"]
        docs["<code>docs: the dark mode</code><br>no change for users<br>so no beta"]
        fix["<code>fix: the contrast</code><br>the beta <b>v1.3.0-beta.2</b>"]
        after["<code>chore: release 1.3.0</code><br>the release <b>v1.3.0</b>"]
        before --> feat --> docs --> fix --> after
    end

    classDef bot fill:#526cfe2e,stroke:#526cfe,stroke-width:2px
    classDef done fill:#16a34a2e,stroke:#16a34a,stroke-width:2px
    class feat,fix bot
    class before,after done
```

## Consequences

A project with the beta channel has a tag and a prerelease for every change for users. HACS, npm and PyPI offer them only to those who ask for betas.
