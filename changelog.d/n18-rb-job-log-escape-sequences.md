### Bug fixes

- The report of flaky tests names the tests of a job that failed at first again: since version 2.97.0 of the GitHub CLI, which the runners bring, it refused to print a job's log with its colors, and the report found no test in the empty log, without a word. A log that can't be read now gives a warning in the run, with the reason, and every repository gets the fix with the next release of the blueprint.
