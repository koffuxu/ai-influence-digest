# AI影响力信息汇总（ai-influence-digest）

把「刷一周 X」变成可复用的内容雷达流水线：
- 批量扫描指定 X 账号过去 7 天推文（工具/工作流/教程/Prompt）
- 过滤出对内容创作者“立刻可用”的高价值内容
- 产出结构化中文周报 Markdown
- 一键生成多页截图海报（便于发 Telegram / 知识星球 / Notion）

## ✅ 前提与约束（强制）
- **绝对禁止使用 X API**（包括任何 X API 搜索/时间线拉取）。
- 只允许走“公开网页 + 已登录浏览器会话复用”路径：
  - 发现：`opencli google search` / `opencli twitter search`（只读，按场景选择）
  - 正文抓取：X 官方 `oEmbed`（oEmbed 失败时跳过并记录 warn 日志）
  - 兜底发现：X 公共 `syndication`（无需登录，但时间线可能不完整）

## 依赖
- Python 3.9+
- `requests`（Python 包，见 `requirements.txt`）
- `opencli`（默认发现后端，支持 google/twitter search）
- Chrome + Browser Bridge extension + 已登录 X 的独立浏览器 Profile
- 可选：`screenshot-generator`（用于把最终周报渲染成多页图片）

运行环境要求（重要）：
- 涉及 `opencli` 的发现阶段（`opencli google search` / `opencli twitter search`）必须在系统环境执行，不能在沙箱环境执行。
- 原因是 `opencli` 需要直接复用本机 Chrome Profile 与 Browser Bridge 扩展。

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
- 给 `opencli` 单独建浏览器 Profile（仅用于 `opencli-twitter`；`opencli-google` 不依赖 X 登录）
- 这个仓库只会调用只读命令 `opencli google search` / `opencli twitter search`

在 `~/.zshrc` 中配置 Chrome Profile 名称，脚本启动时会打印确认：

```bash
export OPENCLI_CHROME_PROFILE=<your-alt-account-profile-name>
```

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
- `discover-backend=auto`：优先尝试 `opencli-google`，不足时回退 `opencli-twitter`，最后回退 `syndication`
- `fetch-backend=auto`：使用 X 官方 `oEmbed`；失败时跳过并记录 warn 日志

后端选择建议：

| 场景 | 推荐 `--discover-backend` |
|---|---|
| 日报 / 近1-2天 | `opencli-twitter` |
| 周报 / 7天（默认） | `auto` |
| 账号安全优先、时效性要求不高 | `opencli-google` |

注意：`opencli-google` 对 X 推文的索引有 **1-3 天延迟**，1天窗口基本搜不到内容；即使是7天窗口，部分低频或个人账号也可能未被索引。`opencli-twitter` 直接拦截 X 内部 API，时效性好但需要已登录的 X 副号。

显式指定后端：

```bash
python3 scripts/scan_x_weekly.py \
  --accounts references/accounts_65.txt \
  --discover-backend opencli-twitter \
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
