"""The registration -> code -> verified membership flow, in one place."""

import logging

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.db import transaction
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .models import Member, VerificationCode

logger = logging.getLogger(__name__)


@transaction.atomic
def save_registration(form, request=None, user=None):
    """Create or refresh a pending membership and issue a fresh verification code."""
    member = form.save(commit=False)
    existing = Member.objects.filter(email=member.email).exclude(verified=True).first()
    if existing:
        # Same person registering again - keep the row (and its code history) instead of duplicating.
        member.pk = existing.pk
        member.membership_no = existing.membership_no
    if user is not None and getattr(user, "is_authenticated", False):
        member.user = user
    member.verification_channel = form.cleaned_data.get("channel", "both")
    member.status = Member.Status.PENDING
    member.verified = False
    member.save()
    return member


def issue_code(member, channel=None):
    from apps.communications.services import send_verification_code

    channel = channel or member.verification_channel or "both"
    code, plaintext = VerificationCode.issue(member, channel=channel)
    report = send_verification_code(member, plaintext, channel=channel)
    logger.info("Verification code for %s issued via %s", member.email, channel)
    return code, plaintext, report


def current_code(member):
    """The newest code that has not expired and still has attempts left."""
    return (
        member.codes.filter(confirmed_at__isnull=True)
        .order_by("-created_at")
        .first()
    )


def check_code(member, raw_code):
    """Return (ok, message). On success the membership is confirmed."""
    code = current_code(member)
    if code is None:
        return False, "We cannot find an active code. Please request a new one."
    if code.expired:
        return False, "That code has expired. Request a new one and try again."
    if code.out_of_attempts:
        return False, "Too many wrong tries with this code. Request a new one."
    if not code.is_valid_for(raw_code):
        code.register_attempt()
        remaining = max(0, settings.VERIFICATION_MAX_ATTEMPTS - code.attempts)
        return False, f"Wrong code. {remaining} attempt(s) left before it is blocked."
    code.mark_confirmed()
    return True, "Code confirmed."


def ensure_login_account(member, request=None):
    """Give a verified member an account (or reuse an existing one).

    Returns (user, reset_url) - reset_url is set only when we had to create the account,
    in which case the member is emailed a link to choose a password.
    """
    from apps.accounts.models import User

    if member.user_id and member.user:
        return member.user, None

    user = User.objects.filter(email__iexact=member.email).first()
    reset_url = None
    if user is None:
        user = User.objects.create_user(
            email=member.email,
            name=member.full_name,
            password=None,
            phone=member.phone,
        )
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        path = reverse("accounts:password_reset_confirm", kwargs={"uidb64": uid, "token": token})
        reset_url = request.build_absolute_uri(path) if request is not None else path
    member.user = user
    member.save(update_fields=["user", "updated_at"])
    return user, reset_url


def confirm_membership(member, request=None):
    """Verify, assign KOC number, welcome the member by email + SMS."""
    from apps.communications.services import (
        send_membership_confirmation,
        send_welcome_account_link,
    )

    member.confirm_membership()
    user, reset_url = ensure_login_account(member, request)
    if reset_url:
        send_welcome_account_link(member, reset_url)
    delivery = send_membership_confirmation(member)
    return {
        "member": member,
        "user": user,
        "created_account": bool(reset_url),
        "reset_url": reset_url,
        "delivery": delivery,
    }
