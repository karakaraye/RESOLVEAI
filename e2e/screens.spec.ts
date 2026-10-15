// Visual review captures of populated states (fixtures). Runs only when SCREENS_DIR is set:
//   SCREENS_DIR=../../screens pnpm exec playwright test e2e/screens.spec.ts
import { test } from "@playwright/test";
import { mockApi } from "./fixtures";

const dir = process.env.SCREENS_DIR;
const shots: [string, string, (page: import("@playwright/test").Page) => Promise<void>][] = [
  ["home", "/", async () => {}],
  ["complaints", "/complaints", async () => {}],
  ["complaints-menu", "/complaints", async (page) => { await page.getByRole("button", { name: /More actions for/ }).nth(2).click(); }],
  ["my-cases", "/my-cases?due=overdue", async () => {}],
  ["forwarded", "/forwarded", async () => {}],
  ["reports", "/reports", async () => {}],
  ["reports-issues", "/reports?type=RECURRING_ISSUES", async () => {}],
  ["notifications", "/notifications", async () => {}],
  ["settings", "/settings", async () => {}],
  ["settings-prefs", "/settings?section=preferences", async () => {}],
  ["settings-help", "/settings?section=help", async () => {}],
  ["detail", "/complaints/c-1001", async () => {}],
  ["detail-forward", "/complaints/c-1001?action=forward", async () => {}],
  ["detail-review", "/complaints/c-1001?action=forward", async (page) => { await page.getByRole("button", { name: "Review handoff" }).click(); }],
  ["popover-notifications", "/", async (page) => { await page.getByRole("button", { name: /Notifications/ }).click(); }],
];

test.describe("visual captures @mobile", () => {
  test.skip(!dir, "set SCREENS_DIR to capture");
  for (const scheme of ["light", "dark"] as const) {
    for (const [name, path, act] of shots) {
      test(`${scheme} ${name}`, async ({ page }, info) => {
        if (scheme === "dark" && !["home", "complaints", "detail", "reports"].includes(name)) test.skip();
        await page.emulateMedia({ colorScheme: scheme, reducedMotion: "reduce" });
        await mockApi(page);
        await page.goto(path);
        await page.locator("h1").first().waitFor();
        await page.waitForTimeout(900);
        await act(page);
        await page.waitForTimeout(300);
        await page.screenshot({ path: `${dir}/${info.project.name}-${scheme}-${name}.png`, fullPage: true });
      });
    }
  }
});
