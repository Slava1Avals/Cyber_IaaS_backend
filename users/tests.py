from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from .models import User


class UserPermissionsTests(APITestCase):
    def setUp(self):
        self.super_admin = User.objects.create_superuser(
            user_name="super_admin",
            email="super_admin@example.com",
            password="strong-password",
        )
        self.admin = User.objects.create_user(
            user_name="admin_user",
            email="admin@example.com",
            password="strong-password",
            is_staff=True,
        )
        self.regular_user = User.objects.create_user(
            user_name="regular_user",
            email="regular@example.com",
            password="strong-password",
        )

    def test_regular_user_cannot_access_users_list(self):
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.get("/api/users/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_access_users_list(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.get("/api/users/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_regular_user_can_access_own_profile_via_me(self):
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.get("/api/users/me/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.regular_user.id)

    def test_register_response_has_no_max_count_vm_field(self):
        url = "/api/register/"
        payload = {
            "user_name": "new_user",
            "email": "new_user@example.com",
            "password": "strong-password",
        }
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn("max_count_vm", response.data)

    def test_admin_can_generate_temporary_password_for_user(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(f"/api/users/{self.regular_user.id}/generate-temp-password/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("temporary_password", response.data)

        self.regular_user.refresh_from_db()
        self.assertTrue(self.regular_user.must_change_password)
        self.assertTrue(
            self.regular_user.check_password(response.data["temporary_password"])
        )

    def test_user_with_must_change_password_is_blocked_on_other_endpoints(self):
        self.regular_user.must_change_password = True
        self.regular_user.save(update_fields=["must_change_password"])
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.get("/api/vms/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_user_can_change_own_password_and_clear_flag(self):
        self.regular_user.must_change_password = True
        self.regular_user.save(update_fields=["must_change_password"])
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.post(
            "/api/users/change-my-password/",
            {
                "current_password": "strong-password",
                "new_password": "new-strong-password",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.regular_user.refresh_from_db()
        self.assertFalse(self.regular_user.must_change_password)
        self.assertTrue(self.regular_user.check_password("new-strong-password"))

    def test_non_super_admin_cannot_change_employee_status(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.patch(
            f"/api/users/{self.regular_user.id}/",
            {"is_staff": True},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.regular_user.refresh_from_db()
        self.assertFalse(self.regular_user.is_staff)

    def test_super_admin_can_change_employee_status(self):
        self.client.force_authenticate(user=self.super_admin)

        response = self.client.patch(
            f"/api/users/{self.regular_user.id}/",
            {"is_staff": True},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.regular_user.refresh_from_db()
        self.assertTrue(self.regular_user.is_staff)

    def test_me_contains_is_superuser_flag_for_frontend(self):
        self.client.force_authenticate(user=self.super_admin)

        response = self.client.get("/api/users/me/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("is_superuser", response.data)
        self.assertTrue(response.data["is_superuser"])


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class EmailTwoFactorAuthTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            user_name="mfa_user",
            email="mfa_user@example.com",
            password="strong-password",
        )
        self.super_admin = User.objects.create_superuser(
            user_name="super_admin_mfa",
            email="super_admin_mfa@example.com",
            password="strong-password",
        )

    def _extract_code_from_last_email(self):
        from django.core import mail

        self.assertGreater(len(mail.outbox), 0)
        body = mail.outbox[-1].body
        marker = "Your login verification code is: "
        start = body.index(marker) + len(marker)
        return body[start:start + 6]

    def test_regular_user_login_requires_email_code(self):
        response = self.client.post(
            "/api/login/",
            {"user_name": "mfa_user", "password": "strong-password"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["mfa_required"])
        self.assertIn("mfa_token", response.data)

    def test_super_admin_login_returns_jwt_without_2fa(self):
        response = self.client.post(
            "/api/login/",
            {"user_name": "super_admin_mfa", "password": "strong-password"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertNotIn("mfa_required", response.data)

    def test_login_with_email_code_completes_flow(self):

        first_step = self.client.post(
            "/api/login/",
            {"user_name": "mfa_user", "password": "strong-password"},
            format="json",
        )

        self.assertEqual(first_step.status_code, status.HTTP_200_OK)
        self.assertTrue(first_step.data["mfa_required"])
        self.assertIn("mfa_token", first_step.data)

        code = self._extract_code_from_last_email()
        second_step = self.client.post(
            "/api/login/2fa/",
            {"mfa_token": first_step.data["mfa_token"], "code": code},
            format="json",
        )

        self.assertEqual(second_step.status_code, status.HTTP_200_OK)
        self.assertIn("access", second_step.data)
        self.assertIn("refresh", second_step.data)

    def test_invalid_code_is_rejected(self):
        first_step = self.client.post(
            "/api/login/",
            {"user_name": "mfa_user", "password": "strong-password"},
            format="json",
        )
        response = self.client.post(
            "/api/login/2fa/",
            {"mfa_token": first_step.data["mfa_token"], "code": "000000"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_regular_user_cannot_disable_mandatory_2fa(self):
        self.client.force_authenticate(user=self.user)

        enable_response = self.client.post(
            "/api/users/2fa/enable/",
            {"current_password": "strong-password"},
            format="json",
        )
        self.assertEqual(enable_response.status_code, status.HTTP_200_OK)

        disable_response = self.client.post(
            "/api/users/2fa/disable/",
            {"current_password": "strong-password"},
            format="json",
        )
        self.assertEqual(disable_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_super_admin_can_call_disable_2fa(self):
        self.client.force_authenticate(user=self.super_admin)

        disable_response = self.client.post(
            "/api/users/2fa/disable/",
            {"current_password": "strong-password"},
            format="json",
        )
        self.assertEqual(disable_response.status_code, status.HTTP_200_OK)

        self.super_admin.refresh_from_db()
        self.assertFalse(self.super_admin.two_factor_enabled)
