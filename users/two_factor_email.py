import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core import mail, signing
from django.utils import timezone
from rest_framework import exceptions

MFA_TOKEN_SALT = "users.mfa.login"
MFA_TOKEN_MAX_AGE_SECONDS = 300
EMAIL_CODE_TTL_SECONDS = 300
EMAIL_CODE_RESEND_MIN_SECONDS = 30
MAX_2FA_ATTEMPTS = 5
LOCKOUT_MINUTES = 5


def generate_email_code():
    return f"{secrets.randbelow(1_000_000):06d}"


def issue_mfa_token(user):
    payload = {"uid": user.id, "pwd": user.password}
    return signing.dumps(payload, salt=MFA_TOKEN_SALT)


def get_user_from_mfa_token(token, user_model):
    try:
        payload = signing.loads(token, max_age=MFA_TOKEN_MAX_AGE_SECONDS, salt=MFA_TOKEN_SALT)
    except signing.BadSignature as exc:
        raise exceptions.AuthenticationFailed("Invalid or expired MFA token.") from exc

    try:
        user = user_model.objects.get(id=payload["uid"], is_active=True)
    except user_model.DoesNotExist as exc:
        raise exceptions.AuthenticationFailed("Invalid MFA token user.") from exc

    if payload.get("pwd") != user.password:
        raise exceptions.AuthenticationFailed("MFA token is no longer valid.")

    return user


def ensure_can_send_new_code(user):
    if user.is_two_factor_locked():
        raise exceptions.PermissionDenied("2FA temporarily locked. Try again later.")

    if user.two_factor_email_last_sent_at and (
        timezone.now() - user.two_factor_email_last_sent_at
    ).total_seconds() < EMAIL_CODE_RESEND_MIN_SECONDS:
        raise exceptions.Throttled(detail="Code was sent recently. Try again a bit later.")


def send_email_2fa_code(user):
    code = generate_email_code()
    now = timezone.now()

    user.two_factor_email_code_hash = make_password(code)
    user.two_factor_email_code_expires_at = now + timedelta(seconds=EMAIL_CODE_TTL_SECONDS)
    user.two_factor_email_last_sent_at = now
    user.save(
        update_fields=[
            "two_factor_email_code_hash",
            "two_factor_email_code_expires_at",
            "two_factor_email_last_sent_at",
        ]
    )

    subject = "Cyber IaaS: code for login"
    message = (
        f"Your login verification code is: {code}\n\n"
        f"This code will expire in {EMAIL_CODE_TTL_SECONDS // 60} minutes."
    )
    mail.send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False)


def clear_email_2fa_code(user):
    user.two_factor_email_code_hash = ""
    user.two_factor_email_code_expires_at = None
    user.save(update_fields=["two_factor_email_code_hash", "two_factor_email_code_expires_at"])


def verify_email_code(user, code):
    if not user.two_factor_email_code_hash or not user.two_factor_email_code_expires_at:
        return False

    if user.two_factor_email_code_expires_at <= timezone.now():
        return False

    return check_password(code, user.two_factor_email_code_hash)


def register_failed_2fa_attempt(user):
    user.two_factor_failed_attempts += 1
    if user.two_factor_failed_attempts >= MAX_2FA_ATTEMPTS:
        user.two_factor_locked_until = timezone.now() + timedelta(minutes=LOCKOUT_MINUTES)
        user.two_factor_failed_attempts = 0
    user.save(update_fields=["two_factor_failed_attempts", "two_factor_locked_until"])


def reset_2fa_attempts(user):
    user.two_factor_failed_attempts = 0
    user.two_factor_locked_until = None
    user.save(update_fields=["two_factor_failed_attempts", "two_factor_locked_until"])
