"""Helpers shared by the automated test suite.

Only plain functions and a mixin live here - no TestCase subclass - so Django's test
discovery imports this file without running anything from it.
"""

import shutil
import tempfile
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings


def png_upload(name="picture.png", size=(600, 400), colour=(11, 77, 57)):
    from PIL import Image

    canvas = BytesIO()
    Image.new("RGB", size, colour).save(canvas, format="PNG")
    return SimpleUploadedFile(name, canvas.getvalue(), content_type="image/png")


def make_admin(email="committee@example.org", password="Committee#2026"):
    from apps.accounts.models import User

    return User.objects.create_superuser(email=email, password=password, name="Committee Admin")


def seed_dropdown_options():
    """The registration form only accepts values the committee has published."""
    from apps.membership.models import DropdownOption

    seed = {
        "gender": ["Female", "Male"],
        "role": ["Youth Member", "Elder"],
        "occupation": ["Farmer", "Teacher"],
    }
    for field, labels in seed.items():
        for order, label in enumerate(labels, start=1):
            DropdownOption.objects.get_or_create(field=field, label=label, defaults={"order": order})


def register_payload(email="jane@example.com", phone="0712 345 678", **overrides):
    """One POST creates the account and the membership, so it carries both halves."""
    data = {
        "name": "Jane Owacho Adega",
        "email": email,
        "password1": "Member#2026",
        "password2": "Member#2026",
        "phone": phone,
        "gender": "Female",
        "role": "Youth Member",
        "location": "Kagan Ward",
        "sub_location": "Rangwe",
        "occupation": "Farmer",
    }
    data.update(overrides)
    return data


def member_details_payload(phone="0712 345 678", **overrides):
    """The membership half only - used when an existing account completes its record."""
    data = {
        "phone": phone,
        "gender": "Female",
        "role": "Youth Member",
        "location": "Kagan Ward",
        "sub_location": "Rangwe",
        "occupation": "Farmer",
    }
    data.update(overrides)
    return data


def make_member(email="jane@example.com", phone="+254712345678", password="Member#2026", verified=True):
    """A login account plus its membership row, ready to use."""
    from apps.accounts.models import User
    from apps.membership.models import Member

    user = User.objects.create_user(email=email, name="Jane Owacho", password=password, phone=phone)
    member = Member.objects.create(
        user=user,
        full_name="Jane Owacho",
        phone=phone,
        email=email,
        gender="Female",
        role="Youth Member",
        location="Kagan Ward",
        sub_location="Rangwe",
        occupation="Farmer",
        verification_channel="email",
    )
    if verified:
        member.confirm_membership()
    return member


class MediaRootMixin:
    """Keep uploaded test files out of the real media folder."""

    def enable_temp_media(self):
        self._media_dir = tempfile.mkdtemp(prefix="koco-test-media-")
        self._media_override = override_settings(MEDIA_ROOT=self._media_dir)
        self._media_override.enable()
        self.addCleanup(self._media_override.disable)
        self.addCleanup(lambda: shutil.rmtree(self._media_dir, ignore_errors=True))
