"""
CLI entrypoint for the crawler.

Invoked on the host (via run_local.sh) or wrapped by Temporal activities.
Each subcommand processes ONE page:

    python -m crawler.main crawl-links   --page 7
    python -m crawler.main scrape-detail --page 7
    python -m crawler.main upload-gcs    --page 7
    python -m crawler.main full          --page 7   # all 3 in one shot
"""
from __future__ import annotations

import argparse
import sys

from crawler.config import (
    LINK_FOLDER,
    MAX_BROWSER_WORKERS,
    PAGE_NUMBER,
    RAW_DATA_DIR,
)
from crawler.detail_scraper import scrape_from_files_parallel
from crawler.gcs_uploader import upload_to_gcs
from crawler.link_crawler import crawl_listing_urls
from crawler.logging_setup import get_logger

log = get_logger("crawler.main")


def _cmd_crawl_links(args: argparse.Namespace) -> int:
    crawl_listing_urls(
        start_page=args.page,
        end_page=args.page,
        output_dir=LINK_FOLDER,
    )
    return 0


def _cmd_scrape_detail(args: argparse.Namespace) -> int:
    result = scrape_from_files_parallel(
        from_page=args.page,
        to_page=args.page,
        link_folder=LINK_FOLDER,
        output_root=RAW_DATA_DIR,
        n_workers=args.workers,
    )
    # Non-zero exit on total failure so the caller (Temporal activity) sees it.
    if result["done"] == 0 and result["fail"] > 0:
        log.error("All URLs failed for page %s", args.page)
        return 1
    return 0


def _cmd_upload_gcs(args: argparse.Namespace) -> int:
    upload_to_gcs(from_page=args.page, to_page=args.page)
    return 0


def _cmd_full(args: argparse.Namespace) -> int:
    """Run all three stages back-to-back for the given page."""
    rc = _cmd_crawl_links(args)
    if rc:
        return rc
    rc = _cmd_scrape_detail(args)
    if rc:
        return rc
    return _cmd_upload_gcs(args)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="crawler", description="Cars.com weekly crawler")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument(
            "--page",
            type=int,
            default=PAGE_NUMBER,
            help="Page number to process (default: env PAGE_NUMBER or 1)",
        )

    p_links = sub.add_parser("crawl-links", help="Collect detail URLs for one page")
    add_common(p_links)
    p_links.set_defaults(func=_cmd_crawl_links)

    p_detail = sub.add_parser("scrape-detail", help="Scrape detail pages for one page")
    add_common(p_detail)
    p_detail.add_argument("--workers", type=int, default=MAX_BROWSER_WORKERS)
    p_detail.set_defaults(func=_cmd_scrape_detail)

    p_upload = sub.add_parser("upload-gcs", help="Upload JSON + images for one page")
    add_common(p_upload)
    p_upload.set_defaults(func=_cmd_upload_gcs)

    p_full = sub.add_parser("full", help="Run crawl-links + scrape-detail + upload-gcs")
    add_common(p_full)
    p_full.add_argument("--workers", type=int, default=MAX_BROWSER_WORKERS)
    p_full.set_defaults(func=_cmd_full)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    log.info("Running command=%s page=%s", args.cmd, args.page)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
