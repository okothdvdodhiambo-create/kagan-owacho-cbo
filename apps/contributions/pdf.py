"""Render the printable contribution statement to PDF with xhtml2pdf (pure Python)."""

import os
from io import BytesIO

from django.conf import settings
from django.template.loader import render_to_string
from django.http import HttpResponse
from django.utils import timezone
from xhtml2pdf import pisa

from apps.contributions.models import Contribution
from apps.core.models import SiteSettings
from apps.core.utils import file_uri_for_pdf


def _link_callback(uri, path):
    """Let xhtml2pdf read local media files and static assets."""
    if os.path.isabs(path) and os.path.exists(path):
        return path
    for base in (str(settings.STATIC_ROOT), str(settings.BASE_DIR / "static")):
        candidate = os.path.join(base, path.lstrip("/"))
        if os.path.exists(candidate):
            return candidate
    return None


def html_to_pdf(html):
    buffer = BytesIO()
    pisa.CreatePDF(src=html, dest=buffer, encoding="utf-8", link_callback=_link_callback)
    pdf = buffer.getvalue()
    buffer.close()
    if not pdf:
        raise RuntimeError("PDF generation produced nothing - check the statement template.")
    return pdf


def statement_pdf(member, contributions, as_attachment=True):
    site = SiteSettings.load()
    totals = Contribution.totals(member)
    context = {
        "site": site,
        "member": member,
        "contributions": contributions,
        "totals": totals,
        "logo_uri": file_uri_for_pdf(site.logo.name) if site.logo else None,
        "generated_at": timezone.localtime(),
        "reference": f"STMT-{member.membership_no}-{timezone.localdate():%Y%m%d}",
    }
    html = render_to_string("pdf/statement.html", context)
    pdf = html_to_pdf(html)
    response = HttpResponse(pdf, content_type="application/pdf")
    disposition = "attachment" if as_attachment else "inline"
    filename = f"kagan-owacho-statement-{member.membership_no or member.pk}.pdf"
    response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
    response["Content-Length"] = str(len(pdf))
    return response
