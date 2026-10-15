import type { Metadata } from "next";
import { Suspense } from "react";
import { PageFallback } from "@/components/page-fallback";
import { ReportsView } from "@/components/views/reports-view";

export const metadata: Metadata = { title: "Reports" };

export default function Page() {
  return <Suspense fallback={<PageFallback title="Reports" />}><ReportsView /></Suspense>;
}
