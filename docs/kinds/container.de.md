---
description: "Eine Vorlage für ein Container-Image: Alpine per Digest festgelegt, Hadolint, ein Build und ein Selbsttest in jedem Pull Request und Releases in der GitHub Container Registry für amd64 und arm64 mit SBOM und signierter Provenance."
---

# Vorlage für Container-Images: Alpine per Digest, Hadolint und Multi-Arch-Images auf GHCR mit SBOM

Ein Image für die GitHub Container Registry, gebaut auf einer Basis, die Renovate per Digest weiterzieht.

## Eines anlegen

```sh
uvx --from copier==9.19.1 copier copy --data project_type=container gh:Dennis-Otto/repo-blueprint my-image
cd my-image
python3 .github/blueprint.py create
```

Mit [uv](https://docs.astral.sh/uv/) und der GitHub CLI, wie [der Schnellstart](../guide.md#ein-repository-anlegen) zeigt. Copier fragt nach dem Namen, dem Eigentümer und den anderen Antworten, und `create` legt das Repository auf GitHub an, wendet die Einstellungen als Code an und zeigt die Checkliste.

## Was du bekommst

- **Das Beispiel:** `Dockerfile`, das von Alpine startet, per Digest festgelegt, und `app/entrypoint.sh`, das der Selbsttest ausführt. Ersetze es durch den echten Code; seine Tests zeigen, wie.
- **Die Schritte von `scripts/check.sh` für diese Art,** auf deinem Rechner wie in der CI: Hadolint für das `Dockerfile`, der Build des Images und sein Selbsttest.
- **Die Schritte jeder Art:** die Textdateien, die Diagramme, die Seiten in einer Spalte, die Fragmente des Changelogs, die akzeptierten Advisories, die Lock-Dateien, die Version, die Git-Hooks, ShellCheck für die Shell-Skripte und der strenge Build der Website.
- **Alles, was jedes Repository bekommt:** den PR-Coach und den Fix-Bot, den Release-Bot, Renovate, die Einstellungen als Code, den Issue-Assistenten, die Website auf Deutsch und Englisch, die Sicherheitsprüfungen und den Blueprint-Bot, wie [die Anleitung](../guide.md#was-ein-neues-repository-bekommt) sie nennt.

## Die Prüfungen, die ein Pull Request braucht

Das Ruleset *Protect main* aus `.github/repository.toml` lässt einen Pull Request mergen, sobald diese Prüfungen grün sind:

- `check (container)`: `scripts/check.sh` mit Hadolint und Docker.
- `lint`, `diagrams`, `docs`, `conventional title`, `codeql`, `dependency-review` und `gitleaks`, die jede Art braucht: jeder Linter in einem Job, die Bilder der Diagramme, der strenge Build der Website, der Titel des Pull Requests mit seinem Eintrag im Changelog, CodeQL, die Prüfung neuer Abhängigkeiten und der Secret-Scan.

## Auslieferung

Der Merge des Release-Pull-Requests baut das Image für `linux/amd64` und `linux/arm64` und schiebt es in die GitHub Container Registry, mit den Tags der Version, etwa `1.4.2`, `1.4` und `1`, mit seiner SBOM und der signierten Provenance nach SLSA Build Level 3.

## Einmal von Hand

`python3 .github/blueprint.py checklist` hakt jeden Schritt ab, den es sehen kann, und nennt den Rest, jeweils mit seinem Link: die Release-App des Eigentümers mit ihrem privaten Schlüssel, wie [dein eigenes Konto](../own-account.md) zeigt, das Token des Issue-Assistenten, außer seine KI ist aus, OpenSSF Best Practices, die REUSE-API und die Social Preview.

Diese Art bringt diese Schritte dazu:

- Nach dem ersten Release das Paket des Images öffentlich machen.

## Ein echtes Repository

<!-- --8<-- [start:real-repository] -->

Noch folgt kein öffentliches Repository dieser Art dem Blueprint. Der Workflow Variants des Blueprints macht bei jeder Änderung eines daraus und führt seine Prüfungen mit ihren echten Werkzeugen aus, und er aktualisiert eines von der neuesten Version, wie sein Blueprint-Bot es täte.

<!-- --8<-- [end:real-repository] -->

Wie sich der Blueprint mit anderen Vorlagen vergleicht: [der Vergleich](../compare.md).
