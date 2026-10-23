# A dependency dashboard, the whole Monday, fix(deps) for what the users run, and pinned downloads that move with their checksum

- Status: accepted, amended by [0057](0057-renovate-keeps-no-dependency-dashboard.md), which switches the dependency dashboard off again
- Date: 2026-10-17

## Context

Four gaps in the rules of Renovate ([0005](0005-renovate-instead-of-dependabot.md)):

- **Nothing showed what waited or failed.** The rules switched off the dependency dashboard of `config:recommended`. An update that waited for its week, its window or the maintainer, and one whose lock file couldn't be written, showed only in the log of the bot: the update of PHPUnit to 13 in paperless-sync failed with "Artifact update problem" and closed itself 9 hours later, unseen, and in ha-autodarts two branches of vulnerability fixes ended in "Detected empty commit" in every run.
- **The window caught one run.** Routine updates came on Mondays from 00:00 to 06:59, Berlin time. GitHub starts the scheduled runs of the bot, every two hours, only roughly and skips some: 12 of 34 from 2026-10-09 to 2026-10-12, and in the week of 2026-10-05 one run, at 01:39, fell into the window. One more skipped run would have held every routine update of six repositories back by a week.
- **What the users run reached no release.** The title of the squashed commit decides the release: `fix(deps)` makes a patch release, `chore(deps)` none. `config:recommended` commits as `fix` only the dependency types `dependencies` of npm and `require` of Composer. The requirements of the manifest of a Home Assistant integration, the dependencies of a Python package in `pyproject.toml`, the actions that a composite action runs and the base images of a container were `chore(deps)`: their users got them only with a release made for another reason.
- **Four tools never moved.** The workflows and `.github/sign-tag.sh` download gitsign, Infection, krankerl and Nextcloud at a pinned version and check each download against its sha256. No line `# renovate:` named them, and the pattern of the custom manager knew YAML only, not the `version=` of a script: Infection and Nextcloud were two patch releases behind. And Renovate moves a version, but not the checksum beside it, since its `github-releases` datasource gives the commit of a tag as the digest, not the sha256 of an asset: a version moved alone would merge on its own and fail its checksum in the next release.

## Options

1. **Dashboard:** keep it off and read the log, of which the issue *Renovate logs problems* shows warnings and errors only, or an issue in every repository.
2. **Window:** more runs, which cost minutes of Actions and get skipped all the same; a schedule of its own for Mondays; or the whole Monday.
3. **What the users run:** one rule that makes every update `fix`, so that the tools make releases too, or a rule for each kind of project.
4. **Checksums:** verify each download against a checksum file of its release, which not every release has and which comes from the same place as the download; let only the maintainer move these tools; a check that fails until someone writes the checksum; or a script that Renovate runs after the update and that writes it.

## Decision

1. Every repository has an issue *Dependency dashboard*, with the label `dependencies`: the updates that wait and why, those that failed with their error, the vulnerabilities that OSV knows, and a checkbox for each, which the next run of the bot acts on. No update needs a checkbox to be opened. The issue assistant and the other bots leave an issue of a bot alone.
2. Routine updates and the refresh of the lock files come on the whole Monday, Berlin time, with a dozen runs of the bot; a fix of a vulnerability comes at any time, as before.
3. A rule of each kind makes what its users run `fix(deps)`: the requirements of the manifest of a Home Assistant integration, the `project.dependencies` of a Python package (in a group of their own, *the Python packages*), the actions of `action.yml` of a GitHub Action and the images of the `Dockerfile` of a container. The blueprint commits all its updates as `fix(deps)`, as before, since every repository gets them.
4. Each pinned download has its line `# renovate:`, with `datasource=github-releases` and, where a tag begins with v, `extractVersion=^v(?<version>.+)$`; the pattern reads the shell form `name=1.2.3` too. `.github/pins.toml` records the address of each download and the version and sha256 that the files pin. After Renovate moved a version, a week after its release, it runs `python3 pins.py` (a post-upgrade task, the one command that the bot allows, without a shell and without the environment of the bot; the checkout it runs in still holds the token of the release app in `.git/config`, so `pins.py` uses the standard library alone, runs nothing that it downloads and is reviewed like a workflow), which downloads the new release and writes its sha256 beside the version and into the record; Renovate commits both, and the update merges on its own. `tests/test_pins.py` fails while a version and its sha256 disagree with the record, and checks that every file downloads from the address of the record. In every other repository, these pins follow the blueprint, as the uv of the workflows does: its Renovate leaves them alone, and the next release of the blueprint brings them.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/how-renovate-moves-a-pinned-download.dark.svg">
  <img src="../images/diagrams/how-renovate-moves-a-pinned-download.svg" alt="How Renovate moves a pinned download: A week after a new release of gitsign, Infection, krankerl or Nextcloud, Renovate moves its version in the workflows and in .github/sign-tag.sh. Then pins.py downloads the new release and writes its sha256 beside the version and into .github/pins.toml, and Renovate commits both. The tests check that every version has the sha256 of the record. Once every check passes, the update merges on its own as fix(deps), and the next release of the blueprint brings it to every repository.">
</picture>

## Consequences

- Every repository has one more open issue, which Renovate keeps current; closed, it comes back with the next run. A checkbox acts with the next run, within two hours, or at once with a run of the Renovate workflow of the blueprint.
- The refresh of the lock files is built anew throughout its window ([0012](0012-lock-refresh-waits-for-the-maintainer.md)), now the whole Monday: a review on a Monday holds until the refresh changes again, one from Tuesday on until the next Monday.
- Home Assistant integrations, Python packages, actions and containers get more patch releases, each with the updates of a week.
- `pins.py` runs in the container of Renovate, on the files of the branch of the update, which are those of `main` with the version that Renovate moved; a change of `pins.py` needs the review of a change of a workflow. A new download goes into `.github/pins.toml` by hand, with its address, version and sha256, and gets its line `# renovate:` in the file that downloads it.
