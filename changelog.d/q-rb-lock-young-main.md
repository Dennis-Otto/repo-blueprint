### Bug fixes

- The weekly refresh of the lock files of pip-compile no longer fails when `main` has a version younger than a week, such as the fix of a vulnerability or a release of Playwright: that package keeps the version of `main`, and every other package still takes only versions at least a week old. A refresh that would take back a version of `main`, such as npm's refresh that resolves a range back to an older version, now waits until Renovate builds it anew, and no longer passes once that version is a week old.
