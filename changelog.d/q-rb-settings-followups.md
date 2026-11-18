### Bug fixes

- `blueprint.py checklist` no longer asks a repository to register and install the release app when its settings say that it has none, with `RELEASE_APP`, `RELEASE_AUTOMATION_CLIENT_ID` and `RELEASE_AUTOMATION_APP_ID` set to `""`: it ticks the release app off as left out by choice.
- When GitHub's rate limit or an outage stops `settings apply` in the middle of the rulesets or the variables, the run still names each one that GitHub refused before it, with its reason, instead of only the rate limit or the outage. The next run sends what was left, as before.
