"""
Signal handlers for the restock workflow
It connects Django model signals to orchestrator
"""

from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver
from .models import Product, RestockItem, Order, OrderItem
from .websocket_events import broadcast_update
import logging

logger = logging.getLogger(__name__)

# Cache for tracking stock changes
_product_stock_cache = {}


@receiver(pre_save, sender=Product)
def cache_product_stock(sender, instance, **kwargs):
    # The stock value is first cached before it changes
    try:
        previous = Product.objects.get(pk=instance.pk)
        _product_stock_cache[instance.pk] = previous.stock
    except Product.DoesNotExist:
        _product_stock_cache[instance.pk] = instance.stock


@receiver(post_save, sender=Product)
def handle_stock_below_threshold(sender, instance, created, **kwargs):
    # The restock workflow is queued when stock falls below threshold
    if created:
        return

    current_stock = instance.stock

    if instance.needs_restock():
        logger.info(f"Stock below threshold for '{instance.name}'")

        try:
            from .celery_tasks import workflow_orchestration

            # Task queuing via Celery
            task = workflow_orchestration.delay(
                product_id=instance.id,
                current_stock=current_stock,
            )

            logger.info(f"Restock workflow queued: task_id={task.id}")

        except Exception as exc:
            logger.error(f"Failed to queue restock task: {exc}")

    # Cache is then cleared for the next cached data
    _product_stock_cache.pop(instance.pk, None)


@receiver(post_save, sender=Order)
def handle_order_created(sender, instance, created, **kwargs):
    """When an Order is created, trigger restock workflow for each item.
    MQTT-created orders may already queue the workflow directly in the MQTT
    handler, so skip duplicate processing when indicated."""
    if not created:
        return

    if getattr(instance, "_skip_mqtt_signal", False):
        logger.debug(
            "Skipping order-created restock workflow for MQTT-created order %s",
            instance.order_id,
        )
        return

    try:
        is_mqtt_order = instance.user.username == "RECAP"

        if is_mqtt_order:
            logger.info(f"Processing MQTT-triggered restock order {instance.order_id}")

            from .celery_tasks import workflow_orchestration

            for order_item in instance.items.all():
                try:
                    task = workflow_orchestration.delay(
                        product_id=order_item.product.id,
                        current_stock=order_item.product.stock,
                    )
                    logger.info(
                        f"Queued restock workflow for product "
                        f"{order_item.product.name} "
                        f"(quantity: {order_item.quantity}) - task_id={task.id}"
                    )
                except Exception as exc:
                    logger.exception(
                        f"Failed to queue restock workflow for product "
                        f"{order_item.product.id}: {exc}"
                    )
    except Exception as exc:
        logger.exception(
            f"Error handling order creation for {instance.order_id}: {exc}"
        )


@receiver(post_save, sender=RestockItem)
def restock_item_updated(sender, instance, created, **kwargs):
    """Broadcast restock item updates via WebSocket. Allows real-time UI
    updates for all connected clients."""
    broadcast_update(instance)
    logger.info(f"RestockItem update broadcasted: {instance.id} - {instance.status}")
