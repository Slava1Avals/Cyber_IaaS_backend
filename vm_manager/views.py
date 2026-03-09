import secrets
from datetime import timedelta

from django.db import transaction
from django.db import models
from django.db.models import Sum
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from users.models import User
from users.permissions import MustChangePasswordPermission

from .models import PeakResourceSchedule, SystemResource, Tenant, VMActionLog, VMMetricsSnapshot, VirtualMachine
from .notifications import notify_tenant_event, notify_vm_event
from .serializers import (
    PeakResourceScheduleCreateSerializer,
    PeakResourceScheduleSerializer,
    SystemResourceSerializer,
    TenantCreateSerializer,
    TenantMemberSerializer,
    TenantSerializer,
    TenantTransferOwnerSerializer,
    TenantUpdateSerializer,
    VMActionLogSerializer,
    VMCreateSerializer,
    VMMetricsSnapshotSerializer,
    VMResizeSerializer,
    VMSerializer,
)
from .services import (
    DockerService,
    DockerServiceError,
    check_system_capacity,
    collect_vm_metrics,
    collect_vm_metrics_loop,
    is_tenant_overcommitted,
    log_action,
    validate_tenant_capacity,
)


class TenantViewSet(viewsets.ModelViewSet):
    queryset = Tenant.objects.select_related("owner").prefetch_related("members")

    def get_permissions(self):
        return [permissions.IsAuthenticated(), MustChangePasswordPermission()]

    def get_serializer_class(self):
        if self.action == "create":
            return TenantCreateSerializer
        if self.action in {"update", "partial_update"}:
            return TenantUpdateSerializer
        if self.action == "transfer_owner":
            return TenantTransferOwnerSerializer
        if self.action == "add_member":
            return TenantMemberSerializer
        return TenantSerializer

    def get_queryset(self):
        queryset = Tenant.objects.select_related("owner").prefetch_related("members")
        if self.request.user.is_staff:
            return queryset
        return queryset.filter(
            models.Q(members=self.request.user) | models.Q(owner=self.request.user)
        ).distinct()

    def create(self, request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied("Only admin can create tenants")

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tenant = serializer.save()
        notify_tenant_event(
            tenant,
            action="created",
            actor=request.user,
            details={"owner_id": tenant.owner_id},
        )
        return Response(TenantSerializer(tenant).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied("Only admin can update tenants")
        response = super().update(request, *args, **kwargs)
        notify_tenant_event(self.get_object(), action="updated", actor=request.user, details=request.data)
        return response

    def partial_update(self, request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied("Only admin can update tenants")
        response = super().partial_update(request, *args, **kwargs)
        notify_tenant_event(self.get_object(), action="updated_partial", actor=request.user, details=request.data)
        return response

    def destroy(self, request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied("Only admin can delete tenants")
        tenant = self.get_object()
        notify_tenant_event(tenant, action="deleted", actor=request.user)
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="members")
    def add_member(self, request, pk=None):
        if not request.user.is_staff:
            raise PermissionDenied("Only admin can manage tenant access")

        tenant = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            user = User.objects.get(id=serializer.validated_data["user_id"])
        except User.DoesNotExist as exc:
            raise PermissionDenied("User not found") from exc

        tenant.members.add(user)
        notify_tenant_event(tenant, action="member_added", actor=request.user, details={"user_id": user.id})
        return Response({"detail": "Member added"})

    @action(detail=True, methods=["delete"], url_path=r"members/(?P<user_id>\d+)")
    def remove_member(self, request, pk=None, user_id=None):
        if not request.user.is_staff:
            raise PermissionDenied("Only admin can manage tenant access")

        tenant = self.get_object()
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist as exc:
            raise PermissionDenied("User not found") from exc

        if tenant.owner_id == user.id:
            if request.user.id == user.id:
                return Response(
                    {"detail": "Owner cannot remove own access"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            tenant.owner = request.user
            tenant.save(update_fields=["owner", "updated_at"])
            tenant.members.add(request.user)

        tenant.members.remove(user)
        notify_tenant_event(tenant, action="member_removed", actor=request.user, details={"user_id": user.id})
        return Response({"detail": "Member removed"})

    @action(detail=True, methods=["post"], url_path="transfer-owner")
    def transfer_owner(self, request, pk=None):
        if not request.user.is_staff:
            raise PermissionDenied("Only admin can transfer tenant owner")

        tenant = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_owner_id = serializer.validated_data["new_owner_id"]
        try:
            new_owner = User.objects.get(id=new_owner_id)
        except User.DoesNotExist as exc:
            raise PermissionDenied("User not found") from exc

        old_owner = tenant.owner
        tenant.owner = new_owner
        tenant.save(update_fields=["owner", "updated_at"])
        tenant.members.add(new_owner)
        tenant.members.remove(old_owner)
        notify_tenant_event(
            tenant,
            action="owner_transferred",
            actor=request.user,
            details={"old_owner_id": old_owner.id, "new_owner_id": new_owner.id},
        )
        return Response({"detail": "Tenant owner transferred"})

    @action(detail=True, methods=["get"], url_path="vms")
    def list_vms(self, request, pk=None):
        tenant = self.get_object()
        vms = tenant.vms.all().order_by("-created_at")
        return Response(VMSerializer(vms, many=True).data)


class VirtualMachineViewSet(viewsets.ModelViewSet):
    queryset = VirtualMachine.objects.select_related("tenant")
    serializer_class = VMSerializer

    def get_serializer_class(self):
        if self.action == "create":
            return VMCreateSerializer
        if self.action == "resize":
            return VMResizeSerializer
        return VMSerializer

    def get_permissions(self):
        return [permissions.IsAuthenticated(), MustChangePasswordPermission()]

    def _user_can_access_tenant(self, tenant_id):
        if self.request.user.is_staff:
            return True
        return Tenant.objects.filter(id=tenant_id, members=self.request.user).exists()

    def get_queryset(self):
        queryset = VirtualMachine.objects.select_related("tenant")
        tenant_id = self.request.query_params.get("tenant_id")

        if tenant_id:
            queryset = queryset.filter(tenant_id=tenant_id)

        if self.request.user.is_staff:
            return queryset

        return queryset.filter(tenant__members=self.request.user).distinct()

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        tenant_id = serializer.validated_data["tenant_id"]
        if not self._user_can_access_tenant(tenant_id):
            raise PermissionDenied("No access to tenant")

        try:
            tenant = Tenant.objects.get(id=tenant_id)
        except Tenant.DoesNotExist:
            return Response({"detail": "Tenant not found"}, status=status.HTTP_404_NOT_FOUND)

        docker_image = "ubuntu:22.04"
        cpu_cores = serializer.validated_data.get("cpu_cores", 1)
        ram_mb = serializer.validated_data.get("ram_mb", 512)
        disk_gb = serializer.validated_data.get("disk_gb", 4)
        network_mbps = serializer.validated_data.get("network_mbps", 100)

        validate_tenant_capacity(
            tenant=tenant,
            cpu_cores=cpu_cores,
            ram_mb=ram_mb,
            disk_gb=disk_gb,
            network_mbps=network_mbps,
        )
        check_system_capacity(
            cpu_cores=cpu_cores,
            ram_mb=ram_mb,
            disk_gb=disk_gb,
            network_mbps=network_mbps,
        )

        vm_name = f"vm-t{tenant.id}-{secrets.token_hex(3)}"
        vm_candidate = VirtualMachine(
            tenant=tenant,
            name=vm_name,
            docker_image=docker_image,
            status=VirtualMachine.Status.STARTING,
            cpu_cores=cpu_cores,
            ram_mb=ram_mb,
            disk_gb=disk_gb,
            network_mbps=network_mbps,
        )
        runtime = DockerService()
        try:
            # Important order: create/start runtime first, then persist in DB.
            runtime.create_and_start(vm_candidate)
        except DockerServiceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                vm = VirtualMachine.objects.create(
                    tenant=tenant,
                    name=vm_name,
                    docker_image=docker_image,
                    container_id=vm_candidate.container_id,
                    status=VirtualMachine.Status.RUNNING,
                    cpu_cores=cpu_cores,
                    ram_mb=ram_mb,
                    disk_gb=disk_gb,
                    network_mbps=network_mbps,
                )
                log_action(
                    vm,
                    request.user,
                    "created_started",
                    {
                        "docker_image": docker_image,
                        "cpu_cores": cpu_cores,
                        "ram_mb": ram_mb,
                        "disk_gb": disk_gb,
                        "network_mbps": network_mbps,
                    },
                )
                notify_vm_event(
                    vm,
                    action="created_started",
                    actor=request.user,
                    details={
                        "docker_image": docker_image,
                        "cpu_cores": cpu_cores,
                        "ram_mb": ram_mb,
                        "disk_gb": disk_gb,
                        "network_mbps": network_mbps,
                    },
                )
        except Exception:
            try:
                runtime.delete(vm_candidate)
            except DockerServiceError:
                pass
            raise

        return Response(VMSerializer(vm).data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        vm = self.get_object()
        runtime = DockerService()
        try:
            runtime.delete(vm)
        except DockerServiceError as exc:
            log_action(vm, request.user, "delete_failed", {"error": str(exc)})
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        log_action(vm, request.user, "deleted")
        notify_vm_event(vm, action="deleted", actor=request.user)
        vm.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="start")
    def start(self, request, pk=None):
        vm = self.get_object()
        if is_tenant_overcommitted(vm.tenant):
            return Response(
                {"detail": "Tenant is over limits. VM start is blocked."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        runtime = DockerService()
        try:
            vm.status = VirtualMachine.Status.STARTING
            vm.save(update_fields=["status", "updated_at"])
            runtime.start(vm)
            vm.status = VirtualMachine.Status.RUNNING
            vm.save(update_fields=["status", "updated_at"])
            log_action(vm, request.user, "started")
            notify_vm_event(vm, action="started", actor=request.user)
            return Response(VMSerializer(vm).data)
        except DockerServiceError as exc:
            vm.status = VirtualMachine.Status.FAILED
            vm.save(update_fields=["status", "updated_at"])
            log_action(vm, request.user, "start_failed", {"error": str(exc)})
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="stop")
    def stop(self, request, pk=None):
        vm = self.get_object()
        runtime = DockerService()

        try:
            vm.status = VirtualMachine.Status.STOPPING
            vm.save(update_fields=["status", "updated_at"])
            runtime.stop(vm)
            vm.status = VirtualMachine.Status.STOPPED
            vm.save(update_fields=["status", "updated_at"])
            log_action(vm, request.user, "stopped")
            notify_vm_event(vm, action="stopped", actor=request.user)
            return Response(VMSerializer(vm).data)
        except DockerServiceError as exc:
            vm.status = VirtualMachine.Status.FAILED
            vm.save(update_fields=["status", "updated_at"])
            log_action(vm, request.user, "stop_failed", {"error": str(exc)})
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="restart")
    def restart(self, request, pk=None):
        vm = self.get_object()
        if is_tenant_overcommitted(vm.tenant):
            return Response(
                {"detail": "Tenant is over limits. VM restart is blocked."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        runtime = DockerService()
        try:
            vm.status = VirtualMachine.Status.RESTARTING
            vm.save(update_fields=["status", "updated_at"])
            runtime.restart(vm)
            vm.status = VirtualMachine.Status.RUNNING
            vm.save(update_fields=["status", "updated_at"])
            log_action(vm, request.user, "restarted")
            notify_vm_event(vm, action="restarted", actor=request.user)
            return Response(VMSerializer(vm).data)
        except DockerServiceError as exc:
            vm.status = VirtualMachine.Status.FAILED
            vm.save(update_fields=["status", "updated_at"])
            log_action(vm, request.user, "restart_failed", {"error": str(exc)})
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="move-tenant")
    def move_tenant(self, request, pk=None):
        vm = self.get_object()
        if not request.user.is_staff:
            raise PermissionDenied("Only admin can move VM between tenants")

        tenant_id = request.data.get("tenant_id")
        if not tenant_id:
            return Response(
                {"tenant_id": ["This field is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            target_tenant = Tenant.objects.get(id=tenant_id)
        except Tenant.DoesNotExist:
            return Response({"detail": "Target tenant not found"}, status=status.HTTP_404_NOT_FOUND)

        source_tenant_id = vm.tenant_id
        vm.tenant = target_tenant
        vm.save(update_fields=["tenant", "updated_at"])
        log_action(
            vm,
            request.user,
            "moved_tenant",
            {"from_tenant_id": source_tenant_id, "to_tenant_id": target_tenant.id},
        )
        notify_vm_event(
            vm,
            action="moved_tenant",
            actor=request.user,
            details={"from_tenant_id": source_tenant_id, "to_tenant_id": target_tenant.id},
        )
        return Response(VMSerializer(vm).data)

    @action(detail=True, methods=["post"], url_path="resize")
    def resize(self, request, pk=None):
        vm = self.get_object()
        if not request.user.is_staff:
            raise PermissionDenied("Only admin can resize VM resources")

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        cpu_cores = serializer.validated_data["cpu_cores"]
        ram_mb = serializer.validated_data["ram_mb"]
        disk_gb = serializer.validated_data["disk_gb"]
        network_mbps = serializer.validated_data["network_mbps"]

        validate_tenant_capacity(
            tenant=vm.tenant,
            cpu_cores=cpu_cores,
            ram_mb=ram_mb,
            disk_gb=disk_gb,
            network_mbps=network_mbps,
            exclude_vm_id=vm.id,
        )
        check_system_capacity(
            cpu_cores=cpu_cores,
            ram_mb=ram_mb,
            disk_gb=disk_gb,
            network_mbps=network_mbps,
            exclude_vm_id=vm.id,
        )

        vm.cpu_cores = cpu_cores
        vm.ram_mb = ram_mb
        vm.disk_gb = disk_gb
        vm.network_mbps = network_mbps
        vm.save(update_fields=["cpu_cores", "ram_mb", "disk_gb", "network_mbps", "updated_at"])
        log_action(
            vm,
            request.user,
            "resized",
            {
                "cpu_cores": cpu_cores,
                "ram_mb": ram_mb,
                "disk_gb": disk_gb,
                "network_mbps": network_mbps,
            },
        )
        notify_vm_event(
            vm,
            action="resized",
            actor=request.user,
            details={
                "cpu_cores": cpu_cores,
                "ram_mb": ram_mb,
                "disk_gb": disk_gb,
                "network_mbps": network_mbps,
            },
        )
        return Response(VMSerializer(vm).data)


class SystemResourceViewSet(viewsets.ViewSet):
    permission_classes = [IsAdminUser, MustChangePasswordPermission]

    @staticmethod
    def _with_usage_payload(resource: SystemResource) -> dict:
        used = VirtualMachine.objects.aggregate(
            cpu=Sum("cpu_cores"),
            ram=Sum("ram_mb"),
            disk=Sum("disk_gb"),
        )
        used_cpu = used["cpu"] or 0
        used_ram = used["ram"] or 0
        used_disk = used["disk"] or 0
        payload = SystemResourceSerializer(resource).data
        payload["used_cpu_cores"] = used_cpu
        payload["used_ram_mb"] = used_ram
        payload["used_disk_gb"] = used_disk
        payload["available_cpu_cores"] = max(resource.total_cpu_cores - used_cpu, 0)
        payload["available_ram_mb"] = max(resource.total_ram_mb - used_ram, 0)
        payload["available_disk_gb"] = max(resource.total_disk_gb - used_disk, 0)
        return payload

    def list(self, request):
        resource = SystemResource.get_default()
        return Response(self._with_usage_payload(resource))

    def partial_update(self, request, pk=None):
        resource = SystemResource.get_default()
        serializer = SystemResourceSerializer(resource, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(self._with_usage_payload(resource))

    def update(self, request, pk=None):
        resource = SystemResource.get_default()
        serializer = SystemResourceSerializer(resource, data=request.data, partial=False)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(self._with_usage_payload(resource))

    @action(detail=False, methods=["post"], url_path="collect-metrics")
    def collect_metrics(self, request):
        simulate = str(request.data.get("simulate", "false")).lower() in {"1", "true", "yes"}
        lightweight = str(request.data.get("lightweight", "false")).lower() in {"1", "true", "yes"}
        lightweight = lightweight or simulate
        only_running = str(request.data.get("only_running", "true")).lower() in {"1", "true", "yes"}
        iterations_raw = request.data.get("iterations", 1)
        interval_raw = request.data.get("interval_seconds", 1.0)

        try:
            iterations = max(1, min(int(iterations_raw), 10000))
        except (TypeError, ValueError):
            return Response(
                {"iterations": ["Must be integer in range [1, 10000]."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            interval_seconds = max(0.1, min(float(interval_raw), 3600.0))
        except (TypeError, ValueError):
            return Response(
                {"interval_seconds": ["Must be number in range [0.1, 3600]."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            if iterations == 1:
                created = collect_vm_metrics(
                    simulate=simulate,
                    only_running=only_running,
                    lightweight=lightweight,
                )
            else:
                created = collect_vm_metrics_loop(
                    simulate=simulate,
                    interval_seconds=interval_seconds,
                    iterations=iterations,
                    only_running=only_running,
                    lightweight=lightweight,
                )
        except DockerServiceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "detail": "Metrics collected",
                "created": created,
                "simulate": simulate,
                "lightweight": lightweight,
                "only_running": only_running,
                "iterations": iterations,
                "interval_seconds": interval_seconds,
            }
        )

    @action(detail=False, methods=["get"], url_path="metrics")
    def metrics(self, request):
        minutes = request.query_params.get("minutes", "60")
        limit = request.query_params.get("limit", "720")
        vm_id = request.query_params.get("vm_id")
        tenant_id = request.query_params.get("tenant_id")

        try:
            minutes = max(1, min(int(minutes), 24 * 60))
        except (TypeError, ValueError):
            return Response({"minutes": ["Must be integer in range [1, 1440]."]}, status=status.HTTP_400_BAD_REQUEST)

        try:
            limit = max(1, min(int(limit), 5000))
        except (TypeError, ValueError):
            return Response({"limit": ["Must be integer in range [1, 5000]."]}, status=status.HTTP_400_BAD_REQUEST)

        since = timezone.now() - timedelta(minutes=minutes)
        queryset = VMMetricsSnapshot.objects.select_related("vm", "tenant").filter(created_at__gte=since)

        if vm_id:
            queryset = queryset.filter(vm_id=vm_id)
        if tenant_id:
            queryset = queryset.filter(tenant_id=tenant_id)

        points = list(queryset.order_by("-created_at")[:limit])
        points.reverse()

        serialized = VMMetricsSnapshotSerializer(points, many=True).data
        return Response(
            {
                "from": since,
                "to": timezone.now(),
                "points_count": len(serialized),
                "points": serialized,
            }
        )


class VMActionLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = VMActionLog.objects.select_related("vm", "actor")
    serializer_class = VMActionLogSerializer
    permission_classes = [IsAdminUser, MustChangePasswordPermission]

    def get_queryset(self):
        qs = VMActionLog.objects.select_related("vm", "actor")
        vm_id = self.request.query_params.get("vm_id")
        actor_id = self.request.query_params.get("actor_id")

        if vm_id:
            qs = qs.filter(vm_id=vm_id)
        if actor_id:
            qs = qs.filter(actor_id=actor_id)

        return qs


class PeakResourceScheduleViewSet(viewsets.ModelViewSet):
    queryset = PeakResourceSchedule.objects.select_related("created_by", "vm__tenant", "tenant")

    def get_permissions(self):
        return [permissions.IsAuthenticated(), MustChangePasswordPermission()]

    def get_serializer_class(self):
        if self.action == "create":
            return PeakResourceScheduleCreateSerializer
        return PeakResourceScheduleSerializer

    def get_queryset(self):
        qs = PeakResourceSchedule.objects.select_related("created_by", "vm__tenant", "tenant")
        if self.request.user.is_staff:
            return qs
        return qs.filter(created_by=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        target_type = serializer.validated_data["target_type"]
        vm = serializer.validated_data.get("vm")

        if not request.user.is_staff:
            if target_type != PeakResourceSchedule.TargetType.VM:
                raise PermissionDenied("Only admin can schedule tenant resource peaks.")
            if not Tenant.objects.filter(id=vm.tenant_id, members=request.user).exists():
                raise PermissionDenied("No access to target VM tenant.")

        schedule = serializer.save()
        return Response(PeakResourceScheduleSerializer(schedule).data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        schedule = self.get_object()

        if schedule.status != PeakResourceSchedule.Status.PENDING:
            return Response(
                {"detail": "Only pending schedules can be canceled."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not request.user.is_staff and schedule.created_by_id != request.user.id:
            raise PermissionDenied("You can cancel only your own schedules.")

        schedule.status = PeakResourceSchedule.Status.CANCELED
        schedule.save(update_fields=["status"])
        return Response(status=status.HTTP_204_NO_CONTENT)
