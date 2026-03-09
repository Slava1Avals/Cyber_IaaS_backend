from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    model = User
    list_display = ("id", "user_name", "email", "is_active", "is_staff")
    list_filter = ("is_active", "is_staff", "is_superuser")
    ordering = ("id",)
    search_fields = ("user_name", "email")

    fieldsets = (
        (None, {"fields": ("user_name", "email", "password")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login",)}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("user_name", "email", "password1", "password2", "is_active", "is_staff"),
            },
        ),
    )
