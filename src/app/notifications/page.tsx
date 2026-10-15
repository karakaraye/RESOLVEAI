import type { Metadata } from "next";
import { Suspense } from "react";
import { PageFallback } from "@/components/page-fallback";
import { NotificationsView } from "@/components/views/notifications-view";

export const metadata: Metadata = { title: "Notifications" };

export default function Page() {
  return <Suspense fallback={<PageFallback title="Notifications" />}><NotificationsView /></Suspense>;
}
