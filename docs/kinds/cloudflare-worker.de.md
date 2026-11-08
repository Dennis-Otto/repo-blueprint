---
description: "Eine Vorlage für einen Cloudflare Worker in TypeScript: Tests, die in workerd laufen, der Laufzeitumgebung von Cloudflare, mit jeder Zeile abgedeckt, und jedes Release ausgeliefert von Workers Builds von Cloudflare, ohne einen Schlüssel von Cloudflare in GitHub."
---

# Vorlage für Cloudflare Worker mit Tests in workerd und Auslieferung ohne Schlüssel in GitHub

Ein Cloudflare Worker in TypeScript auf Node 24, dessen Tests in workerd laufen, der Laufzeitumgebung von Cloudflare Workers, und den Cloudflare aus jedem Release von selbst ausliefert, ohne dass ein Schlüssel von Cloudflare in GitHub liegt.

## Einen anlegen

```sh
uvx --from copier==9.19.1 copier copy --data project_type=cloudflare-worker gh:Dennis-Otto/repo-blueprint my-worker
cd my-worker
python3 .github/blueprint.py create
```

Mit [uv](https://docs.astral.sh/uv/) und der GitHub CLI, wie [der Schnellstart](../guide.md#ein-repository-anlegen) zeigt. Copier fragt nach dem Namen, dem Eigentümer und den anderen Antworten, und `create` legt das Repository auf GitHub an, wendet die Einstellungen als Code an und zeigt die Checkliste.

## Was du bekommst

- **Das Beispiel:** ein Worker in `src/index.ts`, der `GET /?name=Ada` mit einem Gruß in JSON beantwortet und jeden anderen Pfad und jede andere Methode ablehnt, der Code, den er aufruft, in `src/greet.ts`, und seine Tests in `test/`. `wrangler.jsonc` hält den Namen des Workers, sein Hauptmodul, sein Kompatibilitätsdatum und seine Bindings. Ersetze es durch den echten Worker; seine Tests zeigen, wie.
- **Tests in der Laufzeitumgebung von Cloudflare:** Vitest führt sie in workerd aus, mit den Bindings aus `wrangler.jsonc`, über die [Vitest-Integration von Cloudflare](https://developers.cloudflare.com/workers/testing/vitest-integration/), und jede Anfrage erreicht den Worker, wie eine aus dem Internet es täte. Ein Geheimnis liegt nur bei Cloudflare, also ruft ein Test, der eines braucht, den Worker aus `src/index.ts` mit einem eigenen `env` auf: `worker.fetch(request, { ...env, TOKEN: "test" }, createExecutionContext())`, mit `env` und `createExecutionContext` aus `cloudflare:test`. `npm run dev` startet ihn auf deinem Rechner.
- **Die Schritte von `scripts/check.sh` für diese Art,** auf deinem Rechner wie in der CI: die Lock-Datei, Biome, tsc auf den Typen, die Wrangler aus `wrangler.jsonc` schreibt, die Tests mit jeder Zeile, jedem Zweig und jeder Funktion abgedeckt, und dann *Worker*, der den Worker mit Wrangler bündelt, wie Cloudflare es tut, ohne Upload und ohne Anmeldung.
- **Workflows dieser Art:** das neueste Node auf `main` (`newest-node.yml`); Cloudflare baut und liefert den Worker selbst aus, also hält kein Workflow einen Schlüssel von Cloudflare.
- **Die Schritte jeder Art:** die Textdateien, die Diagramme, die Seiten in einer Spalte, die Dateien des Projekts, die Fragmente des Changelogs, die akzeptierten Advisories, die Lock-Dateien, die Version, die Git-Hooks, ShellCheck für die Shell-Skripte und der strenge Build der Website.
- **Alles, was jedes Repository bekommt:** den PR-Coach und den Fix-Bot, den Release-Bot, Renovate, die Einstellungen als Code, den Issue-Assistenten, die Website auf Deutsch und Englisch, die Sicherheitsprüfungen und den Blueprint-Bot, wie [die Anleitung](../guide.md#was-ein-neues-repository-bekommt) sie nennt.

## Die Prüfungen, die ein Pull Request braucht

Das Ruleset *Protect main* aus `.github/repository.toml` lässt einen Pull Request mergen, sobald diese Prüfungen grün sind:

- `check (node)`: `scripts/check.sh` mit den Werkzeugen von Node, den Tests in workerd und dem Bündel des Workers.
- `lint`, `diagrams`, `docs`, `conventional title`, `codeql`, `dependency-review` und `gitleaks`, die jede Art braucht: jeder Linter in einem Job, die Bilder der Diagramme, der strenge Build der Website, der Titel des Pull Requests mit seinem Eintrag im Changelog, CodeQL, die Prüfung neuer Abhängigkeiten und der Secret-Scan.

## Auslieferung

[Workers Builds](https://developers.cloudflare.com/workers/ci-cd/builds/), die Integration von Cloudflare mit GitHub, baut jeden Commit von `main` bei Cloudflare und führt `npm run deploy` aus. Sein Skript, `scripts/deploy-worker.sh`, liefert nur den Merge des Release-Pull-Requests aus, `chore: release X.Y.Z`, als Version `vX.Y.Z`; jeder andere Commit wird eine Version ohne Verkehr, die das Dashboard auflistet. Der Release-Workflow taggt denselben Commit und veröffentlicht das Release mit seinen SBOMs und der signierten Provenance seines isolierten Builds, also ist der Worker, der läuft, der Code des neuesten Releases.

Kein Schlüssel von Cloudflare liegt in GitHub: Ein API-Token von Cloudflare lässt sich nicht auf einen Worker beschränken, und Workers Builds braucht keines. Die Geheimnisse des Workers liegen bei Cloudflare, gesetzt mit `npx wrangler secret put`. [Entscheidung 0115](../decisions/0115-cloudflare-deploys-a-worker-from-its-release-with-workers-builds.md) hält fest, warum.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/how-a-cloudflare-worker-goes-live.de.dark.svg">
  <img src="../images/diagrams/how-a-cloudflare-worker-goes-live.de.svg" alt="Wie ein Cloudflare Worker live geht: Du mergst einen Pull Request in main, nachdem jede nötige Prüfung bestanden hat. Workers Builds von Cloudflare baut den Commit mit der Lock-Datei des Repositorys und führt npm run deploy aus, dessen Skript fragt, ob der Commit ein Release ist. Ein gewöhnlicher Commit wird eine Version des Workers ohne Verkehr, die das Dashboard auflistet. Der Merge des Release-Pull-Requests geht mit seiner Version live; der Release-Workflow taggt denselben Commit und veröffentlicht das Release auf GitHub, mit seinen SBOMs und signierter Provenance. Kein Schlüssel von Cloudflare liegt in GitHub.">
</picture>

## Einmal von Hand

`python3 .github/blueprint.py checklist` hakt jeden Schritt ab, den es sehen kann, und nennt den Rest, jeweils mit seinem Link: die Release-App des Eigentümers mit ihrem privaten Schlüssel, wie [dein eigenes Konto](../own-account.md) zeigt, das Token des Issue-Assistenten, außer seine KI ist aus, OpenSSF Best Practices, die REUSE-API und die Social Preview.

Diese Art bringt diese Schritte dazu:

- Den Worker mit seiner ersten Auslieferung von deinem Rechner anlegen, `npx wrangler login` und `npx wrangler deploy`, wobei die Anmeldung dort bleibt.
- Das Repository im Dashboard von Cloudflare verbinden, unter *Settings* und *Builds* des Workers, mit der App von Cloudflare nur für dieses Repository installiert, dem Build-Befehl `npm ci --ignore-scripts`, der Build-Variable `SKIP_DEPENDENCY_INSTALL` auf `1`, damit Cloudflare kein Installationsskript eines Pakets ausführt, und dem Deploy-Befehl `npm run deploy`.
- Jedes Geheimnis des Workers mit `npx wrangler secret put NAME` bei Cloudflare hinterlegen.

Sie geschehen bei Cloudflare, also nennt die Checkliste die ersten beiden als einen Schritt, den sie nicht abhaken kann.

`docs/releases.md` des neuen Repositorys beschreibt jeden Schritt, wie man ein Release zurückrollt und was zu tun ist, wenn ein Build fehlschlägt.

## Ein echtes Repository

<!-- --8<-- [start:real-repository] -->

[Repo Pager](https://github.com/Dennis-Otto/repo-pager) ist aus dem Blueprint entstanden: ein privater Telegram-Pager, den jeder Maintainer für seine eigenen Repositories betreibt und der nur meldet, was ihn braucht, und es per Button erledigt.

Der Workflow Variants probiert jeden Pull Request des Blueprints, der ändert, was die Antworten von Repo Pager rendern, mit ihnen aus, bevor er merged.

<!-- --8<-- [end:real-repository] -->

Wie sich der Blueprint mit anderen Vorlagen vergleicht: [der Vergleich](../compare.md).
