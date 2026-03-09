import random
import time
import uuid as uuid_module

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import PeakResourceSchedule, SystemResource, Tenant, VMActionLog, VMMetricsSnapshot, VirtualMachine


class DockerServiceError(Exception):
    pass


class DockerService:
    """Mock Docker service that simulates VM operations without actually running containers."""
    
    def __init__(self):
        pass

    def create_and_start(self, vm: VirtualMachine):
        """Mock: Generate a fake container ID without actually running Docker."""
        # Generate a unique mock container ID
        vm.container_id = str(uuid_module.uuid4())[:12]

    def start(self, vm: VirtualMachine):
        """Mock: Simulate starting a container."""
        if not vm.container_id:
            raise DockerServiceError("VM has no container ID.")
        # No actual operation needed - just a mock

    def stop(self, vm: VirtualMachine):
        """Mock: Simulate stopping a container."""
        if not vm.container_id:
            raise DockerServiceError("VM has no container ID.")
        # No actual operation needed - just a mock

    def restart(self, vm: VirtualMachine):
        """Mock: Simulate restarting a container."""
        if not vm.container_id:
            raise DockerServiceError("VM has no container ID.")
        # No actual operation needed - just a mock

    def delete(self, vm: VirtualMachine):
        """Mock: Simulate deleting a container."""
        if not vm.container_id:
            raise DockerServiceError("VM has no container ID.")
        # No actual operation needed - just a mock

    def resize(self, vm: VirtualMachine, cpu_cores: int, ram_mb: int, disk_gb: int, network_mbps: int):
        """Mock: Simulate resizing container resources."""
        if not vm.container_id:
            raise DockerServiceError("VM has no container ID.")
        # No actual operation needed - just a mock

    def read_metrics(self, vm: VirtualMachine):
        """Mock: Return simulated metrics without reading from Docker."""
        if not vm.container_id:
            raise DockerServiceError("VM has no container ID.")
        
        # Return simulated metrics with realistic values
        return {
            "cpu_percent": round(random.uniform(10.0, 80.0), 1),
            "memory_mb": round(vm.ram_mb * random.uniform(0.2, 0.9), 1),
            "net_rx_mb": round(random.uniform(0.1, 50.0), 1),
            "net_tx_mb": round(random.uniform(0.1, 50.0), 1),
            "block_read_mb": round(random.uniform(0.0, 10.0), 1),
            "block_write_mb": round(random.uniform(0.0, 10.0), 1),
        }


def check_system_capacity(
    cpu_cores: int,
    ram_mb: int,
    disk_gb: int,
    network_mbps: int,
    exclude_vm_id=None,
):
    resource = SystemResource.get_default()
    queryset = VirtualMachine.objects.all()
    if exclude_vm_id:
        queryset = queryset.exclude(id=exclude_vm_id)

    used = queryset.aggregate(
        cpu=Sum("cpu_cores"),
        ram=Sum("ram_mb"),
        disk=Sum("disk_gb"),
    )

    used_cpu = used["cpu"] or 0
    used_ram = used["ram"] or 0
    used_disk = used["disk"] or 0

    if used_cpu + cpu_cores > resource.total_cpu_cores:
        raise ValidationError({"detail": "Not enough CPU resources"})
    if used_ram + ram_mb > resource.total_ram_mb:
        raise ValidationError({"detail": "Not enough RAM resources"})
    if used_disk + disk_gb > resource.total_disk_gb:
        raise ValidationError({"detail": "Not enough disk resources"})

    _ = network_mbps


def get_tenant_usage(tenant: Tenant, exclude_vm_id=None):
    queryset = tenant.vms.all()
    if exclude_vm_id:
        queryset = queryset.exclude(id=exclude_vm_id)
    used = queryset.aggregate(
        cpu=Sum("cpu_cores"),
        ram=Sum("ram_mb"),
        disk=Sum("disk_gb"),
        network=Sum("network_mbps"),
    )
    return {
        "cpu_cores": used["cpu"] or 0,
        "ram_mb": used["ram"] or 0,
        "disk_gb": used["disk"] or 0,
        "network_mbps": used["network"] or 0,
        "vm_count": queryset.count(),
    }


