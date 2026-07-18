"""Download podcast audio (and optional description markdown) from an RSS feed."""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path
from typing import List, Optional

from .http_client import HttpClient, format_bytes, print_download_progress
from .names import episode_basename
from .progress import ProgressStore, save_episodes_json
from .rss import RssEpisode, display_title, parse_rss_feed


def rss_basename(ep: RssEpisode) -> str:
    """
    Build output basename.

    Prefer \"{episode_num}-{title}\" when itunes/title episode number exists
    (matches the older NSQ downloader convention); otherwise title-only.
    """
    title = display_title(ep)
    base = episode_basename(title)
    if ep.episode_num is not None:
        return f"{ep.episode_num}-{base}"
    return base


def render_rss_description_markdown(ep: RssEpisode) -> str:
    """Lightweight markdown from RSS description (not a full website transcript)."""
    lines = [
        f"# {ep.title}",
        "",
        f"- **Source:** RSS",
        f"- **GUID:** {ep.guid}",
    ]
    if ep.episode_num is not None:
        lines.append(f"- **Episode:** {ep.episode_num}")
    if ep.pub_date:
        lines.append(f"- **Published:** {ep.pub_date}")
    if ep.duration:
        lines.append(f"- **Duration:** {ep.duration}")
    if ep.link:
        lines.append(f"- **Link:** {ep.link}")
    if ep.audio_url:
        lines.append(f"- **Audio:** {ep.audio_url}")
    lines.append("")
    lines.append("## Description")
    lines.append("")
    lines.append(ep.description or "_(no description in feed)_")
    lines.append("")
    return "\n".join(lines)


