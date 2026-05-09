"""CLI entry point: ``python -m crawler discover`` / ``python -m crawler scrape``."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .pipeline import discover_listing_urls, scrape_listings
from .settings import CrawlerSettings
from .utils import configure_logging


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--from", dest="start_page", type=int, default=1, help="First page (inclusive)")
    p.add_argument("--to", dest="end_page", type=int, default=10, help="Last page (inclusive)")
    p.add_argument("--link-dir", type=Path, default=Path("car_links"))
    p.add_argument("--output-dir", type=Path, default=Path("raw_data"))
    p.add_argument("--cache-dir", type=Path, default=Path("html_cache"))
    p.add_argument("--no-resume", action="store_true", help="Disable cache; refetch everything")
    p.add_argument("--no-headless", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")


def _to_settings(args: argparse.Namespace) -> CrawlerSettings:
    return CrawlerSettings(
        link_dir=args.link_dir,
        output_dir=args.output_dir,
        html_cache_dir=args.cache_dir,
        start_page=args.start_page,
        end_page=args.end_page,
        http_workers=getattr(args, "http_workers", 16),
        selenium_workers=getattr(args, "selenium_workers", 2),
        parser_workers=getattr(args, "parser_workers", 8),
        resume=not args.no_resume,
        headless=not args.no_headless,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="crawler")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_disc = sub.add_parser("discover", help="Crawl search-result pages for listing URLs")
    _add_common(p_disc)

    p_scr = sub.add_parser("scrape", help="Scrape full listing/seller/review data")
    _add_common(p_scr)
    p_scr.add_argument("--http-workers", type=int, default=16)
    p_scr.add_argument("--selenium-workers", type=int, default=2)
    p_scr.add_argument("--parser-workers", type=int, default=8)

    args = parser.parse_args(argv)
    configure_logging(logging.DEBUG if args.verbose else logging.INFO)
    settings = _to_settings(args)

    if args.cmd == "discover":
        discover_listing_urls(settings)
    elif args.cmd == "scrape":
        scrape_listings(settings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
