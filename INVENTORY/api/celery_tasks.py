import logging
import os
from datetime import timedelta

import requests
from celery import shared_task, chain, chord, group
from celery.signals import task_revoked
from django.db.models import F
from django.utils import timezone

from api.events import EventBus
from api.models import Product, RestockItem, MAX_STOCK

logger = logging.getLogger(__name__)

ROS_BRIDGE_API_URL = os.environ.get("ROS_BRIDGE_API_URL", "http://localhost:9000")


@shared_task(bind=True, max_retries=3)
def validate_restock_task(self, product_id):
    try:

        product = Product.objects.get(id=product_id)

        # Conditions
        if not product.auto_restock_enabled:
            logger.info(f"Product {product_id} has auto_restock disabled")
            return {
                "is_valid": False,
                "reason": "auto_restock_disabled",
                "product_id": product_id,
            }

        pending = RestockItem.objects.filter(
            product_id=product_id, status__in=["PENDING", "IN_PROGRESS"]
        ).exists()

        if pending:
            logger.info(f"Pending restock exists for product {product_id}")
            return {
                "is_valid": False,
                "reason": "pending_restock_exists",
                "product_id": product_id,
            }

        logger.info(f"Product {product_id} has passed validation")
        return {
            "is_valid": True,
            "product_id": product_id,
        }

    except Product.DoesNotExist:
        self.dont_retry = True
        raise
    except Exception as exc:
        logger.error(f"Validation error: {exc}")
        raise self.retry(exc=exc, countdown=300)  # Automatic retry after 5 minutes


# Task creation
@shared_task(bind=True, max_retries=3)
def create_restock_item_task(
    self,
    product_id,
    current_stock,
    explicit_quantity=None,
    shelf_location=None,
    priority=2,
):

    try:
        product = Product.objects.get(id=product_id)

        # Determine how many items are needed using the camera-provided current_stock
        needed = product.restock_quantity_needed(current_stock=current_stock)

        if explicit_quantity is not None:
            # Do not allow explicit quantity to exceed needed amount
            quantity = min(int(explicit_quantity), needed) if needed > 0 else 0
        else:
            quantity = needed

        # If nothing is needed (already at max), publish a notification and don't create a restock
        if quantity <= 0:
            EventBus.publish(
                "restock_rejected_full",
                {
                    "product_id": product_id,
                    "current_stock": current_stock,
                    "max_stock": MAX_STOCK,
                },
            )
            logger.info(
                f"Restock rejected for product {product_id}: already at or above max stock ({current_stock})"
            )
            return {
                "rejected": True,
                "reason": "max_stock_reached",
                "product_id": product_id,
            }

        restock_item = RestockItem.objects.create(
            product=product,
            quantity=quantity,
            shelf_location=shelf_location or product.shelf_location or "Unknown",
            status="PENDING",
            priority=priority,
        )

        EventBus.publish(
            "restock_item_created",
            {
                "product_id": product_id,
                "quantity": needed,
                "shelf_location": restock_item.shelf_location,
                "priority": priority,
            },
        )

        logger.info(f"Created RestockItem {restock_item.id} for product {product_id}")

        return {
            "restock_item_id": restock_item.id,
            "quantity": needed,
            "priority": priority,
        }

    except Product.DoesNotExist:
        self.dont_retry = True
        raise
    except Exception as exc:
        logger.error(f"Failed to create RestockItem: {exc}")
        raise self.retry(exc=exc, countdown=300)


