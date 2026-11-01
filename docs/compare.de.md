---
description: "Repo Blueprint neben Template-Repositorys von GitHub, Cookiecutter mit cruft, anderen Copier-Vorlagen wie copier-uv und scientific-python/cookie und projen, Punkt für Punkt, auch dort, wo ein anderes Werkzeug besser passt."
---

# Repo Blueprint im Vergleich mit Template-Repositorys, Cookiecutter, Copier-Vorlagen und projen

Jedes Werkzeug auf dieser Seite macht aus einer Vorlage ein neues Repository. Sie unterscheiden sich darin, was nach dem Kopieren geschieht: ob Verbesserungen der Vorlage das Repository später erreichen, ob Code der Vorlage auf deinem Rechner läuft und wie viel vom Repository über seine Dateien hinaus sie pflegen. Diese Seite sagt, wo der Blueprint vorne liegt und wo ein anderes Werkzeug besser passt.

Die Werkzeuge: [Template-Repositorys](https://docs.github.com/de/repositories/creating-and-managing-repositories/creating-a-repository-from-a-template) von GitHub, [Cookiecutter](https://github.com/cookiecutter/cookiecutter) mit [cruft](https://github.com/cruft/cruft), andere Vorlagen für [Copier](https://copier.readthedocs.io/), etwa [copier-uv](https://github.com/pawamoy/copier-uv) und [scientific-python/cookie](https://github.com/scientific-python/cookie), und [projen](https://github.com/projen/projen).

## Wo der Blueprint vorne liegt

- **Ein getestetes Ausrollen in jedes Repository.** Bevor eine Änderung der Vorlage merged, macht der Workflow Variants daraus ein neues Repository jeder Art und aktualisiert eines jeder Art von der neuesten Version, und der Workflow Downstream aktualisiert damit einen Klon jedes echten Repositorys. Nach dem Release startet der Workflow Rollout den Blueprint-Bot jedes Repositorys, eines nach dem anderen; der Bot prüft das signierte Release, führt `copier update` aus und hält einen Pull Request, der merged, sobald alle Prüfungen grün sind.
- **Beim Kopieren läuft kein Code der Vorlage.** Die Vorlage hat keine Tasks, Migrationen oder Jinja-Erweiterungen, also braucht Copier kein `--trust`, weder beim Kopieren noch bei einem Update.
- **Einstellungen als Code, mit einem Bot gegen Abweichungen.** Die Rulesets, die Sicherheit, Actions, die Environments, die Variablen, die Labels und GitHub Pages stehen in `.github/repository.toml`, und der Einstellungs-Bot wendet sie nach jeder Änderung und jede Woche an.
- **Releases nach SLSA Build Level 3, mit SBOMs und VEX.** Ein Release hat signierte Tags, die Provenance eines isolierten Builds (ein Container-Image die des Release-Workflows, Level 2), SBOMs als SPDX und CycloneDX, ein OpenVEX-Dokument und ein unveränderliches Release, und sein Workflow prüft es so, wie seine Nutzer es können, auch jede Woche.
- **Home Assistant, Nextcloud und GitHub Actions in einem Standard,** neben Python- und Node-Paketen, Chrome-Erweiterungen, Containern und Repositories ohne Build: dieselben Prüfungen, Bots und Einstellungen für jede Art, mit den Werkzeugen jeder Art.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="images/diagrams/how-a-change-of-the-template-meets-the-repositories.de.dark.svg">
  <img src="images/diagrams/how-a-change-of-the-template-meets-the-repositories.de.svg" alt="Wie eine Änderung der Vorlage die Repositories vor ihrem Release trifft: Ein Pull Request ändert, was die Repositories vom Blueprint bekommen. Der Variants-Workflow erzeugt ein neues Repository jeder Art, bringt eines jeder Art vom letzten Release auf den Stand und eines mit den Antworten jedes Repositorys aus tests/answers, das jede Datei so bekommen muss wie ein neues Repository mit diesen Antworten und den Bau seiner Website und den Lint seiner Workflows und seines Markdowns bestehen muss. Der Downstream-Workflow klont jedes Repository und aktualisiert es wie sein Blueprint-Bot, auf main und auf den Pull Request, und nennt die Dateien, deren Update der Pull Request ändert, und jeden Konflikt; ein Konflikt, den der Pull Request in einen Workflow oder ein Skript bringt, lässt ihn scheitern. Dann wird der Pull Request gemergt, und das Release und der Rollout bringen ihn in jedes Repository.">
</picture>

## Punkt für Punkt

Ein Strich heißt, dass das Werkzeug es nicht tut; *die Vorlage* heißt, dass es davon abhängt, was die Vorlage mitbringt.

| | Repo Blueprint | Template-Repository | Cookiecutter + cruft | Andere Copier-Vorlagen | projen |
| --- | --- | --- | --- | --- | --- |
| Änderungen der Vorlage nach dem Kopieren | ein Bot bringt jede Version als Pull Request | — | `cruft update` von Hand; `cruft check` scheitert, wenn es zurückliegt | `copier update` von Hand | jeder Lauf von `projen` schreibt die Dateien neu |
| Updates getestet, bevor sie ankommen | an jeder Art und an den echten Repositories | — | — | die Vorlage | — |
| Code, der beim Kopieren läuft | keiner; danach `blueprint.py create` aus der Kopie, das du selbst startest | keiner | die Hooks der Vorlage, falls es welche gibt | die Tasks, Migrationen und Erweiterungen der Vorlage, falls es welche gibt, mit `--trust` | `.projenrc` bei jedem Lauf |
| Was ein neues Repository braucht | Git, Python, uv und die GitHub CLI | einen Knopf auf GitHub | Python und `cookiecutter` | Python und `copier` | Node und `npx projen new` |
| Einstellungen des Repositorys | als Code, mit einem Bot gegen Abweichungen | — | die Vorlage | die Vorlage | — |
| Releases | release-please, signierte Tags, SLSA Build Level 3 (Container-Images: Level 2), SBOM, VEX, geprüft | die Vorlage | die Vorlage | die Vorlage | nach npm, und mit jsii nach PyPI, Maven, NuGet und Go |
| Sicherheitsprüfungen | CodeQL, Scorecard, zizmor, OSV-Scanner, Harden-Runner, ein Secret-Scan, Actions auf Commits festgelegt | die Vorlage | die Vorlage | die Vorlage | die Vorlage |
| Updates der Abhängigkeiten | Renovate, mit Regeln für den Merge und einem Dashboard | die Vorlage | die Vorlage | die Vorlage | ein Workflow, der sie aktualisiert |
| Arten von Projekten | acht, von Home Assistant bis zu Chrome-Erweiterungen und Containern | eine je Vorlage | Tausende Vorlagen, je ein Stack | copier-uv: Python; cookie: Python mit vielen Build-Backends | TypeScript, AWS CDK, jsii, Python, Java und mehr |
| Systeme in der CI | Linux, auf jedem Kern | die Vorlage | die Vorlage | copier-uv und cookie: Linux, macOS und Windows | die Vorlage |
| Prüfung beliebiger Repositories | — | — | — | cookie: sp-repo-review | — |
| Sichtung von Issues | der Issue-Assistent | — | — | — | — |

## Wo ein anderes Werkzeug besser passt

- **Eine Kopie per Knopf und sonst nichts.** Ein Template-Repository von GitHub braucht keine Werkzeuge, keine Fragen und keine App und ist der einfachste Start für ein Repository, das seiner Vorlage später nicht folgen soll.
- **Mehrere Systeme in der CI und uv für das Projekt.** copier-uv und scientific-python/cookie testen auf Linux, macOS und Windows mit mehreren Versionen von Python, und copier-uv verwaltet das Projekt mit uv. Ein Repository des Blueprints testet auf einem Linux-Runner, auf jedem Kern, und installiert seine Werkzeuge in der CI mit uv aus Lock-Dateien mit Hashes; nur der Blueprint selbst führt seine Prüfungen auch unter Windows aus.
- **Eine Prüfung beliebiger Repositories.** [sp-repo-review](https://pypi.org/project/sp-repo-review/) prüft ein Repository gegen den Entwicklungsleitfaden von Scientific Python, auch eines, das keine Vorlage gemacht hat. Die Prüfungen des Blueprints sehen auf Repositories, die aus ihm entstanden sind.
- **Eine Wahl der Build-Backends.** cookie bietet eine Vorlage für Hatchling, Flit, PDM, Poetry, setuptools, scikit-build-core, meson-python, maturin und weitere; der Blueprint baut Python mit Hatchling.
- **Projekte, die in Code definiert sind.** projen passt vor allem zu AWS CDK und jsii, deren viele Dateien es aus einer Definition in Code hält.
- **Einfachheit.** Ein Repository des Blueprints startet mit mehr als 30 Workflows, einer Release-App und Einstellungen als Code. Ein kleines Projekt, das nichts davon will, ist mit einer kleineren Vorlage besser bedient.

## Eines anlegen

[Der Schnellstart](guide.md#ein-repository-anlegen) legt ein Repository mit drei Befehlen an, und jede Art von Projekt hat eine eigene Seite: [Home-Assistant-Integration](kinds/home-assistant.md), [Nextcloud-App](kinds/nextcloud-app.md), [GitHub Action](kinds/github-action.md), [Python-Paket](kinds/python-package.md), [Node-Paket](kinds/node-package.md), [Chrome-Erweiterung](kinds/chrome-extension.md), [Container-Image](kinds/container.md) und [Repository ohne Build](kinds/generic.md).
