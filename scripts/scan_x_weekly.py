#!/usr/bin/env python3
"""Scan recent X posts from target accounts without using the X API.

Default pipeline:
- Discover candidate post URLs via opencli's read-only Google search adapter
- Read post content via X's public oEmbed endpoint

Optional fallback backends:
- syndication: public X timeline widget discovery fallback
- r.jina.ai: text fetch fallback when oEmbed is insufficient
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import shutil
import subprocess
import sys
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

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
DISCOVER_BACKENDS = ("opencli-google", "opencli-twitter", "syndication")
FETCH_BACKENDS = ("oembed",)
DEFAULT_TIMEOUT = 30
STATUS_RE = re.compile(r"https?://(?:www\.)?(?:x|twitter)\.com/([^/]+)/status/(\d+)", re.IGNORECASE)
STATUS_ID_RE = re.compile(
    r"https?://(?:www\.)?(?:x|twitter)\.com/(?:[^/]+|i)/status/(\d+)", re.IGNORECASE
)
MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
HTML_TAG_RE = re.compile(r"<[^>]+>")
OEMBED_PARAGRAPH_RE = re.compile(r"<p\b[^>]*>(.*?)</p>", re.IGNORECASE | re.DOTALL)
NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>')
REPLY_COUNT_RE = re.compile(r"^Read \d+ replies$")
ENGAGEMENT_RE = re.compile(r"^[\d.,]+[KMB]?$", re.IGNORECASE)
READ_ONLY_OPENCLI_COMMANDS = {
    ("twitter", "search"),
    ("google", "search"),
}


def log(message: str) -> None:
    print(f"[ai-influence-digest] {message}", file=sys.stderr)


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def run_opencli_read_only(args: List[str]) -> str:
    if len(args) < 3 or args[0] != "opencli":
        raise ValueError("opencli command must start with: opencli <group> <command>")

    command_key = (args[1], args[2])
    if command_key not in READ_ONLY_OPENCLI_COMMANDS:
        raise ValueError(f"unsafe opencli command blocked: {' '.join(args[:3])}")

    proc = subprocess.run(args, text=True, capture_output=True, check=False)
    output = proc.stdout
    if proc.stderr:
        output = f"{output}\n{proc.stderr}" if output else proc.stderr

    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, args, output=output)
    return output


def extract_first_json_value(raw: str) -> Any:
    text = raw.lstrip()
    if not text:
        raise ValueError("empty output")

    decoder = json.JSONDecoder()
    return decoder.raw_decode(text)[0]


def clean_extracted_text(text: str) -> str:
    text = MARKDOWN_IMAGE_RE.sub("", text)
    text = MARKDOWN_LINK_RE.sub(r"\1", text)

    out_lines: List[str] = []
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            if out_lines and out_lines[-1] != "":
                out_lines.append("")
            continue
        if line.startswith(("Published Time:", "URL Source:", "Markdown Content:")):
            continue
        if line in ("[]",):
            continue
        if REPLY_COUNT_RE.match(line):
            continue
        if ENGAGEMENT_RE.match(line):
            continue
        if line.lower() in ("post", "conversation", "see new posts", "sign up"):
            continue
        out_lines.append(line)
    return "\n".join(out_lines).strip()


def strip_html_fragment(fragment: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.IGNORECASE)
    text = HTML_TAG_RE.sub("", text)
    text = html.unescape(text).replace("\xa0", " ")
    return clean_extracted_text(text)


def normalize_status_url(url: str, preferred_handle: str | None = None) -> str | None:
    match = STATUS_RE.search(url or "")
    if match and match.group(1).lower() != "i":
        return f"https://x.com/{match.group(1)}/status/{match.group(2)}"

    id_match = STATUS_ID_RE.search(url or "")
    if not id_match:
        return None

    if preferred_handle:
        return f"https://x.com/{preferred_handle}/status/{id_match.group(1)}"
    return f"https://x.com/i/status/{id_match.group(1)}"


def extract_status_url(url: str, preferred_handle: str | None = None) -> str | None:
    return normalize_status_url(url, preferred_handle=preferred_handle)


def parse_dateish(value: str | None) -> dt.date | None:
    if not value:
        return None

    text = html.unescape(value).strip()
    text = re.sub(r"\s+", " ", text)
    if not text:
        return None

    for fmt in (
        "%Y-%m-%d",
        "%B %d, %Y",
        "%b %d, %Y",
        "%I:%M %p · %b %d, %Y",
        "%I:%M %p · %B %d, %Y",
    ):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            pass

    try:
        return parsedate_to_datetime(text).date()
    except (TypeError, ValueError, IndexError):
        pass

    try:
        return dt.datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def keyword_hint_regex() -> re.Pattern[str]:
    return re.compile(r"\b(" + "|".join(re.escape(kw) for kw in KW) + r")\b", re.IGNORECASE)


KW_HINT_RE = keyword_hint_regex()


def looks_actionable(text: str) -> bool:
    lowered = text.lower()
    if KW_HINT_RE.search(text):
        return True
    return any(marker in lowered for marker in ("here's", "here is", "how to", "step-by-step"))


def score_text(text: str) -> int:
    t = text.lower()
    score = 0

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
    if "reposted" in t[:120]:
        score -= 2

    for bad in EXCLUDE_HINTS:
        if bad in t:
            score -= 3

    score += min(len(t) // 240, 3)
    return score


def parse_syndication_timeline_html(html_text: str) -> Dict[str, Any]:
    match = NEXT_DATA_RE.search(html_text)
    if not match:
        raise ValueError("syndication payload missing __NEXT_DATA__")
    payload = json.loads(html.unescape(match.group(1)))
    page_props = payload["props"]["pageProps"]
    context = page_props.get("contextProvider") or {}
    timeline = page_props.get("timeline") or {}
    return {
        "has_results": bool(context.get("hasResults")),
        "entries": timeline.get("entries") or [],
        "latest_tweet_id": timeline.get("latest_tweet_id"),
    }


def fetch_syndication_timeline(handle: str, timeout: int = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    response = requests.get(
        f"https://syndication.twitter.com/srv/timeline-profile/screen-name/{handle}",
        params={"lang": "en", "showHeader": "true", "showReplies": "false", "transparent": "false"},
        headers={"User-Agent": "ai-influence-digest/1.0"},
        timeout=timeout,
    )
    response.raise_for_status()
    return parse_syndication_timeline_html(response.text)


def build_opencli_twitter_queries(handle: str, after: str) -> List[str]:
    keyword_clause = " OR ".join(KW)
    return [
        f"from:{handle} ({keyword_clause}) since:{after}",
        f"from:{handle} since:{after}",
    ]


def run_opencli_twitter_search(query: str, limit: int = 20) -> List[Dict[str, Any]]:
    if not command_exists("opencli"):
        raise FileNotFoundError("opencli not found")

    cmd = [
        "opencli",
        "twitter",
        "search",
        "--filter",
        "live",
        "-f",
        "json",
        "--limit",
        str(limit),
        query,
    ]
    try:
        output = run_opencli_read_only(cmd)
    except subprocess.CalledProcessError as exc:
        if "No search results found" in (exc.output or ""):
            return []
        raise

    data = extract_first_json_value(output)
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def run_opencli_google_search(query: str, limit: int = 20, lang: str = "en") -> List[Dict[str, Any]]:
    if not command_exists("opencli"):
        raise FileNotFoundError("opencli not found")

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
    try:
        output = run_opencli_read_only(cmd)
    except subprocess.CalledProcessError as exc:
        if "No search results found" in (exc.output or ""):
            return []
        raise
    data = extract_first_json_value(output)
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def chunk(items: List[str], size: int) -> List[List[str]]:
    if size <= 0:
        size = 1
    return [items[index : index + size] for index in range(0, len(items), size)]


def discover_urls_syndication(
    handles: List[str],
    cutoff_date: dt.date,
    timeout: int,
    require_actionable: bool,
) -> List[str]:
    urls: List[str] = []
    for idx, handle in enumerate(handles, 1):
        try:
            payload = fetch_syndication_timeline(handle, timeout=timeout)
        except (requests.RequestException, ValueError) as exc:
            log(f"warn: syndication user {idx}/{len(handles)} @{handle} failed: {exc}")
            continue

        entries = payload.get("entries") or []
        user_hits = 0
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("type") != "tweet":
                continue
            content = entry.get("content") or {}
            tweet = content.get("tweet") or {}
            if not isinstance(tweet, dict):
                continue
            created_date = parse_dateish(str(tweet.get("created_at") or ""))
            if created_date and created_date < cutoff_date:
                continue
            text = clean_extracted_text(str(tweet.get("full_text") or tweet.get("text") or ""))
            if require_actionable and text and not looks_actionable(text):
                continue
            permalink = tweet.get("permalink")
            if isinstance(permalink, str) and permalink.strip():
                normalized = normalize_status_url("https://x.com" + permalink)
                if normalized:
                    urls.append(normalized)
                    user_hits += 1
        log(f"syndication user {idx}/{len(handles)} @{handle} -> {user_hits} urls")
    return urls


def discover_urls_opencli(
    handles: List[str],
    after: str,
    _batch_size: int,
    per_search: int,
    _lang: str,
    cutoff_date: dt.date,
    require_actionable: bool,
) -> List[str]:
    urls: List[str] = []
    for idx, handle in enumerate(handles, 1):
        user_hits = 0
        seen_for_user = set()
        for query_index, query in enumerate(build_opencli_twitter_queries(handle, after), 1):
            results = run_opencli_twitter_search(query, limit=per_search)
            for result in results:
                author = str(result.get("author") or "").strip()
                normalized = extract_status_url(str(result.get("url", "")), preferred_handle=author or handle)
                if not normalized:
                    continue

                match = STATUS_RE.search(normalized)
                if not match or match.group(1).lower() != handle.lower():
                    continue

                created_date = parse_dateish(str(result.get("created_at") or ""))
                if created_date and created_date < cutoff_date:
                    continue

                text = clean_extracted_text(str(result.get("text") or ""))
                if require_actionable and text and not looks_actionable(text):
                    continue

                if normalized in seen_for_user:
                    continue

                seen_for_user.add(normalized)
                urls.append(normalized)
                user_hits += 1

            log(f"opencli user {idx}/{len(handles)} @{handle} query#{query_index} -> {len(results)} results")

            if user_hits >= per_search:
                break

        log(f"opencli user {idx}/{len(handles)} @{handle} -> {user_hits} urls")
    return urls


def discover_urls_opencli_google(
    handles: List[str],
    after: str,
    batch_size: int,
    per_search: int,
    lang: str,
    _cutoff_date: dt.date,
    require_actionable: bool,
) -> List[str]:
    urls: List[str] = []
    for batch_index, handle_batch in enumerate(chunk(handles, batch_size), 1):
        lower_handles = {handle.lower() for handle in handle_batch}
        user_hits = 0
        seen_for_batch = set()
        sites = " OR ".join(f"site:x.com/{handle}/status" for handle in handle_batch)
        keyword_clause = " OR ".join(KW)
        queries = [
            f"({sites}) ({keyword_clause}) after:{after}",
            f"({sites}) after:{after}",
        ]

        for query_index, query in enumerate(queries, 1):
            results = run_opencli_google_search(query, limit=per_search, lang=lang)
            for result in results:
                normalized = extract_status_url(str(result.get("url") or ""))
                if not normalized:
                    continue

                match = STATUS_RE.search(normalized)
                if not match or match.group(1).lower() not in lower_handles:
                    continue

                text = clean_extracted_text(
                    f"{str(result.get('title') or '')}\n{str(result.get('snippet') or result.get('description') or '')}"
                )
                if require_actionable and text and not looks_actionable(text):
                    continue

                if normalized in seen_for_batch:
                    continue

                seen_for_batch.add(normalized)
                urls.append(normalized)
                user_hits += 1

            log(f"google batch {batch_index} query#{query_index} -> {len(results)} results")
            if user_hits >= per_search:
                break

        log(f"google batch {batch_index} handles={len(handle_batch)} -> {user_hits} urls")
    return urls


def minimum_auto_urls(handle_count: int, per_search: int) -> int:
    return max(10, min(handle_count, per_search))


def dedupe_urls(urls: Iterable[str]) -> List[str]:
    seen = set()
    unique: List[str] = []
    for url in urls:
        normalized = normalize_status_url(url)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return unique


def discover_status_urls(
    backend: str,
    handles: List[str],
    after: str,
    cutoff_date: dt.date,
    batch_size: int,
    per_search: int,
    lang: str,
    timeout: int,
    require_actionable: bool,
) -> Dict[str, str]:
    target_urls = minimum_auto_urls(len(handles), per_search)
    discovered: Dict[str, str] = {}
    backends = [backend] if backend != "auto" else list(DISCOVER_BACKENDS)

    for raw_name in backends:
        name = "opencli-twitter" if raw_name == "opencli" else raw_name
        try:
            if name == "syndication":
                urls = discover_urls_syndication(handles, cutoff_date, timeout, require_actionable=require_actionable)
            elif name == "opencli-twitter":
                urls = discover_urls_opencli(
                    handles,
                    after,
                    batch_size,
                    per_search,
                    lang,
                    cutoff_date,
                    require_actionable=require_actionable,
                )
            elif name == "opencli-google":
                urls = discover_urls_opencli_google(
                    handles,
                    after,
                    batch_size,
                    per_search,
                    lang,
                    cutoff_date,
                    require_actionable=require_actionable,
                )
            else:
                raise ValueError(f"unsupported discover backend: {raw_name}")
        except (FileNotFoundError, requests.RequestException, subprocess.CalledProcessError, ValueError) as exc:
            log(f"warn: discover backend {raw_name} failed: {exc}")
            urls = []

        before = len(discovered)
        for url in dedupe_urls(urls):
            discovered.setdefault(url, name)
        added = len(discovered) - before
        log(f"discover backend {raw_name} added {added} urls (total={len(discovered)})")

        if backend == "auto" and len(discovered) >= target_urls:
            break

    return discovered


def parse_oembed_payload(payload: Dict[str, Any]) -> Dict[str, str | None]:
    html_fragment = str(payload.get("html", "")).strip()
    if not html_fragment:
        raise ValueError("oEmbed response missing html")

    paragraph_match = OEMBED_PARAGRAPH_RE.search(html_fragment)
    if not paragraph_match:
        raise ValueError("oEmbed html missing paragraph")

    text = strip_html_fragment(paragraph_match.group(1))
    if not text:
        raise ValueError("oEmbed text extraction failed")

    published_date = None
    for anchor_text in reversed(re.findall(r"<a\b[^>]*>(.*?)</a>", html_fragment, flags=re.IGNORECASE | re.DOTALL)):
        parsed = parse_dateish(strip_html_fragment(anchor_text))
        if parsed:
            published_date = parsed.isoformat()
            break

    return {
        "text": text,
        "author_name": str(payload.get("author_name") or "").strip() or None,
        "published_date": published_date,
        "canonical_url": normalize_status_url(str(payload.get("url") or "")),
    }


def fetch_tweet_oembed(status_url: str, timeout: int = DEFAULT_TIMEOUT) -> Dict[str, str | None]:
    response = requests.get(
        "https://publish.x.com/oembed",
        params={"url": status_url, "omit_script": "1"},
        headers={"User-Agent": "ai-influence-digest/1.0"},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("unexpected oEmbed payload")
    info = parse_oembed_payload(payload)
    info["backend"] = "oembed"
    return info


def fetch_tweet_info(status_url: str, backend: str, timeout: int = DEFAULT_TIMEOUT) -> Dict[str, str | None]:
    if backend not in ("auto", "oembed"):
        raise ValueError(f"unsupported fetch backend: {backend}")
    try:
        return fetch_tweet_oembed(status_url, timeout=timeout)
    except (requests.RequestException, ValueError) as exc:
        raise RuntimeError(f"oembed: {exc}") from exc


def load_handles(accounts_path: Path) -> List[str]:
    handles: List[str] = []
    for line in accounts_path.read_text("utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        handles.append(stripped.lstrip("@"))
    return handles


def load_seed_urls(seed_path: Path) -> Dict[str, str]:
    discovered: Dict[str, str] = {}
    for line in seed_path.read_text("utf-8").splitlines():
        normalized = normalize_status_url(line.strip())
        if normalized:
            discovered[normalized] = "seed"
    return discovered


def render_candidates_markdown(
    candidates: List[Dict[str, Any]],
    days: int,
    after: str,
    accounts_count: int,
) -> str:
    lines = [
        f"# X weekly candidates (last {days} days)",
        f"- after: {after}",
        f"- accounts: {accounts_count}",
        f"- collected: {len(candidates)}",
        "",
    ]

    for index, candidate in enumerate(candidates[:60], 1):
        lines.append(f"## {index}. @{candidate['handle']} (score={candidate['score']})")
        lines.append(candidate["url"])
        lines.append("")
        meta_bits = [
            f"discovered_via={candidate['discover_backend']}",
            f"fetched_via={candidate['fetch_backend']}",
        ]
        if candidate.get("published_date"):
            meta_bits.append(f"published_date={candidate['published_date']}")
        lines.append("- " + " | ".join(meta_bits))
        lines.append("")
        lines.append(candidate["text"][:800].strip())
        lines.append("")

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--accounts", default=str(Path(__file__).resolve().parent.parent / "references/accounts_65.txt"))
    parser.add_argument("--seed-urls", default="", help="Optional file with known X status URLs, one per line.")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Handle batch size for opencli-google discovery.",
    )
    parser.add_argument("--per-search", type=int, default=20)
    parser.add_argument("--outdir", default=str(Path.cwd() / "output"))
    parser.add_argument(
        "--lang",
        default="en",
        help="Language passed to opencli-google discovery.",
    )
    parser.add_argument(
        "--discover-backend",
        choices=("auto", "syndication", "opencli", "opencli-google", "opencli-twitter", "none"),
        default="auto",
    )
    parser.add_argument(
        "--fetch-backend",
        choices=("auto", "oembed"),
        default="auto",
    )
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument(
        "--allow-non-actionable",
        action="store_true",
        help="Keep posts even when they do not match actionable keyword heuristics.",
    )
    args = parser.parse_args()

    accounts_path = Path(args.accounts).expanduser().resolve()
    if not accounts_path.exists():
        print(f"accounts file not found: {accounts_path}", file=sys.stderr)
        sys.exit(1)

    handles = load_handles(accounts_path)
    today = dt.date.today()
    cutoff_date = today - dt.timedelta(days=args.days)
    after = cutoff_date.isoformat()

    outdir = Path(args.outdir).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    chrome_profile = os.environ.get("OPENCLI_CHROME_PROFILE", "")
    if chrome_profile:
        log(f"chrome profile: {chrome_profile} (from OPENCLI_CHROME_PROFILE)")
    elif args.discover_backend in ("auto", "opencli-google", "opencli-twitter", "opencli"):
        log("warn: OPENCLI_CHROME_PROFILE not set — make sure the Browser Bridge extension is active in the intended Chrome profile")

    log(
        f"starting scan: accounts={len(handles)} days={args.days} "
        f"discover={args.discover_backend} fetch={args.fetch_backend} outdir={outdir}"
    )

    discovered_urls: Dict[str, str]
    if args.seed_urls:
        seed_path = Path(args.seed_urls).expanduser().resolve()
        if not seed_path.exists():
            print(f"seed urls file not found: {seed_path}", file=sys.stderr)
            sys.exit(1)
        discovered_urls = load_seed_urls(seed_path)
        log(f"loaded {len(discovered_urls)} seed urls from {seed_path}")
    elif args.discover_backend == "none":
        print("discover-backend=none requires --seed-urls", file=sys.stderr)
        sys.exit(1)
    else:
        discovered_urls = discover_status_urls(
            backend=args.discover_backend,
            handles=handles,
            after=after,
            cutoff_date=cutoff_date,
            batch_size=args.batch_size,
            per_search=args.per_search,
            lang=args.lang,
            timeout=args.timeout,
            require_actionable=not args.allow_non_actionable,
        )

    unique_urls = list(discovered_urls.keys())
    log(f"deduped candidate urls: {len(unique_urls)}")

    candidates: List[Dict[str, Any]] = []
    for index, status_url in enumerate(unique_urls, 1):
        try:
            info = fetch_tweet_info(status_url, backend=args.fetch_backend, timeout=args.timeout)
        except Exception as exc:  # pragma: no cover - runtime/network variability
            log(f"warn: fetch failed {status_url} {exc}")
            continue

        text = str(info.get("text") or "").strip()
        if not text:
            continue

        published_date = parse_dateish(str(info.get("published_date") or ""))
        if published_date and published_date < cutoff_date:
            continue

        match = STATUS_RE.search(status_url)
        handle = match.group(1) if match else ""
        canonical_url = normalize_status_url(str(info.get("canonical_url") or status_url)) or status_url
        candidate = {
            "url": canonical_url,
            "handle": handle,
            "author_name": info.get("author_name"),
            "text": text,
            "score": score_text(text),
            "discover_backend": discovered_urls.get(status_url, "seed"),
            "fetch_backend": info.get("backend") or args.fetch_backend,
            "published_date": published_date.isoformat() if published_date else None,
            "fetched_at": dt.datetime.now().isoformat(timespec="seconds"),
        }
        candidates.append(candidate)

        if index % 10 == 0 or index == len(unique_urls):
            log(f"fetched {index}/{len(unique_urls)} urls, kept {len(candidates)} candidates")

    candidates.sort(key=lambda item: item.get("score", 0), reverse=True)

    (outdir / "candidates.json").write_text(json.dumps(candidates, ensure_ascii=False, indent=2) + "\n", "utf-8")
    (outdir / "candidates.md").write_text(
        render_candidates_markdown(candidates, days=args.days, after=after, accounts_count=len(handles)),
        "utf-8",
    )

    print(str(outdir / "candidates.json"))


if __name__ == "__main__":
    main()
