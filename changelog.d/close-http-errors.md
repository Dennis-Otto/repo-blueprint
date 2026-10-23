### Bug fixes

- **The checks pass with the newest Python:** Python 3.14 warns of an HTTP error that is left open, and the tests fail on that warning, so the workflow *Newest Python* failed. The checklist (`blueprint.py checklist`), the dashboard, `pins.py` and `downstream.py` now close every HTTP error that they catch, with the answer of the server that it holds.
