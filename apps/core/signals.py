"""Bootstrap the site the first time migrations run (admins, nav, dropdowns, demo)."""

import sys

from django.db.models.signals import post_migrate
from django.dispatch import receiver

MANAGEMENT_COMMANDS_THAT_SEED = {"bootstrap_site", "test", "testserver", "makemigrations", "collectstatic"}


def _should_skip() -> bool:
    argv = [a.lstrip("-") for a in sys.argv]
    if any(command in argv for command in MANAGEMENT_COMMANDS_THAT_SEED):
        return True
    return "pytest" in argv[0]


@receiver(post_migrate)
def bootstrap_after_migrate(sender, **kwargs):
    if sender.name != "apps.core" or _should_skip():
        return
    from django.core.management import call_command

    call_command("bootstrap_site")
