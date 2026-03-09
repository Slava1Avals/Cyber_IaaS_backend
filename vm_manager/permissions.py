from rest_framework import permissions


class IsAdminOrTenantMember(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.user and request.user.is_authenticated and (
            request.user.is_staff or obj.tenant.members.filter(id=request.user.id).exists()
        )
