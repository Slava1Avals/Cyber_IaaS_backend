from django.core import mail
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from users.models import User

from .models import Tenant, VMMetricsSnapshot, VirtualMachine


class TenantVmApiTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            user_name="admin",
            email="admin@example.com",
            password="strong-password",
            is_staff=True,
        )
        self.user1 = User.objects.create_user(
            user_name="user1",
            email="user1@example.com",
            password="strong-password",
        )
        self.user2 = User.objects.create_user(
            user_name="user2",
            email="user2@example.com",
            password="strong-password",
        )

        self.tenant1 = Tenant.objects.create(
            name="tenant-1",
            owner=self.user1,
            cpu_cores_limit=10,
            ram_mb_limit=8192,
            disk_gb_limit=200,
            network_mbps_limit=1000,
            max_vms=10,
        )
        self.tenant1.members.add(self.user1)

        self.tenant2 = Tenant.objects.create(
            name="tenant-2",
            owner=self.user2,
            cpu_cores_limit=1,
            ram_mb_limit=512,
            disk_gb_limit=4,
            network_mbps_limit=100,
            max_vms=1,
        )
        self.tenant2.members.add(self.user2)

        self.vm = VirtualMachine.objects.create(
            tenant=self.tenant1,
            name="vm-1",
            docker_image="ubuntu:22.04",
            status=VirtualMachine.Status.STOPPED,
            cpu_cores=1,
            ram_mb=512,
            disk_gb=4,
            network_mbps=100,
        )

    def test_tenant_member_sees_own_vm(self):
        self.client.force_authenticate(user=self.user1)

        response = self.client.get("/api/vms/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], self.vm.id)

    def test_non_member_cannot_access_vm(self):
        self.client.force_authenticate(user=self.user2)

        response = self.client.get(f"/api/vms/{self.vm.id}/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_can_move_vm_to_another_tenant(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            f"/api/vms/{self.vm.id}/move-tenant/",
            {"tenant_id": self.tenant2.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.vm.refresh_from_db()
        self.assertEqual(self.vm.tenant_id, self.tenant2.id)

    def test_start_is_blocked_when_tenant_is_over_limits(self):
        self.vm.tenant = self.tenant2
        self.vm.save(update_fields=["tenant"])

        self.client.force_authenticate(user=self.user2)
        response = self.client.post(f"/api/vms/{self.vm.id}/start/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "Tenant is over limits. VM start is blocked.")

    def test_transfer_owner_removes_previous_owner_access(self):
        self.tenant1.members.add(self.user2)
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            f"/api/tenants/{self.tenant1.id}/transfer-owner/",
            {"new_owner_id": self.user2.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.tenant1.refresh_from_db()
        self.assertEqual(self.tenant1.owner_id, self.user2.id)
        self.assertFalse(self.tenant1.members.filter(id=self.user1.id).exists())
        self.assertTrue(self.tenant1.members.filter(id=self.user2.id).exists())

    def test_admin_can_resize_vm(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            f"/api/vms/{self.vm.id}/resize/",
            {
                "cpu_cores": 2,
                "ram_mb": 1024,
                "disk_gb": 10,
                "network_mbps": 200,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.vm.refresh_from_db()
        self.assertEqual(self.vm.cpu_cores, 2)
        self.assertEqual(self.vm.ram_mb, 1024)
        self.assertEqual(self.vm.disk_gb, 10)
        self.assertEqual(self.vm.network_mbps, 200)

    def test_non_admin_cannot_resize_vm(self):
        self.client.force_authenticate(user=self.user1)

        response = self.client.post(
            f"/api/vms/{self.vm.id}/resize/",
            {
                "cpu_cores": 2,
                "ram_mb": 1024,
                "disk_gb": 10,
                "network_mbps": 200,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_resize_is_blocked_when_tenant_limit_exceeded(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            f"/api/vms/{self.vm.id}/resize/",
            {
                "cpu_cores": 100,
                "ram_mb": 1024,
                "disk_gb": 10,
                "network_mbps": 200,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "Tenant CPU limit exceeded")

    def test_admin_can_read_metrics_series(self):
        VMMetricsSnapshot.objects.create(
            vm=self.vm,
            tenant=self.tenant1,
            source=VMMetricsSnapshot.Source.SIMULATED,
            cpu_percent=42.5,
            memory_mb=256,
            net_rx_mb=12.2,
            net_tx_mb=8.1,
            block_read_mb=2.0,
            block_write_mb=1.0,
        )
        self.client.force_authenticate(user=self.admin)

        response = self.client.get("/api/system-resources/metrics/?minutes=60&limit=100")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("points", response.data)
        self.assertGreaterEqual(response.data["points_count"], 1)

    def test_admin_can_collect_simulated_metrics(self):
        self.vm.status = VirtualMachine.Status.RUNNING
        self.vm.save(update_fields=["status"])
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            "/api/system-resources/collect-metrics/",
            {"simulate": True, "only_running": True},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(response.data["created"], 1)

    def test_admin_can_collect_multiple_points_in_single_request(self):
        self.vm.status = VirtualMachine.Status.RUNNING
        self.vm.save(update_fields=["status"])
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            "/api/system-resources/collect-metrics/",
            {
                "simulate": True,
                "only_running": True,
                "iterations": 3,
                "interval_seconds": 0.1,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["iterations"], 3)
        self.assertGreaterEqual(response.data["created"], 3)

    def test_vm_delete_removes_metrics_points(self):
        VMMetricsSnapshot.objects.create(
            vm=self.vm,
            tenant=self.tenant1,
            source=VMMetricsSnapshot.Source.SIMULATED,
            cpu_percent=15.0,
            memory_mb=128,
            net_rx_mb=1.0,
            net_tx_mb=1.0,
            block_read_mb=0.1,
            block_write_mb=0.1,
        )
        self.assertEqual(VMMetricsSnapshot.objects.filter(vm=self.vm).count(), 1)

        self.vm.delete()

        self.assertEqual(VMMetricsSnapshot.objects.filter(vm_id=self.vm.id).count(), 0)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        VM_EMAIL_NOTIFICATIONS_ENABLED=True,
    )
    def test_vm_action_email_sent_only_to_non_admin_users(self):
        self.tenant1.members.add(self.admin)
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            f"/api/vms/{self.vm.id}/resize/",
            {
                "cpu_cores": 2,
                "ram_mb": 1024,
                "disk_gb": 10,
                "network_mbps": 200,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user1.email])
