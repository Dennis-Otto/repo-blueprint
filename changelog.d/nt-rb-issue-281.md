### Bug fixes

- **`settings check` names every step that runs an image with `docker://`:** GitHub counts such a step as an action and refuses it unless every action may run, so a workflow with one failed to start once the settings bot had switched to the selected actions, while the check had passed. The check now names each such step, in a workflow or in an action that a workflow runs, with the `docker run --rm` in a `run:` step that replaces it, and `settings apply` no longer switches a repository that still allows every action to the selected ones while such a step exists.
