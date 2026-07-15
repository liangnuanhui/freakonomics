"""Parse a single Freakonomics episode page for audio + transcript."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from bs4 import BeautifulSoup, Tag


@dataclass
class EpisodeContent:
    title: str
    url: str
    audio_url: Optional[str]
    audio_filename: Optional[str]
    transcript: Optional[str]
    transcript_chars: int


def _clean_title(soup: BeautifulSoup, fallback: str) -> str:
    h1 = soup.find("h1")
    if h1:
        text = h1.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            return text
    return fallback


def extract_audio(soup: BeautifulSoup) -> tuple[Optional[str], Optional[str]]:
    audio = soup.find("audio")
    if not audio:
        # fallback: any .mp3 link in page
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if ".mp3" in href.lower():
                return href, a.get_text(strip=True) or None
        html = str(soup)
        m = re.search(r'https?://[^\s\"\']+\.mp3[^\s\"\']*', html, re.I)
        return (m.group(0) if m else None), None

    src = audio.get("src") or audio.get("data-src")
    if not src:
        source = audio.find("source")
        if source:
            src = source.get("src")
    filename = audio.get("data-filename")
    return src, filename


def extract_transcript(soup: BeautifulSoup) -> Optional[str]:
    heading = soup.find(["h2", "h3"], string=re.compile(r"Episode Transcript", re.I))
    if not heading:
        # sometimes the heading text is nested
        for tag in soup.find_all(["h2", "h3"]):
            if re.search(r"Episode Transcript", tag.get_text(" ", strip=True), re.I):
                heading = tag
                break
    if not heading:
        return None

    parent = heading.find_parent(["article", "div", "section"])
    if not parent:
        parent = heading.parent
    if not parent:
        return None

    lines: list[str] = []
    for elem in parent.find_all(["p", "blockquote", "h2", "h3"]):
        if not isinstance(elem, Tag):
            continue
        text = elem.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text).strip()
        if not text or text == "Read full Transcript":
            continue
        if re.match(r"^Episode Transcript$", text, re.I):
            continue
        if text.startswith("Sources") or text.startswith("Resources"):
            break

        if elem.name == "blockquote":
            lines.append(f"> {text}\n")
        elif elem.name in ("h2", "h3"):
            lines.append(f"\n## {text}\n")
        else:
            lines.append(f"{text}\n")

    body = "\n".join(lines).strip()
    return body or None


def parse_episode_page(html: str, url: str, fallback_title: str = "") -> EpisodeContent:
    soup = BeautifulSoup(html, "lxml")
    title = _clean_title(soup, fallback_title or "Untitled Episode")
    audio_url, audio_filename = extract_audio(soup)
    transcript = extract_transcript(soup)
    return EpisodeContent(
        title=title,
        url=url,
        audio_url=audio_url,
        audio_filename=audio_filename,
        transcript=transcript,
        transcript_chars=len(transcript) if transcript else 0,
    )


def render_transcript_markdown(content: EpisodeContent) -> str:
    parts = [
        f"# {content.title}\n",
        f"**URL:** {content.url}\n",
        "---\n",
    ]
    if content.transcript:
        parts.append(content.transcript)
        if not content.transcript.endswith("\n"):
            parts.append("\n")
    return "\n".join(parts)
