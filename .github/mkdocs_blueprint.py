"""The hooks of the documentation website, which the blueprint keeps current.

.github/mkdocs-blueprint.yml names this file under hooks. A project with hooks of
its own lists this file there too, since its list replaces that of the blueprint.
https://github.com/Dennis-Otto/repo-blueprint
"""

from __future__ import annotations

import gzip
import html
import json
import logging
import posixpath
import re
import shutil
import struct
import sys
import time
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import urljoin

log = logging.getLogger("mkdocs.hooks.blueprint")

# The plugins of Material that download from other servers while the website is
# built: privacy the fonts and scripts that the pages use, social the fonts of the
# preview cards.
DOWNLOADING = ("material/privacy", "material/social")
# How often a download is tried before the plugin gets its error.
ATTEMPTS = 3
# The <picture> of a diagram, as scripts/diagrams.sh --extract writes it, with the
# paragraph that Markdown puts around it.
DIAGRAM = re.compile(
    r"(?P<paragraph><p>\s*)?<picture>(?:(?!</picture>).)*?<img\b[^>]*?\bsrc=\"(?:[^\"]*/)?"
    r"images/diagrams/(?P<name>[\w.-]+?)\.svg\".*?</picture>(?(paragraph)\s*</p>)",
    re.S,
)
# The stylesheet and the script of every website: the path where the website serves
# each, and the file beside this one that holds it.
ASSETS = {
    "assets/stylesheets/blueprint.css": "mkdocs-blueprint.css",
    "assets/javascripts/blueprint.js": "mkdocs-blueprint.js",
}
STYLESHEET, SCRIPT = ASSETS
# The Mermaid that draws the diagrams of the website. Material asks unpkg.com for the
# newest release of a major version, which the privacy plugin downloads in every
# build, so that two builds of the same commit could draw the diagrams differently.
# The website loads this release instead, which Renovate keeps current within the
# major version that Material loads.
MERMAID = "https://unpkg.com/mermaid@11.17.2/dist/mermaid.min.js"
FLOATING = re.compile(
    r"https://unpkg\.com/mermaid@(?P<major>\d+)/dist/mermaid\.min\.js"
)
# The script of Material, which loads Mermaid.
BUNDLE = re.compile(r"assets/javascripts/bundle\.\w+\.min\.js")
# The tags of HTML that the hook reads; a value in quotes may hold a >.
TAG = r"(?:[^>\"']|\"[^\"]*\"|'[^']*')*"
IMAGE = re.compile(rf"<img\b{TAG}>", re.I)
SOURCE = re.compile(rf"<source\b{TAG}>", re.I)
PICTURE = re.compile(
    rf"<picture\b{TAG}>(?P<inside>(?:(?!</picture>).)*?)</picture>", re.S | re.I
)
ATTRIBUTE = re.compile(
    r"(?P<name>[^\s=/>\"']+)"
    r"(?:\s*=\s*(?:\"(?P<double>[^\"]*)\"|'(?P<single>[^']*)'|(?P<bare>[^\s>\"']+)))?"
)
# The endings of the address of a picture that Material shows in one scheme alone.
SCHEMES = ("#only-light", "#only-dark")
# The pictures beside a video, NAME.webp or NAME.png, that show until it plays.
POSTERS = (".webp", ".png")
# The live diagrams, whose sources the search leaves out: a search for "token" would
# show "flowchart LR admin([..." as its text.
MERMAID_BLOCK = re.compile(r'<pre class="mermaid"(?=>)')
# The badges of a README, such as those of shields.io, of a workflow or of the
# Scorecard: the website shows none. The privacy plugin would download each once,
# as the build sees it, so the website would show a status that is long gone. A
# button whose address names badges, such as those of My Home Assistant at
# .../badges/hacs_repository.svg, shows no status and stays.
BADGE = re.compile(
    r"https?://(?:img\.shields\.io/|api\.reuse\.software/badge/"
    r"|[^\s\"'<>]*/badge(?:\.svg)?(?=$|[?#]))",
    re.I,
)
LINKED_IMAGE = re.compile(rf"<a\b{TAG}>\s*(?P<image><img\b{TAG}>)\s*</a>", re.I)
EMPTY = re.compile(r"<p>\s*</p>\n?")
# The first paragraph of a page, from which a page without a description in its
# front matter takes the description that search engines and preview cards show, of
# DESCRIPTION characters at most. A paragraph of links alone, such as the line that
# leads to the version in another language, describes nothing.
LINK = re.compile(r"<a\b[^>]*>.*?</a>", re.S)
PARAGRAPH = re.compile(r"<p>(?P<inside>(?:(?!</p>).)*?)</p>", re.S)
DESCRIPTION = 160

