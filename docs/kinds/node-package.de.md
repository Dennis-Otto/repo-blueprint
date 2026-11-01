---
description: "Eine Vorlage für ein Node-Paket in TypeScript: Biome für Lint und Format, tsc, node:test mit jeder Zeile, jedem Zweig und jeder Funktion abgedeckt, npm ohne die Skripte der Pakete und Releases auf npm mit Provenance per Trusted Publishing."
---

# Vorlage für npm-Pakete in TypeScript mit Biome, node:test und npm-Provenance

Ein Paket für npm in TypeScript auf Node 24, mit den Werkzeugen, die Node selbst mitbringt, wo sie genügen.

## Eines anlegen

```sh
uvx --from copier==9.19.1 copier copy --data project_type=node-package gh:Dennis-Otto/repo-blueprint my-package
cd my-package
python3 .github/blueprint.py create
```

Mit [uv](https://docs.astral.sh/uv/) und der GitHub CLI, wie [der Schnellstart](../guide.md#ein-repository-anlegen) zeigt. Copier fragt nach dem Namen, dem Eigentümer und den anderen Antworten, und `create` legt das Repository auf GitHub an, wendet die Einstellungen als Code an und zeigt die Checkliste.

## Was du bekommst

- **Das Beispiel:** `src/index.ts`, gebaut nach `dist/`, die Tests in `test/`, `tsconfig.json` und `tsconfig.build.json`, `biome.jsonc` und `package.json` mit seiner Lock-Datei. Ersetze es durch den echten Code; seine Tests zeigen, wie.
- **Die Schritte von `scripts/check.sh` für diese Art,** auf deinem Rechner wie in der CI: die Lock-Datei, die zu `package.json` passen muss, Biome für Lint und Format, tsc für die Typen, node:test mit jeder Zeile, jedem Zweig und jeder Funktion abgedeckt und seinem Bericht im PR-Coach, und `npm pack`; npm installiert ohne die Skripte der Pakete.
- **Workflows dieser Art:** das neueste Node auf `main` (`newest-node.yml`), nach jeder Änderung und jede Woche, während die CI das Node aus `.nvmrc` prüft.
- **Die Schritte jeder Art:** die Textdateien, die Diagramme, die Seiten in einer Spalte, die Fragmente des Changelogs, die akzeptierten Advisories, die Lock-Dateien, die Version, die Git-Hooks, ShellCheck für die Shell-Skripte und der strenge Build der Website.
- **Alles, was jedes Repository bekommt:** den PR-Coach und den Fix-Bot, den Release-Bot, Renovate, die Einstellungen als Code, den Issue-Assistenten, die Website auf Deutsch und Englisch, die Sicherheitsprüfungen und den Blueprint-Bot, wie [die Anleitung](../guide.md#was-ein-neues-repository-bekommt) sie nennt.

## Die Prüfungen, die ein Pull Request braucht

Das Ruleset *Protect main* aus `.github/repository.toml` lässt einen Pull Request mergen, sobald diese Prüfungen grün sind:

- `check (node)`: `scripts/check.sh` mit den Werkzeugen von Node.
- `lint`, `diagrams`, `docs`, `conventional title`, `codeql`, `dependency-review` und `gitleaks`, die jede Art braucht: jeder Linter in einem Job, die Bilder der Diagramme, der strenge Build der Website, der Titel des Pull Requests mit seinem Eintrag im Changelog, CodeQL, die Prüfung neuer Abhängigkeiten und der Secret-Scan.

## Auslieferung

Der Merge des Release-Pull-Requests veröffentlicht das Paket auf npm mit Provenance, per Trusted Publishing aus dem Environment `npm`, ohne Token, und hängt es an das Release, mit seiner SBOM und der signierten Provenance nach SLSA Build Level 3. Ein Paket, das keine Registry aufnimmt, antwortet bei [`publish_to_npm`](../reference/questions.md#publish_to_npm) mit Nein: Sein Release bleibt dann auf GitHub, mit dem, was `scripts/release-assets.sh` baut, und die Anleitung für Beiträge, `SECURITY.md` und die Einstellungen sagen das auch.

## Einmal von Hand

`python3 .github/blueprint.py checklist` hakt jeden Schritt ab, den es sehen kann, und nennt den Rest, jeweils mit seinem Link: die Release-App des Eigentümers mit ihrem privaten Schlüssel, wie [dein eigenes Konto](../own-account.md) zeigt, das Token des Issue-Assistenten, außer seine KI ist aus, OpenSSF Best Practices, die REUSE-API und die Social Preview.

Diese Art bringt diese Schritte dazu:

- Den Trusted Publisher auf npm eintragen, mit dem Workflow `release.yml` und dem Environment `npm`: <https://www.npmjs.com/settings/~/packages>.

## Ein echtes Repository

<!-- --8<-- [start:real-repository] -->

[Player Switch for Autodarts](https://github.com/Dennis-Otto/player-switch-for-autodarts) ist aus dem Blueprint entstanden: ein gemeinsames Autodarts-Display, an dem jeder unter seinem eigenen Konto spielt und ein Tipp auf eine Kachel den Spieler wechselt, ohne neue Anmeldung.

Der Workflow Variants probiert jeden Pull Request des Blueprints mit den Antworten von Player Switch for Autodarts aus, bevor er merged.

<!-- --8<-- [end:real-repository] -->

Wie sich der Blueprint mit anderen Vorlagen vergleicht: [der Vergleich](../compare.md).
