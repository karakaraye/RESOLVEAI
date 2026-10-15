import type { Metadata } from "next";
import { Suspense } from "react";
import { PageFallback } from "@/components/page-fallback";
import { ComplaintDetailView } from "@/components/views/complaint-detail-view";

export const metadata: Metadata = { title: "Complaint" };

export default function Page() {
  return <Suspense fallback={<PageFallback title="Complaint" />}><ComplaintDetailView /></Suspense>;
}
