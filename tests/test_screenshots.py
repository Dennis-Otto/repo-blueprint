"""Tests of the screenshot bot: blueprint/screenshots.py, which decides when the bot
renders, compares the pictures that scripts/screenshots.sh rendered by their pixels
and turns those that look different into commits of the release app."""

from __future__ import annotations

import base64
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageSequence
from shared import load_yaml

from blueprint.cli import main
from blueprint.screenshots import (
    COMPARED_FILES,
    LARGEST,
    REPORT,
    Correction,
    Kept,
    Page,
    Picture,
    changed_share,
    commit_request,
    corrected_pages,
    corrections,
    due,
    fit_page,
    fitted_size,
    frames,
    is_picture,
    keep,
    kept,
    listing,
    looks_like_its_kind,
    overtaken,
    pages_of_folder,
    parts,
    pathspec,
    patterns,
    picture_size,
    report,
    repository_of,
    resized,
    same_pixels,
    shown_picture,
    shown_share,
    summary,
    written,
)

GIT = shutil.which("git")
ROOT = Path(__file__).resolve().parents[1]
RUN = "https://github.com/o/r/actions/runs/1"
SHA = "a" * 40


def png(
    size: tuple[int, int] = (4, 1),
    color: tuple[int, int, int, int] = (82, 108, 254, 255),
    changed: int = 0,
    level: int = 6,
) -> bytes:
    """A PNG of one color, whose first pixels, as many as changed, are white."""
    image = Image.new("RGBA", size, color)
    for x in range(changed):
        image.putpixel((x, 0), (255, 255, 255, 255))
    out = io.BytesIO()
    image.save(out, "PNG", compress_level=level)
    return out.getvalue()


def gif(colors: list[tuple[int, int, int]], durations: list[int]) -> bytes:
    """An animated GIF with a frame of each color, shown for its duration."""
    pictures = [Image.new("RGB", (2, 2), color) for color in colors]
    out = io.BytesIO()
    pictures[0].save(
        out,
        "GIF",
        save_all=True,
        append_images=pictures[1:],
        duration=durations,
        loop=0,
        optimize=False,
        disposal=1,
    )
    return out.getvalue()


def apng(colors: list[tuple[int, int, int]], disposals: list[int]) -> bytes:
    """An animated PNG with a frame of each color. A frame whose disposal differs
    from that of the one before stays in the file, even when it repeats it."""
    pictures = [Image.new("RGB", (2, 2), color) for color in colors]
    out = io.BytesIO()
    pictures[0].save(
        out,
        "PNG",
        save_all=True,
        append_images=pictures[1:],
        duration=[100] * len(colors),
        disposal=disposals,
    )
    return out.getvalue()


def git_in(root: Path, *arguments: str) -> str:
    assert GIT
    return subprocess.run(
        [GIT, "-c", "user.name=T", "-c", "user.email=t@example.com", *arguments],
        cwd=root,
        check=True,
        capture_output=True,
        encoding="utf-8",
    ).stdout.strip()


def repository(root: Path, files: dict[str, bytes]) -> Path:
    """A git repository whose one commit has these files."""
    root.mkdir(parents=True, exist_ok=True)
    git_in(root, "init", "--quiet", str(root))
    git_in(root, "config", "core.autocrlf", "false")
    write(root, files)
    git_in(root, "add", "--all")
    git_in(root, "commit", "--quiet", "--allow-empty", "-m", "First")
    return root


def write(root: Path, files: dict[str, bytes]) -> None:
    for name, data in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(data)


def commit(root: Path, files: dict[str, bytes], message: str = "Change") -> str:
    write(root, files)
    git_in(root, "add", "--all")
    git_in(root, "commit", "--quiet", "--allow-empty", "-m", message)
    return git_in(root, "rev-parse", "HEAD")


# Which files the bot takes


@pytest.mark.parametrize(
    ("path", "taken"),
    [
        ("docs/images/home.png", True),
        ("docs/images/home.dark.PNG", True),
        ("screenshots/01-search.jpg", True),
        ("img/photo.jpeg", True),
        ("docs/images/copier-copy.gif", True),
        ("docs/images/hero.webp", True),
        # The video that the website plays in place of a GIF.
        ("docs/images/copier-copy.mp4", True),
        (".github/social-preview.png", True),
        ("docs/images/diagrams/steps.svg", False),
        ("docs/index.md", False),
        ("README.md", False),
        (".git/objects/pack.png", False),
        (".github/workflows/shot.png", False),
        ("docs/../../outside.png", False),
        ("docs/with space.png", False),
        ("-rf.png", False),
        ("docs//home.png", False),
    ],
)
def test_the_bot_takes_only_pictures_by_plain_paths(path: str, taken: bool) -> None:
    assert is_picture(path) is taken


def test_a_picture_starts_as_its_kind_does() -> None:
    assert looks_like_its_kind("a.png", png())
    assert looks_like_its_kind("a.gif", gif([(0, 0, 0)], [100]))
    assert looks_like_its_kind("a.JPG", b"\xff\xd8\xff\xe0rest")
    assert looks_like_its_kind("a.webp", b"RIFF\0\0\0\0WEBPVP8 ")
    assert not looks_like_its_kind("a.webp", b"RIFF\0\0\0\0WAVEfmt ")
    assert looks_like_its_kind("a.mp4", b"\0\0\0\x20ftypisom\0\0\x02\0")
    assert not looks_like_its_kind("a.mp4", b"\0\0\0\x20moov")
    assert not looks_like_its_kind("a.mp4", png())
    assert not looks_like_its_kind("a.png", b"<svg>")
    assert not looks_like_its_kind("a.gif", png())


# When the bot renders


def test_the_list_names_the_files_whose_change_can_change_the_pictures(
    tmp_path: Path,
) -> None:
    assert patterns(tmp_path) == [
        "scripts/screenshots.sh",
        ".github/screenshots-paths.txt",
    ]
    listed = tmp_path / ".github/screenshots-paths.txt"
    listed.parent.mkdir()
    listed.write_text(
        "# The pages of the website\n\ndocs/**\n  !docs/changelog.md  \n",
        encoding="utf-8",
    )
    assert patterns(tmp_path) == [
        "scripts/screenshots.sh",
        ".github/screenshots-paths.txt",
        "docs/**",
        "!docs/changelog.md",
    ]
    assert patterns(tmp_path, Path("other.txt"), Path("draw.sh")) == [
        "draw.sh",
        "other.txt",
    ]


def test_a_pattern_is_a_pathspec_of_git() -> None:
    assert pathspec("src/**/*.ts") == ":(glob)src/**/*.ts"
    assert pathspec("!docs/changelog.md") == ":(glob,exclude)docs/changelog.md"


def test_the_bot_is_off_without_the_script(tmp_path: Path) -> None:
    ready, reason = due(repository(tmp_path, {"README.md": b"# Demo\n"}))
    assert not ready
    assert "no `scripts/screenshots.sh`" in reason
    assert "adding the script turns it on" in reason


def test_the_bot_renders_after_a_change_of_a_listed_file(tmp_path: Path) -> None:
    root = repository(
        tmp_path,
        {
            "scripts/screenshots.sh": b"#!/usr/bin/env bash\n",
            ".github/screenshots-paths.txt": b"src/**\n!src/notes.md\n",
            "src/app.ts": b"one\n",
        },
    )
    first = git_in(root, "rev-parse", "HEAD")
    # A release, the weekly run and a start by hand render without a change.
    assert due(root) == (
        True,
        "The bot renders the pictures with `scripts/screenshots.sh`.",
    )

    commit(root, {"README.md": b"# Demo\n", "src/notes.md": b"left out\n"})
    ready, reason = due(root, first)
    assert not ready
    assert "touches no file of the list `.github/screenshots-paths.txt`" in reason

    second = git_in(root, "rev-parse", "HEAD")
    commit(root, {"src/app.ts": b"two\n"})
    assert due(root, second) == (
        True,
        "The change touches `src/app.ts`, so the bot renders the pictures.",
    )
    # The script itself and the list count too.
    third = git_in(root, "rev-parse", "HEAD")
    commit(root, {"scripts/screenshots.sh": b"#!/usr/bin/env bash\necho\n"})
    assert due(root, third)[0]


