#!/usr/bin/env bash
# Create the annotated tag $1 at the commit $2, by default the commit of this run, and
# push it, signed without a key by gitsign: Sigstore certifies the identity of the
# running workflow, and verify-release.yml checks that it is the release workflow of
# this repository. Sigstore and GitHub fail for a moment now and then, so signing and
# pushing try three times each.
#   bash .github/sign-tag.sh v1.2.3 [commit]
# With verify, it checks instead that the tag on GitHub is one that the release
# workflow signed, at the given commit, and fails for any other tag.
#   bash .github/sign-tag.sh verify v1.2.3 commit
# For the release bot only; it needs the permission id-token: write to sign and, in
# GH_TOKEN, a token that may push tags, or read them to verify.
# https://github.com/Dennis-Otto/repo-blueprint
set -euo pipefail

version=0.17.1
sha256=69213a8a0813a151e5a47d0060862952ff833a845d57309dff76f7ba6600abae
remote="https://github.com/$GITHUB_REPOSITORY.git"
issuer=https://token.actions.githubusercontent.com

# gh hands the token to git, so that it appears in no URL and no file.
github() {
  git -c credential.helper= -c credential.helper='!gh auth git-credential' "$@"
}

gitsign="$RUNNER_TEMP/gitsign"
curl --fail --location --silent --show-error --retry 5 --retry-all-errors --connect-timeout 15 \
  --output "$gitsign" \
  "https://github.com/sigstore/gitsign/releases/download/v$version/gitsign_${version}_linux_amd64"
echo "$sha256  $gitsign" | sha256sum --check --strict
chmod +x "$gitsign"

if [[ "$1" == verify ]]; then
  tag="$2"
  commit="$3"
  repository="$(mktemp -d)"
  git init --quiet "$repository"
  github -C "$repository" fetch --quiet --depth=1 "$remote" "refs/tags/$tag:refs/tags/$tag"
  if [[ "$(git -C "$repository" cat-file -t "refs/tags/$tag")" != tag ]]; then
    echo "::error::The tag $tag is not a signed tag; only the release workflow may create the tags of releases."
    exit 1
  fi
  target="$(git -C "$repository" rev-parse "refs/tags/$tag^{commit}")"
  if [[ "$target" != "$commit" ]]; then
    echo "::error::The tag $tag points at $target, not at the commit of the release, $commit."
    exit 1
  fi
  if ! (cd "$repository" && "$gitsign" verify-tag "$tag" \
    --certificate-identity "https://github.com/$GITHUB_REPOSITORY/.github/workflows/release.yml@refs/heads/main" \
    --certificate-oidc-issuer "$issuer"); then
    echo "::error::The signature of the tag $tag isn't one of the release workflow."
    exit 1
  fi
  echo "The tag $tag is signed by the release workflow, at $commit."
  exit 0
fi

tag="$1"
commit="${2:-$GITHUB_SHA}"
# The commit of an earlier merge isn't in the shallow checkout of a later run.
if ! git cat-file -e "$commit^{commit}" 2>/dev/null; then
  github fetch --quiet --depth=1 "$remote" "$commit"
fi
git config user.name "The release bot of $GITHUB_REPOSITORY"
git config user.email "noreply@github.com"
git config gpg.format x509
git config gpg.x509.program "$gitsign"
for attempt in 1 2 3; do
  if git tag --sign --message "$tag" "$tag" "$commit" &&
    "$gitsign" verify-tag "$tag" \
      --certificate-identity "https://github.com/$GITHUB_WORKFLOW_REF" \
      --certificate-oidc-issuer "$issuer"; then
    break
  fi
  git tag --delete "$tag" >/dev/null 2>&1 || true
  if ((attempt == 3)); then
    echo "::error::The tag $tag could not be signed."
    exit 1
  fi
  sleep $((attempt * 10))
done

# A push can fail after GitHub took the tag, as with "fatal error in commit_refs", so
# what counts is the tag on GitHub; every attempt pushes the same signed tag.
signed="$(git rev-parse "refs/tags/$tag")"
for attempt in 1 2 3; do
  if github push "$remote" "refs/tags/$tag"; then
    exit 0
  fi
  pushed="$(github ls-remote --refs "$remote" "refs/tags/$tag" | cut -f 1)" || pushed=""
  if [[ "$pushed" == "$signed" ]]; then
    echo "GitHub has the tag $tag, although the push failed."
    exit 0
  fi
  if [[ -n "$pushed" ]]; then
    echo "::error::The tag $tag exists on GitHub already, as $pushed, which this run didn't sign."
    exit 1
  fi
  if ((attempt == 3)); then
    echo "::error::The tag $tag could not be pushed."
    exit 1
  fi
  sleep $((attempt * 10))
done
