import pytest
from unittest.mock import Mock, patch, MagicMock
from django.test import TestCase
from api.mqtt import (
    MQTTListener,
    start_mqtt_listener,
    stop_mqtt_listener,
    get_mqtt_status,
)


class MQTTListenerTestCase(TestCase):
    def setUp(self):
        self.listener = MQTTListener()

    def tearDown(self):
        if self.listener.is_running():
            self.listener.stop()

    @patch("api.mqtt.mqtt.Client")
    def test_mqtt_listener_initialization(self, mock_client_class):
        """Test that MQTT listener initializes correctly."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        self.listener.start()
        self.assertTrue(self.listener.is_running())

        self.listener.stop()
        self.assertFalse(self.listener.is_running())

    @patch("api.mqtt.mqtt.Client")
    def test_mqtt_message_handling_restock(self, mock_client_class):
        """Test that MQTT messages trigger restock tasks."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        # Mock the message
        mock_message = Mock()
        mock_message.payload = (
            b'{"slots": {"Product A": {"status": "EMPTY", "item_count": 0}}}'
        )
        mock_message.topic = "shelf/status"

        with patch("api.mqtt.Product.objects.get") as mock_get_product, patch(
            "api.celery_tasks.camera_restock_task.delay"
        ) as mock_camera_task:

            mock_product = Mock()
            mock_product.id = 1
            mock_product.name = "Product A"
            mock_product.shelf_location = "A1"
            mock_get_product.return_value = mock_product

            self.listener._on_message(mock_client, None, mock_message)

            mock_camera_task.assert_called_once_with(
                product_id=1,
                shelf_state="empty",
                current_stock=0,
                explicit_quantity=2,
                shelf_location="A1",
            )

    @patch("api.mqtt.mqtt.Client")
    def test_mqtt_message_handling_wrong_item(self, mock_client_class):
        """Test that wrong item messages publish events."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        mock_message = Mock()
        mock_message.payload = b'{"slots": {"Product A": {"status": "WRONG ITEM", "item_count": 1}}, "timestamp": "2024-01-01T12:00:00Z"}'
        mock_message.topic = "shelf/status"

        with patch("api.events.EventBus.publish") as mock_publish:
            self.listener._on_message(mock_client, None, mock_message)

            mock_publish.assert_called_once()
            call_args = mock_publish.call_args
            self.assertEqual(call_args[0][0], "wrong_item")
            self.assertIn("product_name", call_args[0][1])
            self.assertEqual(call_args[0][1]["product_name"], "Product A")

    @patch("api.mqtt.mqtt.Client")
    def test_mqtt_message_handling_camera_blocked(self, mock_client_class):
        """Test that camera blocked messages publish events."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        mock_message = Mock()
        mock_message.payload = b'{"obstacles": 2, "timestamp": "2024-01-01T12:00:00Z"}'
        mock_message.topic = "shelf/status"

        with patch("api.events.EventBus.publish") as mock_publish:
            self.listener._on_message(mock_client, None, mock_message)

            mock_publish.assert_called_once()
            call_args = mock_publish.call_args
            self.assertEqual(call_args[0][0], "camera_blocked")
            self.assertEqual(call_args[0][1]["obstacles"], 2)

    def test_mqtt_status_functions(self):
        """Test MQTT status functions work correctly."""
        # Initially not running
        status = get_mqtt_status()
        self.assertFalse(status["running"])
        self.assertFalse(status["connected"])

        # After starting (mock)
        with patch.object(self.listener, "is_running", return_value=True), patch.object(
            self.listener, "is_connected", return_value=True
        ):
            status = get_mqtt_status()
            self.assertTrue(status["running"])
            self.assertTrue(status["connected"])


class MQTTIntegrationTestCase(TestCase):
    """Integration tests for MQTT functionality."""

    @patch.dict("os.environ", {"DISABLE_MQTT": "true"})
    def test_mqtt_disabled_via_environment(self):
        """Test that MQTT can be disabled via environment variable."""
        # This would normally start MQTT, but should be disabled
        from api.apps import ApiConfig

        config = ApiConfig("api", None)

        # The ready method should not start MQTT when DISABLE_MQTT=true
        with patch("api.mqtt.start_mqtt_listener") as mock_start:
            config.ready()
            mock_start.assert_not_called()

    @patch("api.mqtt.mqtt.Client")
    def test_mqtt_reconnection_logic(self, mock_client_class):
        """Test that MQTT reconnects after disconnection."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.connect.side_effect = Exception("Connection failed")

        # Start listener - it should handle connection failures gracefully
        self.listener.start()

        # Give it a moment to attempt connection
        import time

        time.sleep(0.1)

        # Should still be running despite connection failure
        self.assertTrue(self.listener.is_running())

        self.listener.stop()
