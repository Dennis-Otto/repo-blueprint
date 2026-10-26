### Features

- **The dependency updates of a day make one release:** a release of nothing but dependency updates no longer merges itself after each update, but once a day, in the daily run of the release bot, or when someone starts the Release workflow by hand; one that fixes a vulnerability, an update of Renovate with `[security]` in its title, still merges at once. In the blueprint, this ends the run of releases that each brought a pull request with all its checks to every repository of the Rollout (decision 0087).