# The pages that a website in several languages, and any other, keeps out of the
# search and out of search engines: the template of a decision record, which is
# there to be copied, and a page with robots: noindex in its front matter. A page
# that a further language shows in the default one, untranslated, is the same page
# as that one, which search engines list and the search finds instead.
TEMPLATES = ("decisions/0000-template.md",)
NOINDEX = '<meta name="robots" content="noindex, follow">'
# The links in the head of a page, such as those to its versions in other languages.
HEAD_LINK = re.compile(rf"<link\b{TAG}>", re.I)
# The names of the switch between light and dark in a further language, for those
# of the palette of .github/mkdocs-blueprint.yml.
TOGGLES = {
    "de": {
        "Switch to light mode": "Zum hellen Farbschema wechseln",
        "Switch to dark mode": "Zum dunklen Farbschema wechseln",
        "Switch to the scheme of the system": "Zum Farbschema des Systems wechseln",
    },
}
ENGLISH = {
    name: english for names in TOGGLES.values() for english, name in names.items()
}
# The search index of every language, which the search plugin writes, and beside it
# that of each language, which the hooks write: search/search_index.de.json.
SEARCH_INDEX = "search/search_index.json"
# The script that gives the search of a page the index of its language. Material
# asks for every, search/search_index.json from the folder of the website, before
# the scripts of the website run; the script in the head of the page asks for own,
# the index of the page's language, in its place, and leaves every other request as
# it is.
SEARCH_SCRIPT = (
    "<script>(function(){{"
    "var a=new URL({every},location.href).href,b=new URL({own},location.href).href,"
    "o=XMLHttpRequest.prototype.open;"
    "XMLHttpRequest.prototype.open=function(m,u){{var r=[].slice.call(arguments);"
    "if(new URL(String(u),location.href).href===a)r[1]=b;return o.apply(this,r)}}"
    "}})()</script>"
)
# What the scripts of Material hold while they ask for the index in the way that
# SEARCH_SCRIPT redirects.
SEARCH_REQUEST = ("XMLHttpRequest", "search_index.json")
# The sitemap that the website hands to search engines, with an entry for each page.
SITEMAP_ENTRY = re.compile(r"\s*<url>\s*<loc>(?P<loc>[^<]*)</loc>.*?</url>", re.S)
SITEMAP_LINK = re.compile(r'\s*<xhtml:link\b[^>]*?\bhref="(?P<href>[^"]*)"[^>]*/>')
# A line of a page that includes a file of the repository, --8<-- "README.md", or a
# part of one, "README.md:loop"; a line --8<-- alone starts and ends a block with
# one file on each line.
SNIPPET = re.compile(
    r"[ \t]*-+8<-+[ \t]*(?:(?P<quote>[\"'])(?P<name>.+?)(?P=quote))?[ \t]*"
)


class Retrying:
    """The requests of a plugin, whose get tries a download again, after a second
    and then two, when the network or the server fails."""

    def __init__(self, requests: Any) -> None:
        self.requests = requests

    def __getattr__(self, name: str) -> Any:
        return getattr(self.requests, name)

    def get(self, url: str, **kwargs: Any) -> Any:
        transient = (self.requests.ConnectionError, self.requests.Timeout)
        for attempt in range(1, ATTEMPTS):
            try:
                response = self.requests.get(url, **kwargs)
            except transient:
                pass
            else:
                if response.status_code < 500:
                    return response
            time.sleep(attempt)
        return self.requests.get(url, **kwargs)


def on_config(config: Any) -> None:
    """Let the plugins of Material try a download again before they give up, and
    give every page the stylesheet and the script of the blueprint.

    The plugins try every file once: the privacy plugin warns when a font of Google
    Fonts doesn't come within 5 seconds, which fails a strict build, and the social
    plugin fails on any error of the network. The stylesheet and the script come
    before those of the project, whose extra_css replaces the list of the blueprint
    and whose rules win over them.
    """
    for name in DOWNLOADING:
        plugin = config.plugins.get(name)
        if plugin is None:
            continue
        module: Any = sys.modules[type(plugin).__module__]
        if not isinstance(module.requests, Retrying):
            module.requests = Retrying(module.requests)
    for path, listed in (
        (STYLESHEET, config.extra_css),
        (SCRIPT, config.extra_javascript),
    ):
        if path not in map(str, listed):
            listed.insert(0, path)
    found = languages(config)
    if found is not None:
        name_the_toggles(config.theme, found.current)


