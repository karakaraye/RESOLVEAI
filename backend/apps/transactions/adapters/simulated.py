import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from .base import BankSystemAdapter

logger = logging.getLogger("resolveai.transactions")


class SimulatedBankAdapter(BankSystemAdapter):
    """
    High-fidelity simulated banking adapter for BIIRS.
    Simulates three distinct banking enterprise environments:
      1. Core Banking Ledger (Finacle Core Ledger)
      2. Instant Payment Switch (NIBSS Instant Payments - NIP)
      3. Card Management & Processing Switch (Interswitch / Postilion)

    Includes deterministic synthetic transaction records, realistic ledger
    conflicts, and evidence provenance payloads.

    IMPORTANT SAFETY GUARANTEE:
    This adapter performs only read-only simulation queries.
    It never moves funds or issues live reversals.
    """

    # Realistic synthetic ledger data catalog
    SYNTHETIC_ACCOUNTS = {
        "0123456789": {
            "account_number": "0123456789",
            "account_name": "Amina Bello",
            "account_type": "SAVINGS",
            "currency": "NGN",
            "status": "ACTIVE",
            "bvn": "22334455667",
            "branch": "Victoria Island Main",
            "kyc_level": 3,
        },
        "0987654321": {
            "account_number": "0987654321",
            "account_name": "Chidi Okonkwo",
            "account_type": "CURRENT",
            "currency": "NGN",
            "status": "ACTIVE",
            "bvn": "22446688001",
            "branch": "Lekki Admiralty",
            "kyc_level": 3,
        },
        "0311223344": {
            "account_number": "0311223344",
            "account_name": "Babajide Williams",
            "account_type": "SALARY_SAVINGS",
            "currency": "NGN",
            "status": "ACTIVE",
            "bvn": "22998877665",
            "branch": "Marina Commercial",
            "kyc_level": 3,
        },
        "0556677889": {
            "account_number": "0556677889",
            "account_name": "Apex Logistics Ltd",
            "account_type": "CORPORATE",
            "currency": "NGN",
            "status": "ACTIVE",
            "bvn": "22113355779",
            "branch": "Ikeja Corporate Banking",
            "kyc_level": 3,
        },
    }

    SYNTHETIC_TRANSACTIONS = [
        # 1. NIP Transfer Discrepancy (Amina Bello: Debited in core; Pending in NIBSS)
        {
            "reference": "TXN-TEST-90311",
            "session_id": "999014261012142231001",
            "account_number": "0123456789",
            "source_system": "Core banking (Finacle)",
            "amount_value": Decimal("50000.00"),
            "amount_currency": "NGN",
            "occurred_at": "2026-10-12T14:22:31Z",
            "status_label": "Debited",
            "status": "AVAILABLE",
            "last_updated_at": "2026-10-14T08:00:00Z",
            "conflict": "Core banking shows DEBITED; switch shows PENDING (Session 999014261012142231001 inward credit unconfirmed). No final outcome is assumed.",
            "match_evidence": "Account 0123456789, amount ₦50,000.00, and timestamp matching customer transfer grievance.",
            "raw_payload": {
                "journal_number": "JRN-FIN-20261012-9844",
                "narration": "NIP/ZENITH/BASHIR BELLO/OUTWARD TRF",
                "beneficiary_account": "2044810022",
                "beneficiary_bank": "057",
                "beneficiary_bank_name": "Zenith Bank Plc",
                "channel": "MOBILE_BANKING",
                "response_code": "00",
                "core_status": "POSTED",
                "switch_status": "PENDING",
            },
        },
        # 2. Switch Inward Status for Session 999014261012142231001
        {
            "reference": "NIP-SES-999014261012",
            "session_id": "999014261012142231001",
            "account_number": "0123456789",
            "source_system": "Instant payment switch (NIBSS)",
            "amount_value": Decimal("50000.00"),
            "amount_currency": "NGN",
            "occurred_at": "2026-10-12T14:22:32Z",
            "status_label": "Switch Pending",
            "status": "STALE",
            "last_updated_at": "2026-10-12T15:30:00Z",
            "conflict": "NIBSS switch response delayed over 48 hours; destination bank credit unacknowledged. No final outcome is assumed.",
            "match_evidence": "Exact NIP session ID 999014261012142231001 match.",
            "raw_payload": {
                "nip_session_id": "999014261012142231001",
                "originating_bank": "044",
                "destination_bank": "057",
                "switch_timestamp": "2026-10-12T14:22:32.410Z",
                "switch_state": "AWAITING_BENEFICIARY_ACK",
                "retry_count": 3,
            },
        },
        # 3. ATM Hardware Dispense Error (Chidi Okonkwo: Debited without cash)
        {
            "reference": "ATM-JRNL-8402",
            "session_id": "ATM-VI2-20261013-0844",
            "account_number": "0987654321",
            "source_system": "Core banking (Finacle)",
            "amount_value": Decimal("20000.00"),
            "amount_currency": "NGN",
            "occurred_at": "2026-10-13T20:15:10Z",
            "status_label": "Debited",
            "status": "AVAILABLE",
            "last_updated_at": "2026-10-14T07:15:00Z",
            "conflict": "Core banking ledger debited ₦20,000; ATM journal reports hardware sensor timeout on bill presenter. No automatic reversal logged.",
            "match_evidence": "Card withdrawal at Victoria Island ATM 2 matching account 0987654321.",
            "raw_payload": {
                "terminal_id": "ATM-VI-02",
                "terminal_location": "Victoria Island Branch Lobby",
                "stan": "881204",
                "auth_code": "AT8402",
                "hardware_error": "BILL_PRESENTER_PICK_FAILURE_CODE_42",
                "cassette_notes_deducted": 0,
                "ledger_status": "DEBITED",
            },
        },
        # 4. International Web Card Subscription Double Charge
        {
            "reference": "CRD-TXN-771092",
            "session_id": "STAN-771092",
            "account_number": "0123456789",
            "source_system": "Card management system",
            "amount_value": Decimal("68450.00"),
            "amount_currency": "NGN",
            "occurred_at": "2026-10-13T10:05:00Z",
            "status_label": "Settled",
            "status": "AVAILABLE",
            "last_updated_at": "2026-10-14T02:00:00Z",
            "conflict": "Two identical authorization requests received within 1.2 seconds from merchant gateway. Second debit settled without reversal.",
            "match_evidence": "Card PAN ending in 1234, international merchant ID 'CLOUD_HOST_US'.",
            "raw_payload": {
                "masked_pan": "539941******1234",
                "stan": "771092",
                "rrn": "428901771092",
                "merchant_name": "CloudServices Inc.",
                "merchant_country": "USA",
                "auth_currency": "USD",
                "auth_amount": "45.00",
                "fx_rate": "1521.11",
                "iso_response": "00",
            },
        },
        # 5. Erroneous Maintenance Charge
        {
            "reference": "FEE-20261014-0012",
            "session_id": "FEE-BATCH-1014",
            "account_number": "0311223344",
            "source_system": "Core banking (Finacle)",
            "amount_value": Decimal("3500.00"),
            "amount_currency": "NGN",
            "occurred_at": "2026-10-14T01:00:00Z",
            "status_label": "Debited",
            "status": "AVAILABLE",
            "last_updated_at": "2026-10-14T06:00:00Z",
            "conflict": "Account has salary exemption waiver on record; batch job applied standard commercial account fee.",
            "match_evidence": "Automated monthly ledger maintenance charge on salary account 0311223344.",
            "raw_payload": {
                "batch_id": "BATCH-FEE-2026-M10",
                "fee_code": "MNT_FEE_CORP",
                "exception_flag": True,
                "waiver_id": "WVR-SAL-9941",
            },
        },
        # 6. Corporate Payroll Batch Timeout
        {
            "reference": "CORP-PAY-998201",
            "session_id": "PAYROLL-2026-OCT",
            "account_number": "0556677889",
            "source_system": "Core banking (Finacle)",
            "amount_value": Decimal("12450000.00"),
            "amount_currency": "NGN",
            "occurred_at": "2026-10-13T17:00:00Z",
            "status_label": "Processing Timeout",
            "status": "STALE",
            "last_updated_at": "2026-10-13T19:00:00Z",
            "conflict": "Master corporate debit posted (₦12,450,000); 45 of 120 employee beneficiary credits timed out at clearing switch. No final outcome is assumed.",
            "match_evidence": "Corporate salary disbursement batch #PAYROLL-2026-OCT.",
            "raw_payload": {
                "batch_reference": "CORP-PAY-998201",
                "total_records": 120,
                "processed_records": 75,
                "pending_records": 45,
                "total_debited": "12450000.00",
                "total_disbursed": "7781250.00",
                "held_balance": "4668750.00",
            },
        },
    ]

    def fetch_account(self, account_number: str) -> dict[str, Any] | None:
        """Fetches masked customer account metadata and status."""
        logger.info(f"[SIMULATED_BANK] Querying account: {account_number}")
        account = self.SYNTHETIC_ACCOUNTS.get(account_number)
        if not account:
            # Fallback dynamic mock for unknown accounts
            return {
                "account_number": account_number,
                "account_name": f"Customer {account_number[-4:]}",
                "account_type": "SAVINGS",
                "currency": "NGN",
                "status": "ACTIVE",
                "bvn": "22000000000",
                "branch": "Head Office",
                "kyc_level": 2,
            }
        return account

    def fetch_transactions(
        self,
        account_number: str | None = None,
        reference: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """
        Queries ledger entries for an account or specific reference.
        Filters by account or reference when supplied.
        """
        logger.info(
            f"[SIMULATED_BANK] Searching transactions: account={account_number}, reference={reference}"
        )
        results = []
        for txn in self.SYNTHETIC_TRANSACTIONS:
            # Match by reference
            if reference and reference.lower() in txn["reference"].lower():
                results.append(txn)
                continue

            # Match by account
            if account_number and txn.get("account_number") == account_number:
                results.append(txn)
                continue

        # If searching for an unknown account/reference, generate a deterministic synthetic record
        if not results and account_number:
            dynamic_ref = f"TXN-SIM-{account_number[-4:]}-{datetime.now(timezone.utc).strftime('%H%M%S')}"
            results.append({
                "reference": dynamic_ref,
                "session_id": f"SES-{dynamic_ref}",
                "account_number": account_number,
                "source_system": "Core banking (Finacle)",
                "amount_value": Decimal("15000.00"),
                "amount_currency": "NGN",
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "status_label": "Debited",
                "status": "AVAILABLE",
                "last_updated_at": datetime.now(timezone.utc).isoformat(),
                "conflict": None,
                "match_evidence": f"Matched by customer account {account_number} within active ledger window.",
                "raw_payload": {
                    "account_number": account_number,
                    "journal": f"JRN-{dynamic_ref}",
                    "channel": "ONLINE",
                    "status": "COMPLETED",
                },
            })

        return results

    def check_switch_status(
        self,
        session_id: str | None = None,
        rrn: str | None = None,
        stan: str | None = None,
    ) -> dict[str, Any] | None:
        """Queries electronic payment switch session state."""
        logger.info(
            f"[SIMULATED_BANK] Querying switch: session_id={session_id}, rrn={rrn}, stan={stan}"
        )
        for txn in self.SYNTHETIC_TRANSACTIONS:
            if session_id and txn.get("session_id") == session_id:
                return {
                    "session_id": session_id,
                    "reference": txn["reference"],
                    "status_label": txn["status_label"],
                    "conflict": txn.get("conflict"),
                    "raw_payload": txn.get("raw_payload", {}),
                    "last_updated_at": txn.get("last_updated_at"),
                }
        return {
            "session_id": session_id or "UNKNOWN",
            "status_label": "SWITCH_OFFLINE_OR_NOT_FOUND",
            "conflict": "No switch trace record found for this session reference.",
            "raw_payload": {},
            "last_updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def fetch_reversal_logs(self, reference: str) -> list[dict[str, Any]]:
        """Queries reversal journal entries related to a transaction."""
        logger.info(f"[SIMULATED_BANK] Checking reversal logs for: {reference}")
        # Default: no automatic reversal was recorded for synthetic discrepancy cases
        return []
