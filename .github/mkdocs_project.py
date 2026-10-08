"""The hooks of the blueprint's own website.

They come beside the hooks that every website shares, in .github/mkdocs_blueprint.py;
mkdocs.yml names both files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def on_files(files: Any, config: Any) -> Any:
    """Show the pictures of the READMEs on the website too.

    The guide includes README.md, which names a picture from the root of the
    repository, such as docs/images/dashboard.png, so that GitHub shows it. Every
    file of docs/ that is no page gets that name as well, for the same file on the
    website, and a missing picture still fails the build.
    """
    docs = Path(config.docs_dir)
    for file in list(files):
        if file.src_dir and Path(file.src_dir) == docs and file.is_media_file():
            alias = type(file)(
                f"{docs.name}/{file.src_uri}",
                str(docs.parent),
                config.site_dir,
                file.use_directory_urls,
                dest_uri=file.dest_uri,
            )
            # The i18n plugin sets the place of every file itself, so the second name
            # takes the place of the file rather than working it out.
            alias.abs_dest_path = file.abs_dest_path
            files.append(alias)
    return files


# The i18n plugin makes the files of every language anew in its on_files, which runs
# last (-100); this one runs after it, or the second names would be lost.
on_files.mkdocs_priority = -110  # type: ignore[attr-defined]
