from django.conf import settings
from django.db import models


class SystemResource(models.Model):
    name = models.CharField(max_length=64, unique=True, default="default")
    total_cpu_cores = models.PositiveIntegerField(default=16)
    total_ram_mb = models.PositiveIntegerField(default=32768)
    total_disk_gb = models.PositiveIntegerField(default=500)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "System resource"
        verbose_name_plural = "System resources"

    @classmethod
    def get_default(cls):
        resource, _ = cls.objects.get_or_create(name="default")
        return resource

    def __str__(self):
        return f"{self.name}: CPU={self.total_cpu_cores}, RAM={self.total_ram_mb}MB, Disk={self.total_disk_gb}GB"


class Tenant(models.Model):
    name = models.CharField(max_length=128, unique=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_tenants",
    )
    cpu_cores_limit = models.PositiveIntegerField()
    ram_mb_limit = models.PositiveIntegerField()
    disk_gb_limit = models.PositiveIntegerField()
    network_mbps_limit = models.PositiveIntegerField()
    max_vms = models.PositiveIntegerField()
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="TenantAccess",
        related_name="tenants",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.name


class TenantAccess(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="accesses")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tenant_accesses")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("tenant", "user")
        ordering = ["id"]

    def __str__(self):
        return f"{self.tenant_id}:{self.user_id}"


class VirtualMachine(models.Model):
    class Status(models.TextChoices):
        STARTING = "starting", "Запускается"
        RUNNING = "running", "Работает"
        STOPPING = "stopping", "Останавливается"
        STOPPED = "stopped", "Остановлен"
        RESTARTING = "restarting", "Перезагружается"
        FAILED = "failed", "Ошибка"
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="vms")
    name = models.CharField(max_length=100, unique=True)
    docker_image = models.CharField(max_length=255)
    container_id = models.CharField(max_length=128, blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.STARTING)

    cpu_cores = models.PositiveIntegerField()
    ram_mb = models.PositiveIntegerField()
    disk_gb = models.PositiveIntegerField()
    network_mbps = models.PositiveIntegerField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.status})"


class VMActionLog(models.Model):
    vm = models.ForeignKey(VirtualMachine, on_delete=models.SET_NULL, null=True, blank=True, related_name="logs")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=100)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} ({self.created_at})"


class VMMetricsSnapshot(models.Model):
    class Source(models.TextChoices):
        DOCKER = "docker", "Docker"
        SIMULATED = "simulated", "Simulated"

    vm = models.ForeignKey(
        VirtualMachine,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="metrics_snapshots",
    )
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="metrics_snapshots",
    )
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.DOCKER)
    cpu_percent = models.FloatField(default=0.0)
    memory_mb = models.FloatField(default=0.0)
    net_rx_mb = models.FloatField(default=0.0)
    net_tx_mb = models.FloatField(default=0.0)
    block_read_mb = models.FloatField(default=0.0)
    block_write_mb = models.FloatField(default=0.0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["vm", "created_at"]),
            models.Index(fields=["tenant", "created_at"]),
        ]

    def __str__(self):
        return f"{self.source} vm={self.vm_id} cpu={self.cpu_percent:.2f}% at {self.created_at}"


class PeakResourceSchedule(models.Model):
    class TargetType(models.TextChoices):
        VM = "vm", "Virtual machine"
        TENANT = "tenant", "Tenant"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPLIED = "applied", "Applied"
        FAILED = "failed", "Failed"
        CANCELED = "canceled", "Canceled"

    target_type = models.CharField(max_length=16, choices=TargetType.choices)
    vm = models.ForeignKey(
        VirtualMachine,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="peak_schedules",
    )
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="peak_schedules",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_peak_schedules",
    )

    cpu_cores_delta = models.IntegerField(default=0)
    ram_mb_delta = models.IntegerField(default=0)
    disk_gb_delta = models.IntegerField(default=0)
    network_mbps_delta = models.IntegerField(default=0)
    max_vms_delta = models.IntegerField(default=0)

    apply_at = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    error_message = models.CharField(max_length=255, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"PeakSchedule#{self.id} {self.target_type} status={self.status}"
