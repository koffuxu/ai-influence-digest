#!/bin/bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <weekly_report.md> [output_dir] [date_text]" >&2
  exit 1
fi

MD_PATH="$1"
DEFAULT_OUT_DIR="$(cd "$(dirname "$MD_PATH")" && pwd)/screenshots"
OUT_DIR="${2:-$DEFAULT_OUT_DIR}"
DATE_TEXT="${3:-$(date +"%Y年%m月%d日")}"  # e.g. 2026年04月15日

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

SG_DIR=""
for candidate in \
  "${SCREENSHOT_GENERATOR_DIR:-}" \
  "$REPO_DIR/tools/screenshot-generator" \
  "$REPO_DIR/../tools/screenshot-generator" \
  "$HOME/.openclaw/workspace/skills/screenshot-generator"
do
  if [ -n "$candidate" ] && [ -f "$candidate/paginate_md_to_xhs.py" ]; then
    SG_DIR="$candidate"
    break
  fi
done

PAGINATE="${SG_DIR:+$SG_DIR/paginate_md_to_xhs.py}"

if [ -z "$SG_DIR" ] || [ ! -f "$PAGINATE" ]; then
  echo "paginate_md_to_xhs.py not found. Set SCREENSHOT_GENERATOR_DIR to a screenshot-generator checkout." >&2
  exit 1
fi

AUTHOR_NAME="${AUTHOR_NAME:-可夫小子}"
AVATAR_URL="${AVATAR_URL:-logo.jpg}"

/usr/bin/python3 "$PAGINATE" \
  --md "$MD_PATH" \
  --output-dir "$OUT_DIR" \
  --author-name "$AUTHOR_NAME" \
  --avatar-url "$AVATAR_URL" \
  --date "$DATE_TEXT" \
  --poster-width 800 \
  --poster-height 1200 \
  --max-score 650

echo "OK: $OUT_DIR"
