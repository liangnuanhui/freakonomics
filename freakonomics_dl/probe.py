"""Probe a Freakonomics URL and report whether it is scrapeable."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import urlparse

from .curated import (
    EpisodeRef,
    find_full_archive_url,
    find_next_page_url,
    parse_list_page,
    _slug_from_url,
)
from .episode import EpisodeContent, parse_episode_page
from .http_client import HttpClient


@dataclass
class ProbeResult:
    input_url: str
    ok: bool
    page_kind: str  # episode | series | series_full | curated_list | unknown
    message: str
    effective_list_url: Optional[str] = None
    full_archive_url: Optional[str] = None
    has_pagination: bool = False
    next_page_url: Optional[str] = None
    page_episode_count: int = 0
    page_plus_count: int = 0
    sample_episodes: List[EpisodeRef] = field(default_factory=list)
    episode: Optional[EpisodeContent] = None  # when page_kind == episode
    errors: List[str] = field(default_factory=list)

    @property
    def scrapeable(self) -> bool:
        return self.ok


def _classify_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/") + "/"
    if re.search(r"/podcast/[^/]+/", path):
        return "episode"
    if "/series-full/" in path:
        return "series_full"
    if re.search(r"/series/[^/]+/", path):
        return "series"
    return "curated_list"


def _normalize_user_url(raw: str) -> str:
    url = (raw or "").strip()
    if not url:
        raise ValueError("空网址")
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    return url


def probe_url(
    raw_url: str,
    http: HttpClient,
    *,
    skip_plus: bool = True,
    follow_full_archive: bool = True,
    sample_episode: bool = True,
) -> ProbeResult:
    """
    Visit URL once (or twice if following full archive) and describe structure.
    Does not paginate the whole archive — only inspects the first list page.
    """
    try:
        url = _normalize_user_url(raw_url)
    except ValueError as e:
        return ProbeResult(
            input_url=raw_url or "",
            ok=False,
            page_kind="unknown",
            message=str(e),
            errors=[str(e)],
        )

    kind = _classify_url(url)
    errors: List[str] = []

    try:
        html = http.get_text(url, label="probe")
    except Exception as e:
        return ProbeResult(
            input_url=url,
            ok=False,
            page_kind=kind,
            message=f"无法访问页面: {e}",
            errors=[str(e)],
        )

    # Single episode page
    if kind == "episode":
        content = parse_episode_page(html, url)
        has_audio = bool(content.audio_url)
        has_tr = bool(content.transcript and content.transcript_chars >= 500)
        ok = has_audio or has_tr
        parts = []
        parts.append("有音频" if has_audio else "无音频")
        parts.append(
            f"有文稿({content.transcript_chars}字)"
            if has_tr
            else f"无完整文稿({content.transcript_chars}字)"
        )
        if not ok:
            msg = "单集页可打开，但公开页未找到可用音频/文稿（可能是 PLUS 或结构变化）"
        else:
            msg = "单集页可抓取：" + "，".join(parts)
        return ProbeResult(
            input_url=url,
            ok=ok,
            page_kind="episode",
            message=msg,
            episode=content,
            sample_episodes=[
                EpisodeRef(
                    title=content.title,
                    url=url if url.endswith("/") else url + "/",
                    slug=_slug_from_url(url),
                )
            ],
            errors=errors,
        )

    # List / series pages
    effective = url
    full_archive = find_full_archive_url(html, url)
    if follow_full_archive and full_archive and full_archive.rstrip("/") != url.rstrip("/"):
        try:
            html = http.get_text(full_archive, label="probe full archive")
            effective = full_archive
            kind = "series_full" if kind == "series" else kind
        except Exception as e:
            errors.append(f"跟随 Full Archive 失败: {e}")

    all_on_page = parse_list_page(html, effective, skip_plus=False)
    kept = parse_list_page(html, effective, skip_plus=skip_plus)
    plus_count = sum(1 for e in all_on_page if e.is_plus)
    next_url = find_next_page_url(html, effective)
    has_pag = bool(next_url)

    # Optional sample of first keepable episode for audio/transcript check
    sample_ok = None
    sample_note = ""
    if sample_episode and kept:
        try:
            ep_html = http.get_text(
                kept[0].url, referer=effective, label="probe sample episode"
            )
            c = parse_episode_page(ep_html, kept[0].url, fallback_title=kept[0].title)
            ha, ht = bool(c.audio_url), bool(c.transcript and c.transcript_chars >= 500)
            sample_ok = ha or ht
            sample_note = (
                f"样例「{c.title[:50]}」→ "
                f"音频={'有' if ha else '无'}，"
                f"文稿={'有' if ht else '无'}({c.transcript_chars}字)"
            )
        except Exception as e:
            sample_note = f"样例单集探测失败: {e}"
            errors.append(sample_note)

    ok = len(kept) > 0 and (sample_ok is not False)
    if len(kept) == 0:
        msg = "未解析到可下载剧集链接"
        if plus_count:
            msg += f"（本页仅见 {plus_count} 个 PLUS，已被跳过）"
        ok = False
    else:
        msg = (
            f"列表可抓取：本页 {len(kept)} 集"
            + (f"（另跳过 PLUS {plus_count}）" if skip_plus and plus_count else "")
            + ("；可翻页" if has_pag else "；无下一页")
        )
        if sample_note:
            msg += f"。{sample_note}"

    # refine kind for non-series curated
    if kind == "curated_list" and not full_archive and not has_pag and len(kept) > 0:
        kind = "curated_list"
    elif kind == "curated_list" and full_archive:
        kind = "series"

    return ProbeResult(
        input_url=url,
        ok=ok,
        page_kind=kind,
        message=msg,
        effective_list_url=effective,
        full_archive_url=full_archive,
        has_pagination=has_pag,
        next_page_url=next_url,
        page_episode_count=len(kept),
        page_plus_count=plus_count,
        sample_episodes=kept[:5],
        errors=errors,
    )


def print_probe_report(result: ProbeResult) -> None:
    print("\n" + "-" * 64, flush=True)
    print(" [probe] 结构探测结果", flush=True)
    print("-" * 64, flush=True)
    print(f"  输入网址:   {result.input_url}", flush=True)
    print(f"  页面类型:   {result.page_kind}", flush=True)
    print(f"  可抓取:     {'是 ✓' if result.ok else '否 ✗'}", flush=True)
    if result.effective_list_url and result.effective_list_url != result.input_url:
        print(f"  实际列表:   {result.effective_list_url}", flush=True)
    if result.full_archive_url:
        print(f"  Full Archive: {result.full_archive_url}", flush=True)
    if result.page_kind != "episode":
        print(f"  本页集数:   {result.page_episode_count}（跳过 PLUS 后）", flush=True)
        print(f"  PLUS 数量:  {result.page_plus_count}", flush=True)
        print(
            f"  自动翻页:   {'是 → ' + (result.next_page_url or '') if result.has_pagination else '否'}",
            flush=True,
        )
    if result.episode:
        print(f"  标题:       {result.episode.title}", flush=True)
        print(
            f"  音频:       {'有' if result.episode.audio_url else '无'}",
            flush=True,
        )
        print(
            f"  文稿:       {result.episode.transcript_chars} 字符",
            flush=True,
        )
    if result.sample_episodes and result.page_kind != "episode":
        print("  本页样例:", flush=True)
        for i, ep in enumerate(result.sample_episodes, 1):
            print(f"    {i}. {ep.title[:70]}", flush=True)
    print(f"  说明:       {result.message}", flush=True)
    if result.errors:
        print("  警告:", flush=True)
        for e in result.errors:
            print(f"    - {e}", flush=True)
    print("-" * 64, flush=True)
