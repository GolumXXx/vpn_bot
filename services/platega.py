import hmac
import json
import logging
import time
import uuid
from typing import Any

import requests

from config import (
    PLATEGA_API_BASE_URL,
    PLATEGA_API_KEY,
    PLATEGA_FAILED_URL,
    PLATEGA_MERCHANT_ID,
    PLATEGA_PAYMENT_METHOD,
    PLATEGA_RETURN_URL,
)


logger = logging.getLogger(__name__)
PLATEGA_CREATE_PAYMENT_PATH = "/api/v2/transaction/process"
PLATEGA_VERIFY_PAYMENT_PATH_TEMPLATE = "/api/v2/transaction/{transaction_id}"
PLATEGA_CURRENCY = "RUB"
PLATEGA_CONFIRMED_STATUS = "CONFIRMED"
PLATEGA_CREATE_RETRY_ATTEMPTS = 3
PLATEGA_CREATE_RETRY_DELAY_SECONDS = 1


class PlategaConfigError(RuntimeError):
    pass


class PlategaAPIError(RuntimeError):
    pass


class PlategaWebhookAuthError(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(PLATEGA_MERCHANT_ID and PLATEGA_API_KEY)


def require_config():
    if not is_configured():
        raise PlategaConfigError("PLATEGA_MERCHANT_ID and PLATEGA_API_KEY are required")


def _api_url(path: str) -> str:
    return f"{PLATEGA_API_BASE_URL.rstrip('/')}/{path.lstrip('/')}"


def _headers() -> dict[str, str]:
    require_config()
    return {
        "Content-Type": "application/json",
        "X-MerchantId": PLATEGA_MERCHANT_ID,
        "X-Secret": PLATEGA_API_KEY,
    }


def _extract_payment_url(data: dict[str, Any]) -> str | None:
    return (
        data.get("payment_url")
        or data.get("paymentUrl")
        or data.get("redirect_url")
        or data.get("redirectUrl")
        or data.get("redirect")
        or data.get("url")
    )


def _extract_payment_id(data: dict[str, Any]) -> str | None:
    value = (
        data.get("transactionId")
        or data.get("transaction_id")
        or data.get("payment_id")
        or data.get("paymentId")
        or data.get("id")
    )
    return str(value).strip() if value else None


def _request_create_payment(body: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(
        _api_url(PLATEGA_CREATE_PAYMENT_PATH),
        headers=_headers(),
        json=body,
        timeout=20,
    )

    if response.status_code != 200:
        logger.error("Platega create payment error: status=%s body=%s", response.status_code, response.text)
        raise PlategaAPIError("Platega error")

    try:
        return response.json()
    except ValueError as exc:
        logger.error("Platega create payment returned invalid JSON: %s", response.text)
        raise PlategaAPIError("Invalid Platega create payment response") from exc


def create_payment(
    user_id: int,
    amount: int,
    tariff_code: str = "1m",
    description: str | None = None,
) -> dict[str, Any]:
    payload_order_id = uuid.uuid4().hex[:12]
    body: dict[str, Any] = {
        "paymentMethod": PLATEGA_PAYMENT_METHOD,
        "paymentDetails": {
            "amount": int(amount),
            "currency": PLATEGA_CURRENCY,
        },
        "description": "VPN subscription",
        "return": PLATEGA_RETURN_URL,
        "failedUrl": PLATEGA_FAILED_URL,
        "payload": f"{user_id}:{payload_order_id}",
    }

    last_error = None
    for attempt in range(PLATEGA_CREATE_RETRY_ATTEMPTS):
        try:
            data = _request_create_payment(body)
            break
        except (requests.RequestException, PlategaAPIError) as exc:
            last_error = exc
            logger.warning(
                "Platega create payment attempt failed: attempt=%s/%s error=%s",
                attempt + 1,
                PLATEGA_CREATE_RETRY_ATTEMPTS,
                exc,
            )
            if attempt < PLATEGA_CREATE_RETRY_ATTEMPTS - 1:
                time.sleep(PLATEGA_CREATE_RETRY_DELAY_SECONDS)
    else:
        raise last_error or PlategaAPIError("Platega error")

    payment_id = _extract_payment_id(data)
    payment_url = _extract_payment_url(data)
    if not payment_id or not payment_url:
        raise PlategaAPIError(f"Invalid Platega create payment response: {data}")

    return {
        "payment_id": payment_id,
        "payment_url": payment_url,
        "status": data.get("status"),
        "currency": PLATEGA_CURRENCY,
        "payload_order_id": payload_order_id,
        "request_payload": body,
        "raw": data,
    }


def verify_payment(transaction_id: str) -> dict[str, Any]:
    transaction_id = str(transaction_id or "").strip()
    if not transaction_id:
        raise ValueError("transaction_id is required")

    response = requests.get(
        _api_url(PLATEGA_VERIFY_PAYMENT_PATH_TEMPLATE.format(transaction_id=transaction_id)),
        headers=_headers(),
        timeout=20,
    )

    if response.status_code != 200:
        logger.error("Platega verify payment error: status=%s body=%s", response.status_code, response.text)
        raise PlategaAPIError("Platega verify payment error")

    try:
        return response.json()
    except ValueError as exc:
        logger.error("Platega verify payment returned invalid JSON: %s", response.text)
        raise PlategaAPIError("Invalid Platega verify payment response") from exc


def verify_webhook_headers(headers) -> None:
    require_config()
    merchant_id = headers.get("X-MerchantId") or headers.get("x-merchantid")
    secret = headers.get("X-Secret") or headers.get("x-secret")

    if not merchant_id or not hmac.compare_digest(str(merchant_id), PLATEGA_MERCHANT_ID):
        raise PlategaWebhookAuthError("Invalid Platega webhook merchant id")
    if not secret or not hmac.compare_digest(str(secret), PLATEGA_API_KEY):
        raise PlategaWebhookAuthError("Invalid Platega webhook secret")


def is_paid_status(status: str | None) -> bool:
    return str(status or "").strip().upper() == PLATEGA_CONFIRMED_STATUS


def extract_payment_id(data: dict[str, Any]) -> str | None:
    return _extract_payment_id(data)


def extract_status(data: dict[str, Any]) -> str | None:
    value = data.get("status") or data.get("payment_status") or data.get("state")
    return str(value).strip() if value else None


def _parse_payload(value) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            logger.warning("Invalid Platega payload JSON: %s", value)
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def extract_metadata(data: dict[str, Any]) -> dict[str, Any]:
    metadata = data.get("metadata")
    if isinstance(metadata, dict):
        return metadata
    return _parse_payload(data.get("payload"))


def extract_user_id_from_payload(data: dict[str, Any]) -> int | None:
    payload = data.get("payload")

    if isinstance(payload, int):
        return payload
    if isinstance(payload, str):
        value = payload.strip()
        if ":" in value:
            value = value.split(":", 1)[0].strip()
        if value.isdigit():
            return int(value)
        parsed_payload = _parse_payload(value)
        user_id = parsed_payload.get("user_id") or parsed_payload.get("telegram_id")
        try:
            return int(user_id) if user_id is not None else None
        except (TypeError, ValueError):
            return None
    if isinstance(payload, dict):
        user_id = payload.get("user_id") or payload.get("telegram_id")
        try:
            return int(user_id) if user_id is not None else None
        except (TypeError, ValueError):
            return None

    return None
