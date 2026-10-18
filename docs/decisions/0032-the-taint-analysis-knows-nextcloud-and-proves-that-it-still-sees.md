# The taint analysis of a Nextcloud app knows Nextcloud, and proves in every run that it still sees

- Status: accepted
- Date: 2026-10-18

## Context

CodeQL has no PHP, so the taint analysis of Psalm in `scripts/check.sh` is the only analysis that follows untrusted input through the code of a Nextcloud app, and SECURITY.md and the checks presented it as such. It saw almost nothing:

- **No input:** Nextcloud passes the parameters of a request to a controller as the arguments of its public methods, where Psalm sees no `$_GET`. The taint graph of paperless-sync had 2,130 lines and not one source; a controller that passed a parameter to `file_get_contents()` or to the HTTP client of Nextcloud passed the check. `nextcloud/ocp` marks only the getters of `IRequest` as sources, which the apps never call.
- **No sinks of Nextcloud:** `nextcloud/ocp` marks the queries of the database as sinks, but not the paths of the files and folders of a user, the address of a request of `IClient` or the address of a redirection.
- **No alarm:** an analysis that finds nothing looks the same as one that sees nothing, so nothing showed that it had been blind from the start.

On paperless-sync and paperless-unified-search, the analysis that knows Nextcloud found at once the paths that a review had found by hand: a folder path from the settings to the files of a user, through the function that refuses `..`, and the address of Paperless from the settings to a request of the server, through the function that allows only `http` and `https`.

## Options

1. **Stubs of the classes of `nextcloud/ocp`** with `@psalm-taint-sink` and `@psalm-taint-source`. A stub replaces the class that it names, so each one has to copy the whole interface, and drifts from it with every update of `nextcloud/ocp`.
2. **Nextcloud's own `AppFrameworkTainter.php`** of nextcloud/server, a copy of a file of another project under its license, which makes the parameters of a controller sources, and leaves the sinks to stubs.
3. **A plugin of the blueprint** that makes the parameters of the public methods of every controller sources, as Nextcloud's analysis does, and marks the sources and sinks of `nextcloud/ocp` in what Psalm has read of it, by the names of their classes, methods and parameters; a name that `nextcloud/ocp` no longer has stops Psalm with the name. A canary proves in every run that the analysis finds each kind of path.

## Decision

Option 3. `.github/psalm/NextcloudTaintPlugin.php`, which `psalm.xml` loads, adds to what `nextcloud/ocp` marks itself:

- **Sources:** every parameter of a public method of a controller, the term and the filters of a search, and the answer of another server, its body and its headers, which the app doesn't control.
- **Sinks:** the paths of the files and folders of a user and of the data of the app, the address of every request of `IClient`, and the address of a `RedirectResponse`, an open redirect.

The canary, a controller in `.github/psalm/canary/`, lets the input of a request reach each kind of sink, and marks each line where the analysis has to find a path with `// expect:` and the issue. The step *Psalm taint canary* of `scripts/check.sh` analyses it with the plugin and the same `nextcloud/ocp`, while the types are checked on another processor, and fails unless the analysis finds every path that the canary expects and no other, such as the one that a function of the canary escapes. The CI uploads the paths of the analysis of the app to code scanning, with each line that they take, from a job of its own that runs no code of the app.

A function of the app that makes the input safe for a sink says so with `@psalm-taint-escape` and a comment on why, where a reviewer sees it, instead of a suppression in `psalm.xml`, which would hide every path of its kind.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/how-the-taint-analysis-of-a-nextcloud-app-sees.dark.svg">
  <img src="../images/diagrams/how-the-taint-analysis-of-a-nextcloud-app-sees.svg" alt="How the taint analysis of a Nextcloud app sees untrusted input: The plugin of the blueprint tells Psalm what Nextcloud hides from it. The parameters of a request to a controller, the term of a search and the answers of other servers are untrusted input, next to IRequest. The paths of files, the addresses of requests to other servers and of redirections are sinks, next to the queries that nextcloud/ocp marks itself. Input that reaches a sink unescaped fails check (php), with its path in the log and in code scanning; a function of the app that makes it safe says so. A canary with a path to each kind of sink proves in every run that the analysis still finds them.">
</picture>

## Consequences

- A Nextcloud app fails `check (php)` with the update that brings the plugin when input reaches a sink on a path that no function of the app escapes: paperless-sync and paperless-unified-search each mark one function with `@psalm-taint-escape`, `file` for the paths of folders and `ssrf` for the address of Paperless, in the pull request of the update.
- The canary takes no time of its own: it runs beside the check of the types, which takes one processor, and the three steps of Psalm take about as long as two did.
- An update of `nextcloud/ocp` that renames or removes a method that the plugin names stops Psalm with the name of the method, instead of leaving the analysis blind to that sink; the blueprint adapts the plugin, and the project keeps the update until then. An update of Psalm that changes how plugins work fails the canary.
- The upload to code scanning is a job of its own, `taint report (php)`, the only one with the right to write alerts; it runs for a push and a pull request from a branch of the repository, and not for one from a fork, whose token can't write them.
- The templates of an app, the one place where it writes HTML, stay outside the analysis: Psalm can't follow the parameters of a `TemplateResponse` into them.
