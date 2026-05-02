from django.db import transaction
from rest_framework import serializers
from .models import Product, Order, OrderItem, RestockItem, User, ProductTemplate


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "is_staff"]


class ProductSerializer(serializers.ModelSerializer):
    in_stock = serializers.ReadOnlyField()

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "description",
            "price",
            "stock",
            "in_stock",
            "shelf_location",
            "image",
        )

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Price must be greater than 0.")
        return value


class ProductTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductTemplate
        fields = (
            "id",
            "name",
            "description",
            "price",
            "shelf_location",
            "image",
        )


class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name")
    product_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, source="product.price"
    )

    class Meta:
        model = OrderItem
        fields = ("product_name", "product_price", "quantity", "item_subtotal")


class OrderCreateSerializer(serializers.ModelSerializer):
    class OrderItemCreateSerializer(serializers.ModelSerializer):
        class Meta:
            model = OrderItem
            fields = ("product", "quantity")

    order_id = serializers.UUIDField(read_only=True)
    items = OrderItemCreateSerializer(many=True, required=False)
    created_at = serializers.DateField(read_only=True, format="%Y-%m-%d")
    total_price = serializers.SerializerMethodField(method_name="total")

    def total(self, obj):
        order_items = obj.items.all()
        return sum(order_item.item_subtotal for order_item in order_items)

    def to_representation(self, instance):
        serializer = OrderSerializer(instance)
        return serializer.data

    def update(self, instance, validated_data):
        orderitem_data = validated_data.pop("items")

        with transaction.atomic():
            instance = super().update(instance, validated_data)

            if orderitem_data is not None:
                # Clear existing items (optional, depends on requirements)
                instance.items.all().delete()

                # Recreate items with the updated data
                for item in orderitem_data:
                    OrderItem.objects.create(order=instance, **item)
        return instance

    def create(self, validated_data):
        orderitem_data = validated_data.pop("items")

        with transaction.atomic():
            order = Order.objects.create(**validated_data)

            for item in orderitem_data:
                product = item["product"]
                quantity = item["quantity"]

                if product.stock < quantity:
                    raise serializers.ValidationError(
                        f"Insufficient stock for {product.name}. Available: {product.stock}"
                    )

                # Reducing stock
                product.stock -= quantity
                product.save()

                # Create order item
                OrderItem.objects.create(
                    order=order, product=product, quantity=quantity
                )

        return order

    class Meta:
        model = Order
        fields = (
            "order_id",
            "user",
            "created_at",
            "status",
            "items",
            "total_price",
        )
        extra_kwargs = {"user": {"read_only": True}}


class OrderSerializer(serializers.ModelSerializer):
    order_id = serializers.UUIDField(read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)
    total_price = serializers.SerializerMethodField(method_name="total")
    created_at = serializers.DateTimeField(format="%Y-%m-%d")

    def total(self, obj):
        order_items = obj.items.all()
        return sum(order_item.item_subtotal for order_item in order_items)

    class Meta:
        model = Order
        fields = (
            "order_id",
            "created_at",
            "user",
            "status",
            "items",
            "total_price",
        )


class ProductInfoSerializer(serializers.Serializer):
    products = ProductSerializer(many=True)
    count = serializers.IntegerField()
    max_price = serializers.FloatField()


class RestockItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name")

    class Meta:
        model = RestockItem
        fields = (
            "id",
            "product_name",
            "quantity",
            "shelf_location",
            "status",
            "priority",
        )
