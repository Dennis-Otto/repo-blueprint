### Bug fixes

- **Nextcloud apps lock a safe symfony/filesystem:** the lock of the PHP stack moves symfony/filesystem from 7.4.21 to 7.4.23, which fixes the advisory [GHSA-6prc-h956-hxjq](https://github.com/symfony/symfony/security/advisories/GHSA-6prc-h956-hxjq); Composer's audit failed every new or updated Nextcloud app until then.
