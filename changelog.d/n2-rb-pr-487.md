### Bug fixes

- **Biome 2.6 stays out of the Markdown and YAML of a Node package:** since version 2.6 Biome also formats Markdown and YAML, so `biome ci` in the step *Lint and format* of a Node package or Chrome extension failed on files the blueprint renders, such as `AGENTS.md` and `mkdocs.yml`. `biome.jsonc` now leaves these files out, markdownlint still checks the Markdown, and Biome checks the code and the JSON, as before. The new lock takes Biome 2.6.3 and the other updates of this lock file maintenance.
