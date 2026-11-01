"""Upload storage that lives in the database, for hosts with no persistent disk.

Render free instances (and any Render instance without a paid persistent disk) wipe
MEDIA_ROOT on every restart and redeploy, so photos uploaded by the committee would
vanish within hours. DatabaseStorage keeps each upload in the core_storedfile table
instead: it survives restarts, survives deploys, and travels with the ordinary
database backup that already holds the members those photos belong to.
"""

import mimetypes
from urllib.parse import quote

from django.conf import settings
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible

# Everything this project accepts, served inline. Anything else is sent as opaque
# bytes with a download header so an upload can never be rendered as a page.
INLINE_CONTENT_TYPES = ["image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf"]


def safe_content_type(name, declared=""):
    declared = (declared or "").split(";")[0].strip().lower()
    if declared in INLINE_CONTENT_TYPES:
        return declared
    guessed = (mimetypes.guess_type(name)[0] or "").lower()
    if guessed in INLINE_CONTENT_TYPES:
        return guessed
    return "application/octet-stream"


@deconstructible
class DatabaseStorage(Storage):
    """Default-file storage backed by the StoredFile table (settings.MEDIA_STORAGE)."""

    def get_available_name(self, name, max_length=None):
        # Django's base storage builds candidates with os.path.join, which on Windows
        # would put backslashes into stored names and into /media/ URLs.
        return super().get_available_name(name, max_length=max_length).replace("\\", "/")

    def _open(self, name, mode="rb"):
        from apps.core.models import StoredFile

        return StoredFile.objects.get(name=name).as_file()

    def _save(self, name, content):
        from apps.core.models import StoredFile

        data = bytes(content.read())
        StoredFile.objects.update_or_create(
            name=name,
            defaults={
                "data": data,
                "content_type": safe_content_type(name, getattr(content, "content_type", "")),
                "size": len(data),
            },
        )
        return name

    def delete(self, name):
        from apps.core.models import StoredFile

        StoredFile.objects.filter(name=name).delete()

    def exists(self, name):
        from apps.core.models import StoredFile

        return StoredFile.objects.filter(name=name).exists()

    def size(self, name):
        from apps.core.models import StoredFile

        return StoredFile.objects.get(name=name).size

    def url(self, name):
        return f"{settings.MEDIA_URL}{quote(name)}"
