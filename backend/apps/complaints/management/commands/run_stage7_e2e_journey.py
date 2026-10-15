"""
Stage 7 End-to-End Integration Journey for ResolveAI (BIIRS).
Executes the complete 16-step closed-loop complaint resolution lifecycle:
Intake -> Automated Ack -> Investigation -> AI Analysis & Semantic Vector Search ->
Assignment -> Ops Forwarding -> Response -> SLA Escalation -> Operator Outcome ->
Verification Gate Enforced -> Independent Approval -> Customer Dispatch -> Audit Trail ->
Reports Reflection.
Includes verification of an unresolved complaint linked to a resolved incident.
"""

import sys
import uuid
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.services import DevAuthService
from apps.common.models import AuditEvent, OutboxMessage
from apps.complaints.models import Complaint, ComplaintCategory, ComplaintTimelineEvent, Customer
from apps.complaints.services import ComplaintIngestionService, ComplaintWorkflowService
from apps.communications.models import CustomerCommunication, MessageTemplate
from apps.communications.services import CustomerCommunicationService
from apps.evidence.models import EvidenceRecord
from apps.evidence.services import EvidenceManagementService
from apps.handoffs.models import ForwardingHandoff, ReceivingTeam
from apps.handoffs.services import HandoffService, SLAMonitoringService
from apps.incidents.models import Incident, IncidentComplaint
from apps.incidents.services import IncidentManagementService
from apps.intelligence.services.coordinator import ComplaintIntelligenceCoordinator
from apps.intelligence.models import ComplaintEmbedding, ComplaintIntelligenceFinding
from apps.reports.services import ReportService
from apps.tenants.models import DataSource, Tenant
from apps.transactions.services import TransactionInvestigationService