@shared_task(bind=True, max_retries=3)
def queue_restock_task(
    self,
    product_id,
    current_stock,
    priority=None,
    shelf_state=None,
    shelf_location=None,
    explicit_quantity=None,
):
    """Queue a product restock and start the next queued mission if the system
    is idle."""
    try:
        if priority is None and shelf_state is not None:
            if shelf_state == "empty":
                priority = 1
            elif shelf_state == "partial":
                priority = 2
            else:
                raise ValueError("Invalid shelf_state for restock queue")

        product = Product.objects.get(id=product_id)

        if not product.auto_restock_enabled:
            self.dont_retry = True
            raise ValueError("Auto restock is disabled for this product")

        pending = RestockItem.objects.filter(
            product_id=product_id, status__in=["PENDING", "IN_PROGRESS"]
        ).exists()

        if pending:
            self.dont_retry = True
            raise ValueError(
                "A pending or in-progress restock already exists for this product"
            )

        # Use sensor-provided current_stock to calculate needed quantity and respect MAX_STOCK
        needed = product.restock_quantity_needed(current_stock=current_stock)

        if explicit_quantity is not None and needed > 0:
            quantity = min(int(explicit_quantity), needed)
        else:
            quantity = needed

        if quantity <= 0:
            EventBus.publish(
                "restock_rejected_full",
                {
                    "product_id": product_id,
                    "current_stock": current_stock,
                    "max_stock": MAX_STOCK,
                },
            )
            self.dont_retry = True
            raise ValueError("Product already at max stock")

        restock_item = RestockItem.objects.create(
            product=product,
            quantity=quantity,
            shelf_location=shelf_location or product.shelf_location or "Unknown",
            status="PENDING",
            priority=priority,
            shelf_state=shelf_state,
        )

        EventBus.publish(
            "restock_item_created",
            {
                "product_id": product_id,
                "quantity": needed,
                "shelf_location": restock_item.shelf_location,
                "priority": priority,
            },
        )

        logger.info(f"Queued RestockItem {restock_item.id} for product {product_id}")

        if not RestockItem.objects.filter(status="IN_PROGRESS").exists():
            process_restock_queue.delay()

        return {
            "restock_item_id": restock_item.id,
            "quantity": needed,
            "priority": priority,
        }

    except Product.DoesNotExist:
        self.dont_retry = True
        raise
    except Exception as exc:
        logger.error(f"Failed to queue RestockItem: {exc}")
        raise self.retry(exc=exc, countdown=300)


@shared_task(bind=True, max_retries=3)
def camera_restock_task(
    self,
    product_id,
    shelf_state,
    current_stock,
    explicit_quantity=None,
    shelf_location=None,
):
    """Create a prioritized restock from camera/MQTT shelf state updates."""
    try:
        if shelf_state not in ["empty", "partial"]:
            raise ValueError("Invalid shelf state for camera restock")

        priority = 1 if shelf_state == "empty" else 2
        workflow_label = "EMPTY_RESTOCK" if shelf_state == "empty" else "PARTIAL_RESTOCK"

        logger.info(
            "Camera restock task: product=%s shelf_state=%s workflow=%s priority=%s",
            product_id,
            shelf_state,
            workflow_label,
            priority,
        )

        return queue_restock_task.delay(
            product_id=product_id,
            current_stock=current_stock,
            priority=priority,
            shelf_state=shelf_state,
            shelf_location=shelf_location,
            explicit_quantity=explicit_quantity,
        )

    except Exception as exc:
        logger.error(f"Failed to create camera restock item: {exc}")
        raise self.retry(exc=exc, countdown=300)


# Robot triggering (External API call)
@shared_task(bind=True, max_retries=5)
def trigger_robot_mission_task(self, restock_data):
    try:
        if isinstance(restock_data, int):
            restock_item_id = restock_data
        else:
            restock_item_id = restock_data.get("restock_item_id")

        restock_item = RestockItem.objects.get(id=restock_item_id)

        # Check if already completed to prevent re-execution on worker restart
        if restock_item.status == "COMPLETED":
            logger.info(f"Restock item {restock_item_id} already completed, skipping")
            return {
                "restock_item_id": restock_item.id,
                "mission_started": True,
                "status": "COMPLETED",
                "skipped": True,
            }

        product = restock_item.product

        # Status update
        restock_item.status = "IN_PROGRESS"
        restock_item.save(update_fields=["status"])

        url = f"{ROS_BRIDGE_API_URL}/restock/queue"
        payload = {
            "item_id": restock_item.id,
            "product_name": product.name,
            "quantity": restock_item.quantity,
            "shelf_location": restock_item.shelf_location,
            "current_state": restock_item.shelf_state or "unknown",
        }

        try:
            response = requests.post(url, json=payload, timeout=3600)
            response.raise_for_status()
            mission_result = response.json()

            logger.info(
                f"Robot mission response for item {restock_item.id}: "
                f"{mission_result}"
            )

            EventBus.publish(
                "restock_mission_started",
                {
                    "restock_item_id": restock_item.id,
                    "product_name": product.name,
                },
            )

            if mission_result.get("success") or mission_result.get("status") in (
                "mission_complete",
                "COMPLETED",
            ):
                restock_item.status = "COMPLETED"
                product.stock += restock_item.quantity
                product.save(update_fields=["stock"])
                restock_item.save(update_fields=["status"])

                EventBus.publish(
                    "restock_mission_completed",
                    {
                        "restock_item_id": restock_item.id,
                        "product_name": product.name,
                        "quantity_restocked": restock_item.quantity,
                    },
                )

                process_restock_queue.delay()

                return {
                    "restock_item_id": restock_item.id,
                    "mission_started": True,
                    "status": "COMPLETED",
                }

            restock_item.status = "FAILED"

            restock_item.save(update_fields=["status"])

            EventBus.publish(
                "restock_mission_failed",
                {
                    "restock_item_id": restock_item.id,
                    "product_name": product.name,
                    "reason": mission_result.get("status", "unknown"),
                },
            )

            process_restock_queue.delay()

            self.dont_retry = True
            raise ValueError("Robot mission failed")

        except (requests.ConnectionError, requests.Timeout) as exc:
            logger.warning(f"ROS Bridge unreachable: {exc}")
            # Retry in case server is down temporarily
            countdown = 600 * (self.request.retries + 1)
            # Exponential backoff
            raise self.retry(exc=exc, countdown=countdown)

    except RestockItem.DoesNotExist:
        self.dont_retry = True
        raise
    except ValueError:
        # Mission failed in an expected way and should not be retried.
        raise
    except Exception as exc:
        logger.error(f"Error triggering mission: {exc}")
        raise self.retry(exc=exc, countdown=300)


