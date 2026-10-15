import type { Metadata } from "next";
import { Suspense } from "react";
import { PageFallback } from "@/components/page-fallback";
import { SettingsView } from "@/components/views/settings-view";

export const metadata: Metadata = { title: "Settings" };

export default function Page() {
  return <Suspense fallback={<PageFallback title="Settings" />}><SettingsView /></Suspense>;
}
