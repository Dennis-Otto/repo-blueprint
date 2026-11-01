### Bug fixes

- **A failing `scripts/release-assets.sh` explains itself:** when the script of a project failed, wrote no asset or named one as the release names its own, the release stayed a draft and only the log of the run told why. The summary of the run and an annotation now say what failed, why it matters and how to fix it: re-run the failed jobs after a hiccup, or fix the script for the next release, as the build runs at the commit of the release, and delete the old draft by hand.
