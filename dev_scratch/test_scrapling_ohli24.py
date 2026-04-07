#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional


DEFAULT_URL = "https://ani.ohli24.com/bbs/board.php?bo_table=ing&page=1"
DEFAULT_REFERER = "https://ani.ohli24.com"
DEFAULT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Referer": DEFAULT_REFERER,
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}


@dataclass
class FetchSummary:
    mode: str
    url: str
    ok: bool
    elapsed: float
    status: Optional[int]
    reason: str
    html_length: int
    title: str
    has_list_rows: bool
    has_post_title: bool
    has_item_subject: bool
    has_cloudflare_marker: bool
    has_access_denied: bool
    output_file: Optional[str]
    error: Optional[str] = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Standalone Scrapling tester for ohli24 pages",
    )
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument(
        "--mode",
        choices=["fetcher", "dynamic", "stealthy"],
        default="stealthy",
    )
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--timeout-ms", type=int, default=60000)
    parser.add_argument("--wait-ms", type=int, default=1000)
    parser.add_argument("--headful", action="store_true")
    parser.add_argument("--real-chrome", action="store_true")
    parser.add_argument("--disable-resources", action="store_true")
    parser.add_argument("--solve-cloudflare", action="store_true")
    parser.add_argument("--network-idle", action="store_true")
    parser.add_argument("--proxy", default="")
    parser.add_argument("--save-html", action="store_true")
    parser.add_argument("--output-dir", default="dev_scratch/output_scrapling")
    return parser.parse_args()


def get_fetcher(mode: str) -> Any:
    try:
        from scrapling.fetchers import DynamicFetcher, Fetcher, StealthyFetcher
    except ImportError as exc:
        raise RuntimeError(
            "scrapling 이 설치되어 있지 않습니다. "
            '예: pip install "scrapling[fetchers]"'
        ) from exc

    mapping = {
        "fetcher": Fetcher,
        "dynamic": DynamicFetcher,
        "stealthy": StealthyFetcher,
    }
    return mapping[mode]


def extract_html(response: Any) -> str:
    for attr in ("html_content", "text", "html"):
        value = getattr(response, attr, None)
        if callable(value):
            try:
                value = value()
            except TypeError:
                value = None
        if isinstance(value, str) and value:
            return value
    body = getattr(response, "body", None)
    if isinstance(body, bytes):
        return body.decode("utf-8", errors="ignore")
    if isinstance(body, str):
        return body
    return ""


def extract_title(html: str) -> str:
    start = html.lower().find("<title")
    if start == -1:
        return ""
    start = html.find(">", start)
    end = html.lower().find("</title>", start)
    if start == -1 or end == -1:
        return ""
    return html[start + 1 : end].strip()


def has_marker(html: str, marker: str) -> bool:
    return marker.lower() in html.lower()


def build_kwargs(args: argparse.Namespace) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "timeout": args.timeout_ms,
        "extra_headers": dict(DEFAULT_HEADERS),
    }
    if args.proxy:
        kwargs["proxy"] = args.proxy

    if args.mode in ("dynamic", "stealthy"):
        kwargs.update(
            {
                "headless": not args.headful,
                "wait": args.wait_ms,
                "network_idle": args.network_idle,
                "disable_resources": args.disable_resources,
                "google_search": False,
                "real_chrome": args.real_chrome,
            }
        )

    if args.mode == "stealthy":
        kwargs["solve_cloudflare"] = args.solve_cloudflare

    return kwargs


def maybe_save_html(args: argparse.Namespace, index: int, html: str) -> Optional[str]:
    if not args.save_html or not html:
        return None
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"scrapling_{args.mode}_{index:02d}.html"
    output_path.write_text(html, encoding="utf-8")
    return str(output_path)


def run_once(args: argparse.Namespace, index: int) -> FetchSummary:
    fetcher = get_fetcher(args.mode)
    kwargs = build_kwargs(args)

    started = time.time()
    try:
        if args.mode == "fetcher":
            response = fetcher.get(args.url, **kwargs)
        else:
            response = fetcher.fetch(args.url, **kwargs)
        elapsed = time.time() - started
        html = extract_html(response)
        output_file = maybe_save_html(args, index, html)
        lowered = html.lower()
        return FetchSummary(
            mode=args.mode,
            url=args.url,
            ok=bool(html),
            elapsed=elapsed,
            status=getattr(response, "status", None),
            reason=str(getattr(response, "reason", "") or ""),
            html_length=len(html),
            title=extract_title(html),
            has_list_rows="list-row" in lowered,
            has_post_title="post-title" in lowered,
            has_item_subject="item-subject" in lowered,
            has_cloudflare_marker=has_marker(html, "cloudflare")
            or has_marker(html, "just a moment")
            or has_marker(html, "cf-browser-verification"),
            has_access_denied=has_marker(html, "access denied")
            or has_marker(html, "error 403"),
            output_file=output_file,
        )
    except Exception as exc:
        elapsed = time.time() - started
        return FetchSummary(
            mode=args.mode,
            url=args.url,
            ok=False,
            elapsed=elapsed,
            status=None,
            reason="exception",
            html_length=0,
            title="",
            has_list_rows=False,
            has_post_title=False,
            has_item_subject=False,
            has_cloudflare_marker=False,
            has_access_denied=False,
            output_file=None,
            error=f"{type(exc).__name__}: {exc}",
        )


def main() -> int:
    args = parse_args()
    print(
        json.dumps(
            {
                "mode": args.mode,
                "url": args.url,
                "repeat": args.repeat,
                "timeout_ms": args.timeout_ms,
                "headless": not args.headful,
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    results: list[FetchSummary] = []
    for index in range(1, args.repeat + 1):
        summary = run_once(args, index)
        results.append(summary)
        print(json.dumps(asdict(summary), ensure_ascii=False, indent=2))

    success_count = sum(1 for item in results if item.ok)
    print(
        json.dumps(
            {
                "success_count": success_count,
                "total": len(results),
                "avg_elapsed": round(sum(item.elapsed for item in results) / max(len(results), 1), 3),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if success_count else 1


if __name__ == "__main__":
    sys.exit(main())
