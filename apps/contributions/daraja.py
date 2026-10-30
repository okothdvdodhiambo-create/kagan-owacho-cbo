"""Safaricom Daraja STK Push. Works with sandbox or live credentials from .env.

When credentials are missing the client reports itself as unconfigured so the views can
fall back to manual M-Pesa code entry instead of crashing.
"""

import base64
import logging
from datetime import datetime

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

TOKEN_CACHE_KEY = "daraja_access_token"
SANDBOX_BASE = "https://sandbox.safaricom.co.ke"
LIVE_BASE = "https://api.safaricom.co.ke"


class DarajaNotConfigured(Exception):
    """Raised when M-Pesa keys are absent from .env."""


class DarajaError(Exception):
    pass


class DarajaClient:
    def __init__(self):
        self.env = (settings.MPESA_ENV or "sandbox").lower()
        self.base = LIVE_BASE if self.env == "production" else SANDBOX_BASE
        self.consumer_key = settings.MPESA_CONSUMER_KEY
        self.consumer_secret = settings.MPESA_CONSUMER_SECRET
        self.shortcode = settings.MPESA_SHORTCODE
        self.passkey = settings.MPESA_PASSKEY
        self.callback_url = settings.MPESA_CALLBACK_URL

    @property
    def configured(self):
        return all([self.consumer_key, self.consumer_secret, self.shortcode, self.passkey])

    def require_configuration(self):
        if not self.configured:
            raise DarajaNotConfigured(
                "M-Pesa online payment is not switched on yet: set MPESA_CONSUMER_KEY, "
                "MPESA_CONSUMER_SECRET, MPESA_SHORTCODE and MPESA_PASSKEY in .env."
            )

    # ------------------------------------------------------------------ token
    def access_token(self):
        token = cache.get(TOKEN_CACHE_KEY)
        if token:
            return token
        self.require_configuration()
        url = f"{self.base}/oauth/v1/generate?grant_type=client_credentials"
        try:
            response = requests.get(
                url,
                auth=(self.consumer_key, self.consumer_secret),
                timeout=20,
            )
        except requests.RequestException as exc:
            raise DarajaError(f"Could not reach Safaricom: {exc}") from exc
        if response.status_code != 200:
            raise DarajaError(f"Token request failed (HTTP {response.status_code}): {response.text[:200]}")
        try:
            token = response.json()["access_token"]
        except (KeyError, ValueError) as exc:
            raise DarajaError("Unexpected response while fetching the Daraja token") from exc
        cache.set(TOKEN_CACHE_KEY, token, 3300)
        return token

    def _headers(self):
        return {"Authorization": f"Bearer {self.access_token()}", "Content-Type": "application/json"}

    def _credentials(self, timestamp):
        raw = f"{self.shortcode}{self.passkey}{timestamp}".encode()
        return base64.b64encode(raw).decode()

    # -------------------------------------------------------------- stk push
    def stk_push(self, amount, phone, account_reference, transaction_desc, external_id=""):
        """Ask the member's phone to confirm the payment prompt."""
        self.require_configuration()
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        payload = {
            "BusinessShortCode": self.shortcode,
            "Password": self._credentials(timestamp),
            "Timestamp": timestamp,
            "TransactionType": settings.MPESA_TRANSACTION_TYPE,
            "Amount": int(round(float(amount))),
            "PartyA": phone,
            "PartyB": self.shortcode,
            "PhoneNumber": phone,
            "CallBackURL": self.callback_url,
            "AccountReference": account_reference[:12] or "KAGAN",
            "TransactionDesc": transaction_desc[:90] or "Contribution",
        }
        url = f"{self.base}/mpesa/stkpush/v1/processrequest"
        try:
            response = requests.post(url, json=payload, headers=self._headers(), timeout=25)
        except requests.RequestException as exc:
            raise DarajaError(f"Could not reach Safaricom: {exc}") from exc
        try:
            data = response.json()
        except ValueError:
            raise DarajaError(f"Safaricom replied with HTTP {response.status_code}: {response.text[:200]}")
        if "CheckoutRequestID" not in data:
            raise DarajaError(data.get("errorMessage", f"STK push rejected (HTTP {response.status_code})"))
        return data

    # ---------------------------------------------------------- status check
    def check_status(self, phone, checkout_request_id):
        """Query the result of an STK push (Lipa Na Mpesa Online Query)."""
        self.require_configuration()
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        payload = {
            "BusinessShortCode": self.shortcode,
            "Password": self._credentials(timestamp),
            "Timestamp": timestamp,
            "CheckoutRequestID": checkout_request_id,
        }
        url = f"{self.base}/mpesa/stkpushstatus/v1/query"
        try:
            response = requests.post(url, json=payload, headers=self._headers(), timeout=25)
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise DarajaError(f"Status query failed: {exc}") from exc
        return data.get("QueryResultResponse", data)


def get_client():
    return DarajaClient()
