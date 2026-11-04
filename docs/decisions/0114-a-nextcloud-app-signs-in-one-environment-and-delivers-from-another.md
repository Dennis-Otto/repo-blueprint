# A Nextcloud app signs in one environment and delivers from another

- Status: accepted
- Date: 2026-11-03

## Context

[Decision 0091](0091-the-build-of-a-release-holds-no-secret-and-its-provenance-must-come-from-main-on-github.md) took every secret away from the build of a release, but that of a Nextcloud app: its build entered the whole environment `release` for the key that signs the app, and the release workflow called it with `secrets: inherit`. So the actions that the build runs, such as setup-php and the one that writes the SBOMs, could reach the private key of the release app and the token of the App Store as well. The settings declare the environments `signing`, with `APP_PRIVATE_KEY` alone, and `appstore`, with `APPSTORE_TOKEN` alone, and the maintainer set both secrets in paperless-sync and paperless-unified-search ([#530](https://github.com/Dennis-Otto/repo-blueprint/issues/530), steps 1 and 2).

Two things stood in the way of a plain switch:

- **A called workflow sees no secret that its caller doesn't pass,** not even one of the environment that its own job enters. The caller, the job `assets` of `release.yml`, enters no environment, so the value that it passes is empty. GitHub's documentation says that the secret of the called job's environment takes the place of a passed one; no run of the blueprint had shown that yet.
- **A job enters one environment,** and the one job of `register-app.yml` read the key and the token in one step.

## Options

1. Keep `secrets: inherit` and only move the build to `signing`: the build would get every secret of the repository and of no environment, a finding of zizmor that only an exception at that line silenced.
2. Pass `APP_PRIVATE_KEY` alone, declared by the build as an optional secret, and let the environment `signing` of the build supply its value; register the app in two jobs, one in each environment.
3. As 2, but keep the key in `appstore` as well, so that `register-app.yml` stays one job.

## Decision

Option 2.

- **The build enters `signing`** and gets `APP_PRIVATE_KEY` alone, `secrets: APP_PRIVATE_KEY: ${{ secrets.APP_PRIVATE_KEY }}`, which `build-release.yml` declares with `required: false`. The inline exception of zizmor goes with `secrets: inherit`.
- **A wrong guess fails loudly.** Should GitHub hand the build no key, the step *Sign the Nextcloud app* stops the release with an error that names the environment and the passed secret, before anything is signed or attached, and the signature is checked against the certificate of the app as before, so no release is ever signed by nothing or by another key. The first beta release of a Nextcloud app is the proof; until step 4 of #530, `release` keeps copies of both secrets, so reverting the switch brings the releases back.
- **The delivery to the App Store enters `appstore`.** The job runs only for `PUBLISH_TO` `nextcloud-appstore`, as those of PyPI and npm run only for theirs.
- **Register the app in two jobs.** The job *sign the app id* in `signing` checks the key against the certificate that Nextcloud issued and signs the app id; it hands the app id, the certificate in Base64 and the signature, none of them secret, to the job *register the app* in `appstore`, which posts them with the token. That job checks nothing out and reaches only `apps.nextcloud.com`, and it fails when an output arrives empty, as GitHub drops an output that it takes for a secret.

Option 3 would bring the key back into the reach of every delivery to the App Store, which runs with every release.

## Consequences

The build of a Nextcloud app reaches only the key that signs it, the delivery and the second job of the registration only the token of the App Store, and none of them the private key of the release app. The registration takes two jobs and a hand-over of public data, which `tests/test_workflow_steps.py` runs with a key and a certificate of its own. Once a beta release has built, signed and verified, step 4 of #530 takes both secrets out of `release`.

The proof came from a release instead of a beta: paperless-sync 1.5.0, on version 1.9.0 of the blueprint, built and signed in `signing`, delivered from `appstore` and passed its verification on 2026-11-04. A beta would have replaced the last release in the App Store for every user, as its package still says the version of that release in `appinfo/info.xml` ([#635](https://github.com/Dennis-Otto/repo-blueprint/issues/635)). Step 4 then took both secrets out of `release`.