class Languages(NamedTuple):
    """The languages of a website in several: the default one, the further ones that
    the i18n plugin builds, and the one that it builds now."""

    default: str
    further: tuple[str, ...]
    current: str

    def of(self, location: str) -> str:
        """The language of a page by its path on the website: a further one for
        de/guide.html, and for ha-autodarts/de/games.html, a page of a project
        website that the website of its owner adds to its search; the default one
        for every other page."""
        parts = location.split("/")
        if parts[0] in self.further:
            return parts[0]
        if len(parts) > 2 and parts[1] in self.further:
            return parts[1]
        return self.default

    def versions(self, location: str, language: str) -> tuple[str, ...]:
        """The paths where the version in language of the page of the default
        language at location would be: de/guide.html for guide.html, and also
        ha-autodarts/de/games.html for ha-autodarts/games.html."""
        head, slash, rest = location.partition("/")
        nested = (f"{head}/{language}/{rest}",) if slash else ()
        return (f"{language}/{location}", *nested)


def languages(config: Any) -> Languages | None:
    """The languages of the website, or None for a website in one language."""
    plugin = config.plugins.get("i18n")
    if plugin is None:
        return None
    default = ""
    further = []
    for language in plugin.config.languages:
        if language.default:
            default = language.locale
        elif language.build:
            further.append(language.locale)
    if not further:
        return None
    return Languages(default, tuple(further), plugin.current_language or default)


def name_the_toggles(theme: Any, language: str) -> None:
    """Name the switch between light and dark in the language of the build.

    The palette of .github/mkdocs-blueprint.yml names it in English, which the
    German pages showed as well. The i18n plugin sets the palette of a language
    from its theme in mkdocs.yml afterwards, so a name there wins over these.
    """
    palette = theme.get("palette")
    for option in palette if isinstance(palette, list) else []:
        toggle = option.get("toggle") or {}
        if "name" in toggle:
            english = ENGLISH.get(toggle["name"], toggle["name"])
            toggle["name"] = TOGGLES.get(language, {}).get(english, english)


def on_files(files: Any, config: Any) -> Any:
    """Serve the stylesheet and the script of the blueprint, and pin Mermaid.

    Both are files beside this one, which the i18n plugin leaves in place as files
    of the theme. The script of Material that loads Mermaid comes from a copy in
    .cache/ that names the release of MERMAID: the privacy plugin, which runs after
    this hook, downloads that one for the website.
    """
    here = Path(__file__).resolve().parent
    kind = type(next(iter(files)))
    for file in files:
        if BUNDLE.fullmatch(file.src_uri) and file.abs_src_path:
            pin(file, Path(config.docs_dir).parent / ".cache/plugin/blueprint")
    for destination, name in ASSETS.items():
        files.append(
            kind(
                name,
                str(here),
                config.site_dir,
                config.use_directory_urls,
                dest_uri=destination,
            )
        )
    return files


def pin(file: Any, cache: Path) -> None:
    """Point the script of Material at a copy of it that loads MERMAID.

    A Material that loads another major version of Mermaid, or no longer from
    unpkg.com, warns, which fails a strict build, so that MERMAID follows it.
    """
    script = Path(file.abs_src_path).read_text(encoding="utf-8")
    found = FLOATING.search(script)
    if found is None:
        log.warning(
            "Material no longer loads Mermaid from unpkg.com, so the website can't "
            "pin it: change MERMAID in .github/mkdocs_blueprint.py to follow it."
        )
        return
    major = MERMAID.split("@")[1].split(".")[0]
    if found["major"] != major:
        log.warning(
            f"Material loads Mermaid {found['major']}, and the website pins {MERMAID}: "
            f"change MERMAID in .github/mkdocs_blueprint.py to a release of Mermaid "
            f"{found['major']}."
        )
        return
    copy = cache / file.src_uri
    copy.parent.mkdir(parents=True, exist_ok=True)
    copy.write_text(FLOATING.sub(MERMAID, script), encoding="utf-8", newline="")
    file.abs_src_path = str(copy)


class Built:
    """What the builds of every language found, for the steps after the last one:
    the paths of the pages that a further language shows untranslated, such as
    de/roadmap.html, and the addresses of the pages that no search engine lists.

    The i18n plugin builds every further language within the build of the default
    one, and MkDocs loads the hooks anew for each build of mkdocs serve.
    """

    def __init__(self) -> None:
        self.untranslated: set[str] = set()
        self.unlisted: set[str] = set()


BUILT = Built()


def untranslated(page: Any, config: Any) -> bool:
    """Whether a further language shows this page in the default one: the i18n
    plugin builds it from the file of the default language."""
    found = languages(config)
    if found is None:
        return False
    return bool(getattr(page.file, "locale", found.current) != found.current)


def unlisted(page: Any, config: Any) -> bool:
    """Whether the search and search engines leave the page out: the template of a
    decision record, a page with robots: noindex in its front matter, and a page
    that a further language shows untranslated."""
    robots = str(page.meta.get("robots", "")).lower()
    return (
        page.file.src_uri in TEMPLATES
        or "noindex" in robots
        or untranslated(page, config)
    )


