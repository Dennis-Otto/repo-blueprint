---
description: "Eine Vorlage für eine GitHub Action: eine Composite Action in Python mit Ruff, mypy, voller Abdeckung, Fuzzing, Mutations- und Property-Tests, einem Lauf der Action in jedem Pull Request und signierten Release-Tags mit einem mitwandernden Major-Tag."
---

# Vorlage für GitHub Actions: eine Composite Action mit Tests, Fuzzing und signierten Release-Tags

Eine Composite Action, deren Code Python ist, auf dem Python 3.12 des Runners, sodass sie ohne Container und ohne Build startet, getestet so, wie ihre Nutzer sie ausführen.

## Eines anlegen

```sh
uvx copier copy --data project_type=github-action gh:Dennis-Otto/repo-blueprint my-action
cd my-action
python3 .github/blueprint.py create
```

Mit [uv](https://docs.astral.sh/uv/) und der GitHub CLI, wie [der Schnellstart](../guide.md#ein-repository-anlegen) zeigt. Copier fragt nach dem Namen, dem Eigentümer und den anderen Antworten, und `create` legt das Repository auf GitHub an, wendet die Einstellungen als Code an und zeigt die Checkliste.

## Was du bekommst

- **Das Beispiel:** `action.yml`, das Modul der Action daneben, seine Tests in `tests/` und die Ziele des Fuzzings in `fuzz/`. Ersetze es durch den echten Code; seine Tests zeigen, wie.
- **Die Schritte von `scripts/check.sh` für diese Art,** auf deinem Rechner wie in der CI: Ruff, mypy und die Tests mit jeder Zeile und jedem Zweig abgedeckt, auf jedem Kern.
- **Die Schritte jeder Art:** die Textdateien, die Diagramme, die Seiten in einer Spalte, die Fragmente des Changelogs, die Version, die Git-Hooks, ShellCheck für die Shell-Skripte und der strenge Build der Website.
- **Workflows dieser Art:** ein Lauf der Action, wie ihre Nutzer sie ausführen, in jedem Pull Request (`action-test.yml`), Fuzzing mit Atheris (`fuzz.yml`), das neueste Python auf `main` (`newest-python.yml`), die Property-Tests jede Nacht (`properties.yml`) und die Mutationstests mit mutmut jede Woche (`mutation.yml`).
- **Alles, was jedes Repository bekommt:** den PR-Coach und den Fix-Bot, den Release-Bot, Renovate, die Einstellungen als Code, den Issue-Assistenten, die Website auf Deutsch und Englisch, die Sicherheitsprüfungen und den Blueprint-Bot, wie [die Anleitung](../guide.md#was-ein-neues-repository-bekommt) sie nennt.

## Die Prüfungen, die ein Pull Request braucht

Das Ruleset *Protect main* aus `.github/repository.toml` lässt einen Pull Request mergen, sobald diese Prüfungen grün sind:

- `check (github-action)`: `scripts/check.sh` mit den Werkzeugen von Python.
- `action`: die Action selbst, wie `action-test.yml` sie ausführt.
- `lint`, `diagrams`, `docs`, `conventional title`, `codeql`, `dependency-review` und `gitleaks`, die jede Art braucht: jeder Linter in einem Job, die Bilder der Diagramme, der strenge Build der Website, der Titel des Pull Requests mit seinem Eintrag im Changelog, CodeQL, die Prüfung neuer Abhängigkeiten und der Secret-Scan.

## Auslieferung

Der Merge des Release-Pull-Requests legt den signierten Release-Tag an, etwa `v1.4.2`, und schiebt den Major-Tag, etwa `v1`, darauf, sodass die Nutzer von `@v1` jedes kompatible Release bekommen. Das Release hat seine SBOM und die signierte Provenance nach SLSA Build Level 3.

## Einmal von Hand

`python3 .github/blueprint.py checklist` hakt jeden Schritt ab, den es sehen kann, und nennt den Rest, jeweils mit seinem Link: die Release-App des Eigentümers mit ihrem privaten Schlüssel, wie [dein eigenes Konto](../own-account.md) zeigt, das Token des Issue-Assistenten, außer seine KI ist aus, OpenSSF Best Practices, die REUSE-API und die Social Preview.

Diese Art bringt keinen eigenen Schritt dazu.

## Ein echtes Repository

Der [Issue-Assistent](https://github.com/Dennis-Otto/issue-assistant) ist aus dem Blueprint entstanden: eine erste Analyse jedes neuen Issues durch eine KI, die nur liest, und jedes Repository des Blueprints nutzt ihn.

Wie sich der Blueprint mit anderen Vorlagen vergleicht: [der Vergleich](../compare.md).
