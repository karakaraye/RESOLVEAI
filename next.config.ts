import type { NextConfig } from "next";
import { resolve } from "node:path";
const DJANGO_API_URL = (
  process.env.DJANGO_API_URL ||
  process.env.NEXT_PUBLIC_DJANGO_API_URL ||
  process.env.NEXT_PUBLIC_RESOLVEIQ_API_URL ||
  "http://127.0.0.1:8000"
).replace(/\/$/, "");

console.log("[next.config.ts] Proxying /api/v1/* to DJANGO_API_URL:", DJANGO_API_URL);

const nextConfig: NextConfig = {
  turbopack: { root: resolve(process.cwd()) },
  cacheComponents: true,
  partialPrefetching: true,
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${DJANGO_API_URL}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
