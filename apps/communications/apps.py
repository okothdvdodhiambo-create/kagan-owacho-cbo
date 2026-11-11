import logging

from django.apps import AppConfig
from django.conf import settings

logger = logging.getLogger(__name__)


class CommunicationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.communications"
    label = "communications"
    verbose_name = "Email, SMS & campaigns"

    def ready(self):
        """Print the effective email settings once, so a deploy log shows what Render passed in."""
        from .mail import (
            email_configuration_lines,
            email_configuration_warnings,
            email_reaches_the_outside_world,
        )

        logger.info("Email configuration | %s", " | ".join(email_configuration_lines()))
        for warning in email_configuration_warnings():
            logger.warning("Email configuration | %s", warning)
        if not settings.DEBUG and not email_reaches_the_outside_world():
            logger.warning(
                "Email configuration | this is a live site (DEBUG=False) with no delivering backend, "
                "so verification codes are printed to this log instead of being emailed. Set "
                "EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD and DEFAULT_FROM_EMAIL "
                "in Render's Environment tab, then redeploy."
            )