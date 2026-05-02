import random
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import lorem_ipsum
from api.models import (
    User,
    Product,
    Order,
    OrderItem,
    RestockItem,
    RESTOCK_TARGET_DEFAULT,
)


class Command(BaseCommand):
    help = "Creates application data"

    def handle(self, *args, **kwargs):
        # get or create superuser
        user = User.objects.filter(username="RECAP").first()
        if not user:
            user = User.objects.create_superuser(
                username="RECAP", password="supermarket"
            )

        # create products - name, desc, price, stock, image
        products = [
            Product(
                name="Sugar",
                description=lorem_ipsum.paragraph(),
                price=Decimal("79.99"),
                stock=4,
            ),
            Product(
                name="Coffee Machine",
                description=lorem_ipsum.paragraph(),
                price=Decimal("70.99"),
                stock=6,
            ),
            Product(
                name="Vegetable Oil",
                description=lorem_ipsum.paragraph(),
                price=Decimal("15.99"),
                stock=1,
            ),
            Product(
                name="Soap",
                description=lorem_ipsum.paragraph(),
                price=Decimal("17.99"),
                stock=2,
            ),
            Product(
                name="Camera",
                description=lorem_ipsum.paragraph(),
                price=Decimal("350.99"),
                stock=4,
            ),
            Product(
                name="Watch",
                description=lorem_ipsum.paragraph(),
                price=Decimal("500.05"),
                stock=0,
            ),
        ]

        # create products & re-fetch from DB
        Product.objects.bulk_create(products)
        products = Product.objects.all()

        # create restock items
        restock_items = []
        for product in products:
            # Restock if stock is low
            if product.stock < RESTOCK_TARGET_DEFAULT:
                restock_items.append(
                    RestockItem(
                        product=product,
                        # configurable quantity
                        quantity=max(1, RESTOCK_TARGET_DEFAULT - product.stock),
                        shelf_location=(
                            f"{random.choice(['A', 'B', 'C', 'D'])}"
                            f"{random.randint(1, 3)}"
                        ),
                        status=random.choice(
                            ["PENDING", "IN_PROGRESS", "COMPLETED", "FAILED"]
                        ),
                    )
                )
        RestockItem.objects.bulk_create(restock_items)

        self.stdout.write(self.style.SUCCESS("Successfully populated the database"))
