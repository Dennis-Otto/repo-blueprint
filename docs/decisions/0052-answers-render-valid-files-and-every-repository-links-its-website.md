# The answers render valid files, and every new repository links its website

- Status: accepted
- Date: 2026-10-18

## Context

The answers of Copier go into files of many languages. Most of them escape what they take, such as the JSON of `package.json` or the TOML of `repository.toml`, but a few take the name and the description as they are: the docstring of a Python module, the comment at the top of `src/index.ts` and the CDATA of `appinfo/info.xml`. A description with `"""`, `*/` or `]]>` ended them early, a backslash started an escape, and `$HOME` in a label of the `Dockerfile` became the folder of the build's user. The id of a Nextcloud app came from the name of the repository without a limit, while the App Store takes 32 characters at most, from a letter to a letter or a digit.

The homepage and the topics had no defaults. The website that the Docs workflow publishes for every repository was linked from nowhere: not from the README, not from the About box, not from the manifest of an integration or `appinfo/info.xml` of an app, so each of the blueprint's own repositories set it by hand. A new integration without topics failed the required check *hacs*, and HACS doesn't list it.

The templates that take a file of the blueprint and replace a text in it, such as the languages of `codeql.yml` or the jobs of the CI that only the blueprint skips, did so with `filter replace`, which replaces nothing when the text is gone. A reworded comment of the blueprint's workflow then left the blueprint's own values in every repository, and the test that compared the files removed the same line before it compared them.

## Options

1. Escape every answer for every target. That needs one escape per language and a test for each, and a docstring with `\"""` still reads badly.
2. Refuse at the question what a target can't take as it is, escape what the targets can, and give the homepage and the topics the defaults of each kind.
3. Leave it to the owner to answer well.

## Decision

Option 2.

- **The name and the description** may hold neither `"""`, `*/`, `]]>`, a backslash nor a line break: Copier says so at the question. The other files escape what they take: JSON and TOML by `to_json`, XML and HTML by `e`, the `Dockerfile` with `\$`, and the docstring of a Python package a quote at its end.
- **The id of a Nextcloud app** follows the schema of the App Store, 2 to 32 characters, and its default is cut to 32; the namespace is a name of PHP in CamelCase. A Nextcloud app analyzes JavaScript with CodeQL by default, as the apps of its pages do.
- **The homepage** is by default the website at the address that `mkdocs.yml` names, `https://OWNER.github.io/NAME/`, or the root for the website of an owner. The README shows a badge and a link to it, the About box gets it by `settings apply`, and the manifest of an integration and `appinfo/info.xml` of an app name it as their documentation and website; `info.xml` also names the discussions and the sponsor, in the order of its schema.
- **The topics** have the defaults of each kind, such as `home-assistant, hacs, hacs-integration` for an integration; an integration can't do without them, and GitHub's rules for topics apply to all: at most 20, each of 50 characters at most, of lowercase letters, digits and hyphens. The checklist of an integration shows whether the description and the topics are on GitHub.
- **A template that replaces a text of a file of the blueprint** does so with the macro `replaced` of `includes/replace.jinja`, which stops the render with the file and the text when the text is gone, so that a change of the blueprint's file fails the tests of the blueprint, never the repositories.

## Consequences

A new repository renders files that parse whatever its name and description say, links its website from its first commit, and an integration passes the check *hacs* with the default answers. An existing repository keeps its answers, which pass the new questions: the Variants test them with the answers of each repository of the Rollout. A change of a comment or a step that a template looks for, in a file of the blueprint, needs the template changed with it, and the error of the render names both.
