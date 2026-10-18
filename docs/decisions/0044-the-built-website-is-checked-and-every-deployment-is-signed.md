# The built website is checked, and every deployment is signed and asked for its pages

- Status: accepted
- Date: 2026-10-18

## Context

`mkdocs build --strict` was the only check of every website. It checks the links that Markdown writes, but not those that a page writes in HTML: a probe with `<a href="no-such-page.html">` and `<img src="images/no-such.png">` in a page of `dennis-otto.github.io` built strictly and passed. Neither did anything check the cards, the links of the theme, the 404 page or a page of HTML of the project. The hooks of `.github/mkdocs_blueprint.py` copy the sitemap into every folder of pages, which the language switch of Material reads, keep the 404 page of the default language at the root, and give each page the full addresses of its versions; their tests fake the plugins, and no variant builds a website in two languages, so an update of Material or of the i18n plugin that broke them would have reached the published websites. The deployment ended with `actions/deploy-pages`: no run asked the published website whether it answers, and nothing tied what readers load to the workflow and the commit that built it. The Links workflow checked no anchor at all, so a renamed heading of a README broke the buttons of other repositories that lead to it, such as `issue-assistant#set-up-a-repository`.

## Options

1. lychee over the built website with the network, in every pull request: it checks the links to other sites too, but a site that is down for a moment fails the pull request.
2. A link check of the built website without the network, in the check *docs*, and the links to other sites with their anchors in the weekly Links run.
3. A link checker of our own in Python, within `blueprint.py`.

## Decision

Option 2, with lychee, which the Links workflow already runs, so that one tool and one pin check every link.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/how-the-website-is-checked-and-published.dark.svg">
  <img src="../images/diagrams/how-the-website-is-checked-and-published.svg" alt="How the website is checked and published: The check docs builds the website strictly. Then lychee checks every link and anchor of the built pages without the network, blueprint.py site-check what the hooks of the website promise, scripts/check-site.sh what the project checks, and axe-core the accessibility of every page. A failure names the file and how to fix it. On main, the same build goes to GitHub Pages. The job that publishes it signs its provenance with Sigstore and asks the published website for the home page of each language and for an address that leads nowhere, which must answer 404.">
</picture>

- **The links of the built website:** after the build, `lychee --offline --include-fragments` reads every page of `site/` and checks each link and anchor to a file of the website. It runs in `site/`, away from `lychee.toml` and `.lycheeignore`, which are the rules of the links to other sites, and the path of the address, such as `/repo/` of a project website, from which the 404 page links the files, leads to `site/`.
- **What the hooks promise:** `blueprint.py site-check site`, with the standard library alone, reads what the real plugins and hooks wrote: one canonical address on every page that MkDocs built, the full addresses of the other languages with `x-default`, and, on a website in several languages, a sitemap in every folder of pages, the same as at the root and without a page that search engines leave out, the 404 page of the default language at the root, and every untranslated page in the default language, without versions of its own and with `noindex`. It also names the further languages and the path of the address for the steps that follow.
- **The checks of a project:** `scripts/check-site.sh`, which the blueprint never writes, gets the folder of the website, such as for the `robots.txt` of `dennis-otto.github.io`.
- **Each check after the build runs** when the build passed, even when the check before it failed, and the website of a pull request is kept for its reviewer in either case.
- **The deployment:** the job that publishes signs the build provenance of `artifact.tar` of the artifact `github-pages` with Sigstore, not the job of the check, which runs the code of pull requests and gets no `id-token`. It then asks the published website for the home page of each language, which must answer with a page, and for an address that leads nowhere, which must answer with 404.
- **Anchors in the Links workflow:** lychee checks the anchor of each link, also in the README of another repository, and the weekly run reads the pages of HTML in `docs/` too. `#readme` of a repository, which GitHub draws with a script, leads to the repository; the anchors of the Markdown files of the repository, which `--8<--` may put together from others, and the links to pages of HTML that only the build writes, stay with the check *docs*, whose strict build and link check see the built pages. Run over the six repositories that take the blueprint, these rules found no false error.

## Consequences

A broken link or anchor in a built page fails the pull request that brings it, in about a second more on the blueprint's website of 4,750 links, and so does an update of Material or of its plugins that breaks a promise of the hooks. Every deployment has a provenance that `gh attestation verify` checks as `SECURITY.md` shows, as long as GitHub keeps the artifact, a day; a deployment that GitHub Pages doesn't serve fails its run, which the bot-health bot reports. The check *docs* depends on lychee and its pin as the Links workflow does, and `blueprint.py site-check` on what the plugins write into the head of a page: a plugin that writes it differently fails the check of its update, and the hook or the check follows it.
