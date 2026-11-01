### Bug fixes

- **A project's own sentences about its releases no longer conflict with every update:** `## Releases` of `CONTRIBUTING.md` now has two marked lines, and every update keeps the text between them, so an existing repository moves its sentences there once. The check *lint* and the report of the PR coach take no notice of a change that stays between them. The sentence that repositories receive the release of an action as a Dependabot pull request now comes with the guide of that kind.
