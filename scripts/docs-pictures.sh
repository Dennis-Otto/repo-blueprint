#!/usr/bin/env bash
# Renders the pictures of the documentation into docs/images/: copier-copy.gif, a copy
# of the blueprint in the terminal as .github/docs-pictures/copier-copy.tape plays it,
# and dashboard.png, the dashboard of the repositories as the website publishes it.
# Run it again after the questions, the output of Copier or the dashboard change.
#
# It needs Docker and the network: VHS records the terminal while Copier clones the
# blueprint from GitHub, and the headless Chromium of the social preview's image
# loads the dashboard.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

# Git Bash on Windows: keep the container's paths and mount the Windows path.
export MSYS_NO_PATHCONV=1
root="$(pwd -W 2>/dev/null || pwd)"
gif="$(mktemp)"
png="$(mktemp)"
log="$(mktemp)"
trap 'rm -f "$gif" "$png" "$log"' EXIT

# VHS, git and Copier: the image comes from a Dockerfile, so that Renovate keeps it
# current. Its build context is the repository, for the requirements of Copier.
if ! terminal="$(docker build --quiet --tag repo-blueprint-docs-pictures \
  --file .github/docs-pictures/Dockerfile . 2>"$log")"; then
  cat "$log" >&2
  echo "Building the image of .github/docs-pictures/Dockerfile failed." >&2
  exit 1
fi

# The pictures leave the containers through stdout, so they belong to whoever runs this.
if docker run --rm --volume "$root:/work:ro" --entrypoint sh "$terminal" -c '
  mkdir -p /tmp/out/docs/images && cd /tmp/out &&
    vhs /work/.github/docs-pictures/copier-copy.tape >&2 &&
    cat docs/images/copier-copy.gif' >"$gif" 2>"$log" &&
  [[ -s "$gif" ]]; then
  mkdir -p docs/images
  cp "$gif" docs/images/copier-copy.gif
  echo "Rendered docs/images/copier-copy.gif."
else
  cat "$log" >&2
  echo "Recording .github/docs-pictures/copier-copy.tape failed." >&2
  exit 1
fi

# The dashboard as the website shows it, in the browser of the social preview. Python
# first checks that the page loads: the browser would take a picture of an error too.
dashboard="https://dennis-otto.github.io/repo-blueprint/dashboard/"
browser="$(sed -n 's/^FROM //p' .github/social-preview/Dockerfile)"
if docker run --rm "$browser" sh -c '
  python3 -c "import sys, urllib.request; urllib.request.urlopen(sys.argv[1], timeout=60)" "$1" &&
    /ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell \
    --no-sandbox --hide-scrollbars --force-device-scale-factor=1 --window-size=1480,900 \
    --virtual-time-budget=10000 --screenshot=/tmp/dashboard.png "$1" >&2 &&
    cat /tmp/dashboard.png' sh "$dashboard" >"$png" 2>"$log" &&
  [[ -s "$png" ]]; then
  cp "$png" docs/images/dashboard.png
  echo "Rendered docs/images/dashboard.png."
else
  cat "$log" >&2
  echo "Rendering $dashboard failed." >&2
  exit 1
fi
