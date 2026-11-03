# Cloudflare deploys a Worker from its release with Workers Builds

- Status: accepted
- Date: 2026-11-03

## Context

The blueprint had eight kinds of projects, and none for a service that is always on. A Cloudflare Worker is one: TypeScript that Cloudflare runs on its own network for every request, such as the receiver of webhooks of a bot. Its code fits the stack of Node, but three things differ from the other kinds:

- It runs in workerd, the runtime of Cloudflare, not in Node: a test in Node would test another runtime than the one that serves the requests.
- Nobody installs it from a registry. Cloudflare deploys it, and the deployed Worker is the product.
- Cloudflare offers two ways to deploy from GitHub. A workflow of GitHub Actions runs `wrangler deploy` with an API token of Cloudflare, a long-lived secret: Cloudflare has no sign-in with the OIDC token of GitHub, and an API token with the permission *Workers Scripts: Edit* reaches every Worker of its account, not only one. [Workers Builds](https://developers.cloudflare.com/workers/ci-cd/builds/), the integration of Cloudflare with GitHub, builds each push on Cloudflare instead, with the GitHub app of Cloudflare, and needs no key in GitHub at all. It deploys every push of its production branch, though, with a deploy command of the project.

## Options

1. Leave it to each Worker: a project of the kind `node-package` writes its own configuration, tests and delivery, and its tests run in Node.
2. A kind whose release workflow deploys with an API token of Cloudflare, in an environment that only `main` can use: the deployed code would be that of the signed tag, but a secret that reaches every Worker of the account would live in GitHub.
3. A kind whose Worker Cloudflare builds and deploys with Workers Builds after every push to `main`: no key in GitHub, but every merge would go live, a release would only describe what already runs, and an update of a dependency by Renovate would reach the users before anyone released it.
4. A kind built by Workers Builds, whose deploy command deploys only the commit of a release and uploads every other commit as a version without traffic.

## Decision

Option 4.

- **The kind** `cloudflare-worker` takes the tools of Node: the same `check (node)`, Biome and tsc, on its own lock file in `stacks/worker/`, with Wrangler, Vitest and the [Vitest integration of Cloudflare](https://developers.cloudflare.com/workers/testing/vitest-integration/). `wrangler.jsonc`, with the name, the main module, the compatibility date and the bindings of the Worker, belongs to the project; `vitest.config.ts`, `tsconfig.json` and `scripts/deploy-worker.sh` to the blueprint. Its `package.json` is private.
- **The checks** of `scripts/check.sh` run the tests in workerd, with every line, branch and function covered and `lcov.info` for the PR coach, and tsc on the types that `wrangler types` writes from `wrangler.jsonc` into `worker-configuration.d.ts`, which git ignores, so they never go stale. The step *Worker* bundles the Worker with Wrangler as Cloudflare does, with `wrangler deploy --dry-run`, which needs no sign-in and uploads nothing. Wrangler sends no telemetry from the checks.
- **The deploy** is Workers Builds, with the build command `npm ci --ignore-scripts`, the build variable `SKIP_DEPENDENCY_INSTALL=1`, which stops Cloudflare's own install with the install scripts of every package, and the deploy command `npm run deploy`, which warns when that variable is missing. `scripts/deploy-worker.sh` deploys a commit of `main` only when its subject is that of a release pull request, `chore: release X.Y.Z`, and `package.json` has the version X.Y.Z; it tags the deployment `vX.Y.Z`. A prerelease is uploaded as a version without traffic, tagged `vX.Y.Z-beta.N`, as every other kind keeps a prerelease away from its users. It uploads every other commit with `wrangler versions upload`, as a version without traffic tagged with its commit, and says why. What it can't tell, such as a build without the history of its commit, it uploads as well, so it never deploys by mistake. Outside Workers Builds it refuses. Builds of other branches stay off, since the checks of each pull request run in GitHub.
- **The release** is the release of every kind: release-please, the signed tag and the SBOMs and provenance of the isolated build, which describes the files of the tag. The tag and the deployment name the same commit and the same version.
- **The secrets** of a Worker live in Cloudflare, set with `wrangler secret put`, and those of `wrangler dev` in `.dev.vars`, which git ignores. The docs of the kind and of each project say so.
- **What only a person can do,** the account of Cloudflare, the first deployment that creates the Worker and the connection of the repository, is in `docs/releases.md` of the project.

## Consequences

A Worker of the blueprint has no key of Cloudflare in GitHub, and what serves its requests is the code of its latest release. A merge reaches Cloudflare as a version that the maintainer can try first, and goes live with the next release, as a package of the other kinds reaches its users. Cloudflare builds the release itself, so the provenance of the release describes the tag rather than the bundle that runs; both come from the same commit and the same lock file. A Worker that has to go live with every merge changes its deploy command to `npx wrangler deploy` in the dashboard of Cloudflare. GitHub can't see whether the connection to Cloudflare exists, so the checklist names it as a step it can't tick off, as it does for PyPI and HACS. Should Cloudflare offer a sign-in with the OIDC token of GitHub, or tokens limited to one Worker, a deploy from the release workflow becomes the better way, as for the Chrome Web Store ([decision 0085](0085-a-chrome-extension-reaches-the-store-with-the-zip-that-its-release-attests.md)).
