# The SBOMs of a release describe what it ships, by its name and version

- Status: accepted
- Date: 2026-10-18

## Context

Every release carries an SBOM as SPDX and as CycloneDX, beside the weekly SBOM of the repository ([0009](0009-run-a-check-only-where-it-can-change-a-result.md)). Both came from `anchore/sbom-action` on the checkout of the tag, `path: .`:

- **They described the repository, not the release.** The SBOM of paperless-sync v0.1.10 listed 206 components: 101 GitHub Actions of the workflows, 66 packages of PyPI from the tools of the website and of Copier, 2 tools of npm and 35 files. Its package, a Nextcloud app, holds no third-party code. The one of ha-autodarts v1.12.2 listed 351, among them cryptography and PyJWT of the tools; `grype sbom:` on it reported 17 vulnerabilities, 1 of them critical, and `grype dir:` on the zip that HACS installs none.
- **They named no release.** The root was `{type: file, name: "."}`, without a version or a supplier, which the minimum elements of an SBOM (NTIA) ask for, so a scanner could tell neither which release an SBOM belonged to nor apply the OpenVEX document of the release to it.
- **An installer ran where the release is written.** The action downloads the `install.sh` of syft and runs it, in the job that holds `contents: write`, `id-token: write` and `attestations: write` and, for a Nextcloud app, its signing key.

## Options

1. **What to describe:** the checkout with a configuration of syft that leaves out `.github/`, `docs/` and the like; the archive of the package as one file; or the package unpacked as its users install it.
2. **The catalogers:** syft's default for a folder, which reads what manifests and lock files declare, or its default for an image, which reads what is installed, such as `vendor/composer/installed.json` or the `package.json` of an npm package.
3. **syft:** the action, or its release, pinned by version and sha256 like gitsign and krankerl ([0029](0029-a-dependency-dashboard-the-whole-monday-and-pins-with-their-checksum.md)).

## Decision

1. The build unpacks what the release ships into a folder of its own, by `PUBLISH_TO`: the zip of HACS, the wheel, the npm package and the signed Nextcloud app; an action, an image and a project without a package ship the files of their tag, which `git archive` gives, without `.github/`, `.devcontainer/`, `.githooks/`, `changelog.d/`, `docs/`, `fuzz/`, `scripts/`, `test/`, `tests/` and the lock files of their tools, `requirements-dev.*`, `requirements-fuzz.*` and `requirements-test.*`. An image carries an SBOM of its own in the registry, which BuildKit writes.
2. A package is described with the catalogers of an image, what it installs; sources with those of a folder, what they declare.
3. syft comes from its release, checked by its sha256 and moved by Renovate with `pins.py`, and names the root after the repository, the version of the release and its owner as the supplier. The build fails before the release is published, and the release verification fails, when an SBOM doesn't name the release; the weekly verification only notes a release made before.
4. The OpenVEX document names the release by its tag on GitHub and, as an identifier, by the name that Grype gives the root of an SPDX SBOM, `pkg:generic/<name>@<version>`, so that `grype sbom:<name>.spdx.json --vex <name>.openvex.json` applies it. `SECURITY.md` shows that command.
5. The weekly SBOM of the SBOM workflow keeps describing the whole repository with its tools, as an artifact, by its name and commit.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/what-the-sboms-of-a-release-describe.dark.svg">
  <img src="../images/diagrams/what-the-sboms-of-a-release-describe.svg" alt="What the SBOMs of a release describe: The build unpacks what the release ships into a folder of its own: the zip of HACS, the wheel, the npm package or the signed Nextcloud app, and for an action, an image or a project without a package the files of its tag without those that only check, test and document it. syft, checked by its sha256, lists the components that a package installs, or that the sources declare, under the name of the repository and the version of the release, as SPDX and as CycloneDX. The build and the release verification check that both name the release, and a scanner of a user applies the OpenVEX document of the release to the SPDX SBOM.">
</picture>

## Consequences

- A scanner of a user sees the components that the release ships, often only the package itself: the advisories of the tools of the checks no longer reach the users, and those of a component that a package does ship do.
- The requirements in the manifest of a Home Assistant integration and the dependencies of a Python or npm package, which the installer of the user resolves, are not components of the SBOM; the SBOM of the user's installation names them.
- Grype reads the name and version of the root from an SPDX SBOM, not yet from a CycloneDX one, so `--vex` applies to the SPDX SBOM.
- The SBOMs of the releases made before stay as they are, since a release is immutable.
- A new kind of package needs its case in the step that unpacks it; until then, its SBOMs describe its sources.
