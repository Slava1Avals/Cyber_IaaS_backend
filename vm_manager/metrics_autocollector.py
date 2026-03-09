import atexit
import fcntl
import logging
import threading
import time
from pathlib import Path

from django.conf import settings

from .services import DockerServiceError, apply_due_peak_schedules, collect_vm_metrics

logger = logging.getLogger(__name__)

_started = False
_lock_file = None


def _acquire_singleton_lock(lock_path: str) -> bool:
    global _lock_file

    path = Path(lock_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _lock_file = open(path, "w", encoding="utf-8")
    try:
        fcntl.flock(_lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_file.write(str(Path('/proc/self').resolve().name))
        _lock_file.flush()
        return True
    except OSError:
        _lock_file.close()
        _lock_file = None
        return False


def _release_lock():
    global _lock_file
    if _lock_file is not None:
        try:
            fcntl.flock(_lock_file.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            _lock_file.close()
        except OSError:
            pass
        _lock_file = None


def _collector_loop(interval_seconds: float, only_running: bool, lightweight: bool, metrics_enabled: bool, scheduler_enabled: bool):
    while True:
        if scheduler_enabled:
            try:
                apply_due_peak_schedules()
            except Exception:
                logger.exception("Unexpected peak scheduler error")

        if metrics_enabled:
            try:
                collect_vm_metrics(
                    simulate=False,
                    only_running=only_running,
                    lightweight=lightweight,
                )
            except DockerServiceError as exc:
                logger.warning("Metrics collector tick failed: %s", exc)
            except Exception:
                logger.exception("Unexpected metrics collector error")
        time.sleep(interval_seconds)


def start_metrics_autocollector():
    global _started

    if _started:
        return

    metrics_enabled = bool(getattr(settings, "VM_METRICS_AUTO_COLLECT_ENABLED", True))
    scheduler_enabled = bool(getattr(settings, "VM_PEAK_SCHEDULER_ENABLED", True))
    if not metrics_enabled and not scheduler_enabled:
        return

    lock_path = getattr(settings, "VM_METRICS_AUTO_COLLECT_LOCK_PATH", "/tmp/cyber_iaas_metrics_collector.lock")
    if not _acquire_singleton_lock(lock_path):
        logger.info("Metrics collector not started: lock is already held by another process")
        return

    interval_seconds = float(getattr(settings, "VM_METRICS_AUTO_COLLECT_INTERVAL_SECONDS", 2.0))
    interval_seconds = max(interval_seconds, 0.2)

    only_running = bool(getattr(settings, "VM_METRICS_AUTO_COLLECT_ONLY_RUNNING", True))
    lightweight = bool(getattr(settings, "VM_METRICS_AUTO_COLLECT_LIGHTWEIGHT", True))

    thread = threading.Thread(
        target=_collector_loop,
        args=(interval_seconds, only_running, lightweight, metrics_enabled, scheduler_enabled),
        daemon=True,
        name="vm-background-worker",
    )
    thread.start()
    _started = True
    atexit.register(_release_lock)

    logger.info(
        "VM background worker started (interval=%ss, metrics_enabled=%s, scheduler_enabled=%s, only_running=%s, lightweight=%s)",
        interval_seconds,
        metrics_enabled,
        scheduler_enabled,
        only_running,
        lightweight,
    )
