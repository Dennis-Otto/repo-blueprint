---
# The title of the page and of the preview card of a link to it, which said Home.
title: Repositories, die sich selbst pflegen
hide:
  - navigation
  - toc
---

# Repo Blueprint

Eine [Copier](https://copier.readthedocs.io/)-Vorlage für GitHub-Repositories, die sich selbst pflegen: Tests bei jeder Änderung, ein Release-Bot, Sicherheitsprüfungen, ein Issue-Assistent und die Einstellungen des Repositorys als Code, für sieben Arten von Projekten, und ein Bot hält sie mit jeder neuen Version des Blueprints aktuell.

[Ein Repository anlegen](#ein-repository-anlegen){ .md-button .md-button--primary }
[Zur Anleitung](guide.md){ .md-button }

![Die Social Preview des Blueprints: sieben Arten von Projekten mit einem Standard und ein Terminal, in dem copier copy nach der Art des Projekts fragt, die Prüfungen und Bots ankommen, blueprint.py settings apply die Rulesets, Environments und Labels setzt und copier update jeder neuen Version folgt](images/social-preview.webp)

## Wie sich ein Repository selbst pflegt

--8<-- "README.de.md:loop"

## Was ein neues Repository bekommt

<div class="grid cards" markdown>

- :material-check-all:{ .lg .middle } **Prüfungen**

    ---

    `scripts/check.sh` bei jeder Änderung, lokal wie in der CI: Tests mit voller Abdeckung, in Python-Projekten auf jedem Kern, Typen, Lint und Paketbau. Dazu werden die Workflows, die Lizenz jeder Datei, das Markdown, der Sign-off jedes Commits und der Titel jedes Pull Requests geprüft. Ein vorübergehender Fehler eines Downloads lässt keinen Lauf scheitern: Jeder Download versucht es erneut.

- :material-lightbulb-on-outline:{ .lg .middle } **PR-Coach**

    ---

    Jede Prüfung, die scheitert, sagt, was sie gefunden hat, warum das wichtig ist und wie man es behebt, mit den Befehlen dafür: in der Prüfung und in einem Kommentar am Pull Request, der jedem Push folgt, auch an einem Pull Request aus einem Fork. Was ein Befehl beheben kann, behebt der Pull Request selbst: Der Fix-Bot committet es, schlägt es an einem Fork vor und hält `main` repariert.

- :material-shield-lock-outline:{ .lg .middle } **Sicherheit**

    ---

    CodeQL, die Taint-Analyse von Psalm für das PHP einer Nextcloud-App, OpenSSF Scorecard, Dependency Review, Secret Scan, SBOMs dessen, was jedes Release ausliefert, die Sicherheitsprüfung der Workflows und jede Lock-Datei gegen die OSV-Datenbank. Jede Action ist auf einen Commit-Hash gepinnt.

- :material-rocket-launch-outline:{ .lg .middle } **Releases**

    ---

    Ein Pull Request mit der nächsten Version, bestimmt aus den Titeln der gemergten Pull Requests, und dem Changelog als Notes. Sein Merge veröffentlicht das Release mit Paket, SBOM und signierter Provenance (SLSA Build Level 3) und prüft es so, wie es seine Nutzer können.

- :material-package-up:{ .lg .middle } **Abhängigkeiten**

    ---

    Renovate, das der Blueprint mehrmals am Tag ausführt: Actions, Abhängigkeiten und Images eine Woche nach ihrem Release, montags, sofort ein Update, das eine Schwachstelle behebt, oder den neuen Commit eines Branches, dem eine Action folgt. Routine-Updates mergen sich selbst, sobald alle Prüfungen grün sind; die wöchentliche Auffrischung jeder Lock-Datei wartet auf den Maintainer. Das Issue *Dependency dashboard* listet jedes Update, das wartet oder fehlschlug.

- :material-robot-outline:{ .lg .middle } **Issues**

    ---

    Der [Issue-Assistent](https://github.com/Dennis-Otto/issue-assistant): eine erste Analyse jedes neuen Issues durch eine KI, die nur liest, Labels, Duplikate, Erinnerungen und das Schließen mit dem Release, das den Fix enthält. Jedes neue Release des Assistenten kommt von selbst in jedes Repository, sobald ein Bot geprüft hat, dass sein Release-Workflow es gebaut hat. Ein Bot, der auf `main` fehlschlägt, öffnet ein eigenes Issue, das sich schließt, sobald der Bot wieder besteht.

- :material-web:{ .lg .middle } **Website**

    ---

    Die Dokumentation aus `docs/` als Website mit Suche und hellem und dunklem Design, auf Englisch und Deutsch. Jeder Pull Request baut sie streng, jede Änderung an `main` veröffentlicht sie auf GitHub Pages.

- :material-sitemap-outline:{ .lg .middle } **Diagramme**

    ---

    Jedes Diagramm als Bild, das alle sehen, auch in der GitHub-App und in den Stores, gezeichnet aus seiner Mermaid-Quelle; die Website zeichnet die Quelle live. Die Bots reparieren sie selbst: im Pull Request, auf `main` und nach einem Update des Renderers.

- :material-camera-outline:{ .lg .middle } **Screenshots**

    ---

    Die Bilder des Projekts erneuern sich selbst: Nach einer Änderung dessen, was sie zeigen, nach jedem Release und jede Woche führt der Screenshot-Bot `scripts/screenshots.sh` aus und hält einen Pull Request mit den Bildern, deren Pixel sich geändert haben, der sich selbst merged.

- :material-cog-outline:{ .lg .middle } **Einstellungen als Code**

    ---

    Merges, Rulesets, Sicherheit, Actions, Environments, Variablen, Labels und GitHub Pages in `.github/repository.toml`. Der Settings-Bot wendet sie nach jeder Änderung und jede Woche an.

- :material-update:{ .lg .middle } **Updates**

    ---

    Nach jedem Release und jede Woche prüft der Blueprint-Bot das Release, das unveränderlich und vom Release-Workflow des Blueprints signiert sein muss, führt dann `copier update` aus und hält einen Pull Request aktuell. Ohne Konflikte merged er sich selbst, sobald alle Prüfungen grün sind; die Dateien des Projekts und deine Commits auf seinem Branch werden nie überschrieben.

- :material-account-group-outline:{ .lg .middle } **Community**

    ---

    README, Beitragsleitfaden, Verhaltenskodex, Sicherheitsrichtlinie und Sicherheitsdesign, Governance, Issue-Formulare, Aufzeichnungen der Entscheidungen und Discussions mit einer Ankündigung jedes Releases.

- :material-head-cog-outline:{ .lg .middle } **Coding-Agents**

    ---

    `AGENTS.md` gibt Claude Code, Codex, GitHub Copilot und Cursor die Befehle, die Regeln für Pull Requests und das Changelog, und welche Dateien dem Projekt gehören und welche dem Blueprint. Die Notizen des Projekts kommen aus `.github/agents.project.md` dazu.

</div>

Die [Anleitung](guide.md#was-ein-neues-repository-bekommt) nennt jeden Bereich, auch den PR-Coach, die Abdeckung jedes Pull Requests, Mutationstests, wackelige Tests, abgebrochene Prüfungen, gescheiterte Releases, das Aufräumen und den Dev-Container.

## Arten von Projekten

<div class="grid cards" markdown>

- :material-home-assistant:{ .lg .middle } **Home-Assistant-Integration**

    ---

    Ruff, mypy, Tests, HACS und hassfest; ein Zip-Asset für HACS.

- :simple-nextcloud:{ .lg .middle } **Nextcloud-App**

    ---

    php-cs-fixer, Psalm mit seiner Taint-Analyse und PHPUnit in zufälliger Reihenfolge mit jeder Zeile abgedeckt, die Werkzeuge auf PHP 8.3 und der Code auch auf PHP 8.2; ein signiertes Paket für den App Store.

- :simple-githubactions:{ .lg .middle } **GitHub Action**

    ---

    Eine Composite Action mit Ruff, mypy, Tests und einem Lauf der Action; Release-Tags und ein mitwandernder Major-Tag.

- :material-language-python:{ .lg .middle } **Python-Paket**

    ---

    Ruff, mypy, Tests und ein Build mit Hatchling; PyPI mit Trusted Publishing.

- :material-nodejs:{ .lg .middle } **Node-Paket**

    ---

    TypeScript, tsc und node:test mit voller Abdeckung; npm mit Provenance.

- :material-docker:{ .lg .middle } **Container-Image**

    ---

    Alpine per Digest, Hadolint, ein Build und ein Selbsttest; GHCR, Multi-Arch, mit SBOM und Provenance.

</div>

Ein Repository ohne Build prüft seine Textdateien und Shell-Skripte und macht nur Releases. Jede Art startet mit einem kleinen, funktionierenden Beispiel samt Tests, das durch den echten Code ersetzt wird. Die [Anleitung](guide.md#arten-von-projekten) nennt den Stack jeder Art.

## Ein Repository anlegen

--8<-- "README.de.md:quick-start"

Die Anleitung beschreibt, was jedes Repository [einmal](guide.md#einmal-pro-repository) braucht, etwa die Release-App, und wie [ein bestehendes Repository](guide.md#ein-bestehendes-repository) den Blueprint übernimmt.

## Mehr erfahren

<div class="grid cards" markdown>

- :material-book-open-variant:{ .lg .middle } **Anleitung**

    ---

    Alles, was ein neues Repository bekommt, die Einstellungen als Code, die Updates und was einem Projekt gehört.

    [:octicons-arrow-right-24: Zur Anleitung](guide.md)

- :material-map-marker-path:{ .lg .middle } **Roadmap**

    ---

    Wohin sich der Blueprint in den nächsten zwölf Monaten entwickelt und was er nicht tun wird, auf Englisch.

    [:octicons-arrow-right-24: Roadmap](roadmap.md)

- :material-shield-search:{ .lg .middle } **Sicherheitsdesign**

    ---

    Was der Blueprint schützt, wem er vertraut, die Bedrohungen mit ihren Gegenmaßnahmen und die verbleibenden Risiken, auf Englisch.

    [:octicons-arrow-right-24: Sicherheitsdesign](security.md)

- :material-scale-balance:{ .lg .middle } **Entscheidungen**

    ---

    Die Entscheidungen, die den Blueprint prägen, jede mit ihren Gründen, auf Englisch.

    [:octicons-arrow-right-24: Entscheidungen](decisions/README.md)

- :material-history:{ .lg .middle } **Releases und Änderungen**

    ---

    Jedes Release mit seinen Notes auf GitHub und die Änderungen jeder Version, auf Englisch.

    [:octicons-arrow-right-24: Releases](https://github.com/Dennis-Otto/repo-blueprint/releases) · [Änderungen](changelog.md)

- :material-view-dashboard-outline:{ .lg .middle } **Dashboard**

    ---

    Jedes öffentliche Repository des Besitzers auf einen Blick: das Release des Blueprints, auf dem es steht, seine Releases, Pull Requests, Workflow-Läufe, Scorecard und Gesundheit.

    [:octicons-arrow-right-24: Dashboard](https://dennis-otto.github.io/repo-blueprint/dashboard/)

</div>
