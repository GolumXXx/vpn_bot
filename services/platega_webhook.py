import json
import logging
from datetime import datetime
from typing import Any

from aiogram import Bot

from config import BOT_TOKEN, SHORT_LINK_BASE_URL
from core.tariffs import TARIFFS
from database.connection import DATETIME_FORMAT
from database.db import (
    add_bot_log,
    get_key_by_id,
    get_user,
)
from keyboards import payment_done_menu
from repositories import platega_payment_repo
from services import platega
from services.payment_service import fulfill_paid_order
from services.short_links import create_short_link, resolve_vless_link
from utils.rows import row_get


logger = logging.getLogger(__name__)

PLATEGA_STATUS_PENDING = "pending"
PLATEGA_STATUS_PROCESSING = "processing"
PLATEGA_STATUS_PAID = "paid"
PLATEGA_LEGACY_STATUS_APPROVED = "approved"
PLATEGA_STATUS_FAILED = "failed"
PLATEGA_FINAL_STATUSES = {
    PLATEGA_STATUS_PAID,
    PLATEGA_LEGACY_STATUS_APPROVED,
}
PLATEGA_PROCESSABLE_STATUSES = (
    PLATEGA_STATUS_PENDING,
    PLATEGA_STATUS_FAILED,
)


def _now() -> str:
    return datetime.now().strftime(DATETIME_FORMAT)


def _extract_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_amount(data: dict[str, Any]) -> int | None:
    payment_details = data.get("paymentDetails")
    if not isinstance(payment_details, dict):
        payment_details = {}

    return _extract_int(
        data.get("amount")
        or data.get("payment_amount")
        or payment_details.get("amount")
    )


def _ensure_payment_record(payment_id: str, data: dict[str, Any]):
    payment = platega_payment_repo.get_by_payment_id(payment_id)
    if payment:
        return payment

    telegram_id = platega.extract_user_id_from_payload(data)
    tariff_code = "1m"
    tariff = TARIFFS.get(tariff_code)
    if not telegram_id or not tariff:
        return None

    now = _now()
    platega_payment_repo.insert_payment(
        payment_id=payment_id,
        telegram_id=telegram_id,
        tariff_code=tariff_code,
        amount=_extract_amount(data) or tariff["price"],
        currency="RUB",
        status=PLATEGA_STATUS_PENDING,
        payment_url=None,
        request_payload=json.dumps(data, ensure_ascii=False),
        created_at=now,
        updated_at=now,
    )
    return platega_payment_repo.get_by_payment_id(payment_id)


def _build_short_url(key_id: int | None) -> str | None:
    if not key_id:
        return None

    key = get_key_by_id(key_id)
    key_value = row_get(key, "key_value")
    vless = resolve_vless_link(key_value)
    if not vless:
        return None

    return create_short_link(vless, base_url=SHORT_LINK_BASE_URL)


def _build_user_message(tariff: dict, result: dict, short_url: str | None) -> str:
    action_text = "Подписка продлена." if result["action"] == "extended" else "VPN уже готов к использованию."
    lines = [
        "Оплата подтверждена ✅",
        "",
        f"Тариф: {tariff['label']}",
        action_text,
    ]

    if result.get("expires_at"):
        lines.append(f"Действует до: {result['expires_at']}")
    if short_url:
        lines.extend(["", f"Ключ: {short_url}"])

    return "\n".join(lines)


async def _notify_user(telegram_id: int, text: str):
    if not BOT_TOKEN:
        logger.error("Cannot notify Platega payment user: BOT_TOKEN is not configured")
        return

    bot = Bot(token=BOT_TOKEN)
    try:
        await bot.send_message(
            chat_id=telegram_id,
            text=text,
            reply_markup=payment_done_menu,
        )
    finally:
        await bot.session.close()


