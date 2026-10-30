from django import template
from django.utils.safestring import mark_safe

from apps.core.utils import ksh

register = template.Library()


@register.filter(name="money")
def money(value):
    """KES amount with thousand separators; prefix is added in the markup."""
    return ksh(value)


@register.filter(name="initials")
def initials(value):
    """Avatar fallback letters from a name or email."""
    text = (value or "").strip()
    if not text:
        return "?"
    parts = text.split()
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


@register.simple_tag(takes_context=True)
def keep_query(context, **kwargs):
    """Rebuild the current query string with overridden params (pagination + filters)."""
    params = dict(context["request"].GET.items())
    for key, val in kwargs.items():
        if val in (None, ""):
            params.pop(key, None)
        else:
            params[key] = val
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return mark_safe("?" + query if query else "")


@register.filter(name="percent")
def percent(value):
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return "0%"


@register.filter(name="boundfield")
def boundfield(form, name):
    """Fetch one BoundField by name so a long form can be split across cards."""
    try:
        return form[name]
    except KeyError:
        return None
