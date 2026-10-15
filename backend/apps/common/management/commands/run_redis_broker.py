import sys
import logging
from django.core.management.base import BaseCommand

logger = logging.getLogger("resolveai.redis")

class Command(BaseCommand):
    help = "Runs a local TCP-accessible Redis broker on 127.0.0.1:6379 using fakeredis.TcpFakeServer."

    def add_arguments(self, parser):
        parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind (default: 127.0.0.1)")
        parser.add_argument("--port", type=int, default=6379, help="TCP port to bind (default: 6379)")

    def handle(self, *args, **options):
        host = options["host"]
        port = options["port"]

        try:
            from fakeredis import TcpFakeServer
        except ImportError:
            self.stderr.write(self.style.ERROR("fakeredis package is required to run the local Redis broker."))
            sys.exit(1)

        self.stdout.write(self.style.SUCCESS(f"Starting ResolveAI Redis broker on {host}:{port}..."))
        try:
            server = TcpFakeServer((host, port))
            self.stdout.write(self.style.SUCCESS(f"Redis broker listening on tcp://{host}:{port}. Ready for Celery workers."))
            server.serve_forever()
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Redis broker shutting down..."))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Redis broker failed to start: {e}"))
            sys.exit(1)
