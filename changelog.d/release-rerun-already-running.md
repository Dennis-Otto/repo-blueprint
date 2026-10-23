### Bug fixes

- **The bot for failed releases leaves a release alone that runs again already:** when you or another bot had started a failed release again before the bot did, its run of *After the checks* failed with "This workflow is already running", although the release went on and passed. The bot now looks at the run first and leaves it alone when it runs again or ran again, and takes that answer of GitHub as done too.
