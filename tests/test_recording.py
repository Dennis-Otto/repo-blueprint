"""The screens of the recording of copier copy: .github/docs-pictures/recording.py,
which marks the GIF with the fingerprint of the pictures of its screens and keeps the
committed GIF and video while that fingerprint stays the same (#827)."""

from __future__ import annotations

import importlib.util
import io
import re
from pathlib import Path
from types import ModuleType

import pytest
from PIL import Image, ImageSequence

ROOT = Path(__file__).resolve().parents[1]
TAPE = ROOT / ".github/docs-pictures/copier-copy.tape"
SCRIPT = ROOT / "scripts/docs-pictures.sh"


@pytest.fixture
def recording() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "recording", ROOT / ".github/docs-pictures/recording.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def gif(*shades: int, loop: bool = True) -> bytes:
    """A GIF of a frame of each shade of gray, as Pillow writes it: with a global
    color table and, with loop, the extension NETSCAPE2.0 before the first frame."""
    frames = [Image.new("L", (4, 3), shade) for shade in shades]
    out = io.BytesIO()
    extra = {"loop": 0} if loop else {}
    frames[0].save(
        out, "GIF", save_all=True, append_images=frames[1:], duration=100, **extra
    )
    return out.getvalue()


def pixels(data: bytes) -> list[bytes]:
    with Image.open(io.BytesIO(data)) as image:
        return [
            frame.convert("RGBA").tobytes() for frame in ImageSequence.Iterator(image)
        ]


def comment_block(text: bytes) -> bytes:
    return b"\x21\xfe" + bytes((len(text),)) + text + b"\x00"


def test_the_fingerprint_names_the_screens_in_their_order(
    recording: ModuleType,
) -> None:
    first = recording.fingerprint([b"one", b"two"])

    assert first.startswith("The screens of the recording: 2, sha256 ")
    assert first == recording.fingerprint([b"one", b"two"])
    # Another order, another screen or one more screen is another recording.
    assert first != recording.fingerprint([b"two", b"one"])
    assert first != recording.fingerprint([b"one", b"three"])
    assert first != recording.fingerprint([b"one", b"two", b"two"])
    with pytest.raises(ValueError, match="no picture of a screen"):
        recording.fingerprint([])


def test_a_marked_gif_shows_the_same_frames_and_carries_its_fingerprint(
    recording: ModuleType,
) -> None:
    data = gif(0, 128, 255)
    mark = recording.fingerprint([b"screen"])

    marked = recording.marked(data, mark)

    assert recording.mark_of(data) is None
    assert recording.mark_of(marked) == mark
    assert pixels(marked) == pixels(data)
    with Image.open(io.BytesIO(marked)) as image:
        assert image.info["comment"] == mark.encode()
        assert image.info["loop"] == 0
    # The extension NETSCAPE2.0, which makes the GIF loop, stays right after the
    # global color table, and the comment follows it.
    start = recording.blocks_start(data)
    assert data[start : start + 3] == b"\x21\xff\x0b"
    assert marked[start : start + 19] == data[start : start + 19]
    assert marked[start + 19 : start + 21] == b"\x21\xfe"
    # A new mark takes the place of the old one, and marking twice changes nothing.
    other = recording.fingerprint([b"another screen"])
    again = recording.marked(marked, other)
    assert recording.mark_of(again) == other
    assert len(again) == len(marked)
    assert recording.marked(again, other) == again


def test_a_long_mark_fills_several_sub_blocks(recording: ModuleType) -> None:
    mark = recording.MARK + "x" * 600

    marked = recording.marked(gif(0, loop=False), mark)

    assert recording.mark_of(marked) == mark
    with Image.open(io.BytesIO(marked)) as image:
        assert image.info["comment"] == mark.encode()


def test_other_comments_stay_and_a_gif87a_becomes_a_gif89a(
    recording: ModuleType,
) -> None:
    # A GIF without a global color table, a comment of someone else and one frame.
    data = gif(0, loop=False)
    start = recording.blocks_start(data)
    plain = b"GIF87a" + data[6:start] + comment_block(b"made by hand") + data[start:]

    marked = recording.marked(plain, recording.fingerprint([b"screen"]))

    assert marked.startswith(b"GIF89a")
    assert comment_block(b"made by hand") in marked
    assert recording.mark_of(plain) is None
    assert pixels(marked) == pixels(data)
    bare = b"GIF89a" + bytes((1, 0, 1, 0, 0, 0, 0)) + b"\x3b"
    assert recording.blocks_start(bare) == 13
    assert recording.mark_of(recording.marked(bare, "The screens of the recording: 1"))


