### Bug fixes

- **The Findings check passes again with the newer zizmor:** zizmor now reports the start of the issue assistant on a new comment (`issue_comment`) as a dangerous trigger. `.github/zizmor.yml` accepts it for that rule and that workflow alone, with the reason: the issue assistant checks out no code of a pull request and reads the comment only as text, its AI runs with read-only tools on the egress-firewall runner, and its answer is checked before anything is written.
