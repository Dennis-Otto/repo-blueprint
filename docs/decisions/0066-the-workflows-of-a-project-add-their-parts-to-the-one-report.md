# The workflows of a project add their parts to the one report

- Status: accepted
- Date: 2026-10-25

## Context

The PR coach keeps one comment on a pull request ([decision 0030](0030-one-report-on-each-pull-request.md)): the checks that failed, the release, the coverage and the website. The workflows of a project had no way into it, so each one that had something to say about a pull request kept a comment of its own: the visual tests of ha-autodarts and of paperless-unified-search, the size of the card module of ha-autodarts, and the screenshots of the changed pages of a website. A pull request had more than one comment of a bot again, each with its own notifications, and each workflow wrote the code of its comment anew, with its own rules for text that the pull request controls.

Such a workflow runs the code of the pull request, also of one from a fork, so what it hands over is as trusted as the pull request itself.

## Options

1. Each workflow writes a section into the comment of the coach. The coach writes the whole comment anew after every workflow, and GitHub can't write a comment only if nobody changed it since, so a section could get lost between two writers; and every workflow would need a token that writes pull requests.
2. Each workflow keeps its part as an artifact, and the coach collects the artifacts of the head in every run, by any name with a prefix. The API lists the artifacts of a run or of the repository, not those of a commit: the coach would ask once for each run of the head, about fifteen requests in each of its runs, or read the newest artifacts of the repository and miss the part of a busy day.
3. As 2, but the catalog of the default branch names each part: `[report.<name>]` in `.github/checks.project.toml`, with its title. The coach asks for the artifact `pr-report-<name>` by its name, one request for each part, as it does for the website.

## Decision

Option 3.

- **The contract:** a workflow keeps the artifact `pr-report-<name>` for the head of the pull request with the file `report.md`, Markdown in UTF-8. `<name>` has lowercase letters, digits and hyphens, at most 40. The newest artifact of that name for the head counts, so a run again takes the place of the one before. `[report.<name>]` in `.github/checks.project.toml`, or in `.github/checks.toml` for a workflow of the blueprint, gives the part its `title`, an optional `about`, a text in Markdown that the coach shows as it is, and an optional `replaces`, the marker of the old comment of the token of the workflows, such as `<!-- visual-check -->`, which the coach deletes once the part shows. The coach shows at most four parts, in the order of the catalog, after its own.
- **Data, never code:** the coach runs nothing of the artifact. It downloads one of at most 256 kB with `gh run download` into a folder of its own and reads the first 64 kB of `report.md`, never a link. The text shows only as code: a paragraph, an item of a list or a heading as inline code, a table with code in each cell and every pipe escaped, a block of code in a fence that none of its lines can close, without control characters, at most 8,000 characters of a part, 20 rows and 6 columns of a table and 30 lines of a block of code. Links, images, HTML and mentions of the text show as they are written, and the only links of a part lead to its artifact on GitHub, built from the numbers of the API.
- **News:** a part is news, so that a pull request of a person whose checks pass gets the comment, unless the first line of its `report.md` is `<!-- quiet -->`, such as a size that stays as it was. A `report.md` that says nothing gives no part. An artifact too large to read is news and says so, one that the coach couldn't read is no news and waits for the next run.
- **When:** the coach runs after the workflows that start it, those of the blueprint and those that the answer `test_workflows` names. A workflow of the project that keeps a part belongs into `test_workflows`; otherwise its part shows with the next run of the coach for the same commit.
- **The size of the comment:** the parts fill the comment first, in their order, as many as fit, and a note counts those that don't; the checks that failed take the room that is left, as before.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/the-report-of-a-pull-request.dark.svg">
  <img src="../images/diagrams/the-report-of-a-pull-request.svg" alt="The report of a pull request: A push to a pull request of a person runs the checks, which keep the coverage of the tests and the website that they built as artifacts, and the workflows of the project, which keep their parts as artifacts pr-report-name. After the checks, the PR coach reads the check runs, the title and description, the files, the coverage reports of the pull request and of main, the artifact website and the parts from the API, with the release-please files, mkdocs.yml and the parts that .github/checks.project.toml declares of main, and runs no code of the pull request. It keeps one comment: the checks that failed, the next version with the entry of the changelog, the coverage file by file, the website with the pages that change, and the parts of the workflows as code. A pull request whose checks pass gets it only when it has something of this to say.">
</picture>

## Consequences

A workflow of a project says what it found in the comment of the coach, with the rules of the coach for untrusted text, and needs no token that writes pull requests for it. Its old comment goes away with `replaces`. A rich report, such as pictures of visual tests, shows as a table or a list in the part, with the link to the artifact that holds the pictures; the coach shows no picture, as it would load it from wherever the pull request says.

The coach asks GitHub once more for each declared part in each of its runs, and three times more for each part whose artifact the head has, as `gh run download` lists the artifacts of the run and downloads the one. A repository declares only the parts of its workflows, so a pull request of a repository without parts costs nothing more. A pull request of a bot gets no parts, as before.

The catalog of an existing repository belongs to the project, so the update brings no `[report.<name>]`: each repository adds the parts of its own workflows, and the starter of `.github/checks.project.toml` shows how.
