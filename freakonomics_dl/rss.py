"""Parse podcast RSS/Atom feeds into episode records."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional
from urllib.parse import unquote

ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"

# Common podcast RSS feeds used with this tool
DEFAULT_NSQ_RSS = "https://feeds.simplecast.com/dfh_verV"

_NS = {
    "itunes": ITUNES_NS,
    "content": CONTENT_NS,
    "atom": "http://www.w3.org/2005/Atom",
}


@dataclass
class RssEpisode:
    """One episode from a podcast RSS feed."""

    guid: str
    title: str
    audio_url: Optional[str]
    audio_length: int = 0
    episode_num: Optional[int] = None
    description: str = ""
    pub_date: str = ""
    duration: str = ""
    link: str = ""

    @property
    def slug(self) -> str:
        """Stable id for progress.json (prefer GUID)."""
        if self.guid:
            # Keep filesystem/json friendly
            return re.sub(r"[^\w.\-]+", "_", self.guid)[:120]
        base = re.sub(r"\W+", "-", (self.title or "episode").lower()).strip("-")
        return (base or "episode")[:80]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["slug"] = self.slug
        return d


def _text(elem: Optional[ET.Element]) -> str:
    if elem is None or elem.text is None:
        return ""
    return elem.text.strip()


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _episode_num_from_title(title: str) -> Optional[int]:
    # "58. Title" / "No. 58: Title" / "No 58 Title"
    match = re.search(r"^(?:No\.?\s*)?(\d+)[\.:\s]", title, re.IGNORECASE)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def parse_rss_item(item: ET.Element) -> Optional[RssEpisode]:
    """Parse a single <item> into RssEpisode."""
    title = _text(item.find("title")) or "Unknown"

    guid = _text(item.find("guid"))
    if not guid:
        guid = f"generated_{abs(hash(title)) % 10_000_000}"

    episode_num: Optional[int] = None
    ep_elem = item.find("itunes:episode", _NS)
    if ep_elem is not None and ep_elem.text:
        try:
            episode_num = int(ep_elem.text.strip())
        except ValueError:
            episode_num = None
    if episode_num is None:
        episode_num = _episode_num_from_title(title)

    audio_url: Optional[str] = None
    audio_length = 0
    enclosure = item.find("enclosure")
    if enclosure is not None:
        raw_url = enclosure.get("url")
        if raw_url:
            audio_url = unquote(raw_url.strip())
        length_attr = enclosure.get("length")
        if length_attr:
            try:
                audio_length = int(length_attr)
            except ValueError:
                audio_length = 0

    description = _strip_html(_text(item.find("description")))
    if not description:
        content = item.find("content:encoded", _NS)
        if content is not None and content.text:
            description = _strip_html(content.text)

    pub_date = _text(item.find("pubDate"))
    duration = _text(item.find("itunes:duration", _NS))
    link = _text(item.find("link"))

    return RssEpisode(
        guid=guid,
        title=title,
        audio_url=audio_url,
        audio_length=audio_length,
        episode_num=episode_num,
        description=description,
        pub_date=pub_date,
        duration=duration,
        link=link,
    )


def parse_rss_feed(rss_xml: str) -> List[RssEpisode]:
    """
    Parse RSS 2.0 podcast XML into episodes (channel/item list).

    Returns episodes in feed order (typically newest first).
    """
    try:
        root = ET.fromstring(rss_xml)
    except ET.ParseError as e:
        raise ValueError(f"invalid RSS XML: {e}") from e

    # RSS 2.0
    channel = root.find("channel")
    if channel is not None:
        items = channel.findall("item")
        episodes: List[RssEpisode] = []
        for item in items:
            ep = parse_rss_item(item)
            if ep is not None:
                episodes.append(ep)
        return episodes

    # Minimal Atom support (entry/link rel=enclosure)
    if root.tag.endswith("feed"):
        return _parse_atom_feed(root)

    raise ValueError("RSS format error: no <channel> (or Atom <feed>) found")


def _parse_atom_feed(root: ET.Element) -> List[RssEpisode]:
    episodes: List[RssEpisode] = []
    # Handle default namespace
    ns = {"a": "http://www.w3.org/2005/Atom"}
    entries = root.findall("a:entry", ns) or root.findall("entry")
    for entry in entries:
        title = _text(entry.find("a:title", ns) or entry.find("title")) or "Unknown"
        guid = _text(entry.find("a:id", ns) or entry.find("id")) or title
        audio_url = None
        audio_length = 0
        for link in entry.findall("a:link", ns) or entry.findall("link"):
            rel = (link.get("rel") or "").lower()
            href = link.get("href") or ""
            typ = (link.get("type") or "").lower()
            if rel == "enclosure" or typ.startswith("audio/"):
                audio_url = unquote(href)
                try:
                    audio_length = int(link.get("length") or 0)
                except ValueError:
                    audio_length = 0
                break
        summary = _strip_html(
            _text(entry.find("a:summary", ns) or entry.find("summary"))
        )
        pub = _text(
            entry.find("a:published", ns)
            or entry.find("published")
            or entry.find("a:updated", ns)
            or entry.find("updated")
        )
        link_el = entry.find("a:link[@rel='alternate']", ns)
        if link_el is None:
            for link in entry.findall("a:link", ns) or entry.findall("link"):
                if (link.get("rel") or "alternate") == "alternate" and link.get("href"):
                    link_el = link
                    break
        page_link = (link_el.get("href") if link_el is not None else "") or ""
        episodes.append(
            RssEpisode(
                guid=guid,
                title=title,
                audio_url=audio_url,
                audio_length=audio_length,
                episode_num=_episode_num_from_title(title),
                description=summary,
                pub_date=pub,
                duration="",
                link=page_link,
            )
        )
    return episodes


def display_title(ep: RssEpisode) -> str:
    """
    Title used for filenames.

    Strips a leading \"N. \" prefix when episode_num is known so we can
    prefer \"{num}-{clean_title}\" naming.
    """
    title = ep.title or "Unknown"
    if ep.episode_num is not None:
        title = re.sub(r"^(\d+)\.\s*", "", title)
    return title.strip() or "Unknown"
