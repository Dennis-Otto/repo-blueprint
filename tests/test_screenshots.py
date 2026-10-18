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

from blueprint.cli import main
from blueprint.screenshots import (
    LARGEST,
    REPORT,
    Kept,
    Picture,
    changed_share,
    commit_request,
    due,
    frames,
    is_picture,
    keep,
    kept,
    listing,
    looks_like_its_kind,
    parts,
    pathspec,
    patterns,
    report,
    same_pixels,
    shown_share,
    summary,
)

GIT = shutil.which("git")
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
            {"path": "docs/images/gone.png", "status": "deleted", "share": None},
            {"path": "docs/images/new.png", "status": "new", "share": None},
            {"path": "docs/images/other.png", "status": "changed", "share": 0.25},
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
                    {"path": p.path, "status": p.status, "share": p.share}
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
        "commits pictures only: `README.md`.\n"
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
