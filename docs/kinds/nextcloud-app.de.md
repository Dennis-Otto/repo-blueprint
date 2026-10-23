---
description: "Eine Vorlage für eine Nextcloud-App: php-cs-fixer, Psalm mit seiner Taint-Analyse, PHPUnit mit jeder Zeile abgedeckt, das älteste PHP geprüft, ein Upstream-Bot für neue Versionen von Nextcloud und signierte Pakete für den App Store."
---

# Vorlage für Nextcloud-Apps mit der Taint-Analyse von Psalm, PHPUnit und signierten Releases im App Store

Eine App für Nextcloud in PHP, mit der Analyse von Psalm, die den Daten einer Anfrage durch den Code folgt, und einem signierten Paket, das der Release-Bot in den App Store schickt.

## Eines anlegen

```sh
uvx --from copier==9.19.0 copier copy --data project_type=nextcloud-app gh:Dennis-Otto/repo-blueprint my-app
cd my-app
python3 .github/blueprint.py create
```

Mit [uv](https://docs.astral.sh/uv/) und der GitHub CLI, wie [der Schnellstart](../guide.md#ein-repository-anlegen) zeigt. Copier fragt nach dem Namen, dem Eigentümer und den anderen Antworten, und `create` legt das Repository auf GitHub an, wendet die Einstellungen als Code an und zeigt die Checkliste.

## Was du bekommst

- **Das Beispiel:** `appinfo/info.xml`, `lib/AppInfo/Application.php`, die PHPUnit-Tests in `tests/Unit/` mit dem `tests/bootstrap.php` und den `tests/stubs/`, die sie laden, `psalm.xml`, `phpunit.xml`, `composer.json` mit seiner Lock-Datei und `krankerl.toml`, das das Paket baut. Die Lizenz beginnt als AGPL-3.0-or-later, die Lizenz von Nextcloud. Ersetze es durch den echten Code; seine Tests zeigen, wie.
- **Die Schritte von `scripts/check.sh` für diese Art,** auf deinem Rechner wie in der CI: Composer, die Metadaten der App, die Syntax von PHP, der Code und seine Pakete auf dem ältesten PHP, php-cs-fixer, Psalm, ein Kanarienvogel, der zeigt, dass die Taint-Analyse noch sieht, die Taint-Analyse selbst, PHPUnit in zufälliger Reihenfolge mit jeder Zeile abgedeckt und das Paket.
- **Die Schritte jeder Art:** die Textdateien, die Diagramme, die Seiten in einer Spalte, die Fragmente des Changelogs, die Version, die Git-Hooks, ShellCheck für die Shell-Skripte und der strenge Build der Website.
- **Workflows dieser Art:** die Mutationstests mit Infection jede Woche (`mutation.yml`), der Upstream-Bot, der `max-version` anhebt, wenn Nextcloud eine neue Major-Version hat (`upstream.yml`), und die Registrierung der App im App Store (`register-app.yml`).
- **Alles, was jedes Repository bekommt:** den PR-Coach und den Fix-Bot, den Release-Bot, Renovate, die Einstellungen als Code, den Issue-Assistenten, die Website auf Deutsch und Englisch, die Sicherheitsprüfungen und den Blueprint-Bot, wie [die Anleitung](../guide.md#was-ein-neues-repository-bekommt) sie nennt.

## Die Prüfungen, die ein Pull Request braucht

Das Ruleset *Protect main* aus `.github/repository.toml` lässt einen Pull Request mergen, sobald diese Prüfungen grün sind:

- `check (php)`: `scripts/check.sh` mit den Werkzeugen von PHP.
- `lint`, `diagrams`, `docs`, `conventional title`, `codeql`, `dependency-review` und `gitleaks`, die jede Art braucht: jeder Linter in einem Job, die Bilder der Diagramme, der strenge Build der Website, der Titel des Pull Requests mit seinem Eintrag im Changelog, CodeQL, die Prüfung neuer Abhängigkeiten und der Secret-Scan.

## Auslieferung

Der Merge des Release-Pull-Requests baut das Paket mit krankerl, signiert es mit dem Schlüssel der App und veröffentlicht es im App Store, mit seiner SBOM und der signierten Provenance nach SLSA Build Level 3. Das Environment `release` hält die Secrets `APP_PRIVATE_KEY` und `APPSTORE_TOKEN`.

## Einmal von Hand

`python3 .github/blueprint.py checklist` hakt jeden Schritt ab, den es sehen kann, und nennt den Rest, jeweils mit seinem Link: die Release-App des Eigentümers mit ihrem privaten Schlüssel, wie [dein eigenes Konto](../own-account.md) zeigt, das Token des Issue-Assistenten, außer seine KI ist aus, OpenSSF Best Practices, die REUSE-API und die Social Preview.

Diese Art bringt diese Schritte dazu:

- Das Zertifikat der App beantragen: <https://nextcloudappstore.readthedocs.io/en/latest/developer.html>.
- Danach *Actions → Register the app* mit der ID der App starten.

## Ein echtes Repository

[Paperless Sync](https://github.com/Dennis-Otto/paperless-sync) und [Paperless Unified Search](https://github.com/Dennis-Otto/paperless-unified-search) sind aus dem Blueprint entstanden: zwei Nextcloud-Apps für Paperless-ngx, mit End-to-End-Tests in einem echten Nextcloud.

Wie sich der Blueprint mit anderen Vorlagen vergleicht: [der Vergleich](../compare.md).
