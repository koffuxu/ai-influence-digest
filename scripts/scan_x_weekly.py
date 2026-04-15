#!/usr/bin/env python3
"""Scan recent (past N days) X posts from a list of accounts without using X API.

Data sources:
- Google search via opencli (public web)
- Tweet page text via r.jina.ai (public HTML to text)

Outputs:
- candidates.json: list of {url, handle, text, score, fetched_at}
- candidates.md: quick skim markdown

NOTE: This is a "collector" script. Final selection + Chinese rewrite is intended to be done by the agent using the skill workflow.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

import requests


KW = ["tool", "workflow", "method", "tutorial", "prompt", "tip", "guide", "framework"]
EXCLUDE_HINTS = [
    "gpu",
    "tpu",
    "benchmark",
    "funding",
    "raised",
    "valuation",
    "revenue",
    "pricing",
    "acquisition",
]


def run_opencli_google_search(query: str, limit: int = 20, lang: str = "en") -> List[Dict[str, Any]]:
    cmd = [
        "opencli",
        "google",
        "search",
        "-f",
        "json",
        "--limit",
        str(limit),
        "--lang",
        lang,
        query,
    ]
    out = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT)
    data = json.loads(out)
    if not isinstance(data, list):
        return []
    return data


STATUS_RE = re.compile(r"^https?://x\.com/([^/]+)/status/(\d+)")


def extract_status_url(url: str) -> str | None:
    if not url:
        return None
    m = STATUS_RE.match(url)
    if not m:
        return None
    # Normalize to https
    return f"https://x.com/{m.group(1)}/status/{m.group(2)}"


def fetch_tweet_text(status_url: str, timeout: int = 30) -> str:
    # Use r.jina.ai to avoid login walls / heavy JS.
    r = requests.get("https://r.jina.ai/" + status_url, timeout=timeout)
    r.raise_for_status()
    text = r.text

    # Heuristic extraction: find "## Conversation" then take subsequent non-empty lines until "Quote" or "## New to X?".
    idx = text.find("## Conversation")
    if idx == -1:
        idx = text.find("# Conversation")
    body = text[idx:] if idx != -1 else text

    lines = [ln.strip() for ln in body.splitlines()]
    out_lines: List[str] = []
    started = False
    for ln in lines:
        if ln in ("## Conversation", "# Conversation"):
            started = True
            continue
        if not started:
            continue
        if ln.startswith("Quote") or ln.startswith("## New to X") or ln.startswith("Sign up"):
            break
        # stop if we hit analytics/footer noise
        if ln.startswith("[") and "Views" in ln:
            break
        if not ln:
            # keep one blank at most
            if out_lines and out_lines[-1] != "":
                out_lines.append("")
            continue
        # skip UI noise
        if ln.lower() in ("post", "conversation", "see new posts"):
            continue
        out_lines.append(ln)

    cleaned = "\n".join(out_lines).strip()
    # Fallback: if too short, return whole fetched text snippet
    return cleaned if len(cleaned) >= 40 else cleaned


def score_text(text: str) -> int:
    t = text.lower()
    score = 0

    # Actionability cues
    if "here's" in t or "here is" in t:
        score += 3
    if re.search(r"\b\d\)\b|\b\d\.\b", t):
        score += 2
    if "step" in t or "steps" in t:
        score += 3
    if "prompt" in t:
        score += 3
    if "template" in t:
        score += 2
    if "workflow" in t:
        score += 2
    if "how to" in t:
        score += 2

    # Penalize infra/business noise
    for bad in EXCLUDE_HINTS:
        if bad in t:
            score -= 3

    # length bonus (but cap)
    score += min(len(t) // 240, 3)
    return score


def chunk(items: List[str], size: int) -> List[List[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--accounts", default=str(Path(__file__).resolve().parent.parent / "references/accounts_65.txt"))
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--batch-size", type=int, default=10)
    ap.add_argument("--per-search", type=int, default=20)
    ap.add_argument("--outdir", default=str(Path.cwd() / "output"))
    ap.add_argument("--lang", default="en")
    args = ap.parse_args()

    accounts_path = Path(args.accounts).expanduser().resolve()
    if not accounts_path.exists():
        print(f"accounts file not found: {accounts_path}", file=sys.stderr)
        sys.exit(1)

    handles = []
    for ln in accounts_path.read_text("utf-8").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        handles.append(ln.lstrip("@"))

    today = dt.date.today()
    after = (today - dt.timedelta(days=args.days)).isoformat()

    outdir = Path(args.outdir).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    urls = []
    for batch in chunk(handles, args.batch_size):
        sites = " OR ".join([f"site:x.com/{h}/status" for h in batch])
        kws = " OR ".join(KW)
        query = f"({sites}) ({kws}) after:{after}"
        try:
            results = run_opencli_google_search(query, limit=args.per_search, lang=args.lang)
        except subprocess.CalledProcessError as e:
            print(f"[warn] opencli search failed: {e}", file=sys.stderr)
            continue

        for r in results:
            u = extract_status_url(str(r.get("url", "")))
            if u:
                urls.append(u)

    # dedup preserve order
    seen = set()
    uniq_urls = []
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        uniq_urls.append(u)

    candidates = []
    for u in uniq_urls:
        m = STATUS_RE.match(u)
        handle = m.group(1) if m else ""
        try:
            text = fetch_tweet_text(u)
        except Exception as e:
            print(f"[warn] fetch failed: {u} {e}", file=sys.stderr)
            continue
        if not text:
            continue
        s = score_text(text)
        candidates.append(
            {
                "url": u,
                "handle": handle,
                "text": text,
                "score": s,
                "fetched_at": dt.datetime.now().isoformat(timespec="seconds"),
            }
        )

    candidates.sort(key=lambda x: x.get("score", 0), reverse=True)

    (outdir / "candidates.json").write_text(json.dumps(candidates, ensure_ascii=False, indent=2) + "\n", "utf-8")

    md_lines = [
        f"# X weekly candidates (last {args.days} days)",
        f"- after: {after}",
        f"- accounts: {len(handles)}",
        f"- collected: {len(candidates)}",
        "",
    ]
    for i, c in enumerate(candidates[:60], 1):
        md_lines.append(f"## {i}. @{c['handle']} (score={c['score']})")
        md_lines.append(c["url"])
        md_lines.append("")
        md_lines.append(c["text"][:800].strip())
        md_lines.append("")

    (outdir / "candidates.md").write_text("\n".join(md_lines) + "\n", "utf-8")

    print(str(outdir / "candidates.json"))


if __name__ == "__main__":
    main()
