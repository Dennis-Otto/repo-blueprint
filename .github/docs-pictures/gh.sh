#!/usr/bin/env bash
# The GitHub CLI of the recording, as the Dockerfile next to it installs it. The
# recording runs without secrets, and the dry run of python3 .github/blueprint.py create
# at its end shows its commands only after a preflight that nothing stops. So this
# answers what the preflight asks, as gh does for the owner of the blueprint when signed
# in with the scopes of create and before the repository exists, and nothing else: a
# dry run makes nothing. A test of the blueprint runs the preflight with these answers.
# Each call of the API asks at its end for the version of the API, as
# blueprint/github.py has it.
set -euo pipefail

version="--header X-GitHub-Api-Version: 2022-11-28"
case "$*" in
--version)
  echo "gh version 2.62.0 (2024-11-14)"
  ;;
"api --include user $version")
  printf 'HTTP/2.0 200 OK\nX-Oauth-Scopes: repo, workflow\n\n'
  echo '{"login": "Dennis-Otto", "type": "User"}'
  ;;
"config get git_protocol --host github.com")
  echo https
  ;;
"api users/Dennis-Otto $version")
  echo '{"login": "Dennis-Otto", "type": "User"}'
  ;;
"api repos/Dennis-Otto/paperless-sync $version")
  echo "gh: Not Found (HTTP 404)" >&2
  exit 1
  ;;
*)
  echo "The GitHub CLI of the recording doesn't answer: gh $*" >&2
  exit 1
  ;;
esac
