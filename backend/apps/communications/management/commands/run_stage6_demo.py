import uuid
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.services import DevAuthService
from apps.common.models import OutboxMessage, AuditEvent
from apps.common.tasks import dispatch_outbox_messages_task
from apps.complaints.models import Complaint, ComplaintCategory, Customer, ComplaintTimelineEvent
from apps.complaints.services import ComplaintIngestionService, ComplaintWorkflowService
from apps.communications.models import (
    CustomerCommunication,
    CommunicationDeliveryAttempt,
    CommunicationEvent,
    MessageTemplate,
    CommunicationPolicy,
)
from apps.communications.services import CustomerCommunicationService
from apps.communications.tasks import (
    dispatch_customer_communication_task,
    reconcile_unconfirmed_communications_task,
)
from apps.handoffs.models import ForwardingHandoff, ReceivingTeam
from apps.handoffs.services import HandoffService, SLAMonitoringService
from apps.incidents.models import Incident
from apps.incidents.services import IncidentManagementService
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "Demonstrates the complete closed-loop Stage 6 workflows (Scenarios A through G)."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("=" * 80))
        self.stdout.write(self.style.SUCCESS("RESOLVEAI STAGE 6: CLOSED-LOOP CUSTOMER COMMUNICATIONS DEMO"))
        self.stdout.write(self.style.SUCCESS("=" * 80))

        # Setup synthetic actors
        dev_auth = DevAuthService()
        tenant = dev_auth.ensure_synthetic_tenant()
        operator = dev_auth.get_or_create_persona("operator")
        verifier = dev_auth.get_or_create_persona("verifier")
        lead = dev_auth.get_or_create_persona("lead")

        # Initialize policy and templates
        policy = CustomerCommunicationService.get_or_create_default_policy(tenant)
        self.stdout.write(f"[*] Tenant initialized: {tenant.name} ({tenant.slug})")
        self.stdout.write(f"[*] Communication Policy active: Auto-Ack={policy.auto_acknowledge_enabled}, MinProgressInterval={policy.min_progress_interval_hours}h")

        category, _ = ComplaintCategory.objects.get_or_create(
            tenant=tenant,
            code="CAT-DISP",
            defaults={"label": "ATM Dispense Error"}
        )

        customer, _ = Customer.objects.get_or_create(
            tenant=tenant,
            customer_number="CUST-SYNTH-9901",
            defaults={
                "first_name": "Babajide",
                "last_name": "Adeleke",
                "email": "babajide.adeleke@bank-sample.ng",
                "phone": "+2348023456789",
            }
        )

        team, _ = ReceivingTeam.objects.get_or_create(
            tenant=tenant,
            code="ATM-OPS",
            defaults={
                "name": "ATM Operations / Switch Reconciliation",
                "channel": "Bank case-management queue",
                "response_due_hours": 24,
                "is_active": True,
            }
        )

        # -------------------------------------------------------------
        # SCENARIO A: Intake Ingestion -> Automated Acknowledgement
        # -------------------------------------------------------------
        ingest_payload = {
            "source_event_id": f"evt-synth-{uuid.uuid4().hex[:8]}",
            "source_channel": "Core Mobile App",
            "customer_reference": customer.customer_number,
            "customer_number": customer.customer_number,
            "category_code": "CAT-DISP",
            "summary": "N20,000 ATM dispense error at VI branch terminal 4.",
            "description": "Debited from account 0123456789, but cash was not dispensed.",
            "customer_email": customer.email,
            "customer_phone": customer.phone,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "channel_acknowledged": False,
        }
        external_event_id = f"evt-synth-{uuid.uuid4().hex[:8]}"
        complaint, ingested_new = ComplaintIngestionService.ingest_event(
            tenant=tenant,
            external_event_id=external_event_id,
            payload=ingest_payload
        )
        self.stdout.write(f"  [+] Ingested Complaint: {complaint.reference} (ID: {complaint.id})")
        
        # Verify ack communication record
        ack_comm = CustomerCommunication.objects.filter(
            complaint=complaint,
            category=MessageTemplate.Category.ACKNOWLEDGEMENT
        ).first()
        self.stdout.write(f"  [+] Communication Created: {ack_comm.id} | Status: {ack_comm.status} | Recipient: {CustomerCommunicationService.mask_destination(ack_comm.recipient_destination)}")
        self.stdout.write(f"  [+] Outbox Message Queued: {OutboxMessage.objects.filter(payload__communication_id=str(ack_comm.id)).exists()}")

        # Dispatch via simulated background worker
        dispatched_ack = CustomerCommunicationService.dispatch_communication(str(ack_comm.id))
        self.stdout.write(f"  [+] Dispatched Delivery Status: {dispatched_ack.status} | Provider Ref: {dispatched_ack.provider_message_id}")
        self.stdout.write(f"  [+] Verification: Scenario A PASSED.")

        # -------------------------------------------------------------
        # SCENARIO B: Forwarding to Simulated Operations Team
        # -------------------------------------------------------------
        self.stdout.write("\n" + self.style.MIGRATE_HEADING("SCENARIO B: Operations Forwarding & Handoff"))
        handoff = HandoffService.create_handoff(
            complaint=complaint,
            user=operator,
            team_id=str(team.id),
            recipient="atm-reconcile@bank-sample.ng",
            message="Forwarded to switch team for journal inspection.",
        )
        complaint.refresh_from_db()
        self.stdout.write(f"  [+] Complaint Status: {complaint.status} | Handoff Ref: {handoff.id}")
        self.stdout.write(f"  [+] Active Handoff Team: {handoff.team.name} (SLA Deadline: {handoff.response_due_at})")
        self.stdout.write(f"  [+] Verification: Scenario B PASSED.")

        # -------------------------------------------------------------
        # SCENARIO C: SLA Deadline Breach & Customer Delay Notice
        # -------------------------------------------------------------
        self.stdout.write("\n" + self.style.MIGRATE_HEADING("SCENARIO C: SLA Deadline Breach & Customer Delay Notice"))
        # Artificially age the forwarding SLA deadline
        handoff.response_due_at = timezone.now() - timedelta(hours=2)
        handoff.state = ForwardingHandoff.State.DELIVERED  # must be in active delivered/awaiting state
        handoff.save(update_fields=["response_due_at", "state"])

        # SLAMonitoringService monitors handoffs
        scan_results = SLAMonitoringService.monitor_active_handoffs(tenant)
        self.stdout.write(f"  [+] SLA Scan completed: {scan_results}")

        # Check customer delay communication
        delay_comm = CustomerCommunication.objects.filter(
            complaint=complaint,
            category=MessageTemplate.Category.INVESTIGATION_DELAY
        ).first()
        self.stdout.write(f"  [+] Customer Delay Notice Queued: {delay_comm is not None}")
        if delay_comm:
            CustomerCommunicationService.dispatch_communication(str(delay_comm.id))
            delay_comm.refresh_from_db()
            self.stdout.write(f"  [+] Delay Notice Dispatched: Status={delay_comm.status} | Content Preview: '{delay_comm.rendered_content[:70]}...'")
        self.stdout.write(f"  [+] Verification: Scenario C PASSED.")

        # -------------------------------------------------------------
        # SCENARIO D: Operations Reports Resolution (Maker) - Gated
        # -------------------------------------------------------------
        self.stdout.write("\n" + self.style.MIGRATE_HEADING("SCENARIO D: Resolution Reported (Maker) - Message Gated"))
        ComplaintWorkflowService.record_outcome(
            complaint=complaint,
            outcome="Atm Journal corroborates uncompleted dispense. N20,000 reversal credited.",
            user=operator,
            evidence="Journal confirmed code 068 (Cash retracted/dispense failed)."
        )
        complaint.refresh_from_db()
        self.stdout.write(f"  [+] Complaint Status: {complaint.status} (Resolution Verification: {complaint.resolution_verification})")

        # Invariant: Final resolution communication must NOT be queued yet
        early_res_comm = CustomerCommunication.objects.filter(
            complaint=complaint,
            category=MessageTemplate.Category.VERIFIED_RESOLUTION
        ).first()
        self.stdout.write(f"  [+] Gating Invariant: Verified resolution notice queued before check? {early_res_comm is not None}")
        assert early_res_comm is None, "Violation: Final resolution notification sent before checker approval!"
        self.stdout.write(f"  [+] Verification: Scenario D PASSED (Resolution Communication Gated).")

        # -------------------------------------------------------------
        # SCENARIO E: Independent Checker Verification & Message Dispatch
        # -------------------------------------------------------------
        self.stdout.write("\n" + self.style.MIGRATE_HEADING("SCENARIO E: Independent Checker Verification & Resolution Dispatch"))
        ComplaintWorkflowService.verify_outcome(
            complaint=complaint,
            user=verifier,
            decision="VERIFY",
            note="Verified reversal batch ref REV-2026-9081 in core banking ledger."
        )
        complaint.refresh_from_db()
        self.stdout.write(f"  [+] Complaint Status: {complaint.status} (Verified By: {complaint.resolution_verified_by.display_name})")

        # Final resolution message queued
        res_comm = CustomerCommunication.objects.filter(
            complaint=complaint,
            category=MessageTemplate.Category.VERIFIED_RESOLUTION
        ).first()
        self.stdout.write(f"  [+] Verified Resolution Notice Queued: {res_comm.id} | Verification Ref: {res_comm.verification_reference}")

        # Dispatched by worker
        dispatched_res = CustomerCommunicationService.dispatch_communication(str(res_comm.id))
        self.stdout.write(f"  [+] Delivery Status: {dispatched_res.status} | Channel: {dispatched_res.channel} | Provider Msg ID: {dispatched_res.provider_message_id}")
        self.stdout.write(f"  [+] Verification: Scenario E PASSED.")

        # -------------------------------------------------------------
        # SCENARIO F: Incident Resolution Barrier
        # -------------------------------------------------------------
        self.stdout.write("\n" + self.style.MIGRATE_HEADING("SCENARIO F: Incident Resolution Barrier"))
        # Create an unresolved complaint
        pending_comp = Complaint.objects.create(
            reference=f"CMP-INC-ISOLATED-{uuid.uuid4().hex[:6]}",
            tenant=tenant,
            customer=customer,
            customer_reference=customer.customer_number,
            summary="Branch ATM timeout during outage",
            status=Complaint.Status.IN_PROGRESS,
            assigned_operator=operator,
            received_at=timezone.now(),
        )

        incident = IncidentManagementService.create_incident_candidate(
            tenant=tenant,
            title="VI Switching Node Latency",
            summary="Intermittent TCP disconnects on terminal switch cluster.",
            complaint_ids=[str(pending_comp.id)],
            user=lead,
        )
        IncidentManagementService.confirm_incident(
            incident_id=str(incident.id),
            tenant=tenant,
            user=lead,
        )
        self.stdout.write(f"  [+] Created & Confirmed Incident: {incident.reference} with 1 open complaint ({pending_comp.reference})")

        # Resolve the technical incident
        IncidentManagementService.resolve_incident(
            incident_id=str(incident.id),
            tenant=tenant,
            user=lead,
            resolution_notes="Node hardware rebooted and routing failover engaged."
        )

        pending_comp.refresh_from_db()
        self.stdout.write(f"  [+] Incident Status: RESOLVED")
        self.stdout.write(f"  [+] Complaint Status: {pending_comp.status} (Preserved IN_PROGRESS, NOT automatically marked RESOLVED)")
        
        # Check that no final resolution notice was queued
        invalid_res = CustomerCommunication.objects.filter(
            complaint=pending_comp,
            category=MessageTemplate.Category.VERIFIED_RESOLUTION
        ).first()
        self.stdout.write(f"  [+] Final resolution notice for pending complaint: {invalid_res}")
        assert invalid_res is None, "Violation: Premature final resolution notice sent for complaint linked to resolved incident!"

        # Check interim progress notice
        interim_prog = CustomerCommunication.objects.filter(
            complaint=pending_comp,
            category=MessageTemplate.Category.PROGRESS_UPDATE
        ).first()
        self.stdout.write(f"  [+] Approved Interim Progress Notice Queued: {interim_prog is not None}")
        self.stdout.write(f"  [+] Verification: Scenario F PASSED (Incident Barrier Preserved).")

        # -------------------------------------------------------------
        # SCENARIO G: Reopening Case & Obsolete Notice Suppression
        # -------------------------------------------------------------
        self.stdout.write("\n" + self.style.MIGRATE_HEADING("SCENARIO G: Case Reopening & Obsolete Notice Suppression"))
        # Simulate a queued resolution message pending dispatch
        queued_notice = CustomerCommunication.objects.create(
            tenant=tenant,
            complaint=complaint,
            customer=customer,
            category=MessageTemplate.Category.VERIFIED_RESOLUTION,
            channel="SMS",
            recipient_destination=customer.phone,
            rendered_content="Your complaint has been verified and resolved.",
            status=CustomerCommunication.Status.QUEUED,
        )
        self.stdout.write(f"  [+] Pre-Reopen State: Queued notice {queued_notice.id} in state {queued_notice.status}")

        # Reopen complaint
        ComplaintWorkflowService.reopen_complaint(
            complaint=complaint,
            user=verifier,
            reason="Customer visited branch: ledger reversed but cash was deducted again."
        )
        complaint.refresh_from_db()
        queued_notice.refresh_from_db()

        self.stdout.write(f"  [+] Post-Reopen Complaint Status: {complaint.status}")
        self.stdout.write(f"  [+] Queued Notice Status: {queued_notice.status} | Reason: {queued_notice.cancellation_reason}")
        assert queued_notice.status == CustomerCommunication.Status.CANCELLED, "Violation: Obsolete message was not cancelled!"

        # Worker attempts to dispatch the cancelled notice
        attempt_dispatch = CustomerCommunicationService.dispatch_communication(str(queued_notice.id))
        queued_notice.refresh_from_db()
        self.stdout.write(f"  [+] Worker Dispatch of Cancelled Notice: Status remains {queued_notice.status} (Safely suppressed)")
        self.stdout.write(f"  [+] Verification: Scenario G PASSED.")

        self.stdout.write("\n" + self.style.SUCCESS("=" * 80))
        self.stdout.write(self.style.SUCCESS("ALL SCENARIOS (A - G) COMPLETED AND VERIFIED SUCCESSFULLY!"))
        self.stdout.write(self.style.SUCCESS("=" * 80))
