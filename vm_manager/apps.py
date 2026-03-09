import os
import sys

from django.apps import AppConfig


class VmManagerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "vm_manager"

    def ready(self):
        # Skip collector for management commands where background loop is unwanted.
        skipped_commands = {"makemigrations", "migrate", "collectstatic", "shell", "dbshell", "test"}
        if len(sys.argv) > 1 and sys.argv[1] in skipped_commands:
            return

        # In runserver with autoreload, start only in child process.
        if len(sys.argv) > 1 and sys.argv[1] == "runserver" and os.environ.get("RUN_MAIN") != "true":
            return

        from .metrics_autocollector import start_metrics_autocollector

        start_metrics_autocollector()
