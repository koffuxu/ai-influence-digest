# AI影响力信息汇总（ai-influence-digest）

把「刷一周 X」变成可复用的内容雷达流水线：
- 批量扫描指定 X 账号过去 7 天推文（工具/工作流/教程/Prompt）
- 过滤出对内容创作者“立刻可用”的高价值内容
- 产出结构化中文周报 Markdown
- 一键生成多页截图海报（便于发 Telegram / 知识星球 / Notion）

## ✅ 前提与约束（强制）
- **绝对禁止使用 X API**（包括任何 X API 搜索/时间线拉取）。
- 只允许走“公开网页 + 已登录浏览器会话复用”路径：
  - 默认发现：`opencli twitter search`（只读）
  - 默认正文抓取：X 官方 `oEmbed`
  - 回退发现/抓取：X 公共 `syndication`、`r.jina.ai`

## 依赖
- Python 3.9+
- `requests`（Python 包，见 `requirements.txt`）
- `opencli`（默认发现后端）
- Chrome + Browser Bridge extension + 已登录 X 的独立浏览器 Profile
- 可选：`screenshot-generator`（用于把最终周报渲染成多页图片）

## 安装
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm install -g @jackwener/opencli
```

再安装 `opencli` 的 Browser Bridge 扩展，并用单独的 Chrome Profile 登录 X。
建议：
- 使用副号，不用主号
- 给 `opencli` 单独建浏览器 Profile
- 这个仓库只会调用只读命令 `opencli twitter search`

如果你要生成截图，建议把 `screenshot-generator` 作为同仓库的 `tools/screenshot-generator`、上级目录的 `tools/screenshot-generator`，或通过环境变量显式指定：

```bash
export SCREENSHOT_GENERATOR_DIR=/path/to/screenshot-generator
```

## 快速开始

### 1) 扫描候选推文（收集）
```bash
python3 scripts/scan_x_weekly.py \
  --accounts references/accounts_65.txt \
  --days 7 \
  --outdir ./output/ai-influence-digest
```
输出：
- `candidates.json`（url/handle/text/score）
- `candidates.md`（便于人工快速扫读）

默认行为：
- `discover-backend=auto`：优先尝试 `opencli`，失败或结果不足时回退到 `syndication`
- `fetch-backend=auto`：优先尝试 `oembed`，失败时回退到 `r.jina.ai`

说明：
- `opencli` 使用已登录浏览器会话在 X 内搜索公开帖子，发现能力更强
- `syndication` 不需要登录或插件，但对少数账号可能返回偏旧或不完整的时间线，所以只保留为回退

显式指定后端：

```bash
python3 scripts/scan_x_weekly.py \
  --accounts references/accounts_65.txt \
  --discover-backend opencli \
  --fetch-backend oembed \
  --outdir ./output/ai-influence-digest
```

如果你已经有一批推文 URL，可以跳过发现阶段，只用 `oEmbed` 抓正文：

```bash
python3 scripts/scan_x_weekly.py \
  --accounts references/accounts_65.txt \
  --discover-backend none \
  --seed-urls ./output/ai-influence-digest/seed_urls.txt \
  --fetch-backend oembed \
  --outdir ./output/ai-influence-digest
```

### 2) 人工筛选并整理成周报 Markdown（编辑）
筛选标准见：`references/filters.md`

建议将最终稿保存为：
- `./output/ai-influence-digest/weekly_report.md`

### 3) 生成周报截图（发布物）
> 这里依赖外部 `screenshot-generator`。脚本会优先查找 `SCREENSHOT_GENERATOR_DIR`，其次查找仓库附近的 `tools/screenshot-generator`。

```bash
bash scripts/render_weekly_screenshots.sh \
  ./output/ai-influence-digest/weekly_report.md \
  ./output/ai-influence-digest/screenshots \
  "2026年04月15日"
```
会得到：`01.png`、`02.png`…

## 作者
- X：https://x.com/koffuxu
