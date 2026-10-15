import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET() {
  const djangoUrl = process.env.DJANGO_API_URL || process.env.NEXT_PUBLIC_DJANGO_API_URL || process.env.NEXT_PUBLIC_RESOLVEIQ_API_URL;
  return NextResponse.json({
    djangoUrlSet: Boolean(djangoUrl),
    djangoUrlValue: djangoUrl || null,
    relevantEnvKeys: Object.keys(process.env).filter(
      (k) => k.includes("DJANGO") || k.includes("API") || k.includes("VERCEL") || k.includes("URL")
    ),
  });
}