class RssDownloader:
    """
    HTTP-only RSS audio downloader.

    Reuses HttpClient + ProgressStore so resume behaviour matches the
    curated website path. Transcripts from RSS are **show notes / description**
    only — not full site transcripts.
    """

    def __init__(
        self,
        feed_url: str,
        out_dir: Path,
        *,
        want_audio: bool = True,
        want_description: bool = False,
        delay: float = 1.5,
        limit: Optional[int] = None,
        force: bool = False,
        max_retries: int = 5,
    ):
        if not want_audio and not want_description:
            raise ValueError("At least one of audio or description must be enabled")

        self.feed_url = feed_url
        self.out_dir = Path(out_dir)
        self.want_audio = want_audio
        self.want_description = want_description
        self.limit = limit
        self.force = force
        self.max_retries = max_retries

        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.http = HttpClient(min_interval=delay, max_retries=max_retries)
        self.progress = ProgressStore(self.out_dir)

    def _paths_for(self, ep: RssEpisode) -> tuple[Path, Path]:
        base = rss_basename(ep)
        return self.out_dir / f"{base}.mp3", self.out_dir / f"{base}.md"

    def _assets_present(self, ep: RssEpisode) -> bool:
        mp3, md = self._paths_for(ep)
        ok = True
        if self.want_audio:
            ok = ok and mp3.is_file() and mp3.stat().st_size > 0
        if self.want_description:
            ok = ok and md.is_file() and md.stat().st_size > 0
        return ok

    def fetch_episodes(self) -> List[RssEpisode]:
        print(f"[rss] fetch  {self.feed_url}", flush=True)
        t0 = time.monotonic()
        xml_text = self.http.get_text(self.feed_url, label="rss feed")
        episodes = parse_rss_feed(xml_text)
        if self.limit is not None:
            episodes = episodes[: self.limit]

        save_episodes_json(
            self.out_dir / "episodes.json",
            self.feed_url,
            [
                {
                    **ep.to_dict(),
                    "basename": rss_basename(ep),
                }
                for ep in episodes
            ],
        )
        dt = time.monotonic() - t0
        with_audio = sum(1 for e in episodes if e.audio_url)
        print(
            f"[rss] OK  {len(episodes)} episode(s) "
            f"({with_audio} with enclosure) in {dt:.1f}s",
            flush=True,
        )
        return episodes

    def download_one(self, ep: RssEpisode, index: int, total: int) -> bool:
        basename = rss_basename(ep)
        mp3_path, md_path = self._paths_for(ep)
        tag = f"[{index}/{total}]"
        slug = ep.slug

        print(f"\n{tag} {ep.title}", flush=True)
        if ep.episode_num is not None:
            print(f"      ep#:  {ep.episode_num}", flush=True)
        print(f"      name: {basename}.{{mp3,md}}", flush=True)

        if not self.force and (
            self.progress.is_completed(slug) or self._assets_present(ep)
        ):
            print(f"{tag} status: SKIP (already complete)", flush=True)
            self.progress.mark_completed(slug, title=ep.title, basename=basename)
            return True

        try:
            if self.want_description:
                print(f"{tag} status: WRITE description…", flush=True)
                md_path.write_text(
                    render_rss_description_markdown(ep), encoding="utf-8"
                )
                print(f"{tag} status: DESCRIPTION OK → {md_path.name}", flush=True)

            if self.want_audio:
                if not ep.audio_url:
                    raise RuntimeError("no audio enclosure URL in RSS item")
                if mp3_path.exists() and mp3_path.stat().st_size > 0 and not self.force:
                    # Optional size check against enclosure length
                    if ep.audio_length > 0 and mp3_path.stat().st_size < ep.audio_length * 0.98:
                        print(
                            f"{tag} status: AUDIO incomplete on disk, re-download…",
                            flush=True,
                        )
                    else:
                        print(
                            f"{tag} status: AUDIO SKIP exists → {mp3_path.name}",
                            flush=True,
                        )
                        self.progress.mark_completed(
                            slug, title=ep.title, basename=basename
                        )
                        print(f"{tag} status: DONE", flush=True)
                        return True

                # Avoid collisions when titles clash
                if (
                    mp3_path.exists()
                    and self.force is False
                    and not self.progress.is_completed(slug)
                ):
                    # different guid, same name — suffix short guid
                    short = re.sub(r"\W+", "", ep.guid)[:8] or str(index)
                    mp3_path = self.out_dir / f"{basename}_{short}.mp3"
                    md_path = self.out_dir / f"{basename}_{short}.md"
                    basename = mp3_path.stem
                    print(f"{tag} name:  collision → {basename}", flush=True)

                print(f"{tag} status: DOWNLOAD audio…", flush=True)
                nbytes = self.http.download_file(
                    ep.audio_url,
                    mp3_path,
                    referer=self.feed_url,
                    label=f"audio {index}",
                    on_progress=print_download_progress,
                )
                sys.stdout.write("\n")
                sys.stdout.flush()
                print(
                    f"{tag} status: AUDIO OK "
                    f"({format_bytes(nbytes)}) → {mp3_path.name}",
                    flush=True,
                )

            self.progress.mark_completed(slug, title=ep.title, basename=basename)
            print(f"{tag} status: DONE", flush=True)
            return True

        except Exception as e:
            reason = str(e)[:240]
            print(f"{tag} status: FAIL  {reason}", flush=True)
            self.progress.mark_failed(slug, reason, title=ep.title, basename=basename)
            return False

    def run(self) -> int:
        print("=" * 64, flush=True)
        print(" Freakonomics downloader (RSS)", flush=True)
        print("=" * 64, flush=True)
        print(f" feed:       {self.feed_url}", flush=True)
        print(f" out:        {self.out_dir.resolve()}", flush=True)
        print(
            f" assets:     audio={'on' if self.want_audio else 'off'}  "
            f"description={'on' if self.want_description else 'off'}",
            flush=True,
        )
        print(
            f" throttle:   delay={self.http.min_interval}s  "
            f"retries={self.max_retries}",
            flush=True,
        )
        print(
            f" layout:     [N-]{{title}}.mp3  (+ optional .md from RSS notes)",
            flush=True,
        )
        print("=" * 64, flush=True)

        try:
            episodes = self.fetch_episodes()
        except Exception as e:
            print(f"[rss] FAIL  {e}", flush=True)
            return 1

        if not episodes:
            print("[rss] FAIL  no episodes in feed", flush=True)
            return 1

        if self.force:
            pending = list(episodes)
        else:
            pending = [
                ep
                for ep in episodes
                if not (
                    self.progress.is_completed(ep.slug) or self._assets_present(ep)
                )
            ]

        skipped = len(episodes) - len(pending)
        print(
            f"\n[plan] total={len(episodes)}  pending={len(pending)}  "
            f"skip={skipped}",
            flush=True,
        )
        if not pending:
            print("[plan] nothing to do — all complete", flush=True)
            return 0

        ok = 0
        fail = 0
        t_run = time.monotonic()
        try:
            for i, ep in enumerate(pending, 1):
                if self.download_one(ep, i, len(pending)):
                    ok += 1
                else:
                    fail += 1
                self.progress.save()
                elapsed = time.monotonic() - t_run
                print(
                    f"[progress] completed={ok}  failed={fail}  "
                    f"left={len(pending) - i}  elapsed={elapsed:.0f}s",
                    flush=True,
                )
        except KeyboardInterrupt:
            print("\n[run] INTERRUPTED by user — progress saved", flush=True)
        finally:
            self.progress.save()

        elapsed = time.monotonic() - t_run
        print("\n" + "=" * 64, flush=True)
        print(
            f" finished  ok={ok}  fail={fail}  elapsed={elapsed:.0f}s",
            flush=True,
        )
        print(f" output    {self.out_dir.resolve()}", flush=True)
        if fail:
            print(" failed:   see progress.json → failed", flush=True)
        print("=" * 64, flush=True)
        return 0 if fail == 0 else 2
