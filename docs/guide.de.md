# Anleitung

Wie man ein Repository anlegt, die Arten von Projekten, was jedes Repository bekommt und was eine Person einmal einrichtet.

## Ein Repository anlegen

--8<-- "README.de.md:quick-start"

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="images/diagrams/how-a-new-repository-starts.de.dark.svg">
  <img src="images/diagrams/how-a-new-repository-starts.de.svg" alt="Wie ein neues Repository beginnt: copier copy schreibt die Dateien des Projekts und führt keinen Code des Blueprints aus. python3 .github/blueprint.py create, das jede Kopie mitbringt, macht den ersten Commit auf dem Branch main mit Sign-off, legt das Repository mit gh repo create an und pusht dorthin, wendet die Einstellungen als Code an und zeigt die Checkliste. Du erledigst die Schritte, die nur eine Person erledigen kann, etwa die Release-App und die Secrets, und dann laufen die Prüfungen und die Bots.">
</picture>

### Was create zuerst prüft

`create` prüft zuerst, was seine Schritte brauchen, in seiner Vorabprüfung (*preflight*), die nur fragt: Python ab 3.12, Git und den Namen und die E-Mail-Adresse des ersten Commits, die GitHub CLI ab 2.48, angemeldet mit den Scopes `repo` und `workflow`, und `read:org` für eine Organisation, einen Eigentümer, bei dem dieses Konto das Repository anlegen darf, und einen Namen, den GitHub noch nicht hat. Ein Befund mit ✘ hält es an, bevor etwas entsteht, und nennt den Befehl, der ihn behebt, etwa `gh auth refresh --hostname github.com --scopes workflow`; `python3 .github/blueprint.py doctor` führt die Vorabprüfung allein aus, und `create --dry-run` zeigt die Vorabprüfung und die Befehle und führt keinen aus. [Die Fehlerbehebung](troubleshooting.md) erklärt jeden Befund. Hört ein Lauf mittendrin auf, beim Push oder bei den Einstellungen, starte `create` noch einmal: In einem Ordner, dessen `origin` zum Repository auf GitHub pusht, macht es beim ersten Schritt weiter, der noch fehlt, dem Push, wenn GitHub noch keinen Branch `main` hat, dann den Einstellungen und der Checkliste. `create` lehnt einen Ordner ab, der zu einem anderen Repository pusht. Jeder Workflow läuft auf `main`, deshalb nennt `settings check` ein Repository, dessen Standard-Branch anders heißt.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="images/diagrams/how-create-checks-first-and-goes-on-where-it-stopped.de.dark.svg">
  <img src="images/diagrams/how-create-checks-first-and-goes-on-where-it-stopped.de.svg" alt="Wie create zuerst prüft und dort weitermacht, wo es aufgehört hat: python3 .github/blueprint.py create beginnt mit seiner Vorabprüfung, die nur fragt: Python, Git und die Identität des ersten Commits, die GitHub CLI und ihre Anmeldung mit den Scopes repo und workflow, den Eigentümer und den Namen. Ein Befund mit ✘ hält es an, bevor etwas entsteht, und nennt den Befehl, der ihn behebt; python3 .github/blueprint.py doctor zeigt dasselbe allein. Eine neue Kopie bekommt dann git init, ihren ersten Commit und gh repo create mit dem Push. Ein Ordner, dessen origin schon zum Repository auf GitHub pusht, von einem Lauf, der mittendrin aufgehört hat, bekommt nur den Push, wenn GitHub noch keinen Branch main hat. Beide enden mit settings apply und der Checkliste.">
</picture>

### Was create nach seinem Push nachsieht

