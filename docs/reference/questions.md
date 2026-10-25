---
description: Every question of the Copier template of Repo Blueprint, with its default, when Copier asks it and the answers it refuses, the values worked out from the answers and the files that belong to a project.
---

# The questions of Copier

<!-- reference.py writes this page from copier.yml: change copier.yml and run python3 reference.py. -->

Copier asks these 26 questions when it copies the blueprint, in this order, and keeps the answers in `.copier-answers.yml`, so that `copier update` asks only a new question. `--data name=value` gives an answer without the question, also later: `copier update --defaults --vcs-ref=:current: --data name=value` changes an answer of an existing repository, and the defaults of Copier's [settings file](https://copier.readthedocs.io/en/stable/settings/) answer the questions that stay the same for all of your repositories, as [your own account](../own-account.md) shows. A default that is a template of Copier comes from the answers before it, in the delimiters of the blueprint: `{= … =}` for a value and `[% … %]` for a block.

- [`project_name`](#project_name): The name of the project, such as "Paperless Sync"
- [`project_slug`](#project_slug): The name of the repository; owner.github.io, such as dennis-otto.github.io, for the website of the owner itself
- [`description`](#description): One sentence that says what the project does
- [`project_type`](#project_type): The kind of project
- [`owner`](#owner): The GitHub account or organization of the repository, such as octo-org
- [`author`](#author): The maintainer, named in the license and the governance
- [`copyright`](#copyright): The copyright of the license, years and holder; several separated by semicolons
- [`license`](#license): The license
- [`python_package`](#python_package): The name of the Python package or module
- [`ha_domain`](#ha_domain): The domain of the integration in Home Assistant
- [`nextcloud_app_id`](#nextcloud_app_id): The id of the Nextcloud app, 32 characters at most
- [`nextcloud_namespace`](#nextcloud_namespace): The PHP namespace of the app, under OCA
- [`languages`](#languages): The languages of the code, which CodeQL analyzes (it has no PHP)
- [`discussions`](#discussions): Use GitHub Discussions for questions, ideas and the announcements of releases
- [`successor`](#successor): The owner has designated a successor through GitHub's account successor setting, who can take over the repository
- [`homepage`](#homepage): The website of the project; by default the one that the Docs workflow publishes on GitHub Pages, empty for none
- [`topics`](#topics): The topics of the repository, separated by commas; up to 20, each of lowercase letters, digits and hyphens
- [`sponsor`](#sponsor): The GitHub Sponsors account of the sponsor button; empty for none
- [`release_app`](#release_app): The GitHub App of the owner that opens the release and update pull requests, by the name in its address (github.com/apps/NAME); empty to register one after the copy, as the checklist shows
- [`release_app_client_id`](#release_app_client_id): The Client ID of the release app, on its settings page, such as Iv23li…
- [`release_app_id`](#release_app_id): The App ID of the release app, the number on its settings page
- [`renovate_runner`](#renovate_runner): Who runs Renovate, which opens the updates of the dependencies
- [`issue_assistant_ai`](#issue_assistant_ai): Let an AI engine, Claude, analyze each new issue, with its token as a secret of the environment issue-assistant
- [`sample_code`](#sample_code): Start with sample code and tests; an existing repository that takes the blueprint answers no
- [`test_workflows`](#test_workflows): Other workflows of the repository that run tests, by their names and separated by commas, whose failed jobs the flaky-test bot runs once more; empty for none
- [`test_marker`](#test_marker): The text before the name of each test or step in the logs of the tests that pytest doesn't run, such as "Browser step:", by which the flaky-test bot names the test that failed; empty for none

## The questions

### `project_name`

The name of the project, such as "Paperless Sync".

The name and the description stand as they are in a docstring of Python, a comment of TypeScript and the CDATA of appinfo/info.xml, which """, \*/ and \]\]> would end, and a backslash would start an escape there; the other files escape them.

- **Type:** text
- **Asked:** always
- **When Copier refuses an answer, it says:** Name the project. Write the name without """, \*/, \]\]>, backslashes and line breaks, which would end or break the code that names it.
- **Default:** none: Copier asks for it

### `project_slug`

The name of the repository; owner.github.io, such as dennis-otto.github.io, for the website of the owner itself.

- **Type:** text
- **Asked:** always
- **When Copier refuses an answer, it says:** Use lowercase letters, digits and hyphens, or the name of the website of an owner, such as dennis-otto.github.io.
- **Default:** a template of Copier, from the answers before it:

```text
{= project_name | lower | regex_replace('[^a-z0-9]+', '-') | trim('-') =}
```

### `description`

One sentence that says what the project does.

- **Type:** text
- **Asked:** always
- **When Copier refuses an answer, it says:** Describe the project in one sentence. Write the description without """, \*/, \]\]>, backslashes and line breaks, which would end or break the code that quotes it.
- **Default:** none: Copier asks for it

### `project_type`

The kind of project.

- **Type:** one of the choices
- **Asked:** always
- **Default:** none: Copier asks for it

| Answer | What Copier shows |
| --- | --- |
| `home-assistant` | Home Assistant integration (Python, HACS) |
| `nextcloud-app` | Nextcloud app (PHP, App Store) |
| `github-action` | GitHub Action (Python, composite) |
| `python-package` | Python package (PyPI) |
| `node-package` | Node package (TypeScript, npm) |
| `chrome-extension` | Chrome extension (Manifest V3, Chrome Web Store) |
| `container` | Container image (GHCR) |
| `generic` | Repository without a build (docs, configuration, scripts) |

### `owner`

The GitHub account or organization of the repository, such as octo-org.

No default: each owner names their account, or sets it once for all of their repositories in the defaults of Copier's settings file.

- **Type:** text
- **Asked:** always
- **When Copier refuses an answer, it says:** Name the GitHub account or organization of the repository, such as octo-org.
- **Default:** none: Copier asks for it

### `author`

The maintainer, named in the license and the governance.

- **Type:** text
- **Asked:** always
- **When Copier refuses an answer, it says:** Name the maintainer.
- **Default:** a template of Copier, from the answers before it:

```text
[% if owner == blueprint_owner.account %]{= blueprint_owner.author =}
[% else %]{= owner =}
[% endif %]
```

### `copyright`

The copyright of the license, years and holder; several separated by semicolons.

- **Type:** text
- **Asked:** always
- **Default:** `{= '%Y' | strftime =} {= author =}`, a template of Copier

### `license`

The license.

- **Type:** one of the choices
- **Asked:** always
- **Default:** a template of Copier, from the answers before it:

```text
[% if project_type == 'nextcloud-app' %]AGPL-3.0-or-later
[% else %]MIT
[% endif %]
```

| Answer | What Copier shows |
| --- | --- |
| `MIT` | MIT |
| `MIT-0` | MIT No Attribution (MIT-0) |
| `BSD-3-Clause` | BSD 3-Clause |
| `Apache-2.0` | Apache 2.0 |
| `GPL-3.0-or-later` | GPL 3.0 or later |
| `AGPL-3.0-or-later` | AGPL 3.0 or later |

### `python_package`

The name of the Python package or module.

- **Type:** text
- **Asked:** only when `project_type in ['python-package', 'github-action', 'home-assistant']`
- **When Copier refuses an answer, it says:** Use lowercase letters, digits and underscores.
- **Default:** `{= project_slug | replace('-', '_') =}`, a template of Copier

### `ha_domain`

The domain of the integration in Home Assistant.

- **Type:** text
- **Asked:** only when `project_type == 'home-assistant'`
- **When Copier refuses an answer, it says:** Use lowercase letters, digits and underscores.
- **Default:** `{= python_package =}`, a template of Copier

### `nextcloud_app_id`

The id of the Nextcloud app, 32 characters at most.

The App Store takes an id of 32 characters at most, from a lowercase letter to a letter or a digit, as the schema of appinfo/info.xml says.

- **Type:** text
- **Asked:** only when `project_type == 'nextcloud-app'`
- **When Copier refuses an answer, it says:** Use 2 to 32 lowercase letters, digits and underscores, from a letter to a letter or a digit, as the App Store takes them.
- **Default:** `{= (project_slug | replace('-', '_'))[:32] | trim('_') =}`, a template of Copier

### `nextcloud_namespace`

The PHP namespace of the app, under OCA.

- **Type:** text
- **Asked:** only when `project_type == 'nextcloud-app'`
- **When Copier refuses an answer, it says:** Use a name of PHP in CamelCase, such as PaperlessSync or Files\_Sharing: a capital letter, then letters, digits and underscores.
- **Default:** a template of Copier, from the answers before it:

```text
{= project_name | regex_replace('[^A-Za-z0-9]+', ' ') | title | replace(' ', '') =}
```

### `languages`

The languages of the code, which CodeQL analyzes (it has no PHP).

- **Type:** several of the choices
- **Asked:** always
- **Default:** a template of Copier, from the answers before it:

```text
[%- if project_type in ['home-assistant', 'github-action', 'python-package'] -%][python]
[%- elif project_type in ['node-package', 'chrome-extension', 'nextcloud-app'] -%][javascript-typescript]
[%- else -%][]
[%- endif -%]
```

| Answer | What Copier shows |
| --- | --- |
| `python` | Python |
| `javascript-typescript` | JavaScript or TypeScript |
| `go` | Go |
| `java-kotlin` | Java or Kotlin |
| `ruby` | Ruby |
| `rust` | Rust |

### `discussions`

Use GitHub Discussions for questions, ideas and the announcements of releases.

- **Type:** yes or no
- **Asked:** always
- **Default:** yes

### `successor`

The owner has designated a successor through GitHub's account successor setting, who can take over the repository.

- **Type:** yes or no
- **Asked:** always
- **Default:** no

### `homepage`

The website of the project; by default the one that the Docs workflow publishes on GitHub Pages, empty for none.

The website that the Docs workflow publishes on GitHub Pages, at the address that mkdocs.yml names: the README, the About box of the repository, the issue forms and the manifest of an integration or an app link it.

- **Type:** text
- **Asked:** always
- **When Copier refuses an answer, it says:** Name the address of the website, such as `https://octo-org.github.io/demo/`, or leave it empty.
- **Default:** a template of Copier, from the answers before it:

```text
https://{= owner | lower =}.github.io/
[% if project_slug != (owner | lower) ~ '.github.io' %]{= project_slug =}/
[% endif %]
```

### `topics`

The topics of the repository, separated by commas; up to 20, each of lowercase letters, digits and hyphens.

The topics of the repository on GitHub, with those of each kind by default: HACS lists an integration only with topics, and its check asks for them.

- **Type:** text
- **Asked:** always
- **When Copier refuses an answer, it says:** Separate up to 20 topics by commas, each of 50 characters at most, with lowercase letters, digits and hyphens, such as home-assistant. HACS lists an integration only with topics, and its check asks for them: name at least one, such as home-assistant.
- **Default:** a template of Copier, from the answers before it:

```text
[%- if project_type == 'home-assistant' -%]home-assistant, hacs, hacs-integration, home-assistant-integration, home-assistant-custom-component, homeassistant
[%- elif project_type == 'nextcloud-app' -%]nextcloud, nextcloud-app
[%- elif project_type == 'github-action' -%]github-actions, github-action
[%- elif project_type == 'python-package' -%]python, pypi
[%- elif project_type == 'node-package' -%]typescript, nodejs, npm
[%- elif project_type == 'chrome-extension' -%]chrome-extension, browser-extension, manifest-v3
[%- elif project_type == 'container' -%]docker, container, ghcr
[%- endif -%]
```

### `sponsor`

The GitHub Sponsors account of the sponsor button; empty for none.

- **Type:** text
- **Asked:** always
- **When Copier refuses an answer, it says:** Name a GitHub account, or leave it empty.
- **Default:** `{= owner =}`, a template of Copier

### `release_app`

The GitHub App of the owner that opens the release and update pull requests, by the name in its address (github.com/apps/NAME); empty to register one after the copy, as the checklist shows.

The GitHub App of the release and update pull requests, whose token starts their checks, signs the release tags and runs the bots. Empty for none yet: the checklist then shows how to register one, and copier update with these answers names it.

- **Type:** text
- **Asked:** always
- **When Copier refuses an answer, it says:** Name the app as its address does, github.com/apps/NAME, with lowercase letters, digits and hyphens, or leave it empty.
- **Default:** a template of Copier, from the answers before it:

```text
[% if owner == blueprint_owner.account %]{= blueprint_owner.release_app =}
[% endif %]
```

### `release_app_client_id`

The Client ID of the release app, on its settings page, such as Iv23li…

- **Type:** text
- **Asked:** only when `release_app != ''`
- **When Copier refuses an answer, it says:** Copy the Client ID from the settings page of the app, such as Iv23li…; the App ID is the number next to it.
- **Default:** a template of Copier, from the answers before it:

```text
[% if release_app == blueprint_owner.release_app %]{= blueprint_owner.release_app_client_id =}
[% endif %]
```

### `release_app_id`

The App ID of the release app, the number on its settings page.

- **Type:** text
- **Asked:** only when `release_app != ''`
- **When Copier refuses an answer, it says:** Copy the App ID, a number, from the settings page of the app.
- **Default:** a template of Copier, from the answers before it:

```text
[% if release_app == blueprint_owner.release_app %]{= blueprint_owner.release_app_id =}
[% endif %]
```

### `renovate_runner`

Who runs Renovate, which opens the updates of the dependencies.

Who runs Renovate, which opens the updates of the dependencies: a workflow of the repository itself, as the release app; the Mend Renovate app, which the owner installs; or the Renovate workflow of the blueprint, which runs it for every repository of the blueprint's owner and only for them.

- **Type:** one of the choices
- **Asked:** always
- **When Copier refuses an answer, it says:** The Renovate workflow of the blueprint runs only for the repositories of Dennis-Otto: choose a workflow in this repository (self) or the Mend Renovate app (mend). The Renovate workflow of the blueprint already runs for every repository of Dennis-Otto that has its rules, so a second Renovate would fight it over the branches: choose the blueprint's workflow (hub).
- **Default:** a template of Copier, from the answers before it:

```text
[% if owner == blueprint_owner.account %]hub
[% else %]self
[% endif %]
```

| Answer | What Copier shows |
| --- | --- |
| `self` | A Renovate workflow in this repository, as the release app (self) |
| `mend` | The Mend Renovate app, which the owner installs (mend) |
| `hub` | The Renovate workflow of the blueprint, for the repositories of its owner (hub) |

### `issue_assistant_ai`

Let an AI engine, Claude, analyze each new issue, with its token as a secret of the environment issue-assistant.

The issue assistant labels the issues and answers its commands without AI; with AI, the engine of .github/issue-assistant/config.toml, Claude, also analyzes each new issue, with its secret in the environment issue-assistant.

- **Type:** yes or no
- **Asked:** always
- **Default:** yes

### `sample_code`

Start with sample code and tests; an existing repository that takes the blueprint answers no.

- **Type:** yes or no
- **Asked:** always
- **Default:** yes

### `test_workflows`

Other workflows of the repository that run tests, by their names and separated by commas, whose failed jobs the flaky-test bot runs once more; empty for none.

The flaky-test bot watches the CI and Docker E2E of every repository; a repository whose other workflows run tests, such as visual tests, names them here.

- **Type:** text
- **Asked:** always
- **When Copier refuses an answer, it says:** Name each workflow as the name: line of its file does, with letters, digits, spaces and ( ) . \_ / - only, and separate them by commas.
- **Default:** empty

### `test_marker`

The text before the name of each test or step in the logs of the tests that pytest doesn't run, such as "Browser step:", by which the flaky-test bot names the test that failed; empty for none.

The flaky-test bot names the tests that pytest lists as failed in the log of a job. Other tests, such as the browser tests of a Docker E2E, write a line of their own as each test or step starts: the bot names the one that the log names last before the failure, and takes the first exception after that line as the error.

- **Type:** text
- **Asked:** always
- **When Copier refuses an answer, it says:** Write the text as the log writes it, with letters, digits, spaces and : ( ) . \_ / # > = - only, and at least one that isn't a space.
- **Default:** empty

## The values that Copier works out

Copier never asks these and doesn't keep them in `.copier-answers.yml`: the files of the template read them, and Copier works them out from the answers at every copy and update.

### `blueprint_owner`

The owner of this blueprint, whose own repositories keep its name and its release app as their defaults; every other owner names their own. A fork of the blueprint names its owner here. Never asked and not stored.

- **Type:** YAML
- **Default:** these values, as YAML:

```yaml
account: Dennis-Otto
author: Dennis Otto
release_app: dennis-otto-release-automation
release_app_client_id: Iv23liP9PIEHOV74AiIA
release_app_id: '4739928'
```

### `stack`

- **Type:** text
- **Default:** a template of Copier, from the answers before it:

```text
[%- if project_type == 'home-assistant' -%]home-assistant
[%- elif project_type == 'nextcloud-app' -%]php
[%- elif project_type in ['github-action', 'python-package'] -%]python
[%- elif project_type in ['node-package', 'chrome-extension'] -%]node
[%- elif project_type == 'container' -%]container
[%- else -%]generic
[%- endif -%]
```

### `publish_to`

- **Type:** text
- **Default:** a template of Copier, from the answers before it:

```text
[%- if project_type == 'home-assistant' -%]hacs
[%- elif project_type == 'nextcloud-app' -%]nextcloud-appstore
[%- elif project_type == 'github-action' -%]github-action
[%- elif project_type == 'python-package' -%]pypi
[%- elif project_type == 'node-package' -%]npm
[%- elif project_type == 'chrome-extension' -%]chrome-web-store
[%- elif project_type == 'container' -%]ghcr
[%- else -%]none
[%- endif -%]
```

### `codeql_languages`

The languages CodeQL analyzes, besides the workflows; it has no PHP.

- **Type:** text
- **Default:** a template of Copier, from the answers before it:

```text
[%- set found = [] -%]
[%- for language in ['python', 'javascript-typescript', 'go', 'java-kotlin', 'ruby', 'rust'] if language in languages -%]
[%- set _ = found.append(language) -%]
[%- endfor -%] [{= (found + ['actions']) | join(', ') =}]
```

### `ci_workflow`

The workflow of the checks: the stack's, or one with the action's own test run.

- **Type:** text
- **Default:** a template of Copier, from the answers before it:

```text
[% if project_type == 'github-action' %]github-action
[% else %]{= stack =}
[% endif %]
```

### `python_version`

Home Assistant needs the newest Python; actions run on the runner's Python 3.12.

- **Type:** text
- **Default:** a template of Copier, from the answers before it:

```text
[% if stack == 'home-assistant' %]3.14
[% else %]3.12
[% endif %]
```

### `release_type`

How the release bot finds the version: Python and Node in their manifests, the others in version.txt, with the version in other files kept equal.

- **Type:** text
- **Default:** a template of Copier, from the answers before it:

```text
[%- if project_type == 'python-package' -%]python
[%- elif stack == 'node' -%]node
[%- else -%]simple
[%- endif -%]
```

### `schedule_slot`

The slot of the schedules of this repository, so that the scheduled workflows of the repositories of one owner don't all start in the same minute and wait for the same runners (decision 0083): includes/replace.jinja moves each weekly schedule of a workflow of the blueprint by as many days, and every one by 8 minutes for each. The blueprint keeps its own times, slot 0; a repository of .github/fleet.toml takes its place in the Rollout, so that each has a day of its own; any other one a slot from the hash of its name.

- **Type:** a number
- **Default:** a template of Copier, from the answers before it:

```text
[%- set fleet -%]
[% include ".github/fleet.toml" %]
[%- endset -%]
[%- set slot = namespace(value=((owner ~ '/' ~ project_slug) | hash('md5'))[:8] | int(base=16) % 28) -%]
[%- if owner == blueprint_owner.account and project_slug == 'repo-blueprint' -%]
[%- set slot.value = 0 -%]
[%- elif ('\nowner = "' ~ owner ~ '"\n') in fleet -%]
[%- for entry in fleet.split('[[repository]]')[1:] if ('\nname = "' ~ project_slug ~ '"\n') in entry -%]
[%- set slot.value = entry | regex_search('\nrollout = [0-9]+\n') | trim | replace('rollout = ', '') | int -%]
[%- endfor -%]
[%- endif -%] {= slot.value =}
```

## The files of a project

After the first copy, these belong to the project: an update never overwrites them. Renovate keeps the dependency manifests of the project current. The patterns follow .gitignore: those without a slash would match at any depth, so the files of the root start with one. template/AGENTS.md.jinja lists them for coding agents, and a test keeps both lists equal.

<details markdown>
<summary>The 58 patterns of the files of a project</summary>

- `/README.md`
- `/CHANGELOG.md`
- `/version.txt`
- `/.release-please-manifest.json`
- `/mkdocs.yml`
- `/docs/index.md`
- `/docs/security.md`
- `/docs/releases.md`
- `.github/issue-assistant/project.md`
- `.github/agents.project.md`
- `/docs/decisions`
- `.github/ISSUE_TEMPLATE/bug_report.yml`
- `.github/ISSUE_TEMPLATE/feature_request.yml`
- `.github/ISSUE_TEMPLATE/config.yml`
- `.github/DISCUSSION_TEMPLATE/q-a.yml`
- `.github/DISCUSSION_TEMPLATE/ideas.yml`
- `.github/labels.toml`
- `.github/labeler.yml`
- `/.markdownlint.jsonc`
- `.github/cspell-words.txt`
- `.github/renovate.json5`
- `.github/renovate-accepted.json5`
- `/osv-scanner.toml`
- `.github/findings.toml`
- `.github/dependency-review.yml`
- `.github/social-preview.html`
- `/scripts/screenshots.sh`
- `.github/screenshots-paths.txt`
- `.github/repository.project.toml`
- `.github/checks.project.toml`
- `.github/workflows/action-test.yml`
- `/.lycheeignore`
- `/pyproject.toml`
- `/requirements-dev.in`
- `/requirements-dev.txt`
- `/requirements-test.in`
- `/requirements-test.txt`
- `/requirements-fuzz.in`
- `/requirements-fuzz.txt`
- `/fuzz`
- `/composer.json`
- `/composer.lock`
- `/package.json`
- `/package-lock.json`
- `/extension`
- `/store`
- `/Dockerfile`
- `/action.yml`
- `/hacs.json`
- `/src`
- `/lib`
- `/app`
- `/appinfo`
- `/img`
- `/custom_components`
- `/tests`
- `/test`
- `/*.py`

</details>
