### Bug fixes

- **The dependency review accepts the new license of `wcwidth`:** the current release of this tool of the blueprint bot declares `HPND-Markus-Kuhn AND MIT`, a permissive license that the review did not know, so it stopped every refresh of the lock files. A new project accepts it from the start. An existing project owns its `.github/dependency-review.yml`, so add `pkg:pypi/wcwidth` under `allow-dependencies-licenses` there.
