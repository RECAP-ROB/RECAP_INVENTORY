from django.db.models import Max
from django_filters.rest_framework import DjangoFilterBackend
from main.celery import app
from rest_framework.decorators import action
from rest_framework import filters, generics, viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from api.filters import InStockFilterBackend, OrderFilter, ProductFilter
from api.models import Order, Product, RestockItem, ProductTemplate
from api.serializers import (
    OrderSerializer,
    ProductInfoSerializer,
    ProductSerializer,
    OrderCreateSerializer,
    RestockItemSerializer,
    UserSerializer,
    ProductTemplateSerializer,
)


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)


class DashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Aggregate data for dashboard
        products = Product.objects.all()
        orders = Order.objects.all()
        restock_items = RestockItem.objects.all()

        data = {
            "products": ProductSerializer(
                products[:10], many=True
            ).data,  # Recent products
            "orders": OrderSerializer(orders[:10], many=True).data,  # Recent orders
            "restock_queue": RestockItemSerializer(restock_items, many=True).data,
            "stats": {
                "total_products": products.count(),
                "total_orders": orders.count(),
                "pending_orders": orders.filter(status="Pending").count(),
                "low_stock_products": products.filter(stock__lt=1).count(),
            },
        }
        return Response(data)


class ProductListCreateAPIView(generics.ListCreateAPIView):
    queryset = Product.objects.order_by("pk")
    serializer_class = ProductSerializer
    filterset_class = ProductFilter
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
        InStockFilterBackend,
    ]
    search_fields = ["name", "description"]
    ordering_fields = ["name", "price", "stock"]
    pagination_class = PageNumberPagination

    def get_permissions(self):
        self.permission_classes = [AllowAny]
        if self.request.method == "POST":
            self.permission_classes = [IsAdminUser]
        return super().get_permissions()

    def perform_create(self, serializer):
        product = serializer.save()
        if product.stock < 1:
            RestockItem.objects.create(
                product=product,
                quantity=2 - product.stock,  # Restock to reach 2
                shelf_location=product.shelf_location or "Unknown",
            )


class ProductDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    lookup_url_kwarg = "product_id"

    def get_permissions(self):
        self.permission_classes = [AllowAny]
        if self.request.method in ["PUT", "PATCH", "DELETE"]:
            self.permission_classes = [IsAdminUser]
        return super().get_permissions()


class ProductTemplateListCreateAPIView(generics.ListCreateAPIView):
    queryset = ProductTemplate.objects.order_by("pk")
    serializer_class = ProductTemplateSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "description"]
    ordering_fields = ["name", "price"]
    pagination_class = None

    def get_permissions(self):
        self.permission_classes = [AllowAny]
        if self.request.method == "POST":
            self.permission_classes = [IsAdminUser]
        return super().get_permissions()


class ProductTemplateDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = ProductTemplate.objects.all()
    serializer_class = ProductTemplateSerializer
    lookup_url_kwarg = "pk"

    def get_permissions(self):
        self.permission_classes = [AllowAny]
        if self.request.method in ["PUT", "PATCH", "DELETE"]:
            self.permission_classes = [IsAdminUser]
        return super().get_permissions()


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.prefetch_related("items__product")
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    filterset_class = OrderFilter
    filter_backends = [DjangoFilterBackend]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def get_serializer_class(self):
        # can also check if POST: if self.request.method == 'POST'
        if self.action == "create" or self.action == "update":
            return OrderCreateSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        qs = super().get_queryset()
        if not self.request.user.is_staff:
            qs = qs.filter(user=self.request.user)
        return qs


class RestockQueueAPIView(generics.ListAPIView):
    queryset = RestockItem.objects.all()
    serializer_class = RestockItemSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None


class RestockUpdateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        restock = RestockItem.objects.get(pk=pk)
        restock.status = request.data.get("status")
        restock.save()

        if restock.status == "COMPLETED":
            product = restock.product
            product.stock += restock.quantity
            product.save()

        return Response({"status": "updated"})

# class UserOrderListAPIView(generics.ListAPIView):
#     queryset = Order.objects.prefetch_related('items__product')
#     serializer_class = OrderSerializer
#     permission_classes = [IsAuthenticated]

#     def get_queryset(self):
#         qs = super().get_queryset()
#         return qs.filter(user=self.request.user)


class ProductInfoAPIView(APIView):
    def get(self, request):
        products = Product.objects.all()
        serializer = ProductInfoSerializer(
            {
                "products": products,
                "count": len(products),
                "max_price": products.aggregate(max_price=Max("price"))["max_price"],
            }
        )
        return Response(serializer.data)


class TaskStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, task_id):
        result = app.AsyncResult(task_id)

        data = {
            "task_id": task_id,
            "status": result.status,
            "result": result.result if result.successful() else None,
            "error": str(result.info) if result.failed() else None,
            "traceback": str(result.traceback) if result.failed() else None,
        }

        # Progress update
        if hasattr(result, "info") and isinstance(result.info, dict):
            data["progress"] = result.info.get("progress")
            data["current"] = result.info.get("current")
            data["total"] = result.info.get("total")

        return Response(data)
