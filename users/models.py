from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    def create_user(self, user_name, email, password=None, **extra_fields):
        if not user_name:
            raise ValueError("Username required")

        if not email:
            raise ValueError("Email required")

        email = self.normalize_email(email)
        extra_fields.setdefault("two_factor_enabled", not extra_fields.get("is_superuser", False))

        user = self.model(
            user_name=user_name,
            email=email,
            **extra_fields
        )

        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, user_name, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        return self.create_user(user_name, email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    user_name = models.CharField(max_length=255, unique=True)
    email = models.EmailField(unique=True)

    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    must_change_password = models.BooleanField(default=False)

    two_factor_enabled = models.BooleanField(default=False)
    two_factor_email_code_hash = models.CharField(max_length=255, blank=True)
    two_factor_email_code_expires_at = models.DateTimeField(null=True, blank=True)
    two_factor_email_last_sent_at = models.DateTimeField(null=True, blank=True)
    two_factor_failed_attempts = models.PositiveSmallIntegerField(default=0)
    two_factor_locked_until = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "user_name"
    REQUIRED_FIELDS = ["email"]

    def __str__(self):
        return self.user_name

    def is_two_factor_locked(self):
        return bool(self.two_factor_locked_until and self.two_factor_locked_until > timezone.now())

    def requires_two_factor(self):
        return not self.is_superuser
