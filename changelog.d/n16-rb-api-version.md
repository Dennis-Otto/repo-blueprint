### Bug fixes

- **The bots ask GitHub for the version of its API:** every call of `gh api` in the workflows and in `blueprint.py` now sends `X-GitHub-Api-Version: 2022-11-28`, as GitHub recommends, so that the answers stay the same when the GitHub CLI or GitHub moves to a newer version of its REST API ([#690](https://github.com/Dennis-Otto/repo-blueprint/issues/690)). A workflow that a project adds of its own can ask the same way: `API_VERSION_HEADER: "X-GitHub-Api-Version: 2022-11-28"` in its `env:`, and `gh api --header "$API_VERSION_HEADER" …` for each call.
