# A project writes about its releases between two marked lines of CONTRIBUTING.md

- Status: accepted
- Date: 2026-11-01

## Context

`## Releases` of `CONTRIBUTING.md` belongs to the blueprint, and each of its paragraphs is one line. issue-assistant, player-switch-for-autodarts and homedarts-for-autodarts each wrote a sentence of their own into its first paragraph, so every change of that paragraph in the blueprint conflicted in all three, and an update with a conflict waits for a person and stops the Rollout there.

One of those sentences only repaired another: player-switch-for-autodarts is a Node package that sets `PUBLISH_TO` to `none` in `.github/repository.project.toml`, but its guide said that a release "delivers it to npm", because `publish_to` follows the kind of project alone. `SECURITY.md`, the settings and the answers of the Best Practices said the same.

## Options

1. A file of the project, `.github/contributing.project.md`, that the guide links, as `AGENTS.md` links `.github/agents.project.md`. It can never conflict, but every repository gets a link to a page that is mostly empty, and a reader takes two clicks to the release guide that the sentence names.
2. An answer of Copier that holds the text. The guide stays one page and never differs from what the blueprint renders, but a sentence then lives in a YAML file, and a change of a word needs `copier update --data`.
3. Two marked lines in `## Releases`, as HTML comments. An update merges line by line, and the lines around the text never change, so it keeps the text; an empty part shows nothing on the page.
4. For the delivery, a sentence that hedges: "delivers it as `PUBLISH_TO` says". It is never wrong, and it tells nobody anything.

## Decision

Option 3, and an answer for the delivery.

- **The part** is what lies between the two lines of `PART_START` and `PART_END` in `blueprint/ownership.py`, which `template/CONTRIBUTING.md.jinja` writes at the end of `## Releases`. Not right after the first paragraph, where the sentences of the projects were: a merge that adds lines right after a line that both sides changed marks a conflict, even when both changed it the same, so the update that brings the part would have stopped the Rollout at issue-assistant. Tests run a real `copier update` on the guide: the update that brings the part to a repository with a sentence in the paragraph, and one that changes the paragraphs on both sides of a filled part.
- **The notice of [0092](0092-a-pull-request-hears-when-it-changes-a-file-of-the-blueprint.md) leaves the part alone.** The file stays on the list, as a change of any other line can conflict. The step of *lint* and the report of the PR coach read the diff of the file, and a change whose every line lies between the two marked lines isn't a change of a file of the blueprint, also with `BLUEPRINT_OWNERSHIP=fail`. A change of a marked line, or a diff that GitHub finds too long to show, still counts.
- **A sentence that holds for a whole kind goes into the template:** that repositories receive the release of an action as a Dependabot pull request is true of every action, so the guide of that kind says it, in the words of issue-assistant, whose update then merges without a conflict and leaves it no change of its own.
- **`publish_to_npm`** is a question for a Node package, yes by default, and no makes `publish_to` `none`. `PUBLISH_TO`, the guide, `SECURITY.md`, the answers of the Best Practices, `package.json` and the README of a new project all follow from that one answer. It is only for this kind: the other kinds with a registry have no project that needs it, and each would need its own tests.

## Consequences

Existing repositories move their sentences once, in a pull request after the update that brings the marked lines; that change gets the notice, as it changes the paragraph, and the next ones don't. A project with `publish_to_npm` no also drops `PUBLISH_TO` from `.github/repository.project.toml`, once `copier update --data publish_to_npm=false` has set it.

A project can still damage the part, by deleting a marked line. The change then gets the notice like any other, and the next update leaves the deletion as it is.

The part is one place in one file, on purpose. A second one is a new line in `blueprint/ownership.py` and in this record, not a mechanism that any Markdown file can use.
