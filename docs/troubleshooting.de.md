---
description: "Was zu tun ist, wenn in einem Repository von Repo Blueprint etwas nicht funktioniert: ein Update mit Konflikten, eine Pflichtprüfung, die nie berichtet, settings apply ohne Administratorrechte, ein Release-Pull-Request ohne Prüfungen und Renovate, das keine Updates öffnet."
---

# Fehlerbehebung

Die meisten Probleme erklären sich dort, wo sie auftreten: Eine Prüfung, die scheitert, sagt in ihrer Zusammenfassung und im Bericht des PR-Coachs, was sie gefunden hat und wie man es behebt, ein Bot sagt in der Zusammenfassung seines Laufs, was fehlt, und der Bot-Health-Bot hält für jeden Bot, der auf `main` scheitert, ein Issue offen. Diese Seite behandelt, was darüber hinaus eine Person braucht. Die häufigen Fragen stehen auf der Seite [Fragen und Antworten](faq.md).

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
- **Der Workflow ist nicht gestartet.** Sein Lauf unter *Actions* zeigt einen *startup failure*, wenn er eine Action nutzt, die in der Liste der erlaubten Actions fehlt. `python3 .github/blueprint.py settings check` nennt jede; trage ihr Muster für einen Workflow des Projekts in `[actions.selected]` von `.github/repository.project.toml` ein und wende die Einstellungen an.
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

## Der Release-Pull-Request hat keine Prüfungen

**Was du siehst:** Der Pull Request `chore: release x.y.z` zeigt keine Prüfungen, und die Zusammenfassung des Release-Workflows sagt, dass das Repository keine Release-App nennt.

**Warum:** Ohne die Release-App hält release-please den Release-Pull-Request mit dem Token des Jobs, das keinen Workflow startet, und nur die Release-App darf einen Release-Tag anlegen und signieren, sodass kein Release veröffentlicht werden kann.

**Was zu tun ist:**

1. Registriere die Release-App und nenne sie, wie die Seite [Dein eigenes Konto](own-account.md#3-die-release-app-registrieren) zeigt; die Variable [`RELEASE_AUTOMATION_CLIENT_ID`](reference/variables.md#release_automation_client_id) nennt sie dann.
2. Installiere die App im Repository und setze ihren privaten Schlüssel als Secret [`RELEASE_AUTOMATION_PRIVATE_KEY`](reference/variables.md#release_automation_private_key) des Environments `release`: `python3 .github/blueprint.py checklist` zeigt den Befehl.
3. Starte den Release-Workflow unter *Actions → Release → Run workflow*, oder merge den nächsten Pull Request. Er aktualisiert den Release-Pull-Request als die App, und seine Prüfungen starten.

Scheitert das Token der App, etwa bei einer App, die im Repository nicht installiert ist, oder einem Schlüssel, der nicht zu ihr gehört, scheitert der Schritt, der das Token anfordert, und der Bot-Health-Bot hält ein Issue offen, bis ein Lauf besteht. Ein Pull Request, dessen Prüfungen aus einem anderen Grund nicht gestartet sind, startet sie, wenn eine Person ihn schließt und wieder öffnet.

## Renovate öffnet keine Updates

**Was du siehst:** kein Pull Request von Renovate, oder das Issue *Dependency dashboard* fehlt.

**Warum, und was zu tun ist:** Zuerst können die Regeln ein Update zurückhalten: Es kommt eine Woche nach seinem Release, an einem Montag, außer es behebt eine Schwachstelle, und das Issue *Dependency dashboard* listet jedes Update, das wartet oder scheiterte, mit einem Kästchen, um es erneut zu versuchen. Sonst hängt es davon ab, wer Renovate ausführt, nach der Antwort [`renovate_runner`](reference/questions.md#renovate_runner):

- **`self`, ein Workflow des Repositorys:** `.github/workflows/renovate.yml` läuft als die Release-App; ein Lauf ohne die App sagt in seiner Zusammenfassung, was fehlt. *Actions → Renovate → Run workflow* startet sofort einen, und ein Pull Request, der die Regeln oder eine Lock-Datei ändert, zeigt, ob Renovate sie noch annimmt und liest.
- **`mend`, die Mend-Renovate-App:** Installiere die [Mend-Renovate-App](https://github.com/apps/renovate) im Repository; sie kommt bei jedem Push.
- **`hub`, der Renovate-Workflow des Blueprints,** für die Repositorys des Eigentümers des Blueprints: Die Release-App muss im Repository installiert sein, das eine `.github/renovate.json5` braucht.

Wo ein Renovate-Workflow läuft, hält der Bot-Health-Bot ein Issue mit den Warnungen und Fehlern von Renovate offen.

## Ein geplanter Workflow ist nicht gelaufen

GitHub führt Zeitpläne aus, wie es kann, oft Stunden zu spät und manchmal gar nicht; deshalb startet der Blueprint seine Bots durch Ereignisse, etwa einen Merge in `main` oder das Ende einer Prüfung, und behält die Zeitpläne nur als Sicherheitsnetz ([Entscheidung 0033](decisions/0033-schedules-are-only-a-safety-net.md), englisch). Jede Nacht sieht der Bot-Health-Bot den neuesten Lauf jedes Workflows an und startet einen, dessen Zeitplan GitHub verpasst oder abgeschaltet hat. Ein Workflow mit *Run workflow* unter *Actions* startet von Hand sofort.
