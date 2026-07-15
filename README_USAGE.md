# 使用指南：`freakonomics_dl`

HTTP 精选页下载器的详细说明。总览见 [README.md](./README.md)。

## 安装与运行

```bash
poetry install
poetry run python -m freakonomics_dl --help
```

默认列表页：

`https://freakonomics.com/get-started-with-freakonomics-radio-our-most-downloaded-episodes/`

## 端到端流程

1. GET `--from-page` → `parse_curated_page` 收集 `/podcast/` 链接  
2. 写入 `episodes.json`  
3. 对每集 GET 单集页 → 抽 `audio[src]` 与 Episode Transcript  
4. 流式写 `<集名>.mp3`，Markdown 写同目录 `<集名>.md`  
5. 更新 `progress.json`（支持中断续跑）；429/5xx/网络错误自动退避重试

## 进度文件

`progress.json` 示例：

```json
{
  "completed": ["air-travel-is-a-miracle-why-do-we-hate-it"],
  "failed": {
    "some-slug": "transcript missing or too short (0 chars)"
  },
  "last_updated": "2026-07-15T16:00:00+08:00"
}
```

- 已在 `completed` 或磁盘上已有对应资源 → 跳过  
- `--force` 忽略上述检查并重下  

## 换一张精选页

任何包含剧集链接的 freakonomics 文章页均可：

```bash
poetry run python -m freakonomics_dl \
  --from-page "https://freakonomics.com/some-other-roundup/" \
  --out downloads/other-roundup
```

解析规则：`a[href*="/podcast/"]`，主机为 freakonomics.com，标题长度 ≥ 8，按 URL 去重。

## 故障排查

| 现象 | 处理 |
|------|------|
| `No episodes found` | 检查 URL；页面是否仍含 `/podcast/` 链接 |
| `no audio URL` | 该集页结构变化；打开单集页查看是否有 `<audio>` |
| `transcript … too short` | 可能无文稿或选择器失效 |
| 403 / 连接重置 | 增大 `--delay`；稍后重试；必要时再考虑浏览器兜底 |
| 磁盘暴涨 | 使用 `--no-audio` 或 `--limit` |

## 与 `simple_downloader.py` 的区别

| | `freakonomics_dl` | `simple_downloader.py` |
|--|-------------------|------------------------|
| 协议 | HTTP | Playwright 浏览器 |
| 列表 | 任意精选/文章页 | 固定 NSQ series-full |
| 音频 | 支持 | 否 |
| 文稿 | 支持 | 支持 |
| 状态 | **推荐** | 遗留 |
