"""Parse curated list pages (e.g. most-downloaded episode roundups)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup


@dataclass(frozen=True)
class EpisodeRef:
    title: str
    url: str
    slug: str


def _slug_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    slug = path.split("/")[-1] if path else "episode"
    slug = re.sub(r"[^\w\-]+", "-", slug).strip("-").lower()
    return slug or "episode"


def parse_curated_page(html: str, page_url: str) -> List[EpisodeRef]:
    """
    Extract unique freakonomics.com /podcast/ episode links from a list/article page.
    """
    soup = BeautifulSoup(html, "lxml")
    seen: set[str] = set()
    episodes: List[EpisodeRef] = []

    for a in soup.select('a[href*="/podcast/"]'):
        href = (a.get("href") or "").strip()
        if not href:
            continue
        full = urljoin(page_url, href).split("#")[0].rstrip("/") + "/"
        parsed = urlparse(full)
        if parsed.netloc and "freakonomics.com" not in parsed.netloc:
            continue
        if "/podcast/" not in parsed.path:
            continue
        # skip index-like paths
        parts = [p for p in parsed.path.split("/") if p]
        if parts == ["podcast"] or len(parts) < 2:
            continue

        title = a.get_text(" ", strip=True)
        title = re.sub(r"\s+", " ", title).strip()
        if len(title) < 8:
            # title link may be empty; try nearby text later — skip weak anchors
            continue

        # normalize URL key without trailing slash for dedupe
        key = full.rstrip("/")
        if key in seen:
            continue
        seen.add(key)

        episodes.append(
            EpisodeRef(title=title, url=full, slug=_slug_from_url(full))
        )

    return episodes
