import logging

from database.db import (
    add_bot_log,
    add_or_update_user,
    create_paid_key,
    extend_key_with_panel,
    get_latest_paid_key_by_tariff,
)
from utils.rows import row_get


logger = logging.getLogger(__name__)


async def fulfill_paid_order(
    telegram_id: int,
    tariff_code: str,
    tariff: dict,
    username: str | None = None,
    first_name: str | None = None,
    order_id: str | None = None,
) -> dict:
    if not tariff:
        raise ValueError(f"Unknown tariff code: {tariff_code}")

    add_or_update_user(
        telegram_id=telegram_id,
        username=username,
        first_name=first_name,
    )

    existing_key = get_latest_paid_key_by_tariff(telegram_id, tariff["name"])
    if existing_key:
        key_id = row_get(existing_key, "id")
        if not key_id:
            raise ValueError(f"Cannot extend key without id for user {telegram_id}")

        new_expires = await extend_key_with_panel(key_id, tariff["days"])
        logger.info(
            "Extended paid VPN key after manual confirmation: user_id=%s tariff=%s key_id=%s expires_at=%s",
            telegram_id,
            tariff_code,
            key_id,
            new_expires,
        )
        add_bot_log(
            "paid_key_extended",
            telegram_id=telegram_id,
            username=username,
            key_id=key_id,
            order_id=order_id,
            message=f"Платный ключ продлён: тариф={tariff_code}, до={new_expires}",
        )
        return {
            "action": "extended",
            "expires_at": new_expires,
            "tariff": tariff,
            "key_id": key_id,
        }

    created_key = await create_paid_key(
        telegram_id=telegram_id,
        tariff_name=tariff["name"],
        duration_days=tariff["days"],
        username=username,
        first_name=first_name,
        traffic_limit_gb=0,
        include_details=True,
        upsert_user=False,
    )
    key_id = row_get(created_key, "key_id")
    logger.info(
        "Created paid VPN key after manual confirmation: user_id=%s tariff=%s days=%s",
        telegram_id,
        tariff_code,
        tariff["days"],
    )
    add_bot_log(
        "paid_key_created",
        telegram_id=telegram_id,
        username=username,
        key_id=key_id,
        order_id=order_id,
        message=f"Платный ключ создан: тариф={tariff_code}, дней={tariff['days']}",
    )
    return {
        "action": "created",
        "expires_at": None,
        "tariff": tariff,
        "key_id": key_id,
    }
