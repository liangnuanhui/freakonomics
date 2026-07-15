# Freakonomics Downloader

从 [freakonomics.com](https://freakonomics.com/) 下载播客 **音频 (mp3)** 与 **全文 transcript (Markdown)**。

**主路径：HTTP（requests + BeautifulSoup）**，无需浏览器。适合推荐页、专题页，以及 **系列归档页**（自动跟「Show Full Archive」并翻「Older Posts」）。

默认 **跳过 PLUS** 会员集；**EXTRA** 与普通单集同等下载。

---

## 快速开始

### 安装

```bash
poetry install
poetry run python -m freakonomics_dl --help
```

### 交互模式（推荐）

未传 `--from-page` 时进入交互向导：

```bash
poetry run python -m freakonomics_dl --out downloads/new_folder
```

流程：

1. 提示输入网址（精选页 / `series/` / `series-full/` / 单集 `/podcast/...`）
2. **自动访问并探测结构**，反馈是否可抓、本页集数、PLUS、能否翻页、样例单集是否有音频/文稿
3. **选择下载内容**：音频+文稿 / 仅文稿 / 仅音频
4. 选择下一步：
   - **抓取全部**（自动翻页，跳过 PLUS）
   - **自行选择范围**（如 `1-20` / `5` / `1,3,5-10`）
   - **只抓取某一个单集**（按序号或粘贴 URL）
   - 重新输入网址 / 退出

### 批处理模式

```bash
# 推荐页约 20 集
poetry run python -m freakonomics_dl \
  --from-page "https://freakonomics.com/get-started-with-freakonomics-radio-our-most-downloaded-episodes/" \
  --out downloads/most-downloaded

# 系列归档
poetry run python -m freakonomics_dl \
  --from-page "https://freakonomics.com/series/freakonomics-radio/" \
  --out downloads/freakonomics-radio
```

---

## 常用参数

| 参数 | 说明 | 默认 |
|------|------|------|
| `--from-page URL` | 精选页 / series / 单集；**省略则进交互模式** | 无（交互） |
| `--interactive` | 强制交互模式 | 关 |
| `--out DIR` | 输出目录 | `downloads/most-downloaded` |
| `--audio` / `--no-audio` | 是否下 mp3 | 开 |
| `--transcript` / `--no-transcript` | 是否下文稿 | 开 |
| `--skip-plus` / `--no-skip-plus` | 跳过 PLUS 集（EXTRA 保留） | 开 |
| `--follow-full-archive` / `--no-follow-full-archive` | 遇到「Show Full Archive」则进全库 | 开 |
| `--max-pages N` | 归档最多翻页数 | `200` |
| `--delay SEC` | 请求最小间隔 | `1.5` |
| `--retries N` | 429/5xx/网络错误最大重试次数 | `5` |
| `--limit N` | 只处理前 N 集 | 全部 |
| `--force` | 强制重下（忽略已完成） | 关 |
| `--min-transcript-chars N` | 文稿过短则失败 | `500` |

### 示例

```bash
# 先试 1 集
poetry run python -m freakonomics_dl --limit 1 --out downloads/smoke-test

# 只补文稿（跳过已有成对文件；不要音频）
poetry run python -m freakonomics_dl --no-audio --out downloads/most-downloaded

# 只补音频
poetry run python -m freakonomics_dl --no-transcript --out downloads/most-downloaded

# 换一张精选页（任意含 /podcast/ 链接的文章页）
poetry run python -m freakonomics_dl \
  --from-page "https://freakonomics.com/some-other-roundup/" \
  --out downloads/other-roundup

# Freakonomics Radio 系列（自动进 full archive + 翻页，跳过 PLUS）
poetry run python -m freakonomics_dl \
  --from-page "https://freakonomics.com/series/freakonomics-radio/" \
  --out downloads/freakonomics-radio

# 只要文稿、先试 3 集
poetry run python -m freakonomics_dl \
  --from-page "https://freakonomics.com/series/freakonomics-radio/" \
  --out downloads/freakonomics-radio \
  --no-audio --limit 3

# 强制全部重下
poetry run python -m freakonomics_dl --force --out downloads/most-downloaded
```

列表解析规则：按 `/podcast/` URL 归并锚文本；标题取最长非标签文案；带 **PLUS** 标签的 URL 默认丢弃；**EXTRA** 保留。系列页若有「Show Full Archive」会先跳到 `series-full`，再跟「Older Posts」翻页。

---

## 输出结构

每集的音频与文稿**同名、同目录**（集名作文件名）：

```
downloads/most-downloaded/
├── episodes.json      # 列表解析结果
├── progress.json      # 完成/失败进度（可断点续跑）
├── Air Travel Is a Miracle. Why Do We Hate It.mp3
├── Air Travel Is a Miracle. Why Do We Hate It.md
├── Why Are There So Many Bad Bosses.mp3
├── Why Are There So Many Bad Bosses.md
└── …
```

### 进度与断点续跑

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

- 已在 `completed` **或** 磁盘上已有对应资源 → **SKIP**
- `--force` 忽略上述检查并重下
- 中断后直接重跑同一命令即可续跑

---

## 运行时状态说明

| 标记 | 含义 |
|------|------|
| `[list]` | 拉取/解析列表页 |
| `[plan]` | 总数 / 待下载 / 跳过 |
| `[i/N] status:` | 单集：`FETCH` / `WRITE` / `DOWNLOAD` / `DONE` / `FAIL` / `SKIP` |
| `[progress]` | 累计成功/失败/剩余与耗时 |
| `↻` | 自动重试（HTTP 429、5xx、断线等） |
| `⬇` | 音频下载进度条 |

---

## 端到端流程

1. GET `--from-page`  
2. 若有「Show Full Archive」→ 改走 `series-full`（可关）  
3. 解析本页剧集；跳过 PLUS；跟「Older Posts」翻页直到没有或达 `--max-pages` / `--limit`  
4. 写入 `episodes.json`  
5. 对每集 GET 单集页 → 抽 `audio[src]` 与 Episode Transcript  
6. 流式写 `<集名>.mp3`，Markdown 写同目录 `<集名>.md`  
7. 更新 `progress.json`；429/5xx/网络错误自动退避重试  

单集页上的 transcript 一般已在静态 HTML 中，无需点击展开，也无需 Playwright。

```
series/ 或 精选页
  → (可选) series-full
  → page/1 … Older Posts → page/2 …
  → 过滤 PLUS，保留 EXTRA + 正片
单集页
  → mp3 + Episode Transcript → <title>.mp3 / <title>.md
```

---

## 故障排查

| 现象 | 处理 |
|------|------|
| 未找到剧集 / `no episode links` | 检查 `--from-page`；页面是否仍含 `/podcast/` 链接 |
| `no audio URL` | 该集页结构变化；打开单集页查看是否有 `<audio>` |
| `transcript … too short` | 可能无文稿或选择器失效 |
| 403 / 连接重置 | 增大 `--delay`；稍后重试；必要时再考虑浏览器兜底 |
| 磁盘暴涨 | 使用 `--no-audio` 或 `--limit` |
| 想重下某一集 | 删除对应 `.mp3`/`.md` 后重跑，或使用 `--force` |

---

## 项目结构

```
freakonomics/
├── freakonomics_dl/          # 主程序（HTTP 下载器）
│   ├── cli.py
│   ├── curated.py            # 精选页链接解析
│   ├── episode.py            # 单集音频 + transcript
│   ├── downloader.py
│   ├── http_client.py
│   ├── names.py              # 集名文件名
│   └── progress.py
├── simple_downloader.py      # 旧版：NSQ + Playwright（遗留）
├── pyproject.toml
└── README.md
```

---

## 遗留：`simple_downloader.py`

早期 NSQ 全系列 + Playwright 可见浏览器方案，仅作参考。新需求请用 `freakonomics_dl`。

| | `freakonomics_dl` | `simple_downloader.py` |
|--|-------------------|------------------------|
| 协议 | HTTP | Playwright 浏览器 |
| 列表 | 任意精选/文章页 | 固定 NSQ series-full |
| 音频 | 支持 | 否 |
| 文稿 | 支持 | 支持 |
| 状态 | **推荐** | 遗留 |

```bash
# 可选：浏览器依赖
poetry install -E browser
poetry run playwright install chromium
poetry run python simple_downloader.py
```

---

## 注意事项

- 音频体积大（单集可达数十 MB）；全量 20 集约 1GB，请预留磁盘并保持限速
- 请合理使用：个人离线学习；勿批量镜像或二次分发
- 若将来站点返回 403/Cloudflare，可再加 cookie/Playwright 兜底（当前未作为主路径）
- 文稿过短（默认少于 500 字符）会记为失败，便于发现页面结构变化

## 许可证与版权

站点内容版权归 Freakonomics / 相关权利方所有。本工具仅提供技术抓取便利，使用后果自负。
