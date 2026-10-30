"""Password strength rules used at registration and profile edits."""

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

MINIMUM_LENGTH = 8


class PasswordCompositionValidator:
    """Minimum length plus at least one capital letter, one lowercase letter and one digit."""

    def __init__(self, min_length=MINIMUM_LENGTH):
        self.min_length = min_length

    def validate(self, password, user=None):
        problems = []
        if len(password or "") < self.min_length:
            problems.append(f"use at least {self.min_length} characters")
        if not any(c.isupper() for c in password or ""):
            problems.append("include at least one capital letter")
        if not any(c.islower() for c in password or ""):
            problems.append("include at least one small letter")
        if not any(c.isdigit() for c in password or ""):
            problems.append("include at least one number")
        if problems:
            raise ValidationError(
                _("The password must: %(problems)s."),
                code="password_too_weak",
                params={"problems": ", ".join(problems)},
            )

    def get_help_text(self):
        return (
            f"Your password must be at least {self.min_length} characters long and include a "
            "capital letter, a small letter and a number."
        )
