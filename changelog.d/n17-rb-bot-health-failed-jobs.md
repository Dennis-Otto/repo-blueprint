### Bug fixes

- **A failure issue of the bot-health bot stays open until the jobs that failed pass again:** a run that passes closes the issue only when every job that failed ran again in it and passed, a job of a matrix such as `render (en, 3/4)` in every leg of its name. A run that skipped the broken job, as a push that the Screenshots workflow only plans, leaves the issue open and names the job, so a broken bot no longer looks fixed for a day ([#702](https://github.com/Dennis-Otto/repo-blueprint/issues/702)). Close such an issue by hand when the job that failed is gone or has a new name.
