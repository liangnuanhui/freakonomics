# Freakonomics Downloader

从 [freakonomics.com](https://freakonomics.com/) 下载播客 **音频 (mp3)** 与 **全文 transcript (Markdown)**。

**主路径：HTTP（requests + BeautifulSoup）**，无需浏览器。适合推荐页、专题页等列表页。

## 推荐用法（P0：精选推荐页）

默认目标是官方入门推荐文：

[Get Started With Freakonomics Radio: Our Most Downloaded Episodes](https://freakonomics.com/get-started-with-freakonomics-radio-our-most-downloaded-episodes/)

约 20 集：先解析文内 `/podcast/` 链接，再逐集抓音频与文稿。

### 安装

```bash
poetry install
```

### 下载（推荐页 20 集）

```bash
# 模块方式
poetry run python -m freakonomics_dl \
  --from-page "https://freakonomics.com/get-started-with-freakonomics-radio-our-most-downloaded-episodes/" \
  --out downloads/most-downloaded

# 或安装脚本入口后
poetry run freakonomics-dl --out downloads/most-downloaded
```

### 常用参数

| 参数 | 说明 | 默认 |
|------|------|------|
| `--from-page URL` | 精选/文章列表页 | 上述 most-downloaded 页 |
| `--out DIR` | 输出目录 | `downloads/most-downloaded` |
| `--audio` / `--no-audio` | 是否下 mp3 | 开 |
| `--transcript` / `--no-transcript` | 是否下文稿 | 开 |
| `--delay SEC` | 请求最小间隔 | `1.5` |
| `--retries N` | 429/5xx/网络错误最大重试次数 | `5` |
| `--limit N` | 只处理前 N 集 | 全部 |
| `--force` | 强制重下 | 关 |

示例：

```bash
# 先试 1 集
poetry run python -m freakonomics_dl --limit 1 --out downloads/smoke-test

# 只要文稿
poetry run python -m freakonomics_dl --no-audio --out downloads/transcripts-only

# 只要音频
poetry run python -m freakonomics_dl --no-transcript --out downloads/audio-only
```

### 输出结构

每集的音频与文稿**同名、同目录**（集名作文件名）：

```
downloads/most-downloaded/
├── episodes.json
├── progress.json
├── Air Travel Is a Miracle. Why Do We Hate It.mp3
├── Air Travel Is a Miracle. Why Do We Hate It.md
├── Why Are There So Many Bad Bosses.mp3
├── Why Are There So Many Bad Bosses.md
└── …
```

### 运行时状态说明

| 标记 | 含义 |
|------|------|
| `[list]` | 拉取/解析列表页 |
| `[plan]` | 总数 / 待下载 / 跳过 |
| `[i/N] status:` | 单集状态：`FETCH` / `WRITE` / `DOWNLOAD` / `DONE` / `FAIL` / `SKIP` |
| `[progress]` | 累计成功/失败/剩余与耗时 |
| `↻` | 自动重试（HTTP 429、5xx、断线等） |
| `⬇` | 音频下载进度条 |

中断后直接重跑同一命令即可跳过已完成项。

## 工作原理

```
列表页 HTML
  → 收集 freakonomics.com/podcast/… 链接（去重）
单集页 HTML
  → <audio src="…mp3"> 流式下载
  → h2「Episode Transcript」解析为 Markdown
```

单集页上的 transcript 一般已在静态 HTML 中，无需点击展开，也无需 Playwright。

## 项目结构

```
freakonomics/
├── freakonomics_dl/          # 主程序（HTTP 下载器）
│   ├── cli.py
│   ├── curated.py            # 精选页链接解析
│   ├── episode.py            # 单集音频 + transcript
│   ├── downloader.py
│   ├── http_client.py
│   └── progress.py
├── simple_downloader.py      # 旧版：NSQ + Playwright（遗留）
├── pyproject.toml
└── README.md
```

## 遗留：`simple_downloader.py`

早期 NSQ 全系列 + Playwright 可见浏览器方案，仍保留作参考。新需求请优先用 `freakonomics_dl`。

```bash
# 可选：浏览器依赖
poetry install -E browser
poetry run playwright install chromium
poetry run python simple_downloader.py
```

## 注意事项

- 音频体积大（单集可达数十 MB）；全量 20 集可能超过 1GB，请预留磁盘并保持限速
- 请合理使用：个人离线学习；勿批量镜像或二次分发
- 若将来站点返回 403/Cloudflare，可再加 cookie/Playwright 兜底（当前未作为主路径）
- 文稿过短（默认少于 500 字符）会记为失败，便于发现页面结构变化

## 许可证与版权

站点内容版权归 Freakonomics / 相关权利方所有。本工具仅提供技术抓取便利，使用后果自负。
