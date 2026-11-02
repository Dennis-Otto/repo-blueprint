### Bug fixes

- **The screenshot bot corrects the sizes of the pictures it changes:** when a picture comes out at another size, the bot's pull request also corrects the width and the height that the pages at the top of the repository and in `docs/` name for it, so that a check of those sizes passes without a person editing the pages. `python3 .github/blueprint.py screenshots restore` does the same on your machine.
