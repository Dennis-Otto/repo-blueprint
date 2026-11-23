### Bug fixes

- **The check of a GitHub Action has 15 minutes instead of 8:** a slow runner no longer cancels `check (github-action)` after every test has passed, and a check that hangs still ends after 15 minutes, as those of Node, PHP and Home Assistant do. The limit is measured against the slowest attempts of the check, and the comment above it says so.
