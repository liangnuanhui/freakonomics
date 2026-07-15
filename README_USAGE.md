# 使用指南：`simple_downloader.py`

本文补充 [README.md](./README.md) 的安装与功能说明，聚焦运行细节、缓存行为与常见问题。

## 快速开始

```bash
# 1. 安装依赖
poetry install
poetry run playwright install chromium

# 2. 运行（需本机有 Google Chrome）
poetry run python simple_downloader.py
```

## 工作流程（代码实际行为）

```
SimpleDownloader.run()
  ├─ 启动 Playwright Chromium（channel=chrome, headless=False）
  ├─ get_episodes(page)
  │    ├─ 若存在 .cache/episodes.json → 直接返回缓存列表
  │    └─ 否则
  │         ├─ 打开 https://freakonomics.com/series-full/nsq/
  │         ├─ 提示：手动过 Cloudflare，页面加载完后按 Enter
  │         ├─ 解析 a[href*="/podcast/"] 中文本匹配 /^NO\.\s*(\d+)$/i 的链接
  │         ├─ 点击 “OLDER POSTS” / “Older Posts” 翻页直到没有下一页
  │         ├─ 按集号去重、升序排序
  │         └─ 写入 .cache/episodes.json
  ├─ 过滤 pending：number 不在 progress.downloaded 中的集
  ├─ 对每个 pending 调用 download_one
  │    ├─ 若 transcripts/{number}-*.md 已存在 → 成功
  │    ├─ page.goto(剧集 URL)
  │    ├─ 尝试点击 “Read full Transcript”
  │    ├─ BeautifulSoup 提取 h1 标题与 Episode Transcript 区块
  │    ├─ 正文长度 > 500 才写入 Markdown
  │    └─ 更新 downloaded / failed
  └─ 每 10 集 save_progress；异常中断或 finally 时也会保存
```

## 目录与生成文件

```
.cache/
├── episodes.json      # 节目列表缓存（无自动过期）
├── progress.json      # 下载进度
└── browser_context/   # 本地浏览器数据（若曾生成；非脚本强依赖）

transcripts/
├── 1-Some-Title.md
├── 100-Another-Title.md
└── ...
```

### `progress.json` 示例

```json
{
  "downloaded": [100],
  "failed": [1, 2, 3],
  "last_updated": "2026-01-30T21:33:08.477161"
}
```

- **downloaded**：已成功集号，下次会跳过
- **failed**：提取失败或出错的集号；只要不在 `downloaded` 里，下次仍会再试

### 输出 Markdown 格式

```markdown
# {页面 h1 标题}

**Episode:** {集号}

**URL:** {剧集 URL}

---

{正文}
```

正文规则摘要：

- 定位 `h2` 文本匹配 “Episode Transcript”
- 在其父级 `article`/`div`/`section` 内收集 `p`、`blockquote`、`h2`、`h3`
- 跳过空行、“Read full Transcript”、标题本身
- 遇到以 `Sources` / `Resources` 开头的文本则停止
- `blockquote` 写成 `> ...`，小标题写成 `## ...`

## 常见问题

### Q1: 遇到 Cloudflare 验证怎么办？

1. 不要关浏览器
2. 在窗口中完成验证（勾选/滑块等）
3. 等到能看到节目列表
4. 回到终端按 **Enter**

仅在需要重新抓取列表（没有或删除了 `episodes.json`）时会走到这一步。

### Q2: 下载中断了怎么办？

直接再运行：

```bash
poetry run python simple_downloader.py
```

已写入 `downloaded` 或已存在 `transcripts/{集号}-*.md` 的集会被跳过。

### Q3: 如何强制重新抓取节目列表？

```bash
rm .cache/episodes.json
poetry run python simple_downloader.py
```

注意：列表缓存**没有 24 小时过期逻辑**；有文件就一直用。

### Q4: 如何只重试失败的集？

失败集默认下次会再试。若某集被误记入 `downloaded`，从 `.cache/progress.json` 的 `downloaded` 中删掉该集号，并删除对应 `transcripts/{集号}-*.md` 后再运行。

### Q5: 提示找不到 Chrome / 启动失败？

脚本使用：

```python
browser = await p.chromium.launch(headless=False, channel='chrome')
```

请确认本机已安装 Google Chrome。也可改为安装 Playwright 自带浏览器后调整 `channel`（需改代码）。

### Q6: 为什么有的集显示「无 transcript」？

可能原因：

- 页面没有 “Episode Transcript” 区块
- 未成功展开全文
- 提取文本长度 ≤ 500
- 页面结构变化导致解析失败

该集号会进入 `failed`，可稍后重跑。

## 当前局限（与代码一致）

- 无命令行参数（不能指定起止集、输出目录、headless 等）
- 串行下载，固定约 1 秒间隔
- 列表缓存不过期
- 不针对 Cloudflare 做自动化绕过，依赖人工验证
- 仅适配 NSQ 系列页与当前站点 DOM 结构

## 历史说明

开发过程中曾存在 `scraper.py`、`scraper_enhanced.py`、`download_uc.py`、`download_transcripts.py` 等多套方案，已在 2026-01-30 清理删除。仓库现仅保留 `simple_downloader.py` 作为正式入口。
