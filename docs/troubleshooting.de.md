---
description: "Was zu tun ist, wenn in einem Repository von Repo Blueprint etwas nicht funktioniert: ein create, das bei seiner Vorabprüfung oder mittendrin anhält, ein Update mit Konflikten, eine Pflichtprüfung, die nie berichtet, settings apply ohne Administratorrechte, ein Settings-Bot, dessen Token die Release-App verweigert, ein Schalter der Sicherheit, den GitHub aus lässt, ein Release-Pull-Request ohne Prüfungen, Renovate, das keine Updates öffnet, und OSV-Scanner, der eine Version meldet, die ein anderes Paket festlegt."
---

# Fehlerbehebung

Die meisten Probleme erklären sich dort, wo sie auftreten: Eine Prüfung, die scheitert, sagt in ihrer Zusammenfassung und im Bericht des PR-Coachs, was sie gefunden hat und wie man es behebt, ein Bot sagt in der Zusammenfassung seines Laufs, was fehlt, und der Bot-Health-Bot hält für jeden Bot, der auf `main` scheitert, ein Issue offen. Diese Seite behandelt, was darüber hinaus eine Person braucht. Die häufigen Fragen stehen auf der Seite [Fragen und Antworten](faq.md).

## create hält bei seiner Vorabprüfung an

**Was du siehst:** `python3 .github/blueprint.py create` zeigt *The preflight of OWNER/NAME* mit einer Zeile mit ✘ und darunter dem Befehl, der sie behebt, und endet mit *the preflight found 1 problem that would stop create, which made nothing*.

**Warum:** Vor seinem ersten Schritt prüft `create`, was seine Schritte brauchen, damit ein fehlendes Werkzeug oder Recht kein halb fertiges Repository hinterlässt. Die Vorabprüfung fragt git und gh nur, und `create` macht nichts, solange ein Befund ein ✘ trägt. Ein Befund mit · ist einer, auf den GitHub nicht geantwortet hat oder den die Vorabprüfung nicht erkennen kann, und er hält nichts an. `python3 .github/blueprint.py doctor` führt die Vorabprüfung allein aus, und `create --dry-run` zeigt sie mit den Befehlen.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="images/diagrams/how-create-checks-first-and-goes-on-where-it-stopped.de.dark.svg">
  <img src="images/diagrams/how-create-checks-first-and-goes-on-where-it-stopped.de.svg" alt="Wie create zuerst prüft und dort weitermacht, wo es aufgehört hat: python3 .github/blueprint.py create beginnt mit seiner Vorabprüfung, die nur fragt: Python, Git und die Identität des ersten Commits, die GitHub CLI und ihre Anmeldung mit den Scopes repo und workflow, den Eigentümer und den Namen. Ein Befund mit ✘ hält es an, bevor etwas entsteht, und nennt den Befehl, der ihn behebt; python3 .github/blueprint.py doctor zeigt dasselbe allein. Eine neue Kopie bekommt dann git init, ihren ersten Commit und gh repo create mit dem Push. Ein Ordner, dessen origin schon zum Repository auf GitHub pusht, von einem Lauf, der mittendrin aufgehört hat, bekommt nur den Push, wenn GitHub noch keinen Branch main hat. Beide enden mit settings apply und der Checkliste.">
</picture>

**Was zu tun ist:** Führe den Befehl unter dem Befund aus, dann noch einmal `create`.

