import secrets

from django.contrib.auth import authenticate
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User
from .permissions import MustChangePasswordPermission
from .serializers import (
    ChangeMyPasswordSerializer,
    LoginSerializer,
    LoginTwoFactorResendSerializer,
    LoginTwoFactorSerializer,
    RegisterSerializer,
    SetPasswordSerializer,
    TwoFactorDisableSerializer,
    TwoFactorEnableSerializer,
    UserAdminSerializer,
    UserCreateSerializer,
    UserSerializer,
)
from .two_factor_email import (
    clear_email_2fa_code,
    ensure_can_send_new_code,
    get_user_from_mfa_token,
    issue_mfa_token,
    register_failed_2fa_attempt,
    reset_2fa_attempts,
    send_email_2fa_code,
    verify_email_code,
)


def _issue_jwt_pair(user):
    refresh = RefreshToken.for_user(user)
    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_name = serializer.validated_data["user_name"]
        password = serializer.validated_data["password"]
        user = authenticate(request=request, user_name=user_name, password=password)

        if not user or not user.is_active:
            raise AuthenticationFailed("Invalid credentials.")

        if not user.requires_two_factor():
            return Response(_issue_jwt_pair(user), status=status.HTTP_200_OK)

        ensure_can_send_new_code(user)
        send_email_2fa_code(user)

        return Response(
            {
                "mfa_required": True,
                "mfa_token": issue_mfa_token(user),
                "detail": "Verification code sent to your email.",
            },
            status=status.HTTP_200_OK,
        )


class LoginTwoFactorView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginTwoFactorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = get_user_from_mfa_token(serializer.validated_data["mfa_token"], User)
        if not user.requires_two_factor():
            raise AuthenticationFailed("2FA is not required for this user.")

        if user.is_two_factor_locked():
            raise PermissionDenied("2FA temporarily locked. Try again later.")

        if not verify_email_code(user, serializer.validated_data["code"]):
            register_failed_2fa_attempt(user)
            raise AuthenticationFailed("Invalid or expired code.")

        reset_2fa_attempts(user)
        clear_email_2fa_code(user)
        return Response(_issue_jwt_pair(user), status=status.HTTP_200_OK)


class LoginTwoFactorResendView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginTwoFactorResendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = get_user_from_mfa_token(serializer.validated_data["mfa_token"], User)
        if not user.requires_two_factor():
            raise AuthenticationFailed("2FA is not required for this user.")

        ensure_can_send_new_code(user)
        send_email_2fa_code(user)

        return Response({"detail": "Verification code resent to email."}, status=status.HTTP_200_OK)


class RegisterViewSet(viewsets.GenericViewSet):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.IsAdminUser, MustChangePasswordPermission]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by("id")
    permission_classes = [permissions.IsAdminUser, MustChangePasswordPermission]

    def _validate_staff_status_change_permission(self, request):
        if "is_staff" in request.data and not request.user.is_superuser:
            raise PermissionDenied("Only super admin can change employee status")

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        if self.action == "set_password":
            return SetPasswordSerializer
        return UserAdminSerializer

    @action(
        detail=False,
        methods=["get", "patch"],
        url_path="me",
        permission_classes=[permissions.IsAuthenticated, MustChangePasswordPermission],
    )
    def me(self, request):
        if request.method == "GET":
            return Response(UserSerializer(request.user).data)

        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        self._validate_staff_status_change_permission(request)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        self._validate_staff_status_change_permission(request)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._validate_staff_status_change_permission(request)
        return super().partial_update(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="activate")
    def activate(self, request, pk=None):
        user = self.get_object()
        user.is_active = True
        user.save(update_fields=["is_active"])
        return Response({"detail": "User activated"})

    @action(detail=True, methods=["post"], url_path="deactivate")
    def deactivate(self, request, pk=None):
        user = self.get_object()
        user.is_active = False
        user.save(update_fields=["is_active"])
        return Response({"detail": "User deactivated"})

    @action(detail=True, methods=["post"], url_path="set-password")
    def set_password(self, request, pk=None):
        user = self.get_object()

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user.set_password(serializer.validated_data["password"])
        user.save(update_fields=["password"])

        return Response({"detail": "Password updated"})

    @action(detail=True, methods=["post"], url_path="generate-temp-password")
    def generate_temp_password(self, request, pk=None):
        user = self.get_object()

        temporary_password = secrets.token_urlsafe(12)
        user.set_password(temporary_password)
        user.must_change_password = True
        user.save(update_fields=["password", "must_change_password"])

        return Response(
            {
                "detail": "Temporary password generated. User must change password after login.",
                "temporary_password": temporary_password,
            }
        )

    @action(
        detail=False,
        methods=["post"],
        url_path="change-my-password",
        permission_classes=[permissions.IsAuthenticated],
    )
    def change_my_password(self, request):
        serializer = ChangeMyPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        current_password = serializer.validated_data["current_password"]
        new_password = serializer.validated_data["new_password"]

        if not request.user.check_password(current_password):
            return Response(
                {"current_password": ["Current password is incorrect."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        request.user.set_password(new_password)
        request.user.must_change_password = False
        request.user.save(update_fields=["password", "must_change_password"])
        return Response({"detail": "Password changed"})

    @action(
        detail=False,
        methods=["post"],
        url_path="2fa/enable",
        permission_classes=[permissions.IsAuthenticated, MustChangePasswordPermission],
    )
    def two_factor_enable(self, request):
        serializer = TwoFactorEnableSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if not request.user.check_password(serializer.validated_data["current_password"]):
            return Response(
                {"current_password": ["Current password is incorrect."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if request.user.is_superuser:
            request.user.two_factor_enabled = False
            request.user.two_factor_failed_attempts = 0
            request.user.two_factor_locked_until = None
            request.user.save(
                update_fields=["two_factor_enabled", "two_factor_failed_attempts", "two_factor_locked_until"]
            )
            return Response({"detail": "2FA is disabled for super admin by policy."})

        request.user.two_factor_enabled = True
        request.user.two_factor_failed_attempts = 0
        request.user.two_factor_locked_until = None
        request.user.save(
            update_fields=["two_factor_enabled", "two_factor_failed_attempts", "two_factor_locked_until"]
        )

        return Response({"detail": "2FA is mandatory for this account and is enabled."})

    @action(
        detail=False,
        methods=["post"],
        url_path="2fa/disable",
        permission_classes=[permissions.IsAuthenticated, MustChangePasswordPermission],
    )
    def two_factor_disable(self, request):
        serializer = TwoFactorDisableSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if not request.user.is_superuser:
            raise PermissionDenied("2FA is mandatory for all users except super admin.")

        if not request.user.check_password(serializer.validated_data["current_password"]):
            return Response(
                {"current_password": ["Current password is incorrect."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        request.user.two_factor_enabled = False
        request.user.two_factor_email_code_hash = ""
        request.user.two_factor_email_code_expires_at = None
        request.user.two_factor_email_last_sent_at = None
        request.user.two_factor_failed_attempts = 0
        request.user.two_factor_locked_until = None
        request.user.save(
            update_fields=[
                "two_factor_enabled",
                "two_factor_email_code_hash",
                "two_factor_email_code_expires_at",
                "two_factor_email_last_sent_at",
                "two_factor_failed_attempts",
                "two_factor_locked_until",
            ]
        )

        return Response({"detail": "Email 2FA disabled."})
