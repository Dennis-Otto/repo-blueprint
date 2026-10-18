"""The hooks of the documentation website, which the blueprint keeps current.

.github/mkdocs-blueprint.yml names this file under hooks. A project with hooks of
its own lists this file there too, since its list replaces that of the blueprint.
https://github.com/Dennis-Otto/repo-blueprint
"""

from __future__ import annotations

import html
import logging
import posixpath
import re
import shutil
import struct
import sys
import time
from pathlib import Path
from typing import Any, NamedTuple

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


def on_page_content(html_text: str, page: Any, config: Any, files: Any) -> str:
    """Fit the pictures of a page to the website: diagrams drawn live, pictures that
    follow the scheme the reader picks, videos in place of GIFs, and pictures that
    load as the reader comes to them.

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
    html_text = PICTURE.sub(lambda m: themed(m, where), html_text)
    html_text = IMAGE.sub(lambda m: video(m[0], where), html_text)
    return lazy(html_text, where)


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


def on_post_build(config: Any) -> None:
    """Copy the sitemap of a website in several languages into every folder of pages.

    The language switch of Material asks for sitemap.xml in the folder of the page in
    each language: decisions/ and de/decisions/ on decisions/0006-beta-channel.html.
    The i18n plugin writes a single sitemap with every language at the root, so every
    other folder that holds a page gets a copy.
    """
    plugin = config.plugins.get("i18n")
    site = Path(config.site_dir)
    sitemap = site / "sitemap.xml"
    if plugin is None or not sitemap.is_file():
        return
    if not any(lang.build and not lang.default for lang in plugin.config.languages):
        return
    for folder in {page.parent for page in site.rglob("*.html")} - {site}:
        shutil.copyfile(sitemap, folder / "sitemap.xml")


def on_post_template(output_content: str, template_name: str, config: Any) -> str:
    """Keep the 404 page of the default language at the root.

    The i18n plugin builds every further language into the same folder, and that
    build would write 404.html at the root again: in the further language, and with
    the language switch of the page that was built last. MkDocs writes no empty page.
    """
    plugin = config.plugins.get("i18n")
    further = plugin is not None and not plugin.is_default_language_build
    return "" if template_name == "404.html" and further else output_content
