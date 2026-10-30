"""What happens when money arrives: Daraja callbacks, status polling, admin decisions."""

import logging

from django.utils import timezone

from .daraja import DarajaError, DarajaNotConfigured, get_client
from .models import Contribution, MpesaCallback

logger = logging.getLogger(__name__)


def initiate_stk(contribution):
    """Send the prompt; returns (ok, message). Updates the contribution row."""
    client = get_client()
    try:
        client.require_configuration()
    except DarajaNotConfigured as exc:
        contribution.status = Contribution.Status.PENDING
        contribution.result_message = str(exc)
        contribution.save(update_fields=["status", "result_message", "updated_at"])
        return False, str(exc)

    try:
        data = client.stk_push(
            amount=contribution.amount,
            phone=contribution.phone,
            account_reference=contribution.member.membership_no or contribution.member.full_name,
            transaction_desc=f"{contribution.member.membership_no or 'Member'} contribution",
        )
    except DarajaError as exc:
        contribution.status = Contribution.Status.FAILED
        contribution.result_message = str(exc)[:200]
        contribution.save(update_fields=["status", "result_message", "updated_at"])
        return False, f"The M-Pesa prompt could not be sent: {exc}"

    contribution.checkout_request_id = data.get("CheckoutRequestID", "")
    contribution.result_code = str(data.get("ResponseCode", ""))
    contribution.result_message = data.get("ResponseDescription", "")
    contribution.status = Contribution.Status.WAITING
    contribution.save(update_fields=["checkout_request_id", "result_code", "result_message", "status", "updated_at"])
    return True, "Check your phone and enter your M-Pesa PIN to complete the payment."


def apply_callback_payload(payload, source_ip=None):
    """Store a Daraja callback and, when we can, settle the matching contribution."""
    body = payload.get("Body", {}) if isinstance(payload, dict) else {}
    callback = body.get("stkCallback", {}) if isinstance(body, dict) else {}
    checkout_id = callback.get("CheckoutRequestID", "")
    result_code = str(callback.get("ResultCode", ""))
    item = {i.get("Name"): i.get("Value") for i in callback.get("CallbackItem", []) if isinstance(i, dict)}

    contribution = Contribution.objects.filter(checkout_request_id=checkout_id).first() if checkout_id else None
    MpesaCallback.objects.create(
        contribution=contribution,
        checkout_request_id=checkout_id,
        merchant_request_id=str(callback.get("MerchantRequestID", "")),
        result_code=result_code,
        result_desc=callback.get("ResultDesc", "")[:200],
        mpesa_receipt_number=str(item.get("MpesaReceiptNumber", ""))[:30],
        amount=item.get("Amount") or None,
        raw_payload=payload if isinstance(payload, dict) else {},
        source_ip=source_ip,
    )
    if contribution is None:
        return None

    if result_code == "0":
        contribution.status = Contribution.Status.CONFIRMED
        contribution.transaction_id = str(item.get("MpesaReceiptNumber", contribution.transaction_id))
        if contribution.reference != contribution.transaction_id:
            contribution.reference = contribution.transaction_id
        contribution.result_code = result_code
        contribution.result_message = callback.get("ResultDesc", "")[:200]
        contribution.payment_date = timezone.localdate()
        contribution.verified_at = timezone.now()
        contribution.verified_by = None  # confirmed automatically by Safaricom
    else:
        contribution.status = Contribution.Status.FAILED if result_code not in ("1",) else Contribution.Status.CANCELLED
        contribution.result_code = result_code
        contribution.result_message = (callback.get("ResultDesc", "") or "")[:200]
    contribution.save()
    return contribution


def refresh_status(contribution):
    """Poll the Daraja query API for an STK push we are still waiting on."""
    if contribution.status != Contribution.Status.WAITING or not contribution.checkout_request_id:
        return contribution.status
    client = get_client()
    try:
        result = client.check_status(contribution.phone, contribution.checkout_request_id)
    except (DarajaError, DarajaNotConfigured) as exc:
        logger.info("Status query unavailable for %s: %s", contribution.pk, exc)
        return contribution.status

    data = result.get("QueryResultResponse", {}) if isinstance(result, dict) else {}
    description = data.get("ResultDesc", "")
    third_party = data.get("ThirdPartyResponse", {}).get("ThirdPartyRef", {}).get("Coordinates", {}).get("RequestItemID")
    if description:
        contribution.result_message = str(description)[:200]
    if third_party:
        receipt = third_party.get("ReceiptID")
        if receipt:
            contribution.transaction_id = str(receipt)
            contribution.reference = str(receipt)
        contribution.status = Contribution.Status.CONFIRMED
        contribution.payment_date = timezone.localdate()
    elif "Failed" in str(description) or "Cancelled" in str(description):
        contribution.status = Contribution.Status.CANCELLED
    contribution.save()
    return contribution.status


def mark_confirmed(contribution, actor):
    contribution.status = Contribution.Status.CONFIRMED
    contribution.verified_by = actor
    contribution.verified_at = timezone.now()
    if not contribution.payment_date:
        contribution.payment_date = timezone.localdate()
    contribution.save()
    return contribution


def mark_rejected(contribution, actor, reason=""):
    contribution.status = Contribution.Status.REJECTED
    contribution.verified_by = actor
    contribution.verified_at = timezone.now()
    if reason:
        contribution.result_message = reason[:200]
    contribution.save()
    return contribution
