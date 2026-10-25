# A private repository passes its checks without what its plan lacks

- Status: accepted
- Date: 2026-10-25

## Context

`blueprint.py create --private` makes a private repository, and many people try a template on a private one first. GitHub offers a private repository less than a public one: code scanning and the dependency review only with GitHub Code Security, secret scanning only with GitHub Secret Protection, both for organizations on GitHub Team or Enterprise, and the rulesets and GitHub Pages only on a paid plan, GitHub Pro, Team or Enterprise. On GitHub Free, the plan of most people, the first pull request of such a repository was red: the required checks *codeql* and *dependency-review* failed on their uploads to GitHub, as did zizmor, OSV-Scanner, the Scorecard and the Findings workflow, and `settings apply` failed on the rulesets and the website that GitHub refused. [Decision 0055](0055-what-github-does-not-do-for-a-repository-fails-no-settings-run.md) already lets a switch that the plan lacks fail no settings run, but only for the switches of `security_and_analysis`, and nothing told the workflows.

## Options

1. Document what a private repository lacks and leave the checks red until its owner pays: the first run of every evaluator stays red, and a red check that no one can fix teaches everyone to ignore red.
2. Leave the checks that need code scanning out of the required checks of a private repository: they would still fail on every pull request, only without stopping its merge, and nothing would look at the code.
3. Let the settings read what GitHub offers the repository and tell the workflows by variables, which switch each check to what it can do without the part: every check still runs and passes where nothing is wrong, and keeps its name, so the required checks stay as they are.

## Decision

Option 3.

- **The plan.** `settings apply` and the checklist read whether the repository is private and whether `security_and_analysis` has `advanced_security` or `code_security` on. A private repository without it gets the variables `CODE_SCANNING` and `DEPENDENCY_REVIEW` set to `off`, and the ruleset of `main` loses its rule of code scanning, which would wait for an analysis that no tool can upload. Where GitHub offers them again, the variables turn `on`; one that `[variables]` of the settings as code names decides instead. A token that may not read `security_and_analysis` decides nothing.
- **What GitHub refuses for the plan.** A part of the settings that GitHub refuses with an answer that names the plan, such as "Upgrade to GitHub Pro or make this repository public" for a ruleset or "Your current plan does not support GitHub Pages" for the website, is a notice of the run with that answer, which fails nothing, like the switches of decision 0055. Every other refusal still fails the run. The checklist, which only reads, shows *Settings as code applied* as neutral when a private repository lacks only rulesets or the website, and a private repository gets the step *GitHub Code Security on*, neutral without it.
- **The workflows,** with `CODE_SCANNING` at `off`: CodeQL doesn't analyze, because its terms allow it on the code of a private repository only with a licence of GitHub Code Security or Advanced Security, and its check *codeql* passes with a notice that says so; zizmor fails on every finding, with an annotation at its line, as code scanning stops every new alert of zizmor; OSV-Scanner, the Scorecard and the taint analysis of PHP keep their findings in their checks and artifacts; the Findings workflow, which keeps the alerts of code scanning fixed or accepted, doesn't run. With `DEPENDENCY_REVIEW` at `off`, the check *dependency-review* leaves the vulnerabilities to the check *osv-scanner (pull request)*, which compares the lock files of the pull request with those of its base, and says so in its summary.
- **The website** of a run on `main` of a private repository that GitHub Pages doesn't publish is the artifact `website`, as that of a pull request is.
- **A public repository** sets none of the variables, and every workflow runs as before.

## Consequences

The first pull request of a private repository on GitHub Free is green where its code is, and the Settings workflow passes. Such a repository has no analysis of CodeQL, which its terms don't allow there; zizmor, OSV-Scanner and the linters of `check.sh` still look at the code. Environments and their secrets need GitHub Pro, Team or Enterprise on a private repository, and whether GitHub refuses them with an answer that names the plan is still to be seen on a real repository. The dependency review of a private repository on GitHub Free checks no licenses, and nothing protects `main` from a push: the FAQ shows what works on which plan. Code scanning, the dependency review, the rulesets and the website come with the next run of the settings once the repository is public or on a plan that has them.
