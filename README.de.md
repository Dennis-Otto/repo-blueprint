# Repo Blueprint

[![Dokumentation](https://img.shields.io/badge/docs-dennis--otto.github.io-526cfe?logo=materialformkdocs&logoColor=white)](https://dennis-otto.github.io/repo-blueprint/)

[English version](https://github.com/Dennis-Otto/repo-blueprint/blob/main/README.md)

![Repo Blueprint für GitHub-Repositories: sieben Arten von Projekten mit einem Standard und ein Terminal, in dem copier copy nach der Art des Projekts fragt, die Prüfungen und Bots ankommen, blueprint.py settings apply die Rulesets, Environments und Labels setzt und copier update jeder neuen Version folgt](https://raw.githubusercontent.com/Dennis-Otto/repo-blueprint/main/.github/social-preview.png)

Eine [Copier](https://copier.readthedocs.io/)-Vorlage für GitHub-Repositories, die sich selbst pflegen: Tests bei jeder Änderung, ein Release-Bot, Sicherheitsprüfungen, ein Issue-Assistent und die Einstellungen des Repositorys als Code, für sieben Arten von Projekten. Ein Bot bringt jedes Repository, das aus der Vorlage entstanden ist, auf jede neue Version des Blueprints.

Die [Website des Blueprints](https://dennis-otto.github.io/repo-blueprint/de/) zeigt diese Anleitung auf Deutsch und Englisch, zusammen mit der Roadmap, dem Sicherheitsdesign, den Entscheidungen und dem Dashboard.

<sub>💛 Wenn dir der Blueprint hilft, kannst du [seine Entwicklung unterstützen](https://github.com/sponsors/Dennis-Otto).</sub>

## Wie sich ein Repository selbst pflegt

<!-- --8<-- [start:loop] -->

Jede Änderung, deine oder die eines Bots, ist ein Pull Request, der merged, sobald alle Prüfungen grün sind, und der Release-Bot macht aus dem, was auf `main` ankommt, ein signiertes Release; drei Bots halten das Repository von selbst aktuell. In den Bildern ist Blau der Blueprint mit seinen Bots, Orange bist du mit allem, was dir gehört, und Grün ist das Ergebnis.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/diagrams/how-a-repository-looks-after-itself.de.dark.svg">
  <img src="docs/images/diagrams/how-a-repository-looks-after-itself.de.svg" alt="Wie sich ein Repository selbst pflegt: copier copy legt aus dem Blueprint ein Repository an. Jede Änderung, deine oder die eines Bots, ist ein Pull Request, der merged, sobald alle Prüfungen grün sind, und der Release-Bot macht aus dem, was auf main ankommt, ein signiertes Release. Renovate, der Blueprint-Bot und der Settings-Bot halten das Repository von selbst aktuell.">
</picture>

<!-- --8<-- [end:loop] -->

## Was ein neues Repository bekommt

| Bereich | Was läuft | Womit |
| --- | --- | --- |
| **Prüfungen** | `scripts/check.sh` bei jeder Änderung, lokal wie in der CI: Tests mit voller Abdeckung, Typen, Lint, Paketbau; ein vorübergehender Fehler eines Downloads lässt keinen Lauf scheitern, weil jeder Download der Workflows es erneut versucht; die CI hält die Pakete von Composer, pip und npm und krankerl in ihrem Cache, php-cs-fixer prüft nur die geänderten Dateien, und Psalm liest den Code einer Nextcloud-App und was er nutzt, nicht ganz `vendor/` | die Werkzeuge der jeweiligen Projektart, per Hash gepinnt |
| **Lint** | Workflows (actionlint), Lizenz jeder Datei (REUSE), das Markdown jedes Dokuments (markdownlint), Hinweise zur Rechtschreibung auf Englisch und Deutsch (cspell) und zum Stil des Englischen (Vale) der geänderten Dokumente, Sign-off jedes Commits (DCO), Titel jedes Pull Requests (Conventional Commits), ein Eintrag im Changelog für jede Änderung für Nutzer, ein Fragment in `changelog.d/` oder eine Zeile unter *Unreleased*, geprüft so, wie das Release ihn übernimmt | `lint.yml`, `pull-request-title.yml` |
| **Sicherheit** | CodeQL, OpenSSF Scorecard, Dependency Review, Secret Scan, SBOMs als SPDX und CycloneDX, OpenVEX, schlüssellos signierte und vor jedem Build geprüfte Release-Tags (gitsign), Findings-Wächter, die Sicherheitsprüfung der Workflows (zizmor), jede Lock-Datei gegen die OSV-Datenbank (OSV-Scanner), der Netzwerkverkehr jedes Jobs (Harden-Runner) | jede Action auf einen Commit-Hash gepinnt |
| **Releases** | ein Pull Request mit der nächsten Version, bestimmt aus den Titeln der gemergten Pull Requests (`fix` ein Patch, `feat` ein Minor, `!` ein Major), und dem Text der Fragmente in `changelog.d/` und von *Unreleased* im Changelog als Notes; sein Merge veröffentlicht das Release mit Paket, SBOM und der signierten Provenance eines isolierten Builds (SLSA Build Level 3), liefert es aus und prüft es danach so, wie es seine Nutzer können, auch jede Woche; wo die Repository-Variable `BETA_CHANNEL` auf true steht, wird außerdem jede Änderung für Nutzer zu einer Beta des nächsten Releases, einem Prerelease für Tester | release-please, die Release-App, unveränderliche Releases, `verify-release.yml` |
| **Abhängigkeiten** | Renovate, das der Blueprint alle zwei Stunden für jedes Repository als Release-App ausführt: Actions, Abhängigkeiten, Images und die Pins der Workflows, eine Woche nach ihrem Release, und sofort ein Update, das eine Schwachstelle behebt, oder den neuen Commit eines Branches, dem eine Action folgt; Routine-Updates und Releases, die nur Abhängigkeiten aktualisieren, mergen sich selbst, sobald alle Prüfungen grün sind, während die wöchentliche Auffrischung jeder Lock-Datei, die die neuesten Versionen ohne die Woche Wartezeit bringt, auf den Maintainer wartet; der Blueprint prüft, dass Renovate jede Lock-Datei liest, die er mitbringt. Dependabot pflegt die Features des Dev-Containers. | `renovate.json5`, `renovate-blueprint.json5`, `dependabot.yml` |
| **Abdeckung** | ein Kommentar an jedem Pull Request mit der Abdeckung seiner Tests im Vergleich zu `main`, Datei für Datei | `after-checks.yml` |
| **PR-Coach** | jede Prüfung, die scheitert, sagt, was sie gefunden hat, warum das wichtig ist und wie man es behebt, mit den Befehlen dafür: in der Zusammenfassung der Prüfung, als ihre Annotation und in einem Kommentar am Pull Request, der jedem Push folgt, auch an einem Pull Request aus einem Fork; ein Titel, der kein Conventional Commit ist, bekommt einen, der besteht, und `scripts/check.sh` erklärt den Schritt, an dem es scheitert, auch auf deinem Rechner | `.github/checks.toml`, `.github/checks.project.toml`, `after-checks.yml` |
| **Mutationstests** | jede Woche laufen Tausende kleiner Änderungen des Codes gegen die Tests, und die Zusammenfassung zeigt den Anteil, den sie bemerken, und die überlebenden Mutanten; ein niedriger Wert ist ein Bericht, nie ein Fehlschlag, aber ein Lauf, der nichts misst, schlägt fehl; ein Pull Request, der ändert, wie sie laufen, probiert sie aus | `mutation.yml`: mutmut, Infection |
| **Wackelige Tests** | ein Testlauf, der fehlschlägt oder dessen Job sein Zeitlimit erreicht, führt seine fehlgeschlagenen Jobs einmal neu aus, außer dieselben Jobs sind schon für den Commit davor gescheitert; ein Job, der dann besteht, wird in einem Issue als wackelig gemeldet, mit dem Schritt, dem Test und dem Fehler, die gescheitert sind | `after-checks.yml` |
| **Abgebrochene Prüfungen** | die schnellen Prüfungen laufen einmal für jeden Commit, sodass kein Lauf für einen anderen Commit sie abbricht; ein Lauf einer längeren vorgeschriebenen Prüfung für den neuesten Commit eines Pull Requests, den ein verspäteter Lauf für einen älteren Commit abgebrochen hat, startet von selbst neu, statt den Merge zu blockieren | `after-checks.yml` |
| **Gescheiterte Releases** | das Release eines Merges, das scheitert, etwa am Push seines Tags, den GitHub für einen Moment ablehnt, führt seine fehlgeschlagenen Jobs von selbst einmal neu aus, dort, wo sie stehen geblieben sind | `after-checks.yml` |
| **Zustand der Bots** | ein Bot oder ein geplanter Workflow, der auf `main` fehlschlägt, führt seine fehlgeschlagenen Jobs einmal neu aus, wo ein zweiter Versuch bestehen kann, und hält sonst ein Issue pro Workflow offen, mit den fehlgeschlagenen Jobs, ihren Schritten und ihren ersten Fehlern, das der nächste bestandene Lauf schließt; jede Nacht ein Blick auf den letzten Lauf jedes Workflows, auch der des Projekts, der einen Workflow startet, dessen Zeitplan GitHub verpasst oder abgeschaltet hat; im Blueprint ein Issue mit den Warnungen und Fehlern von Renovate | `bot-health.yml`, `blueprint.py bot-health` |
| **Schnelle Prüfungen** | eine Prüfung läuft nur, wo sie ein Ergebnis ändern kann: ein Scanner in den Pull Requests, die ändern, was er liest, auf `main` nur, was eine Vergleichsbasis hält oder veröffentlicht, der Rest jede Woche, und im Release-Pull-Request gar kein Scanner; das neueste Python prüft `main` eines Python-Projekts nach jeder Änderung und jede Woche | die Auslöser und Pfadfilter der Workflows, `newest-python.yml` |
| **Issues** | eine erste Analyse jedes neuen Issues durch eine KI, die nur liest, Labels, Duplikate, Erinnerungen und das Schließen mit dem Release, das den Fix enthält | der [Issue-Assistent](https://github.com/Dennis-Otto/issue-assistant) |
| **Community** | README, Beitragsleitfaden mit den Coding-Standards und der Regel, dass jede Änderung ihre Tests mitbringt, Verhaltenskodex, Sicherheitsrichtlinie mit der Prüfung eines Releases und einem Assurance Case, das Sicherheitsdesign der Software (`docs/security.md`), Support, Governance mit den Rollen und dem Fortbestand des Projekts, Issue-Formulare, Pull-Request-Vorlage, Aufzeichnungen der Entscheidungen, die das Projekt prägen (`docs/decisions/`), Discussions mit Formularen für Fragen und Ideen und einer Ankündigung jedes Releases, Sponsor-Button, Social Preview | |
| **Website** | die Dokumentation aus `docs/` als Website mit Suche und hellem und dunklem Design, auf Englisch und, mit deutschen Seiten wie `index.de.md` neben den englischen, auf Deutsch: jeder Pull Request baut sie streng, und ebenso `scripts/check.sh`, sobald die Werkzeuge ihrer Vorschau installiert sind, unter Linux, macOS und Windows; jede Änderung an `main` veröffentlicht sie auf GitHub Pages | MkDocs mit dem Material-Theme, `mkdocs.yml`, `docs.yml` |
| **Diagramme** | jedes Diagramm als Bild, das alle sehen, auch in der GitHub-App, in den Stores und in E-Mails, die kein Mermaid zeichnen: eine Mermaid-Quelle in `docs/diagrams/`, gezeichnet als SVG für das helle und eines für das dunkle Design, während die Website die Quelle live zeichnet; die Prüfung *diagrams* zeichnet die Bilder in jedem Pull Request neu, der ein Diagramm ändert oder einen `mermaid`-Block hinzufügt, und der Diagramm-Bot committet Quellen und Bilder auf seinen Branch; auf `main` behebt ein Pull Request des Diagramm-Bots, was noch fehlt, und merged sich selbst; `bash scripts/diagrams.sh --extract` macht aus den `mermaid`-Blöcken vorhandenen Markdowns Quellen und ihre Bilder | `scripts/diagrams.sh` mit mermaid-cli, `lint.yml`, `after-checks.yml`, `diagrams.yml` |
| **Einstellungen** | die Einstellungen des Repositorys als Code: Merges, Rulesets, Sicherheit, Actions, Environments, Variablen, Labels, GitHub Pages und jede Datei der Community-Standards von GitHub; der Settings-Bot wendet sie nach jeder Änderung und jede Woche an | `.github/repository.toml` und `blueprint.py` |
| **Aufräumen** | jede Woche verschwinden die Branches, die `main` enthält, und die Caches geschlossener Pull Requests; ein Branch mit eigener Arbeit bleibt und wird nach einem Monat aufgelistet | `cleanup.yml` |
| **Entwicklung** | ein Dev-Container für VS Code und GitHub Codespaces mit den Werkzeugen der Prüfungen und der Website, und ein Hook, der sie vor jedem Push ausführt, unter Linux, macOS und Windows: `scripts/check.sh` schlägt fehl, wenn Git ihn überspringen würde | `.devcontainer/`, `.githooks/pre-push` |
| **Coding-Agents** | die Regeln des Repositorys für Claude Code, Codex, GitHub Copilot und Cursor: die Befehle der Prüfungen und Tests seiner Art, die Titel von Pull Requests und die Versionen, die sie ergeben, das Changelog, das Sign-off, und welche Dateien dem Projekt gehören und welche dem Blueprint, eine Liste, die ein Test des Blueprints gleich den Dateien hält, die ein Update nie überschreibt; die Notizen des Projekts kommen aus einer eigenen Datei dazu | `AGENTS.md`, `CLAUDE.md`, `.github/agents.project.md` |
| **Updates** | gleich nach jedem Release des Blueprints, und jede Woche, führt der Blueprint-Bot `copier update` aus und öffnet einen Pull Request | `blueprint-update.yml` |
| **App Store** | für eine Nextcloud-App: die Registrierung ihrer ID mit ihrem Zertifikat, einmal, von Hand | `register-app.yml` |
| **Upstream** | für eine Nextcloud-App, jede Woche: hat Nextcloud eine neue Hauptversion, hebt ein Pull Request `max-version` an und merged sich selbst, sobald jede Prüfung, auch die End-to-End-Tests, dagegen besteht; von Hand als Probelauf gestartet, zeigt er den Pull Request, den er öffnen würde, und ändert nichts | `upstream.yml` |
| **Bereichs-Labels** | jeder Pull Request bekommt die Labels der Bereiche, deren Dateien er ändert, nach den Pfaden in `.github/labeler.yml`, die dem Projekt gehört | `area-labels.yml` |
| **Branches** | nach jeder Änderung an `main` bringt der Branch-Bot jeden Pull Request, der auf Auto-Merge wartet, auf den neuesten Stand, auch die von Renovate, damit er nach grünen Prüfungen merged | `update-branches.yml` |

### Von einer Änderung zum Release

Der Titel eines Pull Requests bestimmt die nächste Version, und der Merge des Release-Pull-Requests erledigt den Rest:

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/diagrams/from-a-change-to-a-release.de.dark.svg">
  <img src="docs/images/diagrams/from-a-change-to-a-release.de.svg" alt="Von einer Änderung zum Release: Ein Pull Request mit dem Titel fix, feat oder feat! merged in main, sobald alle Prüfungen grün sind. Der Release-Bot hält einen Release-Pull-Request mit der nächsten Version und dem Text der Fragmente und von Unreleased. Sein Merge signiert zuerst seinen Tag, im nächsten Lauf des Release-Bots, baut dann das Release isoliert, sobald der Tag geprüft ist, signiert und veröffentlicht es, liefert es aus und prüft es, sofort und jede Woche. Mit BETA_CHANNEL wird außerdem jede Änderung für Nutzer zu einer Beta.">
</picture>

Ein Pull Request beschreibt, was er für Nutzer ändert, in einer eigenen Datei, einem Fragment in `changelog.d/`, etwa `changelog.d/dark-mode.md`, unter der Überschrift seiner Art von Änderung, etwa `### Features`. Eine neue Datei kollidiert mit nichts, also mergen Pull Requests, die gleichzeitig laufen, nacheinander, ohne dass jemand `main` in jeden von ihnen mergt, und ein Release kollidiert nicht mehr mit den wartenden Pull Requests. Die Prüfung *changelog* prüft jedes Fragment so, wie das Release es übernimmt, und der Release-Bot verschiebt jedes Fragment in den Abschnitt des Releases und löscht es im selben Commit. Eine Zeile unter `## Unreleased` in `CHANGELOG.md` funktioniert weiterhin.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/diagrams/the-changelog-without-conflicts.de.dark.svg">
  <img src="docs/images/diagrams/the-changelog-without-conflicts.de.svg" alt="Der Changelog ohne Konflikte: Zwei Pull Requests fügen je eine eigene Datei zu changelog.d hinzu, also mergen sie nacheinander ohne Konflikt in main. Der Release-Bot schreibt den Abschnitt des nächsten Releases aus den Fragmenten und dem Text von Unreleased in CHANGELOG.md des Release-Pull-Requests und löscht die Fragmente im selben Commit. Sein Merge macht diesen Abschnitt zu den Notes des Releases.">
</picture>

### Wann die Prüfungen laufen

Eine Prüfung läuft nur, wo sie ein Ergebnis ändern kann, denn ein Konto bei GitHub führt etwa 20 Jobs gleichzeitig aus, und jeder Job, der nicht fehlschlagen kann, lässt einen Pull Request auf einen Runner warten:

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/diagrams/when-the-checks-run.de.dark.svg">
  <img src="docs/images/diagrams/when-the-checks-run.de.svg" alt="Wann die Prüfungen laufen: Jeder Pull Request führt die vorgeschriebenen Prüfungen aus, und die Scanner dessen, was er ändert: zizmor für einen Workflow, OSV-Scanner für eine Lock-Datei, Fuzzing für Python-Code und die Link-Prüfung für ein Dokument. Der Release-Pull-Request, der nur den Changelog und die Version ändert, führt die vorgeschriebenen Prüfungen ohne die Scanner aus. Nach einem Merge führt main nur aus, was eine Vergleichsbasis hält oder veröffentlicht. Jede Woche führt main die Scanner vollständig aus, den Secret Scan der ganzen History, die SBOM und das neueste Python.">
</picture>

- **Nach einem Merge:** `main` nimmt einen Pull Request nur auf, wenn er auf dem neuesten Stand ist, also bekommt `main` durch den Merge die Dateien, mit denen die Prüfungen des Pull Requests bestanden haben. `main` führt nur die Tests aus, mit deren Abdeckung der Abdeckungs-Bot jeden Pull Request vergleicht, die Analysen, mit denen Code Scanning vergleicht, und was veröffentlicht, etwa die Website und das Release. Lint läuft in den Pull Requests, Secret Scan und Fuzzing dort und jede Woche, und die SBOM jede Woche; jedes Release hat eine eigene SBOM.
- **Der Release-Pull-Request** ändert nur den Changelog und die Version, die nichts an dem ändern, was ein Scanner findet. Im Blueprint steht die vorgeschriebene Prüfung *variants* für die Varianten und Updates jeder Projektart: Sie besteht, wenn jede bestanden hat oder keine laufen musste, wie im Release-Pull-Request.
- **Das neueste Python**, Betas eingeschlossen, führt die Prüfungen eines Python-Projekts nach jeder Änderung an `main` und jede Woche aus, in einem eigenen Workflow, der die CI von `main` grün lässt. Ein neues Python bricht jeden Pull Request gleichermaßen, und keiner wartet darauf. Ein Fehlschlag hält ein Issue offen, das der wöchentliche Lauf schließt, sobald die Prüfungen wieder bestehen.
- **Die Runner** sind mit ihrer Version benannt, `ubuntu-24.04`, nicht `ubuntu-latest`: GitHub zieht dieses Label über Wochen Job für Job auf ein neues Image um, wie ab dem 19. Oktober 2026 auf Ubuntu 26.04, sodass die Läufe eines Workflows zufällig auf dem einen oder dem anderen Image landen würden, mit einem anderen Python, ShellCheck und Docker, und wie ein flaky Test fehlschlügen. Im Blueprint führt der Workflow Next runner die Varianten jede Woche auf dem nächsten Runner aus, und ein Fehlschlag hält ein Issue offen; sobald sie dort bestehen, zieht ein Release des Blueprints jeden Job dorthin um. Ein eigener Workflow, den ein Update nicht anfasst, behält den Runner, den er nennt: Mit `ubuntu-latest` zieht er mit GitHubs Label um.

### Wenn eine Prüfung scheitert oder abbricht

Eine Prüfung, die ein Runner, eine Website oder GitHub für einen Moment scheitern lässt oder die ein Wettlauf zweier Läufe abbricht, braucht niemanden: Die Bots nach den Prüfungen führen sie einmal neu aus und lassen nur rot, was aus einem Grund scheitert.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/diagrams/when-a-check-fails-or-stops.de.dark.svg">
  <img src="docs/images/diagrams/when-a-check-fails-or-stops.de.svg" alt="Wenn eine Prüfung scheitert oder abbricht: Wenn ein Lauf der Prüfungen oder des Releases endet, schauen die Bots nach den Prüfungen, wie. Tests, die beim ersten Versuch fehlgeschlagen sind oder ihr Zeitlimit erreicht haben, führen ihre fehlgeschlagenen Jobs einmal neu aus, außer dieselben Jobs sind schon für den Commit davor gescheitert; ein Job, der dann besteht, kommt mit seinem Schritt, seinem Test und seinem Fehler in das Issue der wackeligen Tests, und einer, der wieder scheitert, bleibt rot. Eine vorgeschriebene Prüfung, die ein verspäteter Lauf für einen älteren Commit abgebrochen hat, startet neu. Das Release eines Merges, das gescheitert ist, führt seine fehlgeschlagenen Jobs einmal neu aus, dort, wo sie stehen geblieben sind.">
</picture>

- **Einmal, nicht immer wieder:** Der Bot für wackelige Tests führt die fehlgeschlagenen Jobs des ersten Versuchs eines Testlaufs einmal neu aus, ebenso der Bot für gescheiterte Releases mit einem Release, das ein Merge gestartet hat; der Bot für abgebrochene Prüfungen startet einen Lauf höchstens zweimal. Ein Job, den GitHub an seinem Zeitlimit stoppt, endet abgebrochen, nicht fehlgeschlagen, und läuft ebenfalls einmal neu. Ein Lauf, den du oder ein neuerer Lauf abgebrochen hat, bleibt abgebrochen, auch wenn ein Job, der auf die anderen wartet, deshalb fehlgeschlagen ist.
- **Ein Fehler, der sich wiederholt, ist echt:** Wenn dieselben Jobs schon für den Commit davor auf demselben Branch gescheitert sind, nachdem sie einmal neu liefen, laufen sie nicht noch einmal, damit ein kaputter Test keinen Runner umsonst beschäftigt.
- **Das Issue der wackeligen Tests** bekommt für jeden Lauf, der beim Neustart bestanden hat, eine Tabelle: jeden Job, der zuerst fehlgeschlagen ist, mit einem Link zu seinem Log, den Schritt, der gescheitert ist, die Tests, die pytest im Log nennt, und den ersten Fehler. Ein Name oder eine Zeile eines Logs steht dort als reiner Code, sodass ein Pull Request damit weder die Tabelle beenden noch jemanden erwähnen kann.
- **Die schnellen Prüfungen laufen einmal für jeden Commit:** Titel und Changelog, Dependency Review, Secret Scan, Bereichs-Labels und Website. Ein verspäteter Lauf für einen älteren Commit, etwa einer, den eine Änderung des Release-Pull-Requests startet, während release-please in ihn pusht, bricht sie für den neuesten Commit nicht mehr ab. Die Prüfungen, die Minuten dauern, Tests, Lint, CodeQL und die Varianten, brechen den Lauf für einen älteren Commit weiter ab; einen Wettlauf dort repariert der Bot für abgebrochene Prüfungen.
- **Weitere Test-Workflows** eines Repositorys, etwa visuelle Tests, kommen mit `copier update --data "test_workflows=Visual check, Screenshot bot"` zur CI und zu Docker E2E dazu.
- **Die Link-Prüfung eines Pull Requests** liest die Dokumente, die er ändert, und alle Dokumente, wenn er die Regeln ändert oder eine Datei verschiebt oder löscht, auf die ein Dokument verlinken kann. lychee behält die Antworten der Websites einen Tag lang und fragt bei einem Link, der gescheitert ist, erneut nach, sodass eine Website, die für einen Moment nicht erreichbar ist, nur die Pull Requests scheitern lässt, die auf sie verlinken.

### Der PR-Coach

Eine Prüfung, die scheitert, erklärt sich selbst, dir und allen, die einen Pull Request schicken, auch aus einem Fork: was sie gefunden hat, warum das wichtig ist und wie man es behebt, mit den Befehlen dafür.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/diagrams/the-pr-coach.de.dark.svg">
  <img src="docs/images/diagrams/the-pr-coach.de.svg" alt="Der PR-Coach: Ein Push in einen Pull Request, auch in einen aus einem Fork, startet die Prüfungen. Eine Prüfung, die scheitert, erklärt sich in ihrer Zusammenfassung und als ihre Annotation, aus den Erklärungen von .github/checks.toml und .github/checks.project.toml. Nach den Prüfungen liest der PR-Coach die Check-Runs und ihre Annotationen über die API, ohne Code des Pull Requests auszuführen, und hält einen Kommentar am Pull Request aktuell: einen Abschnitt für jede gescheiterte Prüfung, mit dem Problem, warum es wichtig ist, der Behebung und ihren Befehlen. Du pushst die Behebung, und sobald jede Prüfung besteht, sagt der Kommentar das.">
</picture>

- **In der Prüfung:** Ein Job, der scheitert, endet mit einem Schritt, der die Erklärung seiner Prüfung in die Zusammenfassung und als Annotation schreibt, die die Liste der Prüfungen zeigt. `scripts/check.sh` macht dasselbe für den Schritt, an dem es scheitert, auch auf deinem Rechner, und in der CI zeigen die Dateien des Pull Requests die Probleme der Textdateien, von Ruff und von actionlint an ihren Zeilen.
- **Ein Kommentar, auch für einen Fork:** Die Läufe eines Pull Requests aus einem Fork können nicht in ihn schreiben, deshalb läuft der Coach nach den Prüfungen, im Repository selbst. Er hält einen Kommentar mit einem Abschnitt für jede gescheiterte Prüfung, den Funden ihrer Annotationen und einem Link zu ihrem Log, und einem Vorschlag für den Titel, wenn der Titel kein Conventional Commit ist. Ein Pull Request, dessen Prüfungen nie gescheitert sind, bekommt keinen Kommentar; sobald jede Prüfung besteht, wird ein Kommentar, der Fehler gezeigt hat, zu einer kurzen Entwarnung.
- **Sicher mit jedem Pull Request:** Der Coach liest die Check-Runs und ihre Annotationen über die API und checkt nur die Erklärungen des Standard-Branches aus; er führt keinen Code des Pull Requests aus. Text, den ein Pull Request bestimmt, etwa ein Dateiname, eine Meldung oder ein Titel, erscheint nur als Code, auf eine kurze Länge gekürzt, sodass er niemanden erwähnen, nirgendwohin verlinken und den Kommentar nicht kaputt machen kann.
- **Jede Prüfung erklärt sich:** Die Erklärungen stehen in `.github/checks.toml`, die der Blueprint aktuell hält, und die der eigenen Prüfungen eines Projekts in `.github/checks.project.toml`, die dem Projekt gehört und Vorrang hat. Ein Test des Blueprints scheitert an einer vorgeschriebenen Prüfung oder einem Schritt von `scripts/check.sh` ohne Erklärung, und `python3 .github/blueprint.py coach verify` listet sie in einem Repository auf.

### Diagramme, die sich selbst reparieren

Die GitHub-App, HACS, der Nextcloud App Store, PyPI und die E-Mails von GitHub zeichnen kein Mermaid und zeigen einen `mermaid`-Block als Code. Darum ist jedes Diagramm ein Bild seiner Quelle, und die Bots halten das ohne einen Menschen so.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/diagrams/how-the-diagrams-fix-themselves.de.dark.svg">
  <img src="docs/images/diagrams/how-the-diagrams-fix-themselves.de.svg" alt="Wie sich die Diagramme selbst reparieren: Ein Pull Request, der einen mermaid-Block hinzufügt oder ein Diagramm ändert, und Renovate mit einer neuen Version von mermaid-cli führen die Prüfung diagrams aus, die die Diagramme neu zeichnet. Auf einem Branch des Repositorys committet der Diagramm-Bot die Quellen und Bilder auf den Branch, und die Prüfungen laufen erneut; ein Fork behält die fehlschlagende Prüfung, die den Befehl nennt. Nach dem Merge und jede Woche wird auch main gezeichnet: Ist ein Diagramm noch kein Bild seiner Quelle, behebt das ein Pull Request von bot/diagrams, der sich selbst merged. So sehen alle Leser jedes Diagramm.">
</picture>

- **Ein Pull Request repariert sich selbst:** Fügt ein Pull Request von einem Branch des Repositorys einen `mermaid`-Block hinzu oder ändert er eine Quelle, führt die Prüfung *diagrams* `bash scripts/diagrams.sh --extract` aus, und der Diagramm-Bot committet die Quellen und Bilder, die dabei entstehen, als Release-App auf den Branch, mit einem Kommentar, der die geänderten Seiten nennt. Die Prüfungen dieses Commits bestehen. Ein Pull Request aus einem Fork bekommt die fehlschlagende Prüfung, deren Zusammenfassung die Dateien und den Befehl nennt.
- **`main` repariert sich selbst:** Nach jeder Änderung von `main`, die ein Diagramm betrifft oder einen `mermaid`-Block hinzufügt, und jede Woche zeichnet der Workflow Diagrams alle Diagramme von `main`. Fehlt etwas, etwa die Blöcke eines Repositorys direkt nach dem Update des Blueprints, hält er einen Pull Request vom Branch `bot/diagrams` mit der Korrektur, der sich selbst merged, sobald alle Prüfungen bestehen, und schließt ihn, wenn `main` anders repariert wurde. Ein fehlgeschlagener Lauf öffnet ein Issue, das der wöchentliche Lauf schließt, sobald der Bot wieder besteht.
- **Ein neuer Renderer zeichnet neu:** Renovate hält das Image von mermaid-cli in `scripts/diagrams.sh` aktuell; die Prüfung zeichnet die Bilder auf seinem Branch neu, und der Diagramm-Bot committet sie, sodass das Update weiterhin von selbst merged.
- **Nur Diagramme:** Der Bot führt keinen Code eines Pull Requests aus. Er committet nur Quellen in `docs/diagrams/`, SVG-Bilder in `docs/images/diagrams/` und Markdown-Seiten, mit einfachen Pfaden, auf genau den Commit, den die Prüfung gezeichnet hat, und nur für einen Branch des Repositorys.

### Mutationstests

Die Mutationstests zeigen die Zeilen, die die Tests ausführen, aber nicht prüfen: Jeden Samstag ändern sie den Code auf Tausende kleine Weisen, die Mutanten, und führen die Tests aus, die jeden davon abdecken. Ein Mutant, den kein Test bemerkt, überlebt.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/diagrams/how-the-mutation-tests-run.de.dark.svg">
  <img src="docs/images/diagrams/how-the-mutation-tests-run.de.svg" alt="Wie die Mutationstests laufen: Jeden Samstag, auf Abruf und für einen Pull Request, der ändert, wie sie laufen, führt der Mutation-Workflow die Mutanten aus. mutmut ändert das Python in einer Kopie des Repositorys und lässt die Tests mit der Markierung mutation_unsafe aus; Infection ändert das PHP einer Nextcloud-App, mit dem Bootstrap ihrer Tests. Wenn Mutanten liefen, zeigt die Zusammenfassung den Wert und die überlebenden Mutanten, das Artefakt bewahrt sie auf und das Dashboard zeigt den Wert. Ein Lauf, der nichts gemessen hat, schlägt fehl und zeigt die letzten Worte des Werkzeugs.">
</picture>

- **Der Wert ist der Anteil der Mutanten, den ein Test bemerkt hat,** unter denen des Codes, den die Tests ausführen: bei mutmut die getöteten unter den getöteten und den überlebenden, bei Infection sein *Covered Code MSI*. Das Dashboard zeigt ihn als *gefangene Mutanten*.
- **Ein niedriger Wert lässt nichts fehlschlagen,** auch nicht unter einem Minimum, das die eigene Konfiguration des Projekts setzt, aber ein Lauf, in dem kein Mutant lief, schon, mit dem Ende der Ausgabe von mutmut oder Infection in seiner Zusammenfassung: Eine kaputte Konfiguration zeigt sich in der Woche, in der sie kaputtgeht, nicht als leeres Dashboard.
- **Ein Pull Request, der ändert, wie die Mutanten laufen,** `mutation.yml` oder das gepinnte mutmut, probiert sie aus, mutmut eine Viertelstunde lang, und zeigt einen Fehler als roten Check vor dem wöchentlichen Lauf. Der Check ist nicht erforderlich, also wartet ein Pull Request, der sich selbst zusammenführt, etwa ein Update von mutmut, nicht auf ihn: Sein roter Check ist eine Warnung zum Lesen.
- **mutmut führt die Tests in einer Kopie des Repositorys aus,** `mutants/`, mit dem geänderten Code und ohne Git. Ein Test, der dort nicht funktionieren kann, weil er den Code als Text liest oder Git fragt, bekommt die Markierung `@pytest.mark.mutation_unsafe`, und die Mutationstests lassen ihn aus; die `pyproject.toml` eines neuen Python-Projekts registriert die Markierung.
- **Eine Konfiguration des Projekts hat Vorrang:** eine Tabelle `[tool.mutmut]` in `pyproject.toml` oder ein Abschnitt `[mutmut]` in `setup.cfg` für mutmut, eine `infection.json5` für Infection. Ohne sie mutiert mutmut `custom_components/`, `src/` oder die Module und Pakete der Wurzel, und Infection mutiert `lib/` auf PHP 8.3, mit `tests/bootstrap.php`, das die Klassen von Nextcloud lädt.

### Wenn ein Bot fehlschlägt

GitHub schickt den Fehlschlag eines geplanten Laufs nur an den, der seinen Zeitplan zuletzt geändert hat, und den eines anderen Laufs an den, der ihn gestartet hat, in diesen Repositorys meist die Release-App: Ein roter Bot zeigte sich nur im Actions-Tab, so wie Findings, Mutation und Renovate tagelang fehlschlugen. Der Bot für den Zustand der Bots (`bot-health.yml`) macht aus jedem solchen Fehlschlag ein Issue und schließt es, sobald der Bot wieder besteht.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/diagrams/what-the-bot-health-bot-does-when-a-bot-fails.de.dark.svg">
  <img src="docs/images/diagrams/what-the-bot-health-bot-does-when-a-bot-fails.de.svg" alt="Was der Bot für den Zustand der Bots tut, wenn ein Bot fehlschlägt: Wenn ein Lauf eines Bots oder eines geplanten Workflows auf dem Standardbranch endet, sieht der Bot ihn sich an; Läufe von Pull Requests starten nichts. Ein erster Fehlschlag, den ein zweiter Versuch beheben kann, führt seine fehlgeschlagenen Jobs einmal neu aus. Ein Fehlschlag, der bleibt, öffnet ein Issue für den Workflow oder aktualisiert es, mit den fehlgeschlagenen Jobs, ihren Schritten und ihren ersten Fehlern. Ein Lauf, der besteht, schließt das Issue. Jede Nacht sieht sich der Bot den letzten Lauf jedes Workflows an, falls GitHub ein Ereignis verloren hat, und startet einen Workflow, dessen Zeitplan GitHub verpasst oder abgeschaltet hat.">
</picture>

- **Ein Issue pro Workflow,** mit einem Titel wie *Findings fails on main* und den Labels `bot-failure` und `maintenance`. Es nennt den letzten fehlgeschlagenen Lauf, seinen Versuch und seinen Auslöser und eine Tabelle der fehlgeschlagenen Jobs mit dem Schritt, der fehlschlug, und dem ersten Fehler eines jeden, aus den Annotationen des Laufs. Ein späterer Fehlschlag an derselben Stelle aktualisiert es nur, ohne Benachrichtigung; ein Fehlschlag in einem anderen Job oder Schritt fügt einen Kommentar hinzu. Der nächste Lauf, der besteht, schließt es mit einem Link auf diesen Lauf.
- **Ein zweiter Versuch nur, wo er bestehen kann:** Ein erster Fehlschlag führt seine fehlgeschlagenen Jobs einmal neu aus, wie es der Bot für wackelige Tests bei den Tests tut, außer ein anderer Bot hat das schon getan. Findings, das fehlschlägt, solange ein Alarm offen ist, Mutation, das Stunden braucht, um dasselbe noch einmal zu messen, und die Property-Tests und das Fuzzing, die an einer Eingabe fehlschlugen, die sie gefunden haben, werden sofort gemeldet. Ein Lauf, den GitHub nicht starten konnte, weil seine Workflow-Datei ungültig ist, ebenso.
- **Welche Läufe zählen:** die der Bots und geplanten Workflows, die `bot-health.yml` aufzählt, auf dem Standardbranch, von einem Zeitplan, einem Push, einem Start von Hand oder einem anderen Workflow, nie von einem Pull Request oder einem Fork. Die Prüfungen, die in Pull Requests laufen, etwa die CI, die Website oder CodeQL, und die Workflows des Projekts zählen im nächtlichen Blick, der den letzten beendeten Lauf jedes Workflows auf dem Standardbranch nimmt, sodass keiner ihrer Läufe für einen Pull Request einen Lauf des Bots startet. Einem Lauf, den das Ende einer Prüfung eines Pull Requests startet, wie bei After the checks, gibt GitHub ebenfalls den Standardbranch, deshalb zählt der nächtliche Blick bei einem solchen Workflow nur dessen andere Läufe. Der Workflow Diagrams, Newest Python und Next runner halten je ein eigenes Issue.
- **Verpasste Zeitpläne:** GitHub führt einen Zeitplan zu Stoßzeiten verspätet aus, manchmal gar nicht, und schaltet die Zeitpläne eines Repositorys nach 60 Tagen ohne Aktivität ab. Jede Nacht startet ein Workflow von Hand, dessen letzter Lauf älter ist als die letzte Zeit seines Zeitplans, die sechs Stunden oder länger her ist, höchstens vier pro Nacht, damit die Pull Requests ihre Runner behalten; Findings und Issue lifecycle starten mit abgeschaltetem `dry_run`, wie ihr Zeitplan sie ausführt. Einen Zeitplan, den GitHub abgeschaltet hat, schaltet der Bot wieder ein.
- **Die Probleme von Renovate:** Renovate läuft zentral im Blueprint und protokolliert eine Lock-Datei, die es nicht lesen kann, als Warnung, ohne fehlzuschlagen. Der Renovate-Workflow hält ein Issue, *Renovate logs problems*, mit den Warnungen und Fehlern seines letzten Laufs, der welche hatte, nach Repository, und schließt es nach drei Läufen in Folge ohne eines. Ein öffentliches Issue nennt nur öffentliche Repositorys.
- Der Bot liest Läufe, Jobs und Annotationen und schreibt Issues mit dem `GITHUB_TOKEN` seines Jobs, und er checkt nur den Standardbranch aus, nie den Code eines Pull Requests. Ein Repository, dessen `.github/labels.toml`, die dem Projekt gehört, kein `bot-failure` hat, bekommt das Label vom Bot; trag es in die Datei ein, damit Farbe und Beschreibung an einem Ort bleiben.

## Arten von Projekten

| Art | Stack | Prüfungen | Auslieferung |
| --- | --- | --- | --- |
| Home-Assistant-Integration | Python 3.14, pytest-homeassistant-custom-component | Ruff, mypy, Tests, HACS, hassfest | ein Zip-Asset für HACS |
| Nextcloud-App | PHP 8.2, Composer | php-cs-fixer, Psalm mit seiner Taint-Analyse, PHPUnit mit jeder Zeile abgedeckt | signiertes Paket in den App Store |
| GitHub Action | Python 3.12 des Runners, Composite Action | Ruff, mypy, Tests, ein Lauf der Action | Release-Tags und ein mitwandernder Major-Tag |
| Python-Paket | Python 3.12, Hatchling | Ruff, mypy, Tests, Build | PyPI, Trusted Publishing |
| Node-Paket | Node 24, TypeScript | tsc, node:test mit voller Abdeckung, Pack | npm mit Provenance |
| Container-Image | Alpine per Digest | Hadolint, Build, Selbsttest | GHCR, Multi-Arch, mit SBOM und Provenance |
| Repository ohne Build | | Textdateien, Shell-Skripte | nur Releases |

Jede Art startet mit einem kleinen, funktionierenden Beispiel samt Tests, das durch den echten Code ersetzt wird.

## Ein Repository anlegen

<!-- --8<-- [start:quick-start] -->

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

![copier copy im Terminal: Copier klont den Blueprint und fragt nach dem Namen Paperless Sync, dem Repository, einer Beschreibung und der Art des Projekts, Python-Paket, übernimmt für den Rest die Vorgaben, schreibt die Dateien und nennt die nächsten Schritte; das neue Repository hat seine Community-Dateien, seine Prüfungen und seine Workflows](docs/images/copier-copy.gif)

<!-- --8<-- [end:quick-start] -->

### Einmal pro Repository

- **Die Release-App** öffnet die Release- und Update-Pull-Requests, damit ihre Prüfungen laufen. Installiere sie auf dem Repository und hinterlege ihren privaten Schlüssel als Secret `RELEASE_AUTOMATION_PRIVATE_KEY` im Environment `release`. Die App braucht die Berechtigungen *Actions*, *Administration*, *Checks*, *Commit statuses*, *Contents*, *Issues*, *Pages*, *Pull requests*, *Variables* und *Workflows* (Lesen und Schreiben) sowie *Dependabot alerts*, *Environments* und *Secrets* (Lesen): Damit wendet der Settings-Bot die Einstellungen als Code an, Renovate aktualisiert die Abhängigkeiten, und der Rollout des Blueprints startet nach einem Release den Blueprint-Bot jedes Repositorys. Renovate bekommt ein Token ohne *Administration*. Der Release-Workflow legt jeden Release-Tag mit der App an, und das Ruleset *Release tag creation* lässt niemand anderen einen anlegen; die Variablen `RELEASE_AUTOMATION_CLIENT_ID` und `RELEASE_AUTOMATION_APP_ID` in `.github/repository.toml` nennen die App, und ein Projekt mit einer eigenen App setzt beide in `.github/repository.project.toml`.
- **Der Issue-Assistent** braucht `CLAUDE_CODE_OAUTH_TOKEN` im Environment `issue-assistant`.
- **Auslieferung:** Trusted Publishing auf PyPI oder npm, das App-Zertifikat einer Nextcloud-App oder die Einreichung bei HACS, wie es die Checkliste sagt.

`checklist` gibt die `gh secret set`-Befehle aus; der Wert wird in die Abfrage der GitHub CLI eingegeben und erscheint nirgends sonst.

### Ein bestehendes Repository

Ein bestehendes Repository übernimmt den Blueprint auf einem Branch, in einem Pull Request:

1. `copier copy --overwrite --vcs-ref vX.Y.Z --data sample_code=false gh:Dennis-Otto/repo-blueprint .` mit den Antworten, die zum Repository passen, ohne den Beispielcode und die Beispieltests eines neuen, etwa Beschreibung, Topics und Homepage wie auf GitHub, damit `settings apply` dort nichts ändert. Die Dateien des Projekts (README, Changelog, Code, Tests, Manifeste, Labels, Issue-Formulare, Icons) bleiben, wie sie sind.
2. Den Diff jeder Datei des Blueprints ansehen und zurückholen, was nur dem Projekt gehört: Abschnitte von SECURITY.md oder CONTRIBUTING.md, Regeln von Renovate (in `.github/renovate.json5`), Hosts des Issue-Assistenten, Ignore-Regeln. `copier update` behält diese Änderungen von da an.
3. Die Version des letzten Releases in `version.txt` und `.release-please-manifest.json` schreiben, `CHANGELOG.md` mit `## Unreleased` beginnen und `.github/labels.toml` die Labels der Bots geben (`autorelease: pending`, `autorelease: tagged`, `merge-conflict`, `maintenance`, `bot-failure`, `docker`).
4. Die Prüfungen nur dieses Projekts, etwa seine End-to-End-Tests, in `.github/repository.project.toml` und `scripts/check-project.sh` eintragen; die Workflows, Skripte und Tests entfernen, die der Blueprint ersetzt, und Dateien der Vorlage löschen, die das Projekt nicht braucht, etwa einen Beispieltest. Ein Repository ohne `docs/` hat keine Website, bis es `docs/index.md` schreibt; `mkdocs.yml` zeigt, wie deutsche Seiten dazukommen.
5. Den Pull Request öffnen. Sobald seine neuen Prüfungen bestehen, stellt `blueprint.py settings apply` die Pflicht-Prüfungen, Variablen und Labels um, und der Pull Request kann mergen.

Die Konfiguration der Prüfungen gehört dem Blueprint und sucht den Code dort, wo ihn ein neues Projekt derselben Art hat. Jede Datei, die sie nennt, kommt mit dem Blueprint, auch ohne den Beispielcode:

| Art | Code | Tests | Vom Blueprint |
| --- | --- | --- | --- |
| Nextcloud-App | `lib/` | PHPUnit-Tests in `tests/Unit/` | `psalm.xml` und `phpunit.xml`, mit den `tests/bootstrap.php` und `tests/stubs/`, die sie laden |
| Node-Paket | `src/`, gebaut nach `dist/` | `test/`, von `tsconfig.json` typgeprüft; das `npm test` eines neuen Projekts führt `test/**/*.test.ts` aus | `tsconfig.json` und `tsconfig.build.json`, die `typescript` und `@types/node` in der `package.json` des Projekts brauchen |

Die anderen Arten legen diese Orte in eigenen Dateien fest, etwa in `pyproject.toml`. Was in `tests/` liegt, gehört dem Projekt: Die Kopie und jedes Update ergänzen dort nur die Dateien, die fehlen, und eine App mit eigenem Bootstrap behält ihn.

## Einstellungen als Code

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/diagrams/the-settings-as-code.de.dark.svg">
  <img src="docs/images/diagrams/the-settings-as-code.de.svg" alt="Die Einstellungen als Code: Die Einstellungen eines Repositorys stehen in .github/repository.toml, mit denen nur dieses Projekts und den Labels. blueprint.py settings apply, ausgeführt von einem Administrator, und der Settings-Bot, nach jeder Änderung und jede Woche, gleichen GitHub an sie an; settings check zeigt, was abweicht.">
</picture>

`.github/repository.toml` enthält die Einstellungen eines Repositorys; `blueprint.py settings check` vergleicht sie mit GitHub, `settings apply` gleicht GitHub an:

- **Repository:** Squash-Merges mit dem Titel des Pull Requests, Auto-Merge, Branch-Updates, gelöschte Branches, Sign-off auch für Commits im Web, kein Wiki, keine Projects.
- **Sicherheit:** unveränderliche Releases, private Meldung von Schwachstellen, Dependabot-Alerts mit den Sicherheitsupdates von Renovate, Secret Scanning mit Push-Schutz.
- **Actions:** standardmäßig nur lesende Tokens, keine Freigaben durch Workflows, Actions nur per Commit-Hash, Freigabe der Workflows jedes externen Beitragenden.
- **Rulesets:** *Protect main* (nur Pull Requests, Squash, lineare Historie, alle Pflichtprüfungen, kein Löschen und kein Force-Push), *Release tags* (`v*.*.*` bewegt sich nie) und *Release tag creation* (nur die Release-App, deren App-ID `RELEASE_AUTOMATION_APP_ID` nennt, legt einen `v*.*.*`-Tag an, den der Release-Workflow signiert).
- **Variablen und Environments:** `PUBLISH_TO`, die Release-App (`RELEASE_AUTOMATION_CLIENT_ID` und `RELEASE_AUTOMATION_APP_ID`) und Environments, die nur `main` nutzen darf, mit den Secrets, die sie brauchen.
- **Pages:** GitHub Pages veröffentlicht die Website, die der Docs-Workflow baut.

`blueprint.py` braucht Python 3.12 und die GitHub CLI, angemeldet als Administrator, sonst nichts. Es liest und zeigt nie den Wert eines Secrets. Jedes Repository hat eine Kopie in `.github/blueprint.py` und `.github/blueprint/`, und der Settings-Bot (`settings.yml`) vergleicht seine Einstellungen jede Woche und nach jeder Änderung mit den Einstellungen als Code, damit kein Repository abdriftet.

## Updates

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/diagrams/how-an-update-of-the-blueprint-arrives.de.dark.svg">
  <img src="docs/images/diagrams/how-an-update-of-the-blueprint-arrives.de.svg" alt="Wie ein Update des Blueprints ankommt: Gleich nach jedem Release des Blueprints, und jede Woche, prüft der Blueprint-Bot zuerst das neueste veröffentlichte Release. Ein Release, das nicht unveränderlich ist, dessen Tag nicht auf dem main-Branch des Blueprints liegt oder das der Release-Workflow des Blueprints nicht signiert hat, lässt den Lauf fehlschlagen, und nichts wird aktualisiert. Sonst führt der Bot copier update auf dieses Release aus. Ist sein Pull Request noch offen und hast du auf seinen Branch committet, überlässt der Bot dir den Branch und sagt einmal, dass ein neueres Release erschienen ist. Sonst öffnet er den Pull Request oder bringt den offenen auf das neue Release. Mit Konflikten, die Auto-Merge abschalten, oder mit BLUEPRINT_AUTOMERGE auf off, wartet er auf den Maintainer; sonst merged er sich selbst, sobald alle Prüfungen grün sind.">
</picture>

Der Blueprint-Bot (`blueprint-update.yml`) führt jede Woche `copier update` aus, und gleich nach jedem Release des Blueprints, dessen Rollout-Workflow ihn in jedem Repository der Release-App startet. Er nimmt das neueste veröffentlichte Release des Blueprints, den `.copier-answers.yml` nennt, vielleicht eines Forks davon, nie einen Tag, dessen Release noch ein Entwurf ist. Vor dem Update prüft er das Release: Es muss unveränderlich sein, sein Tag muss auf einen Commit von `main` des Blueprints zeigen, der nicht älter ist als die Version des Repositorys, und der Release-Workflow des Blueprints muss den Tag signiert haben (gitsign, wie [SECURITY.md](https://github.com/Dennis-Otto/repo-blueprint/blob/main/SECURITY.md#verify-a-release) zeigt). Jedes andere Release lässt den Lauf fehlschlagen, bevor Copier etwas rendert, mit dem Grund und dem, was zu tun ist, in der Zusammenfassung des Laufs, sodass ein Tag, den jemand anderes gepusht hat, kein Repository erreicht; antworten GitHub oder Sigstore nicht, fragt der Bot dreimal und wartet dann auf seinen nächsten Lauf. Einen Blueprint, der nicht auf GitHub liegt, kann er nicht prüfen, also aktualisiert er nicht von ihm. Der Bot hält einen Pull Request auf dem Branch `blueprint/update`: Ein neueres Release bringt diesen Pull Request weiter, mit seiner Nummer und seinem Auto-Merge, statt ihn zu ersetzen. Ohne Konflikte merged er sich selbst, sobald alle Prüfungen grün sind. Konflikte bleiben als Markierungen für den Maintainer darin, in den Dateien, die das Update geändert hat; sie schalten sein Auto-Merge ab und setzen das Label `merge-conflict`. Die Repository-Variable `BLUEPRINT_AUTOMERGE` mit dem Wert `off` lässt jedes Update auf den Maintainer warten. Von Hand startet er unter *Actions → Blueprint update*, lokal mit `copier update`.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/diagrams/how-a-release-of-the-blueprint-rolls-out.de.dark.svg">
  <img src="docs/images/diagrams/how-a-release-of-the-blueprint-rolls-out.de.svg" alt="Wie ein Release des Blueprints ausgerollt wird: Sobald der Release-Workflow ein Release veröffentlicht und geprüft hat, nimmt sich der Rollout-Workflow die Repositorys der Release-App nacheinander vor, die mit den schnellsten Prüfungen zuerst. Er startet den Blueprint-Bot eines Repositorys und wartet bis zu 15 Minuten auf den Bot und die Prüfungen seines Update-Pull-Requests, dann geht es mit dem nächsten weiter. Ein Repository, dessen Bot er nicht starten kann oder dessen Bot scheitert, lässt den Lauf mit seinem Namen fehlschlagen, und die anderen bekommen das Release trotzdem.">
</picture>

Der Rollout-Workflow des Blueprints bringt jedes Release nacheinander in die Repositorys der Release-App, die mit den schnellsten Prüfungen zuerst: Er startet den Blueprint-Bot eines Repositorys und gibt dem Bot und den Prüfungen seines Update-Pull-Requests bis zu 15 Minuten, bevor er den nächsten startet, damit die Update-Pull-Requests nicht alle zugleich auf die Runner des Kontos warten. Ein Repository, dessen Bot er nicht starten kann oder dessen Bot scheitert, lässt den Lauf mit seinem Namen fehlschlagen; die anderen bekommen das Release trotzdem. Er rollt jedes Release aus, das ein Lauf des Release-Workflows veröffentlicht hat, ob der Merge des Release-Pull-Requests diesen Lauf gestartet hat, der stündliche Zeitplan oder ein Start von Hand; ein Release, das der Lauf eines späteren Merges fertiggestellt hat, weil der Lauf seines eigenen Merges verloren ging, wartet auf einen Start von Hand (Actions → Rollout) oder den wöchentlichen Lauf der Bots. Selbst von Hand gestartet, rollt er das neueste Release aus. Rollouts von Releases, die kurz nacheinander kommen, überlappen sich, aber nie im selben Repository: Dort nimmt das neuere Release den Platz eines älteren ein, das noch wartet.

Sobald du auf den Branch des Pull Requests committest, etwa um die Markierungen aufzulösen, überlässt der Bot dir den Branch: Ist ein neueres Release erschienen, sagt er das in einem Kommentar, und nachdem du den Pull Request gemerged oder geschlossen hast, bringt sein nächster Lauf den Rest. Ein Merge von `main` mit dem Button *Update branch* zählt nicht als dein Commit, und ein Auto-Merge, das du abschaltest, bleibt aus. Ein Update, das nur ein neues Release in `.copier-answers.yml` festhält, kommt ebenfalls als Pull Request, und die Updates bringen auch die Modi von Dateien mit, etwa ein Skript, das ausführbar wird.

Dem Blueprint gehören die Workflows, `scripts/check.sh` und die Community-Dateien: ihre Änderungen kommen mit den Updates. Dateien des Projekts werden nie überschrieben: README, Changelog, das Sicherheitsdesign in `docs/security.md`, Manifeste und Lock-Dateien der Abhängigkeiten (die hält Renovate aktuell), Code und Tests, `mkdocs.yml` und die Seiten der Website, Issue-Formulare, Labels, akzeptierte Findings und die Notizen für Coding-Agents. Prüfungen, die nur ein Projekt braucht, gehören in `scripts/check-project.sh`, das `scripts/check.sh` zuletzt ausführt.

## Was einem Projekt gehört

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/diagrams/what-belongs-to-the-blueprint-and-what-to-the-project.de.dark.svg">
  <img src="docs/images/diagrams/what-belongs-to-the-blueprint-and-what-to-the-project.de.svg" alt="Was dem Blueprint gehört und was dem Projekt: copier update bringt die Änderungen der Dateien des Blueprints, Zeile für Zeile mit den Änderungen des Repositorys zusammengeführt, und überschreibt nie die Dateien des Projekts. Ein Projekt ergänzt eigene Prüfungen, Einstellungen, Notizen für Coding-Agents und Workflows neben denen des Blueprints.">
</picture>

Der Blueprint hält die gemeinsamen Teile aller Repositories gleich; ein Projekt ergänzt seine eigenen, ohne sie abzuspalten:

- **Änderungen an den Dateien des Blueprints überstehen Updates:** `copier update` führt die Änderungen des Blueprints und die des Repositorys Zeile für Zeile zusammen und markiert nur dort einen Konflikt, wo beide dieselben Zeilen geändert haben.
- **Einstellungen nur dieses Projekts** gehören in `.github/repository.project.toml`, etwa die Prüfungen seiner End-to-End-Tests oder ein Environment mit seinen Secrets. `blueprint.py` und der Settings-Bot ergänzen damit `.github/repository.toml`.
- **Prüfungen nur dieses Projekts** gehören in `scripts/check-project.sh`, das `scripts/check.sh` zuletzt ausführt; **Workflows nur dieses Projekts** sind eigene Workflow-Dateien.
- **Notizen für Coding-Agents** gehören in `.github/agents.project.md`, etwa die Architektur des Projekts und die Befehle seiner eigenen Prüfungen. `AGENTS.md`, das der Blueprint aktuell hält, enthält die Regeln jedes Repositorys und verweist darauf, und `CLAUDE.md` bringt beides zu Claude Code.
- **Erklärungen der Prüfungen nur dieses Projekts,** die der PR-Coach zeigt, wenn eine scheitert, gehören in `.github/checks.project.toml`; sie haben Vorrang vor denen von `.github/checks.toml`.
- **Mehrere Copyright-Inhaber,** etwa die Autoren eines Forks, sind die Antwort `copyright`, durch Semikolons getrennt; LICENSE und REUSE.toml nennen jeden von ihnen.
- **Dateien unter einer anderen Lizenz,** etwa Grafiken Dritter, bekommen eine `.license`-Datei daneben, wie REUSE es beschreibt.
- **Das Paket einer Nextcloud-App** prüft `scripts/check-package.sh ARCHIV unsigned|signed`, wenn das Projekt eines hat: `scripts/check.sh` führt es für das Paket aus, das krankerl baut, das Release für das Paket vor und nach dem Signieren.
- **Die Version in anderen Zeilen einer Datei des Releases,** etwa das Tag in der URL eines Screenshots in `appinfo/info.xml`, folgt jedem Release, wenn die Zeile mit dem Kommentar `x-release-please-version` endet, etwa `<!-- x-release-please-version -->`.

## Werkzeuge in jedem Repository

- `bash scripts/check.sh`: die Prüfungen der CI, lokal.
- `bash scripts/diagrams.sh`: zeichnet jedes Diagramm aus `docs/diagrams/` als seine Bilder in `docs/images/diagrams/`, mit Docker; `--extract` macht vorher aus jedem `mermaid`-Block des Markdowns eine Quelle und ihr Bild, und `--check` prüft ohne Docker, was `scripts/check.sh` prüft.
- `bash scripts/social-preview.sh`: rendert `.github/social-preview.html` in das 1280×640-Bild, das GitHub bei Links auf das Repository zeigt; hochladen unter *Settings → Social preview*.

## Dashboard

![Das Dashboard: eine Tabelle mit jedem öffentlichen Repository des Besitzers, seiner Art, dem Release des Blueprints, auf dem es steht, seinem Release, seinem nächsten Release, seinen Pull Requests und dem Zustand von CI, CodeQL, Release, Prüfung, Einstellungen, Findings und Links mit seinem Scorecard, und eine zweite Tabelle mit der Gesundheit jedes Repositorys: Abdeckung, gefangene Mutanten, Releases in 90 Tagen, die erste Antwort auf ein Issue und die Dauer der CI](docs/images/dashboard.png)

[Das Dashboard](https://dennis-otto.github.io/repo-blueprint/dashboard/) zeigt jedes öffentliche Repository des Besitzers auf einen Blick: das Release des Blueprints, auf dem es steht, sein letztes Release und den Pull Request des nächsten, seine offenen Pull Requests und die mit Konflikten, den letzten Lauf seiner wichtigsten Workflows auf `main` und sein OpenSSF Scorecard; eine zweite Tabelle zeigt die Gesundheit jedes Repositorys: die Zeilenabdeckung und den Anteil der Mutanten, die die Tests fangen, die stabilen Releases und die mittlere Zeit bis zur ersten Antwort auf ein Issue über 90 Tage und die mittlere Dauer der CI, jeweils mit einem Pfeil, wenn sich der Wert seit einer Woche bewegt hat, aus dem Verlauf, den das veröffentlichte Dashboard aufbewahrt. Der Dashboard-Workflow baut es alle sechs Stunden mit `dashboard.py` und veröffentlicht es auf GitHub Pages, unter der Website des Blueprints, die diese Dokumentation ist. Es zeigt nur, was ohnehin öffentlich ist, keine Findings des Code Scannings und keine Alerts von Dependabot.

Jeden Montag veröffentlicht der Workflow Weekly report in den [Discussions](https://github.com/Dennis-Otto/repo-blueprint/discussions), was die öffentlichen Repositorys des Besitzers in der Woche veröffentlicht, gemergt und behoben haben: ihre Releases, gemergten Pull Requests und die Updates darunter, geöffnete und geschlossene Issues, fehlgeschlagene Läufe auf `main` und die mittlere Dauer ihrer CI (`weekly.py`). Wie das Dashboard berichtet er nur, was öffentlich ist.

## Wie der Blueprint funktioniert

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/diagrams/how-the-blueprint-works.de.dark.svg">
  <img src="docs/images/diagrams/how-the-blueprint-works.de.svg" alt="Wie der Blueprint funktioniert: Copier rendert ein neues Repository aus den Fragen in copier.yml und den Dateien in template/, die die Workflows aus .github/workflows/, die Manifeste aus stacks/ und blueprint.py aufnehmen. Renovate hält die Workflows und die Stacks aktuell.">
</picture>

- `copier.yml` enthält die Fragen. `template/` enthält die Dateien eines neuen Repositorys; ein Datei- oder Ordnername wie `[% if stack == 'php' %]composer.json[% endif %]` trägt seine Bedingung, und ein Name, der leer gerendert wird, entfällt. Die Trennzeichen `{= =}` und `[% %]` kommen in keinem Workflow, Skript oder Manifest vor; so bleiben `${{ }}` von GitHub Actions und `[[ ]]` von Bash und TOML unverändert.
- Die Workflows in `.github/workflows/` laufen in diesem Repository und sind zugleich die Vorlagen der Workflows jedes neuen Repositorys: actionlint prüft sie, und Renovate hält ihre Actions hier aktuell. Eine Zeile mit *Not in the blueprint itself* schaltet einen Job in diesem Repository ab und fehlt in neuen.
- `blueprint.py` startet das Werkzeug der Einstellungen als Code, der Checkliste und der Bots. Sein Code liegt in `blueprint/`, ein Modul für jede Aufgabe, mit einer eigenen `ruff.toml`, damit die Ruff-Einstellungen eines Projekts nicht für ihn gelten.
- `stacks/` enthält Manifeste und Lock-Dateien jeder Projektart, die Renovate aktuell hält; ein neues Projekt startet von ihnen.
- `tests/` prüft `blueprint.py` gegen ein simuliertes GitHub und rendert jede Projektart; der Variants-Workflow rendert jede einzelne und führt ihre eigenen Prüfungen mit den echten Werkzeugen aus. Außerdem bringt er ein Repository jeder Art vom letzten Release auf den Commit; das muss jede Datei des Blueprints so bekommen, wie ein neues Repository sie hat, und dieselben Prüfungen bestehen: in jedem Pull Request außer dem Release-Pull-Request, und jede Woche. Der Windows-Workflow führt `scripts/check.sh` außerdem unter Windows aus, in Git Bash wie auf dem Rechner eines Mitwirkenden, jede Woche und für jeden Pull Request, der den Code oder die Tests ändert. Der Workflow Next runner führt die Variants jede Woche auf dem Runner aus, auf den die Jobs als Nächstes umziehen.
- `docs/` macht diese Dokumentation zur Website des Blueprints: ihre Seiten binden die READMEs ein, und der Dashboard-Workflow veröffentlicht sie mit dem Dashboard unter `dashboard/`.

Wohin sich der Blueprint entwickelt: [die Roadmap](https://github.com/Dennis-Otto/repo-blueprint/blob/main/docs/roadmap.md) (englisch). Was er schützt und wem er vertraut: [sein Sicherheitsdesign](https://github.com/Dennis-Otto/repo-blueprint/blob/main/docs/security.md) (englisch).

Beiträge sind willkommen: siehe [CONTRIBUTING.md](https://github.com/Dennis-Otto/repo-blueprint/blob/main/CONTRIBUTING.md). Fragen und Probleme: [SUPPORT.md](https://github.com/Dennis-Otto/repo-blueprint/blob/main/SUPPORT.md). Schwachstellen bitte vertraulich melden, wie es [SECURITY.md](https://github.com/Dennis-Otto/repo-blueprint/blob/main/SECURITY.md) beschreibt.

## Lizenz

[MIT No Attribution](https://github.com/Dennis-Otto/repo-blueprint/blob/main/LICENSE): Repositories aus dem Blueprint schulden ihm nichts, nicht einmal einen Hinweis. Jede Datei nennt ihre Lizenz in der maschinenlesbaren Form von [REUSE](https://reuse.software).
