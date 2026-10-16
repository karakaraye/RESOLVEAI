"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import {
  ArrowRight,
  CheckCircle2,
  Clock,
  CreditCard,
  Landmark,
  Mail,
  MessageSquare,
  RefreshCw,
  Send,
  ShieldCheck,
  Smartphone,
  Sparkles,
  Zap,
} from "lucide-react";
import { api } from "@/lib/api/endpoints";
import { useToast } from "./toast";
import { BrandMark } from "./brand-mark";

export type ChannelId = "mobile_app" | "email" | "whatsapp" | "web_portal" | "atm_switch" | "pos_terminal";

interface ChannelConfig {
  id: ChannelId;
  name: string;
  sourceLabel: string;
  icon: typeof Smartphone;
  description: string;
  badge: string;
  accent: string;
}

const CHANNELS: ChannelConfig[] = [
  {
    id: "mobile_app",
    name: "Mobile App",
    sourceLabel: "Apex Bank Mobile App (v4.2)",
    icon: Smartphone,
    description: "Self-service complaint ticket logged from customer's mobile banking app",
    badge: "Most Common",
    accent: "oklch(52% 0.23 26)",
  },
  {
    id: "email",
    name: "Inbound Email",
    sourceLabel: "Email to complaints@apexbank.ng",
    icon: Mail,
    description: "Customer complaint email parsed by RESOLVEIQ intelligent mailbox parser",
    badge: "Automated OCR",
    accent: "oklch(48% 0.18 245)",
  },
  {
    id: "whatsapp",
    name: "WhatsApp Bot",
    sourceLabel: "Apex Bank Verified WhatsApp (+234 800 2739)",
    icon: MessageSquare,
    description: "Conversational dispute & grievance intake via bank's verified WhatsApp bot",
    badge: "Chatbot AI",
    accent: "oklch(55% 0.19 148)",
  },
  {
    id: "web_portal",
    name: "Web Portal",
    sourceLabel: "Online Banking Web Self-Service",
    icon: Landmark,
    description: "Customer dispute form submitted through desktop internet banking portal",
    badge: "Internet Banking",
    accent: "oklch(50% 0.18 200)",
  },
  {
    id: "atm_switch",
    name: "ATM Terminal Alert",
    sourceLabel: "ATM Switch Telemetry / Terminal Auto-Log",
    icon: CreditCard,
    description: "Dispense failure telemetry or direct dispute report logged at ATM terminal",
    badge: "Switch Telemetry",
    accent: "oklch(48% 0.2 45)",
  },
  {
    id: "pos_terminal",
    name: "POS / Agent Desk",
    sourceLabel: "Merchant POS & Branch Ingestion Desk",
    icon: Zap,
    description: "Dispute logged at merchant POS terminal, branch desk, or agency banking point",
    badge: "Merchant & Agent",
    accent: "oklch(46% 0.22 300)",
  },
];

export interface ComplaintCategoryDef {
  code: string;
  label: string;
  badge: string;
  description: string;
  isFinancial: boolean;
  defaultPriority: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  slaHours: number;
  placeholderSummary: string;
  placeholderNarrative: string;
}

