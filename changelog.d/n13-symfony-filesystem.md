### Bug fixes

- **Nextcloud apps lock a safe symfony/filesystem:** the lock of the PHP stack moves symfony/filesystem from 7.4.21 to 7.4.23, which fixes the advisory [GHSA-6prc-h956-hxjq](https://github.com/symfony/symfony/security/advisories/GHSA-6prc-h956-hxjq); Composer's audit failed every new or updated Nextcloud app until then.
- **The update leg of the Variants updates a package that an advisory names:** the update keeps the `composer.lock` of a Nextcloud app as the latest release locked it, so an advisory published since then failed every pull request, also the one that fixes the lock; now the leg updates the named packages first, as Renovate's vulnerability alerts do in a repository, and `composer audit` still fails a package that no version fixes.
