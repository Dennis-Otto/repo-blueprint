# The release app comes from a manifest, through a server on 127.0.0.1, and its key touches no disk

- Status: accepted
- Date: 2026-11-01

## Context

Every owner brings their own release app ([decision 0049](0049-every-owner-brings-their-own-release-app.md)), and registering it was the biggest hurdle of a new owner. A link filled in the form on GitHub, but its parameters have no name for *Variables*, so one permission was set by hand. The owner then generated a private key, copied the name, the Client ID and the App ID into a `copier update`, opened a pull request, opened the page of the installation and set the secret. A typing error in a copied value showed only later, when a bot failed, and the `.pem` stayed in the folder of the downloads.

GitHub offers a flow for this, [registering an app from a manifest](https://docs.github.com/en/apps/sharing-github-apps/registering-a-github-app-from-a-manifest): a form sends the manifest, the owner confirms one page, and GitHub redirects with a code that `POST /app-manifests/{code}/conversions` trades for the id, the slug, the client ID and the private key. The private key comes once, in that answer. A manifest takes every permission under its API name, `actions_variables` too.

## Options

1. Keep the link and check the copied values afterwards. The steps stay, and the key stays a download.
2. A page of the website that shows the form and shows the answer. A page on the web can't reach `gh`, and the private key would pass through a browser.
3. A command with a local form written to a temporary file, and a server for the redirect. A file holds the state, which has to be secret from other pages, and browsers treat a `file://` page differently from one with an address.
4. A command with a server on a free port of `127.0.0.1` that shows the form and takes the redirect. The form lives in memory, and only this machine reaches the port.

## Decision

Option 4, as `python3 .github/blueprint.py app register`, in [`blueprint/app.py`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/blueprint/app.py), which every repository gets.

- **Check first.** A private key comes once, so a preflight checks everything that could be known before the browser opens: the sign-in of `gh`, the owner, the environment `release`, a folder without changes and a Copier to run. Marks and fixes are those of `create` ([decision 0078](0078-create-checks-what-it-needs-first-and-goes-on-where-it-stopped.md)).
- **The server trusts only this run.** The `state` of the form is a fresh `secrets.token_urlsafe(32)`, compared in constant time. A wrong one is refused with a 400 and ends nothing, so that any page that calls the port can't end the wait, and its code is never traded. A request for another `Host` is refused too, so that a stranger's page under a name that points to `127.0.0.1` can't read the state from the form. The log of the server is off: an address with the code in it would be on the terminal, and the code trades for the key for an hour.
- **The private key touches no disk.** It stays in memory and goes on the stdin of `gh secret set`, not in an argument, which any process could read. No `repr` shows it, no error quotes the answer of GitHub, and the client secret and the secret of the webhook are dropped. The key is set before anything else, since it is the one value that can't be asked for again.
- **What can't be undone is said, not hidden.** A browser signed in as another account makes an app on that account, which can't be installed on the repository, since it is private: the command stops before the key is set and names the page that deletes it. A refused key leaves an app without a key: the command names the page that makes another and the `app connect` that goes on. A step of the pull request that fails leaves the steps that are left, to run by hand.
- **The answers go through a pull request,** with a branch, the pinned Copier of the quick start, or the first of `uvx`, `pipx` and `copier` that runs, a commit with a sign-off and `gh pr create`, because `create` has protected `main`. `--no-update` prints these commands.
- **A person still confirms and installs.** GitHub has no API for either, and neither should be done for the owner without asking.
- **`app connect --key-file` serves an app that exists,** such as for a further repository, which needs its own secret. GitHub answers `GET /apps/{slug}` of a private app with a 404 even to its owner's token of `gh`, so the name and the IDs come from the answers or the command line, where the rules of the questions of Copier check them. The key comes from a file, which the owner deletes: GitHub offers no other way to a second key.
- **The checklist names the command** in place of the link. It ticks the installation off when `GET /repos/{repo}/commits/main/check-suites?app_id=` shows a suite of the app, which GitHub opens for an installed app with *Checks* at each push. No API tells the opposite to the owner, and an app may have come after the last push, so without such a suite the step stays neutral, never a cross.

## Consequences

- A new owner runs one command, confirms one page, installs the app and merges a pull request. No value is copied by hand, and no key file stays behind.
- A copy needs a browser on the same machine or a forwarded port; `--no-browser` prints the address. An owner who can't use this registers the app by hand and uses `app connect`.
- The real page of GitHub can't run in the tests. They use a simulated `gh`, git and Copier and a fake browser, whose requests reach the real server over a real socket, so the first real run of a new owner is what tests the part of GitHub.
- The settings app ([decision 0077](0077-a-second-app-writes-the-administration.md)) is still registered by hand; the same flow could register it.
