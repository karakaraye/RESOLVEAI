"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import {
  AlertCircle,
  ArrowRight,
  Bot,
  CheckCircle2,
  Clock,
  CreditCard,
  ExternalLink,
  HelpCircle,
  Landmark,
  Mail,
  MessageSquare,
  Phone,
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
    description: "In-app self-service dispute ticket from retail mobile banking app",
    badge: "Most Common",
    accent: "oklch(52% 0.23 26)",
  },
  {
    id: "email",
    name: "Inbound Email",
    sourceLabel: "Email to complaints@apexbank.ng",
    icon: Mail,
    description: "Inbound email parsed by RESOLVEIQ intelligent OCR & mail parser",
    badge: "Automated OCR",
    accent: "oklch(48% 0.18 245)",
  },
  {
    id: "whatsapp",
    name: "WhatsApp Bot",
    sourceLabel: "Apex Bank Verified WhatsApp (+234 800 2739)",
    icon: MessageSquare,
    description: "Conversational dispute intake via bank's verified WhatsApp business bot",
    badge: "Chatbot AI",
    accent: "oklch(55% 0.19 148)",
  },
  {
    id: "web_portal",
    name: "Web Portal",
    sourceLabel: "Online Banking Web Self-Service",
    icon: Landmark,
    description: "Consumer dispute form submitted through desktop internet banking",
    badge: "Internet Banking",
    accent: "oklch(50% 0.18 200)",
  },
  {
    id: "atm_switch",
    name: "ATM Terminal Alert",
    sourceLabel: "ATM Switch Telemetry / Terminal Auto-Log",
    icon: CreditCard,
    description: "Automated failure signal from Interswitch / Postilion cash dispenser sensor",
    badge: "Switch Telemetry",
    accent: "oklch(48% 0.2 45)",
  },
  {
    id: "pos_terminal",
    name: "POS Terminal",
    sourceLabel: "Merchant POS Settlement Dispute",
    icon: Zap,
    description: "Cardholder dispute logged from merchant POS double debit receipt",
    badge: "Merchant Terminal",
    accent: "oklch(46% 0.22 300)",
  },
];

interface QuickScenario {
  label: string;
  channel: ChannelId;
  categoryCode: string;
  priority: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  customerName: string;
  customerPhone: string;
  customerEmail: string;
  accountNumber: string;
  amount: string;
  transactionRef: string;
  summary: string;
  narrative: string;
  slaHours: number;
}

const QUICK_SCENARIOS: QuickScenario[] = [
  {
    label: "🏧 ATM Failed (₦50,000 Cash Dispense Failure)",
    channel: "mobile_app",
    categoryCode: "CARDS_ATM",
    priority: "CRITICAL",
    customerName: "Judge Adaeze Okonkwo",
    customerPhone: "+234 803 456 7890",
    customerEmail: "adaeze.judge@hackathon.ng",
    accountNumber: "0123456789",
    amount: "50000",
    transactionRef: "ATM-VI-004-DISP-991",
    summary: "ATM Cash Dispense Failure: ₦50,000 debited without cash disbursement",
    narrative: "Attempted to withdraw ₦50,000 at Victoria Island Branch ATM 4. Machine counted notes, made mechanical clicking sound, but shutter did not open. Account was debited immediately with SMS alert received.",
    slaHours: 24,
  },
  {
    label: "💸 Stuck NIP Transfer (₦250,000 Interbank Wire)",
    channel: "email",
    categoryCode: "TRANSFERS",
    priority: "HIGH",
    customerName: "Judge Babatunde Adeleke",
    customerPhone: "+234 802 345 6789",
    customerEmail: "babatunde.judge@hackathon.ng",
    accountNumber: "0234567890",
    amount: "250000",
    transactionRef: "NIP-990023412984-ZENITH-GTB",
    summary: "NIP Transfer of ₦250,000 debited but beneficiary not credited after 6 hours",
    narrative: "Initiated an urgent interbank transfer of ₦250,000 to GTBank beneficiary. Sender account was debited, transaction status is stuck in PENDING on NIBSS switch. Beneficiary bank confirmed non-receipt.",
    slaHours: 24,
  },
  {
    label: "💬 WhatsApp Bot: POS Double Debit (₦18,500)",
    channel: "whatsapp",
    categoryCode: "CARDS_ATM",
    priority: "MEDIUM",
    customerName: "Judge Chinedu Eze",
    customerPhone: "+234 807 890 1234",
    customerEmail: "chinedu.judge@hackathon.ng",
    accountNumber: "0345678901",
    amount: "18500",
    transactionRef: "POS-STANBIC-SPAR-7721",
    summary: "POS Double Debit at Supermarket: ₦18,500 charged twice for single grocery purchase",
    narrative: "First attempt at merchant POS showed 'Issuer Timeout / Declined', cashier asked me to swipe again. Second attempt succeeded, but checking my bank alert both transactions of ₦18,500 were debited.",
    slaHours: 48,
  },
  {
    label: "⚠️ Unauthorized Debit Alert (₦120,000 Online Charge)",
    channel: "web_portal",
    categoryCode: "FRAUD_SECURITY",
    priority: "CRITICAL",
    customerName: "Judge Fatima Aliyu",
    customerPhone: "+234 809 123 4567",
    customerEmail: "fatima.judge@hackathon.ng",
    accountNumber: "0456789012",
    amount: "120000",
    transactionRef: "WEB-PAYSTACK-EXT-44219",
    summary: "Suspected Unauthorized Card Transaction: ₦120,000 international charge without OTP",
    narrative: "Received SMS notification for ₦120,000 debit from an unknown online merchant while my physical card was inside my wallet. I did not receive or authorize any 2FA/OTP prompt.",
    slaHours: 12,
  },
];

