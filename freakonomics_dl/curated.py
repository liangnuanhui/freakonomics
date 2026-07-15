"""Parse curated / series list pages, with pagination and PLUS filtering."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag


# Anchor texts that are labels, not episode titles
_LABEL_RE = re.compile(
    r"^(PLUS|EXTRA|UPDATE|No\.\s*\d+|NO\.\s*\d+|\d+)$",
    re.I,
)


@dataclass(frozen=True)
class EpisodeRef:
    title: str
    url: str
    slug: str
    is_plus: bool = False
    labels: Tuple[str, ...] = field(default_factory=tuple)


def _slug_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    slug = path.split("/")[-1] if path else "episode"
    slug = re.sub(r"[^\w\-]+", "-", slug).strip("-").lower()
    return slug or "episode"


def _normalize_episode_url(href: str, page_url: str) -> Optional[str]:
    if not href:
        return None
    full = urljoin(page_url, href).split("#")[0].rstrip("/") + "/"
    parsed = urlparse(full)
    if parsed.netloc and "freakonomics.com" not in parsed.netloc:
        return None
    if "/podcast/" not in parsed.path:
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if parts == ["podcast"] or len(parts) < 2:
        return None
    return full


def _clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _is_label(text: str) -> bool:
    return bool(_LABEL_RE.match(text.strip()))


def _pick_title(labels: Iterable[str]) -> Optional[str]:
    """Prefer longest non-label anchor text as the episode title."""
    candidates = [t for t in labels if t and not _is_label(t) and len(t) >= 8]
    if not candidates:
        # fall back to any non-empty long-ish text
        candidates = [t for t in labels if t and len(t) >= 8]
    if not candidates:
        return None
    return max(candidates, key=len)


def find_full_archive_url(html: str, page_url: str) -> Optional[str]:
    """If a series page links to series-full archive, return that URL."""
    soup = BeautifulSoup(html, "lxml")
    for a in soup.find_all("a", href=True):
        href = a.get("href") or ""
        text = _clean_text(a.get_text(" ", strip=True))
        if "series-full" in href and re.search(r"full\s+archive", text, re.I):
            return urljoin(page_url, href).split("#")[0]
        if re.search(r"show\s+full\s+archive", text, re.I):
            return urljoin(page_url, href).split("#")[0]
    return None


def find_next_page_url(html: str, page_url: str) -> Optional[str]:
    """
    Find the next archive page (WordPress-style Older Posts /page/N/).
    """
    soup = BeautifulSoup(html, "lxml")
    # Prefer explicit "Older Posts"
    for a in soup.find_all("a", href=True):
        text = _clean_text(a.get_text(" ", strip=True))
        if re.fullmatch(r"Older\s+Posts", text, re.I):
            return urljoin(page_url, a["href"]).split("#")[0]
    # Fallback: rel=next
    a = soup.find("a", rel=lambda v: v and "next" in v)
    if a and a.get("href"):
        return urljoin(page_url, a["href"]).split("#")[0]
    # Fallback: link with /page/N+1 if current is /page/N
    m = re.search(r"/page/(\d+)/?$", urlparse(page_url).path)
    if m:
        n = int(m.group(1)) + 1
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if re.search(rf"/page/{n}/?$", href):
                return urljoin(page_url, href).split("#")[0]
    else:
        # on page 1, look for /page/2/
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if re.search(r"/page/2/?$", href) and "series" in href:
                return urljoin(page_url, href).split("#")[0]
    return None


def parse_list_page(
    html: str,
    page_url: str,
    *,
    skip_plus: bool = True,
) -> List[EpisodeRef]:
    """
    Extract episode refs from one list/archive/curated page.

    - Title = best non-label anchor text for each /podcast/ URL
    - is_plus if any anchor text for that URL is exactly PLUS
    - EXTRA is treated as a normal episode (only PLUS is special)
    """
    soup = BeautifulSoup(html, "lxml")
    by_url: dict[str, Set[str]] = {}

    for a in soup.select('a[href*="/podcast/"]'):
        if not isinstance(a, Tag):
            continue
        full = _normalize_episode_url(a.get("href") or "", page_url)
        if not full:
            continue
        text = _clean_text(a.get_text(" ", strip=True))
        if not text:
            continue
        by_url.setdefault(full, set()).add(text)

    episodes: List[EpisodeRef] = []
    for url, labels in by_url.items():
        label_list = tuple(sorted(labels, key=lambda s: (-len(s), s)))
        is_plus = any(t.strip().upper() == "PLUS" for t in labels)
        if skip_plus and is_plus:
            continue
        title = _pick_title(labels)
        if not title:
            continue
        episodes.append(
            EpisodeRef(
                title=title,
                url=url,
                slug=_slug_from_url(url),
                is_plus=is_plus,
                labels=label_list,
            )
        )

    # Stable order: as first appearance in document of the title link
    order: dict[str, int] = {}
    i = 0
    for a in soup.select('a[href*="/podcast/"]'):
        full = _normalize_episode_url(a.get("href") or "", page_url)
        if full and full not in order:
            order[full] = i
            i += 1
    episodes.sort(key=lambda e: order.get(e.url, 10**9))
    return episodes


# Back-compat alias used by older call sites
def parse_curated_page(html: str, page_url: str) -> List[EpisodeRef]:
    return parse_list_page(html, page_url, skip_plus=True)