def on_page_markdown(markdown: str, page: Any, config: Any, files: Any) -> str:
    """Leave the pages that nobody looks for out of the search, and date a page by
    the newest of its files.

    It runs after the plugin git-revision-date-localized, which dates the page by
    its own file, and before the search plugin, which reads the front matter.
    """
    if unlisted(page, config):
        page.meta["search"] = {**(page.meta.get("search") or {}), "exclude": True}
        BUILT.unlisted.add(page.canonical_url)
        if untranslated(page, config):
            BUILT.untranslated.add(page.url)
    if config.plugins.get("material/social") and page.file.dest_uri in homes(config):
        # The preview card of a home page took its title from the menu: Home. The
        # social plugin draws it after this hook.
        social = page.meta.setdefault("social", {})
        social.setdefault("cards_layout_options", {}).setdefault(
            "title", config.site_name
        )
    redate(markdown, page, config)
    # The sitemap tells search engines when a page changed last; MkDocs gives it the
    # date of the build.
    changed = page.meta.get("git_revision_date_localized_raw_iso_date")
    if changed:
        page.update_date = changed
    return markdown


# After the plugin git-revision-date-localized.
on_page_markdown.mkdocs_priority = -10  # type: ignore[attr-defined]


def redate(markdown: str, page: Any, config: Any) -> None:
    """Date a page that includes files of the repository by the newest of them, and
    an untranslated page in the language of its menu.

    The guide includes README.md, and the changelog CHANGELOG.md, with a line
    --8<--, so their own files hardly ever change, and the plugin dated them by
    those: the changelog showed the date of its first release. The plugin writes
    the date in the language of the file, which for an untranslated page is not
    that of the words around it, such as "Letzte Aktualisierung".
    """
    plugin = config.plugins.get("git-revision-date-localized")
    if plugin is None or "git_revision_date_localized" not in page.meta:
        return
    root = Path(config.config_file_path).parent
    bases = config.mdx_configs.get("pymdownx.snippets", {}).get("base_path", ".")
    paths = included(
        markdown,
        [root / base for base in ([bases] if isinstance(bases, str) else bases)],
    )
    found = languages(config)
    copy = untranslated(page, config)
    if not paths and not copy:
        return
    newest = max(
        (
            plugin.util.get_git_commit_timestamp(path=str(path), is_first_commit=False)
            for path in [Path(page.file.abs_src_path), *paths]
        ),
        key=lambda commit: commit[1],
    )
    locale = found.current if found and copy else plugin._get_locale(page)
    plugin._render_date(markdown, page, locale, "git_revision_date_localized", *newest)


def included(
    markdown: str, bases: list[Path], seen: set[Path] | None = None
) -> list[Path]:
    """The files that the lines --8<-- of markdown include, and those that they
    include in turn, each found in the first folder of bases that has it, as the
    extension pymdownx.snippets finds them. A part of a file, README.md:loop, is
    that file; an address or a file that is missing is none."""
    seen = set() if seen is None else seen
    names = []
    block = False
    for line in markdown.splitlines():
        match = SNIPPET.fullmatch(line)
        if match and match["name"]:
            names.append(match["name"])
        elif match:
            block = not block
        elif block and line.strip() and not line.lstrip().startswith(";"):
            names.append(line.strip())
    found = []
    for name in names:
        candidates = (base / name.split(":")[0] for base in bases)
        path = next((path for path in candidates if path.is_file()), None)
        if path is not None and path not in seen:
            seen.add(path)
            found.append(path)
            found += included(path.read_text(encoding="utf-8"), bases, seen)
    return found


def on_page_content(html_text: str, page: Any, config: Any, files: Any) -> str:
    """Fit a page to the website: diagrams drawn live, which the search leaves out,
    pictures that follow the scheme the reader picks, videos in place of GIFs,
    pictures that load as the reader comes to them, no badges, a description of its
    own, and the language of an untranslated page.

    It runs before the plugin glightbox, which then wraps each picture that is left
    in a link that opens it enlarged, among the pictures of the reader's scheme.
    """
    docs = Path(config.docs_dir)
    where = Where(
        posixpath.dirname(page.file.dest_uri),
        posixpath.dirname(page.file.src_uri),
        docs.name,
        {file.dest_uri: file for file in files},
    )
    html_text = live_diagrams(html_text, docs / "diagrams")
    html_text = MERMAID_BLOCK.sub(r"\g<0> data-search-exclude", html_text)
    html_text = without_badges(html_text)
    html_text = PICTURE.sub(lambda m: themed(m, where), html_text)
    html_text = IMAGE.sub(lambda m: video(m[0], where), html_text)
    html_text = lazy(html_text, where)
    describe(page, html_text, config)
    found = languages(config)
    if found is not None and untranslated(page, config):
        # The text is in the default language, the menu and the header in that of
        # the page; a screen reader reads each in its own (WCAG 3.1.2).
        html_text = f'<div lang="{found.default}">\n{html_text}\n</div>'
    return html_text