@pytest.mark.parametrize(
    ("data", "said"),
    [
        (b"PNG and more bytes", "no GIF"),
        (b"GIF89a\x01\x00", "no GIF"),
        # Extensions that end early: within the label, and within the sub-blocks.
        (b"GIF89a" + bytes(7) + b"\x21", "ends within a block"),
        (b"GIF89a" + bytes(7) + b"\x21\xfe\x05ab", "ends within a block"),
        # Something that is neither an extension nor a frame, and no block at all.
        (b"GIF89a" + bytes(7) + b"\x00", "no extension and no frame"),
        (b"GIF89a" + bytes(7), "no extension and no frame"),
    ],
)
def test_a_broken_gif_is_refused(recording: ModuleType, data: bytes, said: str) -> None:
    with pytest.raises(ValueError, match=said):
        recording.mark_of(data)


def write_pictures(folder: Path, data: bytes, video: bytes) -> tuple[Path, Path]:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "copier-copy.gif").write_bytes(data)
    (folder / "copier-copy.mp4").write_bytes(video)
    return folder / "copier-copy.gif", folder / "copier-copy.mp4"


def screens(folder: Path, *contents: bytes) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    found = []
    for number, content in enumerate(contents, 1):
        path = folder / f"{number:02d}.png"
        path.write_bytes(content)
        found.append(path)
    return found


def test_the_same_screens_keep_the_committed_gif_and_video(
    recording: ModuleType, tmp_path: Path
) -> None:
    shown = screens(tmp_path / "screens", b"question", b"answer")
    committed = recording.marked(
        gif(0, 255), recording.fingerprint([b"question", b"answer"])
    )
    write_pictures(tmp_path / "committed", committed, b"old video")
    # The new run caught other frames, with other colors.
    new_gif, new_video = write_pictures(
        tmp_path / "new", gif(0, 128, 255), b"new video"
    )

    assert recording.keep(new_gif, new_video, tmp_path / "committed", shown)

    assert new_gif.read_bytes() == committed
    assert new_video.read_bytes() == b"old video"


@pytest.mark.parametrize(
    ("contents", "committed_mark", "video"),
    [
        # A screen changed.
        ((b"question", b"other answer"), [b"question", b"answer"], True),
        # The committed GIF has no fingerprint yet.
        ((b"question", b"answer"), None, True),
        # The committed video is missing.
        ((b"question", b"answer"), [b"question", b"answer"], False),
    ],
)
def test_other_screens_renew_the_gif_and_the_video(
    recording: ModuleType,
    tmp_path: Path,
    contents: tuple[bytes, ...],
    committed_mark: list[bytes] | None,
    video: bool,
) -> None:
    shown = screens(tmp_path / "screens", *contents)
    committed = gif(0, 255)
    if committed_mark is not None:
        committed = recording.marked(committed, recording.fingerprint(committed_mark))
    write_pictures(tmp_path / "committed", committed, b"old video")
    if not video:
        (tmp_path / "committed/copier-copy.mp4").unlink()
    new = gif(0, 128, 255)
    new_gif, new_video = write_pictures(tmp_path / "new", new, b"new video")

    assert not recording.keep(new_gif, new_video, tmp_path / "committed", shown)

    assert pixels(new_gif.read_bytes()) == pixels(new)
    assert recording.mark_of(new_gif.read_bytes()) == recording.fingerprint(
        list(contents)
    )
    assert new_video.read_bytes() == b"new video"


def test_a_first_recording_has_no_committed_one(
    recording: ModuleType, tmp_path: Path
) -> None:
    shown = screens(tmp_path / "screens", b"question")
    new_gif, new_video = write_pictures(tmp_path / "new", gif(0), b"new video")

    assert not recording.keep(new_gif, new_video, tmp_path / "none", shown)
    assert recording.mark_of(new_gif.read_bytes())


