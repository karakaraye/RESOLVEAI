import type { Metadata } from "next";
import { Suspense } from "react";
import { PageFallback } from "@/components/page-fallback";
import { HomeView } from "@/components/views/home-view";

export const metadata: Metadata = { title: { absolute: "RESOLVEIQ" } };

export default function Page() {
  return <Suspense fallback={<PageFallback title="Home" />}><HomeView /></Suspense>;
}
