# Freakonomics Transcript Downloader

下载 [Freakonomics](https://freakonomics.com/) 播客 **No Stupid Questions (NSQ)** 系列的 episode transcript，保存为 Markdown。

当前代码库只有一个业务入口：`simple_downloader.py`。

## 功能概览

| 功能 | 说明 |
|------|------|
| 启动可见浏览器 | Playwright 使用系统 Chrome（非无头），便于处理 Cloudflare |
| 手动验证一次 | 首次抓取列表时打开系列页，终端等待你按 Enter 后继续 |
| 节目列表抓取 | 从 NSQ 系列页解析 `NO. N` 链接，点击 Older Posts 翻页 |
| 列表缓存 | 写入 `.cache/episodes.json`；文件存在则直接复用，不再访问列表页 |
| 断点续传 | 读取 `.cache/progress.json`，跳过已成功下载的集数 |
| 文件跳过 | `transcripts/{集号}-*.md` 已存在则视为成功 |
| 单集下载 | 打开剧集页 → 点击 “Read full Transcript” → 解析 HTML |
| 正文提取 | 定位 “Episode Transcript”，抽取段落/引用/小标题，到 Sources/Resources 停止 |
| Markdown 输出 | 含标题、集数、原始 URL、完整 transcript |
| 质量门槛 | transcript 须超过 500 字符，否则记为失败 |
| 进度落盘 | 成功/失败分别记录；每 10 集保存一次，中断或结束也会保存 |
| 可中断 | 支持 Ctrl+C，退出前仍会保存进度 |

**未实现：** CLI 参数（集数范围/并发等）、列表缓存自动过期、失败自动重试队列、无头模式、其它播客系列。

## 项目结构

```
freakonomics/
├── simple_downloader.py   # 唯一下载脚本
├── pyproject.toml         # Poetry 依赖
├── README.md              # 本文件
├── README_USAGE.md        # 详细使用与排错
├── .gitignore
├── transcripts/           # 下载输出（默认被 gitignore）
└── .cache/                # 列表缓存、进度、浏览器数据（本地生成）
    ├── episodes.json
    ├── progress.json
    └── browser_context/   # 若存在，为浏览器运行数据
```

## 环境要求

- Python 3.10+
- [Poetry](https://python-poetry.org/)
- 本机已安装 Google Chrome（脚本使用 `channel='chrome'`）

## 安装

```bash
poetry install
poetry run playwright install chromium
```

> 脚本优先使用系统 Chrome；Playwright 自带 Chromium 可作为后备环境的一部分安装。

## 使用

```bash
poetry run python simple_downloader.py
```

运行过程：

1. 启动可见 Chrome
2. 若无 `.cache/episodes.json`：打开 [NSQ 系列页](https://freakonomics.com/series-full/nsq/)，必要时在浏览器中完成 Cloudflare 验证，回到终端按 Enter
3. 抓取或读取缓存的节目列表
4. 跳过 `progress.json` 中已下载的集，串行下载其余集
5. 将 Markdown 写入 `transcripts/`，并更新进度

更细的说明见 [README_USAGE.md](./README_USAGE.md)。

## 输出

文件名示例：

```
transcripts/100-Is It Weird for Adults to Have Imaginary Friends Replay.md
```

每个文件大致结构：

```markdown
# 标题

**Episode:** 100

**URL:** https://freakonomics.com/podcast/...

---

transcript 正文...
```

## 进度与缓存

| 路径 | 作用 |
|------|------|
| `.cache/episodes.json` | 节目列表（number + url） |
| `.cache/progress.json` | `downloaded` / `failed` / `last_updated` |
| `transcripts/` | 已下载的 Markdown |

重新抓取列表：删除 `.cache/episodes.json` 后再运行。  
重试失败集：失败集只要不在 `downloaded` 中，下次运行会再次尝试；也可手动编辑 `progress.json`。

## 注意事项

- 首次（或无列表缓存时）需要手动完成 Cloudflare 验证
- 下载为串行，集与集之间有约 1 秒间隔，全集耗时较长
- 浏览器窗口在运行期间请勿关闭
- 当前依赖里仍保留部分历史反爬相关包（selenium 等），实际脚本主要使用 Playwright + BeautifulSoup
