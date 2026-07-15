"""Progress and episode list persistence."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class ProgressStore:
    def __init__(self, out_dir: Path):
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.path = out_dir / "progress.json"
        self.data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.path.exists():
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {
            "completed": [],  # slugs
            "items": {},  # slug -> {title, basename, status, error?}
            "failed": {},  # slug -> reason (legacy + quick view)
            "last_updated": None,
        }

    def save(self) -> None:
        self.data["last_updated"] = _now_iso()
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def mark_completed(
        self,
        slug: str,
        *,
        title: Optional[str] = None,
        basename: Optional[str] = None,
    ) -> None:
        if slug not in self.data["completed"]:
            self.data["completed"].append(slug)
        self.data.setdefault("failed", {}).pop(slug, None)
        item = self.data.setdefault("items", {}).setdefault(slug, {})
        item["status"] = "completed"
        item.pop("error", None)
        if title:
            item["title"] = title
        if basename:
            item["basename"] = basename

    def mark_failed(
        self,
        slug: str,
        reason: str,
        *,
        title: Optional[str] = None,
        basename: Optional[str] = None,
    ) -> None:
        self.data.setdefault("failed", {})[slug] = reason
        if slug in self.data.get("completed", []):
            self.data["completed"].remove(slug)
        item = self.data.setdefault("items", {}).setdefault(slug, {})
        item["status"] = "failed"
        item["error"] = reason
        if title:
            item["title"] = title
        if basename:
            item["basename"] = basename

    def is_completed(self, slug: str) -> bool:
        return slug in self.data.get("completed", [])


def save_episodes_json(path: Path, page_url: str, episodes: List[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": page_url,
        "cached_at": _now_iso(),
        "count": len(episodes),
        "episodes": episodes,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