def test_the_reason_names_five_files_at_most(tmp_path: Path) -> None:
    root = repository(
        tmp_path,
        {"scripts/screenshots.sh": b"", ".github/screenshots-paths.txt": b"src/\n"},
    )
    first = git_in(root, "rev-parse", "HEAD")
    commit(root, {f"src/{number}.ts": b"x\n" for number in range(7)})
    ready, reason = due(root, first)
    assert ready
    assert reason.endswith("and 2 more, so the bot renders the pictures.")
    assert reason.count("`") == 10


def test_another_script_and_list_decide_for_themselves(tmp_path: Path) -> None:
    root = repository(
        tmp_path,
        {
            "scripts/docs-pictures.sh": b"",
            ".github/docs-pictures/paths.txt": b"copier.yml\ntemplate/**\n",
        },
    )
    first = git_in(root, "rev-parse", "HEAD")
    release = commit(root, {"template/README.md.jinja": b"# {= name =}\n"})
    script, paths = (
        Path("scripts/docs-pictures.sh"),
        Path(".github/docs-pictures/paths.txt"),
    )
    assert not due(root, first, release, paths=paths)[0]
    assert due(root, first, release, paths=paths, script=script)[0]
    later = commit(root, {"docs/guide.md": b"# Guide\n"})
    assert not due(root, release, later, paths=paths, script=script)[0]


# How the bot compares


def test_a_frame_that_repeats_the_one_before_counts_once() -> None:
    blue, white = (82, 108, 254), (255, 255, 255)
    # A recording that waited a moment longer, or whose encoder merged the frames.
    assert frames(gif([blue, blue, white], [100, 100, 100])) == frames(
        gif([blue, white], [700, 40])
    )
    assert len(frames(gif([blue, white, blue], [100, 100, 100]))) == 3
    repeated = apng([blue, blue, white], [0, 1, 0])
    with Image.open(io.BytesIO(repeated)) as image:
        assert sum(1 for _ in ImageSequence.Iterator(image)) == 3
    assert frames(repeated) == frames(gif([blue, white], [100, 100]))
    assert frames(gif([blue, white], [100, 100])) != frames(
        gif([white, blue], [100, 100])
    )


def test_a_transparent_pixel_has_no_color() -> None:
    assert frames(png(color=(1, 2, 3, 0))) == frames(png(color=(200, 100, 50, 0)))
    assert frames(png(color=(1, 2, 3, 128))) != frames(png(color=(200, 100, 50, 128)))


def test_the_same_pixels_in_another_file_look_the_same() -> None:
    assert png(level=0) != png(level=9)
    assert same_pixels(png(level=0), png(level=9))
    assert same_pixels(png(), png())
    assert not same_pixels(png(), png(changed=1))
    assert not same_pixels(png(), png(size=(4, 2)))
    # A file that Pillow can't read differs from every other.
    assert not same_pixels(b"\x89PNG\r\n\x1a\nbroken", png())
    assert same_pixels(b"same bytes", b"same bytes")


def test_the_share_of_the_changed_pixels() -> None:
    assert changed_share(png(), png(level=0)) == 0
    assert changed_share(png(), png(changed=1)) == 0.25
    assert changed_share(png(), png(changed=4)) == 1
    assert changed_share(png(), png(size=(2, 2))) is None
    blue, white = (82, 108, 254), (255, 255, 255)
    two = gif([blue, white], [100, 100])
    assert changed_share(two, gif([blue], [100])) is None
    # The second of two frames changed in all its pixels: half of all.
    assert changed_share(two, gif([blue, (0, 0, 0)], [100, 100])) == 0.5


@pytest.mark.parametrize(
    ("share", "shown"),
    [
        (None, "another size or frames"),
        (1.0, "100 %"),
        (0.00001, "< 0.01 %"),
        (0.0, "< 0.01 %"),
        (0.25, "25.00 %"),
        (0.0001, "0.01 %"),
    ],
)
def test_the_share_as_the_pull_request_shows_it(
    share: float | None, shown: str
) -> None:
    assert shown_share(share) == shown


# What the bot keeps


def rendered(tmp_path: Path) -> Path:
    """A repository after scripts/screenshots.sh rendered its pictures anew: one in
    another file with the same pixels, one with other pixels, a new one, a deleted
    one, an animation that waited longer, and a page of Markdown."""
    blue, white = (82, 108, 254), (255, 255, 255)
    root = repository(
        tmp_path / "repository",
        {
            "README.md": b"# Demo\n",
            "docs/images/same.png": png(level=9),
            "docs/images/other.png": png(),
            "docs/images/gone.png": png(),
            "docs/images/recording.gif": gif([blue, white], [100, 100]),
            "docs/images/untouched.png": png(changed=2),
        },
    )
    write(
        root,
        {
            "README.md": b"# Demo, rendered\n",
            "docs/images/same.png": png(level=0),
            "docs/images/other.png": png(changed=1),
            "docs/images/new.png": png(size=(2, 2)),
            "docs/images/recording.gif": gif([blue, blue, white], [100, 300, 100]),
        },
    )
    (root / "docs/images/gone.png").unlink()
    return root


def test_keep_takes_only_the_pictures_that_look_different(tmp_path: Path) -> None:
    root = rendered(tmp_path)
    folder = tmp_path / "kept"
    found = keep(root, folder)

    assert found == Kept(
        (
            Picture("docs/images/gone.png", "deleted"),
            Picture("docs/images/new.png", "new"),
            Picture("docs/images/other.png", "changed", 0.25),
        ),
        ("README.md",),
    )
    # The pictures that look the same have their committed files back.
    assert git_in(root, "status", "--porcelain", "--", "docs/images/same.png") == ""
    assert (
        git_in(root, "status", "--porcelain", "--", "docs/images/recording.gif") == ""
    )
    files = sorted(
        path.relative_to(folder).as_posix()
        for path in folder.rglob("*")
        if path.is_file()
    )
    assert files == [
        "deleted.txt",
        "files/docs/images/new.png",
        "files/docs/images/other.png",
        REPORT,
    ]
    assert (folder / "files/docs/images/other.png").read_bytes() == png(changed=1)
    assert (folder / "deleted.txt").read_text(
        encoding="utf-8"
    ) == "docs/images/gone.png\n"
    assert json.loads((folder / REPORT).read_text(encoding="utf-8")) == {
        "pictures": [
            {
                "path": "docs/images/gone.png",
                "status": "deleted",
                "share": None,
                "before": None,
            },
            {
                "path": "docs/images/new.png",
                "status": "new",
                "share": None,
                "before": None,
            },
            {
                "path": "docs/images/other.png",
                "status": "changed",
                "share": 0.25,
                "before": None,
            },
        ],
        "ignored": ["README.md"],
    }
    # What it kept passes the checks of the job that commits it.
    assert kept(folder) == found


