"""The screens of the recording of copier copy, which decide whether its GIF and its
video change.

VHS records the terminal in real time, so each run of copier-copy.tape catches the
typing and the output of Copier at other moments: another number of frames, and with
them other colors of the GIF, whose palette and lossy compression depend on every
frame. Its pixels then differ in every frame, although it shows the same screens, and
`blueprint.py screenshots keep` can't keep it. The tape also takes a picture of each
screen on which it waits, before each key, as VHS draws it the same way whenever the
terminal shows the same: those pictures say what the recording shows.

scripts/docs-pictures.sh runs it in the image of .github/docs-pictures/Dockerfile,
after gifsicle made the GIF smaller, in the folder of the new pictures:

    python3 recording.py keep copier-copy.gif copier-copy.mp4 FOLDER SCREEN...

keep writes the fingerprint of the screens, the sha256 of the pictures in their order,
into a comment of the GIF. When the GIF in FOLDER, the committed one, carries the same
fingerprint, it copies that GIF and its video from FOLDER over the new ones, which then
change no file: only a change of a screen renews the recording.
https://github.com/Dennis-Otto/repo-blueprint
"""

from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

# How the comment of the GIF starts, which holds the fingerprint.
MARK = "The screens of the recording: "
HEADERS = (b"GIF87a", b"GIF89a")
# The blocks of a GIF after its header: an extension, the picture of a frame, the end.
EXTENSION, IMAGE, TRAILER = 0x21, 0x2C, 0x3B
COMMENT, APPLICATION = 0xFE, 0xFF
# The most bytes of a sub-block of a GIF.
LONGEST = 255


def fingerprint(screens: list[bytes]) -> str:
    """The text of the comment for the pictures of the screens, in their order: their
    number and the sha256 of their sha256s."""
    if not screens:
        raise ValueError("The recording took no picture of a screen.")
    digest = hashlib.sha256()
    for screen in screens:
        digest.update(hashlib.sha256(screen).digest())
    return f"{MARK}{len(screens)}, sha256 {digest.hexdigest()}"


def blocks_start(data: bytes) -> int:
    """Where the blocks of a GIF begin: after its header, its logical screen and its
    global color table, when it has one."""
    if data[:6] not in HEADERS or len(data) < 13:
        raise ValueError("The file is no GIF.")
    packed = data[10]
    table = 3 << ((packed & 0x07) + 1) if packed & 0x80 else 0
    return 13 + table


def sub_blocks_end(data: bytes, at: int) -> int:
    """Where the sub-blocks that begin at at end, after the empty one."""
    while True:
        if at >= len(data):
            raise ValueError("The GIF ends within a block.")
        length = data[at]
        at += 1 + length
        if length == 0:
            return at


def leading_extensions(data: bytes) -> list[tuple[int, int, int]]:
    """The extensions before the first frame of a GIF, as their label, where each
    starts and where it ends."""
    found = []
    at = blocks_start(data)
    while at < len(data) and data[at] == EXTENSION:
        if at + 1 >= len(data):
            raise ValueError("The GIF ends within a block.")
        end = sub_blocks_end(data, at + 2)
        found.append((data[at + 1], at, end))
        at = end
    if at >= len(data) or data[at] not in (IMAGE, TRAILER):
        raise ValueError("The GIF has a block that is no extension and no frame.")
    return found


def text_of(data: bytes, start: int, end: int) -> str:
    """The text of the comment extension of data from start to end."""
    at, parts = start + 2, []
    while at < end - 1:
        length = data[at]
        parts.append(data[at + 1 : at + 1 + length])
        at += 1 + length
    return b"".join(parts).decode("utf-8", "replace")


def mark_of(data: bytes) -> str | None:
    """The fingerprint that a GIF carries in a comment before its first frame, or
    None."""
    for label, start, end in leading_extensions(data):
        if label == COMMENT:
            text = text_of(data, start, end)
            if text.startswith(MARK):
                return text
    return None


def marked(data: bytes, mark: str) -> bytes:
    """The GIF with mark as its comment, in place of a fingerprint that it carried; a
    comment needs the version 89a of GIF. The comment follows the application
    extensions at the start, such as NETSCAPE2.0 that makes the GIF loop, which some
    viewers look for right after the global color table."""
    start = blocks_start(data)
    kept = bytearray(data[:start])
    kept[:6] = HEADERS[1]
    text = mark.encode()
    comment = bytearray((EXTENSION, COMMENT))
    for at in range(0, len(text), LONGEST):
        part = text[at : at + LONGEST]
        comment += bytes((len(part),)) + part
    comment += b"\x00"
    placed = False
    at = start
    for label, begin, end in leading_extensions(data):
        if not placed and label != APPLICATION:
            kept += comment
            placed = True
        if label != COMMENT or not text_of(data, begin, end).startswith(MARK):
            kept += data[begin:end]
        at = end
    if not placed:
        kept += comment
    return bytes(kept + data[at:])


def keep(gif: Path, video: Path, folder: Path, screens: list[Path]) -> bool:
    """Marks the new GIF with the fingerprint of the screens and, when the GIF of the
    same name in folder carries the same, puts that GIF and its video in place of the
    new ones. Whether it kept them."""
    mark = fingerprint([screen.read_bytes() for screen in screens])
    gif.write_bytes(marked(gif.read_bytes(), mark))
    old_gif, old_video = folder / gif.name, folder / video.name
    if not (old_gif.is_file() and old_video.is_file()):
        return False
    if mark_of(old_gif.read_bytes()) != mark:
        return False
    shutil.copyfile(old_gif, gif)
    shutil.copyfile(old_video, video)
    return True


def main(arguments: list[str]) -> None:
    if len(arguments) < 5 or arguments[0] != "keep":
        raise SystemExit(__doc__)
    gif, video, folder = (Path(argument) for argument in arguments[1:4])
    try:
        kept = keep(gif, video, folder, [Path(screen) for screen in arguments[4:]])
    except (OSError, ValueError) as error:
        raise SystemExit(f"recording.py: {error}") from None
    if kept:
        print(
            f"{gif.name} shows the same screens as before: it and {video.name} "
            "stay as they are.",
            file=sys.stderr,
        )
    else:
        print(
            f"{gif.name} shows other screens: it and {video.name} are new.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main(sys.argv[1:])
