# Repo Blueprint

[English version](README.md)

Eine [Copier](https://copier.readthedocs.io/)-Vorlage für GitHub-Repositories, die sich selbst pflegen: Tests bei jeder Änderung, ein Release-Bot, Sicherheitsprüfungen, ein Issue-Assistent und die Einstellungen des Repositorys als Code, für sieben Arten von Projekten. Ein Bot bringt jedes Repository, das aus der Vorlage entstanden ist, auf jede neue Version des Blueprints.

<sub>💛 Wenn dir der Blueprint hilft, kannst du [seine Entwicklung unterstützen](https://github.com/sponsors/Dennis-Otto).</sub>

## Was ein neues Repository bekommt

| Bereich | Was läuft | Womit |
| --- | --- | --- |
| **Prüfungen** | `scripts/check.sh` bei jeder Änderung, lokal wie in der CI: Tests mit voller Abdeckung, Typen, Lint, Paketbau | die Werkzeuge der jeweiligen Projektart, per Hash gepinnt |
| **Lint** | Workflows (actionlint), Lizenz jeder Datei (REUSE), Sign-off jedes Commits (DCO), Titel jedes Pull Requests (Conventional Commits) | `lint.yml`, `pull-request-title.yml` |
| **Sicherheit** | CodeQL, OpenSSF Scorecard, Dependency Review, Secret Scan, SBOM, Findings-Wächter | jede Action auf einen Commit-Hash gepinnt |
| **Releases** | ein Pull Request mit der nächsten Version und dem Changelog; sein Merge veröffentlicht das Release mit Paket, SBOM und signierter Provenance und liefert es aus | release-please, die Release-App, unveränderliche Releases |
| **Abhängigkeiten** | Dependabot mit einer Woche Wartezeit; Routine-Updates und Releases, die nur Abhängigkeiten aktualisieren, mergen sich selbst, sobald alle Prüfungen grün sind | `dependabot.yml`, `dependabot-automerge.yml` |
| **Issues** | eine erste Analyse jedes neuen Issues durch eine KI, die nur liest, Labels, Duplikate, Erinnerungen und das Schließen mit dem Release, das den Fix enthält | der [Issue-Assistent](https://github.com/Dennis-Otto/issue-assistant) |
| **Community** | README, Beitragsleitfaden, Verhaltenskodex, Sicherheitsrichtlinie, Support, Governance, Issue-Formulare, Pull-Request-Vorlage, Sponsor-Button, Social Preview | |
| **Einstellungen** | die Einstellungen des Repositorys als Code: Merges, Rulesets, Sicherheit, Actions, Environments, Variablen | `.github/repository.toml` und `blueprint.py` |
| **Updates** | jede Woche führt der Blueprint-Bot `copier update` aus und öffnet einen Pull Request | `blueprint-update.yml` |

## Arten von Projekten

| Art | Stack | Prüfungen | Auslieferung |
| --- | --- | --- | --- |
| Home-Assistant-Integration | Python 3.14, pytest-homeassistant-custom-component | Ruff, mypy, Tests, HACS, hassfest | ein Zip-Asset für HACS |
| Nextcloud-App | PHP 8.2, Composer | php-cs-fixer, Psalm, PHPUnit | signiertes Paket in den App Store |
| GitHub Action | Python 3.12 des Runners, Composite Action | Ruff, mypy, Tests, ein Lauf der Action | Release-Tags und ein mitwandernder Major-Tag |
| Python-Paket | Python 3.12, Hatchling | Ruff, mypy, Tests, Build | PyPI, Trusted Publishing |
| Node-Paket | Node 24, TypeScript | tsc, node:test mit voller Abdeckung, Pack | npm mit Provenance |
| Container-Image | Alpine per Digest | Hadolint, Build, Selbsttest | GHCR, Multi-Arch, mit SBOM und Provenance |
| Repository ohne Build | | Textdateien, Shell-Skripte | nur Releases |

Jede Art startet mit einem kleinen, funktionierenden Beispiel samt Tests, das durch den echten Code ersetzt wird.

## Ein Repository anlegen

Copier ab 9.4, Git, die GitHub CLI und ein Checkout des Blueprints (für `blueprint.py`):

```sh
copier copy gh:Dennis-Otto/repo-blueprint mein-projekt
cd mein-projekt
git init && git add --all && git commit --signoff --message "chore: start from the blueprint"
gh repo create Dennis-Otto/mein-projekt --public --source . --push
python3 ../repo-blueprint/blueprint.py settings apply
python3 ../repo-blueprint/blueprint.py checklist
```

Copier fragt nach Name, einer Beschreibung in einem Satz, der Art des Projekts, der Lizenz (MIT, MIT-0, BSD-3-Clause, Apache-2.0, GPL-3.0-or-later oder AGPL-3.0-or-later) und ein paar Details der Art. `settings apply` setzt alles, was die API setzen kann; `checklist` zeigt, was noch eine Person erledigen muss, etwa die Secrets, und welche Schritte schon erledigt sind.

### Einmal pro Repository

- **Die Release-App** öffnet die Release- und Update-Pull-Requests, damit ihre Prüfungen laufen. Installiere sie auf dem Repository und hinterlege ihren privaten Schlüssel als Secret `RELEASE_AUTOMATION_PRIVATE_KEY` im Environment `release`. Die App braucht die Berechtigungen *Contents*, *Pull requests* und *Workflows* (Lesen und Schreiben).
- **Der Issue-Assistent** braucht `CLAUDE_CODE_OAUTH_TOKEN` im Environment `issue-assistant`.
- **Auslieferung:** Trusted Publishing auf PyPI oder npm, das App-Zertifikat einer Nextcloud-App oder die Einreichung bei HACS, wie es die Checkliste sagt.

`checklist` gibt die `gh secret set`-Befehle aus; der Wert wird in die Abfrage der GitHub CLI eingegeben und erscheint nirgends sonst.

## Einstellungen als Code

`.github/repository.toml` enthält die Einstellungen eines Repositorys; `blueprint.py settings check` vergleicht sie mit GitHub, `settings apply` gleicht GitHub an:

- **Repository:** Squash-Merges mit dem Titel des Pull Requests, Auto-Merge, Branch-Updates, gelöschte Branches, Sign-off auch für Commits im Web, kein Wiki, keine Projects.
- **Sicherheit:** unveränderliche Releases, private Meldung von Schwachstellen, Dependabot-Alerts und -Sicherheitsupdates, Secret Scanning mit Push-Schutz.
- **Actions:** standardmäßig nur lesende Tokens, keine Freigaben durch Workflows, Actions nur per Commit-Hash, Freigabe der Workflows jedes externen Beitragenden.
- **Rulesets:** *Protect main* (nur Pull Requests, Squash, lineare Historie, alle Pflichtprüfungen, kein Löschen und kein Force-Push) und *Release tags* (`v*.*.*` bewegt sich nie).
- **Variablen und Environments:** `PUBLISH_TO`, die Release-App und Environments, die nur `main` nutzen darf, mit den Secrets, die sie brauchen.

`blueprint.py` braucht Python 3.12 und die GitHub CLI, angemeldet als Administrator, sonst nichts. Es liest und zeigt nie den Wert eines Secrets.

## Updates

Der Blueprint-Bot (`blueprint-update.yml`) führt jede Woche `copier update` aus. Ohne Konflikte merged sich sein Pull Request selbst, sobald alle Prüfungen grün sind; Konflikte bleiben als Markierungen für den Maintainer darin. Die Repository-Variable `BLUEPRINT_AUTOMERGE` mit dem Wert `off` lässt jedes Update auf den Maintainer warten. Von Hand startet er unter *Actions → Blueprint update*, lokal mit `copier update`.

Dem Blueprint gehören die Workflows, `scripts/check.sh` und die Community-Dateien: ihre Änderungen kommen mit den Updates. Dateien des Projekts werden nie überschrieben: README, Changelog, Manifeste und Lock-Dateien der Abhängigkeiten (die pflegt Dependabot des Projekts), Code und Tests, Labels und akzeptierte Findings. Prüfungen, die nur ein Projekt braucht, gehören in `scripts/check-project.sh`, das `scripts/check.sh` zuletzt ausführt.

## Werkzeuge in jedem Repository

- `bash scripts/check.sh`: die Prüfungen der CI, lokal.
- `bash scripts/social-preview.sh`: rendert `.github/social-preview.html` in das 1280×640-Bild, das GitHub bei Links auf das Repository zeigt; hochladen unter *Settings → Social preview*.

## Wie der Blueprint funktioniert

- `copier.yml` enthält die Fragen. `template/` enthält die Dateien eines neuen Repositorys; ein Datei- oder Ordnername wie `[% if stack == 'php' %]composer.json[% endif %]` trägt seine Bedingung, und ein Name, der leer gerendert wird, entfällt. Die Trennzeichen `{= =}` und `[% %]` kommen in keinem Workflow, Skript oder Manifest vor; so bleiben `${{ }}` von GitHub Actions und `[[ ]]` von Bash und TOML unverändert.
- Die Workflows in `.github/workflows/` laufen in diesem Repository und sind zugleich die Vorlagen der Workflows jedes neuen Repositorys: actionlint prüft sie, und Dependabot hält ihre Actions hier aktuell. Eine Zeile mit *Not in the blueprint itself* schaltet einen Job in diesem Repository ab und fehlt in neuen.
- `stacks/` enthält Manifeste und Lock-Dateien jeder Projektart, die Dependabot aktuell hält; ein neues Projekt startet von ihnen.
- `tests/` prüft `blueprint.py` gegen ein simuliertes GitHub und rendert jede Projektart; der Variants-Workflow rendert jede einzelne und führt ihre eigenen Prüfungen mit den echten Werkzeugen aus.

Beiträge sind willkommen: siehe [CONTRIBUTING.md](CONTRIBUTING.md). Fragen und Probleme: [SUPPORT.md](SUPPORT.md). Schwachstellen bitte vertraulich melden, wie es [SECURITY.md](SECURITY.md) beschreibt.

## Lizenz

[MIT No Attribution](LICENSE): Repositories aus dem Blueprint schulden ihm nichts, nicht einmal einen Hinweis. Jede Datei nennt ihre Lizenz in der maschinenlesbaren Form von [REUSE](https://reuse.software).
