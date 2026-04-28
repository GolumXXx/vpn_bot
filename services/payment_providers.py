from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any

from database.connection import DATETIME_FORMAT
from database.db import create_manual_payment, get_manual_payment_by_order_id
from repositories import platega_payment_repo
from services import platega
from utils.rows import row_get


@dataclass(frozen=True)
class PaymentCreateResult:
    provider: str
    payment_id: str | None
    status: str | None
    payment_url: str | None = None
    raw_payment: Any = None


@dataclass(frozen=True)
class PaymentCheckResult:
    provider: str
    payment_id: str
    status: str | None
    raw_payment: Any = None


class PaymentProvider(ABC):
    provider = "base"

    @abstractmethod
    def create_payment(self, *, telegram_id: int, tariff_code: str, amount: int | None = None) -> PaymentCreateResult:
        raise NotImplementedError

    @abstractmethod
    def check_payment(self, *, payment_id: str) -> PaymentCheckResult:
        raise NotImplementedError


class ManualPaymentProvider(PaymentProvider):
    provider = "manual"

    def __init__(self, payment_url_by_tariff):
        self.payment_url_by_tariff = payment_url_by_tariff

    def create_payment(self, *, telegram_id: int, tariff_code: str, amount: int | None = None) -> PaymentCreateResult:
        payment = create_manual_payment(telegram_id=telegram_id, tariff_code=tariff_code)
        payment_id = row_get(payment, "order_id")
        return PaymentCreateResult(
            provider=self.provider,
            payment_id=payment_id,
            status=row_get(payment, "status"),
            payment_url=self.payment_url_by_tariff(tariff_code),
            raw_payment=payment,
        )

    def check_payment(self, *, payment_id: str) -> PaymentCheckResult:
        payment = get_manual_payment_by_order_id(payment_id)
        return PaymentCheckResult(
            provider=self.provider,
            payment_id=payment_id,
            status=row_get(payment, "status"),
            raw_payment=payment,
        )


class CryptoPaymentProvider(PaymentProvider):
    provider = "crypto"

    def create_payment(self, *, telegram_id: int, tariff_code: str, amount: int | None = None) -> PaymentCreateResult:
        raise NotImplementedError("Crypto payment provider is not configured")

    def check_payment(self, *, payment_id: str) -> PaymentCheckResult:
        raise NotImplementedError("Crypto payment provider is not configured")


class YooKassaPaymentProvider(PaymentProvider):
    provider = "yookassa"

    def create_payment(self, *, telegram_id: int, tariff_code: str, amount: int | None = None) -> PaymentCreateResult:
        raise NotImplementedError("YooKassa payment provider is not configured")

    def check_payment(self, *, payment_id: str) -> PaymentCheckResult:
        raise NotImplementedError("YooKassa payment provider is not configured")


class StarsPaymentProvider(PaymentProvider):
    provider = "stars"

    def create_payment(self, *, telegram_id: int, tariff_code: str, amount: int | None = None) -> PaymentCreateResult:
        raise NotImplementedError("Telegram Stars payment provider is not configured")

    def check_payment(self, *, payment_id: str) -> PaymentCheckResult:
        raise NotImplementedError("Telegram Stars payment provider is not configured")


class PlategaPaymentProvider(PaymentProvider):
    provider = "platega"

    def create_payment(self, *, telegram_id: int, tariff_code: str, amount: int | None = None) -> PaymentCreateResult:
        if amount is None:
            raise ValueError("amount is required for Platega payment")

        result = platega.create_payment(
            user_id=telegram_id,
            amount=amount,
            tariff_code=tariff_code,
        )
        now = datetime.now().strftime(DATETIME_FORMAT)
        payment_id = result["payment_id"]
        platega_payment_repo.insert_payment(
            payment_id=payment_id,
            telegram_id=telegram_id,
            tariff_code=tariff_code,
            amount=amount,
            currency=result["currency"],
            status="pending",
            payment_url=result["payment_url"],
            request_payload=json.dumps(result["request_payload"], ensure_ascii=False),
            created_at=now,
            updated_at=now,
        )
        return PaymentCreateResult(
            provider=self.provider,
            payment_id=payment_id,
            status=result.get("status") or "pending",
            payment_url=result["payment_url"],
            raw_payment=result,
        )

    def check_payment(self, *, payment_id: str) -> PaymentCheckResult:
        payment = platega_payment_repo.get_by_payment_id(payment_id)
        return PaymentCheckResult(
            provider=self.provider,
            payment_id=payment_id,
            status=row_get(payment, "status"),
            raw_payment=payment,
        )