def test_restore_changes_only_the_work_tree(tmp_path: Path) -> None:
    root = rendered(tmp_path)
    found = keep(root)
    assert [picture.path for picture in found.pictures] == [
        "docs/images/gone.png",
        "docs/images/new.png",
        "docs/images/other.png",
    ]
    assert git_in(root, "status", "--porcelain", "--", "docs/images/same.png") == ""


def test_keep_leaves_the_folder_away_when_every_picture_looks_the_same(
    tmp_path: Path,
) -> None:
    root = repository(tmp_path / "repository", {"docs/images/a.png": png(level=9)})
    write(root, {"docs/images/a.png": png(level=1)})
    found = keep(root, tmp_path / "kept")
    assert found == Kept(())
    assert not (tmp_path / "kept").exists()
    assert git_in(root, "status", "--porcelain") == ""


def test_keep_keeps_a_deletion_alone_too(tmp_path: Path) -> None:
    # A script that dropped a picture and changed no other pixels.
    root = repository(
        tmp_path / "repository",
        {"docs/images/a.png": png(), "docs/images/gone.png": png()},
    )
    (root / "docs/images/gone.png").unlink()
    folder = tmp_path / "kept"
    found = keep(root, folder)
    assert found == Kept((Picture("docs/images/gone.png", "deleted"),))
    assert (folder / "deleted.txt").read_text(
        encoding="utf-8"
    ) == "docs/images/gone.png\n"
    assert not (folder / "files").exists()
    assert kept(folder) == found


def test_keep_names_a_picture_it_cant_read(tmp_path: Path) -> None:
    root = repository(
        tmp_path / "repository", {"docs/images/a.png": b"\x89PNG\r\n\x1a\nold"}
    )
    write(root, {"docs/images/a.png": png()})
    assert keep(root, tmp_path / "kept").pictures == (
        Picture("docs/images/a.png", "changed", None),
    )


def test_keep_takes_a_video_whose_bytes_changed(tmp_path: Path) -> None:
    # Pillow reads no video, so a video counts as changed by its bytes alone.
    video = b"\0\0\0\x20ftypisom\0\0\x02\0"
    root = repository(
        tmp_path / "repository",
        {"docs/images/a.mp4": video + b"old", "docs/images/b.mp4": video},
    )
    write(root, {"docs/images/a.mp4": video + b"new", "docs/images/b.mp4": video})
    kept = keep(root, tmp_path / "kept")
    assert kept.pictures == (Picture("docs/images/a.mp4", "changed", None),)
    assert (tmp_path / "kept/files/docs/images/a.mp4").read_bytes() == video + b"new"


def test_keep_takes_a_video_beside_a_gif_only_with_the_gif(tmp_path: Path) -> None:
    # The script records again: the GIF of a.mp4 kept its pixels, that of b.mp4 not.
    video = b"\0\0\0\x20ftypisom\0\0\x02\0"
    root = repository(
        tmp_path / "repository",
        {
            "docs/images/a.gif": gif([(1, 2, 3)], [100]),
            "docs/images/a.mp4": video + b"old",
            "docs/images/b.gif": gif([(1, 2, 3)], [100]),
            "docs/images/b.mp4": video + b"old",
        },
    )
    write(
        root,
        {
            "docs/images/a.gif": gif([(1, 2, 3), (1, 2, 3)], [50, 50]),
            "docs/images/a.mp4": video + b"new",
            "docs/images/b.gif": gif([(0, 0, 0)], [100]),
            "docs/images/b.mp4": video + b"new",
        },
    )
    kept = keep(root, tmp_path / "kept")
    assert [picture.path for picture in kept.pictures] == [
        "docs/images/b.gif",
        "docs/images/b.mp4",
    ]
    assert (root / "docs/images/a.mp4").read_bytes() == video + b"old"
    assert (root / "docs/images/b.mp4").read_bytes() == video + b"new"


def test_keep_fails_on_a_picture_that_is_no_picture(tmp_path: Path) -> None:
    root = repository(tmp_path / "repository", {"README.md": b"# Demo\n"})
    write(root, {"docs/images/a.png": b"<html>an error page</html>"})
    with pytest.raises(
        ValueError, match=r"docs/images/a\.png, which is no PNG picture"
    ):
        keep(root, tmp_path / "kept")


# What the job of the pull request takes


def folder_with(
    tmp_path: Path, files: dict[str, bytes], pictures: list[Picture]
) -> Path:
    folder = tmp_path / "kept"
    for path, data in files.items():
        (folder / "files" / path).parent.mkdir(parents=True, exist_ok=True)
        (folder / "files" / path).write_bytes(data)
    deleted = [picture.path for picture in pictures if picture.status == "deleted"]
    folder.mkdir(exist_ok=True)
    if deleted:
        (folder / "deleted.txt").write_text(
            "".join(f"{p}\n" for p in deleted), encoding="utf-8"
        )
    (folder / REPORT).write_text(
        json.dumps(
            {
                "pictures": [
                    {
                        "path": p.path,
                        "status": p.status,
                        "share": p.share,
                        "before": p.before,
                    }
                    for p in pictures
                ],
                "ignored": [],
            }
        ),
        encoding="utf-8",
    )
    return folder


@pytest.mark.parametrize(
    ("files", "pictures", "message"),
    [
        (
            {"docs/index.md": b"# Hi\n"},
            [Picture("docs/index.md", "new")],
            r"hold docs/index\.md, which is no picture",
        ),
        (
            {".github/workflows/x.png": png()},
            [Picture(".github/workflows/x.png", "new")],
            r"which is no picture",
        ),
        (
            {"docs/a.png": b"<svg/>"},
            [Picture("docs/a.png", "new")],
            r"hold docs/a\.png, which is no PNG picture",
        ),
        (
            {},
            [Picture("README.md", "deleted")],
            r"would delete README\.md, which is no picture",
        ),
        (
            {"docs/a.png": png()},
            [Picture("docs/b.png", "new")],
            r"names other pictures than the run holds",
        ),
        ({}, [], r"hold nothing to commit"),
    ],
)
def test_the_bot_takes_nothing_but_the_pictures_of_the_report(
    tmp_path: Path, files: dict[str, bytes], pictures: list[Picture], message: str
) -> None:
    folder = folder_with(tmp_path, files, pictures)
    with pytest.raises(ValueError, match=message):
        kept(folder)


def test_the_report_names_the_deleted_pictures_too(tmp_path: Path) -> None:
    pictures = [Picture("docs/a.png", "new"), Picture("docs/c.png", "deleted")]
    folder = folder_with(tmp_path, {"docs/a.png": png()}, pictures)
    assert kept(folder).pictures == tuple(pictures)
    (folder / "deleted.txt").unlink()
    with pytest.raises(ValueError, match="names other pictures than the run holds"):
        kept(folder)


@pytest.mark.parametrize("report_text", [None, "not json", '{"pictures": [{}]}', "[]"])
def test_the_bot_needs_a_readable_report(
    tmp_path: Path, report_text: str | None
) -> None:
    folder = folder_with(
        tmp_path, {"docs/a.png": png()}, [Picture("docs/a.png", "new")]
    )
    if report_text is None:
        (folder / REPORT).unlink()
    else:
        (folder / REPORT).write_text(report_text, encoding="utf-8")
    with pytest.raises(ValueError, match=r"no readable report\.json"):
        kept(folder)


def test_the_bot_refuses_a_link(tmp_path: Path) -> None:
    folder = folder_with(tmp_path, {}, [Picture("docs/a.png", "new")])
    (folder / "files/docs").mkdir(parents=True)
    target = tmp_path / "secret.png"
    target.write_bytes(png())
    try:
        os.symlink(target, folder / "files/docs/a.png")
    except OSError:
        pytest.skip("this system makes no symbolic links")
    with pytest.raises(ValueError, match="which is no picture"):
        kept(folder)


