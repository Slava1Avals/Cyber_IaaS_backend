import json
import logging

from django.conf import settings
from django.core.mail import send_mass_mail

logger = logging.getLogger(__name__)


def _is_enabled() -> bool:
    return bool(getattr(settings, "VM_EMAIL_NOTIFICATIONS_ENABLED", True))


def _tenant_user_emails(tenant):
    return list(
        tenant.members.filter(is_active=True, is_staff=False)
        .exclude(email="")
        .values_list("email", flat=True)
        .distinct()
    )


def _send_to_recipients(subject: str, body: str, recipients: list[str]) -> None:
    if not recipients or not _is_enabled():
        return

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@cyber-iaas.local")
    payload = tuple((subject, body, from_email, [email]) for email in recipients)
    try:
        send_mass_mail(payload, fail_silently=True)
    except Exception:
        logger.exception("Failed to send VM/Tenant notification emails")


def notify_vm_event(vm, *, action: str, actor=None, details=None) -> None:
    recipients = _tenant_user_emails(vm.tenant)
    if not recipients:
        return

    actor_name = getattr(actor, "user_name", "system")
    details_json = json.dumps(details or {}, ensure_ascii=True, default=str)
    subject = f"[Cyber IaaS] VM event: {action}"
    body = (
        f"VM action: {action}\n"
        f"VM: {vm.name} (id={vm.id})\n"
        f"Tenant: {vm.tenant.name} (id={vm.tenant_id})\n"
        f"Actor: {actor_name}\n"
        f"Details: {details_json}\n"
    )
    _send_to_recipients(subject, body, recipients)


def notify_tenant_event(tenant, *, action: str, actor=None, details=None) -> None:
    recipients = _tenant_user_emails(tenant)
    if not recipients:
        return

    actor_name = getattr(actor, "user_name", "system")
    details_json = json.dumps(details or {}, ensure_ascii=True, default=str)
    subject = f"[Cyber IaaS] Tenant event: {action}"
    body = (
        f"Tenant action: {action}\n"
        f"Tenant: {tenant.name} (id={tenant.id})\n"
        f"Actor: {actor_name}\n"
        f"Details: {details_json}\n"
    )
    _send_to_recipients(subject, body, recipients)
