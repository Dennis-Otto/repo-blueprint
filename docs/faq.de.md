---
description: "Antworten auf die häufigen Fragen zu Repo Blueprint: dein eigenes Konto oder deine Organisation, die KI des Issue-Assistenten, Updates, die sich selbst mergen, private Repositorys und die Kosten von Actions, die Dateien, die ein Projekt ändern darf, und wie man den Blueprint verlässt."
---

# Fragen und Antworten

Die Fragen, die am häufigsten aufkommen, wenn ein Repository den Blueprint übernimmt. Was zu tun ist, wenn etwas nicht funktioniert, steht auf der Seite [Fehlerbehebung](troubleshooting.md), jede Frage von Copier und jede Variable und jedes Secret in der [Referenz](reference/questions.md) (englisch).

## Funktioniert der Blueprint für mein eigenes Konto oder meine Organisation?

Ja, für jedes Konto und jede Organisation auf GitHub. Ein Repository aus ihm nennt nichts vom Eigentümer des Blueprints außer den Links zum Blueprint, und jeder Bot handelt als eine App von dir. Du bringst zweierlei mit: eine **Release-App**, einmal für all deine Repositorys, die du mit Hilfe der Checkliste registrierst, und **deine Vorgaben** in der Einstellungsdatei von Copier, damit jedes neue Repository nur fragt, was neu ist. Renovate läuft in einem Workflow jedes Repositorys oder als die Mend-Renovate-App, nach der Antwort [`renovate_runner`](reference/questions.md#renovate_runner). Die Seite [Dein eigenes Konto](own-account.md) führt durch jeden Schritt, von der Kopie bis zu einer Checkliste ohne Kreuz.

## Warum brauchen die Bots eine Release-App?

Was ein Workflow mit dem Token tut, das GitHub ihm gibt, `GITHUB_TOKEN`, startet keinen anderen Workflow: Ein Release- oder Update-Pull-Request, den es öffnet, führte keine Prüfungen aus, und ein Merge damit startete kein Release. Die Bots handeln stattdessen als eine GitHub-App von dir, deren Token die Prüfungen startet, Workflows ändern darf und die Release-Tags anlegt, die nur diese App anlegen darf. Nur der Eigentümer einer App hat ihren privaten Schlüssel, deshalb kann der Blueprint seine eigene nicht verleihen. Bis die App da ist, sagen die Bots in ihrer Zusammenfassung, was fehlt, statt an einem Token zu scheitern.

## Wie schalte ich die KI des Issue-Assistenten ab?

Ändere die Antwort [`issue_assistant_ai`](reference/questions.md#issue_assistant_ai) und committe das Update:

```sh
copier update --defaults --vcs-ref=:current: --data issue_assistant_ai=false
```

Der Einstellungs-Bot setzt dann die Variable [`ISSUE_ASSISTANT_AI`](reference/variables.md#issue_assistant_ai) auf `off`, das Environment `issue-assistant` verlangt kein Secret, und `SUPPORT.md` sagt Meldenden, dass keine KI ihre Issues liest. Labels, Erinnerungen, das Schließen mit dem Release und die Befehle des Maintainers funktionieren wie zuvor. Das Secret `CLAUDE_CODE_OAUTH_TOKEN` zu löschen, stoppt die KI ebenfalls sofort, aber die Checkliste fragt dann wieder danach. `--data issue_assistant_ai=true` schaltet die KI später wieder ein.

## Wie verhindere ich, dass sich die Updates des Blueprints selbst mergen?

Setze die Repository-Variable [`BLUEPRINT_AUTOMERGE`](reference/variables.md#blueprint_automerge) auf `off`: Jedes Update des Blueprints wartet dann auf dich, mit seinen Notizen und den Dateien, die es ändert, in seiner Beschreibung. Setze sie in `[variables]` von `.github/repository.project.toml`, das der Einstellungs-Bot anwendet, oder unter *Settings → Secrets and variables → Actions → Variables*. Damit sie sich wieder selbst mergen, setze sie dort auf `on` oder lösche die Variable auf GitHub, mit `gh variable delete BLUEPRINT_AUTOMERGE` oder auf jener Seite: Der Einstellungs-Bot setzt Variablen, löscht aber nie eine, eine aus der Datei entfernte Zeile lässt `off` also stehen. Ein Update mit Konflikten wartet immer, ebenso eines, dessen Auto-Merge du abgeschaltet hast, das abgeschaltet bleibt.

Die anderen Bots, die ihre eigenen Pull Requests mergen, haben eigene Schalter:

- **Der Upstream-Bot einer Nextcloud-App** wartet, wenn [`UPSTREAM_AUTOMERGE`](reference/variables.md#upstream_automerge) auf `off` steht.
- **Renovate** merged, was die Regeln von `.github/renovate.json5` erlauben; eine Regel mit `"automerge": false` stoppt das für die Pakete, die sie nennt. Die wöchentliche Auffrischung der Lock-Dateien wartet ohnehin auf dich.

## Kann ein Repository privat sein, und was kostet es?

Ja: `python3 .github/blueprint.py create --private` legt ein privates Repository an. Öffentliche Repositorys nutzen GitHub Actions kostenlos. Ein privates hat bei GitHub Free 2.000 Minuten im Monat, und GitHub rundet jeden Job auf eine ganze Minute auf. Die Zeitpläne eines Projekts und die Läufe, die sie starten, kommen auf etwa 20 Läufe am Tag, etwa 600 im Monat; die Prüfungen der Pull Requests kosten mehr, weshalb der Blueprint eine Prüfung nur dort ausführt, wo sie ein Ergebnis ändern kann, und die Jobs wenige hält (Entscheidungen [0009](decisions/0009-run-a-check-only-where-it-can-change-a-result.md) und [0027](decisions/0027-few-jobs-that-each-run-several-checks.md), englisch).

Manches, was der Blueprint einschaltet, ist nur für öffentliche Repositorys kostenlos. Für ein privates verlangt GitHub einen bezahlten Plan für Rulesets und GitHub Pages und GitHub Advanced Security für Code Scanning, das Dependency Review und den Push-Schutz des Secret Scannings. Bis dahin nennt `settings apply` jeden Teil, den GitHub ablehnt, und die Prüfungen, die ihn brauchen, scheitern.

## Welche Dateien darf ein Projekt ändern?

Jede Datei, und jede Änderung übersteht die Updates:

- **Die Dateien des Projekts,** etwa das README, das Changelog, der Code, die Tests, die Manifeste und die Seiten der Website, überschreibt ein Update nie. Die [Referenz](reference/questions.md#the-files-of-a-project) (englisch) listet ihre Muster aus `_skip_if_exists` von `copier.yml`.
- **Die Dateien des Blueprints,** etwa die Workflows und `scripts/check.sh`, übernehmen die Änderungen jedes Updates: `copier update` führt sie Zeile für Zeile mit den Änderungen des Repositorys zusammen und markiert einen Konflikt nur dort, wo beide dieselben Zeilen geändert haben.

Damit Updates selten Konflikte haben, ergänzt ein Projekt seines neben den Dateien des Blueprints statt in ihnen: seine Einstellungen in `.github/repository.project.toml`, seine Prüfungen in `scripts/check-project.sh` und `scripts/check-site.sh`, deren Erklärungen in `.github/checks.project.toml`, seine Hinweise für Coding-Agents in `.github/agents.project.md` und Workflows in eigenen Dateien. Ein Fix, den jedes Repository braucht, gehört in den Blueprint, dessen nächstes Release ihn zu allen bringt.

## Wie ändere ich später eine Antwort?

Führe `copier update` mit der neuen Antwort aus und committe das Update, etwa für die Topics:

```sh
copier update --defaults --vcs-ref=:current: --data "topics=python, pypi, cli"
```

`--vcs-ref=:current:` behält das Release des Blueprints, auf dem das Repository steht, und `--defaults` nimmt jede andere Antwort aus `.copier-answers.yml`. Was die Antwort in `.github/repository.toml` ändert, etwa eine Variable oder die Topics, wendet der Einstellungs-Bot nach dem Merge an.

## Wie verlasse ich den Blueprint?

Lösche `.github/workflows/blueprint-update.yml`, und kein Update des Blueprints kommt mehr; der Rollout des Blueprints lässt ein Repository ohne Blueprint-Bot aus. Alles andere bleibt und funktioniert, wie es ist, denn es ist eine Datei deines Repositorys: die Workflows, die Prüfungen, die Einstellungen als Code mit `.github/blueprint.py` und die anderen Bots. Die Lizenz des Blueprints, [MIT No Attribution](https://github.com/Dennis-Otto/repo-blueprint/blob/main/LICENSE), verlangt nichts für das, was du behältst, nicht einmal einen Hinweis. Behalte `.copier-answers.yml`, wenn du vielleicht zurückkommst: `copier update` setzt bei dem Release an, das sie nennt.

Um die Updates nur anzuhalten, statt den Blueprint zu verlassen, setze [`BLUEPRINT_AUTOMERGE`](reference/variables.md#blueprint_automerge) auf `off` und lass den Update-Pull-Request offen; ein neueres Release bringt ihn weiter.
