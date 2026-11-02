### Features

- **The fixers run on `main` every week:** Lint and the CI now run on `main` once a week as well, so that a new rule of a tool, or anything else that no commit changes, repairs itself through the pull request from `bot/self-heal` instead of failing the next person's pull request. A week without a finding opens nothing and starts no job of the fix bot; a check that fails with no command to fix it keeps one issue of bot health open.
