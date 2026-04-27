import logging
from dataclasses import dataclass
from typing import Any

from database.db import (
    TrialAlreadyUsedError,
    add_bot_log,
    create_trial_key,
    delete_key_completely,
    extend_key_with_panel,
    get_key_by_id,
    get_user,
    get_user_keys,
)
from utils.rows import row_get


logger = logging.getLogger(__name__)


@dataclass
class AdminKeyActionResult:
    success: bool
    message: str | None = None
    key: Any = None
    user: Any = None
    keys: list[Any] | None = None
    expires_at: str | None = None


async def create_trial_subscription(
    telegram_id: int,
    username: str | None = None,
    first_name: str | None = None,
) -> int | None:
    created_key = await create_trial_key(
        telegram_id=telegram_id,
        username=username,
        first_name=first_name,
        include_details=True,
    )
    logger.info("Created trial VPN key: user_id=%s", telegram_id)
    key_id = row_get(created_key, "key_id")
    add_bot_log(
        "trial_key_created",
        telegram_id=telegram_id,
        username=username,
        key_id=key_id,
        message="Пробный VPN-ключ создан",
    )
    return key_id


def log_key_issue_error(telegram_id: int, username: str | None, message: str) -> None:
    add_bot_log(
        "key_issue_error",
        telegram_id=telegram_id,
        username=username,
        message=message,
    )


async def extend_user_key(
    key_id: int,
    duration_days: int,
    telegram_id: int,
    username: str | None = None,
) -> Any:
    await extend_key_with_panel(key_id, duration_days)
    logger.info(
        "Extended VPN key: user_id=%s key_id=%s days=%s",
        telegram_id,
        key_id,
        duration_days,
    )
    updated_key = get_key_by_id(key_id)
    add_bot_log(
        "key_extended",
        telegram_id=telegram_id,
        username=username,
        key_id=key_id,
        message=f"Ключ продлён на {duration_days} дней",
    )
    return updated_key


async def extend_key_by_admin(key_id: int, admin_id: int) -> AdminKeyActionResult:
    key = get_key_by_id(key_id)
    if not key:
        return AdminKeyActionResult(success=False, message="Ключ не найден")

    new_expires = await extend_key_with_panel(key_id, 30)
    telegram_id = row_get(key, "telegram_id")
    user = get_user(telegram_id)
    add_bot_log(
        "key_extended_admin",
        telegram_id=telegram_id,
        username=row_get(user, "username"),
        key_id=key_id,
        message=f"Ключ продлён админом {admin_id} до {new_expires}",
    )
    keys = get_user_keys(telegram_id)
    return AdminKeyActionResult(
        success=True,
        key=key,
        user=user,
        keys=keys,
        expires_at=new_expires,
    )


async def delete_key_by_admin(key_id: int, admin_id: int) -> AdminKeyActionResult:
    key = get_key_by_id(key_id)
    if not key:
        return AdminKeyActionResult(success=False, message="Ключ не найден")

    telegram_id = row_get(key, "telegram_id")
    success, message = await delete_key_completely(key_id)
    if not success:
        return AdminKeyActionResult(success=False, message=message, key=key)

    user = get_user(telegram_id)
    add_bot_log(
        "key_deleted_admin",
        telegram_id=telegram_id,
        username=row_get(user, "username"),
        key_id=key_id,
        message=message or f"Ключ удалён админом {admin_id}",
    )
    keys = get_user_keys(telegram_id)
    return AdminKeyActionResult(
        success=True,
        message=message,
        key=key,
        user=user,
        keys=keys,
    )
