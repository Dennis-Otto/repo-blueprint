# Community und Entwicklung

Die Dateien der Community, der Dev-Container und die Regeln für Coding-Agents.

## Community

README, Beitragsleitfaden mit den Coding-Standards und der Regel, dass jede Änderung ihre Tests mitbringt, Verhaltenskodex, Sicherheitsrichtlinie mit der Prüfung eines Releases und einem Assurance Case, das Sicherheitsdesign der Software (`docs/security.md`), Support, Governance mit den Rollen und dem Fortbestand des Projekts, Issue-Formulare, Pull-Request-Vorlage, Aufzeichnungen der Entscheidungen, die das Projekt prägen (`docs/decisions/`), Discussions mit Formularen für Fragen und Ideen und einer Ankündigung jedes Releases, Sponsor-Button, Social Preview.

**Womit:** .

## Entwicklung

Ein Dev-Container für VS Code und GitHub Codespaces mit den Werkzeugen der Prüfungen und der Website, und ein Hook, der sie vor jedem Push ausführt, unter Linux, macOS und Windows: `scripts/check.sh` schlägt fehl, wenn Git ihn überspringen würde.

**Womit:** `.devcontainer/`, `.githooks/pre-push`.

## Coding-Agents

Die Regeln des Repositorys für Claude Code, Codex, GitHub Copilot und Cursor: die Befehle der Prüfungen und Tests seiner Art, die Titel von Pull Requests und die Versionen, die sie ergeben, das Changelog, das Sign-off, und welche Dateien dem Projekt gehören und welche dem Blueprint, eine Liste, die ein Test des Blueprints gleich den Dateien hält, die ein Update nie überschreibt; die Notizen des Projekts kommen aus einer eigenen Datei dazu.

**Womit:** `AGENTS.md`, `CLAUDE.md`, `.github/agents.project.md`.

## Werkzeuge in jedem Repository

- `bash scripts/check.sh`: die Prüfungen der CI, lokal.
- `bash scripts/diagrams.sh`: zeichnet jedes Diagramm aus `docs/diagrams/`, das eine Seite zeigt, als seine Bilder in `docs/images/diagrams/`, mit Docker, und lässt die anderen Quellen, wie sie sind; `--extract` macht vorher aus jedem `mermaid`-Block des Markdowns eine Quelle und ihr Bild und schreibt das `alt` jedes Bildes aus seiner Quelle, und `--check` prüft ohne Docker, was `scripts/check.sh` prüft.
- `bash scripts/social-preview.sh`: rendert `.github/social-preview.html` in das 1280×640-Bild, das GitHub bei Links auf das Repository zeigt; hochladen unter *Settings → Social preview*.
