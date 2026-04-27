from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from database.db import create_manual_payment, get_manual_payment_by_order_id
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
