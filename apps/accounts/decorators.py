"""Reusable permission guards for the custom admin dashboard and member pages."""

from functools import wraps

from django.contrib.auth.mixins import AccessMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


def admin_required(view_func):
    """Only the two .env administrators (or Django superusers) may pass."""

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return redirect_to_login(request.get_full_path(), login_url="/accounts/login/")
        if not user.is_administrator:
            raise PermissionDenied("This area is for Kagan Owacho CBO administrators only.")
        return view_func(request, *args, **kwargs)

    return _wrapped


def member_required(view_func):
    """A logged-in account whose membership registration has been verified."""

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return redirect_to_login(request.get_full_path(), login_url="/accounts/login/")
        membership = user.membership
        if membership is None or not membership.verified:
            return redirect("membership:pending")
        return view_func(request, *args, **kwargs)

    return _wrapped


class AdminRequiredMixin(AccessMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not request.user.is_administrator:
            raise PermissionDenied("Administrators only.")
        return super().dispatch(request, *args, **kwargs)
