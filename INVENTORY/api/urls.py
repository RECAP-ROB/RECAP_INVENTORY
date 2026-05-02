from django.urls import path
from . import views
from rest_framework.routers import DefaultRouter

urlpatterns = [
    path("products/", views.ProductListCreateAPIView.as_view()),
    path("products/info/", views.ProductInfoAPIView.as_view()),
    path("products/<int:product_id>/", views.ProductDetailAPIView.as_view()),
    path("restock/queue/", views.RestockQueueAPIView.as_view()),
    path("tasks/<str:task_id>/status/", views.TaskStatusView.as_view()),
    path("restock/<int:pk>/update/", views.RestockUpdateAPIView.as_view()),
    path("user/me/", views.CurrentUserView.as_view()),
    path("dashboard/", views.DashboardView.as_view()),
    path("product-templates/", views.ProductTemplateListCreateAPIView.as_view()),
    path("product-templates/<int:pk>/", views.ProductTemplateDetailAPIView.as_view()),
]

router = DefaultRouter()
router.register("orders", views.OrderViewSet)
urlpatterns += router.urls
