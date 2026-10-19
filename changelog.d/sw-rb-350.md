### Bug fixes

- **The branch bot brings a pull request up to date across a change of a workflow:** once `main` changed a workflow since a pull request left it, GitHub refused the update to the bot's token of the release app, which could not change workflows, so such a pull request, such as one of Renovate that updates the actions, stayed behind with a warning in every run and the Update branches workflow failed on `main`. The token may change workflows now, as Renovate's does; the bot still checks out only `main` and runs nothing of the pull request.