export const COMPLAINT_CATEGORIES: ComplaintCategoryDef[] = [
  {
    code: "TRANSFERS",
    label: "Electronic Funds Transfer (NIP / Interbank / Wire)",
    badge: "Leading · Transfers",
    description: "Interbank or intrabank transfer debited without credit to beneficiary, or stuck in pending state",
    isFinancial: true,
    defaultPriority: "HIGH",
    slaHours: 24,
    placeholderSummary: "e.g. ₦50,000 NIP transfer debited but beneficiary not credited after 24h",
    placeholderNarrative: "State recipient bank, beneficiary account name and number, time of transfer, and session ID if available...",
  },
  {
    code: "CARDS_ATM",
    label: "Card, ATM & POS Terminal Disputes",
    badge: "Cards & Hardware",
    description: "ATM cash dispense failure, merchant POS double debit, or declined payment with debit alert",
    isFinancial: true,
    defaultPriority: "HIGH",
    slaHours: 24,
    placeholderSummary: "e.g. ATM debited ₦30,000 without dispensing cash",
    placeholderNarrative: "Specify ATM/POS terminal location, date and time, and if an error receipt was issued...",
  },
  {
    code: "ACCOUNT_ACCESS",
    label: "Account Maintenance, KYC & Restrictions",
    badge: "Account & KYC",
    description: "Account unexpectedly frozen or Post-No-Debit (PND), BVN/NIN linkage issues, or dormant account delay",
    isFinancial: false,
    defaultPriority: "HIGH",
    slaHours: 24,
    placeholderSummary: "e.g. Post-No-Debit restriction placed on business account despite verified documents",
    placeholderNarrative: "Describe when the restriction was noticed, documents submitted to the branch, and branch visited...",
  },
  {
    code: "BILLING",
    label: "Excess Charges & Unexplained Fees",
    badge: "Billing & Fees",
    description: "Unexplained ledger debits, excessive SMS alert charges, electronic transfer levy, or maintenance fee errors",
    isFinancial: true,
    defaultPriority: "MEDIUM",
    slaHours: 48,
    placeholderSummary: "e.g. Account maintenance fee debited three times within the same billing month",
    placeholderNarrative: "Detail the exact charge entries from your statement, dates debited, and why they appear erroneous...",
  },
  {
    code: "FRAUD_SECURITY",
    label: "Fraud, Phishing & Unauthorized Activity",
    badge: "Security & Fraud",
    description: "Unrecognized debit alerts, suspected account takeover, compromised card details, or suspicious phishing activity",
    isFinancial: true,
    defaultPriority: "CRITICAL",
    slaHours: 12,
    placeholderSummary: "e.g. Unauthorized card charge of ₦85,000 received while physical card is with me",
    placeholderNarrative: "State when alerts were received, if you have blocked the card, and any suspicious SMS or calls received...",
  },
  {
    code: "MOBILE_APP",
    label: "Mobile App, Internet Banking & OTP Issues",
    badge: "Digital Channels",
    description: "App login failures, biometric/face ID errors, OTP not delivering, token generator sync issues, or server timeouts",
    isFinancial: false,
    defaultPriority: "MEDIUM",
    slaHours: 24,
    placeholderSummary: "e.g. OTP SMS not delivering, preventing mobile app authorization",
    placeholderNarrative: "Specify your device model, telecom provider (MTN/Airtel/Glo), and the exact error message displayed...",
  },
  {
    code: "LOANS_CREDIT",
    label: "Loan Repayment & Credit Bureau Records",
    badge: "Loans & Credit",
    description: "Loan deduction deducted twice, wrong overdue status on credit bureau (CRC/FirstCentral), or delayed release",
    isFinancial: true,
    defaultPriority: "HIGH",
    slaHours: 48,
    placeholderSummary: "e.g. Monthly loan repayment debited twice from salary account",
    placeholderNarrative: "Provide loan account reference, expected monthly deduction amount, and dates of the duplicated entries...",
  },
  {
    code: "SERVICE_QUALITY",
    label: "Branch Service & Staff Conduct",
    badge: "Branch Service",
    description: "Excessive branch waiting queues, unprofessional customer desk conduct, delayed cheque clearing, or unaddressed queries",
    isFinancial: false,
    defaultPriority: "LOW",
    slaHours: 72,
    placeholderSummary: "e.g. 3-hour delay at branch customer desk with unhelpful assistance for cheque deposit",
    placeholderNarrative: "Specify the exact bank branch location, date, time of visit, and specific service failure encountered...",
  },
];

