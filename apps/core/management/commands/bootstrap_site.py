"""Idempotent bootstrap: admin accounts, navigation, dropdown options, demo content.

Runs automatically after `python manage.py migrate` (see apps/core/signals.py) and can
be re-run any time:  python manage.py bootstrap_site
"""

import io
from datetime import timedelta

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone


def make_admins():
    from apps.accounts.models import User

    created_any = []
    for index, (email, password) in enumerate(settings.ADMIN_ACCOUNTS, start=1):
        email = (email or "").strip().lower()
        password = password or ""
        if not email:
            print(f"  admin {index}: ADMIN{index}_EMAIL is empty, nothing to create")
            continue
        if not password.strip():
            print(f"  admin {index}: ADMIN{index}_PASSWORD is empty, {email} was NOT created")
            continue
        if not settings.DEBUG and password in settings.DEMO_ADMIN_PASSWORDS:
            print(
                f"  admin {index}: {email} still uses the placeholder ADMIN{index}_PASSWORD. "
                "Set a strong password in Render and redeploy - no account was created."
            )
            continue
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "name": f"Administrator {index}",
                "is_admin": True,
                "is_staff": True,
                "is_active": True,
            },
        )
        if created:
            user.set_password(password)
            user.save()
            created_any.append(email)
            print(f"  admin account created: {email}")
        else:
            # Keep the admin flags correct if the row predates this code.
            if not (user.is_admin and user.is_staff):
                user.is_admin = user.is_staff = True
                user.save(update_fields=["is_admin", "is_staff"])
    return created_any


def make_nav_items():
    from apps.core.models import NavItem

    defaults = [
        ("Home", "/", 10),
        ("About", "/about/", 20),
        ("Events Sponsored", "/events/", 30),
        ("Event Calendar", "/events/calendar/", 40),
        ("Register as a Member", "/member/register/", 50),
    ]
    for title, url, order in defaults:
        if not NavItem.objects.filter(url=url).exists():
            NavItem.objects.create(title=title, url=url, order=order)


def make_dropdown_options():
    from apps.membership.models import DropdownOption

    genders = ["Male", "Female", "Other"]
    roles = [
        "Youth Member",
        "Women Group Member",
        "Men Group Member",
        "Elder",
        "Volunteer",
        "Patron / Donor",
        "Committee Member",
    ]
    occupations = ["Farmer", "Trader", "Teacher", "Student", "Boda Rider", "Casual Labour", "Self-employed"]
    order = 10
    for label in genders:
        DropdownOption.objects.get_or_create(field=DropdownOption.Field.GENDER, label=label, defaults={"order": order})
        order += 10
    order = 10
    for label in roles:
        DropdownOption.objects.get_or_create(field=DropdownOption.Field.ROLE, label=label, defaults={"order": order})
        order += 10
    order = 10
    for label in occupations:
        DropdownOption.objects.get_or_create(field=DropdownOption.Field.OCCUPATION, label=label, defaults={"order": order})
        order += 10


def _placeholder_image(lines, colour_a, colour_b, size=(1280, 720)):
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", size, colour_a)
    draw = ImageDraw.Draw(img)
    # Vertical gradient
    for y in range(size[1]):
        ratio = y / size[1]
        colour = tuple(int(colour_a[i] + (colour_b[i] - colour_a[i]) * ratio) for i in range(3))
        draw.line([(0, y), (size[0], y)], fill=colour)

    def font(px):
        for candidate in ("arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf", "segoeuib.ttf"):
            try:
                return ImageFont.truetype(candidate, px)
            except OSError:
                continue
        return ImageFont.load_default()

    body = font(46)
    y = size[1] // 3
    for line in lines:
        try:
            width = draw.textlength(line, font=body)
        except AttributeError:  # pragma: no cover - very old Pillow
            width = len(line) * 24
        draw.text(((size[0] - width) / 2, y), line, fill=(255, 255, 255), font=body)
        y += 62
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=82, optimize=True)
    buffer.seek(0)
    return ContentFile(buffer.read())


def make_slider_images():
    from apps.core.models import SliderImage

    if SliderImage.objects.exists():
        return
    slides = [
        ("Kagan Owacho CBO", (12, 74, 60), (2, 62, 54)),
        ("Paying school fees", (10, 60, 100), (8, 32, 68)),
        ("Community events", (120, 86, 20), (74, 50, 8)),
    ]
    for order, (caption, colour_a, colour_b) in enumerate(slides, start=1):
        image = SliderImage.objects.create(caption=caption, order=order, active=True)
        name = f"slide-{order}.jpg"
        image.image.save(name, _placeholder_image([caption], colour_a, colour_b), save=True)


def make_demo_events():
    from apps.events.models import Event, EventReport

    if Event.objects.exists():
        return
    today = timezone.localtime().replace(hour=9, minute=0, second=0, microsecond=0)
    samples = [
        ("School fees support day", 0, "Kagan Primary School", "We cleared term fees for 42 students during one gathering."),
        ("Youth mentorship meeting", 9, "Community hall, Kagan", "Elders and employers mentored 60 form-four leavers."),
        ("Mama Otila thank-you lunch", 21, "Rangwe trading centre", "Fundraising lunch that paid the next batch of exam fees."),
    ]
    first = None
    for title, offset, venue, description in samples:
        event = Event.objects.create(
            title=title,
            starts_at=today + timedelta(days=offset),
            ends_at=today + timedelta(days=offset, hours=4),
            venue=venue,
            description=description,
            published=True,
        )
        first = first or event
    if first:
        EventReport.objects.create(
            event=first,
            title="Report: school fees support day",
            body=(
                "Kagan Owacho CBO paid school fees for 42 learners on the sponsored day. "
                "Lists were checked against the head teachers' records, receipts were collected, "
                "and members watched the handover at Kagan Primary School."
            ),
            published=True,
        )


class Command(BaseCommand):
    help = "Create admins, default navigation, dropdown options and (optional) demo content."

    def add_arguments(self, parser):
        parser.add_argument("--skip-demo", action="store_true", help="Do not create demo slider/events.")

    @transaction.atomic
    def handle(self, *args, **options):
        demo = not options["skip_demo"]
        print(f"Bootstrapping {settings.ORGANIZATION_NAME} ...")
        make_admins()
        make_nav_items()
        make_dropdown_options()
        if demo:
            make_slider_images()
            make_demo_events()
        print("Bootstrap complete.")