def test_large_sets_of_pictures_go_in_parts(tmp_path: Path) -> None:
    big = png(size=(64, 64), level=0)
    folder = folder_with(
        tmp_path,
        {"docs/a.png": big, "docs/b.png": big, "docs/c.png": big},
        [
            Picture("docs/a.png", "new"),
            Picture("docs/b.png", "changed", 0.5),
            Picture("docs/c.png", "new"),
            Picture("docs/d.png", "deleted"),
        ],
    )
    assert [len(part) for part in parts(folder)] == [4]
    # Each part stays below the largest request, one picture at least in each.
    limit = len(big) * 4 // 3 * 2
    assert [[p.path for p in part] for part in parts(folder, limit)] == [
        ["docs/a.png", "docs/b.png"],
        ["docs/c.png", "docs/d.png"],
    ]
    assert [len(part) for part in parts(folder, 1)] == [1, 1, 2]
    assert LARGEST < 10_000_000


def test_the_commits_write_the_pictures_and_the_pages(tmp_path: Path) -> None:
    folder = folder_with(
        tmp_path,
        {"docs/a.png": png()},
        [Picture("docs/a.png", "changed", 0.5), Picture("docs/c.png", "deleted")],
    )
    page = Page("docs/index.md", b"# Hi\n", ())
    assert written(folder, [page]) == ["docs/a.png", "docs/c.png", "docs/index.md"]
    assert written(folder) == ["docs/a.png", "docs/c.png"]


def changes(*names: str, **renamed: str) -> list[dict[str, str]]:
    """The files of GitHub's comparison: changed by their names, renamed from the
    names that renamed maps them to."""
    found = [{"filename": name, "status": "modified"} for name in names]
    found += [
        {"filename": new, "status": "renamed", "previous_filename": old}
        for old, new in renamed.items()
    ]
    return found


def test_main_that_changed_no_file_of_the_pull_request_takes_it() -> None:
    # Such as an update of the blueprint that merged while the pictures rendered.
    moved, reason = overtaken(
        ["docs/a.png", "docs/index.md"],
        {"behind_by": 0, "files": changes(".github/workflows/ci.yml", "src/a.py")},
    )
    assert not moved
    assert reason == (
        "`main` changed none of the files of the pull request since the commit that "
        "was rendered."
    )
    assert overtaken(["docs/a.png"], {"behind_by": 0}) == (False, reason)


def test_main_that_changed_a_picture_of_the_pull_request_meanwhile_overtook_it() -> (
    None
):
    # paperless-unified-search#316: the pull request before merged the same GIF while
    # the release rendered.
    moved, reason = overtaken(
        ["docs/images/a.gif", "docs/images/a.mp4", "docs/images/b.gif"],
        {"behind_by": 0, "files": changes("docs/images/a.gif", "docs/images/a.mp4")},
        "trunk",
    )
    assert moved
    assert reason == (
        "`trunk` changed `docs/images/a.gif`, `docs/images/a.mp4` since the commit "
        "that was rendered, so a pull request from that commit would conflict: the "
        "bot renders `trunk` anew."
    )


def test_a_page_or_a_renamed_file_overtakes_the_pull_request_too() -> None:
    assert overtaken(["docs/index.md"], {"files": changes("docs/index.md")})[0]
    # A file that main moved away, and one that it moved there.
    renamed = {"files": changes(**{"docs/old.png": "docs/new.png"})}
    assert overtaken(["docs/old.png"], renamed)[0]
    assert overtaken(["docs/new.png"], renamed)[0]


def test_the_reason_names_five_files_of_the_pull_request_at_most() -> None:
    paths = [f"docs/{number}.png" for number in range(7)]
    moved, reason = overtaken(paths, {"files": changes(*paths)})
    assert moved
    assert "`docs/4.png` and 2 more since" in reason
    assert "docs/5.png" not in reason


def test_main_without_the_commit_that_was_rendered_overtook_it() -> None:
    # After a forced push, main lacks the commit that the pull request would start from.
    assert overtaken(["docs/a.png"], {"behind_by": 2, "files": []}) == (
        True,
        "`main` no longer has the commit that was rendered, so the bot renders `main` "
        "anew.",
    )


def test_a_comparison_too_long_to_list_every_file_overtook_it() -> None:
    files = changes(*(f"src/{number}.py" for number in range(COMPARED_FILES)))
    moved, reason = overtaken(["docs/a.png"], {"behind_by": 0, "files": files})
    assert moved
    assert "more than GitHub lists" in reason
    assert not overtaken(["docs/a.png"], {"files": files[1:]})[0]


def test_the_request_commits_a_part_of_the_pictures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = folder_with(
        tmp_path,
        {"docs/a.png": png(), "docs/b.png": png(changed=1)},
        [
            Picture("docs/a.png", "new"),
            Picture("docs/b.png", "changed", 0.25),
            Picture("docs/c.png", "deleted"),
        ],
    )
    request = commit_request(
        folder, "o/r", "bot/screenshots-next", SHA, "docs: x", "Body"
    )
    assert "createCommitOnBranch" in request["query"]
    assert request["variables"]["input"] == {
        "branch": {
            "repositoryNameWithOwner": "o/r",
            "branchName": "bot/screenshots-next",
        },
        "expectedHeadOid": SHA,
        "message": {"headline": "docs: x", "body": "Body"},
        "fileChanges": {
            "additions": [
                {"path": "docs/a.png", "contents": base64.b64encode(png()).decode()},
                {
                    "path": "docs/b.png",
                    "contents": base64.b64encode(png(changed=1)).decode(),
                },
            ],
            "deletions": [{"path": "docs/c.png"}],
        },
    }
    monkeypatch.setattr("blueprint.screenshots.LARGEST", 1)
    second = commit_request(folder, "o/r", "b", SHA, "docs: x", "Body", part=2)
    assert second["variables"]["input"]["message"]["headline"] == "docs: x (2 of 2)"
    assert second["variables"]["input"]["fileChanges"] == {
        "additions": [
            {
                "path": "docs/b.png",
                "contents": base64.b64encode(png(changed=1)).decode(),
            }
        ],
        "deletions": [{"path": "docs/c.png"}],
    }
    with pytest.raises(ValueError, match="have no part 3, of 2"):
        commit_request(folder, "o/r", "b", SHA, "docs: x", "Body", part=3)


# The sizes that the pages name


def encoded(kind: str, size: tuple[int, int] = (660, 878), **options: object) -> bytes:
    """A picture of a kind that Pillow writes, of one color."""
    out = io.BytesIO()
    Image.new("RGB", size, (82, 108, 254)).save(out, kind, **options)
    return out.getvalue()


def animated_webp(size: tuple[int, int]) -> bytes:
    first = Image.new("RGB", size, (82, 108, 254))
    second = Image.new("RGB", size, (255, 255, 255))
    out = io.BytesIO()
    first.save(out, "WEBP", save_all=True, append_images=[second], duration=100)
    return out.getvalue()


PICTURES = {
    "a.png": png(size=(660, 878)),
    "a.gif": encoded("GIF"),
    "a.jpg": encoded("JPEG"),
    "a.jpeg": encoded("JPEG", progressive=True),
    "lossy.webp": encoded("WEBP"),
    "lossless.webp": encoded("WEBP", lossless=True),
    "animated.webp": animated_webp((660, 878)),
}


