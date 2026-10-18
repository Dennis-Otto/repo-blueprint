# Every website shows its automation, written from its workflows

- Status: accepted
- Date: 2026-10-18

## Context

A repository made from the blueprint has 27 to 31 workflows, and the blueprint itself more than 50. A newcomer saw a folder of files, with no overview of what runs when, which checks a pull request needs and which workflows hold a secret, although nearly every workflow of the blueprint starts with a comment that says what it does. Three repositories wrote a page of their own about the release workflow of the blueprint, `docs/releases.md` in paperless-sync, paperless-unified-search and ha-autodarts, which fall behind with every release of the blueprint that changes it.

## Options

1. A page that each repository writes and keeps current by hand: it falls behind its workflows, as the three pages about the releases did.
2. A page that the template brings: a page of the project, which an update never changes, falls behind like the first; a page of the blueprint can't know the workflows of a project, such as the end-to-end tests of ha-autodarts.
3. A page that the hooks of every website write at every build, from `.github/workflows/` and the settings as code.

## Decision

Option 3, in the hook of every website, `.github/mkdocs_blueprint.py`: the page *Automation*, `automation.md`, which has no file in `docs/`.

- **What it shows:** what the workflows do, with the diagram of how a repository looks after itself; the checks that `[branch]` of `.github/repository.toml` and `.github/repository.project.toml` requires, each with the workflow that makes it; a table of what starts each workflow; and each workflow with the comment at its top, what starts it, each schedule in words, such as *every Tuesday at 04:40 UTC*, with the note that GitHub starts a schedule when it can, the checks of it that `main` requires, its environments and its secrets, by their names, and a link to its file. The comments are no Markdown, so that a comment can't break the page.
- **Groups:** checks, releases, bots, security and maintenance, by a word of the name of its file, and a workflow of a project without such a word by what starts it. The releases come with the diagram from a change to a release.
- **Where it comes from:** a workflow whose comment ends with the address of the blueprint names the blueprint as its origin, on the website of every other repository, so that a reader sees which workflows the updates bring.
- **What doesn't run:** a workflow of which no job runs in the repository of the website, such as the checks of the kinds of projects in the blueprint itself, stays out.
- **Languages:** the page speaks the language of the website, and a website in German gets a German page too, whose comments of the workflows are English and marked so.
- **The menu:** the template lists it after the security design, and the hook puts it there in a menu that doesn't name it, so that every repository gets it with its next update.
- **The address of the repository:** the links to the files take it from `repo_url` when that names owner and repository, and otherwise from an absolute `edit_uri`, as on a personal website whose `repo_url` is its owner's profile; without either the files show as plain names.
- **The title:** *Automation* in the menu of every website. A project where the word means something else, such as the automations of Home Assistant in ha-autodarts, names the page in its own menu, for example `- Repository automation: automation.md`.
- **The project decides:** a page `docs/automation.md` of the project takes its place, and `docs/automation.de.md` that of the German one; paperless-sync keeps its own.
- **Every workflow says what it does:** CodeQL, the dependency review and the Scorecard got the comment at their top that they lacked.

## Consequences

The page is always as current as the workflows, in every repository, with no work of its maintainer. The hook depends on two parts of MkDocs and its plugins: the i18n plugin takes a file of `docs/` that the folder doesn't hold as a page of its language, and MkDocs 1.6 takes the text of a file from `content_string`, which the hook sets after the i18n plugin. An update that changes either stops the strict build. The page is dated by the newest commit of the workflows and the settings. The pages about the releases that three repositories wrote can go, in pull requests of their own.
