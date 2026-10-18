---
description: "Eine Vorlage für eine eigene Home-Assistant-Integration: HACS und hassfest in jedem Pull Request, Python 3.14 mit voller Abdeckung, Mutations- und Property-Tests und signierte Releases, die HACS installiert, aktuell gehalten von einem Bot."
---

# Vorlage für Home-Assistant-Integrationen mit HACS, hassfest und signierten Releases

Eine eigene Integration für Home Assistant, mit den Prüfungen von Home Assistant selbst in jedem Pull Request und einem Release, das HACS ab dem ersten Merge installiert.

## Eines anlegen

```sh
uvx copier copy --data project_type=home-assistant gh:Dennis-Otto/repo-blueprint my-integration
cd my-integration
python3 .github/blueprint.py create
```

Mit [uv](https://docs.astral.sh/uv/) und der GitHub CLI, wie [der Schnellstart](../guide.md#ein-repository-anlegen) zeigt. Copier fragt nach dem Namen, dem Eigentümer und den anderen Antworten, und `create` legt das Repository auf GitHub an, wendet die Einstellungen als Code an und zeigt die Checkliste.

## Was du bekommst

- **Das Beispiel:** `custom_components/<domain>/` mit seinem `manifest.json`, einem Config Flow, Übersetzungen auf Englisch und Deutsch und den Brand-Icons, `hacs.json` und die Tests in `tests/` mit pytest-homeassistant-custom-component, auf Python 3.14. Ersetze es durch den echten Code; seine Tests zeigen, wie.
- **Die Schritte von `scripts/check.sh` für diese Art,** auf deinem Rechner wie in der CI: Ruff, mypy und die Tests mit jeder Zeile und jedem Zweig abgedeckt, auf jedem Kern.
- **Die Schritte jeder Art:** die Textdateien, die Diagramme, die Seiten in einer Spalte, die Fragmente des Changelogs, die Version, die Git-Hooks, ShellCheck für die Shell-Skripte und der strenge Build der Website.
- **Workflows dieser Art:** die Property-Tests mit neuen zufälligen Eingaben jede Nacht (`properties.yml`) und die Mutationstests mit mutmut jede Woche (`mutation.yml`).
- **Alles, was jedes Repository bekommt:** den PR-Coach und den Fix-Bot, den Release-Bot, Renovate, die Einstellungen als Code, den Issue-Assistenten, die Website auf Deutsch und Englisch, die Sicherheitsprüfungen und den Blueprint-Bot, wie [die Anleitung](../guide.md#was-ein-neues-repository-bekommt) sie nennt.

## Die Prüfungen, die ein Pull Request braucht

Das Ruleset *Protect main* aus `.github/repository.toml` lässt einen Pull Request mergen, sobald diese Prüfungen grün sind:

- `check (home-assistant)`: `scripts/check.sh` mit den Werkzeugen von Home Assistant.
- `home-assistant`: die HACS-Action und hassfest, die Validierung von Home Assistant.
- `lint`, `diagrams`, `docs`, `conventional title`, `codeql`, `dependency-review` und `gitleaks`, die jede Art braucht: jeder Linter in einem Job, die Bilder der Diagramme, der strenge Build der Website, der Titel des Pull Requests mit seinem Eintrag im Changelog, CodeQL, die Prüfung neuer Abhängigkeiten und der Secret-Scan.

## Auslieferung

Der Merge des Release-Pull-Requests veröffentlicht ein Release mit dem Zip der Integration, das `hacs.json` nennt, also installiert HACS dieses Zip. Das Release hat seine SBOM und die signierte Provenance nach SLSA Build Level 3.

## Einmal von Hand

`python3 .github/blueprint.py checklist` hakt jeden Schritt ab, den es sehen kann, und nennt den Rest, jeweils mit seinem Link: die Release-App des Eigentümers mit ihrem privaten Schlüssel, wie [dein eigenes Konto](../own-account.md) zeigt, das Token des Issue-Assistenten, außer seine KI ist aus, OpenSSF Best Practices, die REUSE-API und die Social Preview.

Diese Art bringt diese Schritte dazu:

- Dem Repository die Beschreibung und die Topics geben, die HACS anzeigt und seine Prüfung braucht: Die Antwort `topics` nennt sie in `.github/repository.toml`, und `settings apply` setzt sie.
- Das Repository bei den Default-Repositories von HACS einreichen: <https://github.com/hacs/default>.

## Ein echtes Repository

[Autodarts für Home Assistant](https://github.com/Dennis-Otto/ha-autodarts) ist aus dem Blueprint entstanden: lokale Steuerung des Boards in Echtzeit, Spiele, Turniere und Statistiken, mit Dashboard-Karten, End-to-End-Tests in einem echten Home Assistant und Screenshots, die sich selbst erneuern.

Wie sich der Blueprint mit anderen Vorlagen vergleicht: [der Vergleich](../compare.md).
