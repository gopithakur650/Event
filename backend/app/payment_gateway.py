import hashlib
import hmac

import requests
from flask import current_app


class PaymentProviderError(Exception):
    pass


class RazorpayGateway:
    base_url = "https://api.razorpay.com/v1"

    def __init__(self):
        self.key_id = current_app.config.get("RAZORPAY_KEY_ID")
        self.key_secret = current_app.config.get("RAZORPAY_KEY_SECRET")
        if not self.key_id or not self.key_secret:
            raise PaymentProviderError("Razorpay credentials are not configured")

    def _request(self, method, path, **kwargs):
        try:
            response = requests.request(
                method,
                f"{self.base_url}{path}",
                auth=(self.key_id, self.key_secret),
                timeout=(5, 15),
                **kwargs,
            )
        except requests.RequestException as error:
            raise PaymentProviderError("Payment provider is temporarily unavailable") from error
        if not response.ok:
            raise PaymentProviderError("Payment provider rejected the request")
        try:
            return response.json()
        except ValueError as error:
            raise PaymentProviderError("Payment provider returned an invalid response") from error

    def create_order(self, amount, currency, receipt, notes, expire_by):
        return self._request("POST", "/orders", json={
            "amount": amount,
            "currency": currency,
            "receipt": receipt,
            "notes": notes,
            "expire_by": expire_by,
        })

    def fetch_payment(self, payment_id):
        return self._request("GET", f"/payments/{payment_id}")

    def refund_payment(self, payment_id, amount):
        return self._request("POST", f"/payments/{payment_id}/refund", json={
            "amount": amount,
        })

    def verify_payment_signature(self, order_id, payment_id, signature):
        body = f"{order_id}|{payment_id}".encode()
        expected = hmac.new(self.key_secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)
