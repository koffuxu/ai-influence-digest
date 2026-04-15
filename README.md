# AI影响力信息汇总（ai-influence-digest）

把「刷一周 X」变成可复用的内容雷达流水线：
- 批量扫描指定 X 账号过去 7 天推文（工具/工作流/教程/Prompt）
- 过滤出对内容创作者“立刻可用”的高价值内容
- 产出结构化中文周报 Markdown
- 一键生成多页截图海报（便于发 Telegram / 知识星球 / Notion）

## ✅ 前提与约束（强制）
- **绝对禁止使用 X API**（包括任何 X API 搜索/时间线拉取）。
- 只允许走“公开网页”路径：
  - Google 搜索：`opencli google search`
  - 推文正文抓取：`https://r.jina.ai/https://x.com/<handle>/status/<id>`

## 依赖
- Python 3.9+
- `opencli`（用于 Google 搜索）
- `requests`（Python 包）
- 生成截图依赖 OpenClaw 的 `screenshot-generator`（内含 Playwright/Jinja2 环境与分页脚本）

## 快速开始

### 1) 扫描候选推文（收集）
```bash
python3 scripts/scan_x_weekly.py \
  --accounts references/accounts_65.txt \
  --days 7 \
  --batch-size 10 \
  --per-search 20 \
  --outdir ./output/ai-influence-digest
```
输出：
- `candidates.json`（url/handle/text/score）
- `candidates.md`（便于人工快速扫读）

### 2) 人工筛选并整理成周报 Markdown（编辑）
筛选标准见：`references/filters.md`

建议将最终稿保存为：
- `./output/ai-influence-digest/weekly_report.md`

### 3) 生成周报截图（发布物）
> 这里默认复用 OpenClaw 的截图分页工具（小红书文字海报风格）。

```bash
bash scripts/render_weekly_screenshots.sh \
  ./output/ai-influence-digest/weekly_report.md \
  /Volumes/T7/OpenClaw/Output/workspace-output/AI影响力信息汇总 \
  "2026年04月15日"
```
会得到：`01.png`、`02.png`…

## 作者
- X：https://x.com/koffuxu
