from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    PeakResourceScheduleViewSet,
    SystemResourceViewSet,
    TenantViewSet,
    VMActionLogViewSet,
    VirtualMachineViewSet,
)

router = DefaultRouter()
router.register(r"tenants", TenantViewSet, basename="tenants")
router.register(r"vms", VirtualMachineViewSet, basename="vms")
router.register(r"system-resources", SystemResourceViewSet, basename="system-resources")
router.register(r"vm-logs", VMActionLogViewSet, basename="vm-logs")
router.register(r"peak-schedules", PeakResourceScheduleViewSet, basename="peak-schedules")

urlpatterns = [
    path("", include(router.urls)),
]
