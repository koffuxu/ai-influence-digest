#!/bin/bash
set -euo pipefail

MD_PATH="$1"
OUT_DIR="${2:-$HOME/.openclaw/workspace/output/ai-influence-digest}"
DATE_TEXT="${3:-$(date +"%Y年%m月%d日")}"  # e.g. 2026年04月15日

# Use the existing screenshot-generator in OpenClaw workspace.
SG_DIR="${SCREENSHOT_GENERATOR_DIR:-$HOME/.openclaw/workspace/skills/screenshot-generator}"
PAGINATE="$SG_DIR/paginate_md_to_xhs.py"

if [ ! -f "$PAGINATE" ]; then
  echo "paginate_md_to_xhs.py not found: $PAGINATE" >&2
  exit 1
fi

/usr/bin/python3 "$PAGINATE" \
  --md "$MD_PATH" \
  --output-dir "$OUT_DIR" \
  --author-name "可夫小子" \
  --avatar-url "logo.jpg" \
  --date "$DATE_TEXT" \
  --poster-width 800 \
  --poster-height 1200 \
  --max-score 650

echo "OK: $OUT_DIR"
