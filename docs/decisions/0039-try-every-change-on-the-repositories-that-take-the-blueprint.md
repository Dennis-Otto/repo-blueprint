# Try every change of the template on the answers and the files of the repositories that take the blueprint, before its release

- Status: accepted, amended by [0099](0099-a-pull-request-runs-only-the-variants-whose-project-it-changes.md), by which a pull request runs only the adopted legs whose project it changes
- Date: 2026-10-18

## Context

The Rollout brings each release to every repository that takes the blueprint within minutes ([decision 0010](0010-roll-out-one-repository-at-a-time.md)), and the Variants workflow tried a release before only with the default answers: sample code, one language, the MIT license and discussions on. None of the five repositories looks like that. All of them took the blueprint without its sample code, the two Nextcloud apps have the AGPL and JavaScript, ha-autodarts two languages of CodeQL, and dennis-otto.github.io no discussions. They also changed files of the blueprint, such as `CONTRIBUTING.md`, `SUPPORT.md` or the configuration of the issue assistant. A conflict or a broken check showed only in the update pull request of each repository, after the release, as in ha-autodarts#148, and the path of an existing repository broke before without a test that saw it.

## Options

1. Keep the default answers, and fix each repository after the release.
2. Legs of the Variants with the answers of each repository, from a file of the blueprint.
3. As 2, and an update of each repository itself, cloned read-only, before the merge.
4. As 3, as a required check that fails on every conflict.

## Decision

Option 3.

- **`tests/answers/`** holds the answers of each repository that the Rollout brings releases to, as its `.copier-answers.yml` has them, without `_commit` and `_src_path`. A test keeps their names equal to those of the Rollout, renders each one without template syntax left, and fails while a question of `copier.yml` has no answer there. `python3 downstream.py --answers` writes them anew from GitHub.
- **A leg `adopted (…)` of the Variants for each:** from the latest release with these answers, updated to the pull request, it must give every file of the blueprint as a new repository with the same answers has it, without a conflict and without `--trust`, and pass the build of its website and the lint of its workflows and its Markdown. It runs no checks of the code, which only the repository has; the required check *variants* stands for these legs as well.
- **The Downstream workflow** clones each repository without a token and updates it as its blueprint bot does, once to the commit of `main` that the pull request merges into and once to the pull request, in one job, for the 20 runners of the account. Its summary names the files whose update the pull request changes and every conflict, with the conflicts that `main` has already apart. A conflict that the pull request brings into a file that is not a page of text, such as a workflow, a hook, a script, code or the configuration of a check or a bot, fails it; one in a page, Markdown, a text file or a license, warns, and so do answers that differ from those of the repository. It runs in the pull requests that change what the repositories get from the blueprint, and every week. It is no required check: a conflict in a page can be the right change, with a line in the changelog that says how a repository resolves it.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/how-a-change-of-the-template-meets-the-repositories.dark.svg">
  <img src="../images/diagrams/how-a-change-of-the-template-meets-the-repositories.svg" alt="How a change of the template meets the repositories before its release: A pull request changes what the repositories get from the blueprint. The Variants workflow makes a new repository of every kind, updates one of every kind from the latest release, and updates one with the answers of each repository in tests/answers, which must give every file as a new repository with these answers has it and pass the build of its website and the lint of its workflows and Markdown. The Downstream workflow clones each repository and updates it as its blueprint bot does, to main and to the pull request, and names the files whose update the pull request changes and every conflict; a conflict that the pull request brings into a workflow or a script fails it. Then the pull request merges, and the release and the Rollout bring it to every repository.">
</picture>

## Consequences

A pull request of the blueprint shows, before its merge, which files of which repository it changes and where it conflicts. The Variants run five more legs of about two minutes, and Downstream ten updates in one job. A repository that changes its answers, or a new one in the Rollout, needs its file in `tests/answers/` in the same week, or the Variants try other answers than its own until then; Downstream warns of it every week. A conflict that the five repositories have on `main` already, such as in their own `SUPPORT.md`, shows in every summary until they resolve it. The checks of the code of each repository, its `scripts/check.sh`, still run only in its update pull request.
