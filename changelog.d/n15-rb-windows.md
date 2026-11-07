### Bug fixes

- **The check on Windows passes on `main` again:** `jq.exe` of Windows ends each line with a CR before its LF, which `mapfile` of bash keeps, so in its test the update leg of the Variants updated `symfony/filesystem` with a CR at the end of its name, and *check (Windows)* failed on every run since 2026-11-05. In the tests of the steps of the workflows, a step now runs jq with `--binary` on Windows, so that jq ends its lines with LF, as on the runners of GitHub ([#676](https://github.com/Dennis-Otto/repo-blueprint/issues/676)).
