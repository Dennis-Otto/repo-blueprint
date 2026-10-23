# Notes of the blueprint for coding agents

These notes add to `AGENTS.md` what a coding agent needs to know about how the blueprint works.

## Where things are

- `copier.yml` holds the questions, the values derived from them and `_skip_if_exists`, the files that belong to a project after its first copy.
- `template/` holds the files of a new repository. Their names carry their conditions, such as `[% if stack == 'php' %]composer.json[% endif %]`, and a name that renders empty is left out with everything inside.
- `.github/workflows/` holds the workflows of the blueprint, which are also those of every repository: a file in `template/.github/workflows/` includes the blueprint's own, and `ci-<stack>.yml` are the checks of each kind of project.
- `blueprint.py`, with its code in `blueprint/`, applies the settings as code, shows the checklist of a repository and runs the bots; every repository gets it as `.github/blueprint.py`.
- `stacks/` holds the dependency manifests and lock files of each kind of project, which Renovate keeps current and the template includes.
- `pins.py` and `.github/pins.toml` keep the sha256 of each tool that the workflows and `.github/sign-tag.sh` download, such as gitsign: Renovate moves the version below its line `# renovate:` and then runs `python3 pins.py`, which writes the checksum. Add a new download to `.github/pins.toml` by hand; `tests/test_pins.py` fails while a version and its sha256 disagree, and the fix bot then runs `python3 pins.py` too, by the autofix of the step of the tests in `.github/checks.project.toml`, and commits what it writes outside `.github/workflows/`.
- `tests/test_template.py` renders all seven kinds of projects and checks them; the other files in `tests/` test `blueprint/` and the scripts.
- `docs/` holds the pages of the website, `docs/decisions/` the records of the decisions, and `docs/images/` the pictures.

## The template

- The template uses delimiters of its own, so that the `${{ }}` of GitHub Actions and the `[[ ]]` of Bash stay as they are: `[% … %]` for blocks, `{= … =}` for values and `[# … #]` for comments.
- `[% include "path" %]` takes a file of the blueprint from the root of this repository, so that the blueprint and every repository share one copy. The files that the blueprint keeps equal to its own rendering are listed in `test_the_blueprint_follows_its_own_template`; change both, or the test fails.
- The seven kinds of projects are the `project_type` of `copier.yml`; most files ask for the derived `stack` instead, which groups them. A change shows in every kind that it touches, and the Variants workflow runs the checks of each kind with its real tools, for a new repository and for one that the update brings from the latest release, and updates one with the answers of each repository that takes the blueprint, from `tests/answers/`. The Downstream workflow updates those repositories themselves before the release (`downstream.py`); a new question of `copier.yml` gets its answer in each file of `tests/answers/`, as the repository will have it.

## Documentation

- `README.md` and `README.de.md` say the same, in English and in German; the home page of the website, `docs/index.md` and `docs/index.de.md`, takes parts of the README.
- Diagrams are pictures of their Mermaid sources ([decision 0016](../docs/decisions/0016-diagrams-as-pictures-of-their-sources.md)): a source is `docs/diagrams/<name>.mmd`, which `bash scripts/diagrams.sh` draws as `docs/images/diagrams/<name>.svg` and `<name>.dark.svg` for a `<picture>` in the Markdown, which the website shows as well ([decision 0058](../docs/decisions/0058-every-website-shows-the-pictures-of-its-diagrams.md)); never a `mermaid` block. They run from top to bottom (`flowchart TB`), with `accTitle` and `accDescr`, which the `alt` of the picture repeats, in the tints of CONTRIBUTING.md: blue (`#526cfe`) the blueprint and its bots, orange (`#f59e0b`) you and what is yours, green (`#16a34a`) what comes out. A diagram in a README comes in English and in German, the German one as `<name>.de.mmd`.
- `docs/reference/` comes from `reference.py`: after a change of `copier.yml`, of a `vars.*` or `secrets.*` of a workflow or of `template/.github/repository.toml.jinja`, run `python3 reference.py` and commit the pages; a new variable or secret needs its description in `ABOUT` of `reference.py`. `tests/test_reference.py` fails otherwise.
- The recording and the screenshot of the README come from `bash scripts/docs-pictures.sh`, with Docker; run it again after a change of what they show.
