import type { Metadata } from "next";
import { CustomerDisputePortal } from "@/components/customer-portal";

export const metadata: Metadata = {
  title: "Apex Bank — Customer Incident & Dispute Gateway",
  description: "Public multi-channel dispute portal for retail customers, web banking, mobile app, and WhatsApp banking bot.",
};

export default function PortalPage() {
  return <CustomerDisputePortal />;
}
