import { defineConfig, devices } from "@playwright/test";

// The suite runs against a production build whose API address points at a host the tests intercept.
// The web server builds with that address, then serves on :3100 (an already running :3100 is reused).
export default defineConfig({
  testDir: "e2e",
  fullyParallel: true,
  workers: 3,
  retries: 0,
  reporter: [["list"]],
  use: { baseURL: "http://localhost:3100", trace: "retain-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "mobile", use: { ...devices["Pixel 7"] }, grep: /@mobile/ },
  ],
  webServer: {
    command: "pnpm exec next build && pnpm exec next start -p 3100",
    env: { NEXT_PUBLIC_BIIRS_API_URL: "http://api.biirs.test/api/v1" },
    url: "http://localhost:3100",
    reuseExistingServer: true,
    timeout: 300_000,
  },
});