export function CustomerDisputePortal() {
  const toast = useToast();
  const [activeChannel, setActiveChannel] = useState<ChannelId>("mobile_app");
  const [customerName, setCustomerName] = useState("");
  const [customerPhone, setCustomerPhone] = useState("");
  const [customerEmail, setCustomerEmail] = useState("");
  const [accountNumber, setAccountNumber] = useState("");
  const [amount, setAmount] = useState("");
  const [transactionRef, setTransactionRef] = useState("");
  const [summary, setSummary] = useState("");
  const [narrative, setNarrative] = useState("");
  const [categoryCode, setCategoryCode] = useState("CARDS_ATM");
  const [submitting, setSubmitting] = useState(false);
  const [submittedData, setSubmittedData] = useState<{
    reference: string;
    complaintId: string;
    channel: string;
    slaHours: number;
    submittedAt: string;
  } | null>(null);

  const currentChannelConfig = CHANNELS.find((c) => c.id === activeChannel) || CHANNELS[0];

  const applyScenario = (sc: QuickScenario) => {
    setActiveChannel(sc.channel);
    setCategoryCode(sc.categoryCode);
    setCustomerName(sc.customerName);
    setCustomerPhone(sc.customerPhone);
    setCustomerEmail(sc.customerEmail);
    setAccountNumber(sc.accountNumber);
    setAmount(sc.amount);
    setTransactionRef(sc.transactionRef);
    setSummary(sc.summary);
    setNarrative(sc.narrative);
    toast(`Preset applied: "${sc.label}"! Click Submit below to send live.`, "info");
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!summary.trim() || !narrative.trim()) {
      toast("Please provide both an issue summary and description.", "error");
      return;
    }

    setSubmitting(true);
    try {
      const priority = amount && Number(amount) >= 100000 ? "CRITICAL" : "HIGH";
      const slaHours = priority === "CRITICAL" ? 12 : 24;

      const res = await api.ingestComplaint({
        customerName: customerName.trim() || "Hackathon Attendee",
        customerReference: `CUST-LIVE-${Math.floor(100000 + Math.random() * 900000)}`,
        customerPhone: customerPhone.trim() || "+234 800 000 0000",
        customerEmail: customerEmail.trim() || "attendee@hackathon.ng",
        accountNumber: accountNumber.trim() || "0123456789",
        channel: currentChannelConfig.sourceLabel,
        categoryCode,
        categoryLabel: categoryCode.replace("_", " "),
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
            customerName: customerName.trim() || "Hackathon Attendee",
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
            <BrandMark size={32} />
            <div>
              <strong>Apex Commercial Bank</strong>
              <small>Customer Resolution &amp; Omnichannel Dispute Gateway</small>
            </div>
          </div>
          <div className="portal-status-badge">
            <span className="live-pulse-dot" />
            <span>RESOLVEIQ Ingestion Gateway: <strong>LIVE</strong></span>
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
                    <small>Extracting switch telemetry &amp; classifying fault</small>
                  </div>
                </li>
                <li className="step-pending">
                  <div className="step-bubble"><Clock size={16} /></div>
                  <div className="step-info">
                    <strong>3. Investigation &amp; Settlement</strong>
                    <small>Assigned to Switch Operations for reversal</small>
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
                <span>Submit Another Test Dispute</span>
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
            {/* Left: Interactive Channel Selector & Presets */}
            <div className="portal-sidebar-col">
              <div className="portal-panel">
                <div className="portal-panel-head">
                  <Smartphone size={18} />
                  <h3>1. Select Inbound Banking Channel</h3>
                </div>
                <p className="portal-panel-desc">
                  Simulate how customer complaints enter the bank across various touchpoints:
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

              {/* 1-Tap Hackathon Presets */}
              <div className="portal-panel">
                <div className="portal-panel-head">
                  <Zap size={18} />
                  <h3>⚡ 1-Tap Hackathon Presets</h3>
                </div>
                <p className="portal-panel-desc">
                  Click any scenario below to auto-fill the complaint form instantly:
                </p>
                <div className="quick-scenarios-grid">
                  {QUICK_SCENARIOS.map((sc) => (
                    <button
                      key={sc.label}
                      type="button"
                      onClick={() => applyScenario(sc)}
                      className="quick-scenario-btn"
                    >
                      <div className="scenario-label">{sc.label}</div>
                      <div className="scenario-meta">
                        <span>₦{Number(sc.amount).toLocaleString()}</span>
                        <span>•</span>
                        <span>{sc.slaHours}h SLA</span>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Right: Channel-Styled Complaint Form */}
            <div className="portal-form-col">
              <div className="portal-form-card">
                <div className="portal-form-header">
                  <div className="portal-channel-banner">
                    <currentChannelConfig.icon size={22} style={{ color: currentChannelConfig.accent }} />
                    <div>
                      <h3>{currentChannelConfig.name} Intake Gateway</h3>
                      <p>{currentChannelConfig.sourceLabel}</p>
                    </div>
                  </div>
                </div>

                <form onSubmit={handleSubmit} className="portal-form-body">
                  {/* Customer Identity */}
                  <div className="form-section-title">
                    <span>Customer &amp; Account Details</span>
                  </div>
                  <div className="portal-row-2">
                    <label className="field">
                      <span className="field-label">Your Name (or Judge Name) *</span>
                      <input
                        type="text"
                        value={customerName}
                        onChange={(e) => setCustomerName(e.target.value)}
                        placeholder="e.g. Judge Babatunde"
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

                  {/* Transaction Information */}
                  <div className="form-section-title" style={{ marginTop: "12px" }}>
                    <span>Dispute Transaction Particulars</span>
                  </div>
                  <div className="portal-row-2">
                    <label className="field">
                      <span className="field-label">Disputed Amount (NGN ₦)</span>
                      <input
                        type="number"
                        value={amount}
                        onChange={(e) => setAmount(e.target.value)}
                        placeholder="50000"
                        className="field-input mono"
                      />
                    </label>
                    <label className="field">
                      <span className="field-label">Session ID / Reference</span>
                      <input
                        type="text"
                        value={transactionRef}
                        onChange={(e) => setTransactionRef(e.target.value)}
                        placeholder="e.g. ATM-VI-004-DISP-991"
                        className="field-input mono"
                      />
                    </label>
                  </div>

                  {/* Narrative */}
                  <div className="form-section-title" style={{ marginTop: "12px" }}>
                    <span>Complaint Narrative</span>
                  </div>
                  <label className="field">
                    <span className="field-label">Issue Headline / Subject *</span>
                    <input
                      type="text"
                      value={summary}
                      onChange={(e) => setSummary(e.target.value)}
                      placeholder="e.g. ATM debited ₦50,000 without dispensing cash"
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
                      placeholder="Describe what occurred, terminal location, error messages on screen, or beneficiary details..."
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
                          <span>Submit Incident via {currentChannelConfig.name}</span>
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
