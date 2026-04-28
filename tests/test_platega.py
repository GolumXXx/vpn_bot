import unittest
from unittest.mock import patch

from services import platega


class FakeResponse:
    status_code = 200
    text = ""

    def json(self):
        return {
            "transactionId": "tx_123",
            "redirectUrl": "https://pay.example/tx_123",
            "status": "CREATED",
        }


class PlategaTest(unittest.TestCase):
    def test_create_payment_uses_actual_api_contract(self):
        with (
            patch.object(platega, "PLATEGA_API_BASE_URL", "https://app.platega.io"),
            patch.object(platega, "PLATEGA_MERCHANT_ID", "merchant"),
            patch.object(platega, "PLATEGA_API_KEY", "secret"),
            patch.object(platega, "PLATEGA_PAYMENT_METHOD", 2),
            patch.object(platega, "PLATEGA_RETURN_URL", "https://golum.shop/success"),
            patch.object(platega, "PLATEGA_FAILED_URL", "https://golum.shop/fail"),
            patch("services.platega.requests.post", return_value=FakeResponse()) as post,
        ):
            result = platega.create_payment(user_id=12345, amount=89)

        post.assert_called_once()
        _, kwargs = post.call_args
        payload = kwargs["json"].pop("payload")
        self.assertEqual(
            post.call_args.args[0],
            "https://app.platega.io/api/v2/transaction/process",
        )
        self.assertEqual(kwargs["headers"]["X-MerchantId"], "merchant")
        self.assertEqual(kwargs["headers"]["X-Secret"], "secret")
        self.assertRegex(payload, r"^12345:[a-f0-9]{12}$")
        self.assertEqual(
            kwargs["json"],
            {
                "paymentMethod": 2,
                "paymentDetails": {
                    "amount": 89,
                    "currency": "RUB",
                },
                "description": "VPN subscription",
                "return": "https://golum.shop/success",
                "failedUrl": "https://golum.shop/fail",
            },
        )
        self.assertEqual(result["payment_id"], "tx_123")
        self.assertEqual(result["payment_url"], "https://pay.example/tx_123")

    def test_verify_payment_uses_get_transaction_endpoint(self):
        with (
            patch.object(platega, "PLATEGA_API_BASE_URL", "https://app.platega.io"),
            patch.object(platega, "PLATEGA_MERCHANT_ID", "merchant"),
            patch.object(platega, "PLATEGA_API_KEY", "secret"),
            patch("services.platega.requests.get", return_value=FakeResponse()) as get,
        ):
            result = platega.verify_payment("tx_123")

        get.assert_called_once()
        self.assertEqual(
            get.call_args.args[0],
            "https://app.platega.io/api/v2/transaction/tx_123",
        )
        self.assertEqual(get.call_args.kwargs["headers"]["X-MerchantId"], "merchant")
        self.assertEqual(get.call_args.kwargs["headers"]["X-Secret"], "secret")
        self.assertEqual(result["transactionId"], "tx_123")

    def test_webhook_helpers_use_confirmed_status_and_payload_user_id(self):
        self.assertTrue(platega.is_paid_status("CONFIRMED"))
        self.assertFalse(platega.is_paid_status("paid"))
        self.assertEqual(
            platega.extract_user_id_from_payload({"payload": "12345:order_id"}),
            12345,
        )

    def test_webhook_secret_header_is_required(self):
        with (
            patch.object(platega, "PLATEGA_MERCHANT_ID", "merchant"),
            patch.object(platega, "PLATEGA_API_KEY", "secret"),
        ):
            platega.verify_webhook_headers(
                {
                    "X-MerchantId": "merchant",
                    "X-Secret": "secret",
                }
            )
            with self.assertRaises(platega.PlategaWebhookAuthError):
                platega.verify_webhook_headers(
                    {
                        "X-MerchantId": "merchant",
                        "X-Secret": "bad",
                    }
                )


if __name__ == "__main__":
    unittest.main()
