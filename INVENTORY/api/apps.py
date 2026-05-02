import os
import sys

from django.apps import AppConfig
from django.db.models.signals import post_save
# from .models import Order
# from .signals import order_created_handler


class ApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "api"

    def ready(self):
        from . import signals  # Import signals to ensure they are registered
        from .mqtt import start_mqtt_listener

        management_commands = {
            "makemigrations",
            "migrate",
            "collectstatic",
            "shell",
            "test",
            "check",
            "showmigrations",
        }

        # Skip MQTT listener in management commands, Celery workers,
        # and when disabled
        is_celery_worker = any(arg in sys.argv[0] for arg in ["celery", "worker"])
        is_management_cmd = len(sys.argv) > 1 and sys.argv[1] in management_commands
        is_mqtt_disabled = os.environ.get("DISABLE_MQTT", "").lower() in (
            "true",
            "1",
            "yes",
        )

        if is_celery_worker or is_management_cmd or is_mqtt_disabled:
            return

        start_mqtt_listener()