def test_main_says_whether_it_kept_the_recording(
    recording: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    shown = screens(tmp_path / "screens", b"question")
    committed = recording.marked(gif(0), recording.fingerprint([b"question"]))
    write_pictures(tmp_path / "committed", committed, b"old video")
    new_gif, new_video = write_pictures(tmp_path / "new", gif(0, 255), b"new video")
    arguments = ["keep", str(new_gif), str(new_video), str(tmp_path / "committed")]

    recording.main([*arguments, *map(str, shown)])
    assert capsys.readouterr().err == (
        "copier-copy.gif shows the same screens as before: it and copier-copy.mp4 "
        "stay as they are.\n"
    )

    (tmp_path / "screens/01.png").write_bytes(b"another question")
    recording.main([*arguments, *map(str, shown)])
    assert capsys.readouterr().err == (
        "copier-copy.gif shows other screens: it and copier-copy.mp4 are new.\n"
    )


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["keep", "a.gif", "a.mp4", "folder"],
        ["mark", "a.gif", "a.mp4", "f", "s.png"],
    ],
)
def test_main_explains_itself_without_its_arguments(
    recording: ModuleType, arguments: list[str]
) -> None:
    with pytest.raises(SystemExit) as stopped:
        recording.main(arguments)

    assert "python3 recording.py keep" in str(stopped.value.code)


def test_main_names_what_failed(recording: ModuleType, tmp_path: Path) -> None:
    (tmp_path / "new.gif").write_bytes(b"no GIF at all")
    (tmp_path / "screen.png").write_bytes(b"screen")

    with pytest.raises(SystemExit) as stopped:
        recording.main(
            [
                "keep",
                str(tmp_path / "new.gif"),
                str(tmp_path / "new.mp4"),
                str(tmp_path),
                str(tmp_path / "screen.png"),
            ]
        )
    assert stopped.value.code == "recording.py: The file is no GIF."

    with pytest.raises(SystemExit) as stopped:
        recording.main(
            ["keep", str(tmp_path / "new.gif"), "new.mp4", ".", str(tmp_path / "gone")]
        )
    assert str(stopped.value.code).startswith("recording.py: ")


def milliseconds(line: str) -> int | None:
    sleep = re.fullmatch(r"Sleep (\d+)(ms|s)", line)
    if sleep is None:
        return None
    return int(sleep[1]) * (1 if sleep[2] == "ms" else 1000)


def test_the_tape_takes_a_picture_of_each_screen_that_a_key_answers() -> None:
    # A picture shows the frame after its command: the screen it waited for has
    # settled 300 ms after it appeared, and stays at least 200 ms more before the key,
    # so that the next frame still shows it. The pictures are numbered in their order,
    # as the shell lists them for recording.py.
    lines = TAPE.read_text(encoding="utf-8").splitlines()
    shots = [
        index
        for index, line in enumerate(lines)
        if line.startswith("Screenshot screens/")
    ]
    assert len(shots) >= 20
    for number, index in enumerate(shots, 1):
        assert lines[index] == f"Screenshot screens/{number:02d}.png"
        assert lines[index - 1] == "Sleep 300ms", lines[index]
        assert lines[index - 2].startswith(("Wait", "Down@")), lines[index]
        after = milliseconds(lines[index + 1])
        assert after is not None, lines[index]
        assert after >= 200, lines[index]
    # A wait that rests half a second or longer before its key takes its picture; the
    # last one rests before the picture of the last screen, from which the website's
    # poster comes, which ends them.
    commands = [line for line in lines if line and not line.startswith("#")]
    last = commands.index("Screenshot docs/images/copier-copy.png")
    assert last > commands.index(lines[shots[-1]])
    for index, line in enumerate(commands[:-1]):
        if line.startswith(("Wait", "Down@")) and index + 1 != last - 1:
            rest = milliseconds(commands[index + 1])
            assert rest is None or rest < 500, f"{line} sleeps without a picture"


def test_the_script_keeps_the_recording_of_the_same_screens() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert "mkdir -p /tmp/out/docs/images /tmp/out/screens && cd /tmp/out &&" in script
    gifsicle = script.index("gifsicle --batch --optimize=3")
    keep = script.index(
        "python3 /work/.github/docs-pictures/recording.py keep copier-copy.gif "
        "copier-copy.mp4 \\\n      /work/docs/images /tmp/out/screens/*.png "
        "copier-copy.png >&2 &&"
    )
    tar = script.index("tar -cf - copier-copy.gif copier-copy.mp4")
    # After gifsicle, which writes no comment of its own, and before the files leave.
    assert gifsicle < keep < tar
    listed = (ROOT / ".github/docs-pictures/paths.txt").read_text(encoding="utf-8")
    assert "\n.github/docs-pictures/**\n" in listed
