---
description: "Eine Vorlage für ein GitHub-Repository ohne Build, etwa mit Dokumentation, Konfiguration oder Skripten: die Prüfungen der Textdateien und Shell-Skripte, eine Website, signierte Releases, die Einstellungen als Code und die Bots jedes Repositorys."
---

# Vorlage für GitHub-Repositories mit Dokumentation, Konfiguration und Skripten, mit Releases und Einstellungen als Code

Ein Repository mit Dokumentation, Konfiguration oder Skripten, das keinen Build braucht und dieselbe Pflege bekommt wie jede andere Art.

## Eines anlegen

```sh
uvx --from copier==9.19.0 copier copy --data project_type=generic gh:Dennis-Otto/repo-blueprint my-repository
cd my-repository
python3 .github/blueprint.py create
```

Mit [uv](https://docs.astral.sh/uv/) und der GitHub CLI, wie [der Schnellstart](../guide.md#ein-repository-anlegen) zeigt. Copier fragt nach dem Namen, dem Eigentümer und den anderen Antworten, und `create` legt das Repository auf GitHub an, wendet die Einstellungen als Code an und zeigt die Checkliste.

## Was du bekommst

- **Das Beispiel:** keines, nur die Community-Dateien, die Website in `docs/` und die Workflows.
- **Die Schritte jeder Art:** die Textdateien, die Diagramme, die Seiten in einer Spalte, die Fragmente des Changelogs, die akzeptierten Advisories, die Version, die Git-Hooks, ShellCheck für die Shell-Skripte und der strenge Build der Website.
- **Alles, was jedes Repository bekommt:** den PR-Coach und den Fix-Bot, den Release-Bot, Renovate, die Einstellungen als Code, den Issue-Assistenten, die Website auf Deutsch und Englisch, die Sicherheitsprüfungen und den Blueprint-Bot, wie [die Anleitung](../guide.md#was-ein-neues-repository-bekommt) sie nennt.

## Die Prüfungen, die ein Pull Request braucht

Das Ruleset *Protect main* aus `.github/repository.toml` lässt einen Pull Request mergen, sobald diese Prüfungen grün sind:

- `check (generic)`: `scripts/check.sh` mit den Textdateien und den Shell-Skripten.
- `lint`, `diagrams`, `docs`, `conventional title`, `codeql`, `dependency-review` und `gitleaks`, die jede Art braucht: jeder Linter in einem Job, die Bilder der Diagramme, der strenge Build der Website, der Titel des Pull Requests mit seinem Eintrag im Changelog, CodeQL, die Prüfung neuer Abhängigkeiten und der Secret-Scan.

## Auslieferung

Der Merge des Release-Pull-Requests veröffentlicht ein Release mit seinen Notizen aus dem Changelog und einem signierten Tag, ohne Paket.

## Einmal von Hand

`python3 .github/blueprint.py checklist` hakt jeden Schritt ab, den es sehen kann, und nennt den Rest, jeweils mit seinem Link: die Release-App des Eigentümers mit ihrem privaten Schlüssel, wie [dein eigenes Konto](../own-account.md) zeigt, das Token des Issue-Assistenten, außer seine KI ist aus, OpenSSF Best Practices, die REUSE-API und die Social Preview.

Diese Art bringt keinen eigenen Schritt dazu.

## Ein echtes Repository

[dennis-otto.github.io](https://github.com/Dennis-Otto/dennis-otto.github.io) ist aus dem Blueprint entstanden: die Website mit jedem Projekt seines Eigentümers.

Wie sich der Blueprint mit anderen Vorlagen vergleicht: [der Vergleich](../compare.md).
