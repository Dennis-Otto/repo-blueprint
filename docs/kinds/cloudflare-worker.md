---
description: "A template for a Cloudflare Worker in TypeScript: tests that run in workerd, the runtime of Cloudflare, with every line covered, and every release deployed by Cloudflare's Workers Builds, without a key of Cloudflare in GitHub."
---

# Cloudflare Worker template with tests in workerd and deploys without a key in GitHub

A Cloudflare Worker in TypeScript on Node 24, whose tests run in workerd, the runtime of Cloudflare Workers, and which Cloudflare deploys from each release by itself, with no key of Cloudflare stored in GitHub.

## Start one

```sh
uvx --from copier==9.19.1 copier copy --data project_type=cloudflare-worker gh:Dennis-Otto/repo-blueprint my-worker
cd my-worker
python3 .github/blueprint.py create
```

With [uv](https://docs.astral.sh/uv/) and the GitHub CLI, as [the quick start](../guide.md#start-a-repository) shows. Copier asks for the name, the owner and the other answers, and `create` makes the repository on GitHub, applies the settings as code and prints the checklist.

## What you get

- **The example:** a Worker in `src/index.ts`, which answers `GET /?name=Ada` with a greeting in JSON and refuses every other path and method, the code that it calls in `src/greet.ts`, and its tests in `test/`. `wrangler.jsonc` holds the name of the Worker, its main module, its compatibility date and its bindings. Replace it with the real Worker; its tests show how.
- **Tests in the runtime of Cloudflare:** Vitest runs them in workerd with the bindings of `wrangler.jsonc`, through the [Vitest integration of Cloudflare](https://developers.cloudflare.com/workers/testing/vitest-integration/), and each request reaches the Worker as one from the internet would. `npm run dev` runs it on your machine.
- **The steps of `scripts/check.sh` for this kind,** the same on your machine and in the CI: the lock file, Biome, tsc on the types that Wrangler writes from `wrangler.jsonc`, the tests with every line, branch and function covered, and then *Worker*, which bundles the Worker with Wrangler as Cloudflare does, without an upload or a sign-in.
- **Workflows of this kind:** the newest Node on `main` (`newest-node.yml`); Cloudflare builds and deploys the Worker itself, so no workflow holds a key of Cloudflare.
- **The steps of every kind:** the text files, the diagrams, the pages in one column, the files of the project, the fragments of the changelog, the accepted advisories, the lock files, the version, the Git hooks, ShellCheck for the shell scripts and the strict build of the website.
- **Everything that every repository gets:** the PR coach and the fix bot, the release bot, Renovate, the settings as code, the issue assistant, the website in English and German, the security checks and the blueprint bot, as [the guide](../guide.md#what-a-new-repository-gets) lists them.

## The checks that a pull request needs

The ruleset *Protect main* of `.github/repository.toml` lets a pull request merge once these checks pass:

- `check (node)`: `scripts/check.sh` with the tools of Node, the tests in workerd and the bundle of the Worker.
- `lint`, `diagrams`, `docs`, `conventional title`, `codeql`, `dependency-review` and `gitleaks`, which every kind needs: every linter in one job, the pictures of the diagrams, the strict build of the website, the title of the pull request with its entry in the changelog, CodeQL, the review of new dependencies and the secret scan.

## Delivery

[Workers Builds](https://developers.cloudflare.com/workers/ci-cd/builds/), the integration of Cloudflare with GitHub, builds every commit of `main` on Cloudflare and runs `npm run deploy`. Its script, `scripts/deploy-worker.sh`, deploys only the merge of the release pull request, `chore: release X.Y.Z`, as the version `vX.Y.Z`; every other commit becomes a version without traffic, which the dashboard lists. The release workflow tags the same commit and publishes the release with its SBOMs and the signed provenance of its isolated build, so the Worker that runs is the code of the latest release.

No key of Cloudflare is stored in GitHub: an API token of Cloudflare can't be limited to one Worker, and Workers Builds needs none. The secrets of the Worker live in Cloudflare, set with `npx wrangler secret put`. [Decision 0114](../decisions/0114-cloudflare-deploys-a-worker-from-its-release-with-workers-builds.md) records why.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/how-a-cloudflare-worker-goes-live.dark.svg">
  <img src="../images/diagrams/how-a-cloudflare-worker-goes-live.svg" alt="How a Cloudflare Worker goes live: You merge a pull request into main, after every required check passed. Workers Builds of Cloudflare builds the commit with the lock file of the repository and runs npm run deploy, whose script asks whether the commit is a release. An ordinary commit becomes a version of the Worker without traffic, which the dashboard lists. The merge of the release pull request goes live with its version; the release workflow tags the same commit and publishes the release on GitHub, with its SBOMs and signed provenance. No key of Cloudflare is stored in GitHub.">
</picture>

## Once by hand

`python3 .github/blueprint.py checklist` ticks off each step that it can see and names the rest, each with its link: the release app of the owner with its private key, as [your own account](../own-account.md) shows, the token of the issue assistant unless its AI is off, OpenSSF Best Practices, the REUSE API and the social preview.

This kind adds no step of its own. Its steps happen in Cloudflare, which GitHub can't see:

- Create the Worker with its first deployment from your machine, `npx wrangler login` and `npx wrangler deploy`, which keeps the sign-in there.
- Connect the repository in the dashboard of Cloudflare, under *Settings* and *Builds* of the Worker, with the app of Cloudflare installed for this repository only, the build command `npm ci --ignore-scripts` and the deploy command `npm run deploy`.
- Put each secret of the Worker into Cloudflare with `npx wrangler secret put NAME`.

`docs/releases.md` of the new repository describes each step, how to roll a release back, and what to do when a build fails.

## A real repository

<!-- --8<-- [start:real-repository] -->

No public repository of this kind follows the blueprint yet. The Variants workflow of the blueprint makes one from every change of its files and runs its checks with their real tools, and updates one from the latest release as its blueprint bot would.

<!-- --8<-- [end:real-repository] -->

How the blueprint compares with other templates: [the comparison](../compare.md).
