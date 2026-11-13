# A drop of the mutation score counts from the best run

- Status: accepted
- Date: 2026-11-13

## Context

[0031](0031-mutation-tests-in-parts-with-the-logic-first-and-an-issue-on-a-drop.md) opens the issue *Mutation score dropped* when a complete run of the default branch is more than half a point below the complete run before it. The tolerance is there for the noise of a run, such as a mutant at its time limit, but the run before moves on with every run: a score that loses 0.5 points a week, a few weakly tested lines at a time, falls from 90 % to 80 % in twenty weeks without an issue, while the same ten points in one week open it (repo-blueprint#824).

## Options

1. Compare with the run before, as before: the noise and a slow erosion look the same.
2. Compare with each of the last few complete runs: a fall of less than the tolerance across that window still goes unnoticed, and an accepted drop comes back until it leaves the window.
3. Keep a high-water mark: the best score and the best score of the logic of the complete runs, which each run's `mutation.json` carries forward, and compare each run with it, still with the tolerance.

## Decision

Option 3.

- **The mark:** `mutation report` writes `best` into `mutation.json`: for `score` and for `logic_score` the complete run with the highest, without the runs that it keeps itself. A complete run that reaches a score of the mark takes its place for that score; an incomplete one carries the mark on unchanged, as it carries its `baseline`. A `mutation.json` from before the mark counts as its own mark, so the first run after the change compares as before.
- **The drop:** `mutation issue` compares the run with the mark of each score. When either falls by more than half a point, the issue opens with the run of that mark as the run before the drop, the one of the larger fall when both fall, keeps it current while the run stays below it, and closes it once a run is back, as before.
- **An accepted drop:** a lower score can be right, such as after new code with few tests. A maintainer then closes the issue as *not planned*. Its marker keeps the latest run that it showed and the runs of the marks that the score and the score of the logic fell below, which may be two different runs, and while a mark stays at such a run, later runs compare with the score of that latest run instead, so one closure accepts the fall of both scores: a further fall below it opens the issue again, and a run back at the best moves the mark on. Only an issue closed as not planned counts, the newest for each run, among the latest 100 closed issues of the label `maintenance`.

## Consequences

A slow fall of the score crosses the tolerance after a few runs and opens the issue, and the noise of a single run still doesn't. The issue names the best run as the run before, which may be weeks old. Closing the issue by hand without *not planned* no longer accepts the score: the next run opens it again. An acceptance older than the latest 100 closed issues of the label is forgotten, and the issue opens once more, to be closed again.
