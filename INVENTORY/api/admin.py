from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from api.models import Order, OrderItem, User, Product


class OrderItemInline(admin.TabularInline):
    model = OrderItem


class OrderAdmin(admin.ModelAdmin):
    inlines = [OrderItemInline]


class UserAdmin(BaseUserAdmin):
    pass


admin.site.register(Order, OrderAdmin)
admin.site.register(User, UserAdmin)
admin.site.register(Product)