# Before the plugin glightbox.
on_page_content.mkdocs_priority = 10  # type: ignore[attr-defined]


def live_diagrams(html_text: str, sources: Path) -> str:
    """Draw each diagram live from its source, in place of its pictures.

    The Markdown shows a diagram as the pictures that scripts/diagrams.sh draws from
    docs/diagrams/NAME.mmd, which every renderer shows. The website draws the source
    with Mermaid instead, as a block of Material: in the colors of the theme that the
    reader switches to, sharp at every size and with text to search and select. A
    picture without its source stays as it is.
    """

    def live(match: re.Match[str]) -> str:
        source = sources / f"{match['name'].removesuffix('.dark')}.mmd"
        if not source.is_file():
            return match[0]
        text = html.escape(source.read_text(encoding="utf-8"), quote=False)
        return f'<pre class="mermaid"><code>{text}</code></pre>'

    return DIAGRAM.sub(live, html_text)


def attributes(tag: str) -> dict[str, str | None]:
    """The attributes of a tag of HTML by their names, each with its value as the
    tag has it; None for one without a value, such as controls."""
    inside = re.sub(r"^<[\w-]+|/?>$", "", tag)
    found: dict[str, str | None] = {}
    for match in ATTRIBUTE.finditer(inside):
        values = (match["double"], match["single"], match["bare"])
        found[match["name"].lower()] = next((v for v in values if v is not None), None)
    return found


def element(name: str, attrs: dict[str, str | None]) -> str:
    """The opening tag of an element of HTML with these attributes."""
    parts = [name]
    for key, value in attrs.items():
        parts.append(
            key if value is None else f'{key}="{value.replace(chr(34), "&quot;")}"'
        )
    return f"<{' '.join(parts)}>"


def local(src: str, folder: str, found: dict[str, Any]) -> str | None:
    """The path on the website of the file that src names from a page in folder,
    when the website has that file."""
    path = src.split("#")[0].split("?")[0]
    if not path or re.match(r"[a-z][a-z0-9+.-]*:|/", path, re.I):
        return None
    target = posixpath.normpath(posixpath.join(folder, path))
    return target if target in found else None


def relative(target: str, folder: str) -> str:
    """The address of a file of the website from a page in folder."""
    return posixpath.relpath(target, folder or ".")


class Where(NamedTuple):
    """Where a page is: its folder on the website and that of its source, the name
    of the folder of the sources, and the files of the website by their paths."""

    folder: str
    source: str
    docs: str
    found: dict[str, Any]

    def find(self, src: str) -> str | None:
        """The path on the website of the file that src names, when the website has
        that file.

        MkDocs leads the path of a picture of Markdown from the page on the website,
        but leaves that of HTML as the source names it: from the folder of its
        source, which for guide.de.md in de/ is not the folder of the page, or from
        the root of the repository, as a README names docs/images/NAME.png.
        """
        for folder in (self.folder, self.source):
            target = local(src, folder, self.found)
            if target is not None:
                return target
        if src.startswith(f"{self.docs}/"):
            return local(src.removeprefix(f"{self.docs}/"), "", self.found)
        return None

    def address(self, src: str) -> str:
        """src as the page on the website reaches its file, with its ending such as
        #only-dark; src as it is when the website lacks that file."""
        target = self.find(src)
        if target is None or local(src, self.folder, self.found) is not None:
            return src
        ending = re.search(r"[?#].*", src)
        return relative(target, self.folder) + (ending[0] if ending else "")


def themed(match: re.Match[str], where: Where) -> str:
    """Show a <picture> with a picture for each scheme as two pictures.

    GitHub picks the picture of <source media="(prefers-color-scheme: dark)"> by the
    scheme of the reader's system, but the reader of the website can switch it, which
    a <picture> doesn't follow. The website shows each picture with #only-light or
    #only-dark, which Material shows in that scheme alone, and the other one never
    loads. A path from the source of the page, or from the root of the repository
    as a README names docs/images/NAME.png, leads to the same picture on the
    website. Any other <picture> stays as it is.
    """
    image = IMAGE.search(match["inside"])
    if image is None:
        return match[0]
    attrs = attributes(image[0])
    chosen = {"light": attrs.get("src"), "dark": None}
    for source in SOURCE.finditer(match["inside"]):
        source_attrs = attributes(source[0])
        media = re.sub(r"\s+", "", source_attrs.get("media") or "")
        named = re.fullmatch(r"\(prefers-color-scheme:(light|dark)\)", media)
        srcset = (source_attrs.get("srcset") or "").split(",")[0].split()
        if named and srcset:
            chosen[named[1]] = srcset[0]
    if not chosen["light"] or not chosen["dark"]:
        return match[0]
    pictures = []
    for scheme, ending in zip(("light", "dark"), SCHEMES, strict=True):
        src = where.address(str(chosen[scheme]).split("#")[0])
        pictures.append(element("img", {**attrs, "src": src.split("#")[0] + ending}))
    return "".join(pictures)