@pytest.mark.parametrize(("path", "data"), PICTURES.items())
def test_a_picture_names_its_size_in_its_header(path: str, data: bytes) -> None:
    # As Pillow reads it, which the job with the release app doesn't have.
    with Image.open(io.BytesIO(data)) as image:
        assert image.size == (660, 878)
    assert picture_size(path, data) == (660, 878)
    assert picture_size(path.upper(), data) == (660, 878)


@pytest.mark.parametrize(("path", "data"), PICTURES.items())
def test_a_broken_picture_has_no_size_and_stops_nothing(path: str, data: bytes) -> None:
    # The files come from a job that ran the script of the project.
    for length in range(min(len(data), 2000)):
        assert picture_size(path, data[:length]) in (None, (660, 878))


@pytest.mark.parametrize(
    ("path", "data"),
    [
        ("a.mp4", b"\0\0\0\x18ftypmp42" + bytes(40)),
        ("a.svg", b"<svg/>"),
        ("a.png", b"not a picture at all, and long enough for it"),
        # No header where one belongs, and sizes of no pixels.
        ("a.png", b"\x89PNG\r\n\x1a\n" + bytes(40)),
        ("a.png", png()[:16] + bytes(8) + png()[24:]),
        ("a.gif", b"GIF89a" + bytes(40)),
        ("a.jpg", b"\xff\xd8\xff\xe0\0\x02" + b"\0" + bytes(40)),
        ("a.webp", b"RIFF\0\0\0\0WEBPVP8Z" + bytes(40)),
        ("a.webp", b"RIFF\0\0\0\0WEBPVP8 " + bytes(40)),
    ],
    ids=["video", "svg", "text", "png", "png0", "gif0", "jpeg", "webp", "webp0"],
)
def test_a_file_that_names_no_size_has_none(path: str, data: bytes) -> None:
    assert picture_size(path, data) is None


@pytest.mark.parametrize(
    ("named", "before", "after", "fitted"),
    [
        # The whole picture of another shape, as in paperless-unified-search#274.
        ((660, 788), (660, 788), (660, 878), (660, 878)),
        ((1600, 900), (1600, 900), (1280, 800), (1280, 800)),
        # A single pixel more is another shape too, when the page names the whole.
        ((660, 788), (660, 788), (660, 789), (660, 789)),
        # A smaller picture keeps its width, with the height of the new shape.
        ((120, 260), (390, 844), (390, 900), (120, 277)),
        # A size that fits stays: the new size, a sharper file of the same shape,
        # and rounding to the next pixel at a smaller size.
        ((660, 878), (660, 788), (660, 878), None),
        ((660, 788), (660, 788), (1320, 1576), None),
        ((120, 259), (390, 800), (390, 844), None),
        ((120, 260), (390, 800), (390, 844), None),
    ],
)
def test_the_size_that_a_page_should_name(
    named: tuple[int, int],
    before: tuple[int, int],
    after: tuple[int, int],
    fitted: tuple[int, int] | None,
) -> None:
    assert fitted_size(named, before, after) == fitted


def test_a_very_flat_picture_keeps_a_height_of_one_pixel() -> None:
    assert fitted_size((3, 90), (30, 900), (9000, 1)) == (3, 1)


@pytest.mark.parametrize(
    ("address", "page", "shown"),
    [
        # Relative to the page.
        ("a.png", "README.md", "a.png"),
        ("images/a.png#only-dark", "docs/index.md", "docs/images/a.png"),
        ("./images/a.png?v=1", "docs/index.md", "docs/images/a.png"),
        ("../screenshots/a.png", "docs/index.md", "screenshots/a.png"),
        ("../shot.png", "docs/deep/index.md", "docs/shot.png"),
        # From main of the repository, as the hooks of the website read it.
        ("https://github.com/o/r/raw/main/s/a.png", "docs/x.md", "s/a.png"),
        ("https://github.com/o/r/raw/main/s/a.png#only-dark", "x.md", "s/a.png"),
        ("https://github.com/O/R/raw/HEAD/s/a.png", "x.md", "s/a.png"),
        ("https://github.com/o/r/raw/refs/heads/main/s/a.png", "x.md", "s/a.png"),
        ("https://github.com/o/r/blob/main/s/a.png?raw=true", "x.md", "s/a.png"),
        (
            "https://github.com/o/r/blob/main/s/a.png?a=1&amp;raw=true",
            "x.md",
            "s/a.png",
        ),
        ("https://raw.githubusercontent.com/o/r/main/s/a.png", "x.md", "s/a.png"),
        (
            "https://raw.githubusercontent.com/o/r/refs/heads/main/s/a.png",
            "x",
            "s/a.png",
        ),
        # Anything else shows no picture of this branch of this repository.
        ("https://github.com/o/r/blob/main/s/a.png", "x.md", ""),
        ("https://github.com/o/other/raw/main/s/a.png", "x.md", ""),
        ("https://github.com/o/r/raw/v1.0.0/s/a.png", "x.md", ""),
        ("https://github.com/o/r/raw/main", "x.md", ""),
        ("https://example.com/o/r/raw/main/s/a.png", "x.md", ""),
        ("http://github.com/o/r/raw/main/s/a.png", "x.md", ""),
        ("//github.com/o/r/raw/main/s/a.png", "x.md", ""),
        ("data:image/png;base64,AAAA", "x.md", ""),
        ("https://[broken/a.png", "x.md", ""),
    ],
)
def test_the_picture_that_a_page_shows(address: str, page: str, shown: str) -> None:
    assert shown_picture(address, page, "o/r") == shown


def test_without_a_repository_only_a_relative_address_counts() -> None:
    assert shown_picture("https://github.com/o/r/raw/main/a.png", "x.md", "") == ""
    assert shown_picture("a.png", "x.md", "") == "a.png"


RESIZED = {"s/a.png": ((660, 788), (660, 878))}
FROM_MAIN = "https://github.com/o/r/raw/main/s/a.png"


@pytest.mark.parametrize(
    ("line", "corrected"),
    [
        # Markdown with attributes, as paperless-unified-search#274 has it, in any
        # order, with other attributes, a title, a text with brackets, a fragment.
        (
            f'![A]({FROM_MAIN}#only-dark){{ width="660" height="788" }}',
            f'![A]({FROM_MAIN}#only-dark){{ width="660" height="878" }}',
        ),
        (
            f'  ![A [b] c]({FROM_MAIN} "T"){{ .x height="788" loading=lazy width="660" }}',
            f'  ![A [b] c]({FROM_MAIN} "T"){{ .x height="878" loading=lazy width="660" }}',
        ),
        (
            f"![A](<{FROM_MAIN}>){{: width=660 height='788' }}",
            f"![A](<{FROM_MAIN}>){{: width=660 height='878' }}",
        ),
        # HTML, also on several lines and with a > in its text; a width in the text
        # stays text.
        (
            f'<img src="{FROM_MAIN}" width="660" height="788" alt="A">',
            f'<img src="{FROM_MAIN}" width="660" height="878" alt="A">',
        ),
        (
            f"<IMG\n  alt='a > width=\"3\" b'\n  HEIGHT=788\n  WIDTH=660\n  SRC='{FROM_MAIN}'\n/>",
            f"<IMG\n  alt='a > width=\"3\" b'\n  HEIGHT=878\n  WIDTH=660\n  SRC='{FROM_MAIN}'\n/>",
        ),
        # At a smaller size.
        (
            f'<img src="{FROM_MAIN}" width="330" height="394">',
            f'<img src="{FROM_MAIN}" width="330" height="439">',
        ),
        # A line ending and the rest of the page stay.
        (
            f'Before\r\n![A]({FROM_MAIN}){{ width="660" height="788" }}\r\nAfter é\r\n',
            f'Before\r\n![A]({FROM_MAIN}){{ width="660" height="878" }}\r\nAfter é\r\n',
        ),
    ],
)
def test_a_page_gets_the_size_of_the_new_picture(line: str, corrected: str) -> None:
    fitted, made = fit_page(line, "docs/x.md", RESIZED, "o/r")
    assert fitted == corrected
    assert len(made) == 1
    assert made[0].picture == "s/a.png"
    # Once more changes nothing.
    assert fit_page(fitted, "docs/x.md", RESIZED, "o/r") == (fitted, [])


