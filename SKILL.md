---
name: ai-influence-digest
description: 生成「AI影响力信息汇总」周报：在不使用 X API 的前提下，用 opencli 的只读 Google/X 搜索批量扫描指定账号过去7天推文（偏工具/工作流/教程/Prompt），过滤出对内容创作者立刻可用的高价值内容，产出结构化中文周报 Markdown，并生成多页截图海报（用于 Telegram/知识星球/Notion）。当你需要做每周 AI Builder 账号扫描、实用推文精选、工作流/方法论周报、周报截图生成时使用。
---

# AI影响力信息汇总（AI Influence Digest）

目标：把“刷一周 X”变成可复用的内容雷达流水线。

约束（强制）：
- **绝对禁止使用 X API**（包括任何 X API 搜索/时间线拉取）。
- 允许：已登录浏览器会话复用的 `opencli google search` / `opencli twitter search`（只读）+ X 公共 syndication timeline + X 官方 `oEmbed` + 公开页面抓取（`r.jina.ai`）+ 本地整理与截图。
- 执行环境要求：涉及 `opencli` 的发现步骤必须在系统环境执行，不能在沙箱环境执行（需要直接访问本机 Chrome Profile 与 Browser Bridge）。

## 快速流程（推荐）

### 0) 准备账号清单
- 默认账号列表：`references/accounts_65.txt`
- 可以按需删减/追加（每行一个 handle，不带 @）。

### 1) 扫描候选推文（收集阶段）
使用脚本抓”过去 N 天”候选推文（只拿 URL + 公开网页文本，不走 X API）。
默认是：
- `discover-backend=auto`：优先 `opencli-google`，不足时回退 `opencli-twitter`，最后回退 `syndication`
- `fetch-backend=auto`：使用 X 官方 `oEmbed` 接口；oEmbed 失败（如推文被删/受限）时该条跳过并打印 warn 日志

#### 发现后端选择指南

| 场景 | 推荐后端 | 原因 |
|---|---|---|
| **日报 / 近1-2天** | `opencli-twitter` | Google 对 X 推文索引延迟 1-3 天，1天窗口基本搜不到；twitter 直接拦截 X 内部 SearchTimeline API，时效性好 |
| **周报 / 7天窗口** | `auto`（默认） | Google 已完成索引，批量效率高；不足时自动回退 twitter 补充 |
| **账号安全优先、时效性要求不高** | `opencli-google` | Google 搜索不需要 X 登录状态，风险更低；可通过 `--discover-backend opencli-google` 显式指定 |

**`opencli-twitter` 与 `opencli-google` 的核心区别：**
- `opencli-twitter`：Strategy = `INTERCEPT`，需要已登录 X 的 Chrome Profile，拦截 X 内部 API 响应，**数据实时准确**，但对账号有一定风险
- `opencli-google`：Strategy = `PUBLIC`，通过 Google 搜索 `site:x.com/<handle>/status` 发现推文，**不依赖 X 登录**，但 Google 索引有延迟，近期内容可能缺失

#### 账号安全与 Chrome Profile 配置

- 推荐使用 X **副号**（非主号），专门用于 `opencli-twitter` 的登录会话
- 给副号单独创建一个 Chrome Profile，并在该 Profile 中启用 OpenCLI Browser Bridge 扩展
- 在 `~/.zshrc`（或 `.bashrc`）中配置：

```bash
export OPENCLI_CHROME_PROFILE=<your-alt-account-profile-name>
```

脚本启动时会打印当前 Profile 名称用于确认；若未设置且使用 opencli 后端，会发出警告提醒。

- `opencli-google` 对 Chrome Profile 没有特殊要求（不依赖 X 登录），可使用任意已连接 Browser Bridge 的 Profile

```bash
# 准确及时（日报、近期内容）
python3 scripts/scan_x_weekly.py \
  --accounts references/accounts_65.txt \
  --days 1 \
  --discover-backend opencli-twitter \
  --outdir ./output/ai-influence-digest

# 安全优先（周报、对账号风险敏感）
python3 scripts/scan_x_weekly.py \
  --accounts references/accounts_65.txt \
  --days 7 \
  --discover-backend opencli-google \
  --outdir ./output/ai-influence-digest

# 默认（周报，自动 fallback）
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
- oEmbed 对已删推文或受限账号会返回 404，该条会被跳过并记录 warn 日志，可人工补充 `--seed-urls`。
- 候选过多时：先按 score 排序 + 手动筛掉“硬件/融资/纯 benchmark”。

## 资源
- `scripts/scan_x_weekly.py`：批量收集候选推文（opencli Google/X 搜索 / syndication + 公开抓取）
- `scripts/render_weekly_screenshots.sh`：把 Markdown 周报分页截图
- `references/accounts_65.txt`：默认 65 账号清单
- `references/filters.md`：筛选标准（内容创作者视角）
