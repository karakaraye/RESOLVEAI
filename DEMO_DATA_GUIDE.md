# ResolveAI (BIIRS) — Demonstration Data Guide

## 1. Synthetic Financial & Customer Information Notice

> [!IMPORTANT]
> **SYNTHETIC DATA DECLARATION**:  
> All data used within ResolveAI demonstrations, evaluations, and automated tests is **100% synthetic**.  
> - Bank names (e.g. *Apex Commercial Bank*, *First Horizon Bank*) are fictional entities.
> - Customer names, National Identity Numbers (NIN), Bank Verification Numbers (BVN), phone numbers, and email addresses are algorithmically generated test fixtures.
> - Transaction references, switch session IDs, and card PANs (`4111222233334444`) are mock values.
> - Under no circumstances is real banking PII or production financial data ingested.

---

## 2. Test Personas & Access Roles

ResolveAI enforces multi-role Role-Based Access Control (RBAC). The following personas are pre-configured:

| Persona | Username | Role / Department | Permitted Case Actions |
| :--- | :--- | :--- | :--- |
| **Operator** | `operator@bank.test` | Operator / Customer Care | Intake, Review, Add Notes, Assign Case, Forward to Operations, Record Proposed Outcome |
| **Supervisor** | `supervisor@bank.test` | Supervisor / Risk & QA | Maker-Checker Verification, Outcome Approval, Rejection, Case Reopening, Template Approval |
| **Auditor** | `auditor@bank.test` | Compliance Auditor / Audit | Read-only case access, Full audit stream inspection, Compliance reports export |

To switch personas in the frontend, use the dropdown selector in the top-right corner of the application header.

---

## 3. Demonstration Case Catalog

### Case 1: The ATM Dispenser Failure (Primary Demo Hero Case)
- **Reference**: `CMP-2026-0001`
- **Customer**: Adaeze Okonkwo (`CUST-NGN-084920`)
- **Phone**: `+234 801 *** 4567` (Masked for PII compliance)
- **Category**: `CARDS_ATM` | **Subcategory**: `ATM_DISPENSE_ERROR`
- **Disputed Amount**: `50,000 NGN`
- **Incident Link**: `INC-ATM-TIMEOUT` (Victoria Island ATM Cluster)
- **Key Evidence**: Core Switch Journal `TXN-REF-894021` with status `UNCONFIRMED_DISPENSE`.
- **Intended Demo Flow**: Demonstrates full 16-step lifecycle from ingestion to verified resolution.

### Case 2: Interbank NIP Outward Transfer Stuck
- **Reference**: `CMP-2026-0002`
- **Customer**: Babatunde Adeleke (`CUST-NGN-092144`)
- **Category**: `TRANSFERS` | **Subcategory**: `NIP_OUTWARD_FAILED`
- **Disputed Amount**: `150,000 NGN`
- **Incident Link**: `INC-NIP-OUTAGE` (Interbank Switch Gateway Downtime)
- **Key Evidence**: Aggregator Gateway Session Timeout Error Log.
- **Intended Demo Flow**: Demonstrates operational forwarding to Interbank Settlements team and SLA timer countdown.

### Case 3: Suspected Card Clone / POS Fraud
- **Reference**: `CMP-2026-0003`
- **Customer**: Chinedu Eze (`CUST-NGN-073119`)
- **Category**: `FRAUD_SECURITY` | **Subcategory**: `UNAUTHORIZED_TRANSACTION`
- **Disputed Amount**: `85,000 NGN`
- **Priority**: `CRITICAL`
- **Key Evidence**: Geo-location conflict (Card presented physically in London while customer logged in via Lagos IP).
- **Intended Demo Flow**: Demonstrates automated priority escalation and immediate card block workflow.

### Case 4: Power DisCo Prepaid Token API Failure
- **Reference**: `CMP-2026-0004`
- **Customer**: Fatima Mohammed (`CUST-NGN-061802`)
- **Category**: `BILL_PAYMENTS` | **Subcategory**: `UTILITY_PAYMENT_FAILURE`
- **Disputed Amount**: `10,000 NGN`
- **Incident Link**: `INC-DISCO-GATEWAY`
- **Intended Demo Flow**: Demonstrates batch reconciliation and resolution of multiple complaints sharing a single utility outage.

---

## 4. Simulated Operational Teams

ResolveAI routes cases to dedicated receiving teams:

1. **ATM Operations & Field Engineering** (Code: `TEAM-ATM-OPS`)
   - Channel: Webhook / Portal
   - Standard SLA: 4 Hours
2. **Interbank Transfers & Settlements Desk** (Code: `TEAM-NIP-SETTLE`)
   - Channel: Direct Queue
   - Standard SLA: 2 Hours
3. **Fraud & Risk Operations** (Code: `TEAM-FRAUD-RISK`)
   - Channel: Secure Internal Queue
   - Standard SLA: 1 Hour (Priority Escalation)
4. **Merchant & Utility Billing Operations** (Code: `TEAM-BILL-OPS`)
   - Channel: REST API
   - Standard SLA: 8 Hours
