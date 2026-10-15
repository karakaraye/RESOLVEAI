import type { Metadata } from "next";
import { Suspense } from "react";
import { PageFallback } from "@/components/page-fallback";
import { ComplaintsView } from "@/components/views/complaints-view";

export const metadata: Metadata = { title: "Complaints" };

export default function Page() {
  return <Suspense fallback={<PageFallback title="Complaints" />}><ComplaintsView /></Suspense>;
}
