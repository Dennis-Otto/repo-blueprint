# Releases und Sicherheit

Wie aus einer Änderung ein signiertes Release wird, und die Sicherheitsprüfungen jedes Repositorys.

## Releases

Ein Pull Request mit der nächsten Version, bestimmt aus den Titeln der gemergten Pull Requests (`fix` ein Patch, `feat` ein Minor, `!` ein Major, unter 1.0.0 ein Minor), und dem Text der Fragmente in `changelog.d/` und von *Unreleased* im Changelog als Notes; sein Merge veröffentlicht das Release mit Paket, SBOM und der signierten Provenance eines isolierten Builds (SLSA Build Level 3), liefert es aus und prüft es danach so, wie es seine Nutzer können, auch jede Woche; wo die Repository-Variable `BETA_CHANNEL` auf true steht, wird außerdem jede Änderung für Nutzer zu einer Beta des nächsten Releases, einem Prerelease für Tester.

**Womit:** Release-please, die Release-App, unveränderliche Releases, `verify-release.yml`.

## Von einer Änderung zum Release

Der Titel eines Pull Requests bestimmt die nächste Version, und der Merge des Release-Pull-Requests erledigt den Rest:

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/from-a-change-to-a-release.de.dark.svg">
  <img src="../images/diagrams/from-a-change-to-a-release.de.svg" alt="Von einer Änderung zum Release: Ein Pull Request mit dem Titel fix, feat oder feat! merged in main, sobald alle Prüfungen grün sind. Der Release-Bot hält einen Release-Pull-Request mit der nächsten Version und dem Text der Fragmente und von Unreleased. Sein Merge signiert zuerst seinen Tag, im nächsten Lauf des Release-Bots, baut dann das Release isoliert, sobald der Tag geprüft ist, signiert und veröffentlicht es, liefert es aus und prüft es, sofort und jede Woche. Mit BETA_CHANNEL wird außerdem jede Änderung für Nutzer zu einer Beta.">
</picture>

Ein Pull Request beschreibt, was er für Nutzer ändert, in einer eigenen Datei, einem Fragment in `changelog.d/`, etwa `changelog.d/dark-mode.md`, unter der Überschrift seiner Art von Änderung, etwa `### Features`. Eine neue Datei kollidiert mit nichts, also mergen Pull Requests, die gleichzeitig laufen, nacheinander, ohne dass jemand `main` in jeden von ihnen mergt, und ein Release kollidiert nicht mehr mit den wartenden Pull Requests. Die Prüfung des Titels, *conventional title*, prüft jedes Fragment eines Pull Requests so, wie das Release es übernimmt, und zählt nur ein neues als seinen Eintrag, `scripts/check.sh` prüft auch jedes Fragment, das auf `main` wartet, und der Release-Bot verschiebt jedes Fragment in den Abschnitt des Releases und löscht es im selben Commit. Eine Überschrift, die sicher eine Art von Änderung meint, etwa `### Fixes` für `### Fixed` oder `## Features` für `### Features`, benennt der Fix-Bot auf dem Branch des Pull Requests um und schlägt sie auf einem aus einem Fork vor; eine, die einer Art so nahe ist wie einer anderen, etwa `### Change`, bleibt ihrem Autor. Bis zum Release zeigt eine Seite der Website, die `CHANGELOG.md` einbindet, etwa der Changelog dieser, die Einträge der Fragmente unter *Unreleased*, gruppiert wie das Release sie gruppiert. Eine Zeile unter `## Unreleased` in `CHANGELOG.md` funktioniert weiterhin.

