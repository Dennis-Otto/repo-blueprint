#!/usr/bin/env bash
# Builds the extension and zips it for the Chrome Web Store, which Edge installs from
# as well: the contents of extension/ after `npm run build`, with manifest.json at the
# root of the zip, as the store wants it, without source maps and hidden files.
#
#   bash scripts/package-extension.sh [FOLDER] [VERSION]
#
# writes FOLDER/<name>-<version>.zip, dist/ by default, with the name of package.json,
# and prints its path. The same commit makes the same zip, byte for byte: the files in
# their order, each with the time of the commit. The isolated build of a release,
# build-release.yml, passes the version of the release, which the manifest of a
# release has already, as the release bot writes it there; a beta, such as
# 1.3.0-beta.2, comes from main, whose manifest has the version of the last release:
# its zip gets 1.3.0, as a manifest takes only numbers, and the whole version as
# version_name, which Chrome shows. It needs Node and Python 3.
#
# The blueprint keeps this file current: https://github.com/Dennis-Otto/repo-blueprint
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

out="${1:-dist}"
release="${2:-}"
manifest=extension/manifest.json
if [[ ! -f "$manifest" ]]; then
  echo "$manifest is missing: the blueprint builds the extension from the folder extension/, with its manifest.json at the top." >&2
  exit 1
fi
python="$(command -v python3 || command -v python || command -v py || true)"
if [[ -z "$python" ]]; then
  echo "Python 3 is missing, which writes the zip." >&2
  exit 1
fi

npm run --silent build

# The time of the commit, for every file of the zip; the time of now outside Git.
export SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-$(git log -1 --format=%ct 2>/dev/null || date +%s)}"
"$python" - "$manifest" "$out" "$release" <<'PYTHON'
import json
import re
import sys
import time
import zipfile
from os import environ
from pathlib import Path

manifest_path, out, release = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
folder = manifest_path.parent
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
version = manifest.get("version", "")
package = json.loads(Path("package.json").read_text(encoding="utf-8"))
name = str(package.get("name", "extension")).rsplit("/", 1)[-1]
if release:
    numbers = re.match(r"[0-9]+(?:\.[0-9]+)*", release)
    if numbers is None:
        sys.exit(f"{release} is no version of a release.")
    if release != version and numbers.group() == release:
        sys.exit(
            f"{manifest_path.as_posix()} has the version {version}, the release {release}: the"
            " release bot writes the version of a release into the manifest, as"
            " release-please-config.json says."
        )
    beta = release != version
    if beta:
        manifest = {**manifest, "version": numbers.group(), "version_name": release}
else:
    beta = False
    release = version

# The configuration of tools such as Biome or TypeScript stays out of the store.
TOOL_CONFIG = re.compile(r"biome\.jsonc?|tsconfig.*\.json")
# Zip files can't hold a time before 1980.
stamp = time.gmtime(max(int(environ["SOURCE_DATE_EPOCH"]), 315532800))[:6]
files = sorted(
    path
    for path in folder.rglob("*")
    if path.is_file()
    and path.suffix not in {".map", ".ts"}
    and not TOOL_CONFIG.fullmatch(path.name)
    and not any(part.startswith(".") for part in path.relative_to(folder).parts)
)
out.mkdir(parents=True, exist_ok=True)
target = out / f"{name}-{release}.zip"
with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
    for path in files:
        entry = zipfile.ZipInfo(path.relative_to(folder).as_posix(), stamp)
        entry.compress_type = zipfile.ZIP_DEFLATED
        entry.external_attr = 0o644 << 16
        # Made by Unix on every system, so that Windows makes the same bytes.
        entry.create_system = 3
        data = path.read_bytes()
        if beta and path == manifest_path:
            data = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode()
        archive.writestr(entry, data)
print(target.as_posix())
PYTHON
