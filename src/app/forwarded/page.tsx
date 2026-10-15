import type { Metadata } from "next";
import { Suspense } from "react";
import { PageFallback } from "@/components/page-fallback";
import { ForwardedView } from "@/components/views/forwarded-view";

export const metadata: Metadata = { title: "Forwarded" };

export default function Page() {
  return <Suspense fallback={<PageFallback title="Forwarded" />}><ForwardedView /></Suspense>;
}
