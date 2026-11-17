# The packages of Playwright come without a release age, like its images

- Status: accepted, amended by [0172](0172-a-young-version-of-main-stays-in-the-refresh-and-a-refresh-that-takes-one-back-holds.md), with which a refresh that takes a Playwright of `main` back holds until Renovate builds it anew
- Date: 2026-11-17

## Context

Each image of Playwright on mcr.microsoft.com, such as `mcr.microsoft.com/playwright/python` or `mcr.microsoft.com/playwright`, holds the browsers of one release of Playwright, and only the package of the same release starts them: the npm packages `playwright`, `playwright-core` and `@playwright/test`, or the package `playwright` of PyPI. Every repository that runs such an image therefore keeps the two in one group of Renovate, and a test of the project fails while their versions differ.

mcr.microsoft.com gives Renovate no date of a release, so since [0148](0148-an-image-without-a-date-comes-without-a-release-age-and-its-new-digest-in-a-branch-of-its-own.md) an image of Playwright comes at once, while its package waits the week of `minimumReleaseAge: "7 days"`, and with `internalChecksFilter: "strict"` Renovate takes the newest version that is a week old. Playwright 1.65.0 came out on 9 November 2026 on PyPI, 1.65.1 on 11 November and 1.65.2 on 14 November; on 17 November the group of each repository put the image of 1.65.2 beside the package of 1.65.0. The update of Playwright failed its checks in five repositories at once: the blueprint's #977, homedarts-for-autodarts#750, paperless-sync#509, paperless-unified-search#464 and player-switch-for-autodarts#289. It would have stayed red until the package of the newest patch was a week old, and Playwright brings a patch every few days after a minor release.

## Options

1. **Wait:** the group heals once the package of the newest image is a week old, but every patch of Playwright in the meantime starts the wait again, and each red run sends a mail.
2. **A date for the image:** Renovate takes the date of an image only from its registry, and mcr.microsoft.com gives none; `minimumReleaseAgeBehaviour: "timestamp-required"` would hold the image for good, as before 0148.
3. **Only versions `x.y.0`, by `allowedVersions`:** image and package meet, but no patch of Playwright, which fixes its bugs, would ever come.
4. **No release age for the packages of Playwright:** the package comes at once, as its image does, and the group takes the same newest release for both.

## Decision

Option 4. The rules of Renovate that every repository shares give the packages `playwright`, `playwright-core` and `@playwright/**` of npm and PyPI `minimumReleaseAge: null`, right after the rule of the images. The week protects against a version published from a hijacked account. For Playwright, the image of the same release, with the code of that release, already runs at once, but the packages are published with other credentials than the images on mcr.microsoft.com: a release of the package alone, published from a hijacked account of npm or PyPI, now reaches every repository that uses it at the next Monday run of Renovate, also one that runs no image of Playwright and installs its browsers with `playwright install`. The owner accepts that risk, so that an update of Playwright merges at all; the accessibility check of the blueprint, whose `playwright-core` drives the Chrome of the runner beside no image, keeps the week by a rule of its own in `.github/renovate.json5`. A test of the template keeps the rule in every kind of project, after the rule of the images and with no later rule of the blueprint that gives the package a week again.

## Consequences

An update of Playwright brings the image and the package of the same release in one pull request and merges once its checks pass. When the image of a new release comes a few hours after its package, the group splits for one run of Renovate and heals in the next. A project that runs Playwright from npm and from PyPI at once, such as player-switch-for-autodarts, still meets a release that Microsoft publishes only for Python, as 1.65.2: its own test decides which version it follows. The packages of Playwright no longer wait the week, also in a repository without its image; every other package still does. In a project of npm, the weekly refresh of the lock files of [0137](0137-the-refresh-of-the-lock-files-merges-by-itself-from-versions-a-week-old.md) resolves a range such as `^1.65.0` from the versions a week old and so can take a Playwright younger than the week back to the one before; its check dependency-review then holds the refresh until that Playwright is a week old. Nothing breaks, and that wait of up to a week is accepted.
