import uuid

from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator
from django.db import models

RESTOCK_THRESHOLD_DEFAULT = 1
RESTOCK_TARGET_DEFAULT = 2
# Global maximum stock per shelf/product
MAX_STOCK = 2


class User(AbstractUser):
    pass


class Product(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.PositiveIntegerField(validators=[MaxValueValidator(MAX_STOCK)])
    shelf_location = models.CharField(max_length=100, blank=True, null=True)
    image = models.ImageField(upload_to="products/", blank=True, null=True)
    restock_threshold = models.PositiveIntegerField(default=RESTOCK_THRESHOLD_DEFAULT)
    restock_quantity = models.PositiveIntegerField(default=RESTOCK_TARGET_DEFAULT)
    auto_restock_enabled = models.BooleanField(default=True)

    @property
    def in_stock(self):
        return self.stock > 0

    def needs_restock(self) -> bool:
        return self.auto_restock_enabled and self.stock < self.restock_threshold

    def restock_quantity_needed(self, current_stock: int | None = None) -> int:
        """Return how many items are needed to reach the configured target, taking
        into account the global MAX_STOCK. If current_stock is provided use it
        (sensor value) instead of the DB `stock` value.

        Returns 0 when no restock is needed (already at/above max/target).
        """
        target = min(self.restock_quantity, MAX_STOCK)
        current = self.stock if current_stock is None else int(current_stock)
        needed = max(0, target - current)
        return needed

    def save(self, *args, **kwargs):
        # Enforce MAX_STOCK when persisting stock values
        try:
            if self.stock is not None:
                self.stock = min(int(self.stock), MAX_STOCK)
        except Exception:
            pass
        try:
            if self.restock_quantity is not None:
                self.restock_quantity = min(int(self.restock_quantity), MAX_STOCK)
        except Exception:
            pass
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class ProductTemplate(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    shelf_location = models.CharField(max_length=100, blank=True, null=True)
    image = models.ImageField(upload_to="product_templates/", blank=True, null=True)

    def __str__(self):
        return self.name


class Order(models.Model):
    class StatusChoices(models.TextChoices):
        PENDING = "Pending"
        CONFIRMED = "Confirmed"
        CANCELLED = "Cancelled"

    order_id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=10, choices=StatusChoices.choices, default=StatusChoices.PENDING
    )

    products = models.ManyToManyField(
        Product, through="OrderItem", related_name="orders"
    )

    def __str__(self):
        return f"Order {self.order_id} by {self.user.username}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()

    @property
    def item_subtotal(self):
        return self.product.price * self.quantity

    def __str__(self):
        return (
            f"{self.quantity} x {self.product.name} in Order " f"{self.order.order_id}"
        )


class RestockItem(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING"
        IN_PROGRESS = "IN_PROGRESS"
        COMPLETED = "COMPLETED"
        FAILED = "FAILED"

    class ShelfState(models.TextChoices):
        EMPTY = "empty", "EMPTY"
        PARTIAL = "partial", "PARTIAL"
        UNKNOWN = "unknown", "UNKNOWN"

    class Priority(models.IntegerChoices):
        FULL_EMPTY = 0, "FULL_EMPTY"
        PARTIAL_EMPTY = 1, "PARTIAL_EMPTY"
        THRESHOLD = 2, "THRESHOLD"

    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    shelf_location = models.CharField(max_length=100)
    shelf_state = models.CharField(
        max_length=20,
        choices=ShelfState.choices,
        blank=True,
        null=True,
    )
    priority = models.IntegerField(
        choices=Priority.choices,
        default=Priority.THRESHOLD,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.product.name} ({self.status})"
