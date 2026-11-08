# The blueprint answers what it guarantees of the Baseline and of gold

- Status: accepted
- Date: 2026-11-08

## Context

`.bestpractices.json` proposes the answers of OpenSSF Best Practices that the blueprint guarantees for every repository ([decision 0047](0047-every-repository-proposes-the-best-practices-answers-that-the-blueprint-guarantees.md)). Once bestpractices.dev had taken in its proposals on every level of the eight projects made from the blueprint, the same criteria stayed open in each of them: of the OSPS Baseline, OSPS-AC-02.01 (how a new collaborator gets access), OSPS-QA-05.01 and 05.02 (no generated program and no binary that nobody can review in Git), OSPS-DO-06.01 (how the project selects, obtains and tracks its dependencies), OSPS-BR-07.02 (a policy for secrets and credentials) and OSPS-GV-04.01 (a review of a person before escalated permissions); of gold, `small_tasks` and `code_review_standards`; and a few more that only a person can answer. What every project shares belongs in the template rather than in eight forms, but only where the answer is true for every project.

## Options

1. **Leave them to the owner,** in the form of each project: the same answers, typed eight times, and none of them checked.
2. **Propose them all,** also a second reviewer, unassociated contributors, a security review and the coverage of the tests: answers that a project of one maintainer, or one whose files ask for less, can't keep.
3. **Propose what the blueprint guarantees,** after it writes the rules that are missing and adds the check that a criterion needs, and leave the rest to the owner, listed in the guide.

## Decision

Option 3. The template states the rules, and `.bestpractices.json` proposes each with the file that shows it:

- **OSPS-AC-02.01 and OSPS-GV-04.01:** GOVERNANCE.md says that nobody gets access on their own, as GitHub invites a collaborator only by hand, and that the maintainers review a person before escalated permissions: their reviewed contributions, a traceable identity, two-factor authentication and signed commits; the least access, named in the table of maintainers, which ends with the task.
- **`code_review_standards`:** the section Reviews of GOVERNANCE.md says how a pull request is reviewed, what the review checks and what it needs to be accepted.
- **OSPS-DO-06.01 and OSPS-BR-07.02:** SECURITY.md describes how dependencies are selected, obtained and tracked, and how secrets are stored, used and rotated.
- **`small_tasks`:** CONTRIBUTING.md names the label `good first issue`, which every repository has and GitHub lists on its page Contribute.
- **OSPS-QA-05.01 and 05.02:** a new step of `scripts/check.sh`, *Binary files*, runs `blueprint.py binaries` and fails on a program, a library, compiled code or an archive in Git, by its first bytes whatever its name, and on every other binary file but pictures, videos, sounds, fonts, documents and the inputs of the fuzz tests in `fuzz/`, which the Baseline counts as reviewable. A file is binary as Git sees it, with a NUL in its first 8000 bytes.

Left to the owner, as the guide lists them: OSPS-QA-04.01 and 04.02 (N/A only when every release builds from this repository alone, which only the owner knows), OSPS-QA-07.01, `two_person_review`, `contributors_unassociated`, `secure_2FA` and `security_review` (people), `copyright_per_file` and `license_per_file` (REUSE.toml gives the license of every file at once, not in each file), the coverage of `test_statement_coverage90` and `test_branch_coverage80` (the files of a project set it, for the code that it measures) and `build_reproducible`.

## Consequences

Every repository proposes about 100 answers with its next update, the Baseline at level 1 all but OSPS-AC-01.01 and OSPS-QA-04.01. A repository with a binary file that is no picture, video, sound, font, document or fuzz input fails the step until the file leaves Git; none of the repositories that follow the blueprint has one today. A text file that a build generates, such as a bundle of JavaScript, isn't found by the step: the review and the ignore rules of the build keep it out. Coverage floors in `scripts/check.sh` and a header in each source file could later bring the remaining criteria of gold within reach.
