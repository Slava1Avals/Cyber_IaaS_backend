from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    LoginTwoFactorResendView,
    LoginTwoFactorView,
    LoginView,
    RegisterViewSet,
    UserViewSet,
)

router = DefaultRouter()
router.register(r"users", UserViewSet, basename="users")

urlpatterns = [
    path("register/", RegisterViewSet.as_view({"post": "create"})),
    path("", include(router.urls)),
    path("login/", LoginView.as_view()),
    path("login/2fa/", LoginTwoFactorView.as_view()),
    path("login/2fa/resend/", LoginTwoFactorResendView.as_view()),
    path("refresh/", TokenRefreshView.as_view()),
]
