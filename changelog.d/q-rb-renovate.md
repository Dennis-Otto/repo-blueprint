### Bug fixes

- Renovate's update of Playwright merges by itself again. The packages of Playwright from npm and PyPI now come without the week of waiting, as its images on mcr.microsoft.com already did, so the image and the package that starts its browsers move to the same release. Before, the newest image met a package a few patches older, and the checks of the update failed.
- The Renovate of the Renovate workflow and of the Variants workflow is 44.247.2, and the shared rules of Renovate keep the dependency dashboard switched off in the form that Renovate asks for since 44.232.0, `dependencyDashboard: { enabled: false, title: "Dependency dashboard" }`. Its check of the configuration failed on the two settings of before, so the update of the images could not merge.