@pytest.mark.parametrize(
    "line",
    [
        # A width alone leaves the height to the browser.
        f'<img src="{FROM_MAIN}" width="320">',
        f'![A]({FROM_MAIN}){{ width="320" }}',
        # No whole numbers, no size, no picture at all.
        f'<img src="{FROM_MAIN}" width="50%" height="788">',
        f'<img src="{FROM_MAIN}" width="0" height="788">',
        f'<img src="{FROM_MAIN}" data-width="660" data-height="788">',
        f"![A]({FROM_MAIN})",
        '<img width="660" height="788">',
        # Other pictures, and a size that fits already.
        '<img src="https://github.com/o/r/raw/main/s/b.png" width="660" height="788">',
        '![A](s/a.png){ width="660" height="788" }',
        f'<img src="{FROM_MAIN}" width="660" height="878">',
    ],
)
def test_a_page_stays_when_in_doubt(line: str) -> None:
    assert fit_page(line, "docs/x.md", RESIZED, "o/r") == (line, [])


PAGE_OF_274 = (
    f'![A]({FROM_MAIN}#only-light){{ width="660" height="788" }}\n'
    f'![B](https://github.com/o/r/raw/main/s/a.dark.png#only-dark){{ width="660" height="788" }}\n'
)


def repository_with_pages(tmp_path: Path) -> Path:
    """A repository whose script rendered s/a.png taller, with the pages that name
    it, and files that the bot leaves alone."""
    root = repository(
        tmp_path / "repository",
        {
            "s/a.png": png(size=(660, 788)),
            "s/same.png": png(size=(660, 788), changed=1),
            "README.md": b"# Demo\n",
            "README.de.md": PAGE_OF_274.encode(),
            "docs/index.md": PAGE_OF_274.encode(),
            "docs/deep/page.md": b'![A](../../s/a.png){ width="330" height="394" }\n',
            "docs/other.md": b'<img src="../s/same.png" width="660" height="788">\n',
            "docs/latin.md": b'\xe9 ![A](../s/a.png){ width="660" height="788" }\n',
            "docs/with space.md": b'![A](../s/a.png){ width="660" height="788" }\n',
            "tests/page.md": b'![A](../s/a.png){ width="660" height="788" }\n',
            ".github/note.md": b'![A](../s/a.png){ width="660" height="788" }\n',
        },
    )
    write(
        root,
        {
            "s/a.png": png(size=(660, 878)),
            "s/same.png": png(size=(660, 788), changed=2),
        },
    )
    return root


def test_keep_names_the_size_of_a_picture_that_came_out_at_another(
    tmp_path: Path,
) -> None:
    root = repository_with_pages(tmp_path)
    folder = tmp_path / "kept"
    found = keep(root, folder)
    assert found.pictures == (
        Picture("s/a.png", "changed", None, (660, 788)),
        Picture("s/same.png", "changed", 1 / (660 * 788)),
    )
    assert kept(folder) == found
    assert resized(found, root) == {"s/a.png": ((660, 788), (660, 878))}
    assert resized(found, folder / "files") == resized(found, root)


def test_the_incident_of_a_pull_request_that_could_not_pass(tmp_path: Path) -> None:
    # paperless-unified-search#274: the bot rendered a picture taller and left the
    # sizes on the pages, whose check then failed until a person corrected them.
    root = repository_with_pages(tmp_path)
    folder = tmp_path / "kept"
    keep(root, folder)
    # The job with the release app has the checkout of main and the artifact.
    git_in(root, "checkout", "--", ".")

    pages = pages_of_folder(root, folder, "o/r")

    # Only pages at the top and in docs/, that git tracks by plain paths, in UTF-8.
    assert [page.path for page in pages] == [
        "README.de.md",
        "docs/deep/page.md",
        "docs/index.md",
    ]
    by_path = {page.path: page for page in pages}
    # The dark picture of the same page didn't change: its size stays.
    assert by_path["docs/index.md"].data.decode() == PAGE_OF_274.replace(
        'only-light){ width="660" height="788"', 'only-light){ width="660" height="878"'
    )
    assert by_path["docs/index.md"].corrections == (
        Correction("s/a.png", (660, 788), (660, 878)),
    )
    # A smaller picture keeps its width.
    assert by_path["docs/deep/page.md"].data == (
        b'![A](../../s/a.png){ width="330" height="439" }\n'
    )

    additions = commit_request(folder, "o/r", "b", SHA, "docs: x", "Body", pages=pages)[
        "variables"
    ]["input"]["fileChanges"]["additions"]
    assert {
        addition["path"]: base64.b64decode(addition["contents"])
        for addition in additions
    } == {
        "s/a.png": png(size=(660, 878)),
        "s/same.png": png(size=(660, 788), changed=2),
        **{page.path: page.data for page in pages},
    }


def test_a_script_reaches_no_page(tmp_path: Path) -> None:
    # A page that a script changed in its job stays out, and so does one that the
    # artifact holds: the text of a page comes from the checkout of main.
    root = repository_with_pages(tmp_path)
    write(root, {"docs/index.md": b"Written by the script\n"})
    folder = tmp_path / "kept"
    found = keep(root, folder)
    assert "docs/index.md" in found.ignored
    git_in(root, "checkout", "--", ".")
    (folder / "pages/docs").mkdir(parents=True)
    (folder / "pages/docs/index.md").write_bytes(b"Written by the script\n")
    pages = {page.path: page for page in pages_of_folder(root, folder, "o/r")}
    assert b"Written by the script" not in pages["docs/index.md"].data
    assert pages["docs/index.md"].data.startswith(b"![A](")


def test_a_lying_report_changes_only_the_numbers(tmp_path: Path) -> None:
    # The report says another size before, which at most decides whether a page
    # keeps its width: the height follows the file, and no other text changes.
    root = repository_with_pages(tmp_path)
    folder = tmp_path / "kept"
    keep(root, folder)
    git_in(root, "checkout", "--", ".")
    written = json.loads((folder / REPORT).read_text(encoding="utf-8"))
    written["pictures"][0]["before"] = [1, 1]
    (folder / REPORT).write_text(json.dumps(written), encoding="utf-8")
    pages = {page.path: page for page in pages_of_folder(root, folder, "o/r")}
    assert pages["docs/index.md"].corrections == (
        Correction("s/a.png", (660, 788), (660, 878)),
    )


@pytest.mark.parametrize("before", ['"a"', "1", "[1]", "[1, 2, 3]", '["a", "b"]'])
def test_the_bot_needs_a_readable_size_in_the_report(
    tmp_path: Path, before: str
) -> None:
    folder = folder_with(
        tmp_path, {"docs/a.png": png()}, [Picture("docs/a.png", "changed", None)]
    )
    written = (folder / REPORT).read_text(encoding="utf-8")
    (folder / REPORT).write_text(
        written.replace('"before": null', f'"before": {before}'), encoding="utf-8"
    )
    with pytest.raises(ValueError, match=r"no readable report\.json"):
        kept(folder)