def validate_tenant_capacity(
    tenant: Tenant,
    cpu_cores: int,
    ram_mb: int,
    disk_gb: int,
    network_mbps: int,
    vm_count: int = 1,
    exclude_vm_id=None,
):
    used = get_tenant_usage(tenant, exclude_vm_id=exclude_vm_id)
    if used["cpu_cores"] + cpu_cores > tenant.cpu_cores_limit:
        raise ValidationError({"detail": "Tenant CPU limit exceeded"})
    if used["ram_mb"] + ram_mb > tenant.ram_mb_limit:
        raise ValidationError({"detail": "Tenant RAM limit exceeded"})
    if used["disk_gb"] + disk_gb > tenant.disk_gb_limit:
        raise ValidationError({"detail": "Tenant disk limit exceeded"})
    if used["network_mbps"] + network_mbps > tenant.network_mbps_limit:
        raise ValidationError({"detail": "Tenant network limit exceeded"})
    if used["vm_count"] + vm_count > tenant.max_vms:
        raise ValidationError({"detail": "Tenant VM count limit exceeded"})


def is_tenant_overcommitted(tenant: Tenant):
    used = get_tenant_usage(tenant)
    return (
        used["cpu_cores"] > tenant.cpu_cores_limit
        or used["ram_mb"] > tenant.ram_mb_limit
        or used["disk_gb"] > tenant.disk_gb_limit
        or used["network_mbps"] > tenant.network_mbps_limit
        or used["vm_count"] > tenant.max_vms
    )


def log_action(vm, actor, action: str, details=None):
    VMActionLog.objects.create(vm=vm, actor=actor, action=action, details=details or {})


def collect_vm_metrics(simulate: bool = False, only_running: bool = True, lightweight: bool = False) -> int:
    _ = simulate
    _ = lightweight

    vm_queryset = VirtualMachine.objects.select_related("tenant")
    if only_running:
        vm_queryset = vm_queryset.filter(status=VirtualMachine.Status.RUNNING)
    vms = list(vm_queryset)
    if not vms:
        return 0

    runtime = DockerService()
    snapshots = []
    for vm in vms:
        try:
            stats = runtime.read_metrics(vm)
        except DockerServiceError:
            continue

        snapshots.append(
            VMMetricsSnapshot(
                vm=vm,
                tenant=vm.tenant,
                source=VMMetricsSnapshot.Source.SIMULATED,
                cpu_percent=stats["cpu_percent"],
                memory_mb=stats["memory_mb"],
                net_rx_mb=stats["net_rx_mb"],
                net_tx_mb=stats["net_tx_mb"],
                block_read_mb=stats["block_read_mb"],
                block_write_mb=stats["block_write_mb"],
            )
        )

    if snapshots:
        VMMetricsSnapshot.objects.bulk_create(snapshots)
    return len(snapshots)


def collect_vm_metrics_loop(
    *,
    simulate: bool = False,
    interval_seconds: float = 5.0,
    iterations: int = 1,
    only_running: bool = True,
    lightweight: bool = False,
) -> int:
    iterations = max(iterations, 1)
    interval_seconds = max(interval_seconds, 0.1)

    total = 0
    for idx in range(iterations):
        total += collect_vm_metrics(simulate=simulate, only_running=only_running, lightweight=lightweight)
        if idx < iterations - 1:
            time.sleep(interval_seconds)
    return total


