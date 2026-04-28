import asyncio
import json
import logging
from datetime import datetime, timedelta

from database.connection import DATETIME_FORMAT
from repositories import platega_payment_repo
from services import platega
from services.platega_webhook import (
    PLATEGA_STATUS_PENDING,
    process_confirmed_payment,
)
from utils.rows import row_get


logger = logging.getLogger(__name__)
PLATEGA_PENDING_LOOKBACK_DAYS = 1
PLATEGA_PENDING_CHECK_INTERVAL_SECONDS = 60
PLATEGA_PENDING_CHECK_LIMIT = 100


def _since_created_at() -> str:
    return (
        datetime.now() - timedelta(days=PLATEGA_PENDING_LOOKBACK_DAYS)
    ).strftime(DATETIME_FORMAT)


async def check_pending_payments() -> dict:
    if not platega.is_configured():
        return {"ok": True, "checked": 0, "processed": 0, "configured": False}

    payments = platega_payment_repo.get_recent_by_status(
        PLATEGA_STATUS_PENDING,
        _since_created_at(),
        PLATEGA_PENDING_CHECK_LIMIT,
    )
    processed = 0

    for payment in payments:
        payment_id = row_get(payment, "payment_id")
        if not payment_id:
            continue

        try:
            verified_payment = await asyncio.to_thread(
                platega.verify_payment,
                payment_id,
            )
            verified_status = platega.extract_status(verified_payment)
            if platega.is_paid_status(verified_status):
                await process_confirmed_payment(payment_id, verified_payment)
                processed += 1
                continue

            if verified_status and verified_status != PLATEGA_STATUS_PENDING:
                platega_payment_repo.update_status(
                    payment_id,
                    status=verified_status,
                    webhook_payload=json.dumps(verified_payment, ensure_ascii=False),
                    updated_at=datetime.now().strftime(DATETIME_FORMAT),
                )
        except Exception:
            logger.exception(
                "Failed to check pending Platega payment: payment_id=%s",
                payment_id,
            )

    return {
        "ok": True,
        "checked": len(payments),
        "processed": processed,
        "configured": True,
    }


async def platega_pending_payment_loop():
    while True:
        try:
            result = await check_pending_payments()
            if result.get("checked") or result.get("processed"):
                logger.info("Platega pending payment check result: %s", result)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Unexpected Platega pending payment loop error")

        await asyncio.sleep(PLATEGA_PENDING_CHECK_INTERVAL_SECONDS)
