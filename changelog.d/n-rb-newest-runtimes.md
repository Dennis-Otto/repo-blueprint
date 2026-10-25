### Bug fixes

- **The newest-Python check tests the newest Python:** `newest-python.yml` asked for `3.x` without `check-latest`, so setup-python took the Python that the image of the runner keeps in its cache, and every run tested Python 3.14 while Python 3.15 was out. The check now takes the newest release as soon as it is out, the summary of its run names the Python that it tested, and the issue *The checks fail with the newest Python* names it too, such as Python 3.15.1. The promise of a beta is gone, which no run had kept. A test of the lock files no longer depends on how Python words a failed command, which Python 3.15 changed.

### Features

- **Node packages get a check with the newest Node:** the new workflow `newest-node.yml` runs the checks of `scripts/check.sh` with the newest release of Node after every change of `main` and every week, while the CI checks the Node of `.nvmrc`. It is no required check; a failure keeps one issue open, *The checks fail with the newest Node*, which names the Node that failed and which the weekly run closes once the checks pass again.
