import type { Metadata } from "next";
import { Suspense } from "react";
import { PageFallback } from "@/components/page-fallback";
import { MyCasesView } from "@/components/views/complaints-view";

export const metadata: Metadata = { title: "My cases" };

export default function Page() {
  return <Suspense fallback={<PageFallback title="My cases" />}><MyCasesView /></Suspense>;
}
