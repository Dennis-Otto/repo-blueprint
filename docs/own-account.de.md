---
description: Repo Blueprint für dein eigenes GitHub-Konto oder deine Organisation, mit eigener Release-App, Renovate in deinen eigenen Repositorys oder als Mend-App und dem Issue-Assistenten mit oder ohne KI.
---

# Dein eigenes Konto

Der Blueprint funktioniert für jedes Konto und jede Organisation auf GitHub. Ein Repository daraus nennt nichts vom Eigentümer des Blueprints außer den Links auf den Blueprint und seine Werkzeuge, und jeder Bot läuft als eine App von dir. Diese Seite führt durch ein neues eigenes Repository, von der Kopie bis zu einer Checkliste ohne Kreuz.

## Was du mitbringst und was optional ist

- **Eine Release-App,** einmal für alle deine Repositorys, als die die Bots handeln: Ihr Token startet die Checks der Release- und Update-Pull-Requests, darf Workflows ändern und legt die Release-Tags an, was das Token eines Jobs nicht kann. Nur der Eigentümer einer App hat ihren privaten Schlüssel, darum kann der Blueprint seine eigene nicht verleihen.
- **Renovate,** das die Abhängigkeiten aktuell hält: in einem Workflow jedes Repositorys, als deine Release-App, oder als Mend-Renovate-App, die du installierst. Der Renovate-Workflow des Blueprints läuft nur für die Repositorys des Eigentümers des Blueprints.
- **Die KI des Issue-Assistenten** ist optional. Ohne sie labelt der Issue-Assistent neue Issues weiter, erinnert und schließt und führt die Befehle des Maintainers aus, und es braucht kein Secret.
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

## 4. Die Einstellungen anwenden

```sh
python3 ../repo-blueprint/blueprint.py settings apply
```

Es setzt alles, was die API setzen kann: die Rulesets, die Variablen, die die App nennen, die Environments, die Sicherheitsfunktionen und die Actions, die laufen dürfen.

## 5. Renovate

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="images/diagrams/who-runs-renovate.de.dark.svg">
  <img src="images/diagrams/who-runs-renovate.de.svg" alt="Wer Renovate ausführt: Die Antwort renovate_runner entscheidet, wer Renovate für ein Repository ausführt. Der Eigentümer des Blueprints behält den Hub, den Renovate-Workflow des Blueprints, der es für jedes seiner Repositorys ausführt, auf dem die Release-App installiert ist. Jeder andere Eigentümer bekommt einen Renovate-Workflow im Repository selbst, der es alle zwei Stunden als Release-App ausführt, nur für dieses Repository, mit demselben Renovate und denselben Regeln; oder er installiert die Mend-Renovate-App, die keinen Workflow braucht und bei jedem Push kommt. Jeder Weg liest die Regeln aus .github/renovate.json5 und öffnet die Updates als Pull Requests, deren Checks entscheiden, ob sie gemergt werden.">
</picture>

Jeder Weg liest dieselben Regeln, die des Blueprints in `.github/renovate-blueprint.json5` und deine in `.github/renovate.json5`, und hält kein Issue offen: Was auf dich wartet, ist ein Pull Request. Die Checkliste hakt Renovate ab, sobald es einen Pull Request geöffnet hat.

- **`self`, ein Workflow des Repositorys:** `.github/workflows/renovate.yml` führt Renovate alle zwei Stunden als deine Release-App aus, mit einem Token nur für dieses Repository und ohne *Administration*. Es ist der Workflow des Hubs des Blueprints, mit demselben Renovate, gepinnt auf seinen Digest, das jedes Update des Blueprints weiterbewegt, und `.github/renovate-global.json5` hält die Einstellungen des Bots: Commits über die API, die GitHub signiert, und keine Skripte der Paketmanager. Der Bot-Benutzer deiner App ist der Autor, nach dem der Workflow GitHub fragt. Sein erster Lauf startet von selbst; *Actions → Renovate → Run workflow* startet sofort einen. Ein Lauf ohne die Release-App sagt in seiner Zusammenfassung, was fehlt, und ein Pull Request, der die Regeln oder eine Lock-Datei ändert, zeigt, ob Renovate sie weiter annimmt und liest.
- **`mend`, die Mend-Renovate-App:** Installiere die [Mend-Renovate-App](https://github.com/apps/renovate) auf dem Repository. Sie liest dieselben Regeln, kommt bei jedem Push statt nach einem Zeitplan und braucht keinen Workflow und kein Token von dir. Der Branch-Bot und der Fix-Bot aktualisieren ihre Branches als deine Release-App, also trag den Bot-Benutzer der App in `gitIgnoredAuthors` in `.github/renovate.json5` ein, sonst hält Renovate die Branches für bearbeitet und rebased sie nicht mehr; die Checkliste gibt die Zeile mit der Nummer des Bot-Benutzers deiner App aus.

Um die Antwort später zu ändern, führ `copier update --defaults --vcs-ref=:current: --data renovate_runner=mend` aus und committe das Update.

## 6. Der Issue-Assistent

Mit `issue_assistant_ai` analysiert der Issue-Assistent jedes neue Issue mit Claude, und die Checkliste fragt nach seinem Token, als Secret `CLAUDE_CODE_OAUTH_TOKEN` des Environments `issue-assistant`. Ohne sie setzt `.github/repository.toml` die Variable `ISSUE_ASSISTANT_AI` auf `off`, das Environment fragt nach keinem Secret, und `SUPPORT.md` sagt den Meldenden, dass keine KI ihre Issues liest; Labels, Erinnerungen, Schließen und die Befehle des Maintainers funktionieren wie bisher. `copier update --defaults --vcs-ref=:current: --data issue_assistant_ai=true` schaltet die KI später ein.

## 7. Die Checkliste

```sh
python3 ../repo-blueprint/blueprint.py checklist
```

Sie zeigt, was für einen Menschen bleibt und welche Schritte erledigt sind: die Release-App, die Einstellungen, die Secrets, die Installation, Renovate, das Community-Profil, die Social-Preview und die Badges. Sobald jeder Schritt seinen Haken hat, kümmert sich das Repository um sich selbst.
