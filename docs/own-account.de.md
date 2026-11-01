---
description: Repo Blueprint für dein eigenes GitHub-Konto oder deine Organisation, mit eigener Release-App, Renovate in deinen eigenen Repositorys oder als Mend-App und dem Issue-Assistenten mit oder ohne KI.
---

# Dein eigenes Konto

Der Blueprint funktioniert für jedes Konto und jede Organisation auf GitHub. Ein Repository daraus nennt nichts vom Eigentümer des Blueprints außer den Links auf den Blueprint und seine Werkzeuge, und jeder Bot läuft als eine App von dir. Diese Seite führt durch ein neues eigenes Repository, von der Kopie bis zu einer Checkliste ohne Kreuz.

## Was du mitbringst und was optional ist

- **Eine Release-App,** einmal für alle deine Repositorys, als die die Bots handeln: Ihr Token startet die Checks der Release- und Update-Pull-Requests, darf Workflows ändern und legt die Release-Tags an, was das Token eines Jobs nicht kann. Nur der Eigentümer einer App hat ihren privaten Schlüssel, darum kann der Blueprint seine eigene nicht verleihen.
- **Renovate,** das die Abhängigkeiten aktuell hält: in einem Workflow jedes Repositorys, als deine Release-App, oder als Mend-Renovate-App, die du installierst. Der Renovate-Workflow des Blueprints läuft nur für die Repositorys des Eigentümers des Blueprints.
- **Die KI des Issue-Assistenten** ist optional. Ohne sie labelt der Issue-Assistent neue Issues weiter, erinnert und schließt und führt die Befehle des Maintainers aus, und es braucht kein Secret.
- **Die Settings-App** ist optional: eine zweite App mit nur den Berechtigungen der Einstellungen, die sie dann anstelle der Release-App anwendet, damit die Release-App kein *Administration* braucht. [Schritt 8](#8-die-settings-app-optional) richtet sie ein.
- **Der Rollout** ist optional: Der Blueprint-Bot jedes Repositorys läuft jede Woche und bringt das neueste Release des Blueprints von selbst. Der Rollout des Blueprints startet nur die Bots der Repositorys seines Eigentümers gleich nach einem Release.

## 1. Den Blueprint kopieren

```sh
copier copy gh:Dennis-Otto/repo-blueprint my-project
```

Copier fragt nach deinem Konto oder deiner Organisation, `owner`, und nimmt es als Maintainer. Lass die Frage nach der Release-App leer und beantworte zwei weitere:

- **`renovate_runner`**, wer Renovate ausführt: `self`, ein Workflow im Repository, die Vorgabe für jeden Eigentümer außer dem des Blueprints; oder `mend`, die Mend-Renovate-App. Die Repositorys des Eigentümers des Blueprints behalten den Workflow des Blueprints, `hub`, der schon für jedes von ihnen läuft.
- **`issue_assistant_ai`**, ob eine KI, Claude, jedes neue Issue analysiert; *no* schaltet sie aus.

Die Antworten, die für jedes Repository gleich bleiben, nimmt Copiers Einstellungsdatei auf, wie [die Anleitung zeigt](guide.md#dein-eigenes-konto):

```yaml
# ~/.config/copier/settings.yml
defaults:
  owner: octo-org
  author: Octo Org
  renovate_runner: self
  issue_assistant_ai: false
```

## 2. Das Repository anlegen

```sh
cd my-project
git init && git add --all && git commit --signoff --message "chore: start from the blueprint"
gh repo create octo-org/my-project --public --source . --push
python3 ../repo-blueprint/blueprint.py checklist
```

## 3. Die Release-App registrieren

Die Checkliste beginnt mit einem Link, der die App auf deinem Konto oder deiner Organisation registriert, mit Name und Berechtigungen vorausgefüllt und ohne Webhook; *Variables* setzt du von Hand, das kann der Link nicht. Leg die App an, erzeuge auf ihrer Einstellungsseite einen privaten Schlüssel und nenne die App in den Antworten des Blueprints, mit dem Namen in ihrer Adresse und der Client ID und App ID dieser Seite:

```sh
copier update --defaults --vcs-ref=:current: --data release_app=NAME --data release_app_client_id=CLIENT_ID --data release_app_id=APP_ID
git commit --all --signoff --message "chore: name the release app"
git push
```

Installiere die App auf dem Repository, unter `https://github.com/apps/NAME/installations/new`, und setze ihren privaten Schlüssel aus der Datei, die GitHub dir gegeben hat; die GitHub CLI liest ihn und zeigt ihn nirgends:

```sh
gh secret set RELEASE_AUTOMATION_PRIVATE_KEY --env release --repo octo-org/my-project < private-key.pem
```

Bis die App genannt ist und ihren privaten Schlüssel hat, sagt jeder Bot, der als sie handelt, in seiner Zusammenfassung, was fehlt, statt an seinem Token zu scheitern: Einer, dessen Arbeit die der App ist, schlägt fehl, und einer, der einem Pull Request nur weiterhilft, warnt, wie die [Fehlerbehebung](troubleshooting.md#ein-bot-sagt-dass-er-die-release-app-braucht) zeigt. Eine App, die nicht auf dem Repository installiert ist, scheitert weiterhin an ihrem Token.

## 4. Die Einstellungen anwenden

```sh
python3 ../repo-blueprint/blueprint.py settings apply
```

Es setzt alles, was die API setzen kann: die Rulesets, die Variablen, die die App nennen, die Environments, die Sicherheitsfunktionen und die Actions, die laufen dürfen. Ein privates Repository geht auch, mit `--private` für `gh repo create`: Was GitHub ihm in seinem Plan nicht bietet, etwa Code Scanning oder die Rulesets bei GitHub Free, nennen die Einstellungen als Hinweis und überlassen es den Workflows, über die Variablen `CODE_SCANNING` und `DEPENDENCY_REVIEW`. Die [FAQ](faq.md#kann-ein-repository-privat-sein-und-was-kostet-es) zeigt, was mit welchem Plan geht.

## 5. Renovate

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="images/diagrams/who-runs-renovate.de.dark.svg">
  <img src="images/diagrams/who-runs-renovate.de.svg" alt="Wer Renovate ausführt: Die Antwort renovate_runner entscheidet, wer Renovate für ein Repository ausführt. Der Eigentümer des Blueprints behält den Hub, den Renovate-Workflow des Blueprints, der es für jedes seiner Repositorys ausführt, auf dem die Release-App installiert ist. Jeder andere Eigentümer bekommt einen Renovate-Workflow im Repository selbst, der es alle zwei Stunden als Release-App ausführt, nur für dieses Repository, mit demselben Renovate und denselben Regeln; oder er installiert die Mend-Renovate-App, die keinen Workflow braucht und bei jedem Push kommt. Jeder Weg liest die Regeln aus .github/renovate.json5 und öffnet die Updates als Pull Requests, deren Checks entscheiden, ob sie gemergt werden.">
</picture>

Jeder Weg liest dieselben Regeln, die des Blueprints in `.github/renovate-blueprint.json5` und deine in `.github/renovate.json5`, und hält kein Issue offen: Was auf dich wartet, ist ein Pull Request. Die Checkliste hakt Renovate ab, sobald es einen Pull Request geöffnet hat.

- **`self`, ein Workflow des Repositorys:** `.github/workflows/renovate.yml` führt Renovate alle zwei Stunden als deine Release-App aus, mit einem Token nur für dieses Repository und ohne *Administration*. Es ist der Workflow des Hubs des Blueprints, mit demselben Renovate, gepinnt auf seinen Digest, das jedes Update des Blueprints weiterbewegt, und `.github/renovate-global.json5` hält die Einstellungen des Bots: Commits über die API, die GitHub signiert, und keine Skripte der Paketmanager. Der Bot-Benutzer deiner App ist der Autor, nach dem der Workflow GitHub fragt. Sein erster Lauf startet von selbst; *Actions → Renovate → Run workflow* startet sofort einen. Ein Lauf ohne die Release-App sagt in seiner Zusammenfassung, was fehlt, und ein Pull Request, der die Regeln oder eine Lock-Datei ändert, zeigt, ob Renovate sie weiter annimmt und liest; der PR-Coach erklärt ein Scheitern dieser Prüfung, *renovate rules*, auch bei einem Pull Request aus einem Fork, wie es [die Fehlerbehebung](troubleshooting.md#die-prüfung-renovate-rules-scheitert) tut.
- **`mend`, die Mend-Renovate-App:** Installiere die [Mend-Renovate-App](https://github.com/apps/renovate) auf dem Repository. Sie liest dieselben Regeln, kommt bei jedem Push statt nach einem Zeitplan und braucht keinen Workflow und kein Token von dir. Der Branch-Bot und der Fix-Bot aktualisieren ihre Branches als deine Release-App, also trag den Bot-Benutzer der App in `gitIgnoredAuthors` in `.github/renovate.json5` ein, sonst hält Renovate die Branches für bearbeitet und rebased sie nicht mehr; die Checkliste gibt die Zeile mit der Nummer des Bot-Benutzers deiner App aus.

Um die Antwort später zu ändern, führ `copier update --defaults --vcs-ref=:current: --data renovate_runner=mend` aus und committe das Update.

## 6. Der Issue-Assistent

Mit `issue_assistant_ai` analysiert der Issue-Assistent jedes neue Issue mit Claude, und die Checkliste fragt nach seinem Token, als Secret `CLAUDE_CODE_OAUTH_TOKEN` des Environments `issue-assistant`. Ohne sie setzt `.github/repository.toml` die Variable `ISSUE_ASSISTANT_AI` auf `off`, das Environment fragt nach keinem Secret, und `SUPPORT.md` sagt den Meldenden, dass keine KI ihre Issues liest; Labels, Erinnerungen, Schließen und die Befehle des Maintainers funktionieren wie bisher. `copier update --defaults --vcs-ref=:current: --data issue_assistant_ai=true` schaltet die KI später ein.

## 7. Die Checkliste

```sh
python3 ../repo-blueprint/blueprint.py checklist
```

Sie zeigt, was für einen Menschen bleibt und welche Schritte erledigt sind: die Release-App, die Einstellungen, die Secrets, die Installation, Renovate, das Community-Profil, die Social-Preview und die Badges. Ein privates Repository bekommt dazu den Schritt *GitHub Code Security on*, neutral ohne sie, da der Plan seines Besitzers sie vielleicht nicht bietet. Sobald jeder Schritt seinen Haken hat, kümmert sich das Repository um sich selbst.

## 8. Die Settings-App (optional)

Die Release-App kann alles, was die Bots brauchen, auch die Verwaltung jedes Repositorys: seine Rulesets, Environments, Variablen und die Actions, die laufen dürfen. Eine zweite App, die **Settings-App**, kann die Verwaltung übernehmen, damit die Release-App, die die meisten Workflows nutzen, sie abgeben kann: Ein gestohlener Schlüssel der Release-App kann dann kein Ruleset mehr ändern und keine neue Action zulassen.

- **Der Settings-Bot** wendet die Einstellungen als Settings-App an, jede Woche und nach jeder Änderung an ihnen.
- **Der OSV-Scanner-Workflow** schließt die Dependabot-Alerts der Advisories, die eine `osv-scanner.toml` akzeptiert, mit dem Grund und dem Ende der Akzeptanz, und öffnet jeden, den er geschlossen hat, wieder, sobald die Akzeptanz weg ist: Das Token eines Workflows kann die Dependabot-Alerts nicht lesen.
- **Der Blueprint-Bot** lässt die Actions eines neuen Releases des Blueprints starten, bevor er das Update pusht: Er ergänzt die Liste der erlaubten Actions auf GitHub um die Muster aus `[actions.selected]` des Releases und nimmt keines weg, sodass die Checks des Update-Pull-Requests ohne ein `settings apply` von seinem Branch starten. Der Settings-Bot verengt die Liste nach dem Merge auf die Einstellungen.
- **Die Release-App** braucht dann kein *Administration*, *Pages*, *Variables*, *Environments* und *Secrets* mehr.

Ohne Settings-App funktioniert alles wie bisher: Die Release-App wendet die Einstellungen an und schließt die akzeptierten Dependabot-Alerts, und ein Update, das eine neue Action bringt, wartet auf `settings apply` von seinem Branch. Ist nur die Variable oder nur das Secret gesetzt, warnen beide Bots und machen mit der Release-App weiter.

1. **Registriere die App** auf deinem Konto, mit ausgefüllten Berechtigungen und ohne Webhook, über [diesen Link](https://github.com/settings/apps/new?description=Applies+the+settings+as+code+of+the+repositories+made+from+Repo+Blueprint.&public=false&webhook_active=false&administration=write&issues=write&pages=write&vulnerability_alerts=write&actions=read&contents=read&environments=read), oder für eine Organisation unter derselben Adresse mit `https://github.com/organizations/ORG/settings/apps/new`. Gib ihr einen Namen, etwa `octo-org-settings`, und diese Repository-Berechtigungen, keine anderen:

    | Berechtigung | Zugriff | Wofür |
    | --- | --- | --- |
    | Administration | Read and write | Rulesets, die Schalter der Sicherheit, die erlaubten Actions, Environments |
    | Issues | Read and write | die Labels |
    | Pages | Read and write | die Einstellungen der Website |
    | Dependabot alerts | Read and write | die Dependabot-Alerts der Advisories, die eine `osv-scanner.toml` akzeptiert, die der OSV-Scanner-Workflow schließt und wieder öffnet |
    | Variables | Read and write | die Variablen aus `[variables]`; von Hand setzen, der Link kann es nicht |
    | Actions | Read-only | die Einstellungen der Workflows |
    | Contents | Read-only | die Dateien des Community-Profils |
    | Environments | Read-only | die Environments, ihre Branch-Regeln und die Namen ihrer Secrets, nie ihre Werte |
    | Metadata | Read-only | das GitHub selbst verlangt |

    Lass *Where can this GitHub App be installed?* auf *Only on this account* und lege die App an.

2. **Notiere ihre Client ID** auf der Einstellungsseite der App und drück *Generate a private key*; dein Browser speichert den Schlüssel als Datei, etwa `octo-org-settings.2026-10-25.private-key.pem`, die die Befehle unten `settings-private-key.pem` nennen.
3. **Installiere die App** auf jedem Repository aus dem Blueprint, denselben wie die Release-App: *Install App* auf der Einstellungsseite der App, dann *Only select repositories*.
4. **Nenne sie in jedem Repository,** mit ihrer Client ID als Variable und ihrem Schlüssel als Secret des Environments `release`, das nur `main` nutzen darf. Die GitHub CLI liest die Datei und zeigt den Schlüssel nirgends; lösch die Datei danach.

    ```sh
    for repo in octo-org/my-project octo-org/another; do
      gh variable set SETTINGS_APP_CLIENT_ID --repo "$repo" --body CLIENT_ID
      gh secret set SETTINGS_APP_PRIVATE_KEY --env release --repo "$repo" < settings-private-key.pem
    done
    ```

    Die Variable kann auch in den Einstellungen als Code stehen, als `SETTINGS_APP_CLIENT_ID = "CLIENT_ID"` unter `[variables]` in `.github/repository.project.toml`, die der Settings-Bot zuerst noch mit der Release-App anwendet.

5. **Prüf es:** *Actions → Settings → Run workflow*. Der Lauf nimmt den Schritt *Create a token of the settings app* und überspringt *Check that the release app is set up*. Verweigert GitHub das Token, einer App, die nicht auf dem Repository installiert ist oder der eine Berechtigung fehlt, sagt es die Zusammenfassung des Laufs, und keine Einstellung ändert sich.
6. **Einer App, die vor dem Schließen der Dependabot-Alerts registriert wurde,** fehlt deren Berechtigung, und der Job *dependabot alerts* dieses Workflows schlägt fehl oder hinterlässt, in einem Repository eines anderen Eigentümers als dem des Blueprints, einen Hinweis: auf der Einstellungsseite der App, die die Zusammenfassung des Laufs nennt, der Settings-App oder ohne sie der Release-App, unter *Permissions & events* → *Repository permissions* *Dependabot alerts* auf *Read and write* setzen und *Save changes* drücken. GitHub bittet dann darum, die neue Berechtigung auf der Installation zu akzeptieren: *Settings → Applications → Installed GitHub Apps*, *Configure* neben der App, *Review request*, *Accept new permissions*. Danach *Actions → OSV-Scanner → Run workflow*, zuerst mit *dry_run*, um zu sehen, was er schließen würde.
7. **Nimm der Release-App die Berechtigungen,** sobald der Settings-Bot in jedem Repository als Settings-App gelaufen ist: auf der Einstellungsseite der Release-App unter *Permissions & events* *Administration*, *Pages*, *Variables*, *Environments* und *Secrets* auf *No access* und *Dependabot alerts* auf *Read-only*. Ihre übrigen Berechtigungen bleiben, für den Release-Bot, Renovate, den Blueprint-Bot und die anderen.

`gh variable delete SETTINGS_APP_CLIENT_ID` gibt die Einstellungen an die Release-App zurück, die dann ihre Berechtigungen wieder braucht.