def test_a_picture_that_names_no_size_leaves_its_pages(tmp_path: Path) -> None:
    folder = folder_with(
        tmp_path,
        {"s/a.png": b"\x89PNG\r\n\x1a\n" + bytes(40)},
        [Picture("s/a.png", "changed", None, (660, 788))],
    )
    assert resized(kept(folder), folder / "files") == {}
    # Without a picture of another size, git isn't even asked.
    assert corrected_pages(tmp_path / "nowhere", {}, "o/r") == []


def test_the_bot_follows_no_link_to_a_page(tmp_path: Path) -> None:
    root = repository_with_pages(tmp_path)
    try:
        os.symlink("index.md", root / "docs/link.md")
    except OSError:
        pytest.skip("this system makes no symbolic links")
    git_in(root, "add", "docs/link.md")
    pages = corrected_pages(root, {"s/a.png": ((660, 788), (660, 878))}, "o/r")
    assert "docs/link.md" not in [page.path for page in pages]


def test_a_page_that_a_sparse_checkout_leaves_out_stays(tmp_path: Path) -> None:
    root = repository_with_pages(tmp_path)
    (root / "docs/index.md").unlink()
    pages = corrected_pages(root, {"s/a.png": ((660, 788), (660, 878))}, "o/r")
    assert "docs/index.md" not in [page.path for page in pages]


def test_large_pages_go_in_parts_of_their_own(tmp_path: Path) -> None:
    folder = folder_with(tmp_path, {"s/a.png": png()}, [Picture("s/a.png", "new")])
    pages = [Page("docs/a.md", b"a" * 3000, ()), Page("docs/b.md", b"b" * 3000, ())]
    assert [[c.path for c in part] for part in parts(folder, pages=pages)] == [
        ["s/a.png", "docs/a.md", "docs/b.md"]
    ]
    assert [[c.path for c in part] for part in parts(folder, 5000, pages)] == [
        ["s/a.png", "docs/a.md"],
        ["docs/b.md"],
    ]


def test_the_description_names_the_corrected_sizes(tmp_path: Path) -> None:
    folder = folder_with(
        tmp_path, {"s/a.png": png()}, [Picture("s/a.png", "changed", None, (1, 1))]
    )
    assert corrections([]) == ""
    assert "the width and the height" not in report(folder, SHA, RUN)
    pages = [
        Page(
            "docs/index.md",
            b"",
            (
                Correction("s/a.png", (660, 788), (660, 878)),
                Correction("s/a.png", (330, 394), (330, 439)),
            ),
        ),
    ]
    text = report(folder, SHA, RUN, pages=pages)
    assert (
        "| Page | Picture | Named | Now |\n"
        "| --- | --- | ---: | ---: |\n"
        "| `docs/index.md` | `s/a.png` | 660 x 788 | 660 x 878 |\n"
        "| `docs/index.md` | `s/a.png` | 330 x 394 | 330 x 439 |\n"
    ) in text
    assert text.index("look different") < text.index("the width and the height")
    assert text.index("the width and the height") < text.index("merges itself")


@pytest.mark.parametrize(
    ("origin", "found"),
    [
        ("https://github.com/o/r", "o/r"),
        ("https://github.com/o/r.git", "o/r"),
        ("https://github.com/o/r/", "o/r"),
        ("git@github.com:o/r.git", "o/r"),
        ("ssh://git@github.com/o/r.git", "o/r"),
        ("https://example.com/o/r.git", ""),
        ("", ""),
    ],
)
def test_the_repository_of_the_remote(tmp_path: Path, origin: str, found: str) -> None:
    root = repository(tmp_path / "repository", {"a.txt": b"a\n"})
    if origin:
        git_in(root, "remote", "add", "origin", origin)
    assert repository_of(root) == found


def test_the_commands_correct_the_sizes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repository_with_pages(tmp_path)
    folder = tmp_path / "kept"
    assert main(["screenshots", "keep", str(folder)], root=root) == 0
    capsys.readouterr()
    git_in(root, "checkout", "--", ".")

    # The bot names the repository, and the size of a part counts the pages.
    assert main(["--repo", "o/r", "screenshots", "parts", str(folder)], root=root) == 0
    assert capsys.readouterr().out == "1\n"
    # Whether main changed a picture or a page of the pull request meanwhile, from
    # GitHub's comparison, which the bot keeps in a file.
    compared = tmp_path / "compared.json"
    ask = ["--repo", "o/r", "screenshots", "overtaken", str(folder)]
    ask += ["--compared", str(compared)]
    compared.write_text(
        json.dumps({"behind_by": 0, "files": changes("docs/index.md")}),
        encoding="utf-8",
    )
    assert main(ask, root=root) == 0
    assert "`main` changed `docs/index.md` since" in capsys.readouterr().out
    compared.write_text(
        json.dumps({"behind_by": 0, "files": changes("README.md")}), encoding="utf-8"
    )
    assert main([*ask, "--base", "trunk"], root=root) == 3
    assert capsys.readouterr().out.startswith("`trunk` changed none of the files")
    commit = ["--repo", "o/r", "screenshots", "commit", str(folder), "--branch", "b"]
    assert main([*commit, "--head", SHA, "--headline", "h"], root=root) == 0
    additions = json.loads(capsys.readouterr().out)["variables"]["input"][
        "fileChanges"
    ]["additions"]
    assert "docs/index.md" in [addition["path"] for addition in additions]
    show = ["screenshots", "report", str(folder), "--sha", SHA, "--run", RUN]
    assert main(["--repo", "o/r", *show], root=root) == 0
    assert "| `docs/index.md` | `s/a.png` | 660 x 788 | 660 x 878 |" in (
        capsys.readouterr().out
    )
    # Without --repo, the remote names it.
    git_in(root, "remote", "add", "origin", "https://github.com/o/r.git")
    assert main(show, root=root) == 0
    assert "| `docs/index.md` | `s/a.png` |" in capsys.readouterr().out
    # The command changes no file of the job.
    assert git_in(root, "status", "--porcelain") == ""


