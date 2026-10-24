#!/usr/bin/env bash
# Renders the pictures of the documentation into docs/images/: copier-copy.gif, a copy
# of the blueprint in the terminal as .github/docs-pictures/copier-copy.tape plays it,
# with copier-copy.mp4, the same as a video that the website plays in its place, and
# copier-copy.webp, its last screen, which the website shows until the video plays;
# social-preview.webp, the social preview of .github/ at a seventh of its size, for
# the home page of the website; dashboard.png, the dashboard of the repositories as
# the website publishes it; and pictures of public pages of GitHub, each in the light
# and the dark theme: github-update-pull-request.png, an update of the blueprint with
# its checks, github-release.png, the assets of a release with its SBOMs and its
# provenance, and github-pr-coach.png, the comment of the PR coach with the coverage
# of the tests. Run it again after the questions, the output of Copier, the social
# preview, the dashboard or the pages of GitHub change.
#
# It needs Docker and the network: VHS records the terminal while Copier clones the
# blueprint from GitHub, and the headless Chromium of the social preview's image
# loads the dashboard and the pages of GitHub.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

# Git Bash on Windows: keep the container's paths and mount the Windows path.
export MSYS_NO_PATHCONV=1
root="$(pwd -W 2>/dev/null || pwd)"
recording="$(mktemp)"
png="$(mktemp)"
page="$(mktemp)"
github="$(mktemp)"
log="$(mktemp)"
trap 'rm -f "$recording" "$png" "$page" "$github" "$log"' EXIT

# VHS, git and Copier: the image comes from a Dockerfile, so that Renovate keeps it
# current. Its build context is the repository, for the requirements of Copier.
if ! terminal="$(docker build --quiet --tag repo-blueprint-docs-pictures \
  --file .github/docs-pictures/Dockerfile . 2>"$log")"; then
  cat "$log" >&2
  echo "Building the image of .github/docs-pictures/Dockerfile failed." >&2
  exit 1
fi

# The pictures leave the containers through stdout, so they belong to whoever runs this.
# ffmpeg makes the video from the GIF while its colors are still exact: H.264 at a
# third of the size, with its index first, so that it starts while it loads; and the
# pictures of the last screen and of the social preview WebPs of a fifth of the size
# of their PNGs or less. Then gifsicle makes the GIF for GitHub less than half as
# large, in 64 colors, which a terminal of 16 colors needs for the edges of its
# letters.
if docker run --rm --volume "$root:/work:ro" --entrypoint sh "$terminal" -c '
  mkdir -p /tmp/out/docs/images && cd /tmp/out &&
    vhs /work/.github/docs-pictures/copier-copy.tape >&2 && cd docs/images &&
    ffmpeg -loglevel error -i copier-copy.gif -c:v libx264 -preset veryslow -crf 28 \
      -pix_fmt yuv420p -movflags +faststart -an copier-copy.mp4 >&2 &&
    ffmpeg -loglevel error -i copier-copy.png -c:v libwebp -quality 80 copier-copy.webp >&2 &&
    ffmpeg -loglevel error -i /work/.github/social-preview.png -c:v libwebp -quality 85 \
      social-preview.webp >&2 &&
    gifsicle --batch --optimize=3 --lossy=100 --colors=64 copier-copy.gif >&2 &&
    tar -cf - copier-copy.gif copier-copy.mp4 copier-copy.webp social-preview.webp' >"$recording" 2>"$log" &&
  [[ -s "$recording" ]]; then
  mkdir -p docs/images
  tar -xf "$recording" -C docs/images
  echo "Rendered docs/images/copier-copy.gif, .mp4 and .webp, and docs/images/social-preview.webp."
else
  cat "$log" >&2
  echo "Recording .github/docs-pictures/copier-copy.tape failed." >&2
  exit 1
fi

# The dashboard as the website shows it, in the browser of the social preview. curl
# fetches the page first, so a page that does not load fails here instead of becoming a
# picture of an error. The page caps its width below that of its main table, which then
# scrolls: the copy that the browser draws lifts the cap, so every column is in the
# picture. The page has no scripts, and its base address keeps its links and pictures.
dashboard="https://dennis-otto.github.io/repo-blueprint/dashboard/"
browser="$(sed -n 's/^FROM //p' .github/social-preview/Dockerfile)"
# The curl of Git for Windows is a Windows program: it takes the Windows path of the file.
saved="$(cygpath --mixed "$page" 2>/dev/null || echo "$page")"
if curl --fail --location --silent --show-error --retry 3 --retry-all-errors \
  --connect-timeout 10 --max-time 60 --output "$saved" "$dashboard" 2>"$log" &&
  grep --quiet '</head>' "$page" &&
  sed "0,/<\/head>/s||<base href=\"$dashboard\"><style>main { max-width: none; }</style></head>|" "$page" |
  docker run --rm --interactive "$browser" sh -c 'cat >/tmp/dashboard.html &&
    /ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell \
    --no-sandbox --hide-scrollbars --force-device-scale-factor=1 --window-size=1760,900 \
    --virtual-time-budget=10000 --screenshot=/tmp/dashboard.png file:///tmp/dashboard.html >&2 &&
    cat /tmp/dashboard.png' >"$png" 2>>"$log" &&
  [[ -s "$png" ]]; then
  cp "$png" docs/images/dashboard.png
  echo "Rendered docs/images/dashboard.png."
else
  cat "$log" >&2
  echo "Rendering $dashboard failed." >&2
  exit 1
fi

# The pages of GitHub, as .github/docs-pictures/github_pages.py photographs them with
# the Playwright of stacks/screenshots/requirements-browser.txt, which drives the
# browser of the same image. The pictures leave the container as a tar on stdout.
if docker run --rm --volume "$root:/work:ro" "$browser" sh -c '
  pip install --quiet --disable-pip-version-check --root-user-action=ignore     --break-system-packages --require-hashes     -r /work/stacks/screenshots/requirements-browser.txt >&2 &&
    python3 /work/.github/docs-pictures/github_pages.py /tmp/github >&2 &&
    tar -cf - -C /tmp/github .' >"$github" 2>"$log" &&
  [[ -s "$github" ]]; then
  tar -xf "$github" -C docs/images
  echo "Rendered the pictures of the pages of GitHub in docs/images."
else
  cat "$log" >&2
  echo "Photographing the pages of GitHub failed." >&2
  exit 1
fi
