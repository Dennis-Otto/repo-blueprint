# A lock file of pip-compile compiles again on its own pins, with uv

- Status: accepted
- Date: 2026-11-02

## Context

pip installs a lock file as it is. A package that a pull request adds to `requirements-dev.in`, or a bound that it moves there, reaches no install until someone compiles `requirements-dev.txt` again, and no check said so. Self-healing, part 3 ([#429](https://github.com/Dennis-Otto/repo-blueprint/issues/429)) needs that check first, and its fix then is a compile. The step *Lock files* only reads the header of each file, as Renovate does ([decision 0069](0069-a-lock-file-and-a-version-fix-themselves-only-where-their-tool-refuses-them.md) names what fixes itself so far).

The check must not fail at random, and the bot must not write what it doesn't understand. Three things can change a compile without any change of the sources: a new release upstream, a new wheel of a pinned version, and the Python or the system of the machine that runs it. The last one has already cost a lock file of Home Assistant its packages ([#127](https://github.com/Dennis-Otto/repo-blueprint/pull/127)).

## Options

1. Compare the text of the file with a fresh compile. Each new release upstream, each new wheel and each difference between pip-compile and uv would fail the check.
2. Compile with the real tool of each header, pip-compile for most files. It needs pip-tools in the check and the Python of each file on the runner, and it would resolve for the Python that runs it, as in #127.
3. Compile with uv on a copy of the file and compare only the pins.

## Decision

Option 3, as the step *Lock files match their sources* of `scripts/check.sh` with `blueprint.py locks --compile`, and `--fix` as its autofix.

- **The pins of the file win:** uv reads the copy of the file as its output file, so it prefers each version that the file pins and keeps the hashes of that version. Only a change of the sources moves a pin. A test with wheels on the disk and the real uv shows that new versions and a new wheel of a pinned version change neither the result nor the hashes.
- **The Python of the file:** the option `--python-version=` of a header of uv, or the Python that pip-compile named in its header. That one names no patch release, and uv takes a version without one for its release .0, for which a package that needs 3.14.2 has no solution, so the compile asks for the patch release .99, as Renovate takes the newest one. uv runs with the Python of the check, which then decides nothing.
- **The system:** Linux, on which Renovate and the CI compile, unless the header says `--universal`. On Windows, a compile would otherwise add `colorama`.
- **What counts:** name and version, or the name alone for an address, whose commit can move. A pin without a hash counts too when the compile gives it hashes, since `pip install --require-hashes` then refuses the file. Spelling, extras, markers, annotations and the hashes themselves don't count: uv and pip-compile don't write them all alike.
- **What the fix writes:** the comments at the top of the file as they are, with the Python and the tool of the file, above the lines of uv, which are those of pip-compile, byte for byte, in every lock file of the blueprint.
- **Fail closed:** a file that the check doesn't understand stays as it is, and the log says why: a link, a command that Renovate can't read, which the step *Lock files* explains, a line that is no pin, such as an index, which a fix would lose, or a header of uv without `--python-version=`, for which the machine would decide. Sources without a solution fail the check without a change. The check passes without uv, and when uv reaches no package index: neither says anything of the file, and every required check of a project has uv.
- **No shell:** the header comes from the pull request, so its options become arguments of uv, and only those that the step *Lock files* lets through reach it. The compile runs in the job of the check, which can't write. The fix bot takes the file from its artifact as data, as every other fix ([decision 0023](0023-pull-requests-fix-themselves.md)).
- **uv in the CI:** the kinds of project that have no other use for it, those for a container, Node, PHP and without a build, install it only when the repository has a `requirements*.txt`.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/how-a-lock-file-of-pip-compile-fixes-itself.dark.svg">
  <img src="../images/diagrams/how-a-lock-file-of-pip-compile-fixes-itself.svg" alt="How a lock file of pip-compile fixes itself: A pull request changes a source, such as requirements-dev.in. The step Lock files match their sources has uv compile each lock file again, on a copy, for the Python of its header and on the versions that it pins, and compares the pins. Without a difference, the file stays as it is, also after a new release upstream. With one, the check fails, and the autofix keeps the result below the header of the file; the fix bot commits it, and the checks run again. When uv finds no solution, nothing changes, and the log says why.">
</picture>

## Consequences

A pull request that changes a source passes after one commit of the bot, and one from a fork gets the suggestion. Compiling every file takes a few seconds: the 9 lock files of the blueprint take 8 seconds without a cache, at the same time, and a repository made from it has 1 to 3.

A lock file that uv and pip-compile would resolve differently fails where Renovate's result stays valid, and Renovate would then undo the commit of the bot. No file of the seven repositories does so today; such a file can move to a header of `uv pip compile`. A marker that changes without a pin stays unnoticed until the next compile of the file.
