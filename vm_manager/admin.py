from django.contrib import admin

from .models import SystemResource, Tenant, TenantAccess, VMActionLog, VMMetricsSnapshot, VirtualMachine


@admin.register(SystemResource)
class SystemResourceAdmin(admin.ModelAdmin):
    list_display = ("name", "total_cpu_cores", "total_ram_mb", "total_disk_gb", "updated_at")


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "owner",
        "cpu_cores_limit",
        "ram_mb_limit",
        "disk_gb_limit",
        "network_mbps_limit",
        "max_vms",
        "updated_at",
    )
    search_fields = ("name", "owner__user_name")


@admin.register(TenantAccess)
class TenantAccessAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "user", "created_at")
    list_filter = ("tenant", "user")
    search_fields = ("tenant__name", "user__user_name")


@admin.register(VirtualMachine)
class VirtualMachineAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "tenant",
        "status",
        "docker_image",
        "cpu_cores",
        "ram_mb",
        "disk_gb",
        "network_mbps",
        "created_at",
    )
    list_filter = ("status", "tenant")
    search_fields = ("name", "tenant__name", "container_id")


@admin.register(VMActionLog)
class VMActionLogAdmin(admin.ModelAdmin):
    list_display = ("id", "vm", "actor", "action", "created_at")
    list_filter = ("action", "created_at")
    search_fields = ("action", "vm__name", "actor__user_name")


@admin.register(VMMetricsSnapshot)
class VMMetricsSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "created_at",
        "source",
        "vm",
        "tenant",
        "cpu_percent",
        "memory_mb",
        "net_rx_mb",
        "net_tx_mb",
    )
    list_filter = ("source", "tenant", "vm", "created_at")
    search_fields = ("vm__name", "tenant__name")
