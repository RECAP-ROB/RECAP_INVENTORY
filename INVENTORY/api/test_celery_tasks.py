from django.test import TestCase
from unittest.mock import patch, MagicMock
from celery.result import EagerResult
from main.celery import app
from api.models import Product, RestockItem, User
from api.serializers import OrderCreateSerializer
from api.celery_tasks import (
    validate_restock_task,
    create_restock_item_task,
    trigger_robot_mission_task,
)

# Eager mode is enabled for testing
app.conf.task_always_eager = True
app.conf.task_eager_propagates = True


class ValidateRestockTaskTest(TestCase):
    def setUp(self):
        self.product = Product.objects.create(
            name="Test Product",
            description="Test",
            price=9.99,
            stock=5,
            auto_restock_enabled=True,
            restock_threshold=5,
        )

    def test_validation_passes(self):
        result = validate_restock_task.delay(self.product.id)

        self.assertTrue(result.successful())
        self.assertEqual(result.result["is_valid"], True)

    def test_validation_fails_disabled(self):
        # Tests if validation fails when auto restock is disabled
        self.product.auto_restock_enabled = False
        self.product.save()

        result = validate_restock_task.delay(self.product.id)

        self.assertTrue(result.successful())
        self.assertEqual(result.result["is_valid"], False)

    def test_validation_fails_pending_exists(self):
        # Tests if validation fails when a pending restock task exists
        RestockItem.objects.create(
            product=self.product,
            quantity=5,
            shelf_location="TEST",
            status="PENDING",
        )

        result = validate_restock_task.delay(self.product.id)

        self.assertTrue(result.successful())
        self.assertEqual(result.result["is_valid"], False)


class CreateRestockItemTaskTest(TestCase):
    def setUp(self):
        self.product = Product.objects.create(
            name="Test Product",
            description="Test",
            price=9.99,
            stock=2,
            auto_restock_enabled=True,
            restock_quantity=10,
            shelf_location="SHELF-A1",
        )

    def test_create_restock_item(self):
        result = create_restock_item_task.delay(self.product.id, current_stock=2)

        self.assertTrue(result.successful())
        self.assertEqual(result.result["quantity"], 8)

        # Verify if item is created in the database
        restock = RestockItem.objects.get(id=result.result["restock_item_id"])
        self.assertEqual(restock.quantity, 8)
        self.assertEqual(restock.status, "PENDING")


class TriggerRobotMissionTaskTest(TestCase):
    def setUp(self):
        self.product = Product.objects.create(
            name="Test Product",
            description="Test",
            price=9.99,
            stock=2,
            shelf_location="SHELF_A1",
        )
        self.restock_item = RestockItem.objects.create(
            product=self.product,
            quantity=8,
            shelf_location="SHELF_A1",
            status="PENDING",
        )

    @patch("requests.post")
    def test_trigger_success(self, mock_post):
        # Test successful robot trigger and completion
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "status": "mission_complete",
            "success": True,
        }
        mock_post.return_value = mock_response

        result = trigger_robot_mission_task.delay(
            {"restock_item_id": self.restock_item.id}
        )

        self.assertTrue(result.successful())
        self.assertEqual(result.result["status"], "COMPLETED")

        self.restock_item.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.restock_item.status, "COMPLETED")
        self.assertEqual(self.product.stock, 10)

    @patch("requests.post")
    def test_trigger_retry_on_connection_error(self, mock_post):
        # Test that task retries on connection error
        import requests
        from celery.exceptions import Retry

        mock_post.side_effect = requests.ConnectionError("No connection")

        with self.assertRaises(Retry):
            trigger_robot_mission_task.delay(self.restock_item.id)


class OrderRestockWorkflowTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="password123"
        )
        self.product = Product.objects.create(
            name="Test Product",
            description="Test",
            price=9.99,
            stock=6,
            restock_threshold=5,
            restock_quantity=10,
            auto_restock_enabled=True,
            shelf_location="SHELF_A1",
        )

    @patch("requests.post")
    def test_order_creation_triggers_restock(self, mock_post):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "status": "mission_complete",
            "success": True,
        }
        mock_post.return_value = mock_response

        serializer = OrderCreateSerializer(
            data={
                "status": "Pending",
                "items": [
                    {"product": self.product.id, "quantity": 2},
                ],
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        order = serializer.save(user=self.user)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)

        restock_item = RestockItem.objects.filter(product=self.product).last()
        self.assertIsNotNone(restock_item)
        self.assertEqual(restock_item.status, "COMPLETED")
        self.assertEqual(restock_item.quantity, 6)
        self.assertEqual(order.items.count(), 1)

    @patch("requests.post")
    def test_save_triggers_restock_when_stock_already_below_threshold(self, mock_post):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "status": "mission_complete",
            "success": True,
        }
        mock_post.return_value = mock_response

        self.product.stock = 2
        self.product.save()

        self.product.refresh_from_db()
        restock_item = RestockItem.objects.filter(product=self.product).last()

        self.assertIsNotNone(restock_item)
        self.assertEqual(restock_item.status, "COMPLETED")
        self.assertEqual(self.product.stock, 10)


class RestockQueueBehaviorTest(TestCase):
    @patch("api.celery_tasks.trigger_robot_mission_task.delay")
    def test_pending_item_does_not_start_when_active_mission_exists(
        self, mock_trigger_delay
    ):
        product1 = Product.objects.create(
            name="Product A",
            description="A",
            price=9.99,
            stock=2,
            restock_threshold=5,
            restock_quantity=10,
            auto_restock_enabled=True,
            shelf_location="SHELF_A",
        )
        product2 = Product.objects.create(
            name="Product B",
            description="B",
            price=9.99,
            stock=2,
            restock_threshold=5,
            restock_quantity=10,
            auto_restock_enabled=True,
            shelf_location="SHELF_B",
        )

        RestockItem.objects.create(
            product=product1,
            quantity=8,
            shelf_location="SHELF_A",
            status="IN_PROGRESS",
        )
        RestockItem.objects.create(
            product=product2,
            quantity=8,
            shelf_location="SHELF_B",
            status="PENDING",
        )

        from api.celery_tasks import process_restock_queue

        result = process_restock_queue.delay()

        self.assertTrue(result.successful())
        self.assertEqual(
            result.result, {"queued": False, "reason": "in_progress_exists"}
        )
        mock_trigger_delay.assert_not_called()

    @patch("api.celery_tasks.trigger_robot_mission_task.delay")
    def test_process_restock_queue_starts_oldest_pending_item(self, mock_trigger_delay):
        product1 = Product.objects.create(
            name="Product C",
            description="C",
            price=9.99,
            stock=2,
            restock_threshold=5,
            restock_quantity=10,
            auto_restock_enabled=True,
            shelf_location="SHELF_C",
        )
        product2 = Product.objects.create(
            name="Product D",
            description="D",
            price=9.99,
            stock=2,
            restock_threshold=5,
            restock_quantity=10,
            auto_restock_enabled=True,
            shelf_location="SHELF_D",
        )

        item1 = RestockItem.objects.create(
            product=product1,
            quantity=8,
            shelf_location="SHELF_C",
            status="PENDING",
        )
        RestockItem.objects.create(
            product=product2,
            quantity=8,
            shelf_location="SHELF_D",
            status="PENDING",
        )

        from api.celery_tasks import process_restock_queue

        result = process_restock_queue.delay()

        self.assertTrue(result.successful())
        self.assertEqual(result.result, {"queued": True, "restock_item_id": item1.id})
        mock_trigger_delay.assert_called_once_with({"restock_item_id": item1.id})
