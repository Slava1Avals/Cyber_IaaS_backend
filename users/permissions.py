from rest_framework import permissions


class MustChangePasswordPermission(permissions.BasePermission):
    """
    If user is marked with must_change_password, allow only the endpoint
    that changes the current user's password.
    """

    allowed_actions = {"change_my_password"}

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return True

        if not getattr(user, "must_change_password", False):
            return True

        return getattr(view, "action", None) in self.allowed_actions
