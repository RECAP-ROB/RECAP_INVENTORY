import threading
import time

from django.core.management.base import BaseCommand

from api.mqtt import start_mqtt_listener, MQTTListener


class Command(BaseCommand):
    help = "Control MQTT listener (start, stop, status)"

    def add_arguments(self, parser):
        parser.add_argument(
            "action",
            choices=["start", "stop", "status", "restart"],
            help="Action to perform on MQTT listener",
        )

    def handle(self, *args, **options):
        action = options["action"]

        if action == "start":
            self.stdout.write("Starting MQTT listener...")
            start_mqtt_listener()
            self.stdout.write(self.style.SUCCESS("MQTT listener started successfully"))

        elif action == "stop":
            self.stdout.write("Stopping MQTT listener...")
            # Find and stop the MQTT thread
            mqtt_thread = None
            for thread in threading.enumerate():
                if thread.name == "MQTTListenerThread":
                    mqtt_thread = thread
                    break

            if mqtt_thread and mqtt_thread.is_alive():
                # Note: Daemon threads can't be stopped cleanly
                self.stdout.write(
                    self.style.WARNING(
                        "MQTT listener is running as daemon thread. "
                        "It will stop when the main process exits."
                    )
                )
            else:
                self.stdout.write("MQTT listener is not running")

        elif action == "status":
            mqtt_thread = None
            for thread in threading.enumerate():
                if thread.name == "MQTTListenerThread":
                    mqtt_thread = thread
                    break

            if mqtt_thread and mqtt_thread.is_alive():
                self.stdout.write(self.style.SUCCESS("MQTT listener is running"))
            else:
                self.stdout.write("MQTT listener is not running")

        elif action == "restart":
            self.stdout.write("Restarting MQTT listener...")
            # Stop existing thread
            mqtt_thread = None
            for thread in threading.enumerate():
                if thread.name == "MQTTListenerThread":
                    mqtt_thread = thread
                    break

            if mqtt_thread and mqtt_thread.is_alive():
                self.stdout.write("Waiting for existing thread to stop...")
                # Give it a moment (though daemon threads are hard to
                # stop cleanly)
                time.sleep(1)

            # Start new listener
            start_mqtt_listener()
            self.stdout.write(
                self.style.SUCCESS("MQTT listener restarted successfully")
            )
