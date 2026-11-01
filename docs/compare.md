---
description: "Repo Blueprint beside GitHub template repositories, Cookiecutter with cruft, other Copier templates such as copier-uv and scientific-python/cookie, and projen, feature by feature, also where another tool fits better."
---

# Repo Blueprint compared with template repositories, Cookiecutter, Copier templates and projen

Every tool on this page makes a new repository from a template. They differ in what happens after the copy: whether improvements of the template reach the repository later, whether code of the template runs on your machine, and how much of the repository beyond its files they look after. This page says where the blueprint leads, and where another tool fits better.

The tools: [template repositories](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-repository-from-a-template) of GitHub, [Cookiecutter](https://github.com/cookiecutter/cookiecutter) with [cruft](https://github.com/cruft/cruft), other templates of [Copier](https://copier.readthedocs.io/), such as [copier-uv](https://github.com/pawamoy/copier-uv) and [scientific-python/cookie](https://github.com/scientific-python/cookie), and [projen](https://github.com/projen/projen).

## Where the blueprint leads

- **A tested rollout to every repository.** Before a change of the template merges, the Variants workflow makes a new repository of every kind whose files it changes and updates one of each from the latest release, and the Downstream workflow updates a clone of each real repository with it. After the release, the Rollout workflow starts the blueprint bot of each repository, one after the other; the bot verifies the signed release, runs `copier update` and keeps one pull request, which merges itself once every check passes.
- **No code of the template runs at the copy.** The template has no tasks, migrations or Jinja extensions, so Copier needs no `--trust`, neither at the copy nor at an update.
- **Settings as code, with a bot against drift.** The rulesets, the security, Actions, the environments, the variables, the labels and GitHub Pages live in `.github/repository.toml`, and the settings bot applies them after every change and every week.
- **Releases of SLSA Build Level 3, with SBOMs and VEX.** A release has signed tags, the provenance of an isolated build (a container image has that of the release workflow, Level 2), SBOMs as SPDX and CycloneDX, an OpenVEX document and an immutable release, and its workflow verifies it as its users can, also every week.
- **Home Assistant, Nextcloud and GitHub Actions in one standard,** beside Python and Node packages, Chrome extensions, containers and repositories without a build: the same checks, bots and settings for each, with the tools of each kind.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="images/diagrams/how-a-change-of-the-template-meets-the-repositories.dark.svg">
  <img src="images/diagrams/how-a-change-of-the-template-meets-the-repositories.svg" alt="How a change of the template meets the repositories before its release: A pull request changes what the repositories get from the blueprint. The Variants workflow makes a new repository of every kind whose files the pull request changes, updates one of each from the latest release, and updates one with the answers of each repository in tests/answers whose files it changes, which must give every file as a new repository with these answers has it and pass the build of its website and the lint of its workflows and Markdown. The Downstream workflow clones each repository and updates it as its blueprint bot does, to main and to the pull request, and names the files whose update the pull request changes and every conflict; a conflict that the pull request brings into a workflow or a script fails it. Then the pull request merges, and the release and the Rollout bring it to every repository.">
</picture>

## Feature by feature

A dash means that the tool doesn't do it; *the template* means that it depends on what the template brings.

| | Repo Blueprint | Template repository | Cookiecutter + cruft | Other Copier templates | projen |
| --- | --- | --- | --- | --- | --- |
| Changes of the template after the copy | a bot brings each release as a pull request | — | `cruft update` by hand; `cruft check` fails when it is behind | `copier update` by hand | each run of `projen` writes the files anew |
| Updates tested before they arrive | on every kind and on the real repositories | — | — | the template | — |
| Code that runs at the copy | none; then `blueprint.py create` from the copy, which you start yourself | none | the hooks of the template, if any | the tasks, migrations and extensions of the template, if any, with `--trust` | `.projenrc` at every run |
| What a new repository needs | Git, Python, uv and the GitHub CLI | a button on GitHub | Python and `cookiecutter` | Python and `copier` | Node and `npx projen new` |
| Settings of the repository | as code, with a bot against drift | — | the template | the template | — |
| Releases | release-please, signed tags, SLSA Build Level 3 (container images: Level 2), SBOM, VEX, verified | the template | the template | the template | to npm, and with jsii to PyPI, Maven, NuGet and Go |
| Security checks | CodeQL, Scorecard, zizmor, OSV-Scanner, Harden-Runner, a secret scan, actions pinned to commits | the template | the template | the template | the template |
| Dependency updates | Renovate, with merge rules and a dashboard | the template | the template | the template | a workflow that upgrades them |
| Kinds of projects | eight, from Home Assistant to Chrome extensions and containers | one for each template | thousands of templates, one stack each | copier-uv: Python; cookie: Python with many build backends | TypeScript, AWS CDK, jsii, Python, Java and more |
| Systems in the CI | Linux, on every core | the template | the template | copier-uv and cookie: Linux, macOS and Windows | the template |
| Review of any repository | — | — | — | cookie: sp-repo-review | — |
| Triage of issues | the issue assistant | — | — | — | — |

## Where another tool fits better

- **A copy with a button and nothing else.** A template repository of GitHub needs no tools, no questions and no app, and is the simplest start for a repository that won't follow its template later.
- **Several systems in the CI, and uv for the project.** copier-uv and scientific-python/cookie test on Linux, macOS and Windows with several versions of Python, and copier-uv manages the project with uv. A repository of the blueprint tests on one Linux runner, on every core, and installs its tools with uv in the CI from lock files with hashes; only the blueprint itself runs its checks on Windows too.
- **A review of any repository.** [sp-repo-review](https://pypi.org/project/sp-repo-review/) checks a repository against the development guide of Scientific Python, also one that no template made. The checks of the blueprint look at repositories made from it.
- **A choice of build backends.** cookie offers a template for each of Hatchling, Flit, PDM, Poetry, setuptools, scikit-build-core, meson-python, maturin and others; the blueprint builds Python with Hatchling.
- **Projects defined in code.** projen suits AWS CDK and jsii above all, whose many files it keeps from one definition in code.
- **Simplicity.** A repository of the blueprint starts with more than 30 workflows, a release app and settings as code. A small project that wants none of that is better off with a smaller template.

## Start one

[The quick start](guide.md#start-a-repository) makes a repository in three commands, and each kind of project has a page of its own: [Home Assistant integration](kinds/home-assistant.md), [Nextcloud app](kinds/nextcloud-app.md), [GitHub Action](kinds/github-action.md), [Python package](kinds/python-package.md), [Node package](kinds/node-package.md), [Chrome extension](kinds/chrome-extension.md), [container image](kinds/container.md) and [repository without a build](kinds/generic.md).
