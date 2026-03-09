from django.utils import timezone
from rest_framework import serializers

from .models import (
    PeakResourceSchedule,
    SystemResource,
    Tenant,
    VMActionLog,
    VMMetricsSnapshot,
    VirtualMachine,
)


class VMCreateSerializer(serializers.Serializer):
    tenant_id = serializers.IntegerField(min_value=1)
    cpu_cores = serializers.IntegerField(min_value=1, required=False)
    ram_mb = serializers.IntegerField(min_value=1, required=False)
    disk_gb = serializers.IntegerField(min_value=1, required=False)
    network_mbps = serializers.IntegerField(min_value=1, required=False)


class VMResizeSerializer(serializers.Serializer):
    cpu_cores = serializers.IntegerField(min_value=1)
    ram_mb = serializers.IntegerField(min_value=1)
    disk_gb = serializers.IntegerField(min_value=1)
    network_mbps = serializers.IntegerField(min_value=1)


class VMSerializer(serializers.ModelSerializer):
    tenant_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = VirtualMachine
        fields = [
            "id",
            "tenant_id",
            "name",
            "docker_image",
            "container_id",
            "status",
            "cpu_cores",
            "ram_mb",
            "disk_gb",
            "network_mbps",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class TenantSerializer(serializers.ModelSerializer):
    owner_id = serializers.IntegerField(source="owner.id", read_only=True)
    members = serializers.SerializerMethodField(read_only=True)
    used_cpu_cores = serializers.SerializerMethodField(read_only=True)
    used_ram_mb = serializers.SerializerMethodField(read_only=True)
    used_disk_gb = serializers.SerializerMethodField(read_only=True)
    used_network_mbps = serializers.SerializerMethodField(read_only=True)
    used_vm_count = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Tenant
        fields = [
            "id",
            "name",
            "owner_id",
            "cpu_cores_limit",
            "ram_mb_limit",
            "disk_gb_limit",
            "network_mbps_limit",
            "max_vms",
            "members",
            "used_cpu_cores",
            "used_ram_mb",
            "used_disk_gb",
            "used_network_mbps",
            "used_vm_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "owner_id",
            "members",
            "used_cpu_cores",
            "used_ram_mb",
            "used_disk_gb",
            "used_network_mbps",
            "used_vm_count",
            "created_at",
            "updated_at",
        ]

    def get_members(self, obj: Tenant):
        return list(obj.members.order_by("id").values_list("id", flat=True))

    def get_used_cpu_cores(self, obj: Tenant):
        return sum(vm.cpu_cores for vm in obj.vms.all())

    def get_used_ram_mb(self, obj: Tenant):
        return sum(vm.ram_mb for vm in obj.vms.all())

    def get_used_disk_gb(self, obj: Tenant):
        return sum(vm.disk_gb for vm in obj.vms.all())

    def get_used_network_mbps(self, obj: Tenant):
        return sum(vm.network_mbps for vm in obj.vms.all())

    def get_used_vm_count(self, obj: Tenant):
        return obj.vms.count()


class TenantCreateSerializer(serializers.ModelSerializer):
    owner_id = serializers.IntegerField(write_only=True, min_value=1)

    class Meta:
        model = Tenant
        fields = [
            "id",
            "name",
            "owner_id",
            "cpu_cores_limit",
            "ram_mb_limit",
            "disk_gb_limit",
            "network_mbps_limit",
            "max_vms",
        ]
        read_only_fields = ["id"]

    def validate_owner_id(self, value):
        from users.models import User

        if not User.objects.filter(id=value).exists():
            raise serializers.ValidationError("User not found")
        return value

    def create(self, validated_data):
        from users.models import User

        owner = User.objects.get(id=validated_data.pop("owner_id"))
        tenant = Tenant.objects.create(owner=owner, **validated_data)
        tenant.members.add(owner)
        return tenant


class TenantUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = [
            "name",
            "cpu_cores_limit",
            "ram_mb_limit",
            "disk_gb_limit",
            "network_mbps_limit",
            "max_vms",
        ]


class TenantTransferOwnerSerializer(serializers.Serializer):
    new_owner_id = serializers.IntegerField(min_value=1)


class TenantMemberSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(min_value=1)


class SystemResourceSerializer(serializers.ModelSerializer):
    used_cpu_cores = serializers.IntegerField(read_only=True)
    used_ram_mb = serializers.IntegerField(read_only=True)
    used_disk_gb = serializers.IntegerField(read_only=True)
    available_cpu_cores = serializers.IntegerField(read_only=True)
    available_ram_mb = serializers.IntegerField(read_only=True)
    available_disk_gb = serializers.IntegerField(read_only=True)

    class Meta:
        model = SystemResource
        fields = [
            "id",
            "name",
            "total_cpu_cores",
            "total_ram_mb",
            "total_disk_gb",
            "used_cpu_cores",
            "used_ram_mb",
            "used_disk_gb",
            "available_cpu_cores",
            "available_ram_mb",
            "available_disk_gb",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "name",
            "used_cpu_cores",
            "used_ram_mb",
            "used_disk_gb",
            "available_cpu_cores",
            "available_ram_mb",
            "available_disk_gb",
            "updated_at",
        ]


class VMActionLogSerializer(serializers.ModelSerializer):
    vm_name = serializers.CharField(source="vm.name", read_only=True)
    actor_user_name = serializers.CharField(source="actor.user_name", read_only=True)

    class Meta:
        model = VMActionLog
        fields = [
            "id",
            "vm",
            "vm_name",
            "actor",
            "actor_user_name",
            "action",
            "details",
            "created_at",
        ]
        read_only_fields = fields


class VMMetricsSnapshotSerializer(serializers.ModelSerializer):
    vm_name = serializers.CharField(source="vm.name", read_only=True)

    class Meta:
        model = VMMetricsSnapshot
        fields = [
            "id",
            "vm",
            "vm_name",
            "tenant",
            "source",
            "cpu_percent",
            "memory_mb",
            "net_rx_mb",
            "net_tx_mb",
            "block_read_mb",
            "block_write_mb",
            "created_at",
        ]
        read_only_fields = fields


class PeakResourceScheduleCreateSerializer(serializers.ModelSerializer):
    vm_id = serializers.IntegerField(required=False, min_value=1)
    tenant_id = serializers.IntegerField(required=False, min_value=1)

    class Meta:
        model = PeakResourceSchedule
        fields = [
            "id",
            "target_type",
            "vm_id",
            "tenant_id",
            "cpu_cores_delta",
            "ram_mb_delta",
            "disk_gb_delta",
            "network_mbps_delta",
            "max_vms_delta",
            "apply_at",
            "status",
            "error_message",
            "applied_at",
            "created_at",
        ]
        read_only_fields = ["id", "status", "error_message", "applied_at", "created_at"]

    def validate_apply_at(self, value):
        if value <= timezone.now():
            raise serializers.ValidationError("apply_at must be in the future.")
        return value

    def validate(self, attrs):
        target_type = attrs.get("target_type")
        vm_id = attrs.pop("vm_id", None)
        tenant_id = attrs.pop("tenant_id", None)

        if target_type == PeakResourceSchedule.TargetType.VM:
            if not vm_id:
                raise serializers.ValidationError({"vm_id": "This field is required for target_type=vm."})
            if tenant_id:
                raise serializers.ValidationError({"tenant_id": "Do not pass tenant_id for target_type=vm."})
            if attrs.get("max_vms_delta", 0) != 0:
                raise serializers.ValidationError({"max_vms_delta": "Only allowed for target_type=tenant."})
            try:
                attrs["vm"] = VirtualMachine.objects.select_related("tenant").get(id=vm_id)
            except VirtualMachine.DoesNotExist as exc:
                raise serializers.ValidationError({"vm_id": "VM not found."}) from exc

        elif target_type == PeakResourceSchedule.TargetType.TENANT:
            if not tenant_id:
                raise serializers.ValidationError({"tenant_id": "This field is required for target_type=tenant."})
            if vm_id:
                raise serializers.ValidationError({"vm_id": "Do not pass vm_id for target_type=tenant."})
            try:
                attrs["tenant"] = Tenant.objects.get(id=tenant_id)
            except Tenant.DoesNotExist as exc:
                raise serializers.ValidationError({"tenant_id": "Tenant not found."}) from exc
        else:
            raise serializers.ValidationError({"target_type": "Unsupported target_type."})

        if (
            attrs.get("cpu_cores_delta", 0) == 0
            and attrs.get("ram_mb_delta", 0) == 0
            and attrs.get("disk_gb_delta", 0) == 0
            and attrs.get("network_mbps_delta", 0) == 0
            and attrs.get("max_vms_delta", 0) == 0
        ):
            raise serializers.ValidationError("At least one *_delta field must be non-zero.")

        return attrs

    def create(self, validated_data):
        validated_data["created_by"] = self.context["request"].user
        return PeakResourceSchedule.objects.create(**validated_data)


class PeakResourceScheduleSerializer(serializers.ModelSerializer):
    vm_id = serializers.IntegerField(source="vm.id", read_only=True)
    tenant_id = serializers.IntegerField(source="tenant.id", read_only=True)
    created_by_id = serializers.IntegerField(source="created_by.id", read_only=True)

    class Meta:
        model = PeakResourceSchedule
        fields = [
            "id",
            "target_type",
            "vm_id",
            "tenant_id",
            "created_by_id",
            "cpu_cores_delta",
            "ram_mb_delta",
            "disk_gb_delta",
            "network_mbps_delta",
            "max_vms_delta",
            "apply_at",
            "status",
            "error_message",
            "applied_at",
            "created_at",
        ]
        read_only_fields = fields
