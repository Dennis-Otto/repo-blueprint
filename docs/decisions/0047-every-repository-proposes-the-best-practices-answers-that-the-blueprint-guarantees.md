# Every repository proposes the answers of OpenSSF Best Practices that the blueprint guarantees

- Status: accepted
- Date: 2026-10-18

## Context

The [OpenSSF Best Practices badge](https://www.bestpractices.dev) asks about 200 questions of a project, for its metal series, passing, silver and gold, and for the three levels of the [OSPS Baseline](https://baseline.openssf.org), OpenSSF's current measure of the trust of a project. The blueprint holds silver, and its Baseline started at 0 % on every level, although its files, workflows and settings as code meet most of the criteria of the Baseline, and so do those of every repository made from it. Each maintainer answered every question by hand, with a justification that names the file that shows it.

bestpractices.dev reads a file `.bestpractices.json` at the root of the repository, when a project is added and when a maintainer presses *Save (and continue) 🤖* on a level, and proposes its answers: each criterion has a field `<criterion>_status`, such as `Met`, and `<criterion>_justification`. A criterion that the file leaves out, or answers with `?`, keeps the answer that the maintainer gave on the website.

## Options

1. **No file:** every maintainer answers everything by hand, as before, and most repositories never start the Baseline.
2. **A file of the project,** copied once and then the project's own: it can hold the answers that only the project knows, but it never learns of a change of the blueprint, such as a new check, and its answers grow false when the blueprint changes what they name.
3. **A file of the blueprint,** rendered for each repository with its own links, that answers only what the blueprint guarantees: what its files, its workflows and its settings as code make true for every repository of the kind and the answers of Copier, each with the link to the file that shows it.

## Decision

Option 3:

1. `template/.bestpractices.json.jinja` belongs to the blueprint, which renders it for every kind of project with the links of the repository. It answers `Met` only, and only what holds for every repository of the kind: the contribution guide, the license, the security policy and its private reporting, the governance, the DCO, the rulesets of `main`, the token permissions, the secret scanning, CodeQL, the dependency updates, the signed and attested releases with their SBOMs and OpenVEX, and for the kinds with a test suite and manifests of dependencies the answers about them. An answer of Copier decides some of them: a designated successor the continuity and the bus factor, a homepage outside GitHub Pages the sites.
2. What depends on the software or on the people of a project stays out: its cryptography, its user guides, its design and interfaces, its own security assessment, the knowledge of its developers, the times of its answers, the review by a second person and multi-factor authentication. bestpractices.dev keeps what the maintainer answers there.
3. The blueprint's own `.bestpractices.json` is its rendering as the GitHub Action it is rendered as, which `test_the_blueprint_follows_its_own_template` keeps equal.
4. The tests render every kind of project and check that each answer is one that bestpractices.dev knows, from the list of its criteria in `tests/data/bestpractices-criteria.json`, with the source that the file names; that every criterion that needs a link has one, every file that a link names is in the repository and every heading that it names in that file; and that none of the answers of the project is among them.
5. `blueprint.py checklist` shows the badges of both series, the badge of the metal series and that of the Baseline, and, once the README shows one of them, the form of the other with the number of the project.

## Consequences

- A new repository proposes about 90 to 100 answers, and a maintainer answers the rest; the Baseline of a repository no longer starts at 0 %.
- An update of the blueprint brings each new answer, and a changed one, to every repository: *Save (and continue) 🤖* on a level takes it in.
- A repository can't add its own answers to the file, which the next update would overwrite; it gives them on bestpractices.dev.
- When bestpractices.dev renames or adds criteria, `tests/data/bestpractices-criteria.json` is taken anew from its source, and the tests show which answers no longer fit.
