import uuid
from django.core.management.base import BaseCommand
from apps.accounts.services import DevAuthService
from apps.tenants.models import DataSource

class Command(BaseCommand):
    help = "Seeds initial development tenant, personas, and data sources."

    def handle(self, *args, **options):
        dev_auth = DevAuthService()
        tenant = dev_auth.ensure_synthetic_tenant()
        self.stdout.write(self.style.SUCCESS(f"Tenant ready: {tenant.name} ({tenant.id})"))

        for persona in ("operator", "verifier", "lead"):
            user = dev_auth.get_or_create_persona(persona)
            self.stdout.write(self.style.SUCCESS(f"Persona ready: {user.display_name} ({user.username})"))

        # Seed data sources
        sources = [
            {
                "name": "Contact centre feed",
                "kind": "Complaint intake",
                "status": DataSource.Status.AVAILABLE,
                "note": "Real-time stream from phone and email channels",
            },
            {
                "name": "Core banking (Finacle)",
                "kind": "Transactions",
                "status": DataSource.Status.AVAILABLE,
                "note": "Account balance and debit/credit ledger records",
            },
            {
                "name": "Card management system",
                "kind": "Transactions",
                "status": DataSource.Status.STALE,
                "note": "ATM & POS journal sync delayed by ~4 hours",
            },
            {
                "name": "Instant payment switch (NIBSS)",
                "kind": "Settlement",
                "status": DataSource.Status.AVAILABLE,
                "note": "Interbank transfer clearing updates",
            },
        ]

        for s in sources:
            ds, created = DataSource.objects.get_or_create(
                tenant=tenant,
                name=s["name"],
                defaults={
                    "kind": s["kind"],
                    "status": s["status"],
                    "note": s["note"],
                }
            )
            action = "Created" if created else "Exists"
            self.stdout.write(f"  {action} DataSource: {ds.name} [{ds.status}]")

        self.stdout.write(self.style.SUCCESS("Database seeded successfully for development!"))
