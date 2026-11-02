### Bug fixes

- **The Mend Renovate app goes on rebasing a branch that a bot of the repository committed to:** a commit of the fix bot or the branch bot no longer makes Renovate leave its branch to a person. A repository with the answer `renovate_runner: mend` and a release app gets the rule `gitIgnoredAuthors` with its next update of the blueprint, made from the name of the app alone, and the checklist no longer asks you to add it by hand; a line that you added to `.github/renovate.json5` for this can go, and does no harm where it stays.
