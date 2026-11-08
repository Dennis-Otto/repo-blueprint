### Features

- You hear when the social preview that GitHub shows falls behind `.github/social-preview.png`: GitHub takes it only from an upload, so a new picture used to go unseen. `blueprint.py checklist` now says *Social preview uploaded and current* and compares the upload with the committed picture, byte for byte, and the nightly look of the bot-health bot keeps one issue, *Upload the new social preview*, open with the picture and the link to the settings until GitHub shows it, then closes it ([#721](https://github.com/Dennis-Otto/repo-blueprint/issues/721)).
