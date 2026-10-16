import type { Metadata, Viewport } from "next";
import { AppShell } from "@/components/app-shell";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "RESOLVEIQ", template: "%s · RESOLVEIQ" },
  description: "RESOLVEIQ incident intelligence & verified resolution desk.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#141416" },
  ],
};

// Applies the saved theme before first paint so dark-mode users never see a light flash.
const themeScript = `try{var p=JSON.parse(localStorage.getItem("resolveiq-preferences")||localStorage.getItem("biirs-preferences")||"{}");document.documentElement.dataset.theme=p.theme||"system"}catch(e){}`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en-GB" data-theme="system" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
