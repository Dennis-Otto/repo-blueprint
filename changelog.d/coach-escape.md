### Bug fixes

- **The PR coach writes its warning sign as an escape:** the sign before "stopped before the end" carried an invisible variation selector in `.github/blueprint/coach.py`, which a project that refuses characters a review on GitHub can't see, such as issue-assistant, failed in every update of the blueprint. A test keeps every file of the package free of such characters.
