---
name: ai-influence-digest
description: 生成「AI影响力信息汇总」周报：在不使用 X API 的前提下，用 opencli 的只读 X 搜索批量扫描指定账号过去7天推文（偏工具/工作流/教程/Prompt），过滤出对内容创作者立刻可用的高价值内容，产出结构化中文周报 Markdown，并生成多页截图海报（用于 Telegram/知识星球/Notion）。当你需要做每周 AI Builder 账号扫描、实用推文精选、工作流/方法论周报、周报截图生成时使用。
---

# AI影响力信息汇总（AI Influence Digest）

目标：把“刷一周 X”变成可复用的内容雷达流水线。

约束（强制）：
- **绝对禁止使用 X API**（包括任何 X API 搜索/时间线拉取）。
- 允许：已登录浏览器会话复用的 `opencli twitter search`（只读）+ X 公共 syndication timeline + X 官方 `oEmbed` + 公开页面抓取（`r.jina.ai`）+ 本地整理与截图。

## 快速流程（推荐）

### 0) 准备账号清单
- 默认账号列表：`references/accounts_65.txt`
- 可以按需删减/追加（每行一个 handle，不带 @）。

### 1) 扫描候选推文（收集阶段）
使用脚本抓“过去 N 天”候选推文（只拿 URL + 公开网页文本，不走 X API）。
默认是：
- `discover-backend=auto`：优先 `opencli`，不足时回退 `syndication`
- `fetch-backend=auto`：优先 `oembed`，不足时回退 `r.jina.ai`

账号安全要求：
- 推荐使用副号，不要使用主号
- 给 `opencli` 单独准备一个 Chrome Profile
- 当前脚本只允许调用只读命令 `opencli twitter search`

```bash
python3 scripts/scan_x_weekly.py \
  --accounts references/accounts_65.txt \
  --days 7 \
  --outdir ./output/ai-influence-digest
```

输出：
- `candidates.json`：候选列表（url/handle/text/score）
- `candidates.md`：便于快速人工扫读

> 如果遇到搜索源封锁/挑战：降低 `per-search`，或改用人工补充 URL 列表再走 `--seed-urls`。
> 如果已经有推文 URL 列表：直接用 `--discover-backend none --seed-urls <file> --fetch-backend oembed`，跳过发现阶段。
> `opencli` 依赖已登录浏览器会话；如果本机不可用，可切到 `syndication` 或直接提供 `--seed-urls`。
> `syndication` 对部分账号可能不是完整最新时间线，所以只保留为发现回退。

### 2) 按标准筛选 5-10 条高价值内容（编辑阶段）
筛选规则见：`references/filters.md`

产出要求（每条 150-200 字，必须含 Why it’s useful + 推文链接）：

- 标题用中文强调“实用价值”
- 结构固定：
  - Title
  - Account
  - Type（🛠️ 可复用方法｜💡 工作流优化｜📝 小技巧｜🚀 新工具）
  - Core Methods/Techniques：3 条可执行项
  - Why it’s useful：1-2 句解释“为什么内容创作者立刻能用”
  - Tweet Link：必须是原始推文 URL

### 3) 生成周报截图（发布物阶段）
把最终周报 Markdown 渲染成多页截图（默认小红书文字海报风格，适合发 TG/星球）。

```bash
bash scripts/render_weekly_screenshots.sh \
  ./output/ai-influence-digest/weekly_report.md \
  ./output/ai-influence-digest/screenshots \
  "2026年04月15日"
```

输出目录会生成 `01.png` `02.png` ...

> 如需独立仓库运行：通过 `SCREENSHOT_GENERATOR_DIR=/path/to/screenshot-generator` 指定截图分页工具，避免依赖 OpenClaw 工作区目录结构。

## 常见坑
- X 搜索结果可能混入非目标账号/聚合帖：脚本只保留 `https://x.com/<handle>/status/<id>`，并校验 handle 一致。
- r.jina.ai 抓取会带 UI 噪音：脚本已做基础提取；如文本异常，回退到手动读原帖。
- 候选过多时：先按 score 排序 + 手动筛掉“硬件/融资/纯 benchmark”。

## 资源
- `scripts/scan_x_weekly.py`：批量收集候选推文（opencli X 搜索 / syndication + 公开抓取）
- `scripts/render_weekly_screenshots.sh`：把 Markdown 周报分页截图
- `references/accounts_65.txt`：默认 65 账号清单
- `references/filters.md`：筛选标准（内容创作者视角）
