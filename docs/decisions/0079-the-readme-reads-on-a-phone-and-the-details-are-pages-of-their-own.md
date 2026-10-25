# The README reads on a phone, and the details are pages of their own

- Status: accepted
- Date: 2026-10-25

## Context

The README of the blueprint had grown to 17,500 words, the German one to 16,500: about 70 minutes of reading. Its main section, *What a new repository gets*, was a table of three columns whose cells were paragraphs of up to 2,600 characters. The GitHub app and a phone squeeze such a table into narrow strips or scroll it sideways, and a screen reader reads it cell by cell. The website showed the whole README as its guide, one page of 17,000 words whose search hits and table of contents all led to the same place.

The check *Pages in one column*, as `CONTRIBUTING.md` describes it, found HTML tables that set a picture beside text, but no Markdown table with paragraphs in its cells, here or in any repository made from the blueprint.

## Options

1. Keep the README as the full guide, and fold its long sections into `<details>`. It stays one long page, and the table stays a table.
2. A short README, with one line for each area of what a new repository gets and a link to a page of `docs/features/` with the details, and the set-up as the guide of the website.
3. Option 2, and a check that fails on a cell of a Markdown table of more than 30 words in every repository.
4. Option 2, and the same check as a warning, until every repository is clean.

## Decision

Option 4.

- **The README** keeps the pitch, the quick start, the kinds of projects, the loop and a list of the areas, each with one sentence, grouped by the page of `docs/features/` that has its details, in English and German. A test keeps each README below 3,000 words and free of cells of more than 30 words.
- **The pages of `docs/features/`** have the details, each area as a section with what runs and how, and the website shows them as a section of its own. The guide of the website keeps the start, the kinds, a list of these pages and the set-up, so that every anchor that a page links to stays.
- **The check *Pages in one column*** warns of every cell of a Markdown table with more than 30 words, at the line of its row, in a README, a CONTRIBUTING file or a page of `docs/`. A warning fails nothing: the repositories made from the blueprint hold hundreds of such cells today, and only a person can make a list or a page of one, so an error would stop every update of the blueprint at once.

## Consequences

The README reads in about twelve minutes, also in the GitHub app, and the website has a page for each area that its search finds. A new detail goes to its page, and the README gets one line at most. The warnings show where each repository still has paragraphs in tables; once they are gone, the check can fail on them.