- **Python vor 3.12:** Die Werkzeuge des neuen Repositorys, etwa seine Lock-Dateien, brauchen Python ab 3.12. Installiere es von [python.org](https://www.python.org/downloads/); unter Windows startet `py -3` es.
- **Git ist nicht installiert:** Installiere es von [git-scm.com](https://git-scm.com/downloads).
- **Git hat keinen Namen oder keine E-Mail-Adresse für den Commit:** `git config --global user.name "Dein Name"` und `git config --global user.email "du@example.com"`. Der Sign-off des ersten Commits nennt sie.
- **Die GitHub CLI vor 2.48, oder keine:** Installiere oder aktualisiere sie, wie [ihre Installation](https://github.com/cli/cli#installation) es beschreibt.
- **gh ist nicht bei github.com angemeldet:** `gh auth login --hostname github.com --scopes workflow`. Mit einem Token in der Variable `GH_TOKEN` nutzt gh dieses: Gib ihm die Scopes, oder entferne die Variable.
- **Ohne die Scopes, die create braucht:** `gh auth refresh --hostname github.com --scopes workflow,read:org`, mit den Scopes, die der Befund nennt. `repo` legt das Repository an und pusht, `workflow` pusht die Dateien in `.github/workflows/` über HTTPS, die GitHub ohne ihn ablehnt (mit `ssh` als Git-Protokoll von gh pusht sie der Schlüssel, und die Vorabprüfung fragt nicht nach `workflow`), und `read:org` zeigt, ob dir die Organisation gehört. Ein Fine-grained Token nennt keine Scopes, deshalb kann die Vorabprüfung es nicht erkennen (·): Es muss Repositorys des Eigentümers anlegen dürfen, mit *Administration*, *Contents* und *Workflows* (Lesen und Schreiben).
- **GitHub hat kein Konto und keine Organisation dieses Namens:** Der Eigentümer in den Antworten ist falsch geschrieben. Nenne das Repository mit `python3 .github/blueprint.py --repo OWNER/NAME create`.
- **Ein eigenes Konto, während gh als ein anderes angemeldet ist:** Nur dieses Konto legt seine Repositorys an. `gh auth switch --user OWNER` wechselt zu ihm, wenn gh es kennt, `gh auth login` meldet es an.
- **Kein Mitglied der Organisation, oder eingeladen:** Ein Owner der Organisation nimmt dich auf, oder du nimmst die Einladung unter `https://github.com/orgs/OWNER/invitation` an.
- **Ein Mitglied der Organisation, kein Owner (·):** `gh repo create` klappt, wo die Organisation ihren Mitgliedern erlaubt, Repositorys anzulegen, und dann bist du Administrator des Repositorys, das du angelegt hast, was `settings apply` braucht. Sonst startet ein Owner `create`.
- **Der Name ist vergeben:** Wähle einen anderen mit `--repo OWNER/NAME`. Ist es das Repository, das ein früherer Lauf von `create` angelegt hat, verbinde den Ordner mit `git remote add origin https://github.com/OWNER/NAME.git` damit und starte `create` noch einmal, das dort weitermacht.
- **origin pusht zu einem Repository, das GitHub nicht hat:** Es wurde gelöscht, oder die Adresse ist falsch. `git remote remove origin`, dann noch einmal `create`.

## create hat mittendrin aufgehört

**Was du siehst:** `create` hat nach `gh repo create` aufgehört, beim Push oder bei `settings apply`, etwa bei einer Verbindung, die abbrach, und der Ordner pusht jetzt zu `origin`.

**Warum:** `gh repo create` legt das Repository auf GitHub an und fügt `origin` hinzu, bevor es pusht, deshalb hinterlassen ein Push oder Einstellungen, die scheiterten, ein Repository, das da ist.

**Was zu tun ist:** Starte `python3 .github/blueprint.py create` noch einmal. Pusht `origin` zum Repository der Antworten, und GitHub hat es, macht `create` beim ersten Schritt weiter, der noch fehlt: dem Push von `main`, wenn GitHub noch keinen Branch `main` hat, angemeldet durch gh wie bei `gh repo create --push`, dann `settings apply` und die Checkliste, die nur ändern, was abweicht. Ein Ordner, der zu einem anderen Repository pusht, ist keine neue Kopie, und `create` lehnt ihn ab.

## Ein Update des Blueprints hat Konflikte

**Was du siehst:** Der Pull Request des Blueprint-Bots vom Branch `blueprint/update` hat das Label `merge-conflict`, und sein Auto-Merge ist aus. Seine Beschreibung enthält eine Checkliste der Dateien, die zu lösen sind.

**Warum:** Das Repository hat Zeilen einer Datei des Blueprints geändert, die auch das neue Release ändert. `copier update` führt beides Zeile für Zeile zusammen und hinterlässt Konfliktmarker (`<<<<<<<`, `=======`, `>>>>>>>`), wo es das nicht kann.

**Was zu tun ist:** Löse die Marker auf dem Branch des Pull Requests und pushe:

```sh
git fetch origin && git switch blueprint/update
# Jede Datei der Checkliste bearbeiten: behalten, was das Repository von beiden Seiten braucht.
bash scripts/check.sh   # scheitert an einem Konfliktmarker, der übrig ist
git commit -s -am "Resolve the conflicts of the blueprint update"
git push
```

Sobald du auf seinen Branch committest, überlässt der Bot dir den Branch: Ist ein neueres Release da, sagt er es in einem Kommentar, und nachdem du den Pull Request gemergt oder geschlossen hast, bringt sein nächster Lauf den Rest. Um neu anzufangen oder die Konflikte erst auf deinem Rechner zu sehen, führe das Update mit demselben Copier wie der Bot aus, dessen Version und Hashes `.github/copier-requirements.txt` festlegt. Lege seine virtuelle Umgebung außerhalb des Checkouts an und starte von einem aktuellen `main` auf einem eigenen Branch: Copier bricht mit *Destination repository is dirty* ab, solange der Arbeitsbaum eine Änderung oder eine Datei enthält, die Git nicht ignoriert, und auf `blueprint/update` nennen die Antworten schon das neue Release.

```sh
python3 -m venv ~/.venvs/copier
~/.venvs/copier/bin/pip install --require-hashes -r .github/copier-requirements.txt
git switch main && git pull
git status --short   # muss leer bleiben: committe oder stashe, was es zeigt
git switch -c blueprint/local
~/.venvs/copier/bin/copier update --defaults --conflict inline
```

Unter Windows legst du die Umgebung mit `py -3 -m venv %USERPROFILE%\.venvs\copier` an und startest ihre Programme aus `%USERPROFILE%\.venvs\copier\Scripts\` statt aus `~/.venvs/copier/bin/`.

`--defaults` nimmt die Antworten aus `.copier-answers.yml`, und `--conflict inline` schreibt die Marker wie der Bot in die Dateien, statt Dateien mit abgelehnten Änderungen daneben. Eine Änderung, die ein Projekt in einer Datei des Blueprints behält, hat bei jedem Update, das dieselben Zeilen berührt, wieder Konflikte; verlege sie in eine Datei des Projekts, wo es eine gibt, wie die [Fragen und Antworten](faq.md#welche-dateien-darf-ein-projekt-ändern) zeigen.

## Eine Pflichtprüfung berichtet nie

**Was du siehst:** Ein Pull Request wartet auf eine Prüfung mit *Expected — Waiting for status to be reported*, und kein Lauf von ihr startet oder endet.

**Warum, und was zu tun ist:**

- **Ein Update hat eine Pflichtprüfung umbenannt.** Das Ruleset *Protect main* verlangt noch den alten Namen, den kein Workflow mehr meldet. Checke den Branch des Pull Requests aus und führe dort `python3 .github/blueprint.py settings apply` aus, gleich bevor du ihn mergst, damit das Ruleset die neuen Namen verlangt; der Einstellungs-Bot wendet dasselbe nach dem Merge an.
- **Der Workflow ist nicht gestartet.** Sein Lauf unter *Actions* zeigt einen *startup failure*, wenn er eine Action nutzt, die in der Liste der erlaubten Actions fehlt. Die Prüfung *lint* des Pull Requests nennt jede schon, und ebenso `python3 .github/blueprint.py settings check`; trage ihr Muster für einen Workflow des Projekts in `[actions.selected]` von `.github/repository.project.toml` ein und wende die Einstellungen an. Ein Schritt mit `uses: docker://…` scheitert genauso, weil GitHub das Image als Action zählt, die kein Muster erlaubt: Starte es stattdessen in einem `run:`-Schritt mit dem `docker run --rm`, das die Prüfung nennt.
- **Der Pull Request kommt von einem Token, das keinen Workflow startet,** etwa dem Token eines Jobs: siehe [Der Release-Pull-Request hat keine Prüfungen](#der-release-pull-request-hat-keine-prüfungen).
- **Der Pull Request kommt aus dem Fork eines externen Beitragenden:** Seine Workflows warten auf einen Maintainer, der sie mit *Approve and run* am Pull Request startet.
- **Eine Prüfung allein dieses Projekts,** die `.github/repository.project.toml` verlangt, läuft in einem Workflow mit Pfadfilter, sodass ein Pull Request, der andere Dateien ändert, sie nie startet. Eine Pflichtprüfung läuft in jedem Pull Request: Entferne den Filter, oder lass den Job in seinen Schritten entscheiden, was er überspringt, damit er trotzdem Erfolg meldet.

## Die Einstellungen ohne Administratorrechte anwenden

**Was du siehst:** `python3 .github/blueprint.py settings apply` endet mit Zeilen wie *the rulesets could not be applied: … the token may lack the permission Administration (read and write)*.

**Warum:** Die meisten Einstellungen als Code, etwa die Rulesets, die Sicherheit und die Berechtigungen von Actions, brauchen einen Administrator des Repositorys. `blueprint.py` nutzt das Konto, mit dem `gh auth login` angemeldet ist, und wendet jeden Teil an, den GitHub annimmt; jeden Teil, den GitHub abgelehnt hat, nennt es mit der Berechtigung, die er braucht.

**Was zu tun ist:**

- **Lass den Einstellungs-Bot sie anwenden:** Er läuft als die Release-App, die die Berechtigung *Administration* hat, nach jeder Änderung der Einstellungen als Code auf `main`, jede Woche und auf Wunsch unter *Actions → Settings → Run workflow*. Ändere `.github/repository.project.toml` in einem Pull Request, und die Einstellungen folgen seinem Merge.
- **Bitte einen Administrator,** `settings apply` einmal auszuführen, für ein neues Repository, dessen Release-App noch nicht eingerichtet ist.
- **Sieh nach, was abweicht,** mit `python3 .github/blueprint.py settings check`, das nichts ändert; manche Teile, etwa wer ein Ruleset umgehen darf, sieht nur ein Administrator.

## Der Settings-Bot scheitert an seinem Token

**Was du siehst:** Der Settings-Workflow scheitert am Schritt *Create a token of the release app*, und seine Zusammenfassung sagt *The release app refused the token of the settings bot*.

**Warum:** Der Settings-Bot bittet die Release-App um ein Token mit nur den Berechtigungen, die `settings apply` braucht: *Administration*, *Issues*, *Pages* und *Variables* (Lesen und Schreiben) sowie *Actions*, *Contents* und *Environments* (Lesen). GitHub verweigert das ganze Token, wenn der App eine davon fehlt, wie einer App, die registriert wurde, bevor der Bot darum bat, oder ohne *Variables*, das der Link der Checkliste nicht ausfüllen kann. Keine Einstellung hat sich geändert.

**Was zu tun ist:**

- **Erteile die fehlenden Berechtigungen** auf der Einstellungsseite der App, unter *Permissions & events*; das Log des Schritts nennt die Antwort von GitHub.
- **Nimm sie auf der Installation an:** GitHub bittet den Eigentümer jeder Installation, neue Berechtigungen anzunehmen, unter *Settings → Applications → Installed GitHub Apps*.
- **Starte den Workflow erneut** unter *Actions → Settings → Run workflow*.

## Die Einstellungen nennen einen Schalter, den GitHub nicht umsetzt

**Was du siehst:** Die Zusammenfassung des Settings-Workflows oder `python3 .github/blueprint.py settings apply` endet mit *GitHub doesn't do this for the repository, which fails nothing*, und darunter steht ein Schalter wie `security.secret_scanning_non_provider_patterns` mit der Zeile, mit der nicht mehr danach gefragt wird.

**Warum:** Manche Schalter der Sicherheit bietet GitHub nur mit manchen Plänen an, etwa die allgemeinen Muster des Secret Scannings, die private Schlüssel, Verbindungszeichenfolgen und Passwörter finden, die kein Anbieter ausgestellt hat. Auf einem Repository eines Benutzers nimmt GitHub das Einschalten an und lässt sie trotzdem aus, oder es lässt sie in seiner Antwort weg. Der Einstellungs-Bot fragt in jedem Lauf wieder, damit ein Repository, dessen Plan den Schalter bekommt, ihn auch bekommt, und nennt, was GitHub gelassen hat, wie es war, ohne den Lauf fehlschlagen zu lassen ([Entscheidung 0055](decisions/0055-what-github-does-not-do-for-a-repository-fails-no-settings-run.md)).

**Was zu tun ist:**

- **Nichts,** wenn das Repository den Schalter bekommen soll, sobald sein Plan ihn hat: Der Hinweis bleibt in der Zusammenfassung jedes Laufs und lässt nichts fehlschlagen.
- **Frag nicht mehr danach** mit der Zeile, die der Hinweis nennt, etwa `secret_scanning_non_provider_patterns = false` unter `[security]` in `.github/repository.project.toml`, in einem Pull Request; mit seinem Merge endet der Hinweis.
- **Rechne damit, dass `settings check` ihn als Abweichung nennt:** Es schreibt nichts, und nur ein Schreiben zeigt, was GitHub behält.

## Der Release-Pull-Request hat keine Prüfungen

**Was du siehst:** Der Pull Request `chore: release x.y.z` zeigt keine Prüfungen, und die Zusammenfassung des Release-Workflows sagt, dass das Repository keine Release-App nennt.

**Warum:** Ohne die Release-App hält release-please den Release-Pull-Request mit dem Token des Jobs, das keinen Workflow startet, und nur die Release-App darf einen Release-Tag anlegen und signieren, sodass kein Release veröffentlicht werden kann.

**Was zu tun ist:**

1. Registriere die Release-App und nenne sie, wie die Seite [Dein eigenes Konto](own-account.md#3-die-release-app-registrieren) zeigt; die Variable [`RELEASE_AUTOMATION_CLIENT_ID`](reference/variables.md#release_automation_client_id) nennt sie dann.
2. Installiere die App im Repository und setze ihren privaten Schlüssel als Secret [`RELEASE_AUTOMATION_PRIVATE_KEY`](reference/variables.md#release_automation_private_key) des Environments `release`: `python3 .github/blueprint.py checklist` zeigt den Befehl.
3. Starte den Release-Workflow unter *Actions → Release → Run workflow*, oder merge den nächsten Pull Request. Er aktualisiert den Release-Pull-Request als die App, und seine Prüfungen starten.

Scheitert das Token der App, etwa bei einer App, die im Repository nicht installiert ist, oder einem Schlüssel, der nicht zu ihr gehört, scheitert der Schritt, der das Token anfordert, und der Bot-Health-Bot hält ein Issue offen, bis ein Lauf besteht. Ein Pull Request, dessen Prüfungen aus einem anderen Grund nicht gestartet sind, startet sie, wenn eine Person ihn schließt und wieder öffnet.

## Ein Bot sagt, dass er die Release-App braucht

**Was du siehst:** Ein Lauf eines Bots, etwa Settings, der Blueprint-Bot, der Branch-Bot oder der Fix-Bot, zeigt die Annotation *This repository names no release app in the variable RELEASE_AUTOMATION_CLIENT_ID* oder *has no private key of its release app*, und seine Zusammenfassung beginnt mit *… needs the release app of the owner*.

**Warum:** Jeder Bot, der als Release-App handelt, prüft die App, bevor er nach ihrem Token fragt, in seinem Schritt *Check that the release app is set up*, und nennt, was fehlt, statt am Token mit einem Fehler zu scheitern, der nichts über die Ursache sagt. Ein Bot, dessen Arbeit die der App ist, schlägt fehl: der Blueprint-Bot, der Settings-Bot, der Upstream-Bot einer Nextcloud-App, Renovate in einem Workflow des Repositorys und das Rollout. Ein Bot, der einem Pull Request nur weiterhilft, warnt und macht ohne das Token weiter: der Fix-Bot, der Branch-Bot, der Diagramm- und der Screenshot-Bot, das Mergen der Updates von Dependabot und der Release-Bot.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="images/diagrams/the-check-of-the-release-app.de.dark.svg">
  <img src="images/diagrams/the-check-of-the-release-app.de.svg" alt="Die Prüfung der Release-App: Bevor ein Bot nach einem Token der Release-App fragt, prüft er, dass das Repository die App in der Variablen RELEASE_AUTOMATION_CLIENT_ID nennt und ihren privaten Schlüssel in der Umgebung release hat. Mit beidem fragt er nach dem Token und tut seine Arbeit. Fehlt eines, sagt er in einer Annotation und in seiner Zusammenfassung, was fehlt und dass die Checkliste es einrichtet. Ein Bot, dessen Arbeit die der App ist, wie der Blueprint-Bot, der Settings-Bot oder Renovate, schlägt dann fehl; einer, der einem Pull Request nur weiterhilft, wie der Fix-Bot oder der Branch-Bot, warnt und macht ohne das Token weiter.">
</picture>

**Was zu tun ist:** Geh die Schritte der Release-App durch, die `python3 .github/blueprint.py checklist` zeigt, wie die Seite [Dein eigenes Konto](own-account.md#3-die-release-app-registrieren) es tut: Registriere die App und nenne sie, sodass die Variable [`RELEASE_AUTOMATION_CLIENT_ID`](reference/variables.md#release_automation_client_id) sie nennt, installiere sie im Repository und setze ihren privaten Schlüssel als Secret [`RELEASE_AUTOMATION_PRIVATE_KEY`](reference/variables.md#release_automation_private_key) des Environments `release`. Der nächste Lauf jedes Bots tut seine Arbeit.

## Renovate öffnet keine Updates

**Was du siehst:** kein Pull Request von Renovate, und die Checkliste hakt Renovate nicht ab.

**Warum, und was zu tun ist:** Zuerst können die Regeln ein Update zurückhalten: Es kommt eine Woche nach seinem Release, an einem Montag, außer es behebt eine Schwachstelle, und Renovate hält kein Issue, das auflistet, was wartet ([Entscheidung 0057](decisions/0057-renovate-keeps-no-dependency-dashboard.md), englisch). Sonst hängt es davon ab, wer Renovate ausführt, nach der Antwort [`renovate_runner`](reference/questions.md#renovate_runner):

- **`self`, ein Workflow des Repositorys:** `.github/workflows/renovate.yml` läuft als die Release-App; ein Lauf ohne die App sagt in seiner Zusammenfassung, was fehlt. *Actions → Renovate → Run workflow* startet sofort einen, und ein Pull Request, der die Regeln oder eine Lock-Datei ändert, zeigt, ob Renovate sie noch annimmt und liest.
- **`mend`, die Mend-Renovate-App:** Installiere die [Mend-Renovate-App](https://github.com/apps/renovate) im Repository; sie kommt bei jedem Push.
- **`hub`, der Renovate-Workflow des Blueprints,** für die Repositorys des Eigentümers des Blueprints: Die Release-App muss im Repository installiert sein, das eine `.github/renovate.json5` braucht.

Wo ein Renovate-Workflow läuft, hält der Bot-Health-Bot ein Issue mit den Warnungen und Fehlern von Renovate offen.

## OSV-Scanner meldet eine Version, die ein anderes Paket festlegt

**Was du siehst:** Die Prüfung *osv-scanner* scheitert, und Code Scanning hat offene Alerts von OSV-Scanner für eine Lock-Datei, deren Abhängigkeit kein Update bewegen kann, sodass auch der Findings-Workflow auf `main` scheitert. Renovate öffnet keinen Pull Request für sie, und das Issue *Renovate logs problems* nennt `Detected empty commit - aborting git push` für einen Branch wie `renovate/pypi-pillow-vulnerability`. Home Assistant zum Beispiel legt das Pillow und das uv fest, die die Tests einer Integration installieren.

**Warum:** Das Paket, das die Version festlegt, etwa das Test-Plugin von Home Assistant, hält sie bis zu seinem nächsten Release, also bleibt die Lock-Datei, wie sie ist: Renovates Behebung der Schwachstelle ist ein leerer Commit, in jedem Lauf.

**Was zu tun ist:** Akzeptiere jedes Advisory dieser Version in der `osv-scanner.toml` neben der Lock-Datei, mit dem Grund und dem Datum, an dem eine Person wieder hinsieht, als Eintrag von `[[PackageOverrides]]`; OSV-Scanner liest die Datei im Ordner jeder Lock-Datei. Eine neue Home-Assistant-Integration hat die Einträge für ihre Testwerkzeuge schon.

```toml
[[PackageOverrides]]
name = "pillow"
version = "12.3.0"
ecosystem = "PyPI"
vulnerability.ignore = true
effectiveUntil = 2026-11-22
reason = "Home Assistant pins Pillow 12.3.0 for the tests; its next release moves it."
```

Dann lass `blueprint.py` die Regel von Renovate dafür schreiben, und committe beide Dateien:

```sh
python3 .github/blueprint.py advisories --fix
```

`.github/renovate-accepted.json5` hat dann eine Regel für jede solche Version, die `.github/renovate-blueprint.json5` erweitert: Renovate macht kein Update dieser Version in den Lock-Dateien dieses Ordners, die nur das Paket bewegt, das sie festlegt. Der Schritt *Accepted advisories* von `scripts/check.sh` scheitert, solange die Regeln und die `osv-scanner.toml`-Dateien sich widersprechen, und wenn OSV-Scanner eine Datei nicht verwenden kann: Er ignoriert eine ganze Datei mit einem Schlüssel, den er nicht kennt. Nach `effectiveUntil` meldet OSV-Scanner die Advisories wieder; sobald das Paket, das die Version festlegt, sie bewegt, lösche den Eintrag. Ein Advisory, das das Projekt nicht betrifft, einer Version, die ein Update bewegen könnte, gehört allein in `[[IgnoredVulns]]`, mit seiner `id` und dem Grund, und das OpenVEX-Dokument jedes Releases nennt die der `osv-scanner.toml` im Wurzelordner ([Entscheidung 0059](decisions/0059-accept-a-pinned-version-and-tell-renovate.md), englisch).

## Renovate überspringt eine Lock-Datei

**Was du siehst:** Eine Lock-Datei wie `requirements-test.txt` bekommt kein Update, auch keins, das eine Schwachstelle behebt, und das Issue *Renovate logs problems* nennt `pip-compile error` für das Repository. Der Schritt *Lock files* von `scripts/check.sh` scheitert und nennt die Datei und das, woran Renovate hängen bleibt, etwa `--python-version without = before its value`.

**Warum:** Renovate kompiliert jede Lock-Datei von pip-compile neu, mit dem Befehl in ihrem Kopf, der Zeile, die `pip-compile` oder `uv pip compile` darüber geschrieben hat. Es liest nur die Optionen, die es kennt, die mit einem Wert nur mit einem `=` davor, und überspringt eine Datei, deren Befehl es nicht lesen kann, in jedem Lauf und mit nicht mehr als einer Warnung in seinem Log. `uv pip compile --python-version 3.12` schreibt den Kopf genau so, ohne das `=`, also liest Renovate `3.12` als eine weitere Datei zum Kompilieren.

**Was zu tun ist:** Lass `blueprint.py` das `=` zwischen jede Option und ihren Wert setzen, und committe die Lock-Datei:

```sh
python3 .github/blueprint.py locks --fix
```

Der Kopf lautet dann `uv pip compile --generate-hashes --python-version=3.12 --output-file=requirements-test.txt requirements-test.in`, und Renovate behält ihn so, wenn es die Datei kompiliert. Eine Option, die Renovate nicht kennt, etwa `--python-platform`, `--no-header`, eine andere Ausgabedatei oder eine Quelldatei, die es nicht gibt, braucht eine Person: Kompiliere die Datei in ihrem Ordner neu, mit den Optionen, die Renovate kennt, wie im Beispiel. In einem Pull Request eines Branches des Repositorys führt der Fix-Bot `locks --fix` selbst aus.

Eine `requirements*.txt`, die keine Lock-Datei ist, etwa `docs/requirements.txt` für Read the Docs, braucht keinen Befehl im Kopf: Trage sie in `ignorePaths` von `.github/renovate.json5` ein, etwa `ignorePaths: ["docs/requirements.txt"]`, dann lassen Renovate und der Schritt *Lock files* sie beide aus. Ein Name, auf den das Muster `requirements*.txt` nicht passt, tut dasselbe.

## Die Prüfung renovate rules scheitert

**Was du siehst:** In einem Pull Request, der die Regeln von Renovate oder eine Lock-Datei ändert, scheitert die Prüfung *renovate rules* des Renovate-Workflows, in einem Repository, das Renovate selbst ausführt (die Antwort `renovate_runner` `self`), und im Blueprint. Ihre Annotationen nennen jedes Problem, etwa `Invalid configuration option` für eine Regel, `pip-compile error` für eine Lock-Datei oder `Renovate doesn't read the lock file requirements-test.txt.`; ihre Zusammenfassung und der Kommentar des PR-Coachs sagen, wie du es behebst.

**Warum:** Renovate lehnt jede Regel ab, die es nicht kennt, und aktualisiert dann nichts mehr im Repository, und eine Datei, die es nicht lesen kann, überspringt es in jedem Lauf, mit nicht mehr als einer Warnung in seinem Log. Deshalb führt die Prüfung den Validator von Renovate auf `.github/renovate.json5`, `.github/renovate-blueprint.json5`, `.github/renovate-accepted.json5` und den Einstellungen des Bots in `.github/renovate-global.json5` aus und danach Renovate selbst, das jede committete Datei der Abhängigkeiten liest, ohne Token und ohne etwas nachzuschlagen. Eine Warnung oder eine Lock-Datei, die es nicht liest, lässt die Prüfung scheitern.

**Was zu tun ist:** Korrigiere die Regel oder die Datei, die die Annotationen nennen; bei einer Lock-Datei schreibt `python3 .github/blueprint.py locks --fix` ihren Kopf so, wie Renovate ihn liest, wie [Renovate überspringt eine Lock-Datei](#renovate-überspringt-eine-lock-datei) zeigt. Mit Docker laufen dieselben Prüfungen auf deinem Rechner, die letzte auf den Dateien deines letzten Commits; die Prüfung selbst führt das Renovate aus, das `.github/workflows/renovate.yml` festlegt:

```sh
docker run --rm -v "$PWD:/usr/src/app" -w /usr/src/app ghcr.io/renovatebot/renovate:latest renovate-config-validator --strict .github/renovate.json5 .github/renovate-blueprint.json5 .github/renovate-accepted.json5
docker run --rm -v "$PWD:/usr/src/app" -w /usr/src/app -e RENOVATE_CONFIG_FILE=/usr/src/app/.github/renovate-global.json5 ghcr.io/renovatebot/renovate:latest renovate-config-validator --strict
git archive HEAD | docker run --rm -i -e LOG_LEVEL=info -e RENOVATE_GITHUB_TOKEN_WARN=false -e RENOVATE_CONFIG_FILE=/tmp/repository/.github/renovate-blueprint.json5 ghcr.io/renovatebot/renovate:latest bash -c 'mkdir /tmp/repository && cd /tmp/repository && tar -xf - && sed -i "s#\"local>[^\"]*\",\{0,1\}##" .github/renovate.json5 .github/renovate-blueprint.json5 && renovate --platform=local --dry-run=extract'
```

Der letzte Befehl nimmt die Presets des Blueprints aus den Regeln, da Renovate auf deinem Rechner keine Plattform hat, von der es sie holen könnte; die Regeln des Blueprints kommen als die des Bots hinein. Seine Zeile `Extracted dependencies` listet jede Datei, die Renovate liest, mit den Lock-Dateien jeder Quelle von pip-compile unter `lockFiles`; eine Zeile mit `WARN` oder `ERROR` nennt ein Problem, und nach einem Fehler endet Renovate mit dem Exit-Code 1. Unter Windows führe die Befehle in Git Bash mit `MSYS_NO_PATHCONV=1` vor `docker` aus, damit Git Bash die Pfade im Container in Ruhe lässt.

## Die Website nennt ein Bild, das Git nicht verfolgt

**Was du siehst:** Die Prüfung *docs*, oder `scripts/check.sh` mit den Werkzeugen der Website, scheitert mit einer Warnung wie `index.md shows https://github.com/OWNER/NAME/raw/main/screenshots/settings.png, a file that git doesn't track in the repository, so that the picture would be missing on main`.

**Warum:** Eine README zeigt ihre Bilder von `main` ihres eigenen Repositorys, damit sie überall zu sehen sind, wo die README es ist, etwa auf PyPI oder im Store einer App. Die Website liefert ein solches Bild aus dem Checkout aus, damit der Pull Request, der einen Screenshot hinzufügt, ihn auch auf seiner Website zeigt, bevor `main` ihn hat ([Entscheidung 0062](decisions/0062-the-website-shows-the-pictures-of-its-repository-from-the-checkout.md), englisch). Ein Bild, das Git nicht verfolgt, würde auf `main` fehlen, sobald der Pull Request gemergt ist: ein neuer Screenshot, der noch nicht committet ist, einer, den der Pull Request löscht oder verschiebt, oder ein Tippfehler in seiner Adresse.

**Was zu tun ist:** Committe das Bild, etwa mit `git add screenshots/settings.png`, oder korrigiere seine Adresse in der README. Ohne Git, etwa in einem Ordner ohne seine Historie, lädt die Website das Bild wie bisher von `main` herunter.

## Ein geplanter Workflow ist nicht gelaufen

GitHub führt Zeitpläne aus, wie es kann, oft Stunden zu spät und manchmal gar nicht; deshalb startet der Blueprint seine Bots durch Ereignisse, etwa einen Merge in `main` oder das Ende einer Prüfung, und behält die Zeitpläne nur als Sicherheitsnetz ([Entscheidung 0033](decisions/0033-schedules-are-only-a-safety-net.md), englisch). Jede Nacht sieht der Bot-Health-Bot den neuesten Lauf jedes Workflows an und startet einen, dessen Zeitplan GitHub verpasst oder abgeschaltet hat, auch wenn ihn seitdem ein Push ausgeführt hat, denn nur ein Lauf seines Zeitplans oder einer von Hand zählt. Wie spät GitHub die geplanten Läufe jedes Repositorys in den letzten 7 Tagen im Median startete, zeigt die Spalte *Schedule delay* des [Dashboards](https://dennis-otto.github.io/repo-blueprint/dashboard/). Ein Workflow mit *Run workflow* unter *Actions* startet von Hand sofort.
