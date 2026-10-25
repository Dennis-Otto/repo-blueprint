# Repo Blueprint

[![Dokumentation](https://img.shields.io/badge/docs-dennis--otto.github.io-526cfe?logo=materialformkdocs&logoColor=white)](https://dennis-otto.github.io/repo-blueprint/de/)
[![CI](https://github.com/Dennis-Otto/repo-blueprint/actions/workflows/ci-python.yml/badge.svg)](https://github.com/Dennis-Otto/repo-blueprint/actions/workflows/ci-python.yml)
[![Varianten](https://github.com/Dennis-Otto/repo-blueprint/actions/workflows/variants.yml/badge.svg)](https://github.com/Dennis-Otto/repo-blueprint/actions/workflows/variants.yml)
[![CodeQL](https://github.com/Dennis-Otto/repo-blueprint/actions/workflows/codeql.yml/badge.svg)](https://github.com/Dennis-Otto/repo-blueprint/actions/workflows/codeql.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/Dennis-Otto/repo-blueprint/badge)](https://scorecard.dev/viewer/?uri=github.com/Dennis-Otto/repo-blueprint)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/15284/badge)](https://www.bestpractices.dev/projects/15284)
[![REUSE](https://api.reuse.software/badge/github.com/Dennis-Otto/repo-blueprint)](https://api.reuse.software/info/github.com/Dennis-Otto/repo-blueprint)
[![Lizenz: MIT-0](https://img.shields.io/badge/license-MIT--0-blue)](https://github.com/Dennis-Otto/repo-blueprint/blob/main/LICENSE)
[![Sponsern](https://img.shields.io/badge/sponsor-%E2%99%A5-db61a2?logo=githubsponsors&logoColor=white)](https://github.com/sponsors/Dennis-Otto)

[English version](https://github.com/Dennis-Otto/repo-blueprint/blob/main/README.md)

<!-- --8<-- [start:pitch] -->

**GitHub-Repositories, die sich selbst testen, veröffentlichen, absichern und aktualisieren — mit einem `copier copy`.**

Repo Blueprint ist eine [Copier](https://copier.readthedocs.io/)-Vorlage für sieben Arten von Projekten: Home-Assistant-Integrationen, Nextcloud-Apps, GitHub Actions, Python- und Node-Pakete, Container-Images und Repositories ohne Build. Ein neues Repository startet mit mehr als 30 Workflows, und ein Bot bringt es auf jede neue Version des Blueprints.

- **Getestet bei jeder Änderung.** `scripts/check.sh` führt dieselben Prüfungen auf deinem Rechner und in der CI aus, mit voller Abdeckung des Codes. Der PR-Coach erklärt jede Prüfung, die scheitert, und der Fix-Bot committet, was ein Befehl beheben kann.
- **Veröffentlicht und signiert von einem Bot.** Der Merge des Release-Pull-Requests veröffentlicht das Release mit seiner SBOM und der signierten Provenance nach SLSA Build Level 3 und prüft es danach so, wie seine Nutzer es können.
- **Sicher ab dem ersten Commit.** CodeQL, OpenSSF Scorecard, ein Secret-Scan und eine Prüfung der Workflows laufen von Anfang an, jede Action ist auf einen Commit-Hash festgelegt, und etwa 90 bis 100 Antworten von OpenSSF Best Practices sind ausgefüllt.
- **Von selbst aktuell.** Renovate aktualisiert die Abhängigkeiten, der Einstellungs-Bot hält die Einstellungen als Code, und der Blueprint-Bot bringt jede Version des Blueprints als Pull Request, den seine Prüfungen testen, bevor er merged; jedes öffentliche Repository, das [mit dem Blueprint gebaut](#mit-dem-blueprint-gebaut) ist, bekommt so jede Version.

<!-- --8<-- [end:pitch] -->

Die [Website des Blueprints](https://dennis-otto.github.io/repo-blueprint/de/) zeigt die Anleitung und eine Seite für jede Gruppe dessen, was ein neues Repository bekommt, auf Deutsch und Englisch, mit [dem Vergleich](https://dennis-otto.github.io/repo-blueprint/de/compare.html) mit anderen Vorlagen, einer Seite für jede Art von Projekt, den Fragen und Antworten, der Fehlerbehebung, der Architektur, der Referenz jeder Frage, Variable und jedes Secrets, der Roadmap, dem Sicherheitsdesign, der Automatisierung, den Entscheidungen und dem Dashboard.

<sub>💛 Wenn dir der Blueprint hilft, kannst du [seine Entwicklung unterstützen](https://github.com/sponsors/Dennis-Otto).</sub>

## Ein Repository anlegen

<!-- --8<-- [start:quick-start] -->

Git, Python ab 3.12, [uv](https://docs.astral.sh/uv/) und die GitHub CLI ab 2.48, angemeldet als Administrator des Kontos oder der Organisation, der das Repository gehören soll (`gh auth login`):

```sh
uvx --from copier==9.19.0 copier copy gh:Dennis-Otto/repo-blueprint mein-projekt
cd mein-projekt
python3 .github/blueprint.py create
```

![copier copy im Terminal: Copier klont den Blueprint und fragt nach dem Namen Paperless Sync, dem Repository, einer Beschreibung, der Art des Projekts, Python-Paket, und dem Eigentümer Dennis-Otto, übernimmt für den Rest die Vorgaben, auch die Release-App, schreibt die Dateien und nennt den einen Befehl danach; das neue Repository hat seine Community-Dateien, seine Prüfungen und seine Workflows, und ein Probelauf von python3 .github/blueprint.py create zeigt die Befehle, die daraus das Repository auf GitHub machen](docs/images/copier-copy.gif)

Mit pipx statt uv lautet die erste Zeile `pipx run --spec copier==9.19.0 copier copy gh:Dennis-Otto/repo-blueprint mein-projekt`, und ein eigenes Copier, Copier ab 9.8, führt `copier copy gh:Dennis-Otto/repo-blueprint mein-projekt` aus; unter Windows startet `py -3` Python statt `python3`. Das Kopieren führt keinen Code des Blueprints aus: Das Template hat keine Tasks, Migrationen oder Jinja-Erweiterungen, also braucht Copier kein `--trust`.

Copier fragt nach Name, einer Beschreibung in einem Satz, der Art des Projekts, dem GitHub-Konto oder der Organisation, der es gehört, der Lizenz (MIT, MIT-0, BSD-3-Clause, Apache-2.0, GPL-3.0-or-later oder AGPL-3.0-or-later), ein paar Details der Art und der Release-App des Eigentümers, die leer bleiben darf, bis die Checkliste sie registriert hat. Die Homepage ist die Website, die der Docs-Workflow auf GitHub Pages veröffentlicht, wenn du keine andere oder keine nennst, und README, About-Box, Issue-Formulare, das Manifest einer Integration und `appinfo/info.xml` einer App verlinken sie; jede Art beginnt mit eigenen Topics, etwa `home-assistant, hacs` für eine Integration, die HACS braucht, um sie aufzulisten. Copier lehnt eine Antwort ab, die eine Datei kaputt machen würde: eine Beschreibung oder einen Namen mit `"""`, `*/`, `]]>` oder einem Backslash, die einen Docstring von Python, einen Kommentar von TypeScript oder das CDATA von `appinfo/info.xml` beenden würden, eine Nextcloud-App-ID, die der App Store nicht nimmt, und Topics, die GitHub nicht nimmt.

`create` macht aus der Kopie das Repository, ohne Checkout des Blueprints: Jede Kopie bringt `blueprint.py` in `.github/` mit. Es nimmt den Eigentümer und den Namen aus den Antworten von Copier, und seine Vorabprüfung (*preflight*) prüft zuerst Python, Git, die GitHub CLI und ihre Anmeldung, den Eigentümer und den Namen; ein Befund mit ✘ hält es an, bevor etwas entsteht, und nennt den Befehl, der ihn behebt. Dann führt `create` `git init --initial-branch=main` aus, committet die Dateien mit Sign-off, legt das Repository mit `gh repo create` an und pusht dorthin, öffentlich, außer du gibst `--private` an ([grün auch bei GitHub Free](docs/faq.de.md#kann-ein-repository-privat-sein-und-was-kostet-es)), wendet dann die Einstellungen als Code an und zeigt die Checkliste: was noch eine Person erledigen muss, etwa die Release-App und die Secrets, und welche Schritte schon erledigt sind. `--dry-run` zeigt die Vorabprüfung und die Befehle und führt keinen aus. Ein Lauf, der mittendrin aufgehört hat, macht dort weiter, wenn du `create` noch einmal startest. Ein Ordner, der zu einem anderen Repository pusht, ist keine neue Kopie, und `create` lehnt ihn ab. Die [Fehlerbehebung](https://dennis-otto.github.io/repo-blueprint/de/troubleshooting.html) erklärt jeden Befund der Vorabprüfung. Jeder Workflow läuft auf `main`, deshalb nennt `settings check` ein Repository, dessen Standard-Branch anders heißt.

<!-- --8<-- [end:quick-start] -->

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/diagrams/how-a-new-repository-starts.de.dark.svg">
  <img src="docs/images/diagrams/how-a-new-repository-starts.de.svg" alt="Wie ein neues Repository beginnt: copier copy schreibt die Dateien des Projekts und führt keinen Code des Blueprints aus. python3 .github/blueprint.py create, das jede Kopie mitbringt, macht den ersten Commit auf dem Branch main mit Sign-off, legt das Repository mit gh repo create an und pusht dorthin, wendet die Einstellungen als Code an und zeigt die Checkliste. Du erledigst die Schritte, die nur eine Person erledigen kann, etwa die Release-App und die Secrets, und dann laufen die Prüfungen und die Bots.">
</picture>

## Mit dem Blueprint gebaut

<!-- --8<-- [start:made-with] -->

Sechs öffentliche Repositories folgen dem Blueprint, jedes mit eigenem Code und den Prüfungen und Bots des Blueprints; jede Version des Blueprints erreicht sie als Pull Request:

- **[HomeDarts for Autodarts](https://github.com/Dennis-Otto/homedarts-for-autodarts)**, eine Home-Assistant-Integration: lokale Steuerung des Boards in Echtzeit, Spiele, Turniere und Statistiken, ohne Cloud-Konto. [![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/Dennis-Otto/homedarts-for-autodarts/badge)](https://scorecard.dev/viewer/?uri=github.com/Dennis-Otto/homedarts-for-autodarts)
- **[Player Switch for Autodarts](https://github.com/Dennis-Otto/player-switch-for-autodarts)**, eine Chrome-Erweiterung in TypeScript: ein gemeinsames Autodarts-Display, an dem jeder unter seinem eigenen Konto spielt und ein Tipp auf eine Kachel den Spieler wechselt, ohne neue Anmeldung. [![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/Dennis-Otto/player-switch-for-autodarts/badge)](https://scorecard.dev/viewer/?uri=github.com/Dennis-Otto/player-switch-for-autodarts)
- **[Issue-Assistent](https://github.com/Dennis-Otto/issue-assistant)**, eine GitHub Action: eine erste Analyse jedes neuen Issues durch eine KI, die nur liest, geprüft von einem Job ohne KI, bevor sie erscheint. [![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/Dennis-Otto/issue-assistant/badge)](https://scorecard.dev/viewer/?uri=github.com/Dennis-Otto/issue-assistant)
- **[Paperless Sync](https://github.com/Dennis-Otto/paperless-sync)**, eine Nextcloud-App: die Dokumente von Paperless-ngx in Nextcloud Files, nach Korrespondent, Typ und Jahr. [![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/Dennis-Otto/paperless-sync/badge)](https://scorecard.dev/viewer/?uri=github.com/Dennis-Otto/paperless-sync)
- **[Paperless Unified Search](https://github.com/Dennis-Otto/paperless-unified-search)**, eine Nextcloud-App: die Volltextsuche von Paperless-ngx in der Suche von Nextcloud. [![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/Dennis-Otto/paperless-unified-search/badge)](https://scorecard.dev/viewer/?uri=github.com/Dennis-Otto/paperless-unified-search)
- **[dennis-otto.github.io](https://github.com/Dennis-Otto/dennis-otto.github.io)**, ein Repository ohne Build: die Website mit jedem Projekt seines Eigentümers. [![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/Dennis-Otto/dennis-otto.github.io/badge)](https://scorecard.dev/viewer/?uri=github.com/Dennis-Otto/dennis-otto.github.io)

[Das Dashboard](https://dennis-otto.github.io/repo-blueprint/dashboard/) zeigt jedes davon auf einen Blick: die Version des Blueprints, auf der es ist, seine Prüfungen, seine Releases und seine Scorecard.

<!-- --8<-- [end:made-with] -->

## Warum Repo Blueprint

<!-- --8<-- [start:why] -->

- **Statt eines Template-Repositorys von GitHub:** *Use this template* kopiert die Dateien einmal, ohne die Einstellungen, und später folgt nichts. Der Blueprint setzt die Rulesets, die Sicherheit und die Environments als Code und bringt jede Verbesserung als Pull Request.
- **Statt Cookiecutter und cruft:** Die Hooks einer Cookiecutter-Vorlage führen Code auf deinem Rechner aus, und `cruft update` wartet, bis jemand es startet. Copier führt keinen Code des Blueprints aus, also braucht es kein `--trust`; `blueprint.py create`, das du danach startest, ist eine Datei der Kopie, die du vorher lesen kannst. Und der Bot des Blueprints aktualisiert jedes Repository von selbst.
- **Statt einer anderen Copier-Vorlage,** etwa copier-uv oder scientific-python/cookie, die Python-Projekten gut dienen: Der Blueprint bringt einen Standard auch zu Home Assistant, Nextcloud, GitHub Actions, Node und Containern, mit signierten Releases nach SLSA Build Level 3, SBOMs und VEX, und testet jede Version an jeder Art und an den echten Repositories, bevor sie ausrollt.
- **Statt projen:** projen schreibt die Dateien eines Projekts aus Code, der bei jeder Synthese läuft, vor allem für TypeScript, AWS CDK und jsii. Der Blueprint braucht keinen eigenen Code im Projekt: Er hält seine eigenen Dateien aktuell und lässt dir die des Projekts.

[Der Vergleich](https://dennis-otto.github.io/repo-blueprint/de/compare.html) stellt sie nebeneinander, auch dort, wo ein anderes Werkzeug besser passt.

<!-- --8<-- [end:why] -->

## Arten von Projekten

<!-- --8<-- [start:kinds] -->

| Art | Stack | Prüfungen | Auslieferung |
| --- | --- | --- | --- |
| [Home-Assistant-Integration](https://dennis-otto.github.io/repo-blueprint/de/kinds/home-assistant.html) | Python 3.14, pytest-homeassistant-custom-component | Ruff, mypy, Tests, HACS, hassfest | ein Zip-Asset für HACS, geprüft, wie HACS es installiert |
| [Nextcloud-App](https://dennis-otto.github.io/repo-blueprint/de/kinds/nextcloud-app.html) | PHP 8.2 und neuer, die Werkzeuge auf PHP 8.3, Composer | php-cs-fixer, Psalm mit seiner Taint-Analyse, der Code und seine Pakete auf PHP 8.2, PHPUnit in zufälliger Reihenfolge mit jeder Zeile abgedeckt | signiertes Paket in den App Store |
| [GitHub Action](https://dennis-otto.github.io/repo-blueprint/de/kinds/github-action.html) | Python 3.12 des Runners, Composite Action | Ruff, mypy, Tests, ein Lauf der Action | Release-Tags und ein mitwandernder Major-Tag |
| [Python-Paket](https://dennis-otto.github.io/repo-blueprint/de/kinds/python-package.html) | Python 3.12, Hatchling | Ruff, mypy, Tests, Build | PyPI, Trusted Publishing |
| [Node-Paket](https://dennis-otto.github.io/repo-blueprint/de/kinds/node-package.html) | Node 24, TypeScript | Biome für Lint und Format, tsc, node:test mit voller Abdeckung und ihrem Bericht im PR-Coach, Pack; npm installiert ohne die Skripte der Pakete | npm mit Provenance |
| [Container-Image](https://dennis-otto.github.io/repo-blueprint/de/kinds/container.html) | Alpine per Digest | Hadolint, Build, Selbsttest | GHCR, Multi-Arch, mit SBOM und Provenance |
| [Repository ohne Build](https://dennis-otto.github.io/repo-blueprint/de/kinds/generic.html) | | Textdateien, Shell-Skripte | nur Releases |

Jede Art startet mit einem kleinen, funktionierenden Beispiel samt Tests, das durch den echten Code ersetzt wird. Jede Art hat eine eigene Seite auf der Website: was sie bekommt, die Prüfungen, die ihre Pull Requests brauchen, ihre Auslieferung, die Schritte ihrer Checkliste und die eine Zeile, die sie kopiert.

<!-- --8<-- [end:kinds] -->

![Repo Blueprint für GitHub-Repositories: sieben Arten von Projekten mit einem Standard und ein Terminal, in dem copier copy nach der Art des Projekts fragt, die Prüfungen und Bots ankommen, blueprint.py settings apply die Rulesets, Environments und Labels setzt und copier update jeder neuen Version folgt](docs/images/social-preview.webp)

## Wie sich ein Repository selbst pflegt

<!-- --8<-- [start:loop] -->

Jede Änderung, deine oder die eines Bots, ist ein Pull Request, der merged, sobald alle Prüfungen grün sind, und der Release-Bot macht aus dem, was auf `main` ankommt, ein signiertes Release; drei Bots halten das Repository von selbst aktuell. In den Bildern ist Blau der Blueprint mit seinen Bots, Orange bist du mit allem, was dir gehört, und Grün ist das Ergebnis.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/diagrams/how-a-repository-looks-after-itself.de.dark.svg">
  <img src="docs/images/diagrams/how-a-repository-looks-after-itself.de.svg" alt="Wie sich ein Repository selbst pflegt: copier copy legt aus dem Blueprint ein Repository an. Jede Änderung, deine oder die eines Bots, ist ein Pull Request, der merged, sobald alle Prüfungen grün sind, und der Release-Bot macht aus dem, was auf main ankommt, ein signiertes Release. Renovate, der Blueprint-Bot und der Settings-Bot halten das Repository von selbst aktuell.">
</picture>

Die Website jedes Repositorys zeigt das alles auf der Seite *Automatisierung*, die sie bei jedem Build aus den Workflows schreibt: was jeder tut und was ihn startet, welche Prüfungen ein Pull Request braucht und welche Workflows ein Secret halten.

<!-- --8<-- [end:loop] -->

## Was ein neues Repository bekommt

Jede Gruppe hat eine eigene Seite, mit dem, was läuft, den Dateien, die es ausführen, und den Einzelheiten.

### [Prüfungen und der PR-Coach](docs/features/checks.de.md)

- **Prüfungen:** `scripts/check.sh` führt die Tests mit voller Abdeckung, die Typen, das Lint und das Packen aus, lokal wie in der CI.
- **Lint:** Die Workflows, die Lizenz jeder Datei, das Markdown, und die Rechtschreibung und der Stil der geänderten Dokumente.
- **Abdeckung:** Der Bericht eines Pull Requests vergleicht die Abdeckung jeder Datei mit der von `main`.
- **Schnelle Prüfungen:** Ein Scanner läuft nur in den Pull Requests, die ändern, was er liest, und die übrigen Scans jede Woche.
- **PR-Coach:** Jede Prüfung, die scheitert, sagt, was sie gefunden hat, warum das wichtig ist und wie man es behebt, in einem Kommentar, der jedem Push folgt, auch bei Forks.

### [Fix-Bot und Selbstheilung](docs/features/self-healing.de.md)

- **Fix-Bot:** Eine Prüfung, die scheitert, behebt, was ein Befehl beheben kann, etwa das Format des Codes, und committet es auf den Branch.
- **Wackelige Tests:** Gescheiterte Test-Jobs laufen noch einmal, und ein Job, der dann besteht, wird in einem Issue gemeldet.
- **Abgebrochene Prüfungen:** Eine Pflichtprüfung, die ein später Lauf für einen älteren Commit abgebrochen hat, startet von selbst neu.
- **Gescheiterte Releases:** Das Release eines Merges, das für einen Moment scheitert, führt seine gescheiterten Jobs noch einmal aus.
- **Zustand der Bots:** Ein Bot, der auf `main` fehlschlägt, versucht es noch einmal, wo das helfen kann, und hält sonst ein Issue pro Workflow offen.

### [Mutationstests, Fuzzing und Property-Tests](docs/features/tests.de.md)

- **Mutationstests:** Jede Woche zeigen Tausende kleine Änderungen des Codes, welche davon die Tests nicht bemerken.
- **Fuzzing:** Ein Python-Paket oder eine GitHub Action fuzzt jedes Ziel in `fuzz/`, in Pull Requests und jede Woche.
- **Property-Tests:** Die Property-Tests von Python- und Home-Assistant-Projekten laufen jede Nacht mit neuen zufälligen Eingaben.

### [Releases und Sicherheit](docs/features/releases.de.md)

- **Releases:** Ein Pull Request mit der nächsten Version und ihrem Changelog, und signierte Releases mit Provenance und SBOMs.
- **Sicherheit:** CodeQL, OpenSSF Scorecard, die Prüfung der Abhängigkeiten und die Scanner jeder Art von Projekt.
- **App Store:** Eine Nextcloud-App registriert ihre ID mit ihrem Zertifikat, einmal, von Hand.

### [Abhängigkeiten und Updates](docs/features/updates.de.md)

- **Abhängigkeiten:** Renovate aktualisiert die Abhängigkeiten ein paar Mal am Tag, als Release-App des Eigentümers.
- **Updates:** Direkt nach jedem Release des Blueprints, und jede Woche, öffnet der Blueprint-Bot einen Pull Request mit `copier update`.
- **Upstream:** Eine Nextcloud-App bekommt einen Pull Request, der `max-version` anhebt, sobald eine neue Hauptversion von Nextcloud jede Prüfung besteht.

### [Bots, ihre Kosten und das Dashboard](docs/features/bots.de.md)

- **Issues:** Der Issue-Assistent, eine KI, die nur liest, analysiert jedes neue Issue, labelt es und findet Duplikate.
- **Willkommen:** Der erste Pull Request einer Person bekommt einen Kommentar mit dem, was ihm weiterhilft.
- **Bereichs-Labels:** Jeder Pull Request bekommt die Labels der Bereiche, deren Dateien er ändert.
- **Branches:** Der Branch-Bot bringt die Pull Requests, die auf Auto-Merge warten, einen nach dem anderen auf den Stand von `main`.
- **Aufräumen:** Jede Woche verschwinden die gemergten Branches und die Caches geschlossener Pull Requests.
- **Dashboard:** Eine Seite zeigt jedes Repository des Eigentümers, das Release des Blueprints, auf dem es steht, und den Zustand seiner Prüfungen.

### [Website, Diagramme und Screenshots](docs/features/website.de.md)

- **Website:** Die Dokumentation in `docs/` als Website mit Suche und einem hellen und einem dunklen Theme, auf Deutsch und Englisch.
- **Diagramme:** Jedes Diagramm ist ein Bild seiner Mermaid-Quelle, damit auch die GitHub-App es zeigt.
- **Screenshots:** Ein Bot erneuert die Bilder des Projekts, nur wenn sich ihre Pixel ändern.

### [Einstellungen als Code](docs/features/settings.de.md)

- **Einstellungen:** Merges, Rulesets, Sicherheit, Actions, Umgebungen, Variablen und Labels in `.github/repository.toml`, die der Settings-Bot anwendet.

### [Community und Entwicklung](docs/features/development.de.md)

- **Community:** README, Leitfaden für Beiträge, Verhaltenskodex, Sicherheitsrichtlinie und das Sicherheitsdesign der Software.
- **Entwicklung:** Ein Dev-Container für VS Code und Codespaces, und ein Hook, der die Prüfungen vor jedem Push ausführt.
- **Coding-Agents:** Die Regeln des Repositorys für Claude Code, Codex, GitHub Copilot und Cursor, in `AGENTS.md`.
- **Werkzeuge:** `scripts/check.sh`, `scripts/diagrams.sh` und `scripts/social-preview.sh`, in jedem Repository dieselben.

## Ein Repository einrichten

Was eine Person einmal tut: die Release-App des Kontos und ihre Vorgaben, die Secrets und die Auslieferung jedes Repositorys, und wie ein bestehendes Repository den Blueprint übernimmt. [Die Anleitung](https://dennis-otto.github.io/repo-blueprint/de/guide.html#ein-repository-einrichten) führt durch jeden Schritt.

## Wie der Blueprint funktioniert

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/diagrams/the-path-of-a-release.de.dark.svg">
  <img src="docs/images/diagrams/the-path-of-a-release.de.svg" alt="Der Weg eines Releases des Blueprints: Ein Pull Request wird in main des Blueprints gemergt, und der Release-Workflow hält den Release-Pull-Request mit der nächsten Version. Sein Merge, durch den Maintainer oder von selbst, wenn er nur Updates enthält, veröffentlicht das Release mit einem signierten Tag und prüft es. Der Rollout-Workflow startet dann den Blueprint-Bot jedes Repositorys, das den Blueprint übernimmt. Jeder Bot prüft das Release, führt copier update aus und hält einen Update-Pull-Request als Release-App, damit die Prüfungen des Repositorys laufen. Ohne Konflikte merged er sich selbst, sobald sie bestehen; mit Konflikten oder mit BLUEPRINT_AUTOMERGE auf off wartet er auf den Maintainer. Das Dashboard zeigt das Release des Blueprints, auf dem jedes Repository steht.">
</picture>

[Die Architektur](https://dennis-otto.github.io/repo-blueprint/de/architecture.html) zeigt, wie der Blueprint aufgebaut ist, von `copier.yml` und `template/` bis zu den Workflows, die er mit jedem Repository teilt, und den Tests, die jede Änderung an jeder Art von Projekt ausprobieren, und den Weg eines Releases von einem Merge bis zum Update jedes Repositorys. Die Referenz beschreibt [jede Frage von Copier](https://dennis-otto.github.io/repo-blueprint/de/reference/questions.html) und [jede Variable und jedes Secret](https://dennis-otto.github.io/repo-blueprint/de/reference/variables.html) (englisch), geschrieben von `reference.py` aus den Quellen, die sie beschreiben, sodass sie nicht abweichen können. Wenn etwas unklar ist oder nicht funktioniert, helfen [die Fragen und Antworten](https://dennis-otto.github.io/repo-blueprint/de/faq.html) und [die Fehlerbehebung](https://dennis-otto.github.io/repo-blueprint/de/troubleshooting.html).

Wohin sich der Blueprint entwickelt: [die Roadmap](https://github.com/Dennis-Otto/repo-blueprint/blob/main/docs/roadmap.md) (englisch). Was er schützt und wem er vertraut: [sein Sicherheitsdesign](https://github.com/Dennis-Otto/repo-blueprint/blob/main/docs/security.md) (englisch).

Beiträge sind willkommen: siehe [CONTRIBUTING.md](https://github.com/Dennis-Otto/repo-blueprint/blob/main/CONTRIBUTING.md). Fragen und Probleme: [SUPPORT.md](https://github.com/Dennis-Otto/repo-blueprint/blob/main/SUPPORT.md). Schwachstellen bitte vertraulich melden, wie es [SECURITY.md](https://github.com/Dennis-Otto/repo-blueprint/blob/main/SECURITY.md) beschreibt.

## Lizenz

[MIT No Attribution](https://github.com/Dennis-Otto/repo-blueprint/blob/main/LICENSE): Repositories aus dem Blueprint schulden ihm nichts, nicht einmal einen Hinweis. Jede Datei nennt ihre Lizenz in der maschinenlesbaren Form von [REUSE](https://reuse.software).
