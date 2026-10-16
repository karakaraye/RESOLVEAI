import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { ComplaintIntakeForm } from "@/components/complaint-intake";

export const metadata: Metadata = {
  title: "File New Complaint",
  description: "Live omnichannel complaint intake and regulatory ingestion gateway.",
};

export default function NewComplaintPage() {
  return (
    <div className="new-complaint-page">
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link href="/complaints">
          <ArrowLeft size={15} aria-hidden="true" />
          <span>Complaints</span>
        </Link>
        <span className="muted">/</span>
        <span aria-current="page">File New Complaint</span>
      </nav>

      <ComplaintIntakeForm embedded />
    </div>
  );
}
