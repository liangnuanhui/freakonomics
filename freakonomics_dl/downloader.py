"""Orchestrate curated-page → episode audio/transcript downloads."""

from __future__ import annotations

import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional

from .curated import EpisodeRef, parse_curated_page
from .episode import parse_episode_page, render_transcript_markdown
from .http_client import HttpClient, format_bytes, print_download_progress
from .names import episode_basename, episode_paths
from .progress import ProgressStore, save_episodes_json


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
        max_retries: int = 5,
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
        self.max_retries = max_retries

        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.http = HttpClient(min_interval=delay, max_retries=max_retries)
        self.progress = ProgressStore(self.out_dir)

    def _paths_for(self, title: str):
        return episode_paths(self.out_dir, title)

    def _assets_present(self, title: str) -> bool:
        mp3, md = self._paths_for(title)
        ok = True
        if self.want_audio:
            ok = ok and mp3.is_file() and mp3.stat().st_size > 0
        if self.want_transcript:
            ok = ok and md.is_file() and md.stat().st_size > 0
        return ok

    def fetch_episode_list(self) -> List[EpisodeRef]:
        print(f"[list] GET {self.list_url}", flush=True)
        t0 = time.monotonic()
        html = self.http.get_text(self.list_url, label="list page")
        episodes = parse_curated_page(html, self.list_url)
        if self.limit is not None:
            episodes = episodes[: self.limit]

        save_episodes_json(
            self.out_dir / "episodes.json",
            self.list_url,
            [
                {
                    **asdict(e),
                    "basename": episode_basename(e.title),
                }
                for e in episodes
            ],
        )
        dt = time.monotonic() - t0
        print(f"[list] OK  found {len(episodes)} episode(s) in {dt:.1f}s", flush=True)
        return episodes

    def download_one(self, ep: EpisodeRef, index: int, total: int) -> bool:
        title = ep.title
        basename = episode_basename(title)
        mp3_path, md_path = self._paths_for(title)
        tag = f"[{index}/{total}]"

        print(f"\n{tag} {title}", flush=True)
        print(f"      url:  {ep.url}", flush=True)
        print(f"      name: {basename}.{{mp3,md}}", flush=True)

        if not self.force and (
            self.progress.is_completed(ep.slug) or self._assets_present(title)
        ):
            print(f"{tag} status: SKIP (already complete)", flush=True)
            self.progress.mark_completed(ep.slug, title=title, basename=basename)
            return True

        try:
            print(f"{tag} status: FETCH page…", flush=True)
            html = self.http.get_text(
                ep.url, referer=self.list_url, label=f"episode {index}"
            )
            content = parse_episode_page(html, ep.url, fallback_title=title)
            # prefer page h1 for final filenames when richer
            final_title = content.title or title
            basename = episode_basename(final_title)
            mp3_path, md_path = self._paths_for(final_title)
            if final_title != title:
                print(f"{tag} title: {final_title}", flush=True)
                print(f"{tag} name:  {basename}.{{mp3,md}}", flush=True)

            if self.want_transcript:
                if (
                    not content.transcript
                    or content.transcript_chars < self.min_transcript_chars
                ):
                    raise RuntimeError(
                        f"transcript missing or too short "
                        f"({content.transcript_chars} chars)"
                    )
                print(f"{tag} status: WRITE transcript…", flush=True)
                md_path.write_text(
                    render_transcript_markdown(content), encoding="utf-8"
                )
                print(
                    f"{tag} status: TRANSCRIPT OK "
                    f"({content.transcript_chars} chars) → {md_path.name}",
                    flush=True,
                )

            if self.want_audio:
                if not content.audio_url:
                    raise RuntimeError("no audio URL found on episode page")
                if mp3_path.exists() and mp3_path.stat().st_size > 0 and not self.force:
                    print(
                        f"{tag} status: AUDIO SKIP exists → {mp3_path.name}",
                        flush=True,
                    )
                else:
                    print(f"{tag} status: DOWNLOAD audio…", flush=True)
                    nbytes = self.http.download_file(
                        content.audio_url,
                        mp3_path,
                        referer=ep.url,
                        label=f"audio {index}",
                        on_progress=print_download_progress,
                    )
                    # progress bar may end without newline if Content-Length missing
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    print(
                        f"{tag} status: AUDIO OK "
                        f"({format_bytes(nbytes)}) → {mp3_path.name}",
                        flush=True,
                    )

            self.progress.mark_completed(
                ep.slug, title=final_title, basename=basename
            )
            print(f"{tag} status: DONE", flush=True)
            return True

        except Exception as e:
            reason = str(e)[:240]
            print(f"{tag} status: FAIL  {reason}", flush=True)
            self.progress.mark_failed(ep.slug, reason, title=title, basename=basename)
            return False

    def run(self) -> int:
        print("=" * 64, flush=True)
        print(" Freakonomics curated downloader (HTTP)", flush=True)
        print("=" * 64, flush=True)
        print(f" list:       {self.list_url}", flush=True)
        print(f" out:        {self.out_dir.resolve()}", flush=True)
        print(
            f" assets:     audio={'on' if self.want_audio else 'off'}  "
            f"transcript={'on' if self.want_transcript else 'off'}",
            flush=True,
        )
        print(
            f" throttle:   delay={self.http.min_interval}s  "
            f"retries={self.max_retries}",
            flush=True,
        )
        print(
            f" layout:     <title>.mp3 + <title>.md in same folder",
            flush=True,
        )
        print("=" * 64, flush=True)

        try:
            episodes = self.fetch_episode_list()
        except Exception as e:
            print(f"[list] FAIL  {e}", flush=True)
            return 1

        if not episodes:
            print("[list] FAIL  no episode links found", flush=True)
            return 1

        if self.force:
            pending = list(episodes)
        else:
            pending = [
                ep
                for ep in episodes
                if not (
                    self.progress.is_completed(ep.slug)
                    or self._assets_present(ep.title)
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
                # brief status strip
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
