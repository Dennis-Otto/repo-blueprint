### Bug fixes

- A new release of the issue assistant reaches the blueprint within a few hours of its release, as GitHub runs schedules, instead of the next day: the sync bot looks for one on an hourly schedule, and every repository gets it with the next release of the blueprint. A look that finds nothing new ends after a few seconds, without the release app.
