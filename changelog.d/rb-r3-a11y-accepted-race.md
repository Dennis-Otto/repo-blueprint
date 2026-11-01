### Bug fixes

- **The accessibility check no longer trips CodeQL in a project with JavaScript:** the check looked whether `.github/a11y-accepted.toml` exists before it read the file and later wrote it, which CodeQL reports as a high file system race (`js/file-system-race`) and which blocks the merge of the update wherever code scanning is a rule of `main`. The check now just reads the file, and a missing file still means that it accepts nothing.
