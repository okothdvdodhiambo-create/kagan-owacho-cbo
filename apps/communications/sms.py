"""Swappable SMS gateway. Currently Africa's Talking, with a console fallback.

To add another provider, subclass SMSBackend and register it in get_sms_backend().
"""

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class SMSResult:
    def __init__(self, sent, detail, provider_message_id=""):
        self.sent = sent
        self.detail = detail
        self.provider_message_id = provider_message_id

    def __bool__(self):
        return self.sent

    def __repr__(self):
        return f"<SMSResult sent={self.sent} detail={self.detail!r}>"


class SMSBackend:
    provider = "base"

    def send(self, phone, message):
        raise NotImplementedError


class ConsoleSMSBackend(SMSBackend):
    """Development fallback: prints the message instead of paying for SMS."""

    provider = "console"

    def send(self, phone, message):
        if settings.DEBUG:
            banner = "=" * 62
            print(f"\n{banner}\n[SMS -> {phone}]\n{message}\n{banner}\n")
        logger.info("Console SMS to %s: %s", phone, message)
        return SMSResult(True, "printed to the console (development mode)")


class AfricaTalkingSMSBackend(SMSBackend):
    """Africa's Talking SMS API (https://docs.africastalking.com/sms)."""

    provider = "africastalking"
    endpoint = "https://api.africastalking.com/version1/messaging"

    def __init__(self, username, api_key, sender_id):
        self.username = username
        self.api_key = api_key
        self.sender_id = sender_id or username

    def send(self, phone, message):
        payload = {
            "username": self.username,
            "to": phone,
            "message": message,
            "from": self.sender_id,
        }
        try:
            response = requests.post(
                self.endpoint,
                data=payload,
                headers={"apikey": self.api_key, "content-type": "application/x-www-form-urlencoded"},
                timeout=20,
            )
        except requests.RequestException as exc:
            logger.warning("Africa's Talking request failed: %s", exc)
            return SMSResult(False, f"network error: {exc}")
        if response.status_code != 200:
            return SMSResult(False, f"HTTP {response.status_code}: {response.text[:200]}")
        try:
            statuses = response.json()["SMSMessageData"]["Recipients"]
        except (KeyError, ValueError):
            return SMSResult(False, "unexpected response from Africa's Talking")
        if not statuses:
            return SMSResult(False, "no recipient accepted")
        first = statuses[0]
        sent = str(first.get("status", "")).lower() in {"success", "queued", "sent", "delivered"}
        return SMSResult(sent, first.get("messageId", first.get("status", "")), first.get("messageId", ""))


_active_backend = None


def get_sms_backend():
    global _active_backend
    if _active_backend is not None:
        return _active_backend
    provider = (settings.SMS_PROVIDER or "console").lower()
    if provider == "africastalking" and settings.AFRICASTALKING_API_KEY and settings.AFRICASTALKING_USERNAME:
        _active_backend = AfricaTalkingSMSBackend(
            settings.AFRICASTALKING_USERNAME, settings.AFRICASTALKING_API_KEY, settings.AFRICASTALKING_SENDER_ID
        )
    else:
        if provider == "africastalking":
            logger.warning("SMS_PROVIDER=africastalking but no API key in .env - using console SMS instead.")
        _active_backend = ConsoleSMSBackend()
    return _active_backend


def reset_sms_backend():
    global _active_backend
    _active_backend = None


def send_sms(phone, message):
    if not phone:
        return SMSResult(False, "no phone number supplied")
    backend = get_sms_backend()
    return backend.send(phone, message)
