### Bug fixes

- Delivering a Python package to PyPI no longer runs an action with a known vulnerability: the Release workflow moves to `pypa/gh-action-pypi-publish` v1.14.3, which no longer trusts the revoked root certificate of [GHSA-5xjx-3w67-w9x9](https://github.com/advisories/GHSA-5xjx-3w67-w9x9). With the update of the blueprint, the alert of zizmor that this advisory opened on `release.yml` closes, and the Findings workflow passes again, in every repository. The PR coach now also says how to fix such an alert: move the pin to the release that the advisory names as fixed.
