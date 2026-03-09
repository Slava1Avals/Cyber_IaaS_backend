import time

from django.core.management.base import BaseCommand, CommandError

from vm_manager.services import DockerServiceError, collect_vm_metrics_loop


class Command(BaseCommand):
    help = "Collect VM metrics snapshots from Docker or in simulation mode"

    def add_arguments(self, parser):
        parser.add_argument(
            "--simulate",
            action="store_true",
            help="Generate lightweight host-based metrics instead of reading docker stats",
        )
        parser.add_argument(
            "--lightweight",
            action="store_true",
            help="Use max-efficient host-based collection from /proc (no docker stats)",
        )
        parser.add_argument(
            "--interval",
            type=float,
            default=5.0,
            help="Interval between iterations in seconds (default: 5)",
        )
        parser.add_argument(
            "--iterations",
            type=int,
            default=1,
            help="How many collection cycles to run (default: 1)",
        )
        parser.add_argument(
            "--forever",
            action="store_true",
            help="Run metrics collection continuously until process is stopped",
        )
        parser.add_argument(
            "--all-vms",
            action="store_true",
            help="Collect metrics for all VMs, not only running VMs",
        )

    def handle(self, *args, **options):
        simulate = options["simulate"]
        lightweight = options["lightweight"] or simulate
        interval = options["interval"]
        iterations = options["iterations"]
        forever = options["forever"]
        only_running = not options["all_vms"]

        if interval <= 0:
            raise CommandError("--interval must be > 0")
        if iterations <= 0:
            raise CommandError("--iterations must be > 0")

        if forever:
            self.stdout.write(
                self.style.WARNING(
                    f"Starting continuous metrics collector (lightweight={lightweight}, interval={interval}s, only_running={only_running})"
                )
            )
            total = 0
            while True:
                try:
                    created = collect_vm_metrics_loop(
                        simulate=simulate,
                        interval_seconds=interval,
                        iterations=1,
                        only_running=only_running,
                        lightweight=lightweight,
                    )
                    total += created
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Collected {created} snapshots this tick, total={total}"
                        )
                    )
                except DockerServiceError as exc:
                    self.stderr.write(self.style.ERROR(f"Collector tick failed: {exc}"))
                time.sleep(interval)

        try:
            total = collect_vm_metrics_loop(
                simulate=simulate,
                interval_seconds=interval,
                iterations=iterations,
                only_running=only_running,
                lightweight=lightweight,
            )
        except DockerServiceError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Collected {total} snapshots (lightweight={lightweight}, iterations={iterations}, only_running={only_running})"
            )
        )