@shared_task
def process_restock_queue():
    """Start the next pending restock if no mission is currently in progress."""
    if RestockItem.objects.filter(status="IN_PROGRESS").exists():
        logger.info(
            "A restock mission is already in progress; queue processing deferred."
        )
        return {"queued": False, "reason": "in_progress_exists"}

    next_item = (
        RestockItem.objects.filter(status="PENDING")
        .order_by("priority", "created_at")
        .first()
    )
    if not next_item:
        logger.info("No pending restock items to process.")
        return {"queued": False, "reason": "no_pending_items"}

    logger.info(
        f"Starting next queued restock item: {next_item.id} "
        f"(priority={next_item.priority})"
    )
    trigger_robot_mission_task.delay({"restock_item_id": next_item.id})
    return {"queued": True, "restock_item_id": next_item.id}


@task_revoked.connect
def handle_task_revoked(sender=None, request=None, **kwargs):
    """Handle task revocation by marking restock items as failed if in progress."""
    if sender == trigger_robot_mission_task:
        try:
            restock_data = request.args[0] if request.args else None
            if restock_data:
                if isinstance(restock_data, int):
                    restock_item_id = restock_data
                else:
                    restock_item_id = restock_data.get("restock_item_id")

                restock_item = RestockItem.objects.get(id=restock_item_id)
                if restock_item.status == "IN_PROGRESS":
                    restock_item.status = "FAILED"
                    restock_item.save(update_fields=["status"])
                    logger.warning(f"Restock item {restock_item_id} marked as failed due to task revocation")

                    EventBus.publish(
                        "restock_mission_failed",
                        {
                            "restock_item_id": restock_item.id,
                            "product_name": restock_item.product.name,
                            "reason": "task_revoked",
                        },
                    )
        except Exception as exc:
            logger.error(f"Error handling task revocation: {exc}")


# Task with callbacks
@shared_task
def workflow_orchestration(product_id, current_stock):
    # Task execution with conditional branching based on results
    from api.celery_tasks import (
        validate_restock_task,
        create_restock_item_task,
        trigger_robot_mission_task,
    )

    # Callback for passed validation
    def on_validate_completed(validation_result):
        if validation_result:
            # If valid, chain to the next task
            return create_restock_item_task.delay(product_id, current_stock)
        logger.warning("Validation failed or returned no product id")
        return None

    # The chain is initialized with a callback,
    validate_task = validate_restock_task.delay(product_id)
    validate_task.then(on_validate_completed)

    return {"initiated": True}


# Parallel execution
@shared_task
def check_all_products():
    # Checking multiple products in parallel
    from api.celery_tasks import validate_restock_task

    products = Product.objects.filter(auto_restock_enabled=True)

    # Creating a group of tasks that run in parallel
    parallel_tasks = group(validate_restock_task.s(product.id) for product in products)

    # Group execution
    result = parallel_tasks.apply_async()

    # Get results when ready
    all_results = result.get()

    return {
        "total_products": len(products),
        "results": all_results,
    }


@shared_task(bind=True)
def check_low_stock_products(self):
    low_stock_products = Product.objects.filter(
        stock__lt=F("restock_threshold"),
        auto_restock_enabled=True,
    )

    for product in low_stock_products:
        workflow_orchestration.delay(product_id=product.id, current_stock=product.stock)

    return {"queued": low_stock_products.count()}


@shared_task(bind=True)
def cleanup_old_restocks(self):
    cutoff = timezone.now() - timedelta(days=2)
    deleted, _ = RestockItem.objects.filter(
        status="COMPLETED",
        updated_at__lt=cutoff,
    ).delete()
    return {"deleted": deleted}
