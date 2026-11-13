"""Tests of the check of the catalogs of the translations: those of a Home Assistant
integration, of a Nextcloud app and of a Chrome extension, and translations --fix."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from blueprint import cli
from blueprint.translations import (
    Finding,
    browser_catalog,
    check,
    line_of,
    nextcloud_placeholders,
    registered,
)

INTEGRATION = "custom_components/demo"
SOURCE = {
    "config": {
        "abort": {"single": "Already set up for {name}."},
        "step": {"user": {"title": "Set up", "description": "Set it up?"}},
    }
}
GERMAN = {
    "config": {
        "abort": {"single": "Schon für {name} eingerichtet."},
        "step": {"user": {"title": "Einrichten", "description": "Einrichten?"}},
    }
}


def files(root: Path, entries: dict[str, Any]) -> Path:
    """Writes each file, JSON as the catalogs have it, a str as it is."""
    for name, value in entries.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        text = value if isinstance(value, str) else json.dumps(value, indent=2) + "\n"
        path.write_text(text, encoding="utf-8")
    return root


def messages(found: list[Finding]) -> list[str]:
    return [finding.text() for finding in found]


def test_no_catalogs_nothing_to_check(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # A manifest of another kind, or a broken one, is no extension with languages.
    files(
        tmp_path,
        {
            "manifest.json": {"name": "demo"},
            "other/manifest.json": "[",
            "node_modules/x/manifest.json": {"default_locale": "en"},
            "list/manifest.json": "[]",
            f"{INTEGRATION}/translations/README": "",
        },
    )
    assert cli.main(["translations"], root=tmp_path) == 0
    assert capsys.readouterr().out == (
        "No catalogs of translations, so nothing to check.\n"
    )


def test_the_line_of_a_key() -> None:
    text = json.dumps(SOURCE, indent=2)
    assert line_of(text, ("config", "step", "user", "title")) == 8
    assert line_of(text, ("config", "missing")) == 0


# ---------------------------------------------------------------- Home Assistant


def test_an_integration_whose_translations_follow_their_source(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    files(
        tmp_path,
        {
            f"{INTEGRATION}/translations/en.json": SOURCE,
            f"{INTEGRATION}/translations/de.json": GERMAN,
        },
    )
    assert cli.main(["translations"], root=tmp_path) == 0
    assert capsys.readouterr().out == (
        "Each of the 1 catalog(s) of translations has the texts of its source, with "
        "their placeholders, and no other.\n"
    )


def test_what_a_translation_of_an_integration_gets_wrong(tmp_path: Path) -> None:
    german: dict[str, Any] = {
        "config": {
            "step": {"user": {"title": "", "stale": "Alt"}},
            "abort": {"single": "Schon eingerichtet für {other}."},
        }
    }
    files(
        tmp_path,
        {
            f"{INTEGRATION}/strings.json": SOURCE,
            f"{INTEGRATION}/translations/de.json": german,
            f"{INTEGRATION}/translations/fr.json": "{",
            f"{INTEGRATION}/translations/nl.json": "[]",
        },
    )

    result = check(tmp_path)

    translations = f"{INTEGRATION}/translations"
    assert result.catalogs == 1
    assert messages(result.findings) == [
        f"{translations}/en.json: is not the copy of {INTEGRATION}/strings.json, "
        "which Home Assistant shows in English",
        f"{translations}/de.json:6: has 1 text(s) that {INTEGRATION}/strings.json "
        "doesn't have, such as config.step.user.stale",
        f"{translations}/de.json: lacks 1 of the texts of {INTEGRATION}/strings.json, "
        "such as config.step.user.description: write them in its language",
        f"{translations}/de.json:5: has no words for config.step.user.title",
        f"{translations}/de.json:10: shows the placeholders {{other}} in "
        f"config.abort.single, but {INTEGRATION}/strings.json {{name}}: each stands "
        "for a value, so keep those of the source",
        f"{translations}/fr.json: is no JSON: Expecting property name enclosed in "
        "double quotes: line 1 column 2 (char 1)",
        f"{translations}/nl.json: holds no object of texts",
    ]
    assert [finding.fixable for finding in result.findings[:2]] == [True, True]


def test_translations_fix_brings_an_integration_in_step(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    german = {
        "config": {
            "step": {"user": {"description": "Einrichten?", "title": "Einrichten"}},
            "abort": {"single": "Schon für {name} eingerichtet.", "stale": "Alt"},
        }
    }
    files(
        tmp_path,
        {
            f"{INTEGRATION}/strings.json": SOURCE,
            f"{INTEGRATION}/translations/en.json": {"old": "x"},
            f"{INTEGRATION}/translations/de.json": german,
        },
    )
    translations = tmp_path / INTEGRATION / "translations"
    # In another order only, the check says so, and --fix orders it.
    assert messages(check(tmp_path).findings)[1] == (
        f"{INTEGRATION}/translations/de.json:11: has 1 text(s) that "
        f"{INTEGRATION}/strings.json doesn't have, such as config.abort.stale"
    )

    assert cli.main(["translations", "--fix"], root=tmp_path) == 0

    out = capsys.readouterr().out
    assert out.startswith(
        f"{INTEGRATION}/translations/en.json: in step with its source now\n"
        f"{INTEGRATION}/translations/de.json: in step with its source now\n"
    )
    assert (translations / "en.json").read_text(encoding="utf-8") == (
        tmp_path / INTEGRATION / "strings.json"
    ).read_text(encoding="utf-8")
    assert (translations / "de.json").read_text(encoding="utf-8") == (
        json.dumps(GERMAN, indent=2, ensure_ascii=False) + "\n"
    )
    files(
        tmp_path,
        {
            f"{INTEGRATION}/translations/de.json": {
                "config": {"step": GERMAN["config"]["step"], "abort": {}}
            }
        },
    )
    assert messages(check(tmp_path).findings) == [
        f"{INTEGRATION}/translations/de.json: has its texts in another order than "
        f"{INTEGRATION}/strings.json",
        f"{INTEGRATION}/translations/de.json: lacks 1 of the texts of "
        f"{INTEGRATION}/strings.json, such as config.abort.single: write "
        "them in its language",
    ]


def test_a_source_of_an_integration_that_says_nothing(tmp_path: Path) -> None:
    files(tmp_path, {f"{INTEGRATION}/translations/en.json": "{"})
    assert messages(check(tmp_path).findings) == [
        f"{INTEGRATION}/translations/en.json: is no JSON: Expecting property name "
        "enclosed in double quotes: line 1 column 2 (char 1)"
    ]
    files(tmp_path, {f"{INTEGRATION}/strings.json": "[]"})
    assert messages(check(tmp_path).findings) == [
        f"{INTEGRATION}/strings.json: holds no object of texts"
    ]
    files(tmp_path, {f"{INTEGRATION}/strings.json": {"title": " ", "count": 3}})
    assert messages(check(tmp_path).findings)[1:] == [
        f"{INTEGRATION}/strings.json:2: has no words for title",
        f"{INTEGRATION}/strings.json:3: has no words for count",
    ]


# ---------------------------------------------------------------- Nextcloud

PLURAL_FORM = "nplurals=2; plural=(n != 1);"
NEXTCLOUD = {
    "Files": "Dateien",
    "%s of %s": "%2$s von %1$s",
    "Open {file}": "{file} öffnen",
    "_%n document_::_%n documents_": ["ein Dokument", "%n Dokumente"],
}


def nextcloud_files(texts: dict[str, Any], plural: str = PLURAL_FORM) -> dict[str, Any]:
    return {
        "appinfo/info.xml": "<info>\n  <id>demo_app</id>\n</info>\n",
        "l10n/de.json": {"translations": texts, "pluralForm": plural},
        "l10n/de.js": browser_catalog("demo_app", texts, plural),
    }


def test_the_placeholders_of_nextcloud() -> None:
    assert nextcloud_placeholders("%s of %s, %d and {name}, %n") == {
        "%1$s": 1,
        "%2$s": 1,
        "%3$d": 1,
        "{name}": 1,
        "%n": 1,
    }
    assert nextcloud_placeholders("%2$s von %1$s") == nextcloud_placeholders("%s of %s")


def test_an_app_whose_catalogs_agree(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    files(tmp_path, nextcloud_files(NEXTCLOUD))
    assert cli.main(["translations"], root=tmp_path) == 0
    assert "Each of the 1 catalog(s)" in capsys.readouterr().out
    script = (tmp_path / "l10n/de.js").read_text(encoding="utf-8")
    assert script.startswith('OC.L10N.register(\n\t"demo_app",\n\t{\n\t\t"Files": ')
    assert script.endswith('\t},\n\t"nplurals=2; plural=(n != 1);"\n)\n')
    assert registered(script) == ("demo_app", NEXTCLOUD, PLURAL_FORM)
    # One that Nextcloud wrote itself, with a semicolon, reads the same.
    assert registered(script.replace("\n)\n", ");\n")) == registered(script)
    assert registered("OC.L10N.register(x, {}, '')") is None
    assert registered('OC.L10N.register("a", {,}, "")') is None
    assert registered('OC.L10N.register("a", [], "")') is None
    assert registered('OC.L10N.register("a", {})') is None
    assert registered("window.OC = {}") is None


def js_quote(text: Any) -> str:
    """A string in single quotes, as scripts/check-l10n.mjs of a project writes it."""
    if not isinstance(text, str):
        return f"[{', '.join(js_quote(each) for each in text)}]"
    escaped = text.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
    return f"'{escaped}'"


def test_a_browser_catalog_in_single_quotes_reads_as_its_meaning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # As paperless-unified-search writes it with its own tool: single quotes, escapes
    # and a comma after the last text.
    files(tmp_path, nextcloud_files(NEXTCLOUD))
    texts = "".join(
        f"\t\t{js_quote(key)}: {js_quote(value)},\n" for key, value in NEXTCLOUD.items()
    )
    script = (
        f"OC.L10N.register(\n\t'demo_app',\n\t{{\n{texts}\t}},\n\t"
        f"{js_quote(PLURAL_FORM)})\n"
    )
    (tmp_path / "l10n/de.js").write_text(script, encoding="utf-8")
    assert registered(script) == ("demo_app", NEXTCLOUD, PLURAL_FORM)
    assert cli.main(["translations"], root=tmp_path) == 0
    assert "Each of the 1 catalog(s)" in capsys.readouterr().out
    # Left as it is: it says what the .json says.
    assert (tmp_path / "l10n/de.js").read_text(encoding="utf-8") == script


@pytest.mark.parametrize(
    ("literal", "meaning"),
    [
        (r"'can\'t'", "can't"),
        (r'"say \"hi\""', 'say "hi"'),
        (r"'a\\b'", "a\\b"),
        (r"'\n\r\t\b\f\v\0'", "\n\r\t\b\f\v\0"),
        (r"'ä\u{1F600}\x41'", "ä\U0001f600A"),
        ("'one \\\ntwo'", "one two"),
        (r"'\q'", "q"),
        ("'Ä {name}, %s'", "Ä {name}, %s"),
        ("'a,}'", "a,}"),
    ],
)
def test_a_string_of_javascript_means_what_javascript_reads(
    literal: str, meaning: str
) -> None:
    assert registered(f"OC.L10N.register({literal}, {{}}, '')") == (meaning, {}, "")


def test_a_trailing_comma_only_ends_a_list() -> None:
    assert registered("OC.L10N.register('a', {'x': ['y', 'z',],}, '',)") == (
        "a",
        {"x": ["y", "z"]},
        "",
    )
    assert registered("OC.L10N.register('a', {'x': 'y',,}, '')") is None
    assert registered("OC.L10N.register('a', ['x' 'y'], '')") is None
    assert registered("OC.L10N.register('a', {'x': 'y}, '')") is None


def test_what_a_catalog_of_an_app_gets_wrong(tmp_path: Path) -> None:
    texts = {
        "Files": " ",
        "%s of %s": "%s",
        "Open {file}": "Öffnen",
        "_%n document_::_%n documents_": ["%n Dokument"],
        "_%n file_::_%n files_": ["eine Datei", ""],
        "_%n folder of %s_::_%n folders of %s_": ["ein Ordner", "%n Ordner von %s"],
        "_%n tag_::_%n tags_": "Tags",
    }
    files(
        tmp_path,
        {
            **nextcloud_files(texts),
            "l10n/fr.json": {"translations": {"Files": "Fichiers"}},
            "l10n/nl.json": {
                "translations": {"Files": "Bestanden", "Extra": "Extra"},
                "pluralForm": "nplurals=2; plural=(n != 1);",
            },
            "l10n/es.json": "{",
        },
    )

    found = messages(check(tmp_path).findings)

    assert found == [
        'l10n/de.json:3: has no words for "Files"',
        'l10n/de.json:4: shows the placeholders %1$s in "%s", but "%s of %s" '
        "%1$s, %2$s: each stands for a value, so keep them",
        'l10n/de.json:5: shows the placeholders none in "Öffnen", but "Open {file}" '
        "{file}: each stands for a value, so keep them",
        'l10n/de.json:6: has 1 form(s) for "_%n document_::_%n documents_", but its '
        "pluralForm names 2",
        'l10n/de.json:9: has a form without words for "_%n file_::_%n files_"',
        'l10n/de.json:13: shows the placeholders none in "ein Ordner", but '
        '"_%n folder of %s_::_%n folders of %s_" %1$s: each stands for a value, so '
        "keep them",
        'l10n/de.json:17: has no list of form(s) for "_%n tag_::_%n tags_", but its '
        "pluralForm names 2",
        "l10n/es.json: is no JSON: Expecting property name enclosed in double "
        "quotes: line 1 column 2 (char 1)",
        'l10n/fr.json: holds no object "translations" with a rule "pluralForm", '
        'such as "nplurals=2; plural=(n != 1);"',
        "l10n/nl.js: is missing: the browser loads the texts of l10n/nl.json from it",
        'l10n/de.json: lacks 1 text(s) that l10n/nl.json has, such as "Extra": '
        "translate them, or remove them from every catalog when the code no longer "
        "uses them",
        'l10n/nl.json: lacks 6 text(s) that l10n/de.json has, such as "%s of %s": '
        "translate them, or remove them from every catalog when the code no longer "
        "uses them",
    ]


def test_translations_fix_writes_the_catalogs_of_the_browser(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    files(
        tmp_path,
        {
            **nextcloud_files(NEXTCLOUD),
            "l10n/de.js": browser_catalog("own_id", {"Files": "Alt"}, PLURAL_FORM),
            "l10n/nl.json": {
                "translations": {key: key for key in NEXTCLOUD}
                | {"_%n document_::_%n documents_": ["%n document", "%n documenten"]},
                "pluralForm": PLURAL_FORM,
            },
        },
    )
    assert messages(check(tmp_path).findings)[0] == (
        "l10n/de.js: doesn't say what l10n/de.json says, which the browser would "
        "show otherwise than PHP"
    )

    assert cli.main(["translations", "--fix"], root=tmp_path) == 0

    assert capsys.readouterr().out.startswith(
        "l10n/de.js: in step with its source now\nl10n/nl.js: in step with its "
        "source now\n"
    )
    # The id that the file had, else that of appinfo/info.xml.
    de = (tmp_path / "l10n/de.js").read_text(encoding="utf-8")
    assert registered(de) == ("own_id", NEXTCLOUD, PLURAL_FORM)
    nl = registered((tmp_path / "l10n/nl.js").read_text(encoding="utf-8"))
    assert nl is not None
    assert nl[0] == "demo_app"
    (tmp_path / "appinfo/info.xml").unlink()
    (tmp_path / "l10n/nl.js").unlink()
    assert cli.main(["translations", "--fix"], root=tmp_path) == 0
    nl = registered((tmp_path / "l10n/nl.js").read_text(encoding="utf-8"))
    assert nl is not None
    assert nl[0] == tmp_path.resolve().name
    assert "nplurals" not in PLURAL_FORM.replace("nplurals=2", "")
    files(tmp_path, {"l10n/nl.json": {"translations": {}, "pluralForm": "plural=0;"}})
    assert cli.main(["translations", "--fix"], root=tmp_path) == 1


# ---------------------------------------------------------------- Chrome

ENGLISH = {
    "extName": {"message": "Demo"},
    "greeting": {
        "message": "Hello, $NAME$!",
        "placeholders": {"name": {"content": "$1"}},
    },
}


def test_an_extension_whose_languages_follow_the_default(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    german = {
        "extName": {"message": "Demo"},
        "greeting": {
            "message": "Hallo, $name$!",
            "placeholders": {"NAME": {"content": "$1"}},
        },
    }
    files(
        tmp_path,
        {
            "extension/manifest.json": {"default_locale": "en"},
            "extension/_locales/en/messages.json": ENGLISH,
            "extension/_locales/de/messages.json": german,
        },
    )
    assert cli.main(["translations"], root=tmp_path) == 0
    assert "Each of the 2 catalog(s)" in capsys.readouterr().out


def test_what_a_language_of_an_extension_gets_wrong(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    english = {
        **ENGLISH,
        "empty": {"message": ""},
        "count": {"message": "$COUNT$ left", "placeholders": "none"},
    }
    german = {
        "stale": {"message": "Alt"},
        "greeting": {
            "message": "Hallo, $NAME$ und $OTHER$!",
            "placeholders": {"name": {"content": "$2"}, "other": "x"},
        },
        "extName": "Demo",
        "count": {"message": "Noch $COUNT$", "placeholders": {"count": {}}},
    }
    files(
        tmp_path,
        {
            "manifest.json": {"default_locale": "en"},
            "_locales/en/messages.json": english,
            "_locales/de/messages.json": german,
            "_locales/fr/messages.json": "{",
            "_locales/nl/messages.json": "[]",
        },
    )
    monkeypatch.setenv("GITHUB_ACTIONS", "true")

    assert cli.main(["translations"], root=tmp_path) == 1

    out = capsys.readouterr().out
    assert out.splitlines()[:9] == [
        "_locales/de/messages.json:2: has 1 message(s) that _locales/en/messages.json "
        "doesn't have, such as stale",
        "_locales/de/messages.json: lacks 1 of the messages of "
        "_locales/en/messages.json, such as empty: write them in its language",
        "_locales/de/messages.json:5: shows the placeholders NAME, OTHER in "
        "greeting, but _locales/en/messages.json NAME: each stands for a value, so "
        "keep those of the source",
        '_locales/de/messages.json:5: defines $NAME$ of greeting as "$2", but '
        '_locales/en/messages.json as "$1": it would show another value',
        "_locales/de/messages.json:14: has no words for extName",
        "_locales/en/messages.json:13: has no words for empty",
        "_locales/en/messages.json:16: shows $COUNT$ in count, which its "
        "placeholders don't define",
        "_locales/fr/messages.json: is no JSON: Expecting property name enclosed in "
        "double quotes: line 1 column 2 (char 1)",
        "_locales/nl/messages.json: holds no object of messages",
    ]
    # In the CI, also as annotations at their lines.
    assert (
        "::error file=_locales/de/messages.json,line=5,title=Translations::defines "
        "$NAME$ of greeting" in out
    )
    assert "::error file=_locales/de/messages.json,title=Translations::lacks" in out
    assert "translations --fix brings the order" in out
    assert "which only a person can write" in out


def test_translations_fix_orders_the_messages_of_a_language(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    german = {
        "greeting": {
            "message": "Hallo, $NAME$!",
            "placeholders": {"name": {"content": "$1"}},
        },
        "extName": {"message": "Demo"},
    }
    files(
        tmp_path,
        {
            "extension/manifest.json": {"default_locale": "en"},
            "extension/_locales/en/messages.json": ENGLISH,
            "extension/_locales/de/messages.json": german,
        },
    )
    assert cli.main(["translations"], root=tmp_path) == 1
    out = capsys.readouterr().out
    assert out.startswith(
        "extension/_locales/de/messages.json: has its messages in another order "
        "than extension/_locales/en/messages.json\n"
    )
    # Only what --fix fixes: no person needed.
    assert "only a person" not in out

    assert cli.main(["translations", "--fix"], root=tmp_path) == 0

    fixed = tmp_path / "extension/_locales/de/messages.json"
    assert list(json.loads(fixed.read_text(encoding="utf-8"))) == list(ENGLISH)


def test_a_default_locale_that_an_extension_lacks(tmp_path: Path) -> None:
    files(
        tmp_path,
        {
            "extension/manifest.json": {"default_locale": "fr"},
            "extension/_locales/en/messages.json": ENGLISH,
            "other/manifest.json": {"default_locale": "en"},
        },
    )
    assert messages(check(tmp_path).findings) == [
        "extension/manifest.json: names the default_locale fr, which _locales/ lacks"
    ]
    files(tmp_path, {"extension/_locales/fr/messages.json": "{"})
    assert messages(check(tmp_path).findings) == [
        "extension/_locales/fr/messages.json: is no JSON: Expecting property name "
        "enclosed in double quotes: line 1 column 2 (char 1)"
    ]
    files(tmp_path, {"extension/_locales/fr/messages.json": "[]"})
    assert messages(check(tmp_path).findings) == [
        "extension/_locales/fr/messages.json: holds no object of messages"
    ]
