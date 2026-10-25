#!/usr/bin/env bash
# Downloads Chrome for Testing of a channel, Stable unless the first argument names
# another one (Stable, Beta, Dev or Canary), and prints the path of its executable:
#
#   node scripts/load-extension.mjs "$(bash scripts/chrome-for-testing.sh)"
#
# Google Chrome itself no longer loads an unpacked extension from the command line;
# Chrome for Testing, the same browser for automated tests, still does. Beta has the
# version that reaches the users four weeks later. The second argument is the folder
# to keep the downloads in; a version that is there already is used again. It needs
# curl, Node and unzip, which Git Bash, macOS and the runners of GitHub have. The
# versions come from Google's list of the last good builds:
# https://github.com/GoogleChromeLabs/chrome-for-testing
#
# The blueprint keeps this file current: https://github.com/Dennis-Otto/repo-blueprint
set -euo pipefail

channel="${1:-Stable}"
folder="${2:-${TMPDIR:-/tmp}/chrome-for-testing}"
app="Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
case "$(uname -s)-$(uname -m)" in
Linux-x86_64) platform=linux64 executable=chrome-linux64/chrome ;;
Darwin-arm64) platform=mac-arm64 executable="chrome-mac-arm64/$app" ;;
Darwin-x86_64) platform=mac-x64 executable="chrome-mac-x64/$app" ;;
MINGW64*-x86_64 | MSYS*-x86_64 | CYGWIN*-x86_64) platform=win64 executable=chrome-win64/chrome.exe ;;
*)
  echo "Chrome for Testing has no build for $(uname -s) on $(uname -m)." >&2
  exit 1
  ;;
esac

if ! command -v unzip >/dev/null 2>&1; then
  echo "unzip is missing; install it, such as with apt-get install unzip." >&2
  exit 1
fi

versions=https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json
# The version of the channel and the address of its zip file for this platform.
# shellcheck disable=SC2016 # The code is JavaScript for Node, not for the shell.
read_build='
const [channel, platform] = process.argv.slice(1);
let text = "";
process.stdin.on("data", (chunk) => (text += chunk));
process.stdin.on("end", () => {
  const build = JSON.parse(text).channels?.[channel];
  const download = build?.downloads?.chrome?.find((d) => d.platform === platform);
  if (build === undefined || download === undefined) {
    console.error(`Chrome for Testing lists no ${channel} for ${platform}.`);
    process.exit(1);
  }
  console.log(`${build.version} ${download.url}`);
});'
# The list goes to a file first: Node reads it as data, so no download is piped into an
# interpreter (OpenSSF Scorecard, Pinned-Dependencies).
list="$(mktemp)"
trap 'rm -f "$list"' EXIT
curl --fail --location --silent --show-error --retry 5 --retry-all-errors \
  --connect-timeout 15 --max-time 60 --output "$list" "$versions"
build="$(node -e "$read_build" "$channel" "$platform" <"$list")"
version="${build%% *}"
url="${build#* }"

target="$folder/$version"
if [[ ! -x "$target/$executable" ]]; then
  rm -rf "$target"
  mkdir -p "$target"
  echo "Downloading Chrome for Testing $channel $version for $platform." >&2
  curl --fail --location --silent --show-error --retry 5 --retry-all-errors \
    --connect-timeout 15 --max-time 600 --output "$target/chrome.zip" "$url"
  unzip -q "$target/chrome.zip" -d "$target"
  rm "$target/chrome.zip"
fi
echo "$target/$executable"