def size(path: str) -> tuple[int, int] | None:
    """The width and the height of a PNG, a GIF or a WebP, from its first bytes."""
    with open(path, "rb") as file:
        head = file.read(30)
    if head.startswith(b"\x89PNG\r\n\x1a\n") and head[12:16] == b"IHDR":
        width, height = struct.unpack(">II", head[16:24])
        return width, height
    if head[:6] in (b"GIF87a", b"GIF89a"):
        width, height = struct.unpack("<HH", head[6:10])
        return width, height
    if head[:4] != b"RIFF" or head[8:12] != b"WEBP" or len(head) < 30:
        return None
    # The three kinds of WebP: lossy, lossless, and extended, such as an animation.
    chunk = head[12:16]
    if chunk == b"VP8 ":
        width, height = struct.unpack("<HH", head[26:30])
        return width & 0x3FFF, height & 0x3FFF
    if chunk == b"VP8L":
        bits = int.from_bytes(head[21:25], "little")
        return (bits & 0x3FFF) + 1, (bits >> 14 & 0x3FFF) + 1
    if chunk == b"VP8X":
        width = int.from_bytes(head[24:27], "little") + 1
        return width, int.from_bytes(head[27:30], "little") + 1
    return None


def video(tag: str, where: Where) -> str:
    """Show a GIF with a video beside it, NAME.mp4, as that video.

    GitHub shows the GIF, the website the video, which is a third of its size and
    loads only once the reader scrolls to it: the script of the blueprint plays it
    while it is in view, muted and in a loop as the GIF, and the reader can pause it.
    NAME.webp or NAME.png beside it shows until it plays, and the text of the GIF
    names it.
    """
    attrs = attributes(tag)
    target = where.find(attrs.get("src") or "")
    folder, found = where.folder, where.found
    if target is None or not target.lower().endswith(".gif"):
        return tag
    stem = target[: -len(".gif")]
    if f"{stem}.mp4" not in found:
        return tag
    shown: dict[str, str | None] = {
        "class": "blueprint-video",
        "src": relative(f"{stem}.mp4", folder),
    }
    poster = next((f"{stem}{end}" for end in POSTERS if f"{stem}{end}" in found), None)
    if poster is not None:
        shown["poster"] = relative(poster, folder)
    dimensions = size(found[target].abs_src_path)
    if dimensions is not None:
        shown["width"], shown["height"] = map(str, dimensions)
    for flag in ("controls", "muted", "loop", "playsinline"):
        shown[flag] = None
    shown["preload"] = "none"
    for name, shown_as in (("alt", "aria-label"), ("title", "title")):
        if attrs.get(name):
            shown[shown_as] = attrs[name]
    return f"{element('video', shown)}</video>"


def lazy(html_text: str, where: Where) -> str:
    """Load the pictures of a page as the reader comes to them.

    The first picture loads first, as the largest part of the page that a reader
    sees at once; every other one waits until it comes near the screen, and one for
    the other scheme never comes. A PNG or a GIF of the website gets its width and
    height, so that the page doesn't shift while it loads. A picture that says how
    it loads stays as it is.
    """
    first = True

    def load(match: re.Match[str]) -> str:
        nonlocal first
        attrs = attributes(match[0])
        was_first, first = first, False
        if "loading" in attrs:
            return match[0]
        src = attrs.get("src") or ""
        target = where.find(src)
        if target is not None:
            attrs["src"] = src = where.address(src)
        if target is not None and "width" not in attrs and "height" not in attrs:
            dimensions = size(where.found[target].abs_src_path)
            if dimensions is not None:
                attrs["width"], attrs["height"] = map(str, dimensions)
        if was_first and not src.endswith(SCHEMES):
            attrs["fetchpriority"] = "high"
        else:
            attrs["loading"] = "lazy"
            attrs["decoding"] = "async"
        return element("img", attrs)

    return IMAGE.sub(load, html_text)


def without_badges(html_text: str) -> str:
    """Take the badges of a README out of the page, with their links, and the
    paragraph that held nothing else.

    GitHub shows them as they are now; the website would show each as the build
    downloaded it, a release or a result of the checks that is long gone.
    """

    def badge(tag: str) -> bool:
        return bool(BADGE.match(attributes(tag).get("src") or ""))

    html_text = LINKED_IMAGE.sub(lambda m: "" if badge(m["image"]) else m[0], html_text)
    html_text = IMAGE.sub(lambda m: "" if badge(m[0]) else m[0], html_text)
    return EMPTY.sub("", html_text)


