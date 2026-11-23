# A website is published only with its provenance, and a failed publication runs once more

- Status: accepted, amends [0044](0044-the-built-website-is-checked-and-every-deployment-is-signed.md), [0134](0134-a-job-stops-when-harden-runner-doesnt-block.md), [0136](0136-an-outage-of-github-starts-no-bot-failure.md) and [1096](1096-the-flaky-test-bot-reports-only-a-failure-of-the-code.md)
- Date: 2026-11-23

## Context

On 2026-11-22, *Docs* of issue-assistant failed on `main` in both attempts of run 45026526918, each time at the step *Attest the provenance of the website* of the job *publish the website*, with `InternalError: error fetching tlog entry - (404) Not Found`. sigstore-js writes these words in one case only: Rekor answered the new entry with 409 Conflict, as it does when an earlier request was written but its answer was lost, and then couldn't find the entry that the 409 named. The second attempt, started by hand 9 minutes later, signed with a new key and failed the same way; Sigstore answered again by 14:17, when the *Dashboard* of the blueprint attested.

The job published first and signed afterwards, so for an hour readers got a website that `gh attestation verify` couldn't check, although [0044](0044-the-built-website-is-checked-and-every-deployment-is-signed.md) says that every deployment is signed. Nothing tried a failed publication again: the jobs `rerun` and `report` of *After the checks* leave *Docs* out, the bot for stopped checks took it only when Harden-Runner stopped it ([0134](0134-a-job-stops-when-harden-runner-doesnt-block.md)), and the daily look of bot health reported it. In player-switch-for-autodarts, `actions/deploy-pages` failed on 2026-11-02 with `status: 500`, and the website stayed about 31 hours behind `main`, with an issue of bot health and nothing for the maintainer to do.

In the same review, the flaky-test bot of [1096](1096-the-flaky-test-bot-reports-only-a-failure-of-the-code.md) could outlast its job: its look-back asks about each run of a later attempt in the 7 days before with `tried`, which waits 70 seconds for GitHub before it gives up, and then asked about the next one; 53 such runs occurred in 7 days in the Docker E2E of homedarts-for-autodarts. And it counted the gate of end-to-end tests that only sums up the jobs that it needs as a failure of the code whenever the gate didn't say the words of 1096.

## Options

1. **A warning in place of the failure, or `continue-on-error` on the signature:** the check passes, and the website goes out without its provenance, which breaks the promise of 0044.
2. **Match Sigstore's messages, such as `tlog entry`, and try again only then:** a list that lags behind every new wording of sigstore-js.
3. **Sign before publishing, try the signature once more in the job, and let the bots run a failed publication once more, a bounded number of times.**

## Decision

Option 3:

- **Sign first.** The job *publish the website* of `docs.yml` and `dashboard.yml` takes the artifact, signs its `artifact.tar` and only then hands it to `actions/deploy-pages`. When no attestation was made, nothing is published, and the website stays as it was, with its provenance. That trades availability for the promise of 0044: while Sigstore fails, no website is published until a later try. An attestation of a website that GitHub Pages then fails to publish does no harm, and a rerun that signs again leaves two valid attestations of the same digest.
- **A second try in the job,** as the uploads of 1096 have: the first try gets `continue-on-error`, the second runs half a minute later with the same action, commit and inputs, and a step *Say that Sigstore failed* writes the error when it fails as well. A second try is safe: sigstore-js signs each run of the action with a new ephemeral key and Fulcio certificate, so its entry in Rekor is new and can't conflict with the first; an entry that the first try wrote and lost stays unused in the public log, and GitHub keeps an attestation only once its bundle exists. Every failure of the first try gets the second, whatever its message. The job's limit holds the limits of its steps, with two minutes for the wait for Docker.
- **The bot for stopped checks takes a second kind of failure outside the code.** Its job is now *run the checks again that failed outside the code*. Beside Harden-Runner, it runs the failed jobs of a run of *Docs* once more when the run comes from a push to the default branch, at its first attempt, and every job that failed is *publish the website* or *ask the published website*, or *docs* with no failed step but *Hand the website to GitHub Pages* and its second try. It asks GitHub for the head of the branch first, as before, and leaves alone the run of a commit that a newer push replaced, whose website would replace a newer one. Any other failure of *Docs*, such as a broken link, and every run of a pull request, stays as it is.
- **Bot health tries once more the next day.** Sigstore failed for at least ten minutes on 22 November, longer than the try in the job and the rerun minutes later. When the daily look finds such a run of *Docs* from a push, at the head of the default branch, with no later run of *Docs* on it that publishes (a run of its weekly schedule publishes nothing, so one that passed after it doesn't hide it), and older than its second try may take, it starts *Docs* on that branch with `workflow_dispatch` in place of a report. A new run builds and checks the website again, as the artifact of the old one may have expired, and a run that `workflow_dispatch` started is reported when it fails, so the tries end: one in the job, one rerun, one new run. *Dashboard* keeps its second try of bot health.
- **The look-back of the flaky-test bot stops** after a call that GitHub kept failing, with the warning that it writes for the pages, and after `LOOK_BACK_TIME`, 120 seconds, of asking about runs of a later attempt, about 50 of them at 2.4 seconds each. It counts as far as it got, and the summary says how far back it reached, as after 10 pages. There is no limit on the number of runs: 53 have occurred within 7 days.
- **The bot sees a job that only sums up others by itself.** It reads the file of the workflow at the commit of the run once, with the `yq` and `jq` that the runner image `ubuntu-24.04` lists, and a failed job gets no row when its definition, found by its literal `name` or its key, has `needs`, an `if` with `always()` or `!cancelled()`, and a job that it needs failed or was cancelled in the same attempt. A name with an expression gets no exemption. The words of 1096 keep working, and without the file the bot goes by them alone, with a notice.
- **Issue assistant sync says when it couldn't check a release,** with the words of an outage that the report job reads.

The release keeps its signatures as they are: a draft stays a draft until *Make the complete release public*, the bot for failed releases runs a failed job once more, and none of them failed at Sigstore in 30 days.

## Consequences

- No reader gets a website that `gh attestation verify` can't check, and a check never passes while the attestation is missing.
- A failure of GitHub Pages or Sigstore heals without a person: in the job, by a rerun at once, or by a new run the next day; the issue of bot health comes only when that run fails too.
- While Sigstore fails, the website stays at the commit before.
- The report job of the flaky-test bot ends in its 5 minutes when GitHub keeps failing, and reads `contents` to see the jobs that sum up others.
- How a job that runs out of time ends in the jobs API was not measured; the bots treat it, as before, as cancelled with the annotation of its time limit.