def test_restore_corrects_the_pages_on_your_machine(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repository_with_pages(tmp_path)
    git_in(root, "remote", "add", "origin", "git@github.com:o/r.git")
    assert main(["screenshots", "restore"], root=root) == 0
    out = capsys.readouterr().out
    assert "| `docs/index.md` | `s/a.png` | 660 x 788 | 660 x 878 |" in out
    assert (
        b'only-light){ width="660" height="878" }'
        in (root / "docs/index.md").read_bytes()
    )
    # A second run finds them correct, so it says nothing of them.
    assert main(["screenshots", "restore"], root=root) == 0
    assert "| Page |" not in capsys.readouterr().out


@pytest.mark.parametrize("name", ["screenshot-bot.yml", "docs-pictures.yml"])
def test_a_picture_bot_checks_out_its_tool_and_pages_without_pictures(
    tmp_path: Path, name: str
) -> None:
    # The job with the release app needs the Markdown and no picture of main; git
    # itself shows what the patterns of the job leave in the work tree.
    workflow = load_yaml(
        (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
    )
    job = workflow["jobs"]["pull-request"]
    checkout = next(
        step["with"]
        for step in job["steps"]
        if step.get("uses", "").startswith("actions/checkout@")
    )
    assert checkout["persist-credentials"] is False
    assert checkout["sparse-checkout-cone-mode"] is False
    files = {
        path: b"x\n"
        for path in (
            "README.md",
            "README.de.md",
            "CHANGELOG.md",
            "blueprint.py",
            "blueprint/screenshots.py",
            "docs/index.md",
            "docs/deep/er/page.de.md",
            "docs/images/a.png",
            "docs/images/deep/a.webp",
            "screenshots/a.png",
            "screenshots/notes.md",
            "src/secret.py",
            ".github/workflows/ci.yml",
        )
    }
    root = repository(tmp_path / "repository", files)
    git_in(
        root,
        "sparse-checkout",
        "set",
        "--no-cone",
        *checkout["sparse-checkout"].split(),
    )
    present = {path for path in files if (root / path).is_file()}
    assert present == {
        "README.md",
        "README.de.md",
        "CHANGELOG.md",
        "blueprint.py",
        "blueprint/screenshots.py",
        "docs/index.md",
        "docs/deep/er/page.de.md",
    }
    # Each command of the bot reads the same pages, for the same repository.
    script = "\n".join(step.get("run", "") for step in job["steps"])
    for command in ("parts", "commit", "report"):
        assert f'--repo "$GH_REPO" screenshots {command} "$kept"' in script


def test_the_tool_of_a_repository_is_in_the_checkout_of_the_screenshot_bot(
    tmp_path: Path,
) -> None:
    workflow = load_yaml(
        (ROOT / ".github/workflows/screenshot-bot.yml").read_text(encoding="utf-8")
    )
    checkout = next(
        step["with"]
        for step in workflow["jobs"]["pull-request"]["steps"]
        if step.get("uses", "").startswith("actions/checkout@")
    )
    files = {
        path: b"x\n"
        for path in (
            ".github/blueprint.py",
            ".github/blueprint/screenshots.py",
            ".github/other.yml",
        )
    }
    root = repository(tmp_path / "repository", files)
    git_in(
        root,
        "sparse-checkout",
        "set",
        "--no-cone",
        *checkout["sparse-checkout"].split(),
    )
    assert {path for path in files if (root / path).is_file()} == {
        ".github/blueprint.py",
        ".github/blueprint/screenshots.py",
    }


# What the bot says


def test_the_listing_shows_each_picture_with_its_change() -> None:
    found = Kept(
        (
            Picture("docs/a.png", "changed", 0.25),
            Picture("docs/b.png", "new"),
            Picture("docs/c.png", "deleted"),
        )
    )
    assert listing(found) == (
        "| Picture | Change | Pixels changed |\n"
        "| --- | --- | ---: |\n"
        "| `docs/a.png` | changed | 25.00 % |\n"
        "| `docs/b.png` | new |  |\n"
        "| `docs/c.png` | deleted |  |\n"
    )


def test_the_summary_says_what_keep_found() -> None:
    assert (
        summary(Kept(())) == "Every picture looks as committed, so no file changes.\n"
    )
    text = summary(Kept((Picture("docs/a.png", "new"),), ("README.md",)))
    assert text.startswith("These pictures look different:\n\n| Picture |")
    assert text.endswith(
        "\nThe script changed other files too, which the bot leaves out, because it "
        "takes only pictures from the script: `README.md`.\n"
    )


def test_the_description_of_the_pull_request(tmp_path: Path) -> None:
    folder = folder_with(
        tmp_path,
        {"docs/a.png": png(), ".github/social-preview.png": png()},
        [
            Picture(".github/social-preview.png", "changed", 1.0),
            Picture("docs/a.png", "new"),
        ],
    )
    text = report(folder, SHA, RUN)
    assert text.startswith(
        f"`bash scripts/screenshots.sh` rendered the pictures of `main` anew, on {SHA}"
    )
    assert "| `.github/social-preview.png` | changed | 100 % |" in text
    assert "upload it under **Settings → General → Social preview**" in text
    assert "leaves out" not in text
    assert text.endswith(f"keeps the pictures for three days: {RUN}\n")
    assert report(folder, SHA, RUN, Path("scripts/docs-pictures.sh")).startswith(
        "`bash scripts/docs-pictures.sh` rendered"
    )


def test_the_description_names_ten_other_files_at_most(tmp_path: Path) -> None:
    folder = folder_with(
        tmp_path, {"docs/a.png": png()}, [Picture("docs/a.png", "new")]
    )
    data = json.loads((folder / REPORT).read_text(encoding="utf-8"))
    data["ignored"] = [f"notes/{number}.md" for number in range(12)]
    (folder / REPORT).write_text(json.dumps(data), encoding="utf-8")
    text = report(folder, SHA, RUN)
    assert "`notes/9.md` and 2 more.\n" in text
    assert "upload it" not in text


# The commands


def test_the_commands_of_the_screenshot_bot(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = rendered(tmp_path)
    assert main(["screenshots", "due"], root=root) == 1
    assert "no `scripts/screenshots.sh`" in capsys.readouterr().out
    (root / "scripts").mkdir()
    (root / "scripts/screenshots.sh").write_text(
        "#!/usr/bin/env bash\n", encoding="utf-8"
    )
    assert main(["screenshots", "due"], root=root) == 0
    assert "renders the pictures" in capsys.readouterr().out
    assert (
        main(["screenshots", "due", "--since", "HEAD", "--until", "HEAD"], root=root)
        == 1
    )
    capsys.readouterr()
    (root / "scripts/screenshots.sh").unlink()

    folder = tmp_path / "kept"
    assert main(["screenshots", "keep", str(folder)], root=root) == 0
    assert capsys.readouterr().out.startswith("These pictures look different:")
    assert main(["screenshots", "restore"], root=root) == 0
    assert "| `docs/images/other.png` | changed | 25.00 % |" in capsys.readouterr().out
    # Without Pillow, the command names what installs it.
    with pytest.MonkeyPatch.context() as patch:
        patch.setitem(sys.modules, "PIL", None)
        assert main(["screenshots", "restore"], root=root) == 2
        assert (
            "screenshots restore needs PIL: python3 -m pip install --require-hashes"
            " -r stacks/screenshots/requirements.txt"
        ) in capsys.readouterr().err
        (root / ".github").mkdir()
        (root / ".github/screenshots-requirements.txt").write_text(
            "pillow\n", encoding="utf-8"
        )
        assert main(["screenshots", "keep", str(folder)], root=root) == 2
        assert (
            "screenshots keep needs PIL: python3 -m pip install --require-hashes"
            " -r .github/screenshots-requirements.txt"
        ) in capsys.readouterr().err
        shutil.rmtree(root / ".github")
    assert main(["screenshots", "parts", str(folder)], root=root) == 0
    assert capsys.readouterr().out == "1\n"

    assert (
        main(
            [
                "screenshots",
                "commit",
                str(folder),
                "--branch",
                "b",
                "--head",
                SHA,
                "--headline",
                "h",
            ],
            root=root,
        )
        == 2
    )
    assert "needs --repo" in capsys.readouterr().err
    arguments = ["--repo", "o/r", "screenshots", "commit", str(folder), "--branch", "b"]
    assert (
        main([*arguments, "--head", SHA, "--headline", "h", "--part", "1"], root=root)
        == 0
    )
    request = json.loads(capsys.readouterr().out)
    assert request["variables"]["input"]["fileChanges"]["deletions"] == [
        {"path": "docs/images/gone.png"}
    ]
    assert (
        main([*arguments, "--head", SHA, "--headline", "h", "--part", "2"], root=root)
        == 2
    )
    assert "have no part 2, of 1" in capsys.readouterr().err

    assert (
        main(
            ["screenshots", "report", str(folder), "--sha", SHA, "--run", RUN],
            root=root,
        )
        == 0
    )
    assert capsys.readouterr().out.startswith("`bash scripts/screenshots.sh` rendered")
    assert (
        main(
            [
                "screenshots",
                "report",
                str(tmp_path / "none"),
                "--sha",
                SHA,
                "--run",
                RUN,
            ],
            root=root,
        )
        == 2
    )
    assert "no readable report.json" in capsys.readouterr().err