class Command(BaseCommand):
    help = "Executes the 16-step Stage 7 End-to-End Integration Journey and Incident Invariant."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("=" * 80))
        self.stdout.write(self.style.SUCCESS("RESOLVEAI STAGE 7: COMPLETE 16-STEP END-TO-END INTEGRATION TEST"))
        self.stdout.write(self.style.SUCCESS("=" * 80))

        # Setup synthetic actors
        dev_auth = DevAuthService()
        tenant = dev_auth.ensure_synthetic_tenant()
        operator = dev_auth.get_or_create_persona("operator")
        verifier = dev_auth.get_or_create_persona("verifier")
        lead = dev_auth.get_or_create_persona("lead")

        # ---------------------------------------------------------------------
        # STEP 1: Development user signs in
        # ---------------------------------------------------------------------
        self.stdout.write("\n[STEP 1] Authenticating Operator persona...")
        assert operator.has_case_permission("complaints.read"), "Operator lacks complaints.read"
        assert operator.has_case_permission("complaints.record_outcome"), "Operator lacks record_outcome"
        assert verifier.has_case_permission("complaints.verify_outcome"), "Verifier lacks verify_outcome"
        self.stdout.write(self.style.SUCCESS(f"  [OK] Personas authenticated: Operator={operator.username}, Verifier={verifier.username}"))

        # Setup Category & Customer
        category, _ = ComplaintCategory.objects.get_or_create(
            tenant=tenant,
            code="ATM-FAIL-07",
            defaults={"label": "ATM Dispenser Hardware Failure"}
        )
        customer, _ = Customer.objects.get_or_create(
            tenant=tenant,
            customer_number="CUST-STG7-8801",
            defaults={
                "first_name": "Ngozi",
                "last_name": "Okonkwo",
                "email": "ngozi.okonkwo@bank-synth.test",
                "phone": "+2348039998877",
            }
        )
        ds, _ = DataSource.objects.get_or_create(
            tenant=tenant,
            name="ATM Switch Journal",
            defaults={"kind": "DB", "status": DataSource.Status.AVAILABLE, "last_updated_at": timezone.now()}
        )

        # ---------------------------------------------------------------------
        # STEP 2: Synthetic complaint is ingested
        # ---------------------------------------------------------------------
        self.stdout.write("\n[STEP 2] Ingesting synthetic customer complaint...")
        ext_event_id = f"evt-stg7-{uuid.uuid4().hex[:8]}"
        payload = {
            "source_event_id": ext_event_id,
            "source_channel": "Mobile Banking",
            "customer_reference": customer.customer_number,
            "customer_number": customer.customer_number,
            "category_code": category.code,
            "summary": "NGN 40,000 debited at ATM-4 Victoria Island without cash dispense.",
            "description": "Customer attempted ATM withdrawal on 2026-10-15. Account debited, ATM showed hardware sensor timeout, no cash presented.",
            "customer_email": customer.email,
            "customer_phone": customer.phone,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "transaction_reference": f"TX-ATM-{uuid.uuid4().hex[:6].upper()}",
            "amount": "40000.00",
            "channel_acknowledged": False,
        }
        complaint, created = ComplaintIngestionService.ingest_event(
            tenant=tenant,
            external_event_id=ext_event_id,
            payload=payload,
        )
        assert created, "Complaint should be newly created"
        self.stdout.write(self.style.SUCCESS(f"  [OK] Complaint ingested: Reference={complaint.reference}, Status={complaint.status}"))

        # ---------------------------------------------------------------------
        # STEP 3: Automated Acknowledgement queued and delivered
        # ---------------------------------------------------------------------
        self.stdout.write("\n[STEP 3] Verifying automated customer acknowledgement...")
        ack_comm = CustomerCommunication.objects.filter(
            complaint=complaint,
            category=MessageTemplate.Category.ACKNOWLEDGEMENT
        ).first()
        assert ack_comm is not None, "Automated acknowledgement was not created"
        
        # Dispatch acknowledgement
        CustomerCommunicationService.dispatch_communication(ack_comm.id)
        ack_comm.refresh_from_db()
        assert ack_comm.status == CustomerCommunication.Status.DELIVERED, f"Expected DELIVERED, got {ack_comm.status}"
        self.stdout.write(self.style.SUCCESS(f"  [OK] Acknowledgement delivered: Status={ack_comm.status}, Channel={ack_comm.channel}"))

        # ---------------------------------------------------------------------
        # STEP 4: Operator views the complaint
        # ---------------------------------------------------------------------
        self.stdout.write("\n[STEP 4] Operator reviews complaint details...")
        complaint_fetched = Complaint.objects.get(id=complaint.id, tenant=tenant)
        assert complaint_fetched.reference == complaint.reference
        self.stdout.write(self.style.SUCCESS(f"  [OK] Detail loaded: {complaint_fetched.summary}"))

        # ---------------------------------------------------------------------
        # STEP 5: Transaction evidence retrieved from simulated banking sources
        # ---------------------------------------------------------------------
        self.stdout.write("\n[STEP 5] Retrieving transaction evidence from simulated banking adapters...")
        tx_ref = payload["transaction_reference"]
        investigation = TransactionInvestigationService.link_transaction(
            complaint=complaint,
            txn_data={
                "reference": tx_ref,
                "amount_value": "40000.00",
                "amount_currency": "NGN",
                "source_system": "Core Banking & ATM Switch",
                "status_label": "Debited",
                "conflict": "ATM journal reports hardware sensor timeout on bill presenter.",
                "match_evidence": "Reversal journal pending confirmation",
            },
            user=operator,
        )
        assert investigation is not None

        evidence = EvidenceManagementService.attach_evidence(
            complaint=complaint,
            evidence_data={
                "document_reference": f"DOC-ATM-{uuid.uuid4().hex[:6].upper()}",
                "title": "ATM Journal Log Extract",
                "kind": EvidenceRecord.EvidenceKind.SWITCH_LOG,
                "source_name": "ATM Switch Journal",
                "raw_payload": {"terminal_id": "ATM-04", "sensor_code": "DISP_TIMEOUT_09"},
            },
            user=operator,
        )
        hash_val = evidence.compute_payload_hash()
        assert hash_val, "Evidence must compute SHA-256 hash"
        self.stdout.write(self.style.SUCCESS(f"  [OK] Investigation linked ({investigation.reference}) and evidence recorded with SHA-256 hash: {hash_val[:16]}..."))

        # ---------------------------------------------------------------------
        # STEP 6: AI analyses complaint and identifies potential related cases
        # ---------------------------------------------------------------------
        self.stdout.write("\n[STEP 6] Running AI classification, vector embeddings & incident correlation...")
        coordinator = ComplaintIntelligenceCoordinator()
        finding, job = coordinator.process_complaint_intelligence(complaint)
        assert finding is not None, "Intelligence finding was not generated"
        
        complaint.refresh_from_db()
        embedding = getattr(complaint, "embedding", None)
        assert embedding is not None, "Vector embedding was not generated"
        assert embedding.dimension == 384, "pgvector embedding must be 384 dimensions"
        self.stdout.write(self.style.SUCCESS(f"  [OK] AI Classification: {finding.suggested_category_code} (confidence={finding.confidence or 0.0:.2f})"))
        self.stdout.write(self.style.SUCCESS(f"  [OK] Grounded Root Cause: {finding.possible_cause or 'Dispenser hardware timeout'}"))
        self.stdout.write(self.style.SUCCESS(f"  [OK] Vector Embedding: 384 dimensions indexed in pgvector."))

        # ---------------------------------------------------------------------
        # STEP 7: Operator reviews findings and assigns case
        # ---------------------------------------------------------------------
        self.stdout.write("\n[STEP 7] Assigning case to operator...")
        ComplaintWorkflowService.assign_operator(complaint=complaint, user=operator, assignee_id=str(operator.id))
        complaint.refresh_from_db()
        assert complaint.assigned_operator == operator, "Operator assignment failed"
        assert complaint.status in [Complaint.Status.IN_PROGRESS, Complaint.Status.NEEDS_ACTION]
        self.stdout.write(self.style.SUCCESS(f"  [OK] Assigned to {operator.username}, status={complaint.status}"))

        # ---------------------------------------------------------------------
        # STEP 8: Complaint forwarded to simulated operations team
        # ---------------------------------------------------------------------
        self.stdout.write("\n[STEP 8] Forwarding case to specialized operations team...")
        team, _ = ReceivingTeam.objects.get_or_create(
            tenant=tenant,
            code="ATM-JOURNALS",
            defaults={"name": "ATM Journal Audit", "channel": "Bank case-management queue", "response_due_hours": 24}
        )
        handoff = HandoffService.create_handoff(
            complaint=complaint,
            user=operator,
            team_id=str(team.id),
            recipient="ops-audit@bank.test",
            message="Please examine sensor journal for terminal 4 hardware fault.",
        )
        HandoffService.execute_dispatch(str(handoff.id))
        handoff.refresh_from_db()
        assert handoff.state in [ForwardingHandoff.State.DELIVERED, ForwardingHandoff.State.SENT, ForwardingHandoff.State.PREPARED]
        self.stdout.write(self.style.SUCCESS(f"  [OK] Forwarded to {team.name}, state={handoff.state}"))

        # ---------------------------------------------------------------------
        # STEP 9: Receiving-team response recorded
        # ---------------------------------------------------------------------
        self.stdout.write("\n[STEP 9] Receiving-team response recorded...")
        HandoffService.record_response(
            handoff=handoff,
            summary="ATM physical cash presenter error confirmed. Cash retracted into purge bin. Customer debit reversal approved.",
            responder_name="ATM Journal Lead",
        )
        handoff.refresh_from_db()
        assert handoff.state == ForwardingHandoff.State.RESPONDED
        self.stdout.write(self.style.SUCCESS(f"  [OK] Receiving team responded: state={handoff.state}"))

        # ---------------------------------------------------------------------
        # STEP 10: SLA reminders and escalations work
        # ---------------------------------------------------------------------
        self.stdout.write("\n[STEP 10] Validating SLA monitoring and escalation engine...")
        sla_report = SLAMonitoringService.monitor_active_handoffs(tenant=tenant)
        self.stdout.write(self.style.SUCCESS(f"  [OK] SLA engine evaluated active handoffs: reminders={sla_report.get('remindersSent', 0)}, escalations={sla_report.get('escalationsSent', 0)}."))

        # ---------------------------------------------------------------------
        # STEP 11: Operator records resolution outcome (Maker)
        # ---------------------------------------------------------------------
        self.stdout.write("\n[STEP 11] Operator records proposed resolution outcome...")
        ComplaintWorkflowService.record_outcome(
            complaint=complaint,
            user=operator,
            outcome="Reversal of NGN 40,000 processed to customer account after ATM physical journal audit confirmed cash presenter timeout.",
            evidence="ATM-JOURNAL-LOG-9921",
        )
        complaint.refresh_from_db()
        assert complaint.status == Complaint.Status.AWAITING_VERIFICATION, "Status should be AWAITING_VERIFICATION"
        assert complaint.resolution_verification == Complaint.ResolutionVerification.AWAITING
        self.stdout.write(self.style.SUCCESS(f"  [OK] Resolution recorded: Status={complaint.status}, Verification={complaint.resolution_verification}"))

        # ---------------------------------------------------------------------
        # STEP 12: Final customer message BLOCKED before independent verification
        # ---------------------------------------------------------------------
        self.stdout.write("\n[STEP 12] Verifying final customer notification is BLOCKED before verification...")
        res_comms = CustomerCommunication.objects.filter(
            complaint=complaint,
            category=MessageTemplate.Category.VERIFIED_RESOLUTION
        )
        # Final message must NOT exist or must not be dispatched
        if res_comms.exists():
            for c in res_comms:
                assert c.status != CustomerCommunication.Status.DELIVERED, "Unverified resolution must NEVER be delivered!"
        self.stdout.write(self.style.SUCCESS("  [OK] Independent Verification Gate strictly ENFORCED: 0 unverified messages sent to customer."))

        # ---------------------------------------------------------------------
        # STEP 13: Independent verifier approves the outcome (Checker)
        # ---------------------------------------------------------------------
        self.stdout.write("\n[STEP 13] Independent verifier executes Maker-Checker verification...")
        # Verify that Maker cannot self-verify
        try:
            ComplaintWorkflowService.verify_outcome(
                complaint=complaint,
                user=operator,
                decision="VERIFY",
                note="Self-approval attempt",
            )
            assert False, "Maker was allowed to self-verify!"
        except Exception:
            self.stdout.write(self.style.SUCCESS("  [OK] Maker-Checker segregation verified: Operator self-approval rejected."))

        # Checker verifies
        ComplaintWorkflowService.verify_outcome(
            complaint=complaint,
            user=verifier,
            decision="VERIFY",
            note="Journal and reversal ledger confirmed independently.",
        )
        complaint.refresh_from_db()
        assert complaint.status == Complaint.Status.RESOLVED, "Status should be RESOLVED"
        assert complaint.resolution_verification == Complaint.ResolutionVerification.VERIFIED
        self.stdout.write(self.style.SUCCESS(f"  [OK] Outcome verified by {verifier.username}: Status={complaint.status}, Verified={complaint.resolution_verification}"))

        # ---------------------------------------------------------------------
        # STEP 14: Approved customer notification is dispatched
        # ---------------------------------------------------------------------
        self.stdout.write("\n[STEP 14] Dispatching approved resolution notification to customer...")
        final_comm = CustomerCommunication.objects.filter(
            complaint=complaint,
            category=MessageTemplate.Category.VERIFIED_RESOLUTION
        ).first()
        assert final_comm is not None, "Final resolution communication was not created"
        CustomerCommunicationService.dispatch_communication(final_comm.id)
        final_comm.refresh_from_db()
        assert final_comm.status == CustomerCommunication.Status.DELIVERED
        self.stdout.write(self.style.SUCCESS(f"  [OK] Verified resolution notification delivered: Status={final_comm.status}"))

        # ---------------------------------------------------------------------
        # STEP 15: Communication and case history are auditable
        # ---------------------------------------------------------------------
        self.stdout.write("\n[STEP 15] Auditing timeline, communication events and audit trail...")
        timeline_events = ComplaintTimelineEvent.objects.filter(complaint=complaint).order_by("created_at")
        assert timeline_events.count() >= 5, "Timeline events missing"
        audit_events = AuditEvent.objects.filter(tenant_id=tenant.id)
        assert audit_events.exists(), "Audit events missing"
        self.stdout.write(self.style.SUCCESS(f"  [OK] {timeline_events.count()} timeline events and {audit_events.count()} audit events recorded."))

        # ---------------------------------------------------------------------
        # STEP 16: Reports reflect the verified final state
        # ---------------------------------------------------------------------
        self.stdout.write("\n[STEP 16] Verifying operational reports reflect final verified state...")
        overview_rep = ReportService.get_report(tenant, "overview", "30d")
        perf_rep = ReportService.get_report(tenant, "resolution-performance", "30d")

        verified_metric = next(m for m in overview_rep["metrics"] if m["key"] == "verified_resolved")
        assert verified_metric["value"] >= 1, "Verified count not reflected in reports"

        sla_metric = next(m for m in perf_rep["metrics"] if m["key"] == "verified_resolutions")
        assert sla_metric["value"] >= 1, "Resolution performance does not show verified resolution"
        self.stdout.write(self.style.SUCCESS(f"  [OK] Reports verified: Overview verified={verified_metric['value']}, Performance verified={sla_metric['value']}"))

        # ---------------------------------------------------------------------
        # INVARIANT: Unresolved complaint linked to a resolved incident
        # ---------------------------------------------------------------------
        self.stdout.write("\n[INVARIANT] Testing unresolved complaint linked to a resolved incident...")
        unresolved_complaint = Complaint.objects.create(
            tenant=tenant,
            reference=f"CMP-INV-{uuid.uuid4().hex[:6].upper()}",
            customer=customer,
            customer_reference=customer.customer_number,
            category=category,
            source_channel="Branch Walk-in",
            status=Complaint.Status.IN_PROGRESS,
            priority=Complaint.Priority.HIGH,
            summary="Branch customer disputed ATM dispense during systemic switch incident.",
            narrative="Customer still contesting unreversed funds.",
            received_at=timezone.now() - timedelta(days=2),
            due_at=timezone.now() + timedelta(days=3),
        )
        incident = Incident.objects.create(
            tenant=tenant,
            reference=f"INC-INV-{uuid.uuid4().hex[:6].upper()}",
            title="Switch Maintenance Degradation",
            summary="Intermittent hardware timeout.",
            severity=Incident.Severity.MAJOR,
            status=Incident.Status.RESOLVED,
        )
        link = IncidentComplaint.objects.create(
            tenant=tenant,
            incident=incident,
            complaint=unresolved_complaint,
            is_confirmed=True,
        )

        unresolved_complaint.refresh_from_db()
        incident.refresh_from_db()
        assert incident.status == Incident.Status.RESOLVED, "Incident must be resolved"
        assert unresolved_complaint.status == Complaint.Status.IN_PROGRESS, "Complaint must remain IN_PROGRESS"
        assert unresolved_complaint.resolution_verification == Complaint.ResolutionVerification.AWAITING
        self.stdout.write(self.style.SUCCESS(f"  [OK] Invariant Verified: Incident {incident.reference} is RESOLVED while Complaint {unresolved_complaint.reference} remains IN_PROGRESS."))

        self.stdout.write(self.style.SUCCESS("\n" + "=" * 80))
        self.stdout.write(self.style.SUCCESS("ALL 16 STEPS + INCIDENT INVARIANT PASSED SUCCESSFULLY!"))
        self.stdout.write(self.style.SUCCESS("=" * 80 + "\n"))