def describe(page: Any, html_text: str, config: Any) -> None:
    """Give a page the description that search engines and preview cards show: the
    start of its first paragraph, unless its front matter has one.

    Every page had the description of the website, so search engines saw the same
    text for each. The home page of each language keeps it.
    """
    if page.meta.get("description") or page.file.dest_uri in homes(config):
        return
    for paragraph in PARAGRAPH.finditer(html_text):
        # A paragraph of pictures or of links alone describes nothing.
        words = re.sub(r"<[^>]*>", "", LINK.sub("", paragraph["inside"]))
        if re.search(r"\w", words):
            text = " ".join(
                html.unescape(re.sub(r"<[^>]*>", "", paragraph["inside"])).split()
            )
            # MkDocs writes it into an attribute as it is.
            page.meta["description"] = shorten(text.replace('"', "'"), DESCRIPTION)
            return


def homes(config: Any) -> set[str]:
    """The home pages of the website, one of each language that is built."""
    found = languages(config)
    return {"index.html"} | ({f"{found.current}/index.html"} if found else set())


def shorten(text: str, limit: int) -> str:
    """text, or as many of its words as fit into limit characters with an ellipsis."""
    if len(text) <= limit:
        return text
    words = text[:limit].rsplit(" ", 1)[0].rstrip(",;:")
    return f"{words}…"


def on_post_page(output: str, page: Any, config: Any) -> str:
    """Give the head of a page what search engines and the search need to know of
    its language: the full addresses of its versions in other languages, a page
    that a further language shows untranslated as a copy of the page of the default
    language, which no search engine lists, and the search in its language.

    It runs after the hooks of a project, such as one that leads the home page to
    the root of the address, and after the privacy plugin.
    """
    found = languages(config)
    if found is not None:
        output = versions(output, page, config, found)
        if config.plugins.get("material/search"):
            output = search_in_language(output, page, found)
    if unlisted(page, config):
        output = output.replace("</head>", f"{NOINDEX}</head>", 1)
    return output


on_post_page.mkdocs_priority = -60  # type: ignore[attr-defined]


def versions(output: str, page: Any, config: Any, found: Languages) -> str:
    """Name the versions of a page in other languages with their full addresses,
    and the version of the default language once more for every other language.

    Search engines take only a full address, and x-default for the readers of a
    language that the website lacks. A version that only shows the page of the
    default language, untranslated, is no version of its own: a page with no other
    version names none, and an untranslated page names the page of the default
    language as its canonical address.
    """
    here = urljoin(config.site_url or "", page.url)
    alternates = getattr(page.file, "alternates", None) or {}
    translated = {
        language for language, file in alternates.items() if file.locale == language
    }
    named = {}
    for match in HEAD_LINK.finditer(output):
        attrs = attributes(match[0])
        language = attrs.get("hreflang")
        if attrs.get("rel") == "alternate" and language in translated:
            named[str(language)] = urljoin(here, attrs.get("href") or "")
    if found.default in named and len(named) > 1:
        named["x-default"] = named[found.default]
    else:
        named = {}
    tags = "".join(
        f'<link rel="alternate" href="{href}" hreflang="{language}">'
        for language, href in named.items()
    )
    default = alternates.get(found.default)
    canonical = None
    if default is not None and untranslated(page, config):
        canonical = urljoin(config.site_url or "", default.url)

    def replace(match: re.Match[str]) -> str:
        nonlocal tags
        attrs = attributes(match[0])
        if attrs.get("rel") == "alternate" and attrs.get("hreflang"):
            # The links of the languages, all in place of the first one.
            written, tags = tags, ""
            return written
        # A project may have named another page as canonical, such as the one that
        # replaced a page that moved; only the page itself becomes the original.
        if (
            attrs.get("rel") == "canonical"
            and canonical
            and urljoin(here, attrs.get("href") or "") == here
        ):
            return element("link", {**attrs, "href": canonical})
        return match[0]

    return HEAD_LINK.sub(replace, output)


def search_in_language(output: str, page: Any, found: Languages) -> str:
    """Let the search of a page find the pages of its language: the script of
    SEARCH_SCRIPT gives it the index of its language, which on_post_build writes.

    One index held every language: an English search found the German pages too,
    often first, and the German one the English pages that have a German version.
    """
    folder = posixpath.dirname(page.file.dest_uri)
    every = relative(SEARCH_INDEX, folder)
    own = relative(SEARCH_INDEX.replace(".json", f".{found.current}.json"), folder)
    script = SEARCH_SCRIPT.format(every=json.dumps(every), own=json.dumps(own))
    return output.replace("</head>", f"{script}</head>", 1)


