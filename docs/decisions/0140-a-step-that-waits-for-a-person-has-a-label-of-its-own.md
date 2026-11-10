# A step that waits for a person has a label of its own

- Status: accepted, amends [0132](0132-the-bot-health-bot-asks-for-the-upload-of-a-new-social-preview.md)
- Date: 2026-11-10

## Context

The nightly look of the bot-health bot keeps one issue, *Upload the new social preview*, open while GitHub shows another picture than the committed `.github/social-preview.png` ([decision 0132](0132-the-bot-health-bot-asks-for-the-upload-of-a-new-social-preview.md)). It opened that issue as it opens every other one, with the labels `bot-failure` and `maintenance`. The description of `bot-failure` reads *A bot or a scheduled workflow fails on the default branch; closes when it passes again*, but nothing fails there: GitHub takes a social preview only from an upload, which no API offers, so the issue waits for a person ([#807](https://github.com/Dennis-Otto/repo-blueprint/issues/807)). The label sends a maintainer to look for a failed run that doesn't exist, and a list of the issues with `bot-failure` counts a reminder among the failures.

The pager reads the labels of these issues: [`src/rules.ts`](https://github.com/Dennis-Otto/repo-pager/blob/main/src/rules.ts) pages an issue of a bot only with the label `bot-failure`, and already tells the one of the social preview apart by the key `social-preview` in the marker of the bot, with a text of its own.

## Options

1. **A wider description of `bot-failure`,** such as *… or a step waits for a person*: no change of a bot or of the pager, but the name of the label still says that something fails.
2. **A label of its own for the issue of the social preview,** such as `social-preview`: it fits, but the next reminder of a bot would need another one.
3. **A label for every step of a bot that waits for a person, `manual-step`,** in place of `bot-failure` on such an issue: it says what the issue is, and serves the next reminder too, such as a key that expires.

## Decision

Option 3.

- **The issue of the social preview** has the labels `manual-step` and `maintenance`. `manual-step` reads *A bot waits for a step that only a person can take, such as an upload; closes once it is done*, in the group `release` of the labels that the bots set.
- **Every repository has the label:** a new one from its `.github/labels.toml`, and one whose own `.github/labels.toml` lacks it from the bot, which creates it before it opens the issue, as it does with `bot-failure`.
- **The nightly look finds the issue by either label,** with one more request each night: an issue that an earlier release opened with `bot-failure` keeps its labels until the upload closes it, so that the pager, which paged it as a bot-failure issue, also hears of its end. An issue with both labels counts once.
- **The bot's other issues keep `bot-failure`:** each of them is about a bot or a workflow that fails.

## Consequences

The label of the issue of the social preview says what the issue asks for, and a list of the issues with `bot-failure` holds only failures.

Until the pager pages an issue of a bot with the label `manual-step`, as it does one with `bot-failure`, it doesn't page a new issue of the social preview: GitHub still notifies whoever watches the repository. An issue opened before keeps paging and recovering as before. The pager's change is small: it takes either label, and keeps the text that it already gives the issue by its key.