def _apply_peak_schedule(schedule: PeakResourceSchedule):
    if schedule.target_type == PeakResourceSchedule.TargetType.VM:
        vm = schedule.vm
        if vm is None:
            raise ValidationError("Target VM not found.")

        new_cpu = vm.cpu_cores + schedule.cpu_cores_delta
        new_ram = vm.ram_mb + schedule.ram_mb_delta
        new_disk = vm.disk_gb + schedule.disk_gb_delta
        new_network = vm.network_mbps + schedule.network_mbps_delta
        if min(new_cpu, new_ram, new_disk, new_network) < 1:
            raise ValidationError("VM resources cannot be reduced below 1.")

        validate_tenant_capacity(
            tenant=vm.tenant,
            cpu_cores=new_cpu,
            ram_mb=new_ram,
            disk_gb=new_disk,
            network_mbps=new_network,
            exclude_vm_id=vm.id,
        )
        check_system_capacity(
            cpu_cores=new_cpu,
            ram_mb=new_ram,
            disk_gb=new_disk,
            network_mbps=new_network,
            exclude_vm_id=vm.id,
        )

        runtime = DockerService()
        runtime.resize(vm, cpu_cores=new_cpu, ram_mb=new_ram, disk_gb=new_disk, network_mbps=new_network)

        vm.cpu_cores = new_cpu
        vm.ram_mb = new_ram
        vm.disk_gb = new_disk
        vm.network_mbps = new_network
        vm.save(update_fields=["cpu_cores", "ram_mb", "disk_gb", "network_mbps", "updated_at"])
        log_action(
            vm,
            schedule.created_by,
            "peak_schedule_applied",
            {
                "schedule_id": schedule.id,
                "cpu_cores_delta": schedule.cpu_cores_delta,
                "ram_mb_delta": schedule.ram_mb_delta,
                "disk_gb_delta": schedule.disk_gb_delta,
                "network_mbps_delta": schedule.network_mbps_delta,
            },
        )
        return

    if schedule.target_type == PeakResourceSchedule.TargetType.TENANT:
        tenant = schedule.tenant
        if tenant is None:
            raise ValidationError("Target tenant not found.")

        new_cpu_limit = tenant.cpu_cores_limit + schedule.cpu_cores_delta
        new_ram_limit = tenant.ram_mb_limit + schedule.ram_mb_delta
        new_disk_limit = tenant.disk_gb_limit + schedule.disk_gb_delta
        new_network_limit = tenant.network_mbps_limit + schedule.network_mbps_delta
        new_max_vms = tenant.max_vms + schedule.max_vms_delta
        if min(new_cpu_limit, new_ram_limit, new_disk_limit, new_network_limit, new_max_vms) < 1:
            raise ValidationError("Tenant limits cannot be reduced below 1.")

        tenant.cpu_cores_limit = new_cpu_limit
        tenant.ram_mb_limit = new_ram_limit
        tenant.disk_gb_limit = new_disk_limit
        tenant.network_mbps_limit = new_network_limit
        tenant.max_vms = new_max_vms
        tenant.save(
            update_fields=[
                "cpu_cores_limit",
                "ram_mb_limit",
                "disk_gb_limit",
                "network_mbps_limit",
                "max_vms",
                "updated_at",
            ]
        )
        return

    raise ValidationError("Unsupported target type.")


def apply_due_peak_schedules(batch_size: int = 50):
    now = timezone.now()
    applied_count = 0
    failed_count = 0

    due_ids = list(
        PeakResourceSchedule.objects.filter(
            status=PeakResourceSchedule.Status.PENDING,
            apply_at__lte=now,
        )
        .order_by("apply_at")
        .values_list("id", flat=True)[:batch_size]
    )

    for schedule_id in due_ids:
        with transaction.atomic():
            try:
                schedule = PeakResourceSchedule.objects.select_for_update().get(id=schedule_id)
            except PeakResourceSchedule.DoesNotExist:
                continue

            if schedule.status != PeakResourceSchedule.Status.PENDING:
                continue

            try:
                _apply_peak_schedule(schedule)
                schedule.status = PeakResourceSchedule.Status.APPLIED
                schedule.error_message = ""
                schedule.applied_at = timezone.now()
                applied_count += 1
            except Exception as exc:
                schedule.status = PeakResourceSchedule.Status.FAILED
                schedule.error_message = str(exc)[:255]
                schedule.applied_at = timezone.now()
                failed_count += 1

            schedule.save(update_fields=["status", "error_message", "applied_at"])

    return {"applied": applied_count, "failed": failed_count}
