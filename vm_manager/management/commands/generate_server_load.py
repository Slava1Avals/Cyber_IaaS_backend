import multiprocessing as mp
import time

from django.core.management.base import BaseCommand, CommandError


def _cpu_worker(stop_event, busy_seconds: float, period_seconds: float):
    while not stop_event.is_set():
        cycle_start = time.perf_counter()
        # Busy phase
        while (time.perf_counter() - cycle_start) < busy_seconds and not stop_event.is_set():
            pass
        # Sleep phase
        sleep_time = period_seconds - busy_seconds
        if sleep_time > 0:
            time.sleep(sleep_time)


class Command(BaseCommand):
    help = "Generate controlled CPU load for monitoring tests"

    def add_arguments(self, parser):
        parser.add_argument(
            "--target-percent",
            type=float,
            required=True,
            help="Target total CPU load percent across host (1..95), e.g. 30",
        )
        parser.add_argument(
            "--duration",
            type=int,
            default=120,
            help="Duration in seconds (default: 120)",
        )
        parser.add_argument(
            "--period",
            type=float,
            default=0.2,
            help="Control period in seconds (default: 0.2)",
        )

    def handle(self, *args, **options):
        target_percent = options["target_percent"]
        duration = options["duration"]
        period = options["period"]

        if target_percent <= 0 or target_percent > 95:
            raise CommandError("--target-percent must be in range (0, 95]")
        if duration <= 0:
            raise CommandError("--duration must be > 0")
        if period <= 0.02:
            raise CommandError("--period must be > 0.02")

        cpu_count = max(mp.cpu_count(), 1)
        target_cores = cpu_count * (target_percent / 100.0)

        full_workers = int(target_cores)
        fractional = target_cores - full_workers

        workers = []
        stop_event = mp.Event()

        # Fully busy workers
        for _ in range(full_workers):
            p = mp.Process(target=_cpu_worker, args=(stop_event, period, period), daemon=True)
            p.start()
            workers.append(p)

        # One partial worker for fractional core share
        if fractional > 0:
            busy_seconds = period * fractional
            p = mp.Process(target=_cpu_worker, args=(stop_event, busy_seconds, period), daemon=True)
            p.start()
            workers.append(p)

        self.stdout.write(
            self.style.WARNING(
                f"Generating CPU load: target={target_percent:.1f}% for {duration}s, cpu_count={cpu_count}, workers={len(workers)}"
            )
        )

        started_at = time.time()
        try:
            while True:
                elapsed = int(time.time() - started_at)
                if elapsed >= duration:
                    break
                if elapsed % 10 == 0:
                    self.stdout.write(f"... running {elapsed}/{duration}s")
                time.sleep(1)
        finally:
            stop_event.set()
            for p in workers:
                p.join(timeout=2)
                if p.is_alive():
                    p.terminate()

        self.stdout.write(self.style.SUCCESS("Load generation finished"))