async def process_confirmed_payment(payment_id: str, data: dict[str, Any]) -> dict[str, Any]:
    payment = _ensure_payment_record(payment_id, data)
    if not payment:
        logger.warning("Platega webhook for unknown payment_id=%s", payment_id)
        return {"ok": True, "processed": False, "reason": "unknown_payment"}

    if row_get(payment, "status") in PLATEGA_FINAL_STATUSES:
        return {"ok": True, "processed": False, "duplicate": True}

    started = platega_payment_repo.start_processing(
        payment_id,
        status=PLATEGA_STATUS_PROCESSING,
        webhook_payload=json.dumps(data, ensure_ascii=False),
        updated_at=_now(),
        allowed_statuses=PLATEGA_PROCESSABLE_STATUSES,
    )
    if not started:
        payment = platega_payment_repo.get_by_payment_id(payment_id)
        return {
            "ok": True,
            "processed": False,
            "status": row_get(payment, "status"),
        }

    payment = platega_payment_repo.get_by_payment_id(payment_id)
    telegram_id = row_get(payment, "telegram_id")
    tariff_code = row_get(payment, "tariff_code")
    tariff = TARIFFS.get(tariff_code)
    user = get_user(telegram_id) if telegram_id else None

    try:
        if not telegram_id or not tariff:
            raise ValueError(f"Invalid Platega payment payload: payment_id={payment_id}")

        result = await fulfill_paid_order(
            telegram_id=telegram_id,
            tariff_code=tariff_code,
            tariff=tariff,
            username=row_get(user, "username"),
            first_name=row_get(user, "first_name"),
            order_id=payment_id,
        )
        short_url = _build_short_url(result.get("key_id"))
    except Exception:
        platega_payment_repo.update_status(
            payment_id,
            status=PLATEGA_STATUS_FAILED,
            updated_at=_now(),
        )
        logger.exception("Failed to process paid Platega webhook: payment_id=%s", payment_id)
        raise

    platega_payment_repo.mark_processed(
        payment_id,
        status=PLATEGA_STATUS_PAID,
        processed_at=_now(),
        updated_at=_now(),
        expected_status=PLATEGA_STATUS_PROCESSING,
    )
    try:
        add_bot_log(
            "platega_payment_approved",
            telegram_id=telegram_id,
            username=row_get(user, "username"),
            key_id=result.get("key_id"),
            order_id=payment_id,
            message=f"Platega оплата подтверждена: тариф={tariff_code}",
        )
    except Exception:
        logger.exception("Failed to write Platega payment log: payment_id=%s", payment_id)

    try:
        await _notify_user(
            telegram_id,
            _build_user_message(tariff, result, short_url),
        )
    except Exception:
        logger.exception(
            "Failed to notify user about paid Platega payment: payment_id=%s user_id=%s",
            payment_id,
            telegram_id,
        )
    return {
        "ok": True,
        "processed": True,
        "payment_id": payment_id,
        "telegram_id": telegram_id,
        "key_id": result.get("key_id"),
        "short_url": short_url,
    }


async def process_webhook(data: dict[str, Any], headers) -> dict[str, Any]:
    platega.verify_webhook_headers(headers)

    payment_id = platega.extract_payment_id(data)
    status = platega.extract_status(data)
    logger.info(
        "Received Platega webhook: payment_id=%s status=%s payload=%s",
        payment_id,
        status,
        data,
    )

    if not payment_id:
        return {"ok": False, "reason": "missing_payment_id"}

    if not platega.is_paid_status(status):
        platega_payment_repo.update_status(
            payment_id,
            status=status or PLATEGA_STATUS_PENDING,
            webhook_payload=json.dumps(data, ensure_ascii=False),
            updated_at=_now(),
        )
        return {"ok": True, "processed": False, "status": status}

    verified_payment = platega.verify_payment(payment_id)
    verified_status = platega.extract_status(verified_payment)
    if not platega.is_paid_status(verified_status):
        platega_payment_repo.update_status(
            payment_id,
            status=verified_status or PLATEGA_STATUS_PENDING,
            webhook_payload=json.dumps(data, ensure_ascii=False),
            updated_at=_now(),
        )
        return {
            "ok": True,
            "processed": False,
            "status": verified_status,
            "verified": True,
        }

    return await process_confirmed_payment(payment_id, verified_payment or data)