def on_post_build(config: Any) -> None:
    """Write the search index of each language, keep the pages that no search engine
    lists out of the sitemap, and copy the sitemap of a website in several
    languages into every folder of pages.

    The language switch of Material asks for sitemap.xml in the folder of the page in
    each language: decisions/ and de/decisions/ on decisions/0006-beta-channel.html.
    The i18n plugin writes a single sitemap with every language at the root, so every
    other folder that holds a page gets a copy.
    """
    site = Path(config.site_dir)
    sitemap = site / "sitemap.xml"
    for path in (sitemap, site / "sitemap.xml.gz"):
        unlist(path, BUILT.unlisted)
    found = languages(config)
    if found is None:
        return
    index = site / SEARCH_INDEX
    if index.is_file():
        search_by_language(index, found, BUILT.untranslated)
        search_request(site / "assets/javascripts")
    if not sitemap.is_file():
        return
    for folder in {page.parent for page in site.rglob("*.html")} - {site}:
        shutil.copyfile(sitemap, folder / "sitemap.xml")


# After the i18n plugin, which writes the search index of every language with -100,
# and after the hooks of a project that add to it, such as -110.
on_post_build.mkdocs_priority = -120  # type: ignore[attr-defined]


def unlist(path: Path, addresses: set[str]) -> None:
    """Take the pages at addresses out of a sitemap, sitemap.xml or the packed
    sitemap.xml.gz, and the links to them out of its other pages."""
    if not path.is_file():
        return

    def keep(text: str) -> str:
        text = SITEMAP_ENTRY.sub(
            lambda m: "" if html.unescape(m["loc"]) in addresses else m[0], text
        )
        return SITEMAP_LINK.sub(
            lambda m: "" if html.unescape(m["href"]) in addresses else m[0], text
        )

    if path.suffix != ".gz":
        text = path.read_text(encoding="utf-8")
        path.write_text(keep(text), encoding="utf-8", newline="\n")
        return
    with gzip.GzipFile(path) as reader:
        text = reader.read().decode("utf-8")
        built = reader.mtime
    with gzip.GzipFile(path, "wb", mtime=built) as writer:
        writer.write(keep(text).encode("utf-8"))


def search_by_language(index: Path, found: Languages, copies: set[str]) -> None:
    """Write the search index of each language beside that of every language.

    The index of a language holds its pages, and in a further language the pages
    of the default one that have no version in it, at the path of copies where the
    website shows them in that language. A section whose page the index lacks gets
    one, with its title: the search showed it under the address .../undefined.
    """
    data = json.loads(index.read_text(encoding="utf-8"))
    docs = []
    pages = {doc["location"] for doc in data["docs"] if "#" not in doc["location"]}
    for doc in data["docs"]:
        page = doc["location"].partition("#")[0]
        if page not in pages:
            docs.append({"location": page, "title": doc["title"], "text": ""})
            pages.add(page)
        docs.append(doc)
    write_index(index, {**data, "docs": docs})
    for language in (found.default, *found.further):
        kept = []
        for doc in docs:
            location = doc["location"]
            page = location.partition("#")[0]
            spoken = found.of(page)
            if spoken == language:
                kept.append(doc)
            elif language != found.default and spoken == found.default:
                there = found.versions(page, language)
                if not pages.intersection(there):
                    shown = there[0] if there[0] in copies else page
                    kept.append({**doc, "location": shown + location[len(page) :]})
        name = SEARCH_INDEX.replace(".json", f".{language}.json")
        write_index(index.parent.parent / name, {**data, "docs": kept})


def search_request(scripts: Path) -> None:
    """Warn, which stops the strict build, when the scripts of Material in scripts
    ask for the search index in a way that SEARCH_SCRIPT doesn't redirect.

    The search of every page would find every language again, and nothing else
    would show it; the update of Material that changes it fails instead.
    """
    bundles = [path.read_text(encoding="utf-8") for path in scripts.glob("bundle.*.js")]
    if bundles and not any(
        all(part in bundle for part in SEARCH_REQUEST) for bundle in bundles
    ):
        log.warning(
            "Material no longer asks for %s with an XMLHttpRequest, so the search "
            "of every page would find every language: SEARCH_SCRIPT of "
            ".github/mkdocs_blueprint.py has to follow the way it asks now.",
            SEARCH_INDEX,
        )


def write_index(path: Path, data: dict[str, Any]) -> None:
    """Write a search index as the search plugin of Material writes it."""
    text = json.dumps(data, separators=(",", ":"))
    path.write_text(text, encoding="utf-8", newline="\n")


def on_post_template(output_content: str, template_name: str, config: Any) -> str:
    """Keep the 404 page of the default language at the root.

    The i18n plugin builds every further language into the same folder, and that
    build would write 404.html at the root again: in the further language, and with
    the language switch of the page that was built last. MkDocs writes no empty page.
    """
    plugin = config.plugins.get("i18n")
    further = plugin is not None and not plugin.is_default_language_build
    return "" if template_name == "404.html" and further else output_content
