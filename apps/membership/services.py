"""The registration -> code -> verified membership flow, in one place."""

import logging

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .models import Member, VerificationCode

logger = logging.getLogger(__name__)


def save_registration(form):
    """One submitted form creates the account (inactive) and its membership (pending).

    Re-submitting with corrections refreshes the same pair, so a person who mistyped
    an email address is never locked out by their own unfinished registration.
    """
    from apps.accounts.models import User

    details = form.member_details()
    email = form.cleaned_data["email"]
    with transaction.atomic():
        user = form.pending_account()
        if user is None:
            user = User.objects.create_user(
                email=email,
                name=details["full_name"],
                password=form.cleaned_data["password1"],
                phone=details["phone"],
                photo=form.cleaned_data.get("photo"),
                is_active=False,
            )
        else:
            user.name = details["full_name"]
            user.phone = details["phone"]
            user.set_password(form.cleaned_data["password1"])
            if form.cleaned_data.get("photo"):
                user.photo = form.cleaned_data["photo"]
            user.is_active = False
            user.save()

        member = Member.objects.filter(user=user).order_by("-created_at").first()
        if member is None:
            member = Member.objects.filter(email__iexact=email, verified=False).order_by("-created_at").first()
        if member is None:
            member = Member(user=user)
        _apply_details(member, user, details, email)
    return user, member


def save_membership_for_account(form, user, member=None):
    """Add or refresh the membership row that belongs to an existing account."""
    if member is None:
        member = Member.objects.filter(user=user).order_by("-created_at").first()
    if member is None:
        member = Member(user=user)
    if member.verified:
        raise ValidationError("This account is already a verified member.")
    with transaction.atomic():
        _apply_details(member, user, form.member_details(), user.email)
    return member


def _apply_details(member, user, details, email):
    """Write the member half of a form onto a pending membership row."""
    if member.verified:
        raise ValidationError("This membership is already verified. Log in instead.")
    member.user = user
    member.full_name = details["full_name"] or user.name
    member.email = email
    member.phone = details["phone"]
    member.gender = details["gender"]
    member.role = details["role"]
    member.location = details["location"]
    member.sub_location = details["sub_location"]
    member.occupation = details["occupation"]
    member.verification_channel = _channel()
    member.status = Member.Status.PENDING
    member.verified = False
    member.save()
    return member


def _channel():
    from apps.communications.services import default_verification_channel

    return default_verification_channel()


def issue_code(member, channel=None):
    from apps.communications.services import send_verification_code

    channel = channel or member.verification_channel or "email"
    code, plaintext = VerificationCode.issue(member, channel=channel)
    report = send_verification_code(member, plaintext, channel=channel)
    logger.info("Verification code for %s issued via %s", member.email, channel)
    if settings.DEBUG:
        # Never depend on the mail server to know what the code was.
        banner = "=" * 62
        print(f"\n{banner}\n[VERIFICATION CODE -> {member.email}]\nCode: {plaintext}\n{banner}\n")
    return code, plaintext, report


def email_failed(report):
    """True when the code could not be handed to the mail server at all."""
    return not (report or {}).get("email")


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
    """Verify, assign the KOC number, switch the account on, welcome the member."""
    from apps.communications.services import (
        send_membership_confirmation,
        send_welcome_account_link,
    )

    member.confirm_membership()
    user, reset_url = ensure_login_account(member, request)
    if user is not None and not user.is_active:
        user.is_active = True
        user.save(update_fields=["is_active"])
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
