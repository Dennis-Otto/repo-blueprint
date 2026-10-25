---
description: "Eine Vorlage für ein Python-Paket: Hatchling, Ruff, mypy im strengen Modus, Tests mit jeder Zeile und jedem Zweig abgedeckt auf jedem Kern, Fuzzing, Mutations- und Property-Tests und Releases auf PyPI per Trusted Publishing mit signierter Provenance."
---

# Vorlage für Python-Pakete mit Hatchling, voller Abdeckung und Trusted Publishing auf PyPI

Eine Bibliothek oder ein Befehl für PyPI, gebaut mit Hatchling und veröffentlicht ohne Token.

## Eines anlegen

```sh
uvx --from copier==9.19.0 copier copy --data project_type=python-package gh:Dennis-Otto/repo-blueprint my-package
cd my-package
python3 .github/blueprint.py create
```

Mit [uv](https://docs.astral.sh/uv/) und der GitHub CLI, wie [der Schnellstart](../guide.md#ein-repository-anlegen) zeigt. Copier fragt nach dem Namen, dem Eigentümer und den anderen Antworten, und `create` legt das Repository auf GitHub an, wendet die Einstellungen als Code an und zeigt die Checkliste.

## Was du bekommst

- **Das Beispiel:** `src/<package>/` mit seinem `py.typed`, die Tests in `tests/`, die Ziele des Fuzzings in `fuzz/` und `pyproject.toml`, für Python ab 3.12. Ersetze es durch den echten Code; seine Tests zeigen, wie.
- **Die Schritte von `scripts/check.sh` für diese Art,** auf deinem Rechner wie in der CI: Ruff, mypy, die Tests mit jeder Zeile und jedem Zweig abgedeckt, auf jedem Kern, und der Build des Pakets.
- **Die Schritte jeder Art:** die Textdateien, die Diagramme, die Seiten in einer Spalte, die Fragmente des Changelogs, die akzeptierten Advisories, die Lock-Dateien, die Version, die Git-Hooks, ShellCheck für die Shell-Skripte und der strenge Build der Website.
- **Workflows dieser Art:** Fuzzing mit Atheris (`fuzz.yml`), das neueste Python auf `main` (`newest-python.yml`), die Property-Tests jede Nacht (`properties.yml`) und die Mutationstests mit mutmut jede Woche (`mutation.yml`).
- **Alles, was jedes Repository bekommt:** den PR-Coach und den Fix-Bot, den Release-Bot, Renovate, die Einstellungen als Code, den Issue-Assistenten, die Website auf Deutsch und Englisch, die Sicherheitsprüfungen und den Blueprint-Bot, wie [die Anleitung](../guide.md#was-ein-neues-repository-bekommt) sie nennt.

## Die Prüfungen, die ein Pull Request braucht

Das Ruleset *Protect main* aus `.github/repository.toml` lässt einen Pull Request mergen, sobald diese Prüfungen grün sind:

- `check (python)`: `scripts/check.sh` mit den Werkzeugen von Python.
- `lint`, `diagrams`, `docs`, `conventional title`, `codeql`, `dependency-review` und `gitleaks`, die jede Art braucht: jeder Linter in einem Job, die Bilder der Diagramme, der strenge Build der Website, der Titel des Pull Requests mit seinem Eintrag im Changelog, CodeQL, die Prüfung neuer Abhängigkeiten und der Secret-Scan.

## Auslieferung

Der Merge des Release-Pull-Requests baut das Paket einmal, veröffentlicht es auf PyPI per Trusted Publishing aus dem Environment `pypi`, ohne Token, und hängt es an das Release, mit seiner SBOM und der signierten Provenance nach SLSA Build Level 3.

## Einmal von Hand

`python3 .github/blueprint.py checklist` hakt jeden Schritt ab, den es sehen kann, und nennt den Rest, jeweils mit seinem Link: die Release-App des Eigentümers mit ihrem privaten Schlüssel, wie [dein eigenes Konto](../own-account.md) zeigt, das Token des Issue-Assistenten, außer seine KI ist aus, OpenSSF Best Practices, die REUSE-API und die Social Preview.

Diese Art bringt diese Schritte dazu:

- Den Trusted Publisher auf PyPI eintragen, mit dem Workflow `release.yml` und dem Environment `pypi`: <https://pypi.org/manage/account/publishing/>.

## Ein echtes Repository

<!-- --8<-- [start:real-repository] -->

Noch folgt kein öffentliches Repository dieser Art dem Blueprint. Der Workflow Variants des Blueprints macht bei jeder Änderung eines daraus und führt seine Prüfungen mit ihren echten Werkzeugen aus, und er aktualisiert eines von der neuesten Version, wie sein Blueprint-Bot es täte.

<!-- --8<-- [end:real-repository] -->

Wie sich der Blueprint mit anderen Vorlagen vergleicht: [der Vergleich](../compare.md).
