"use client";

import { useEffect, useState } from "react";
import {
  Check,
  Copy,
  ExternalLink,
  Radio,
  X,
} from "lucide-react";
import { QRCodeSVG } from "./qr-code";
import { useToast } from "./toast";

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

  useEffect(() => {
    if (typeof window !== "undefined") {
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

  return (
    <div className="modal-backdrop" onClick={onClose} role="dialog" aria-modal="true">
      <div className="modal-card qr-modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title-group">
            <span className="live-pill">
              <span className="live-pulse-dot" />
              LIVE OMNICHANNEL INGESTION
            </span>
            <h2>Scan to Submit Live Complaint</h2>
            <p>
              Scan this QR code with any mobile device to open the customer dispute portal and submit a complaint across multiple banking channels in real time.
            </p>
          </div>
          <button type="button" onClick={onClose} className="icon-button" aria-label="Close modal">
            <X size={18} />
          </button>
        </div>

        <div className="qr-modal-body">
          <div className="qr-display-box">
            <div className="qr-frame">
              <QRCodeSVG value={portalUrl} size={220} />
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
        </div>

        <div className="modal-footer">
          <div className="modal-footer-note">
            <Radio size={14} className="spin" style={{ color: "oklch(52% 0.23 26)" }} />
            <span>The operator desk will chime and display incoming complaints in real time.</span>
          </div>
          <button type="button" onClick={onClose} className="button button-primary">
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
