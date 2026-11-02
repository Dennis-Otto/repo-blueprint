### Features

- **A check in a workflow of your project fixes itself too:** the fix bot took the fixes of Lint and of the CI alone. Now it reads those of every workflow in the list of `after-checks.yml`, such as Docker E2E and what the answer `test_workflows` names, so that such a check gets the same commit, suggestion or pull request for `main`. It copies two steps from `ci.yml` and names its commands in `autofix`. The bot waits only for the workflows that keep fixes, so that a long run that keeps none holds up no fix, and it reads no workflow that the list of `main` doesn't name.
