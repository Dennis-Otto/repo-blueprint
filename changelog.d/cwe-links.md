### Bug fixes

- **The link check passes again:** since 2026-10-23, cwe.mitre.org gives the runners of GitHub no answer, so the link to the CWE Top 25 in `SECURITY.md` failed the workflow *Links* on `main` of every repository. The check now leaves out the links to cwe.mitre.org, and only those: a link to any other site that doesn't answer still fails it.