GitHub startet einen Workflow erst, wenn es ihn registriert hat, und der erste Push eines neuen Repositorys registriert womöglich keinen ([#652](https://github.com/Dennis-Otto/repo-blueprint/issues/652)). Ein Lauf registriert seinen Workflow, also lernt GitHub jeden Workflow, den ein Push oder ein Pull Request startet, bei seinem ersten Lauf kennen; einer, den nur ein Zeitplan, ein Release oder eine Person startet, bleibt aber unbekannt, etwa der Blueprint-Bot: `gh workflow run` antwortet für ihn mit 404, nicht einmal sein Zeitplan startet ihn, und der Rollout kann ihm kein Release bringen. Deshalb fragt `create` nach seinem Push GitHub bis zu einer Minute lang, ob es jeden Workflow aus `.github/workflows/` kennt, und führt für die, die es nicht kennt, `python3 .github/blueprint.py workflows register` aus. Das öffnet einen Pull Request vom Branch `bot/register-workflows` mit einem Commit, den GitHub signiert und der ans Ende jedes solchen Workflows einen Kommentar von drei Zeilen anhängt. Sein Merge ist ein Push, der sie ändert, und registriert sie. Führst du den Befehl nach dem Merge noch einmal aus, öffnet er den Pull Request, der die Kommentare wieder herausnimmt, sodass die Dateien wieder die des Blueprints sind; solange einer der beiden offen ist, nennt er diesen. Der Branch ist einer eines Bots, deshalb gibt die Prüfung der Dateien des Blueprints keinem von beiden einen Hinweis. Die Checkliste nennt jeden Workflow, den GitHub nicht kennt, und jeden Kommentar, der noch übrig ist, und der Befehl repariert ein älteres Repository genauso.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="images/diagrams/how-github-comes-to-know-every-workflow.de.dark.svg">
  <img src="images/diagrams/how-github-comes-to-know-every-workflow.de.svg" alt="Wie GitHub jeden Workflow eines neuen Repositorys kennenlernt: GitHub startet einen Workflow erst, wenn es ihn registriert hat, und der erste Push eines neuen Repositorys registriert womöglich keinen; ein Lauf registriert seinen Workflow, also bleiben die unbekannt, die nur ein Zeitplan, ein Release oder eine Person startet. Nach seinem Push fragt python3 .github/blueprint.py create GitHub bis zu einer Minute lang, ob es jeden Workflow aus .github/workflows/ kennt. Für jeden, den es nicht kennt, führt create python3 .github/blueprint.py workflows register aus, das einen Pull Request mit einem Commit öffnet, den GitHub signiert, mit einem Kommentar am Ende jedes solchen Workflows. Sein Merge ist ein Push, der sie ändert, und registriert sie. Erneut ausgeführt, öffnet der Befehl den Pull Request, der die Kommentare wieder herausnimmt, und die Dateien sind wieder die des Blueprints. Dann startet jeder Workflow bei seinem Push, seinem Zeitplan, seinem Release oder von Hand.">
</picture>

## Arten von Projekten

--8<-- "README.de.md:kinds"

## Was ein neues Repository bekommt

Jede dieser Seiten beschreibt eine Gruppe dessen, was jedes Repository bekommt: was läuft, die Dateien, die es ausführen, und die Einzelheiten.

- [Prüfungen und der PR-Coach](features/checks.md): Was in jedem Pull Request und auf `main` läuft, wie lange es dauert und wie sich eine Prüfung erklärt, die scheitert.
- [Fix-Bot und Selbstheilung](features/self-healing.md): Was ein Repository selbst repariert: die Befunde, die ein Befehl beheben kann, Tests, die einmal scheitern, Prüfungen, die abbrechen, Releases und Bots, die fehlschlagen.
- [Mutationstests, Fuzzing und Property-Tests](features/tests.md): Die Tests über die Prüfungen eines Pull Requests hinaus: ob die Tests eine Änderung des Codes bemerken, und Eingaben, die niemand aufgeschrieben hat.
- [Releases und Sicherheit](features/releases.md): Wie aus einer Änderung ein signiertes Release wird, und die Sicherheitsprüfungen jedes Repositorys.
- [Abhängigkeiten und Updates](features/updates.md): Wie die Abhängigkeiten und die Dateien des Blueprints aktuell bleiben, und welche Dateien dem Projekt gehören.
- [Bots, ihre Kosten und das Dashboard](features/bots.md): Die Bots der Issues und Pull Requests, was sie startet und was sie kosten, und das Dashboard aller Repositorys.
- [Website, Diagramme und Screenshots](features/website.md): Die Website der Dokumentation, und die Diagramme und Screenshots, die sich selbst aktuell halten.
- [Einstellungen als Code](features/settings.md): Die Einstellungen eines Repositorys als Datei, die ein Pull Request ändert.
- [Community und Entwicklung](features/development.md): Die Dateien der Community, der Dev-Container und die Regeln für Coding-Agents.

## Ein Repository einrichten

Was eine Person einmal erledigt: die Release-App des Kontos und seine Vorgaben, die Secrets und die Auslieferung jedes Repositorys und den Weg, auf dem ein bestehendes Repository den Blueprint übernimmt.

### Dein eigenes Konto

Der Blueprint funktioniert für jedes Konto und jede Organisation auf GitHub, und ein Repository daraus nennt nichts vom Eigentümer des Blueprints außer den Links auf den Blueprint. Jeder Eigentümer bringt zwei eigene Dinge mit:

- **Eine Release-App,** einmal für alle seine Repositories. Die Bots handeln als GitHub App des Eigentümers: Ihr Token startet die Prüfungen der Release- und Update-Pull-Requests, darf Workflows ändern und legt die Release-Tags an, was das Token eines Jobs nicht kann. Nur der Eigentümer einer App hat ihren privaten Schlüssel, deshalb kann der Blueprint seine eigene nicht verleihen. Kopiere den Blueprint und lass die Frage nach der Release-App leer, dann registriert sie nach `create` ein Befehl auf deinem Konto oder deiner Organisation, mit Name und Berechtigungen vorausgefüllt und ohne Webhook:

  ```sh
  python3 .github/blueprint.py app register
  ```

  Du bestätigst eine Seite auf GitHub. Der Befehl setzt den privaten Schlüssel, den keine Datei hält, und öffnet den Pull Request, der die App in `.github/repository.toml` nennt, wo nur sie Release-Tags anlegen darf; du installierst die App und mergst den Pull Request, wie [die Schritt-für-Schritt-Anleitung](own-account.md#3-die-release-app-registrieren) zeigt. `app connect --key-file DATEI` tut dasselbe für eine vorhandene App, etwa für ein weiteres Repository. Bis dahin prüft jeder Bot, der als die App handelt, zuerst, ob es sie gibt, und sagt in seiner Zusammenfassung, was fehlt, die Variable oder der private Schlüssel, statt an einem Token zu scheitern: Ein Bot, dessen Arbeit die der App ist, wie der Blueprint-Bot, der Settings-Bot oder Renovate, schlägt fehl, und einer, der einem Pull Request nur weiterhilft, wie der Fix-Bot oder der Branch-Bot, warnt und macht ohne sie weiter.
- **Deine Vorgaben,** damit jedes neue Repository nur fragt, was neu ist. Die [Einstellungsdatei](https://copier.readthedocs.io/en/stable/settings/) von Copier nimmt die Antworten auf, die gleich bleiben, unter Windows in `%LOCALAPPDATA%\copier\settings.yml` und unter macOS in `~/Library/Application Support/copier/settings.yml`:

  ```yaml
  # ~/.config/copier/settings.yml, oder die Datei, die COPIER_SETTINGS_PATH nennt
  defaults:
    owner: octo-org
    author: Octo Org
    release_app: octo-org-release-automation
    release_app_client_id: Iv23liExample
    release_app_id: "123456"
  ```

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="images/diagrams/how-an-owner-gets-a-release-app.de.dark.svg">
  <img src="images/diagrams/how-an-owner-gets-a-release-app.de.svg" alt="Wie ein Eigentümer zu seiner Release-App kommt: Du kopierst den Blueprint und lässt die Frage nach der Release-App leer. python3 .github/blueprint.py app register registriert die App auf deinem Konto oder deiner Organisation: Du bestätigst eine Seite, der Befehl setzt den privaten Schlüssel und öffnet den Pull Request, der die App nennt. Du installierst die App und mergst den Pull Request. Dann setzt settings apply die Variablen und das Ruleset der Release-Tags, und die Bots laufen als deine App; bis dahin sagt jeder Bot, der als sie handelt, in seiner Zusammenfassung, was fehlt.">
</picture>

Zwei weitere Antworten entscheiden, was für dich läuft, und die Seite [Dein eigenes Konto](https://dennis-otto.github.io/repo-blueprint/de/own-account.html) führt durch jeden Schritt:

- **Renovate,** nach der Antwort `renovate_runner`. Der Eigentümer des Blueprints behält `hub`, den Renovate-Workflow des Blueprints, der es für jedes seiner Repositorys ausführt. Jeder andere Eigentümer bekommt `self`: `.github/workflows/renovate.yml`, denselben Workflow mit demselben Renovate, gepinnt auf seinen Digest, der es alle zwei Stunden als Release-App ausführt, mit einem Token nur für dieses Repository, und den Bot-Benutzer der App als Autor seiner Commits nennt. In einem Pull Request, der die Regeln oder eine Lock-Datei ändert, zeigt seine Prüfung *renovate rules*, ob Renovate die Regeln annimmt und jede Datei liest, und erklärt ein Scheitern über den PR-Coach, wie jede andere Prüfung. Mit `mend` installiert der Eigentümer stattdessen die [Mend-Renovate-App](https://github.com/apps/renovate), die bei jedem Push kommt und keinen Workflow braucht. Jeder Weg liest dieselben Regeln, und `checklist` hakt Renovate ab, sobald es einen Pull Request geöffnet hat.
- **Die KI des Issue-Assistenten,** nach der Antwort `issue_assistant_ai`: Ohne sie ist die Variable `ISSUE_ASSISTANT_AI` `off`, das Environment `issue-assistant` fragt nach keinem Secret, `SUPPORT.md` sagt, dass keine KI die Issues liest, und das README eines neuen Repositorys zeigt kein Badge des Issue-Assistenten; Labels, Erinnerungen, Schließen und die Befehle des Maintainers laufen weiter, und die Checkliste besteht ohne ein Token von Claude.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="images/diagrams/who-runs-renovate.de.dark.svg">
  <img src="images/diagrams/who-runs-renovate.de.svg" alt="Wer Renovate ausführt: Die Antwort renovate_runner entscheidet, wer Renovate für ein Repository ausführt. Der Eigentümer des Blueprints behält den Hub, den Renovate-Workflow des Blueprints, der es für jedes seiner Repositorys ausführt, auf dem die Release-App installiert ist. Jeder andere Eigentümer bekommt einen Renovate-Workflow im Repository selbst, der es alle zwei Stunden als Release-App ausführt, nur für dieses Repository, mit demselben Renovate und denselben Regeln; oder er installiert die Mend-Renovate-App, die keinen Workflow braucht und bei jedem Push kommt. Jeder Weg liest die Regeln aus .github/renovate.json5 und öffnet die Updates als Pull Requests, deren Checks entscheiden, ob sie gemergt werden.">
</picture>

### Einmal pro Repository

- **Die Release-App** des Eigentümers öffnet die Release- und Update-Pull-Requests, damit ihre Prüfungen laufen. Registriere sie einmal für das Konto, wie [Dein eigenes Konto](#dein-eigenes-konto) zeigt, installiere sie auf dem Repository und hinterlege ihren privaten Schlüssel als Secret `RELEASE_AUTOMATION_PRIVATE_KEY` im Environment `release`. Die App braucht die Berechtigungen *Actions*, *Administration*, *Checks*, *Commit statuses*, *Contents*, *Dependabot alerts*, *Issues*, *Pages*, *Pull requests*, *Variables* und *Workflows* (Lesen und Schreiben) sowie *Environments* und *Secrets* (Lesen): Damit wendet der Settings-Bot die Einstellungen als Code an, Renovate aktualisiert die Abhängigkeiten, der OSV-Scanner-Workflow schließt die Dependabot-Alerts der Advisories, die eine `osv-scanner.toml` akzeptiert, und der Rollout des Blueprints startet nach einem Release den Blueprint-Bot jedes Repositorys. Renovate bekommt ein Token ohne *Administration* und der Settings-Bot eines mit nur *Administration*, *Issues*, *Pages* und *Variables* (Lesen und Schreiben) sowie *Actions*, *Contents* und *Environments* (Lesen), das weder einen Commit pushen noch einen Workflow ändern kann; einer App, der eine davon fehlt, verweigert GitHub dieses Token, und die Zusammenfassung des Laufs nennt die Berechtigungen, die sie braucht (Entscheidung 0075 der [Entscheidungen](https://github.com/Dennis-Otto/repo-blueprint/blob/main/docs/decisions/README.md)). Eine optionale zweite App, die Settings-App, übernimmt die Verwaltung: Mit ihrer Client ID in der Variable `SETTINGS_APP_CLIENT_ID` und ihrem privaten Schlüssel im Secret `SETTINGS_APP_PRIVATE_KEY` des Environments `release` fragt der Settings-Bot stattdessen sie nach diesem Token, der Blueprint-Bot lässt die Actions eines neuen Releases starten, bevor er das Update pusht, und die Release-App braucht kein *Administration*, *Pages*, *Variables*, *Environments* und *Secrets*, wie [Dein eigenes Konto](https://dennis-otto.github.io/repo-blueprint/de/own-account.html) zeigt. Der Release-Workflow legt jeden Release-Tag mit der App an, und das Ruleset *Release tag creation* lässt niemand anderen einen anlegen; die Variablen `RELEASE_APP`, `RELEASE_AUTOMATION_CLIENT_ID` und `RELEASE_AUTOMATION_APP_ID` in `.github/repository.toml` nennen die App, aus den Antworten `release_app`, `release_app_client_id` und `release_app_id`, und ein Projekt mit einer anderen App, als seine Antworten nennen, setzt sie in `.github/repository.project.toml`.
- **Der Issue-Assistent** braucht `CLAUDE_CODE_OAUTH_TOKEN` im Environment `issue-assistant`, außer die Antwort `issue_assistant_ai` hat seine KI ausgeschaltet.
- **Auslieferung:** Trusted Publishing auf PyPI oder npm, das App-Zertifikat einer Nextcloud-App oder die Einreichung bei HACS, wie es die Checkliste sagt.
- **Die Social Preview:** Ein neues Repository beginnt mit einer Zeichnung seiner Art von Projekt in `.github/social-preview.html`, aus seinen Antworten gemacht, wo der Blueprint nicht mehr von ihm weiß: dem Schritt `uses:` einer Action in einem Workflow, dem `pip install` oder `npm install` eines Pakets, dem `docker run` eines Images, einer Anfrage an einen Worker und seiner Antwort, dem Popup einer Erweiterung in der Symbolleiste, der App in der Navigation von Nextcloud, den Entitäten einer Integration oder dem Anfang der README. Ersetze dieses Panel, das `data-default-panel` markiert, durch das Projekt selbst: einen Screenshot dessen, was es zeigt, oder eine getreue Zeichnung dessen, was es hervorbringt. Rendere das Bild dann mit `bash scripts/social-preview.sh` und lade `.github/social-preview.png` unter *Settings → General → Social preview* hoch; die Checkliste nennt beide Schritte, bis sie erledigt sind ([Entscheidung 0127](decisions/0127-a-new-social-preview-draws-its-kind-of-project.md)). GitHub nimmt das Bild nur aus diesem Upload, also braucht ein Bild, das sich später ändert, einen weiteren: Der Schritt *Social preview uploaded and current* der Checkliste vergleicht den Upload Byte für Byte mit dem committeten Bild, und der nächtliche Blick des Bots für den Zustand der Bots hält das Issue *Upload the new social preview* mit dem Bild und dem Link offen, bis GitHub es zeigt. Ein privates Repository wartet mit beidem, bis es öffentlich ist, da GitHub die Social Preview nur für ein öffentliches zeigt ([Entscheidung 0132](decisions/0132-the-bot-health-bot-asks-for-the-upload-of-a-new-social-preview.md)).
- **OpenSSF Best Practices:** Lege das Projekt auf [bestpractices.dev](https://www.bestpractices.dev/en/projects/new) mit der URL des Repositorys an. bestpractices.dev schlägt die Antworten aus `.bestpractices.json` vor, etwa 100 des Badges und der OSPS Baseline, die der Blueprint für die Art des Projekts garantiert, jede mit der Datei, die sie belegt; *Save (and continue) 🤖* übernimmt sie auf jeder Stufe, auch nach einem Update der Datei. Beantworte den Rest, was nur deine Software und deine Leute sagen können, und setze beide Badges in die README, wie es die Checkliste zeigt. Diese Antworten überlässt der Blueprint dir, wie [Entscheidung 0129](decisions/0129-the-blueprint-answers-what-it-guarantees-of-the-baseline-and-of-gold.md) erklärt. **Deine Leute:** die Zwei-Faktor-Authentifizierung aller mit Zugriff (OSPS-AC-01.01, *secure_2FA*), eine zweite Person, die jede Änderung von `main` freigibt (OSPS-QA-07.01, *two_person_review*), Mitwirkende verschiedener Organisationen (*contributors_unassociated*) und ein Sicherheitsreview (*security_review*). Gib für ein Projekt mit nur einem Maintainer nie einen zweiten Reviewer an. **Deine anderen Repositorys:** N/A für OSPS-QA-04.01 und OSPS-QA-04.02, wenn jedes Release allein aus diesem Repository gebaut wird; sonst liste die Repositorys auf, deren Code in ein Release eingeht, etwa in der README, jedes mit so strengen Prüfungen wie diese. **Deine Dateien:** ein Copyright- und ein Lizenzvermerk in jeder Quelldatei (*copyright_per_file*, *license_per_file*), die `REUSE.toml` stattdessen für alle Dateien auf einmal angibt; die Abdeckung der Tests (*test_statement_coverage80*, *test_statement_coverage90*, *test_branch_coverage80*), die dein Projekt für den Code festlegt, den es misst; und ein reproduzierbarer Build (*build_reproducible*), N/A, wenn nichts gebaut wird.

`checklist` gibt die `gh secret set`-Befehle aus; der Wert wird in die Abfrage der GitHub CLI eingegeben und erscheint nirgends sonst.

### Ein bestehendes Repository

Ein bestehendes Repository übernimmt den Blueprint auf einem Branch, in einem Pull Request:

1. `uvx --from copier==9.19.1 copier copy --overwrite --vcs-ref vX.Y.Z --data sample_code=false gh:Dennis-Otto/repo-blueprint .` mit den Antworten, die zum Repository passen, ohne den Beispielcode und die Beispieltests eines neuen, etwa Beschreibung, Topics und Homepage wie auf GitHub, damit `settings apply` dort nichts ändert. Die Dateien des Projekts (README, Changelog, Code, Tests, Manifeste, Labels, Issue-Formulare, Icons) bleiben, wie sie sind.
2. Den Diff jeder Datei des Blueprints ansehen und zurückholen, was nur dem Projekt gehört: Abschnitte von SECURITY.md oder CONTRIBUTING.md, Regeln von Renovate (in `.github/renovate.json5`), Hosts des Issue-Assistenten, Ignore-Regeln. `copier update` behält diese Änderungen von da an.
3. Die Version des letzten Releases in `version.txt` und `.release-please-manifest.json` schreiben, `CHANGELOG.md` mit `## Unreleased` beginnen und `.github/labels.toml` die Labels der Bots geben (`autorelease: pending`, `autorelease: tagged`, `merge-conflict`, `maintenance`, `bot-failure`, `docker`).
4. Die Prüfungen nur dieses Projekts, etwa seine End-to-End-Tests, in `.github/repository.project.toml` und `scripts/check-project.sh` eintragen, mit den Mustern der Actions, die seine eigenen Workflows ausführen und die `blueprint.py settings check` nennt; die Workflows, Skripte und Tests entfernen, die der Blueprint ersetzt, und Dateien der Vorlage löschen, die das Projekt nicht braucht, etwa einen Beispieltest. Ein Repository ohne `docs/` hat keine Website, bis es `docs/index.md` schreibt; `mkdocs.yml` zeigt, wie deutsche Seiten dazukommen.
5. Den Pull Request öffnen. Sobald seine neuen Prüfungen bestehen, stellt `blueprint.py settings apply` die Pflicht-Prüfungen, Variablen und Labels um, und der Pull Request kann mergen.

Die Konfiguration der Prüfungen gehört dem Blueprint und sucht den Code dort, wo ihn ein neues Projekt derselben Art hat. Jede Datei, die sie nennt, kommt mit dem Blueprint, auch ohne den Beispielcode:

| Art | Code | Tests | Vom Blueprint |
| --- | --- | --- | --- |
| Nextcloud-App | `lib/` | PHPUnit-Tests in `tests/Unit/` | `psalm.xml` und `phpunit.xml`, mit den `tests/bootstrap.php` und `tests/stubs/`, die sie laden |
| Node-Paket | `src/`, gebaut nach `dist/` | `test/`, von `tsconfig.json` typgeprüft; das `npm test` eines neuen Projekts führt `test/**/*.test.ts` aus | `tsconfig.json` und `tsconfig.build.json`, die `typescript` und `@types/node` in der `package.json` des Projekts brauchen, und `biome.jsonc`, dessen Schritt *Lint and format* läuft, sobald dort auch `@biomejs/biome` steht |
| Chrome-Erweiterung | `src/`, gebaut nach `extension/lib/`; `extension/` mit `manifest.json` und `_locales/` | `test/`, wie bei einem Node-Paket | die Dateien eines Node-Pakets, wobei `tsconfig.build.json` nach `extension/lib/` schreibt; der Schritt *Extension* braucht `extension/manifest.json`, `store/permissions.json` und eine `store/listing.<Sprache>.md` für jede Sprache |
| Cloudflare Worker | `src/`, mit dem Hauptmodul, das `wrangler.jsonc` (oder `wrangler.json`, `wrangler.toml`) nennt | `test/**/*.test.ts`, ausgeführt in workerd | `vitest.config.ts` und `tsconfig.json`, die `wrangler`, `vitest`, `@vitest/coverage-istanbul` und `@cloudflare/vitest-plugin` in `package.json` brauchen und das Skript `typecheck` als `wrangler types && tsc`; `scripts/deploy-worker.sh`, den Deploy-Befehl von Workers Builds |

Die anderen Arten legen diese Orte in eigenen Dateien fest, etwa in `pyproject.toml`. Was in `tests/` liegt, gehört dem Projekt: Die Kopie und jedes Update ergänzen dort nur die Dateien, die fehlen, und eine App mit eigenem Bootstrap behält ihn.
