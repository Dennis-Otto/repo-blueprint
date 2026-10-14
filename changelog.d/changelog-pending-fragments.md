### Bug fixes

- **Every fragment of the changelog that waits for the release is checked first:** `scripts/check.sh` checks each fragment in `changelog.d/` as the release takes it in, also those that other pull requests left on `main`, so that a stricter rule of a new blueprint release fails in a pull request rather than in the release bot. The check *changelog* counts only a new fragment as the entry of a pull request: changing the fragment of another pull request that waits for its release gets a warning, and every failure of the check says in its summary what to write where.
