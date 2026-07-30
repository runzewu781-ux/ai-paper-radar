import asyncio
import logging
from datetime import datetime

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


async def periodic_sync():
    from app.db.session import SessionLocal
    from app.services.ingestion.pipeline import SyncPipeline

    while True:
        await asyncio.sleep(settings.scheduler_interval_minutes * 60)
        logger.info("Scheduled sync triggered at %s", datetime.utcnow().isoformat())
        db = SessionLocal()
        try:
            pipeline = SyncPipeline(db)
            sync_run = pipeline.run_arxiv_sync(days=1)
            logger.info(
                "Scheduled sync done: id=%d new=%d",
                sync_run.id, sync_run.new_paper_count,
            )
            pipeline.run_enrich()
            pipeline._translate_new_papers()
        except Exception as e:
            logger.exception("Scheduled sync failed: %s", e)
        finally:
            db.close()


def start_scheduler(app):
    if not settings.scheduler_enabled:
        logger.info("Scheduler disabled")
        return

    @app.on_event("startup")
    async def _start():
        logger.info(
            "Scheduler started: every %d minutes", settings.scheduler_interval_minutes
        )
        asyncio.create_task(periodic_sync())
