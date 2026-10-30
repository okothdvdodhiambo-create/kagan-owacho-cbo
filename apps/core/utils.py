"""Small shared helpers: image validation/optimisation, formatting, files."""

import io
import os
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.utils import timezone


def validate_image_file(file):
    """Accept only real images of an allowed type and a sane size."""
    if file is None:
        return
    name = getattr(file, "name", "") or ""
    ext = os.path.splitext(name)[1].lower().lstrip(".")
    allowed = [e.lower() for e in settings.IMAGE_ALLOWED_EXTENSIONS]
    if ext and ext not in allowed:
        raise ValidationError(f"Only these image types are allowed: {', '.join(allowed)}.")
    size_mb = settings.MAX_UPLOAD_SIZE_MB
    if file.size and file.size > size_mb * 1024 * 1024:
        raise ValidationError(f"That file is too big. Maximum size is {size_mb} MB.")
    file.seek(0)
    header = file.read(16)
    file.seek(0)
    if not _looks_like_image(header):
        raise ValidationError("That does not look like a valid image file.")


def _looks_like_image(header: bytes) -> bool:
    signatures = (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"GIF87a", b"GIF89a", b"RIFF")
    if any(header.startswith(sig) for sig in signatures):
        return True
    return header[8:12] == b"WEBP"


def validate_document_file(file):
    """Attachments on incident reports: images or PDFs, within the size limit."""
    allowed = settings.IMAGE_ALLOWED_EXTENSIONS + ["pdf"]
    ext = os.path.splitext(getattr(file, "name", "") or "")[1].lower().lstrip(".")
    if ext and ext not in allowed:
        raise ValidationError(f"Attach an image ({', '.join(settings.IMAGE_ALLOWED_EXTENSIONS)}) or a PDF.")
    size_mb = settings.MAX_UPLOAD_SIZE_MB
    if file.size and file.size > size_mb * 1024 * 1024:
        raise ValidationError(f"That file is too big. Maximum size is {size_mb} MB.")


def optimise_image(file, max_side=1400, quality=82):
    """Resize (keeping aspect ratio) and re-encode so uploads stay small.

    Returns a ContentFile ready to save, or None when the image cannot be read.
    """
    from PIL import Image, ImageOps

    if file is None:
        return None
    try:
        file.seek(0)
        img = Image.open(file)
        img = ImageOps.exif_transpose(img)
        img.load()
    except Exception:
        return None

    keep_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
    img = img.convert("RGBA") if keep_alpha else img.convert("RGB")

    if max(img.size) > max_side:
        img.thumbnail((max_side, max_side), Image.LANCZOS)

    buffer = io.BytesIO()
    if keep_alpha:
        img.save(buffer, format="PNG", optimize=True)
        content_type, extension = "image/png", "png"
    else:
        img.save(buffer, format="JPEG", quality=quality, optimize=True)
        content_type, extension = "image/jpeg", "jpg"
    buffer.seek(0)
    return {"data": buffer.read(), "content_type": content_type, "extension": extension}


def replace_image_extension(name, extension):
    base = os.path.splitext(os.path.basename(name or "image"))[0]
    base = re.sub(r"[^A-Za-z0-9_-]+", "-", base).strip("-") or "image"
    return f"{base}-{timezone.now():%Y%m%d%H%M%S}.{extension}"


def new_image_file(original_name, processed):
    """Processed dict from optimise_image() -> Django ContentFile with a clean name."""
    return ContentFile(processed["data"], name=replace_image_extension(original_name, processed["extension"]))


def kenyan_phone_to_254(raw):
    """Normalise 07xx.../01xx.../254.../+254... to +2547xxxxxxxx, or None if invalid."""
    if not raw:
        return None
    digits = re.sub(r"[^0-9+]", "", str(raw).strip())
    if digits.startswith("+"):
        digits = digits[1:]
    if digits.startswith("00254"):
        digits = digits[2:]
    if digits.startswith("254"):
        local = digits[3:]
    elif digits.startswith("0"):
        local = digits[1:]
    else:
        return None
    if not re.fullmatch(r"(7|1)\d{8}", local):
        return None
    return f"+254{local}"


def ksh(value):
    """Money as used everywhere in the UI: 1,250.00 (prefix added in templates)."""
    try:
        return f"{float(value or 0):,.2f}"
    except (TypeError, ValueError):
        return "0.00"


def client_ip(request):
    """Best-effort client address, honouring a proxy's X-Forwarded-For header."""
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    candidate = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")
    return candidate or None


def file_uri_for_pdf(relative_path):
    """Absolute file:// URI (Windows-safe) for xhtml2pdf image embedding."""
    if not relative_path:
        return None
    full = os.path.normpath(os.path.join(str(settings.MEDIA_ROOT), relative_path))
    return "file:///" + full.replace("\\", "/").lstrip("/")


def iso_timestamp():
    return timezone.localtime().strftime("%Y%m%d%H%M%S")