export function CustomerDisputePortal() {
  const toast = useToast();
  const [activeChannel, setActiveChannel] = useState<ChannelId>("mobile_app");
  const [categoryCode, setCategoryCode] = useState<string>("TRANSFERS");
  const [customerName, setCustomerName] = useState("");
  const [customerPhone, setCustomerPhone] = useState("");
  const [customerEmail, setCustomerEmail] = useState("");
  const [accountNumber, setAccountNumber] = useState("");
  const [amount, setAmount] = useState("");
  const [transactionRef, setTransactionRef] = useState("");
  const [summary, setSummary] = useState("");
  const [narrative, setNarrative] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submittedData, setSubmittedData] = useState<{
    reference: string;
    complaintId: string;
    channel: string;
    categoryLabel: string;
    slaHours: number;
    submittedAt: string;
  } | null>(null);

  const currentChannelConfig = CHANNELS.find((c) => c.id === activeChannel) || CHANNELS[0];
  const currentCategory = COMPLAINT_CATEGORIES.find((c) => c.code === categoryCode) || COMPLAINT_CATEGORIES[0];

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!summary.trim() || !narrative.trim()) {
      toast("Please provide both an issue headline and description.", "error");
      return;
    }

    setSubmitting(true);
    try {
      const priority =
        currentCategory.defaultPriority === "CRITICAL" || (amount && Number(amount) >= 100000)
          ? "CRITICAL"
          : currentCategory.defaultPriority;
      const slaHours = priority === "CRITICAL" ? 12 : currentCategory.slaHours;

      const res = await api.ingestComplaint({
        customerName: customerName.trim() || "Bank Customer",
        customerReference: `CUST-LIVE-${Math.floor(100000 + Math.random() * 900000)}`,
        customerPhone: customerPhone.trim() || "+234 800 000 0000",
        customerEmail: customerEmail.trim() || "customer@apexbank.ng",
        accountNumber: accountNumber.trim() || "0123456789",
        channel: currentChannelConfig.sourceLabel,
        categoryCode: currentCategory.code,
        categoryLabel: currentCategory.label,
        priority,
        summary: summary.trim(),
        narrative: narrative.trim(),
        transactionReference: transactionRef.trim() || undefined,
        amount: amount.trim() || undefined,
        sendAcknowledgement: true,
      });

      // Broadcast to any open operator tabs via BroadcastChannel & CustomEvent
      if (typeof window !== "undefined") {
        try {
          const bc = new BroadcastChannel("resolveiq_live_feed");
          bc.postMessage({
            type: "NEW_COMPLAINT_INGESTED",
            reference: res.reference,
            complaintId: res.complaintId,
            channel: currentChannelConfig.name,
            summary: summary.trim(),
            customerName: customerName.trim() || "Bank Customer",
            amount: amount.trim(),
            timestamp: new Date().toISOString(),
          });
          bc.close();
        } catch {
          // BroadcastChannel fallback handled by storage event
        }
      }

      setSubmittedData({
        reference: res.reference,
        complaintId: res.complaintId,
        channel: currentChannelConfig.name,
        categoryLabel: currentCategory.label,
        slaHours,
        submittedAt: new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
      });

      toast(`Dispute ${res.reference} submitted! Operator desk has received it in real time.`, "success");
    } catch {
      toast("Submission failed. Please check connection and try again.", "error");
    } finally {
      setSubmitting(false);
    }
  };

  const resetForm = () => {
    setSubmittedData(null);
    setCategoryCode("TRANSFERS");
    setSummary("");
    setNarrative("");
    setAmount("");
    setTransactionRef("");
  };

  return (
    <div className="portal-wrapper">
      {/* Top Banking Brand Bar */}
      <header className="portal-topbar">
        <div className="portal-container portal-topbar-inner">
          <div className="portal-brand">
            <BrandMark size={30} />
            <div className="portal-brand-text">
              <strong>Apex Commercial Bank</strong>
              <small className="portal-subtitle-desktop">Customer Resolution &amp; Omnichannel Dispute Gateway</small>
              <small className="portal-subtitle-mobile">Dispute Resolution Gateway</small>
            </div>
          </div>
          <div className="portal-status-badge">
            <span className="live-pulse-dot" />
            <span className="portal-badge-text-desktop">RESOLVEIQ Ingestion: </span>
            <strong>LIVE</strong>
          </div>
        </div>
      </header>

      <main className="portal-main portal-container">
        {submittedData ? (
          /* Success & Real-Time Acknowledgment Screen */
          <div className="portal-success-card">
            <div className="portal-success-header">
              <div className="portal-success-icon">
                <CheckCircle2 size={44} />
              </div>
              <div>
                <span className="portal-success-tag">Dispute Successfully Ingested</span>
                <h2>Complaint Registered with Bank Desk</h2>
                <p>
                  Your incident has been securely transmitted through <strong>{submittedData.channel}</strong> and queued on the central bank resolution desk.
                </p>
              </div>
            </div>

            <div className="portal-receipt-box">
              <div className="portal-receipt-item">
                <span className="receipt-label">Official Tracking Reference</span>
                <span className="receipt-value mono highlight">{submittedData.reference}</span>
              </div>
              <div className="portal-receipt-item">
                <span className="receipt-label">Regulatory Resolution Window</span>
                <span className="receipt-value text-danger">Within {submittedData.slaHours} Hours (CBN Guaranteed)</span>
              </div>
              <div className="portal-receipt-item">
                <span className="receipt-label">Complaint Nature / Category</span>
                <span className="receipt-value">{submittedData.categoryLabel}</span>
              </div>
              <div className="portal-receipt-item">
                <span className="receipt-label">Inbound Channel</span>
                <span className="receipt-value">{submittedData.channel}</span>
              </div>
              <div className="portal-receipt-item">
                <span className="receipt-label">Timestamp</span>
                <span className="receipt-value">{submittedData.submittedAt}</span>
              </div>
            </div>

            {/* Live Progress Tracker */}
            <div className="portal-tracker">
              <h4>Regulatory Resolution Pipeline</h4>
              <ol className="portal-steps">
                <li className="step-done">
                  <div className="step-bubble"><CheckCircle2 size={16} /></div>
                  <div className="step-info">
                    <strong>1. Ingestion &amp; Acknowledgment</strong>
                    <small>Received via {submittedData.channel} &amp; registered</small>
                  </div>
                </li>
                <li className="step-active">
                  <div className="step-bubble"><Sparkles size={16} /></div>
                  <div className="step-info">
                    <strong>2. Automated AI Triage</strong>
                    <small>Classifying complaint fault &amp; routing to operations</small>
                  </div>
                </li>
                <li className="step-pending">
                  <div className="step-bubble"><Clock size={16} /></div>
                  <div className="step-info">
                    <strong>3. Investigation &amp; Resolution</strong>
                    <small>Assigned to dedicated resolution unit</small>
                  </div>
                </li>
              </ol>
            </div>

            {/* Notification Confirmation simulated banner */}
            <div className="portal-notice-card">
              <ShieldCheck size={20} />
              <div>
                <strong>Automated Consumer Notification Dispatched</strong>
                <p>An official regulatory acknowledgement SMS &amp; email confirmation has been sent to your registered contact info.</p>
              </div>
            </div>

            <div className="portal-success-actions">
              <button type="button" onClick={resetForm} className="button button-secondary">
                <RefreshCw size={15} />
                <span>Submit Another Dispute</span>
              </button>
              <Link href={`/complaints`} className="button button-primary">
                <span>View On Central Operator Desk</span>
                <ArrowRight size={15} />
              </Link>
            </div>
          </div>
        ) : (
          /* Intake Form */
          <div className="portal-grid">
            {/* Left: Interactive Channel Selector & Regulatory Assurance */}
            <div className="portal-sidebar-col">
              <div className="portal-panel">
                <div className="portal-panel-head">
                  <Smartphone size={18} />
                  <h3>1. Inbound Touchpoint Channel</h3>
                </div>
                <p className="portal-panel-desc">
                  Select the channel through which this customer complaint was received:
                </p>
                <div className="channel-select-list">
                  {CHANNELS.map((ch) => {
                    const Icon = ch.icon;
                    const isSelected = ch.id === activeChannel;
                    return (
                      <button
                        key={ch.id}
                        type="button"
                        onClick={() => setActiveChannel(ch.id)}
                        className={`channel-btn ${isSelected ? "active" : ""}`}
                      >
                        <div className="channel-icon-wrap" style={{ color: ch.accent }}>
                          <Icon size={20} />
                        </div>
                        <div className="channel-btn-text">
                          <div className="channel-btn-title">
                            <strong>{ch.name}</strong>
                            <span className="channel-badge">{ch.badge}</span>
                          </div>
                          <small>{ch.description}</small>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* CBN Regulatory Compliance & Protections */}
              <div className="portal-panel">
                <div className="portal-panel-head">
                  <ShieldCheck size={18} />
                  <h3>CBN Regulatory Protection</h3>
                </div>
                <p className="portal-panel-desc">
                  All banking grievances logged through verified channels adhere to Central Bank consumer protection directives:
                </p>
                <div className="compliance-features-list">
                  <div className="compliance-feature-item">
                    <span className="compliance-dot" />
                    <div>
                      <strong>Cryptographic Ingestion Hash</strong>
                      <small>Generates an immutable audit reference (CMP-YYYY-XXXX).</small>
                    </div>
                  </div>
                  <div className="compliance-feature-item">
                    <span className="compliance-dot" />
                    <div>
                      <strong>Mandated SLA Clocks</strong>
                      <small>12h for fraud alerts, 24h for transfers/cards, 48-72h for billing &amp; service.</small>
                    </div>
                  </div>
                  <div className="compliance-feature-item">
                    <span className="compliance-dot" />
                    <div>
                      <strong>Maker-Checker Verification</strong>
                      <small>Mandatory supervisor sign-off before any complaint is resolved.</small>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Right: Omnichannel Grievance Intake Form */}
            <div className="portal-form-col">
              <div className="portal-form-card">
                <div className="portal-form-header">
                  <div className="portal-channel-banner">
                    <currentChannelConfig.icon size={22} style={{ color: currentChannelConfig.accent }} />
                    <div>
                      <h3>{currentChannelConfig.name} Ingestion Gateway</h3>
                      <p>{currentChannelConfig.sourceLabel}</p>
                    </div>
                  </div>
                </div>

                <form onSubmit={handleSubmit} className="portal-form-body">
                  {/* 1. Complaint Nature / Category Selection */}
                  <div className="form-section-title">
                    <span>1. Complaint Nature &amp; Classification</span>
                  </div>
                  <div className="portal-category-group">
                    <label className="field">
                      <span className="field-label">Complaint Category *</span>
                      <select
                        value={categoryCode}
                        onChange={(e) => setCategoryCode(e.target.value)}
                        className="field-input field-select"
                        required
                      >
                        {COMPLAINT_CATEGORIES.map((cat) => (
                          <option key={cat.code} value={cat.code}>
                            {cat.label} ({cat.slaHours}h SLA)
                          </option>
                        ))}
                      </select>
                    </label>
                    <div className="category-description-hint">
                      <div className="category-hint-header">
                        <span className="category-badge-pill">{currentCategory.badge}</span>
                        <span className="category-sla-pill">{currentCategory.slaHours}h Regulatory SLA</span>
                      </div>
                      <p>{currentCategory.description}</p>
                    </div>
                  </div>

                  {/* 2. Customer Identity */}
                  <div className="form-section-title" style={{ marginTop: "14px" }}>
                    <span>2. Customer &amp; Account Details</span>
                  </div>
                  <div className="portal-row-2">
                    <label className="field">
                      <span className="field-label">Your Full Name *</span>
                      <input
                        type="text"
                        value={customerName}
                        onChange={(e) => setCustomerName(e.target.value)}
                        placeholder="e.g. Babatunde Adeleke"
                        required
                        className="field-input"
                      />
                    </label>
                    <label className="field">
                      <span className="field-label">Bank Account Number *</span>
                      <input
                        type="text"
                        value={accountNumber}
                        onChange={(e) => setAccountNumber(e.target.value)}
                        placeholder="e.g. 0123456789 (10 digits)"
                        required
                        className="field-input mono"
                      />
                    </label>
                  </div>

                  <div className="portal-row-2">
                    <label className="field">
                      <span className="field-label">Phone Number</span>
                      <input
                        type="tel"
                        value={customerPhone}
                        onChange={(e) => setCustomerPhone(e.target.value)}
                        placeholder="+234 800 000 0000"
                        className="field-input"
                      />
                    </label>
                    <label className="field">
                      <span className="field-label">Email Address</span>
                      <input
                        type="email"
                        value={customerEmail}
                        onChange={(e) => setCustomerEmail(e.target.value)}
                        placeholder="name@email.com"
                        className="field-input"
                      />
                    </label>
                  </div>

                  {/* 3. Transaction Details (Optional / Category Aware) */}
                  <div className="form-section-title" style={{ marginTop: "14px" }}>
                    <span>
                      3. Transaction Particulars{" "}
                      <small className="optional-tag">
                        {currentCategory.isFinancial ? "(Optional if available)" : "(Optional / Only if monetary loss occurred)"}
                      </small>
                    </span>
                  </div>
                  <div className="portal-row-2">
                    <label className="field">
                      <span className="field-label">
                        {currentCategory.isFinancial ? "Disputed Amount (NGN ₦)" : "Associated Amount (NGN ₦)"}
                      </span>
                      <input
                        type="number"
                        value={amount}
                        onChange={(e) => setAmount(e.target.value)}
                        placeholder={currentCategory.isFinancial ? "e.g. 50000 (Optional)" : "Leave blank if not applicable"}
                        className="field-input mono"
                      />
                    </label>
                    <label className="field">
                      <span className="field-label">
                        {currentCategory.isFinancial ? "Session ID / Transaction Ref" : "Reference / Ticket Number"}
                      </span>
                      <input
                        type="text"
                        value={transactionRef}
                        onChange={(e) => setTransactionRef(e.target.value)}
                        placeholder={currentCategory.isFinancial ? "e.g. NIP-990023 or ATM-VI-004" : "e.g. Branch ticket or Loan Ref"}
                        className="field-input mono"
                      />
                    </label>
                  </div>

                  {/* 4. Narrative */}
                  <div className="form-section-title" style={{ marginTop: "14px" }}>
                    <span>4. Complaint Narrative</span>
                  </div>
                  <label className="field">
                    <span className="field-label">Issue Headline / Subject *</span>
                    <input
                      type="text"
                      value={summary}
                      onChange={(e) => setSummary(e.target.value)}
                      placeholder={currentCategory.placeholderSummary}
                      required
                      className="field-input"
                    />
                  </label>

                  <label className="field">
                    <span className="field-label">Detailed Description of What Happened *</span>
                    <textarea
                      rows={4}
                      value={narrative}
                      onChange={(e) => setNarrative(e.target.value)}
                      placeholder={currentCategory.placeholderNarrative}
                      required
                      className="field-input field-textarea"
                    />
                  </label>

                  <div className="portal-submit-row">
                    <div className="portal-submit-note">
                      <ShieldCheck size={16} />
                      <span>Transmitted directly to central RESOLVEIQ real-time ingestion queue</span>
                    </div>
                    <button
                      type="submit"
                      disabled={submitting}
                      className="button button-primary portal-submit-btn"
                    >
                      {submitting ? (
                        <>
                          <RefreshCw size={16} className="spin" />
                          <span>Ingesting to Bank Desk...</span>
                        </>
                      ) : (
                        <>
                          <Send size={16} />
                          <span>Submit Grievance via {currentChannelConfig.name}</span>
                        </>
                      )}
                    </button>
                  </div>
                </form>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
