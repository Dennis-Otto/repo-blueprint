# An image without a date comes without a release age, and its new digest in a branch of its own

- Status: accepted
- Date: 2026-11-12

## Context

Renovate waits a week after the release of a version, with `minimumReleaseAge: "7 days"` and `internalChecksFilter: "strict"`, and puts the new versions and the new digests of every image into one group, *the images*. In Renovate 44, an update whose release has no date counts as waiting for good, by the default `minimumReleaseAgeBehaviour: "timestamp-required"`, and no registry gives Renovate a date it can count on:

- **ghcr.io, mcr.microsoft.com and quay.io** give no date at all. Paperless-ngx 3.4.2 never reached paperless-unified-search or paperless-sync, homedarts-for-autodarts stayed at Home Assistant 2026.10.0, and the Renovate of the Renovate workflow stayed at the version of 13 October.
- **Docker Hub** gives the latest push of a tag, which every rebuild of an official image renews, and none at all to a request without a login for an image of more than 1,000 tags: from the eleventh page of 100, it answers 403 *pagination offset too large for anonymous requests*. nextcloud, postgres, python and redis have more; mariadb, with 957, got its updates.

A run of Renovate 44.145.1 with `LOG_LEVEL=debug` on paperless-unified-search showed both: *Marking 6 release(s) as pending, as they do not have a releaseTimestamp* for Paperless-ngx, and the same for nextcloud, redis and postgres after the error of Docker Hub. In the group, the new version of an image and the new digest of its tag then met: Renovate kept the version and dropped the digest (*Ignoring upgrade collision*, at the level info), and then removed the version as well, since it was waiting, from a branch that had other updates. Neither came ([#859](https://github.com/Dennis-Otto/repo-blueprint/issues/859)). The issue *Renovate logs problems* showed nothing, since it reads the warnings and errors alone.

## Options

1. **A login to Docker Hub for Renovate:** dates for every image of Docker Hub, but a new secret in every repository, and the date is still that of the latest rebuild; ghcr.io stays without one.
2. **`minimumReleaseAgeBehaviour: "timestamp-optional"` for images:** an image without a date comes at once, one with a date waits a week after its latest push, so whether an image waits depends on how many tags it has and how often it is rebuilt, and Renovate warns of every update without a date in each run, which a `logLevelRemap` can lower to the level info.
3. **No release age for images:** each comes at the next run of Renovate on a Monday, as one pull request whose checks test it, by its digest, but so does an image with a date, which drops the week that [0005](0005-renovate-instead-of-dependabot.md) and [0012](0012-lock-refresh-waits-for-the-maintainer.md) keep against a version published from a hijacked account.

## Decision

Option 2, for the datasource `docker`, which covers the images of compose files, Dockerfiles, workflows and the pins of scripts: it brings what waited for good and keeps the week wherever a registry gives a date, so it weakens the control of 0005 only where Renovate can't apply it anyway. A date of Docker Hub is that of the latest push of a tag, so an image whose tag is pushed again waits a week from that push, as mariadb did, and still came. `logLevelRemap` lowers Renovate's warning of each update without a date to the level info, so that it doesn't fill the issue *Renovate logs problems*. A second rule moves the new digest of a tag that stays into a branch of its own beside that of its group, `<group>-digests`, with the title *update the digests of …*. It sets the `group` settings of these updates, not a name of a group, so that it applies to a group that the project names as well, such as *Paperless-ngx*: in one branch with the new version of the same image, Renovate would drop one of the two. `logLevelRemap` raises *Ignoring upgrade collision* to a warning, so that the issue *Renovate logs problems* counts each collision, with the dependency, the update that Renovate kept and the one that it dropped, and says how to keep them apart.

## Consequences

Every image gets its new version and its new digest, and a project's group of an image, such as Paperless-ngx, its own pull request. An image without a date, of ghcr.io, mcr.microsoft.com, quay.io or a large image of Docker Hub, comes on the Monday after its release, without the week: its digest keeps it the image that the checks of the pull request tested, and an update merges by itself only once every check passes, but an image published from a hijacked account reaches every repository at the next Monday run, which [the security page](../security.md#residual-risks) names as a residual risk. An image with a date still waits the week. A Monday with both a new version and a new digest of the images brings two pull requests, and the second is rebased after the first merges. A collision that still comes, from a rule of a project that puts two updates of one dependency into one branch, shows in the issue *Renovate logs problems* until the rule keeps them apart. Should Docker Hub or another registry give the date of a release, such as Docker Hub to a login for Renovate, the week of waiting comes back for it without a change of the rules.
