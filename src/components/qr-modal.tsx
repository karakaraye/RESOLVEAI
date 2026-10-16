"use client";

import { useEffect, useState } from "react";
import {
  Check,
  Copy,
  ExternalLink,
  Mail,
  MessageSquare,
  QrCode,
  Radio,
  RefreshCw,
  Send,
  Smartphone,
  Sparkles,
  Wifi,
  X,
  Zap,
} from "lucide-react";
import { QRCodeSVG } from "./qr-code";
import { api } from "@/lib/api/endpoints";
import { useToast } from "./toast";
import { playInboundChime } from "@/lib/audio-chime";

export function AudienceQrModal({
  isOpen,
  onClose,
}: {
  isOpen: boolean;
  onClose: () => void;
}) {
  const toast = useToast();
  const [copied, setCopied] = useState(false);
  const [portalUrl, setPortalUrl] = useState("http://localhost:3000/portal");
  const [simulating, setSimulating] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined") {
      // Use current window location to ensure mobile devices on local network can scan
      const origin = window.location.origin;
      setPortalUrl(`${origin}/portal`);
    }
  }, []);

  if (!isOpen) return null;

  const handleCopy = () => {
    navigator.clipboard.writeText(portalUrl);
    setCopied(true);
    toast("Portal link copied to clipboard!", "success");
    setTimeout(() => setCopied(false), 2500);
  };

  const handleSimulateInbound = async (
    channel: string,
    customerName: string,
    summary: string,
    narrative: string,
    amount: string,
    priority: "CRITICAL" | "HIGH" | "MEDIUM"
  ) => {
    setSimulating(true);
    try {
      const res = await api.ingestComplaint({
        customerName,
        customerReference: `CUST-LIVE-${Math.floor(100000 + Math.random() * 900000)}`,
        customerPhone: "+234 803 123 4567",
        customerEmail: `${customerName.toLowerCase().replace(/\s+/g, ".")}@hackathon.ng`,
        accountNumber: "0123456789",
        channel,
        categoryCode: "CARDS_ATM",
        categoryLabel: "Cards & ATM Terminals",
        priority,
        summary,
        narrative,
        amount,
        sendAcknowledgement: true,
      });

      playInboundChime();
      toast(`Simulated inbound complaint ${res.reference} received from ${channel}!`, "success");

      // Notify open tabs
      if (typeof window !== "undefined") {
        try {
          const bc = new BroadcastChannel("resolveiq_live_feed");
          bc.postMessage({
            type: "NEW_COMPLAINT_INGESTED",
            reference: res.reference,
            complaintId: res.complaintId,
            channel,
            summary,
            customerName,
            amount,
            timestamp: new Date().toISOString(),
          });
          bc.close();
        } catch {
          // handled
        }
      }
    } catch {
      toast("Simulation failed. Please try again.", "error");
    } finally {
      setSimulating(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose} role="dialog" aria-modal="true">
      <div className="modal-card qr-modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title-group">
            <span className="live-pill">
              <span className="live-pulse-dot" />
              LIVE HACKATHON INGESTION
            </span>
            <h2>Invite Audience &amp; Judges to Complain Live</h2>
            <p>
              Anyone in the room can scan this QR code on their phone to submit a complaint across multiple banking channels in real time.
            </p>
          </div>
          <button type="button" onClick={onClose} className="icon-button" aria-label="Close modal">
            <X size={18} />
          </button>
        </div>

        <div className="qr-modal-body">
          {/* Left: QR Code Display */}
          <div className="qr-display-box">
            <div className="qr-frame">
              <QRCodeSVG value={portalUrl} size={190} />
            </div>
            <div className="qr-url-box">
              <span className="qr-url-text mono">{portalUrl}</span>
              <button
                type="button"
                onClick={handleCopy}
                className="button button-small button-secondary copy-btn"
                title="Copy portal URL"
              >
                {copied ? <Check size={14} className="text-success" /> : <Copy size={14} />}
                <span>{copied ? "Copied" : "Copy"}</span>
              </button>
            </div>
            <a
              href={portalUrl}
              target="_blank"
              rel="noreferrer"
              className="text-link text-small qr-open-link"
            >
              <span>Open Customer Portal in new tab</span>
              <ExternalLink size={13} />
            </a>
          </div>

          {/* Right: Quick Simulated Injections */}
          <div className="qr-sim-box">
            <h4>⚡ Or Trigger Inbound Channel Simulation:</h4>
            <p className="qr-sim-note">
              Simulate real-time streaming incoming complaints without needing an audience phone:
            </p>

            <div className="qr-sim-list">
              <button
                type="button"
                disabled={simulating}
                onClick={() =>
                  handleSimulateInbound(
                    "Apex Bank Mobile App",
                    "Judge Adaeze Okonkwo",
                    "ATM Cash Dispenser Failure: ₦50,000 debited without cash",
                    "Withdrew ₦50,000 at Victoria Island branch ATM. Shutter failed to dispense notes.",
                    "50000",
                    "CRITICAL"
                  )
                }
                className="sim-action-btn"
              >
                <div className="sim-btn-icon" style={{ color: "oklch(52% 0.23 26)" }}>
                  <Smartphone size={18} />
                </div>
                <div className="sim-btn-content">
                  <strong>Simulate Mobile App Ingestion</strong>
                  <small>₦50,000 ATM Dispense Failure (CRITICAL 12h SLA)</small>
                </div>
              </button>

              <button
                type="button"
                disabled={simulating}
                onClick={() =>
                  handleSimulateInbound(
                    "Email to complaints@apexbank.ng",
                    "Judge Babatunde Adeleke",
                    "Interbank NIP Transfer stuck in PENDING status for 6 hours",
                    "Sent ₦250,000 to GTBank beneficiary. Money debited, beneficiary not credited.",
                    "250000",
                    "HIGH"
                  )
                }
                className="sim-action-btn"
              >
                <div className="sim-btn-icon" style={{ color: "oklch(48% 0.18 245)" }}>
                  <Mail size={18} />
                </div>
                <div className="sim-btn-content">
                  <strong>Simulate Inbound Customer Email</strong>
                  <small>₦250,000 NIP Interbank Transfer Stuck (HIGH 24h SLA)</small>
                </div>
              </button>

              <button
                type="button"
                disabled={simulating}
                onClick={() =>
                  handleSimulateInbound(
                    "Apex Bank Verified WhatsApp",
                    "Judge Chinedu Eze",
                    "POS Double Debit at Supermarket: ₦18,500 debited twice",
                    "POS machine said Issuer Timeout on swipe 1. Swiped again, both debited.",
                    "18500",
                    "MEDIUM"
                  )
                }
                className="sim-action-btn"
              >
                <div className="sim-btn-icon" style={{ color: "oklch(55% 0.19 148)" }}>
                  <MessageSquare size={18} />
                </div>
                <div className="sim-btn-content">
                  <strong>Simulate WhatsApp Bot Dispute</strong>
                  <small>₦18,500 POS Double Debit (MEDIUM 48h SLA)</small>
                </div>
              </button>
            </div>
          </div>
        </div>

        <div className="modal-footer">
          <div className="modal-footer-note">
            <Radio size={14} className="spin" style={{ color: "oklch(52% 0.23 26)" }} />
            <span>Operator desk will chime and pop up new incidents instantly as they arrive.</span>
          </div>
          <button type="button" onClick={onClose} className="button button-primary">
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
