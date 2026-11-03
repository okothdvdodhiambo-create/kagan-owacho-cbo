from django.conf import settings
from django.db import migrations


PLACEHOLDER = "+254000000{}"
PENDING = "pending_verification"


def placeholder_phone(user_id):
    """A row that cannot pass phone validation until the member types a real number."""
    return PLACEHOLDER.format(f"{user_id:09d}")[:20]


def give_every_account_a_membership(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    Member = apps.get_model("membership", "Member")

    # Only the combined registration sets is_active=False now, so accounts left
    # half-finished by the old two-step flow get a second chance instead of a lockout.
    User.objects.filter(is_active=False, is_admin=False, is_superuser=False).update(is_active=True)

    users = User.objects.filter(is_admin=False, is_superuser=False).order_by("id")
    for user in users:
        if Member.objects.filter(user=user).exists():
            continue
        # A member row created before accounts were linked (the old separate sign-up).
        loose = Member.objects.filter(user__isnull=True, email__iexact=user.email).order_by("-created_at").first()
        if loose is not None:
            loose.user = user
            loose.save(update_fields=["user"])
            continue
        phone = user.phone or ""
        if not phone or Member.objects.filter(phone=phone).exists():
            phone = placeholder_phone(user.id)
        if Member.objects.filter(email__iexact=user.email).exists():
            continue
        Member.objects.create(
            user=user,
            full_name=user.name or user.email,
            phone=phone,
            email=user.email,
            location="",
            status=PENDING,
            verified=False,
            verification_channel="email",
        )


class Migration(migrations.Migration):
    """Having an account now means being a member, so old accounts get the row they need.

    Verified members are pointed at the account that shares their email, half-finished
    registrations are re-opened rather than locked out, and any account without a
    membership row is given a pending one so the "complete your details" page can finish it.

    Backwards is a no-op: the rows added here are the ones the merged flow expects.
    """

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("membership", "0002_membership_no_nullable"),
    ]

    operations = [
        migrations.RunPython(give_every_account_a_membership, migrations.RunPython.noop),
    ]
