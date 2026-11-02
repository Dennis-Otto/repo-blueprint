---
description: "Eine Vorlage für eine Chrome-Erweiterung mit Manifest V3 in TypeScript: die Prüfung des Manifests gegen den Chrome Web Store, ein Test in Chrome for Testing und jedes Release im Store, bei Google angemeldet ohne gespeichertes Geheimnis."
---

# Vorlage für Chrome-Erweiterungen mit Manifest V3 und Lieferung in den Chrome Web Store

Eine Chrome-Erweiterung mit Manifest V3 in TypeScript auf Node 24, die jedes Release von selbst in den Chrome Web Store bringt, bei Google angemeldet ohne gespeichertes Geheimnis.

## Eine anlegen

```sh
uvx --from copier==9.19.1 copier copy --data project_type=chrome-extension gh:Dennis-Otto/repo-blueprint my-extension
cd my-extension
python3 .github/blueprint.py create
```

Mit [uv](https://docs.astral.sh/uv/) und der GitHub CLI, wie [der Schnellstart](../guide.md#ein-repository-anlegen) zeigt. Copier fragt nach dem Namen, dem Eigentümer und den anderen Antworten, und `create` legt das Repository auf GitHub an, wendet die Einstellungen als Code an und zeigt die Checkliste.

## Was du bekommst

- **Das Beispiel:** die Erweiterung in `extension/`, mit `manifest.json` und ihren Texten in `_locales/en/`, ein Service Worker in `src/background.ts`, den der Build nach `extension/lib/` übersetzt, und seine Tests in `test/`. `store/` hält, was das Developer Dashboard nur von Hand nimmt: den Eintrag jeder Sprache, `store/listing.<sprache>.md`, den Grund jeder Berechtigung in `store/permissions.json` und die Bilder. Ersetze es durch die echte Erweiterung; seine Tests zeigen, wie.
- **Die Schritte von `scripts/check.sh` für diese Art,** auf deinem Rechner wie in der CI: die eines Node-Pakets, die Lock-Datei, Biome, tsc und node:test mit jeder Zeile, jedem Zweig und jeder Funktion abgedeckt, und dann *Extension*. Er prüft das Manifest mit `scripts/check-manifest.mjs`: Manifest V3, die Version des Releases, die Grenzen des Stores in jeder Sprache und für jede Berechtigung und jeden Host einen Grund und eine Begründung in den Einträgen. Dann baut er das Zip für den Store mit `scripts/package-extension.sh`, für denselben Commit dasselbe Zip. Biome lässt das Format von `extension/manifest.json` unangetastet, denn der Release-Bot schreibt jeden Eintrag einer Liste auf eine eigene Zeile, sodass ein Release-Pull-Request es besteht, und es lässt die Diagramme aus, die `scripts/diagrams.sh` zeichnet.
- **Ein Test in Chrome:** die CI lädt `extension/` mit `scripts/load-extension.mjs` in Chrome for Testing und schlägt fehl, wenn ihr Service Worker nicht startet.
- **Workflows dieser Art:** *Chrome Web Store* (`publish-store.yml`), der jedes Release liefert und jeden Tag nach ihm sieht, und das neueste Node auf `main` (`newest-node.yml`).
- **Die Schritte jeder Art:** die Textdateien, die Diagramme, die Seiten in einer Spalte, die Fragmente des Changelogs, die akzeptierten Advisories, die Lock-Dateien, die Version, die Git-Hooks, ShellCheck für die Shell-Skripte und der strenge Build der Website.
- **Alles, was jedes Repository bekommt:** den PR-Coach und den Fix-Bot, den Release-Bot, Renovate, die Einstellungen als Code, den Issue-Assistenten, die Website auf Deutsch und Englisch, die Sicherheitsprüfungen und den Blueprint-Bot, wie [die Anleitung](../guide.md#was-ein-neues-repository-bekommt) sie nennt.

## Die Prüfungen, die ein Pull Request braucht

Das Ruleset *Protect main* aus `.github/repository.toml` lässt einen Pull Request mergen, sobald diese Prüfungen grün sind:

- `check (node)`: `scripts/check.sh` mit den Werkzeugen von Node, danach die Erweiterung in Chrome for Testing.
- `lint`, `diagrams`, `docs`, `conventional title`, `codeql`, `dependency-review` und `gitleaks`, die jede Art braucht: jeder Linter in einem Job, die Bilder der Diagramme, der strenge Build der Website, der Titel des Pull Requests mit seinem Eintrag im Changelog, CodeQL, die Prüfung neuer Abhängigkeiten und der Secret-Scan.

## Auslieferung

Der Merge des Release-Pull-Requests veröffentlicht das Release. Sein isolierter Build zippt die Erweiterung aus dem signierten Tag und hängt das Zip an das Release, mit seiner SBOM und der signierten Provenance nach SLSA Build Level 3. Danach lädt der Workflow *Chrome Web Store* genau dieses Zip hoch, sobald er die Provenance geprüft hat, und reicht es zur Prüfung ein; Google veröffentlicht es nach der Prüfung.

Der Workflow meldet sich mit dem OIDC-Token von GitHub über Workload Identity Federation bei Google an, also liegt nirgends ein Geheimnis des Stores; bis das eingerichtet ist, geht es mit einem Refresh-Token. Er läuft auch jeden Tag: Er liefert ein Release nach, dessen Prüfung warten musste, und schlägt mit dem Grund und der Lösung fehl, wenn Google ablehnt oder warnt. [Entscheidung 0085](../decisions/0085-a-chrome-extension-reaches-the-store-with-the-zip-that-its-release-attests.md) hält fest, warum.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/how-a-chrome-extension-reaches-the-store.de.dark.svg">
  <img src="../images/diagrams/how-a-chrome-extension-reaches-the-store.de.svg" alt="Wie eine Chrome-Erweiterung in den Chrome Web Store kommt: Das Mergen des Release-Pull-Requests veröffentlicht das Release, dessen isolierter Build die Erweiterung aus dem signierten Tag zippt und bezeugt. Der Workflow Chrome Web Store fragt den Store nach dem Stand des Eintrags, nimmt das Zip nur mit seiner Provenance, meldet sich mit dem OIDC-Token von GitHub ohne gespeichertes Geheimnis bei Google an, lädt es hoch und reicht es zur Prüfung ein. Google prüft es und veröffentlicht es für die Nutzer; der tägliche Lauf liefert ein Release nach, dessen Prüfung warten musste, und meldet eine Ablehnung.">
</picture>

## Einmal von Hand

`python3 .github/blueprint.py checklist` hakt jeden Schritt ab, den es sehen kann, und nennt den Rest, jeweils mit seinem Link: die Release-App des Eigentümers mit ihrem privaten Schlüssel, wie [dein eigenes Konto](../own-account.md) zeigt, das Token des Issue-Assistenten, außer seine KI ist aus, OpenSSF Best Practices, die REUSE-API und die Social Preview.

Diese Art bringt diese Schritte dazu:

- Die erste Version im [Developer Dashboard](https://chrome.google.com/webstore/devconsole) von Hand hochladen, ihren Eintrag und ihre Datenschutzangaben aus `store/` ausfüllen und die Variablen `CWS_EXTENSION_ID` und `CWS_PUBLISHER_ID` setzen.
- Die Anmeldung ohne gespeichertes Geheimnis einrichten, mit einem Skript in der Cloud Shell von Google, und die Variablen `CWS_WORKLOAD_IDENTITY_PROVIDER` und `CWS_SERVICE_ACCOUNT` setzen.

`docs/releases.md` des neuen Repositorys beschreibt beide, und was zu tun ist, wenn ein Lauf des Workflows *Chrome Web Store* fehlschlägt.

## Ein echtes Repository

<!-- --8<-- [start:real-repository] -->

Noch folgt kein öffentliches Repository dieser Art dem Blueprint. Der Workflow Variants des Blueprints macht bei jeder Änderung seiner Dateien eines daraus und führt seine Prüfungen mit ihren echten Werkzeugen aus, und er aktualisiert eines von der neuesten Version, wie sein Blueprint-Bot es täte.

<!-- --8<-- [end:real-repository] -->

Wie sich der Blueprint mit anderen Vorlagen vergleicht: [der Vergleich](../compare.md).
