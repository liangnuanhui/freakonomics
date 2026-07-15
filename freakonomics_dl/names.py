"""Safe episode filenames from titles."""

from __future__ import annotations

import re


# Path separators and Windows-forbidden characters
_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def episode_basename(title: str, max_len: int = 180) -> str:
    """
    Build a filesystem-safe basename from episode title.

    Example:
      "Air Travel Is a Miracle. Why Do We Hate It?"
      -> "Air Travel Is a Miracle. Why Do We Hate It"
    """
    name = (title or "").strip()
    name = _INVALID.sub("", name)
    # drop trailing ? ! often used in titles (user example has no trailing ?)
    name = re.sub(r"[?!]+$", "", name).strip()
    name = re.sub(r"\s+", " ", name)
    # trailing dots/spaces are awkward on some filesystems
    name = name.rstrip(" .")
    if not name:
        name = "episode"
    if len(name) > max_len:
        name = name[:max_len].rstrip(" .")
    return name


def episode_paths(out_dir, title: str):
    """Return (mp3_path, md_path) sharing the same basename in out_dir."""
    from pathlib import Path

    base = episode_basename(title)
    root = Path(out_dir)
    return root / f"{base}.mp3", root / f"{base}.md"
