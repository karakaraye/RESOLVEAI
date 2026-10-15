from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.services import DevAuthService
from apps.complaints.models import (
    Customer,
    ComplaintCategory,
    Complaint,
    ComplaintNote,
    ComplaintTimelineEvent,
    ComplaintFollowUp,
    SourceEvent,
)
from apps.transactions.models import TransactionInvestigation
from apps.evidence.models import EvidenceRecord
from apps.tenants.models import DataSource


class Command(BaseCommand):
    help = "Seeds realistic, fictional banking complaint demonstration data for Test Bank."

    def handle(self, *args, **options):
        dev_auth = DevAuthService()
        tenant = dev_auth.ensure_synthetic_tenant()
        operator = dev_auth.get_or_create_persona("operator")
        verifier = dev_auth.get_or_create_persona("verifier")
        lead = dev_auth.get_or_create_persona("lead")

        self.stdout.write(f"Seeding synthetic complaint data for tenant: {tenant.name}...")

        # 1. Seed Categories
        categories_data = [
            {"code": "TRANSFERS", "label": "Failed transfer", "description": "Interbank and intrabank electronic transfer discrepancies"},
            {"code": "CARDS_ATM", "label": "Card & ATM debit", "description": "ATM dispense errors, card debit without cash, machine faults"},
            {"code": "ACCOUNT_ACCESS", "label": "Account access", "description": "Token reset, password lockout, biometric login failure"},
            {"code": "BILLING", "label": "Unexpected charges & fees", "description": "Unexplained ledger debits, card maintenance fees, SMS fees"},
            {"code": "MOBILE_APP", "label": "Mobile app error", "description": "App crashes, connection timeouts, update errors"},
            {"code": "POS_TERMINAL", "label": "POS payment failure", "description": "Declined card payment at merchant terminal with debit alert"},
        ]

        category_map = {}
        for c in categories_data:
            cat, _ = ComplaintCategory.objects.get_or_create(
                tenant=tenant,
                code=c["code"],
                defaults={"label": c["label"], "description": c["description"], "is_active": True}
            )
            category_map[c["code"]] = cat

        self.stdout.write(self.style.SUCCESS(f"Categories ready: {len(category_map)}"))

        # Fetch Data Sources
        ds_contact = DataSource.objects.filter(tenant=tenant, name="Contact centre feed").first()
        ds_core = DataSource.objects.filter(tenant=tenant, name="Core banking (Finacle)").first()
        ds_cards = DataSource.objects.filter(tenant=tenant, name="Card management system").first()
        ds_nibss = DataSource.objects.filter(tenant=tenant, name="Instant payment switch (NIBSS)").first()

        now = timezone.now()

        # 2. Seed Synthetic Complaints
        cases = [
            {
                "ref": "CMP-2026-0001",
                "cust_no": "CUST-782101",
                "first_name": "Amina",
                "last_name": "Bello",
                "email": "amina.bello@example.test",
                "phone": "+2348031112233",
                "account": "0123456789",
                "source_ref": "EXT-FEED-99410",
                "channel": "Contact centre feed",
                "data_source": ds_contact,
                "summary": "[DEMO] Interbank transfer debited but beneficiary not credited",
                "narrative": "[SYNTHETIC DEMO] Customer initiated ₦50,000 NIP transfer to Zenith Bank account on 12 Oct at 14:22. Sender account was debited, but beneficiary has not received the credit after 48 hours. Session ID: 999014261012142231001.",
                "category": category_map["TRANSFERS"],
                "priority": Complaint.Priority.HIGH,
                "status": Complaint.Status.NEW,
                "assigned": None,
                "received_delta": timedelta(hours=3),
                "due_delta": timedelta(hours=21),
            },
            {
                "ref": "CMP-2026-0002",
                "cust_no": "CUST-914022",
                "first_name": "Chidi",
                "last_name": "Okonkwo",
                "email": "chidi.okonkwo@example.test",
                "phone": "+2348023334455",
                "account": "0987654321",
                "source_ref": "ATM-JRNL-8402",
                "channel": "Core banking (Finacle)",
                "data_source": ds_core,
                "summary": "[DEMO] ATM dispense error: cash unretrieved, account debited",
                "narrative": "[SYNTHETIC DEMO] Customer attempted withdrawal of ₦20,000 at Victoria Island Branch ATM 2. Machine displayed 'Hardware Error' and rebooted. Card was returned but no cash was dispensed; customer received instant debit SMS notification.",
                "category": category_map["CARDS_ATM"],
                "priority": Complaint.Priority.HIGH,
                "status": Complaint.Status.NEEDS_ACTION,
                "assigned": operator,
                "received_delta": timedelta(hours=18),
                "due_delta": timedelta(hours=6),
            },
            {
                "ref": "CMP-2026-0003",
                "cust_no": "CUST-331045",
                "first_name": "Fatima",
                "last_name": "Yusuf",
                "email": "fatima.yusuf@example.test",
                "phone": "+2348055556677",
                "account": "0456123789",
                "source_ref": "APP-ERR-5102",
                "channel": "Contact centre feed",
                "data_source": ds_contact,
                "summary": "[DEMO] Mobile app crashes repeatedly on FaceID authentication",
                "narrative": "[SYNTHETIC DEMO] Following app v4.2.1 release, customer cannot log into mobile banking on iPhone 15 Pro (iOS 18.0). App terminates immediately upon facial biometric scan. Reinstalling does not resolve the issue.",
                "category": category_map["MOBILE_APP"],
                "priority": Complaint.Priority.MEDIUM,
                "status": Complaint.Status.IN_PROGRESS,
                "assigned": operator,
                "received_delta": timedelta(hours=28),
                "due_delta": timedelta(hours=20),
            },
            {
                "ref": "CMP-2026-0004",
                "cust_no": "CUST-662910",
                "first_name": "Emeka",
                "last_name": "Eze",
                "email": "emeka.eze@example.test",
                "phone": "+2348077778899",
                "account": "0789456123",
                "source_ref": "CMS-DISP-3391",
                "channel": "Card management system",
                "data_source": ds_cards,
                "summary": "[DEMO] Suspected double charge on international web subscription",
                "narrative": "[SYNTHETIC DEMO] Customer was billed twice for a $14.99 cloud storage subscription on 10 Oct at 02:15 UTC. Card management system records two distinct authorization holds for the same merchant reference.",
                "category": category_map["BILLING"],
                "priority": Complaint.Priority.MEDIUM,
                "status": Complaint.Status.FORWARDED,
                "assigned": operator,
                "received_delta": timedelta(hours=40),
                "due_delta": timedelta(hours=8),
            },
            {
                "ref": "CMP-2026-0005",
                "cust_no": "CUST-104928",
                "first_name": "Ngozi",
                "last_name": "Adeyemi",
                "email": "ngozi.adeyemi@example.test",
                "phone": "+2348099990011",
                "account": "0321654987",
                "source_ref": "EXT-FEED-99520",
                "channel": "Contact centre feed",
                "data_source": ds_contact,
                "summary": "[DEMO] Erroneous monthly account maintenance charge on zero balance",
                "narrative": "[SYNTHETIC DEMO] Customer lodged dispute against ₦1,250 ledger debit fee applied to salary account during transition period. Customer agreement waives maintenance charges for accounts receiving active payroll.",
                "category": category_map["BILLING"],
                "priority": Complaint.Priority.LOW,
                "status": Complaint.Status.AWAITING_VERIFICATION,
                "assigned": operator,
                "received_delta": timedelta(days=3),
                "due_delta": timedelta(hours=14),
                "resolution": {
                    "outcome": "[SYNTHETIC DEMO] Fee reversal of ₦1,250 processed via core banking transaction reference REV-20261013-094. Account ledger status updated to Fee-Exempt.",
                    "evidence": "Finacle batch reversal journal #99420 confirmed by Settlement Desk.",
                    "reported_by": operator,
                }
            },
            {
                "ref": "CMP-2026-0006",
                "cust_no": "CUST-449102",
                "first_name": "Babajide",
                "last_name": "Sanusi",
                "email": "babajide.sanusi@example.test",
                "phone": "+2348011223344",
                "account": "0654987321",
                "source_ref": "EXT-FEED-99104",
                "channel": "Contact centre feed",
                "data_source": ds_contact,
                "summary": "[DEMO] Hardware token synchronization failure during overseas travel",
                "narrative": "[SYNTHETIC DEMO] Corporate signatory unable to authorize foreign exchange transfer due to token drift. Online banking rejected 6 consecutive OTP codes.",
                "category": category_map["ACCOUNT_ACCESS"],
                "priority": Complaint.Priority.LOW,
                "status": Complaint.Status.RESOLVED,
                "assigned": operator,
                "received_delta": timedelta(days=5),
                "due_delta": timedelta(days=3),
                "resolution": {
                    "outcome": "[SYNTHETIC DEMO] Soft token profile re-provisioned via secure video verification call. Customer verified successful login and authorized transaction.",
                    "evidence": "Security Operations authorization ticket #SEC-88219 signed off.",
                    "reported_by": operator,
                    "verified_by": verifier,
                }
            },
            {
                "ref": "CMP-2026-0007",
                "cust_no": "CUST-883011",
                "first_name": "Tunde",
                "last_name": "Bakare",
                "email": "tunde.bakare@example.test",
                "phone": "+2348044556677",
                "account": "0147258369",
                "source_ref": "NIBSS-SW-7712",
                "channel": "Instant payment switch (NIBSS)",
                "data_source": ds_nibss,
                "summary": "[DEMO] Corporate payroll batch timeout affecting 45 employees",
                "narrative": "[SYNTHETIC DEMO] Bulk payroll file failed midway through clearing cycle at 17:00 Friday. Debit of ₦4,500,000 posted against employer account but 45 credit legs remained in PENDING_SETTLEMENT state on NIBSS switch.",
                "category": category_map["TRANSFERS"],
                "priority": Complaint.Priority.CRITICAL,
                "status": Complaint.Status.IN_PROGRESS,
                "assigned": operator,
                "received_delta": timedelta(days=2),
                "due_delta": -timedelta(hours=6),  # Overdue!
            },
            {
                "ref": "CMP-2026-0008",
                "cust_no": "CUST-551920",
                "first_name": "Zainab",
                "last_name": "Ibrahim",
                "email": "zainab.ibrahim@example.test",
                "phone": "+2348066778899",
                "account": "0369258147",
                "source_ref": "CMS-POS-1049",
                "channel": "Card management system",
                "data_source": ds_cards,
                "summary": "[DEMO] POS merchant terminal decline with immediate card debit",
                "narrative": "[SYNTHETIC DEMO] Customer paid ₦18,500 at supermarket POS. Terminal printed 'Issuer Timeout', merchant refused release of goods. Reversal promised within 24 hours failed to post.",
                "category": category_map["POS_TERMINAL"],
                "priority": Complaint.Priority.MEDIUM,
                "status": Complaint.Status.REOPENED,
                "assigned": operator,
                "received_delta": timedelta(days=4),
                "due_delta": timedelta(hours=12),
                "reopen_reason": "[SYNTHETIC DEMO] Case was marked resolved on initial auto-reversal advice, but merchant's acquiring bank settled the transaction 48 hours later, debited customer second time.",
            },
        ]

        created_count = 0
        for item in cases:
            cust, _ = Customer.objects.get_or_create(
                tenant=tenant,
                customer_number=item["cust_no"],
                defaults={
                    "first_name": item["first_name"],
                    "last_name": item["last_name"],
                    "email": item["email"],
                    "phone": item["phone"],
                    "account_number": item["account"],
                }
            )

            received_at = now - item["received_delta"]
            due_at = now + item["due_delta"]

            complaint, created = Complaint.objects.get_or_create(
                tenant=tenant,
                reference=item["ref"],
                defaults={
                    "customer": cust,
                    "customer_reference": cust.customer_number,
                    "original_source_reference": item["source_ref"],
                    "source_channel": item["channel"],
                    "source_data_source": item["data_source"],
                    "summary": item["summary"],
                    "narrative": item["narrative"],
                    "category": item["category"],
                    "priority": item["priority"],
                    "status": item["status"],
                    "assigned_operator": item["assigned"],
                    "assigned_at": received_at + timedelta(minutes=15) if item["assigned"] else None,
                    "received_at": received_at,
                    "due_at": due_at,
                    "reopen_reason": item.get("reopen_reason", ""),
                }
            )

            if created:
                created_count += 1
                # SourceEvent for duplicate webhook prevention
                SourceEvent.objects.get_or_create(
                    tenant=tenant,
                    external_event_id=item["source_ref"],
                    defaults={
                        "source_data_source": item["data_source"],
                        "source_channel": item["channel"],
                        "payload": {"reference": item["ref"], "summary": item["summary"]},
                        "processed": True,
                    }
                )

                # Timeline: complaint received
                ComplaintTimelineEvent.objects.create(
                    complaint=complaint,
                    tenant=tenant,
                    at=received_at,
                    kind="RECEIVED",
                    title=f"Complaint received via {item['channel']}",
                    detail=f"Source ID: {item['source_ref']}",
                    actor="Channel Feed Worker",
                )

                if item["assigned"]:
                    ComplaintTimelineEvent.objects.create(
                        complaint=complaint,
                        tenant=tenant,
                        at=received_at + timedelta(minutes=15),
                        kind="ASSIGNED",
                        title=f"Assigned to {item['assigned'].display_name}",
                        detail="Initial case assignment from unassigned queue.",
                        actor="Supervisor",
                    )

                # Case notes
                ComplaintNote.objects.create(
                    complaint=complaint,
                    tenant=tenant,
                    author=operator,
                    author_display_name=operator.display_name,
                    text=f"[SYNTHETIC NOTE] Case opened for customer {cust.full_name}. Initial triage performed.",
                )

                # Resolution if applicable
                res = item.get("resolution")
                if res:
                    complaint.resolution_outcome = res["outcome"]
                    complaint.resolution_evidence = res.get("evidence", "")
                    complaint.resolution_reported_at = received_at + timedelta(hours=4)
                    complaint.resolution_reported_by = res["reported_by"]

                    if "verified_by" in res:
                        complaint.resolution_verification = Complaint.ResolutionVerification.VERIFIED
                        complaint.resolution_verified_at = received_at + timedelta(hours=6)
                        complaint.resolution_verified_by = res["verified_by"]
                        ComplaintTimelineEvent.objects.create(
                            complaint=complaint,
                            tenant=tenant,
                            at=received_at + timedelta(hours=6),
                            kind="OUTCOME_VERIFIED",
                            title="Outcome verified (Case Resolved)",
                            detail="Verified by senior compliance officer.",
                            actor=res["verified_by"].display_name,
                        )
                    else:
                        complaint.resolution_verification = Complaint.ResolutionVerification.AWAITING
                        ComplaintTimelineEvent.objects.create(
                            complaint=complaint,
                            tenant=tenant,
                            at=received_at + timedelta(hours=4),
                            kind="OUTCOME_RECORDED",
                            title="Outcome recorded (Awaiting verification)",
                            detail=res["outcome"][:100],
                            actor=res["reported_by"].display_name,
                        )

                    complaint.save()

                if item["status"] == Complaint.Status.REOPENED:
                    ComplaintTimelineEvent.objects.create(
                        complaint=complaint,
                        tenant=tenant,
                        at=now - timedelta(hours=2),
                        kind="REOPENED",
                        title="Complaint reopened",
                        detail=item["reopen_reason"],
                        actor="Customer via Contact Centre",
                    )

        self.stdout.write(self.style.SUCCESS(f"Seeded {created_count} new synthetic complaints successfully!"))

        # 3. Seed Realistic Transaction Investigations & Authoritative Evidence
        self.stdout.write("Seeding synthetic transaction investigations & evidence records...")

        # Case 1: CMP-2026-0001 (NIP transfer discrepancy)
        c1 = Complaint.objects.filter(tenant=tenant, reference="CMP-2026-0001").first()
        if c1:
            t1_1, _ = TransactionInvestigation.objects.get_or_create(
                tenant=tenant,
                complaint=c1,
                reference="TXN-TEST-90311",
                defaults={
                    "source_system": "Core banking (Finacle)",
                    "amount_value": 50000.00,
                    "amount_currency": "NGN",
                    "occurred_at": c1.received_at - timedelta(hours=2),
                    "status_label": "Debited",
                    "status": TransactionInvestigation.SourceStatus.AVAILABLE,
                    "last_updated_at": now - timedelta(hours=1),
                    "conflict": "Sources disagree: Core banking shows DEBITED; switch shows PENDING (Session 999014261012142231001 inward credit unconfirmed). No final outcome is assumed.",
                    "match_evidence": "Account 0123456789, amount ₦50,000.00, and timestamp matching customer transfer grievance.",
                }
            )
            t1_2, _ = TransactionInvestigation.objects.get_or_create(
                tenant=tenant,
                complaint=c1,
                reference="NIP-SES-999014261012",
                defaults={
                    "source_system": "Instant payment switch (NIBSS)",
                    "amount_value": 50000.00,
                    "amount_currency": "NGN",
                    "occurred_at": c1.received_at - timedelta(hours=2),
                    "status_label": "Switch Pending",
                    "status": TransactionInvestigation.SourceStatus.STALE,
                    "last_updated_at": now - timedelta(hours=3),
                    "conflict": "Sources disagree: NIBSS switch response delayed over 48 hours; destination bank credit unacknowledged. No final outcome is assumed.",
                    "match_evidence": "Exact NIP session ID 999014261012142231001 match.",
                }
            )
            EvidenceRecord.objects.get_or_create(
                tenant=tenant,
                complaint=c1,
                document_reference="JRN-FIN-20261012-9844",
                defaults={
                    "transaction_investigation": t1_1,
                    "kind": EvidenceRecord.EvidenceKind.LEDGER_ENTRY,
                    "title": "Finacle Core Ledger Outward Debit Journal",
                    "summary": "Ledger entry debited ₦50,000.00 from account 0123456789 with response code 00.",
                    "source_system": "Finacle Core Banking Journal",
                    "source_timestamp": c1.received_at - timedelta(hours=2),
                    "provenance": "Extracted via Core Banking Read-Only Journal Feed at 2026-10-14T08:00:00Z by Batch #4412",
                    "data_freshness": EvidenceRecord.DataFreshness.FRESH,
                    "is_verified": True,
                    "verified_by": verifier,
                    "verified_at": now - timedelta(hours=2),
                    "raw_payload": {
                        "journal_number": "JRN-FIN-20261012-9844",
                        "narration": "NIP/ZENITH/BASHIR BELLO/OUTWARD TRF",
                        "amount": "50000.00",
                        "status": "POSTED",
                    },
                }
            )
            EvidenceRecord.objects.get_or_create(
                tenant=tenant,
                complaint=c1,
                document_reference="NIP-TRACE-999014261012",
                defaults={
                    "transaction_investigation": t1_2,
                    "kind": EvidenceRecord.EvidenceKind.SWITCH_LOG,
                    "title": "NIBSS Outward Gateway Session Status Extract",
                    "summary": "Switch session state: AWAITING_BENEFICIARY_ACK; retry count 3.",
                    "source_system": "NIBSS Settlement Switch Log",
                    "source_timestamp": c1.received_at - timedelta(hours=2),
                    "provenance": "Extracted from NIBSS NIP Archive Gateway via API query",
                    "data_freshness": EvidenceRecord.DataFreshness.STALE,
                    "is_verified": False,
                    "raw_payload": {
                        "nip_session_id": "999014261012142231001",
                        "originating_bank": "044",
                        "destination_bank": "057",
                        "status": "PENDING",
                    },
                }
            )

        # Case 2: CMP-2026-0002 (ATM dispense error)
        c2 = Complaint.objects.filter(tenant=tenant, reference="CMP-2026-0002").first()
        if c2:
            t2, _ = TransactionInvestigation.objects.get_or_create(
                tenant=tenant,
                complaint=c2,
                reference="ATM-JRNL-8402",
                defaults={
                    "source_system": "Core banking (Finacle)",
                    "amount_value": 20000.00,
                    "amount_currency": "NGN",
                    "occurred_at": c2.received_at - timedelta(hours=1),
                    "status_label": "Debited",
                    "status": TransactionInvestigation.SourceStatus.AVAILABLE,
                    "last_updated_at": now - timedelta(hours=2),
                    "conflict": "Sources disagree: Core banking ledger debited ₦20,000; ATM journal reports hardware sensor timeout on bill presenter. No final outcome is assumed.",
                    "match_evidence": "Card withdrawal at Victoria Island ATM 2 matching account 0987654321.",
                }
            )
            EvidenceRecord.objects.get_or_create(
                tenant=tenant,
                complaint=c2,
                document_reference="ATM-TRACE-881204",
                defaults={
                    "transaction_investigation": t2,
                    "kind": EvidenceRecord.EvidenceKind.SYSTEM_TRACE,
                    "title": "Victoria Island ATM 2 Hardware Presenter Diagnostic Log",
                    "summary": "Bill presenter pick failure code 42. Zero cassette notes were picked or presented to customer.",
                    "source_system": "Wincor Nixdorf ATM Terminal Journal",
                    "source_timestamp": c2.received_at - timedelta(hours=1),
                    "provenance": "Retrieved from Branch ATM Electronic Journal Server via automated diagnostic probe",
                    "data_freshness": EvidenceRecord.DataFreshness.FRESH,
                    "is_verified": True,
                    "verified_by": verifier,
                    "verified_at": now - timedelta(hours=1),
                    "raw_payload": {
                        "terminal_id": "ATM-VI-02",
                        "stan": "881204",
                        "error_code": "BILL_PRESENTER_PICK_FAILURE_CODE_42",
                        "presented_notes": 0,
                    },
                }
            )

        # Case 4: CMP-2026-0004 (Double charge on card subscription)
        c4 = Complaint.objects.filter(tenant=tenant, reference="CMP-2026-0004").first()
        if c4:
            t4, _ = TransactionInvestigation.objects.get_or_create(
                tenant=tenant,
                complaint=c4,
                reference="CRD-TXN-771092",
                defaults={
                    "source_system": "Card management system",
                    "amount_value": 68450.00,
                    "amount_currency": "NGN",
                    "occurred_at": c4.received_at - timedelta(hours=2),
                    "status_label": "Settled",
                    "status": TransactionInvestigation.SourceStatus.AVAILABLE,
                    "last_updated_at": now - timedelta(hours=4),
                    "conflict": "Sources disagree: Two identical authorization requests received within 1.2 seconds from merchant gateway. Second debit settled without reversal. No final outcome is assumed.",
                    "match_evidence": "Card PAN ending in 1234, international merchant ID 'CLOUD_HOST_US'.",
                }
            )
            EvidenceRecord.objects.get_or_create(
                tenant=tenant,
                complaint=c4,
                document_reference="SW-AUTH-428901771092",
                defaults={
                    "transaction_investigation": t4,
                    "kind": EvidenceRecord.EvidenceKind.SWITCH_LOG,
                    "title": "Interswitch Card Auth Trace Log",
                    "summary": "Duplicate authorization match with RRN 428901771092 and STAN 771092.",
                    "source_system": "Interswitch ISO-8583 Gateway",
                    "source_timestamp": c4.received_at - timedelta(hours=2),
                    "provenance": "Fetched from Card Authorization Switch Gateway log repository",
                    "data_freshness": EvidenceRecord.DataFreshness.FRESH,
                    "is_verified": True,
                    "verified_by": verifier,
                    "verified_at": now - timedelta(hours=3),
                    "raw_payload": {
                        "masked_pan": "539941******1234",
                        "rrn": "428901771092",
                        "stan": "771092",
                        "auth_amount_usd": "45.00",
                    },
                }
            )

        # Case 5: CMP-2026-0005 (Erroneous maintenance fee)
        c5 = Complaint.objects.filter(tenant=tenant, reference="CMP-2026-0005").first()
        if c5:
            t5, _ = TransactionInvestigation.objects.get_or_create(
                tenant=tenant,
                complaint=c5,
                reference="FEE-20261014-0012",
                defaults={
                    "source_system": "Core banking (Finacle)",
                    "amount_value": 3500.00,
                    "amount_currency": "NGN",
                    "occurred_at": c5.received_at - timedelta(hours=5),
                    "status_label": "Debited",
                    "status": TransactionInvestigation.SourceStatus.AVAILABLE,
                    "last_updated_at": now - timedelta(hours=6),
                    "conflict": "Sources disagree: Account has salary exemption waiver on record; batch job applied standard commercial account fee. No final outcome is assumed.",
                    "match_evidence": "Automated monthly ledger maintenance charge on salary account 0311223344.",
                }
            )
            EvidenceRecord.objects.get_or_create(
                tenant=tenant,
                complaint=c5,
                document_reference="WVR-SAL-9941",
                defaults={
                    "transaction_investigation": t5,
                    "kind": EvidenceRecord.EvidenceKind.CUSTOMER_RECEIPT,
                    "title": "Corporate Payroll Agreement & Salary Account Fee Exemption Schedule",
                    "summary": "Customer signed payroll schedule exempting account from ledger maintenance fees.",
                    "source_system": "Document Management System (DMS)",
                    "source_timestamp": now - timedelta(days=120),
                    "provenance": "Archived customer account onboarding agreement scanned document",
                    "data_freshness": EvidenceRecord.DataFreshness.HISTORICAL,
                    "is_verified": True,
                    "verified_by": verifier,
                    "verified_at": now - timedelta(hours=5),
                    "raw_payload": {
                        "waiver_id": "WVR-SAL-9941",
                        "exemption_type": "ZERO_MAINTENANCE_FEE",
                    },
                }
            )

        # Case 7: CMP-2026-0007 (Corporate payroll batch timeout)
        c7 = Complaint.objects.filter(tenant=tenant, reference="CMP-2026-0007").first()
        if c7:
            t7, _ = TransactionInvestigation.objects.get_or_create(
                tenant=tenant,
                complaint=c7,
                reference="CORP-PAY-998201",
                defaults={
                    "source_system": "Core banking (Finacle)",
                    "amount_value": 12450000.00,
                    "amount_currency": "NGN",
                    "occurred_at": c7.received_at - timedelta(hours=2),
                    "status_label": "Processing Timeout",
                    "status": TransactionInvestigation.SourceStatus.STALE,
                    "last_updated_at": now - timedelta(hours=1),
                    "conflict": "Sources disagree: Master corporate debit posted (₦12,450,000); 45 of 120 employee beneficiary credits timed out at clearing switch. No final outcome is assumed.",
                    "match_evidence": "Corporate salary disbursement batch #PAYROLL-2026-OCT.",
                }
            )
            EvidenceRecord.objects.get_or_create(
                tenant=tenant,
                complaint=c7,
                document_reference="PAYROLL-BATCH-20261013",
                defaults={
                    "transaction_investigation": t7,
                    "kind": EvidenceRecord.EvidenceKind.LEDGER_ENTRY,
                    "title": "Core Banking Batch Disbursement Clearing Summary",
                    "summary": "Total debited: ₦12,450,000.00; total successfully disbursed: ₦7,781,250.00; uncleared funds held: ₦4,668,750.00.",
                    "source_system": "Bulk Clearing Ledger (Finacle)",
                    "source_timestamp": c7.received_at - timedelta(hours=2),
                    "provenance": "Extracted from Core Banking End-of-Day clearing ledger output file",
                    "data_freshness": EvidenceRecord.DataFreshness.STALE,
                    "is_verified": True,
                    "verified_by": verifier,
                    "verified_at": now - timedelta(hours=2),
                    "raw_payload": {
                        "batch_id": "PAYROLL-2026-OCT",
                        "records_total": 120,
                        "records_pending": 45,
                    },
                }
            )

        self.stdout.write(self.style.SUCCESS("Transaction investigations & authoritative evidence seeded successfully!"))

        # Stage 4: Seed Embeddings, Intelligence Findings & Emerging Incidents
        self.stdout.write("Generating semantic embeddings and intelligence findings...")
        from apps.intelligence.services.coordinator import ComplaintIntelligenceCoordinator
        from apps.incidents.services import IncidentDetectionService

        coord = ComplaintIntelligenceCoordinator()
        for comp in Complaint.objects.filter(tenant=tenant):
            coord.process_complaint_intelligence(comp)

        self.stdout.write(self.style.SUCCESS("Semantic embeddings and grounded intelligence findings generated!"))

        # Detect emerging incidents
        self.stdout.write("Running emerging incident detection engine...")
        detected = IncidentDetectionService.detect_emerging_incidents(tenant=tenant, lookback_hours=168)
        self.stdout.write(self.style.SUCCESS(f"Emerging incidents active: {len(detected)}"))

        # Stage 5: Seed Receiving Teams, Team Recipients, Policies & Initial Handoffs
        self.stdout.write("Seeding Stage 5 Receiving Teams and Handoffs...")
        from apps.handoffs.models import (
            ReceivingTeam,
            TeamRecipient,
            ForwardingPolicy,
            ForwardingHandoff,
            HandoffAttempt,
            HandoffEvent,
            HandoffResponse,
        )

        team_settle, _ = ReceivingTeam.objects.get_or_create(
            tenant=tenant,
            code="SETTLEMENTS",
            defaults={
                "name": "Settlements team",
                "channel": "Bank case-management queue",
                "fallback_channel": "Secure email",
                "response_due_hours": 24,
            }
        )
        TeamRecipient.objects.get_or_create(team=team_settle, name="Duty lead", defaults={"role_or_title": "Senior Settlements Officer"})
        TeamRecipient.objects.get_or_create(team=team_settle, name="Reconciliation desk", defaults={"role_or_title": "Interbank Recon Specialist"})

        team_cards, _ = ReceivingTeam.objects.get_or_create(
            tenant=tenant,
            code="CARDS",
            defaults={
                "name": "Card operations",
                "channel": "Secure email",
                "fallback_channel": "Bank case-management queue",
                "response_due_hours": 48,
            }
        )
        TeamRecipient.objects.get_or_create(team=team_cards, name="Card dispute desk", defaults={"role_or_title": "Chargeback Analyst"})
        TeamRecipient.objects.get_or_create(team=team_cards, name="Scheme liaison lead", defaults={"role_or_title": "Mastercard/Visa Desk"})

        team_fraud, _ = ReceivingTeam.objects.get_or_create(
            tenant=tenant,
            code="FRAUD",
            defaults={
                "name": "Fraud & Security",
                "channel": "Internal priority queue",
                "fallback_channel": "Emergency dispatch hotline",
                "response_due_hours": 12,
            }
        )
        TeamRecipient.objects.get_or_create(team=team_fraud, name="Duty fraud investigator", defaults={"role_or_title": "Fraud Operations"})

        # Forwarding Policies
        cat_transfer = ComplaintCategory.objects.filter(code="TRANSFER").first()
        if cat_transfer:
            ForwardingPolicy.objects.get_or_create(
                tenant=tenant,
                category=cat_transfer,
                defaults={
                    "default_team": team_settle,
                    "sla_response_hours": 24,
                    "reminder_lead_hours": 4,
                    "max_retry_attempts": 3,
                    "shared_fields": ["Reference", "Issue summary", "Transaction reference", "Masked customer reference"],
                }
            )

        cat_cards = ComplaintCategory.objects.filter(code="CARD").first()
        if cat_cards:
            ForwardingPolicy.objects.get_or_create(
                tenant=tenant,
                category=cat_cards,
                defaults={
                    "default_team": team_cards,
                    "sla_response_hours": 48,
                    "reminder_lead_hours": 8,
                    "max_retry_attempts": 3,
                    "shared_fields": ["Reference", "Issue summary", "Transaction reference", "Masked customer reference"],
                }
            )

        # Demo Forwarded Handoffs for CMP-2026-0004
        c4 = Complaint.objects.filter(tenant=tenant, reference="CMP-2026-0004").first()
        if c4:
            h4, created4 = ForwardingHandoff.objects.get_or_create(
                tenant=tenant,
                complaint=c4,
                team=team_settle,
                defaults={
                    "recipient": "Duty lead",
                    "channel": team_settle.channel,
                    "state": ForwardingHandoff.State.DELIVERED,
                    "message": f"{c4.reference} · ATM Cash Dispense Malfunction. Customer debited but cash retracted. Core banking shows successful debit.",
                    "shared_fields": ["Reference", "Issue summary", "Transaction reference", "Masked customer reference"],
                    "created_by": operator,
                    "created_by_name": operator.display_name,
                    "response_due_at": now + timedelta(hours=18),
                    "delivered_at": now - timedelta(hours=1),
                    "retry_count": 1,
                    "delivery_evidence": {"transmissionId": "TX-SYNTH-SETTLE-004", "receiptToken": "ACK-7721"},
                }
            )
            if created4:
                HandoffAttempt.objects.create(
                    handoff=h4,
                    attempt_number=1,
                    channel=team_settle.channel,
                    outcome="Delivered to Settlements queue. Delivery receipt ACK-7721 recorded.",
                    evidence={"transmissionId": "TX-SYNTH-SETTLE-004"},
                )

        # Demo Forwarded Handoff for CMP-2026-0001
        c1 = Complaint.objects.filter(tenant=tenant, reference="CMP-2026-0001").first()
        if c1:
            h1, created1 = ForwardingHandoff.objects.get_or_create(
                tenant=tenant,
                complaint=c1,
                team=team_settle,
                defaults={
                    "recipient": "Duty lead",
                    "channel": team_settle.channel,
                    "state": ForwardingHandoff.State.RESPONDED,
                    "message": f"{c1.reference} · Interbank transfer delayed. Please trace switch session with NIBSS.",
                    "shared_fields": ["Reference", "Issue summary", "Transaction reference", "Masked customer reference"],
                    "created_by": operator,
                    "created_by_name": operator.display_name,
                    "response_due_at": now - timedelta(hours=2),
                    "delivered_at": now - timedelta(hours=8),
                    "responded_at": now - timedelta(hours=1),
                    "retry_count": 1,
                    "delivery_evidence": {"transmissionId": "TX-SYNTH-SETTLE-001", "receiptToken": "ACK-1102"},
                }
            )
            if created1:
                HandoffAttempt.objects.create(
                    handoff=h1,
                    attempt_number=1,
                    channel=team_settle.channel,
                    outcome="Confirmed delivered by bank case-management gateway.",
                    evidence={"transmissionId": "TX-SYNTH-SETTLE-001"},
                )
                HandoffResponse.objects.create(
                    handoff=h1,
                    summary="Switch trace completed. Outward session 90311 timed out at destination switch. Manual reversal journal advice transmitted to core banking.",
                    responder_name="Reconciliation Desk Lead",
                    responder_contact="recon-desk@bank.test",
                )

        self.stdout.write(self.style.SUCCESS("Stage 5 Receiving Teams, Policies, and Handoffs seeded successfully!"))
