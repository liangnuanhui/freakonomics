"""Orchestrate curated-page → episode audio/transcript downloads."""

from __future__ import annotations

import re
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional

from .curated import EpisodeRef, parse_curated_page
from .episode import parse_episode_page, render_transcript_markdown
from .http_client import HttpClient
from .progress import ProgressStore, save_episodes_json


def _safe_filename(name: str, ext: str) -> str:
    base = re.sub(r"[^\w\s\-]+", "", name, flags=re.UNICODE).strip()
    base = re.sub(r"\s+", "-", base)
    base = base[:80].strip("-") or "episode"
    if not ext.startswith("."):
        ext = f".{ext}"
    return f"{base}{ext}"


class CuratedDownloader:
    def __init__(
        self,
        list_url: str,
        out_dir: Path,
        *,
        want_audio: bool = True,
        want_transcript: bool = True,
        min_transcript_chars: int = 500,
        delay: float = 1.5,
        limit: Optional[int] = None,
        force: bool = False,
    ):
        if not want_audio and not want_transcript:
            raise ValueError("At least one of audio or transcript must be enabled")

        self.list_url = list_url
        self.out_dir = Path(out_dir)
        self.want_audio = want_audio
        self.want_transcript = want_transcript
        self.min_transcript_chars = min_transcript_chars
        self.limit = limit
        self.force = force

        self.audio_dir = self.out_dir / "audio"
        self.transcript_dir = self.out_dir / "transcripts"
        self.out_dir.mkdir(parents=True, exist_ok=True)
        if want_audio:
            self.audio_dir.mkdir(parents=True, exist_ok=True)
        if want_transcript:
            self.transcript_dir.mkdir(parents=True, exist_ok=True)

        self.http = HttpClient(min_interval=delay)
        self.progress = ProgressStore(self.out_dir)

    def fetch_episode_list(self) -> List[EpisodeRef]:
        print(f"📄 Fetching list page:\n   {self.list_url}")
        html = self.http.get_text(self.list_url)
        episodes = parse_curated_page(html, self.list_url)
        if self.limit is not None:
            episodes = episodes[: self.limit]

        save_episodes_json(
            self.out_dir / "episodes.json",
            self.list_url,
            [asdict(e) for e in episodes],
        )
        print(f"✓ Found {len(episodes)} episode link(s)")
        return episodes

    def _audio_path(self, slug: str, preferred_name: Optional[str]) -> Path:
        if preferred_name:
            name = Path(preferred_name).name
            if not name.lower().endswith(".mp3"):
                name = f"{name}.mp3"
            # keep host-provided name but prefix slug for uniqueness
            stem = Path(name).stem
            return self.audio_dir / f"{slug}--{stem}.mp3"
        return self.audio_dir / f"{slug}.mp3"

    def _transcript_path(self, slug: str) -> Path:
        return self.transcript_dir / f"{slug}.md"

    def _assets_present(self, slug: str, audio_name: Optional[str] = None) -> bool:
        ok = True
        if self.want_audio:
            # any matching slug audio counts
            matches = list(self.audio_dir.glob(f"{slug}*.mp3"))
            ok = ok and bool(matches)
        if self.want_transcript:
            ok = ok and self._transcript_path(slug).exists()
        return ok

    def download_one(self, ep: EpisodeRef) -> bool:
        slug = ep.slug
        print(f"\n→ {ep.title}")
        print(f"  {ep.url}")

        if not self.force and (
            self.progress.is_completed(slug) or self._assets_present(slug)
        ):
            print("  ✓ skip (already present)")
            self.progress.mark_completed(slug)
            return True

        try:
            html = self.http.get_text(ep.url, referer=self.list_url)
            content = parse_episode_page(html, ep.url, fallback_title=ep.title)

            if self.want_transcript:
                if (
                    not content.transcript
                    or content.transcript_chars < self.min_transcript_chars
                ):
                    raise RuntimeError(
                        f"transcript missing or too short "
                        f"({content.transcript_chars} chars)"
                    )
                md_path = self._transcript_path(slug)
                md_path.write_text(
                    render_transcript_markdown(content), encoding="utf-8"
                )
                print(f"  ✓ transcript ({content.transcript_chars} chars) → {md_path.name}")

            if self.want_audio:
                if not content.audio_url:
                    raise RuntimeError("no audio URL found on episode page")
                audio_path = self._audio_path(slug, content.audio_filename)
                if audio_path.exists() and not self.force:
                    print(f"  ✓ audio exists → {audio_path.name}")
                else:
                    print(f"  ⬇ audio …")
                    nbytes = self.http.download_file(
                        content.audio_url,
                        audio_path,
                        referer=ep.url,
                    )
                    mb = nbytes / (1024 * 1024)
                    print(f"  ✓ audio {mb:.1f} MB → {audio_path.name}")

            self.progress.mark_completed(slug)
            return True

        except Exception as e:
            reason = str(e)[:200]
            print(f"  ✗ {reason}")
            self.progress.mark_failed(slug, reason)
            # clean partial empty files? leave for inspection
            return False

    def run(self) -> int:
        print("=" * 60)
        print("Freakonomics curated downloader (HTTP)")
        print("=" * 60)
        print(f"out: {self.out_dir.resolve()}")
        print(f"audio={self.want_audio}  transcript={self.want_transcript}")

        episodes = self.fetch_episode_list()
        if not episodes:
            print("❌ No episodes found on list page")
            return 1

        if self.force:
            pending = list(episodes)
        else:
            pending = [
                ep
                for ep in episodes
                if not (
                    self.progress.is_completed(ep.slug) or self._assets_present(ep.slug)
                )
            ]

        print(f"\n📊 total={len(episodes)}  to_process={len(pending)}")
        ok = 0
        fail = 0
        try:
            for i, ep in enumerate(pending, 1):
                print(f"\n[{i}/{len(pending)}]", end="")
                if self.download_one(ep):
                    ok += 1
                else:
                    fail += 1
                if i % 5 == 0:
                    self.progress.save()
        except KeyboardInterrupt:
            print("\n\n⚠️  interrupted")
        finally:
            self.progress.save()

        print("\n" + "=" * 60)
        print(f"done  ok={ok}  fail={fail}")
        print(f"files: {self.out_dir.resolve()}")
        print("=" * 60)
        return 0 if fail == 0 else 2
