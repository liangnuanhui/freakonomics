"""Orchestrate list/series pages → episode audio/transcript downloads."""

from __future__ import annotations

import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional

from .curated import (
    EpisodeRef,
    find_full_archive_url,
    find_next_page_url,
    parse_list_page,
)
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
        skip_plus: bool = True,
        follow_full_archive: bool = True,
        max_pages: int = 200,
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
        self.skip_plus = skip_plus
        self.follow_full_archive = follow_full_archive
        self.max_pages = max_pages

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
        """
        Fetch list URL, optionally jump to series-full archive, then follow
        Older Posts pagination. PLUS episodes are skipped when skip_plus=True.
        EXTRA is kept as a normal episode.
        """
        start_url = self.list_url
        print(f"[list] start  {start_url}", flush=True)
        t0 = time.monotonic()

        html = self.http.get_text(start_url, label="list page 1")
        list_url = start_url

        if self.follow_full_archive:
            full = find_full_archive_url(html, start_url)
            if full and full.rstrip("/") != start_url.rstrip("/"):
                print(f"[list] follow full archive → {full}", flush=True)
                list_url = full
                html = self.http.get_text(list_url, label="full archive page 1")

        all_eps: List[EpisodeRef] = []
        seen_urls: set[str] = set()
        seen_pages: set[str] = set()
        page_url = list_url
        page_num = 0
        skipped_plus_total = 0

        while page_url and page_num < self.max_pages:
            page_key = page_url.rstrip("/")
            if page_key in seen_pages:
                print(f"[list] stop  pagination loop detected at {page_url}", flush=True)
                break
            seen_pages.add(page_key)
            page_num += 1

            if page_num > 1:
                print(f"[list] page {page_num}  GET {page_url}", flush=True)
                html = self.http.get_text(
                    page_url, referer=list_url, label=f"list page {page_num}"
                )
            else:
                print(f"[list] page {page_num}  {page_url}", flush=True)

            # Count PLUS before filtering for stats
            raw_including_plus = parse_list_page(
                html, page_url, skip_plus=False
            )
            page_plus = sum(1 for e in raw_including_plus if e.is_plus)
            skipped_plus_total += page_plus if self.skip_plus else 0

            page_eps = parse_list_page(
                html, page_url, skip_plus=self.skip_plus
            )
            new = 0
            for ep in page_eps:
                key = ep.url.rstrip("/")
                if key in seen_urls:
                    continue
                seen_urls.add(key)
                all_eps.append(ep)
                new += 1
                if self.limit is not None and len(all_eps) >= self.limit:
                    break

            print(
                f"[list] page {page_num}  +{new} new  "
                f"(page total {len(page_eps)}"
                f"{f', plus skipped {page_plus}' if self.skip_plus and page_plus else ''}"
                f")  cumulative={len(all_eps)}",
                flush=True,
            )

            if self.limit is not None and len(all_eps) >= self.limit:
                print(f"[list] stop  reached --limit {self.limit}", flush=True)
                break

            next_url = find_next_page_url(html, page_url)
            if not next_url or next_url.rstrip("/") == page_url.rstrip("/"):
                print(f"[list] stop  no more pages", flush=True)
                break
            page_url = next_url

        if page_num >= self.max_pages:
            print(f"[list] stop  hit --max-pages {self.max_pages}", flush=True)

        if self.limit is not None:
            all_eps = all_eps[: self.limit]

        save_episodes_json(
            self.out_dir / "episodes.json",
            list_url,
            [
                {
                    **asdict(e),
                    "basename": episode_basename(e.title),
                }
                for e in all_eps
            ],
        )
        dt = time.monotonic() - t0
        print(
            f"[list] OK  {len(all_eps)} episode(s) from {page_num} page(s) "
            f"in {dt:.1f}s"
            + (
                f"  (skipped PLUS: {skipped_plus_total})"
                if self.skip_plus
                else ""
            ),
            flush=True,
        )
        return all_eps

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

    def run(self, episodes: Optional[List[EpisodeRef]] = None) -> int:
        print("=" * 64, flush=True)
        print(" Freakonomics downloader (HTTP)", flush=True)
        print("=" * 64, flush=True)
        print(f" list:       {self.list_url}", flush=True)
        print(f" out:        {self.out_dir.resolve()}", flush=True)
        print(
            f" assets:     audio={'on' if self.want_audio else 'off'}  "
            f"transcript={'on' if self.want_transcript else 'off'}",
            flush=True,
        )
        print(
            f" filter:     skip_plus={'on' if self.skip_plus else 'off'}  "
            f"follow_full_archive={'on' if self.follow_full_archive else 'off'}",
            flush=True,
        )
        print(
            f" throttle:   delay={self.http.min_interval}s  "
            f"retries={self.max_retries}  max_pages={self.max_pages}",
            flush=True,
        )
        print(
            f" layout:     <title>.mp3 + <title>.md in same folder",
            flush=True,
        )
        print("=" * 64, flush=True)

        if episodes is None:
            try:
                episodes = self.fetch_episode_list()
            except Exception as e:
                print(f"[list] FAIL  {e}", flush=True)
                return 1
        else:
            print(f"[list] using provided list  n={len(episodes)}", flush=True)
            save_episodes_json(
                self.out_dir / "episodes.json",
                self.list_url,
                [
                    {**asdict(e), "basename": episode_basename(e.title)}
                    for e in episodes
                ],
            )

        if not episodes:
            print("[list] FAIL  no episode links found", flush=True)
            return 1

        # apply limit only when list was auto-fetched
        if self.limit is not None and episodes is not None:
            # limit already applied in fetch; keep for safety if provided externally
            pass

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
