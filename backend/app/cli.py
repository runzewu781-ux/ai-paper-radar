import argparse
import logging
import sys

from app.db.session import SessionLocal
from app.services.ingestion.pipeline import SyncPipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def cmd_sync(args):
    db = SessionLocal()
    try:
        pipeline = SyncPipeline(db)
        logger.info("Starting arXiv sync: days=%d, categories=%s, max=%s", args.days, args.categories, args.max)
        sync_run = pipeline.run_arxiv_sync(
            days=args.days,
            categories=args.categories,
            max_results=args.max,
        )
        logger.info(
            "Sync complete: id=%d status=%s new=%d version=%d",
            sync_run.id, sync_run.status, sync_run.new_paper_count, sync_run.new_version_count,
        )

        if not args.skip_enrich:
            logger.info("Starting enrichment...")
            results = pipeline.run_enrich()
            logger.info("Enrich results: %s", results)

    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="AI Paper Radar CLI")
    sub = parser.add_subparsers(dest="command")

    sync_parser = sub.add_parser("sync", help="Run arXiv sync pipeline")
    sync_parser.add_argument("--days", type=int, default=1, help="Days to look back")
    sync_parser.add_argument("--categories", nargs="+", default=None, help="arXiv categories")
    sync_parser.add_argument("--max", type=int, default=None, help="Max papers to fetch")
    sync_parser.add_argument("--skip-enrich", action="store_true", help="Skip HF/GitHub enrichment")

    args = parser.parse_args()
    if args.command == "sync":
        cmd_sync(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
