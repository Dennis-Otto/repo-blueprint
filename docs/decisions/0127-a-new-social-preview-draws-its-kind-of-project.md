# A new social preview draws its kind of project

- Status: accepted
- Date: 2026-11-08

## Context

GitHub, chats and social networks show the social preview of a repository with every link to it. Each new repository starts with `.github/social-preview.html`, which `scripts/social-preview.sh` renders into the picture. Its left side has the name, the kind and the description of the project. Its right side was a card of the blueprint's checks, the same four lines in every repository: checks on every change, CodeQL and Scorecard, releases with SBOM and provenance, the issue assistant and Renovate. Dennis saw it in the preview of dennis-otto-pager and wanted something there that really has to do with the repository, abstracted where nothing fits ([#712](https://github.com/Dennis-Otto/repo-blueprint/issues/712)). The repositories that replaced the card, such as issue-assistant with a comment of the assistant and homedarts-for-autodarts with a screenshot of its card, show what their project is at a glance. The page belongs to the project after the first copy (`_skip_if_exists`), so the blueprint can only start it well and remind the project to make it its own.

## Options

1. **Keep the card of checks:** the same in every repository, and it says nothing of the project.
2. **A screenshot of the sample:** the samples are a starting point that the project replaces, and most kinds have nothing to photograph before the project's own code.
3. **A drawing of the kind of project, from the answers:** what a user of such a project sees first, with the names that the answers give: the step `uses:` of an action in a workflow, the `pip install` or `npm install` of a package, the `docker run` of an image, a request to a Worker and its answer, the popup of an extension in the toolbar, the app in the navigation of Nextcloud, the entities of a Home Assistant integration, or the start of the README of a repository without a build. Where the blueprint can't know the content, the drawing abstracts it, such as `{ … }` for what a package exports and grey lines for the text of a page.
4. **A question of `copier copy` for three bullets on the left:** more to answer for every new repository and for every answer file of the tests, for a page that the project rewrites anyway.

## Decision

Option 3, without the question of option 4: the left side keeps the description, and a comment in the page says that three short bullets say more. The panel carries the attribute `data-default-panel` and a comment that tells how to replace it: with a screenshot of what the project shows, such as one that `scripts/screenshots.sh` takes, or a faithful drawing of what it produces. `blueprint.py checklist` has the step *Social preview shows the project* before *Social preview uploaded*, which stays open while the page has that attribute or the card of checks of the repositories made before. Only the styles of the kind's own panel reach the page, so that a project edits a short file.

## Consequences

A new repository's preview tells what the project is from its first day, and the checklist keeps asking for the real one. An existing repository keeps its page, since it belongs to the project: the checklist names the old card of checks there, and the changelog says how to take the new panel or design an own one. The drawings show names that the answers give, so a project that changes its kind of delivery, such as a package that starts to publish, renders its page again after it changes the command.
