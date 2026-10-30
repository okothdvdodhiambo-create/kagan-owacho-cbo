"""Template context shared by every page."""

from django.utils import timezone

from .models import NavItem, SiteSettings, SliderImage, SocialLink


def site_settings(request):
    site = SiteSettings.load()
    return {
        "SITE": site,
        "SOCIAL_LINKS": list(SocialLink.objects.filter(active=True)),
        "CURRENT_YEAR": timezone.localtime().year,
        "ORG_NAME": site.organization_name,
    }


def navigation(request):
    """Left-to-right nav buttons; the current path decides the highlighted button."""
    path = request.path or "/"
    items = []
    for item in NavItem.objects.filter(visible=True):
        url = item.url or "/"
        is_active = path == url or (url != "/" and path.startswith(url))
        items.append({"item": item, "url": url, "active": is_active})
    return {
        "NAV_ITEMS": items,
        "SLIDER_IMAGES": list(SliderImage.objects.filter(active=True)[:6]),
    }
