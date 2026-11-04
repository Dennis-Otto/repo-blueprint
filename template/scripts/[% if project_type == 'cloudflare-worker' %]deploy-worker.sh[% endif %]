#!/usr/bin/env bash
# The deploy command of Workers Builds, which builds the Worker on Cloudflare after
# every push to main, as docs/releases.md sets it up:
#
#   npm run deploy
#
# A release deploys: the merge of the release pull request, the commit of main that
# release-please names "chore: release X.Y.Z" and tags vX.Y.Z, goes live with the
# version X.Y.Z of package.json. A prerelease (X.Y.Z-beta.1) uploads a version
# without traffic, tagged vX.Y.Z-beta.1, to try it first. Every other commit uploads a version of the Worker
# that gets no traffic, which the dashboard of Cloudflare lists with its commit; the
# next release deploys what main has then. Whatever this script can't tell, it uploads
# and doesn't deploy. Outside Workers Builds, it refuses: only Cloudflare deploys, from
# main, without a key of Cloudflare anywhere else.
#
# The blueprint keeps this file current: https://github.com/Dennis-Otto/repo-blueprint
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [[ "${WORKERS_CI:-}" != 1 ]]; then
  echo "npm run deploy is the deploy command of Workers Builds and runs only there, as docs/releases.md describes; npx wrangler deploy deploys by hand." >&2
  exit 1
fi
# Workers Builds installs the dependencies itself before the build command, with
# their install scripts, unless SKIP_DEPENDENCY_INSTALL is set; the build command
# npm ci --ignore-scripts installs them without. docs/releases.md sets it once.
case "${SKIP_DEPENDENCY_INSTALL:-}" in
  1 | true) ;;
  *) echo "::warning::Set the build variable SKIP_DEPENDENCY_INSTALL to 1 (Settings, Builds, Variables and secrets): otherwise Cloudflare's own install runs the install scripts of every package, in the build that can deploy, as docs/releases.md describes." >&2 ;;
esac
branch="${WORKERS_CI_BRANCH:-}"
commit="${WORKERS_CI_COMMIT_SHA:-}"
subject="$(git log -1 --format=%s 2>/dev/null || true)"
version="$(node -p 'require("./package.json").version')"
release='^chore(\([^)]*\))?: release v?([0-9]+[.][0-9]+[.][0-9]+[^ ]*)( [(]#[0-9]+[)])?$'
released=""
if [[ "$subject" =~ $release ]]; then
  released="${BASH_REMATCH[2]}"
fi

if [[ "$branch" == main && -n "$released" && "$released" == "$version" && "$released" != *-* ]]; then
  echo "The commit ${commit:-of main} is the release $version: it goes live."
  exec npx --no -- wrangler deploy --tag "v$version" --message "Release $version"
fi
if [[ -z "$branch" ]]; then
  why="Workers Builds named no branch"
elif [[ "$branch" != main ]]; then
  why="it is on the branch $branch, not on main"
elif [[ -z "$subject" ]]; then
  why="Workers Builds checked out no history that names its commit"
elif [[ -n "$released" && "$released" != "$version" ]]; then
  why="it names the release $released, but package.json has the version $version"
elif [[ -n "$released" ]]; then
  echo "The commit ${commit:-of main} is the prerelease $version: it becomes a version without traffic, to try it or roll it out gradually in the dashboard of Cloudflare."
  exec npx --no -- wrangler versions upload --tag "v$version" --message "Prerelease $version"
else
  why="it is no release"
fi
echo "The commit ${commit:-of the build} becomes a version without traffic, because $why; the next release deploys main."
# The version carries the subject of its commit, cut to 100 characters, and the
# commit itself as its tag, by which the dashboard of Cloudflare names it.
message="${subject:-A build of Workers Builds}"
options=(--message "${message:0:100}")
if [[ -n "$commit" ]]; then
  options+=(--tag "${commit:0:12}")
fi
exec npx --no -- wrangler versions upload "${options[@]}"
