import json
import os
import threading
import time

import paho.mqtt.client as mqtt
import rclpy
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.action.server import ServerGoalHandle
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from my_recap_interfaces.action import Restock

MQTT_BROKER_HOST = os.environ.get("MQTT_BROKER_HOST", "10.15.173.106")
MQTT_BROKER_PORT = int(os.environ.get("MQTT_BROKER_PORT", "1883"))
MQTT_TOPIC = os.environ.get("MQTT_TOPIC", "shelf/status")
MQTT_CLIENT_ID = os.environ.get("MQTT_CLIENT_ID", "restock-server")


class RestockCoordinator(Node):

    def __init__(self):
        super().__init__('restock_coordinator')

        self._shelf_status_lock = threading.Lock()
        self._latest_status = {}
        self._confirmation_events = {}

        self.action_server_ = ActionServer(
            self,
            Restock,
            'restock',
            execute_callback=self.execute_callback,
            goal_callback=self.goal_callback,
            cancel_callback=self.cancel_callback,
        )

        self._init_mqtt_client()
        self.get_logger().info("Restock Action Server Ready")

    def _init_mqtt_client(self):
        self.mqtt_client = mqtt.Client(
            client_id=MQTT_CLIENT_ID,
            reconnect_on_failure=True,
            clean_session=True,
        )
        self.mqtt_client.on_connect = self._on_mqtt_connect
        self.mqtt_client.on_disconnect = self._on_mqtt_disconnect
        self.mqtt_client.on_message = self._on_mqtt_message

        try:
            self.mqtt_client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT, 60)
            self.mqtt_client.loop_start()
            self.get_logger().info(
                f"Connected restock server MQTT client to {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}"
            )
        except Exception as exc:
            self.get_logger().warning(
                f"Failed to start MQTT listener in restock server: {exc}"
            )

    def _on_mqtt_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.get_logger().info(f"Restock server subscribed to MQTT topic {MQTT_TOPIC}")
            client.subscribe(MQTT_TOPIC)
        else:
            self.get_logger().warning(f"Restock server MQTT connection failed: {rc}")

    def _on_mqtt_disconnect(self, client, userdata, rc):
        if rc == 0:
            self.get_logger().info("Restock server MQTT disconnected normally")
        else:
            self.get_logger().warning(f"Restock server MQTT disconnected unexpectedly: {rc}")

    def _normalize_shelf_state(self, raw_status):
        status = (raw_status or "").strip().lower()
        if not status:
            return ""
        if "empty" in status and "partial" not in status:
            return "empty"
        if "partial" in status or "p. filled" in status or status.startswith("p"):
            return "partial"
        if "filled" in status or "full" in status:
            return "FILLED"
        return ""

    def _on_mqtt_message(self, client, userdata, message):
        try:
            payload = message.payload.decode("utf-8")
            self.get_logger().debug(
                f"Restock server MQTT received topic={message.topic} payload={payload}"
            )
            data = json.loads(payload)
        except Exception as exc:
            self.get_logger().warning(f"Ignoring invalid MQTT payload: {exc}")
            return

        self._process_mqtt_update(data)

    def _process_mqtt_update(self, data):
        if not isinstance(data, dict):
            return

        if "slots" in data:
            for product_name, slot_data in data.get("slots", {}).items():
                shelf_location = slot_data.get("shelf_location")
                shelf_state = self._normalize_shelf_state(slot_data.get("status"))
                self._update_shelf_status(shelf_location, product_name, shelf_state)
            return

        product_name = data.get("product_name") or data.get("product.name")
        shelf_location = data.get("shelf_location")
        shelf_state = self._normalize_shelf_state(data.get("shelf_state"))

        self._update_shelf_status(shelf_location, product_name, shelf_state)

    def _build_status_keys(self, shelf_location, product_name):
        keys = []
        if shelf_location:
            keys.append(f"shelf:{shelf_location}")
        if product_name:
            keys.append(f"product:{product_name}")
        return keys

    def _update_shelf_status(self, shelf_location, product_name, shelf_state):
        if not shelf_location and not product_name:
            return

        keys = self._build_status_keys(shelf_location, product_name)
        with self._shelf_status_lock:
            for key in keys:
                self._latest_status[key] = shelf_state
                if shelf_state == "FILLED":
                    self._confirmation_events.setdefault(key, threading.Event()).set()
                else:
                    event = self._confirmation_events.get(key)
                    if event is not None:
                        event.clear()

            self.get_logger().info(
                f"Updated restock server shelf status: {', '.join(keys)} -> {shelf_state}"
            )

    def _is_shelf_full(self, shelf_location, product_name):
        keys = self._build_status_keys(shelf_location, product_name)
        with self._shelf_status_lock:
            return any(self._latest_status.get(key) == "FILLED" for key in keys)

    def _get_shelf_state(self, shelf_location, product_name):
        keys = self._build_status_keys(shelf_location, product_name)
        with self._shelf_status_lock:
            for key in keys:
                if key in self._latest_status:
                    return self._latest_status[key]
        return ""

    def _get_or_create_events(self, shelf_location, product_name):
        keys = self._build_status_keys(shelf_location, product_name)
        events = []
        with self._shelf_status_lock:
            for key in keys:
                events.append(self._confirmation_events.setdefault(key, threading.Event()))
        return events

    def _clear_events(self, shelf_location, product_name):
        keys = self._build_status_keys(shelf_location, product_name)
        with self._shelf_status_lock:
            for key in keys:
                self._confirmation_events.pop(key, None)

    def _wait_for_shelf_full(self, goal_handle: ServerGoalHandle, shelf_location, product_name, current_state, expected_state="FILLED"):
        if not shelf_location and not product_name:
            self.get_logger().warn(
                "No shelf or product identifier available for final confirmation. Cancelling mission without MQTT confirmation."
            )
            return False

        current_state = self._get_shelf_state(shelf_location, product_name)
        if current_state == expected_state or current_state == "FILLED":
            self.get_logger().info(
                f"Shelf {shelf_location or product_name} already in desired state '{current_state}'."
            )
            return True

        self.get_logger().info(
            f"Shelf {shelf_location or product_name} initial state: '{current_state}'. "
            f"Waiting until it becomes '{expected_state}'."
        )

        events = self._get_or_create_events(shelf_location, product_name)
        feedback_msg = Restock.Feedback()

        while True:
            if goal_handle.is_cancel_requested:
                goal_handle.canceled()
                self.get_logger().info("Goal canceled while waiting for shelf confirmation")
                self._clear_events(shelf_location, product_name)
                return False

            current_state = self._get_shelf_state(shelf_location, product_name)
            if current_state == expected_state or current_state == "FILLED":
                self.get_logger().info(
                    f"Shelf {shelf_location or product_name} reached desired state '{current_state}'."
                )
                self._clear_events(shelf_location, product_name)
                return True

            if any(event.is_set() for event in events):
                self.get_logger().info(
                    f"Received FILLED confirmation for {shelf_location or product_name}."
                )
                self._clear_events(shelf_location, product_name)
                return True

            feedback_msg.current_step = "Waiting for shelf full confirmation"
            feedback_msg.progress = 0.95
            goal_handle.publish_feedback(feedback_msg)
            time.sleep(0.5)

    # Goal Validation

    def goal_callback(self, goal_request):
        self.get_logger().info(f"Received goal for item {goal_request.product_name} (quantity: {goal_request.quantity})")

        # Validate goal
        if goal_request.quantity < 0:
            self.get_logger().warn("Rejected goal: negative quantity")
            return GoalResponse.REJECT

        return GoalResponse.ACCEPT

    # -------------------------
    # Cancellation Handling
    # -------------------------
    def cancel_callback(self, goal_handle: ServerGoalHandle):
        self.get_logger().info("Cancel request received")
        return CancelResponse.ACCEPT

    # -------------------------
    # Core Execution Logic
    # -------------------------
    def execute_callback(self, goal_handle: ServerGoalHandle):

        self.get_logger().info("Executing restock mission")

        feedback_msg = Restock.Feedback()
        result = Restock.Result()

        try:
            # ---- STATE 1: VALIDATE ----
            feedback_msg.current_step = "Validating inventory"
            feedback_msg.progress = 0.05
            goal_handle.publish_feedback(feedback_msg)
            self.simulated_delay(goal_handle)

            # ---- STATE 2: NAVIGATE TO PICKUP ----
            feedback_msg.current_step = "Navigating to pickup location"
            feedback_msg.progress = 0.25
            goal_handle.publish_feedback(feedback_msg)
            self.simulated_delay(goal_handle)

            # ---- STATE 3: PICK ITEM ----
            feedback_msg.current_step = "Picking item"
            feedback_msg.progress = 0.45
            goal_handle.publish_feedback(feedback_msg)
            self.simulated_delay(goal_handle)

            # ---- STATE 4: NAVIGATE TO SHELF ----
            feedback_msg.current_step = "Navigating to shelf"
            feedback_msg.progress = 0.70
            goal_handle.publish_feedback(feedback_msg)
            self.simulated_delay(goal_handle)

            # ---- STATE 5: PLACE ITEM ----
            feedback_msg.current_step = "Placing item"
            feedback_msg.progress = 0.90
            goal_handle.publish_feedback(feedback_msg)
            self.simulated_delay(goal_handle)

            # ---- COMPLETE ----
            feedback_msg.current_step = "Final verification"
            feedback_msg.progress = 0.92
            goal_handle.publish_feedback(feedback_msg)

            current_state = goal_handle.request.current_state
            expected_state = "FILLED"  # For partial, wait for FILLED

            if not self._wait_for_shelf_full(
                goal_handle,
                goal_handle.request.shelf_location,
                goal_handle.request.product_name,
                current_state,
                expected_state,
            ):
                raise Exception("Mission canceled during final confirmation")

            feedback_msg.current_step = "Restock confirmed full"
            feedback_msg.progress = 1.0
            goal_handle.publish_feedback(feedback_msg)

            result.success = True
            result.message = "Restock completed successfully"

            goal_handle.succeed()
            self.get_logger().info("Restock mission succeeded")

        except Exception as e:
            result.success = False
            result.message = str(e)
            goal_handle.abort()
            self.get_logger().error(f"Mission failed: {e}")

        return result

    # -------------------------
    # Simulated Work + Cancel Check
    def simulated_delay(self, goal_handle):
        for _ in range(10):
            if goal_handle.is_cancel_requested:
                goal_handle.canceled()
                self.get_logger().info("Goal canceled")
                raise Exception("Mission canceled")

            time.sleep(0.2)

    def destroy_node(self):
        try:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
        except Exception:
            pass
        super().destroy_node()


# -------------------------
# Main Entry

def main(args=None):
    rclpy.init(args=args)

    node = RestockCoordinator()

    executor = MultiThreadedExecutor()
    executor.add_node(node)

    try:
        executor.spin()
    except KeyboardInterrupt:
        pass

    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
