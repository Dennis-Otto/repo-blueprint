### Bug fixes

- **A long check no longer loses its run to the fix bot:** when a check that keeps fixes still runs after the bot's quarter of an hour, such as long end-to-end tests, the bot commits nothing on a branch of the repository instead of cancelling that run for a part of the fixes. The job after the run that ends last, however it ends, makes one commit with every fix. Each run of a check of a pull request of the repository now starts a short job of the bot for this, also when it passes.
