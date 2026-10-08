Repo Blueprint is a Copier template for GitHub repositories: a new repository gets its checks, release bot, security checks, issue assistant and settings as code from it, and the blueprint bot keeps every repository made from it current. It serves seven kinds of projects: Home Assistant integrations, Nextcloud apps, GitHub Actions, Python packages, Node packages, container images and repositories without a build.

Where things are:

- `copier.yml` holds the questions; `template/` holds the files of a new repository, whose names carry their conditions, such as `[% if stack == 'php' %]composer.json[% endif %]`.
- `.github/workflows/` holds the workflows of this repository, which are also the templates of the workflows of new repositories; `ci-<stack>.yml` are the checks of each kind of project.
- `stacks/` holds the dependency manifests and lock files of each kind of project, which Renovate keeps current.
- `blueprint.py` applies and checks the settings of `.github/repository.toml` and shows the checklist of a repository, with its code in `blueprint/`, a module for each task; `tests/` holds its tests and those of the template.
- `README.md` is the documentation; `CHANGELOG.md` lists the changes of every release, `docs/roadmap.md` the plans and `docs/security.md` the security design of the blueprint.

What matters in a bug report: the release of the blueprint (the `_commit` of `.copier-answers.yml`), the kind of project, the version of Copier, the command and its output, and the file of the generated repository that is wrong. No tokens or private URLs.

Reporters may write in German; answer them in German.