release-please liest den Titel jedes gemergten Pull Requests, nicht seine ganze Beschreibung. Der Squash-Commit trägt die Beschreibung, und eine Zeile darin, die der strenge Parser von release-please für einen Footer hält, etwa `**[(Full` aus den Release Notes, die Renovate zitiert, ließ ihn den Commit in einem grünen Lauf überspringen, sodass ein Fix auf ein anderes Release wartete, das ihn nicht nannte. Darum schreibt der Release-Bot, bevor release-please läuft, den Titel und die Zeilen `Release-As:` und `BREAKING CHANGE:` jedes Pull Requests seit dem letzten Release, der es ändern kann, an das Ende seiner Beschreibung, als Override in einem HTML-Kommentar, den die Seite nicht zeigt; eine Änderung, die GitHub ablehnt, ist eine Warnung, und release-please läuft trotzdem. Der Release-Pull-Request ändert sich nur noch, wenn sich seine Notes ändern; zuvor baute release-please ihn in jedem Lauf neu, und jede seiner Prüfungen startete von vorn (Entscheidung 0060 der [Entscheidungen](https://github.com/Dennis-Otto/repo-blueprint/blob/main/docs/decisions/README.md)).

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/the-changelog-without-conflicts.de.dark.svg">
  <img src="../images/diagrams/the-changelog-without-conflicts.de.svg" alt="Der Changelog ohne Konflikte: Zwei Pull Requests fügen je eine eigene Datei zu changelog.d hinzu, also mergen sie nacheinander ohne Konflikt in main. Der Release-Bot schreibt den Abschnitt des nächsten Releases aus den Fragmenten und dem Text von Unreleased in CHANGELOG.md des Release-Pull-Requests und löscht die Fragmente im selben Commit. Sein Merge macht diesen Abschnitt zu den Notes des Releases. Bis dahin zeigt die Website die Einträge der Fragmente unter Unreleased, und der Fix-Bot benennt eine Überschrift eines Fragments um, die sicher eine Art von Änderung meint.">
</picture>

Jedes Release beschreibt in seinen SBOMs, als SPDX und als CycloneDX, was es ausliefert: das Paket, das seine Nutzer installieren, oder die Dateien seines Tags ohne die, die das Projekt nur prüfen, testen und dokumentieren, unter dem Namen des Repositorys und der Version des Releases. Ein Scanner eines Nutzers meldet nur die Advisories dessen, was das Release ausliefert, und wendet sein OpenVEX-Dokument darauf an (Entscheidung 0034 der [Entscheidungen](https://github.com/Dennis-Otto/repo-blueprint/blob/main/docs/decisions/README.md)):

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/what-the-sboms-of-a-release-describe.de.dark.svg">
  <img src="../images/diagrams/what-the-sboms-of-a-release-describe.de.svg" alt="Was die SBOMs eines Releases beschreiben: Der Build entpackt, was das Release ausliefert, in einen eigenen Ordner: das Zip von HACS, das Wheel, das npm-Paket oder die signierte Nextcloud-App, und für eine Action, ein Image oder ein Projekt ohne Paket die Dateien seines Tags ohne die, die das Projekt nur prüfen, testen und dokumentieren. syft, geprüft an seinem sha256, listet die Komponenten, die ein Paket installiert oder die die Quellen deklarieren, unter dem Namen des Repositorys und der Version des Releases, als SPDX und als CycloneDX. Der Build und die Release-Prüfung prüfen, dass beide das Release nennen, und ein Scanner eines Nutzers wendet das OpenVEX-Dokument des Releases auf die SPDX-SBOM an.">
</picture>

Ein Release von paperless-sync, wie GitHub seine Assets zeigt: die signierte App, ihre Signatur, ihre SBOMs als CycloneDX und SPDX, die Provenance ihres Builds mit ihrem Sigstore-Bundle, die Hinweise zu ihren Abhängigkeiten und die Attestation des Releases:

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/github-release.dark.png">
  <img src="../images/github-release.png" alt="Die Assets des Releases v1.2.0 von paperless-sync auf GitHub: paperless-sync.cdx.json, paperless-sync.spdx.json, paperless_sync.tar.gz, paperless_sync.tar.gz.sig, provenance.intoto.jsonl, provenance.sigstore.json und THIRD_PARTY_NOTICES.md, jedes mit seinem sha256 und seiner Größe, dann der Quellcode als zip und tar.gz und die Attestation des Releases">
</picture>

## Sicherheit

CodeQL, und für das PHP einer Nextcloud-App die Taint-Analyse von Psalm, die die Controller, Dateien und den HTTP-Client von Nextcloud kennt und mit einem Canary in jedem Lauf beweist, dass sie noch sieht, OpenSSF Scorecard, Dependency Review, Secret Scan, SBOMs dessen, was ein Release ausliefert, als SPDX und CycloneDX, mit seinem Namen und seiner Version, OpenVEX, schlüssellos signierte und vor jedem Build geprüfte Release-Tags (gitsign), Findings-Wächter, die Sicherheitsprüfung der Workflows (zizmor), jede Lock-Datei gegen die OSV-Datenbank (OSV-Scanner), der Netzwerkverkehr jedes Jobs (Harden-Runner), die Antworten von OpenSSF Best Practices und der OSPS Baseline, die der Blueprint garantiert (`.bestpractices.json`).

**Womit:** Jede Action auf einen Commit-Hash gepinnt.

## App Store

Für eine Nextcloud-App: die Registrierung ihrer ID mit ihrem Zertifikat, einmal, von Hand.

**Womit:** `register-app.yml`.
