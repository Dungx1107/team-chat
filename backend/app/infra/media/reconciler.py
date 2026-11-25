"""Recovery khi webhook thiếu: đối soát GROUP, retry cleanup qua trạng thái DB."""
import asyncio
import logging
from contextlib import suppress

from sqlalchemy import or_
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.infra.db.session import SessionLocal
from app.infra.db.models import CallModel
from app.api.dependencies import get_call_service, get_group_media_service

logger = logging.getLogger(__name__)


def _pending_ids():
    with SessionLocal() as db:
        return [row.id for row in db.query(CallModel.id).filter(
            CallModel.mode == "GROUP",
            or_(CallModel.status == "ACTIVE", CallModel.media_cleanup_pending.is_(True)),
        ).all()]


async def reconcile_call(call_id):
    db = SessionLocal()
    try:
        media = get_group_media_service(get_call_service(db))
        await media.sync(call_id)
    finally:
        await run_in_threadpool(db.close)


async def reconcile_groups():
    semaphore = asyncio.Semaphore(4)

    async def one(call_id):
        async with semaphore:
            try:
                await reconcile_call(call_id)
            except Exception:
                logger.warning("Chưa đối soát được GROUP %s; sẽ thử lại", call_id, exc_info=True)

    while True:
        try:
            ids = await run_in_threadpool(_pending_ids)
            await asyncio.gather(*(one(call_id) for call_id in ids))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Không đọc được danh sách GROUP để đối soát", exc_info=True)
        await asyncio.sleep(settings.GROUP_CALL_SYNC_SECONDS)
