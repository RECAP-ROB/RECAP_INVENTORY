import json
import logging
import os
import threading
import time
from typing import Optional

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)

MQTT_BROKER_HOST = os.environ.get("MQTT_BROKER_HOST", "10.15.173.106")
MQTT_BROKER_PORT = int(os.environ.get("MQTT_BROKER_PORT", "1883"))
MQTT_TOPIC = os.environ.get("MQTT_TOPIC", "shelf/status")
MQTT_CLIENT_ID = os.environ.get("MQTT_CLIENT_ID", "inventory-mqtt-client")
MQTT_KEEPALIVE = int(os.environ.get("MQTT_KEEPALIVE", "60"))

#10.15.173.106
class MQTTListener:
    """Controllable MQTT client for shelf status monitoring."""

    def __init__(self):
        self.client: Optional[mqtt.Client] = None
        self.thread: Optional[threading.Thread] = None
        self.running = False
        self.connected = False
        self._shelf_state_lock = threading.Lock()
        self._previous_shelf_states = {}  # Track previous states to detect transitions

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info(
                "Connected to MQTT broker at %s:%s", MQTT_BROKER_HOST, MQTT_BROKER_PORT
            )
            try:
                result = client.subscribe(MQTT_TOPIC)
                # Check subscription result code
                if result[0] == mqtt.MQTT_ERR_SUCCESS:
                    logger.info("Subscribed to MQTT topic: %s", MQTT_TOPIC)
                    self.connected = True
                else:
                    logger.warning(
                        "Failed to subscribe to MQTT topic %s: error code %s",
                        MQTT_TOPIC,
                        result[0],
                    )
                    self.connected = False
            except Exception as exc:
                logger.exception(
                    "Error subscribing to MQTT topic %s: %s", MQTT_TOPIC, exc
                )
                self.connected = False
        else:
            logger.warning("MQTT connection failed with result code %s", rc)
            self.connected = False

    def _on_disconnect(self, client, userdata, rc):
        if rc == 0:
            logger.info("MQTT client disconnected normally")
        else:
            logger.warning("MQTT disconnected unexpectedly with result code %s", rc)
        self.connected = False

    def _should_create_restock_order(self, shelf_key, current_shelf_state):
        """
        Determine if a restock order should be created based on state transition.
        Only create orders when transitioning from FILLED -> empty/partial (stock depletion).
        This prevents ghost restocks.
        """
        with self._shelf_state_lock:
            previous_state = self._previous_shelf_states.get(shelf_key, "")
            self._previous_shelf_states[shelf_key] = current_shelf_state

        # Only trigger restock if transitioning from FILLED to empty/partial
        return (
            previous_state == "filled"
            and current_shelf_state in ("empty", "partial")
        )

    def _normalize_shelf_state(self, raw_status):
        status = (raw_status or "").strip().lower()
        if not status:
            return ""
        if "empty" in status and "partial" not in status:
            return "empty"
        if "partial" in status or status.startswith("p"):
            return "partial"
        return "filled"

    def _should_create_restock_order(self, shelf_key, current_shelf_state):
        """
        Determine if a restock order should be created based on state transition.
        Only create orders when transitioning from FILLED -> empty/partial (stock depletion).
        This prevents ghost restocks.
        """
        with self._shelf_state_lock:
            previous_state = self._previous_shelf_states.get(shelf_key, "")
            self._previous_shelf_states[shelf_key] = current_shelf_state

        # Only trigger restock if transitioning from FILLED to empty/partial
        return (
            previous_state == "filled"
            and current_shelf_state in ("empty", "partial")
        )


    def _on_message(self, client, userdata, message):
        try:
            try:
                payload = message.payload.decode("utf-8")
                logger.debug("MQTT received topic=%s payload=%s", message.topic, payload)
                data = json.loads(payload)
            except Exception as exc:
                logger.warning(
                    "Ignoring invalid MQTT payload: %s (%s)", message.payload, exc
                )
                return

            # Check if it's the new bulk shelf status format
            if "slots" in data:
                # Process bulk shelf status
                slots = data.get("slots", {})
                for product_name, slot_data in slots.items():
                    try:
                        from api.celery_tasks import camera_restock_task
                        from api.models import Product, Order, OrderItem, User

                        product = Product.objects.get(name=product_name)
                        raw_status = slot_data.get("status")
                        shelf_state = self._normalize_shelf_state(raw_status)
                        raw_count = slot_data.get("item_count")

                        try:
                            item_count = int(raw_count) if raw_count is not None else None
                        except (TypeError, ValueError):
                            item_count = None

                        if item_count is None:
                            item_count = 0 if shelf_state == "empty" else 1

                        # Create a unique key for tracking shelf state transitions
                        shelf_key = f"product:{product_name}"
                        should_create_order = self._should_create_restock_order(
                            shelf_key, shelf_state
                        )

                        if should_create_order:
                            restock_quantity = 2 if shelf_state == "empty" else 1

                            # Reflect missing stock immediately when sensor detects empty/partial shelf
                            product.stock = max(0, product.stock - restock_quantity)
                            product.save(update_fields=["stock"])

                            system_user, _ = User.objects.get_or_create(
                                username="RECAP", defaults={"email": ""}
                            )

                            order = Order(user=system_user, status=Order.StatusChoices.PENDING)
                            order._skip_mqtt_signal = True
                            order.save()

                            OrderItem.objects.create(
                                order=order, product=product, quantity=restock_quantity
                            )

                            logger.info(
                                "Created restock order %s for product %s (%s) - "
                                "quantity: %s (shelf_state transition FILLED->%s, item_count=%s)",
                                order.order_id,
                                product.id,
                                product_name,
                                restock_quantity,
                                shelf_state,
                                item_count,
                            )

                            camera_restock_task.delay(
                                product_id=product.id,
                                shelf_state=shelf_state,
                                current_stock=item_count,
                                explicit_quantity=restock_quantity,
                                shelf_location=product.shelf_location or "Unknown",
                            )
                        else:
                            logger.debug(
                                "Skipping restock for product %s - state transition not FILLED->%s",
                                product_name,
                                shelf_state,
                            )
                    except Product.DoesNotExist:
                        logger.warning("Product %s not found in database", product_name)
                    except Exception as exc:
                        logger.exception(
                            "Failed to process slot for product %s: %s",
                            product_name,
                            exc,
                        )

                # Check for wrong items and send notifications
                for product_name, slot_data in slots.items():
                    if slot_data.get("status") == "WRONG ITEM":
                        from api.events import EventBus

                        EventBus.publish(
                            "wrong_item",
                            {
                                "product_name": product_name,
                                "slot_data": slot_data,
                                "timestamp": data.get("timestamp"),
                            },
                        )
                        logger.info(
                            "Sent notification for wrong item: %s", product_name
                        )

                # Check for camera obstacles and send notification
                if data.get("obstacles", 0) > 0:
                    from api.events import EventBus

                    EventBus.publish(
                        "camera_blocked",
                        {
                            "obstacles": data.get("obstacles"),
                            "timestamp": data.get("timestamp"),
                        },
                    )
                    logger.info(
                        "Sent notification for camera blocked: %s " "obstacles",
                        data.get("obstacles"),
                    )

                return

            # Legacy format handling
            product_id = data.get("product.id")
            raw_shelf_state = data.get("shelf_state")
            shelf_state = self._normalize_shelf_state(raw_shelf_state)
            current_stock = data.get("item_count")
            shelf_location = data.get("shelf_location")

            # Fallback to topic suffix for product id if payload omits it.
            if not product_id:
                topic_parts = message.topic.split("/")
                if topic_parts and topic_parts[-1].isdigit():
                    product_id = int(topic_parts[-1])

            if product_id is None:
                logger.debug("MQTT message ignored: missing product_id")
                return

            try:
                current_stock = int(current_stock) if current_stock is not None else None
            except (TypeError, ValueError):
                current_stock = None

            if current_stock is None:
                current_stock = 0 if shelf_state == "empty" else 1

            try:
                from api.celery_tasks import camera_restock_task
                from api.models import Product, Order, OrderItem, User

                product = Product.objects.get(id=product_id)

                # Create a unique key for tracking shelf state transitions
                shelf_key = f"product:{product_id}"
                should_create_order = self._should_create_restock_order(
                    shelf_key, shelf_state
                )

                if should_create_order:
                    restock_quantity = 2 if shelf_state == "empty" else 1

                    # Reflect missing stock immediately when sensor detects empty/partial shelf
                    product.stock = max(0, product.stock - restock_quantity)
                    product.save(update_fields=["stock"])

                    system_user, _ = User.objects.get_or_create(
                        username="RECAP", defaults={"email": ""}
                    )

                    order = Order(user=system_user, status=Order.StatusChoices.PENDING)
                    order._skip_mqtt_signal = True
                    order.save()

                    OrderItem.objects.create(
                        order=order, product=product, quantity=restock_quantity
                    )

                    logger.info(
                        "Created restock order %s for product %s from MQTT topic %s "
                        "(shelf_state transition FILLED->%s, stock=%s)",
                        order.order_id,
                        product_id,
                        message.topic,
                        shelf_state,
                        current_stock,
                    )

                    camera_restock_task.delay(
                        product_id=product.id,
                        shelf_state=shelf_state,
                        current_stock=current_stock,
                        explicit_quantity=restock_quantity,
                        shelf_location=shelf_location or product.shelf_location or "Unknown",
                    )
                else:
                    logger.debug(
                        "Skipping restock for product %s - state transition not FILLED->%s",
                        product_id,
                        shelf_state,
                    )
            except Product.DoesNotExist:
                logger.warning("Product with ID %s not found in database", product_id)
            except Exception as exc:
                logger.exception(
                    "Failed to process legacy MQTT message for product %s: %s",
                    product_id,
                    exc,
                )
        except Exception as exc:
            logger.exception("Unexpected error in MQTT message handler: %s", exc)

    def _run_loop(self):
        """Main MQTT loop that handles connection and reconnection with
        exponential backoff."""
        reconnect_delay = 1  # Start with 1 second delay
        max_delay = 60  # Cap at 60 seconds
        connection_attempt = 0

        while self.running:
            try:
                connection_attempt += 1
                # Use a unique client ID with timestamp to avoid ACL conflicts
                unique_client_id = (
                    f"{MQTT_CLIENT_ID}-{os.getpid()}-{connection_attempt}"
                )

                self.client = mqtt.Client(
                    callback_api_version=mqtt.CallbackAPIVersion.VERSION1,
                    client_id=unique_client_id,
                    reconnect_on_failure=True,
                    clean_session=True,  # Clean session to avoid stale subscriptions
                )
                self.client.on_connect = self._on_connect
                self.client.on_disconnect = self._on_disconnect
                self.client.on_message = self._on_message

                if os.environ.get("MQTT_USERNAME") and os.environ.get("MQTT_PASSWORD"):
                    self.client.username_pw_set(
                        os.environ.get("MQTT_USERNAME"),
                        os.environ.get("MQTT_PASSWORD"),
                    )

                logger.debug(
                    "Attempting to connect to MQTT broker at %s:%s "
                    "with client_id=%s",
                    MQTT_BROKER_HOST,
                    MQTT_BROKER_PORT,
                    unique_client_id,
                )
                self.client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT, MQTT_KEEPALIVE)
                # Use loop_start() instead of loop_forever() to allow
                # graceful shutdown
                self.client.loop_start()

                # Wait for successful connection
                connection_timeout = time.time() + 10  # 10 second timeout
                while (
                    self.running
                    and not self.connected
                    and time.time() < connection_timeout
                ):
                    time.sleep(0.5)

                if self.connected:
                    # Connected successfully, reset reconnect delay
                    reconnect_delay = 1

                    # Keep the thread alive while running and connected
                    while self.running and self.connected:
                        time.sleep(1)
                else:
                    # Connection or subscription failed
                    logger.warning(
                        "Failed to establish MQTT connection, will retry "
                        "in %s seconds",
                        reconnect_delay,
                    )
                    if self.client:
                        try:
                            self.client.loop_stop()
                            self.client.disconnect()
                        except Exception:
                            pass
                    time.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, max_delay)

            except Exception as exc:
                logger.exception("MQTT listener error: %s", exc)
                if self.running:
                    if self.client:
                        try:
                            self.client.loop_stop()
                        except Exception:
                            pass
                    time.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, max_delay)

        # Clean shutdown
        if self.client:
            try:
                self.client.loop_stop()
                self.client.disconnect()
            except Exception:
                pass

    def start(self):
        """Start the MQTT listener in a background thread."""
        if self.running:
            logger.warning("MQTT listener is already running")
            return

        self.running = True
        self.thread = threading.Thread(
            target=self._run_loop,
            name="MQTTListenerThread",
            daemon=True,
        )
        self.thread.start()
        logger.info(
            "Started MQTT listener thread for mosquitto broker %s:%s",
            MQTT_BROKER_HOST,
            MQTT_BROKER_PORT,
        )

    def stop(self):
        """Stop the MQTT listener."""
        if not self.running:
            logger.warning("MQTT listener is not running")
            return

        self.running = False
        if self.client:
            try:
                logger.debug("Stopping MQTT client loop")
                self.client.loop_stop()  # Stop the loop before disconnecting
                self.client.disconnect()
            except Exception as exc:
                logger.warning("Error disconnecting MQTT client: %s", exc)

        logger.info("MQTT listener stopped")

    def is_running(self):
        """Check if the MQTT listener is running."""
        return self.running and self.thread and self.thread.is_alive()

    def is_connected(self):
        """Check if the MQTT client is connected to the broker."""
        return self.connected


# Global MQTT listener instance
_mqtt_listener = MQTTListener()


def start_mqtt_listener():
    """Start the global MQTT listener."""
    _mqtt_listener.start()


def stop_mqtt_listener():
    """Stop the global MQTT listener."""
    _mqtt_listener.stop()


def get_mqtt_status():
    """Get the status of the MQTT listener."""
    return {
        "running": _mqtt_listener.is_running(),
        "connected": _mqtt_listener.is_connected(),
    }


# Legacy functions for backward compatibility
def _on_connect(client, userdata, flags, rc):
    _mqtt_listener._on_connect(client, userdata, flags, rc)


def _on_message(client, userdata, message):
    _mqtt_listener._on_message(client, userdata, message)


def _run_mqtt_loop():
    _mqtt_listener._run_loop()
