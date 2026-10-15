import { expect, test } from "@playwright/test";
import { complaints, mockApi } from "./fixtures";

test.describe("shell and navigation", () => {
  test("every main page is reachable and marks the current item @mobile", async ({ page, isMobile }) => {
    await mockApi(page);
    await page.goto("/");
    const nav = isMobile ? page.locator(".mobile-nav") : page.getByRole("complementary", { name: "Main navigation" });
    for (const [label, heading] of [["Complaints", "Complaints"], ["My Cases", "My cases"], ["Forwarded", "Forwarded"], ["Reports", "Reports"], ["Settings", "Settings"], ["Home", /Good (morning|afternoon|evening), Test/]] as const) {
      await nav.getByRole("link", { name: label, exact: true }).click();
      await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
      await expect(nav.getByRole("link", { name: label, exact: true })).toHaveAttribute("aria-current", "page");
    }
  });

  test("no page scrolls sideways @mobile", async ({ page }) => {
    test.setTimeout(90_000);
    await mockApi(page);
    for (const path of ["/", "/complaints", "/my-cases", "/forwarded", "/reports", "/notifications", "/settings", "/complaints/c-1001"]) {
      await page.goto(path);
      await page.locator("h1").first().waitFor();
      await page.waitForTimeout(600);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow, path).toBeLessThanOrEqual(0);
    }
  });

  test("global search opens the register with the query applied and / focuses it", async ({ page }) => {
    const calls = await mockApi(page);
    await page.goto("/reports");
    await page.keyboard.press("/");
    await expect(page.getByLabel("Search complaints by reference, customer or issue")).toBeFocused();
    await page.keyboard.type("TST-1044");
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/complaints\?q=TST-1044/);
    await expect(page.getByRole("link", { name: "TST-1044", exact: true })).toBeVisible();
    expect(calls.some((c) => c.path === "/complaints" && c.method === "GET")).toBeTruthy();
  });

  test("notification bell shows unread count and recent items", async ({ page }) => {
    await mockApi(page);
    await page.goto("/");
    const bell = page.getByRole("button", { name: "Notifications, 2 unread" });
    await bell.click();
    await expect(page.getByRole("region", { name: "Recent notifications" }).getByText("TST-1044 was assigned to you")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("region", { name: "Recent notifications" })).toBeHidden();
  });

  test("account menu shows the signed-in person and sign-out reports failures honestly", async ({ page }) => {
    await mockApi(page, { "POST /session/sign-out": 500 });
    await page.goto("/");
    await page.getByRole("button", { name: /Test Operator/ }).click();
    await expect(page.getByText("operator@bank.test")).toBeVisible();
    await page.getByRole("region", { name: "Account" }).getByRole("button", { name: "Sign out" }).click();
    await expect(page.getByText("Sign out didn’t complete. Your session is still active; try again.")).toBeVisible();
  });
});

test.describe("connection states", () => {
  test("an unreachable service is explained instead of showing empty data", async ({ page }) => {
    await page.route("http://api.biirs.test/**", (route) => route.abort("connectionrefused"));
    await page.goto("/complaints");
    await expect(page.getByText("BIIRS can’t be reached")).toBeVisible();
    await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
  });

  test("signed-out users are told to sign in, not shown an empty workload", async ({ page }) => {
    await mockApi(page, { "GET /session": 401, "GET /workspace/summary": 401 });
    await page.goto("/");
    await expect(page.getByText("Sign in to continue")).toBeVisible();
    await expect(page.getByText("Once connected, Home shows")).toBeVisible();
  });

  test("unknown complaint shows not found", async ({ page }) => {
    await mockApi(page);
    await page.goto("/complaints/missing");
    await expect(page.getByText("Not found", { exact: true })).toBeVisible();
  });
});

test.describe("home", () => {
  test("workload strip and next actions link to filtered lists", async ({ page }) => {
    await mockApi(page);
    await page.goto("/");
    await expect(page.getByRole("navigation", { name: "Workload summary" })).toContainText("Needs attention");
    await page.getByRole("link", { name: /Review new complaints/ }).click();
    await expect(page).toHaveURL(/\/complaints\?status=NEW/);
    await expect(page.getByRole("combobox", { name: "Status" })).toHaveValue("NEW");
  });

  test("reports never block case handling when unavailable", async ({ page }) => {
    await mockApi(page, { "GET /reports/complaint-volumes": 500 });
    await page.goto("/");
    await expect(page.getByRole("region", { name: "Complaint trend" })).toContainText("Unavailable right now. Case work is not affected.");
    await expect(page.getByRole("heading", { name: "Recent complaints" })).toBeVisible();
  });
});

test.describe("complaints register", () => {
  test("filters live in the URL, combine and clear", async ({ page }) => {
    const calls = await mockApi(page);
    await page.goto("/complaints");
    await page.getByRole("combobox", { name: "Status" }).selectOption("IN_PROGRESS");
    await expect(page).toHaveURL(/status=IN_PROGRESS/);
    await page.getByRole("combobox", { name: "Priority" }).selectOption("HIGH");
    await expect(page).toHaveURL(/priority=HIGH/);
    const last = calls.filter((c) => c.path === "/complaints").at(-1)!;
    expect(last.headers).toBeTruthy();
    await page.getByRole("button", { name: "Clear" }).click();
    await expect(page).toHaveURL(/\/complaints$/);
  });

  test("pagination appears only when needed", async ({ page }) => {
    await mockApi(page);
    await page.goto("/complaints");
    await expect(page.getByText(`1–25 of ${complaints.length} complaints`)).toBeVisible();
    await page.getByRole("button", { name: "Next" }).click();
    await expect(page).toHaveURL(/page=2/);
    await expect(page.getByText(`26–${complaints.length} of ${complaints.length} complaints`)).toBeVisible();
  });

  test("row menu offers only allowed actions and is keyboard operable", async ({ page }) => {
    await mockApi(page);
    await page.goto("/complaints");
    const resolved = complaints.find((c) => c.status === "RESOLVED")!;
    await page.getByRole("button", { name: `More actions for ${resolved.reference}` }).click();
    const menu = page.getByRole("menu");
    await expect(menu.getByRole("menuitem")).toHaveText(["Add note", "Reopen case"]);
    await expect(menu.getByRole("menuitem").first()).toBeFocused();
    await page.keyboard.press("ArrowDown");
    await expect(menu.getByRole("menuitem", { name: "Reopen case" })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(menu).toBeHidden();
    await expect(page.getByRole("button", { name: `More actions for ${resolved.reference}` })).toBeFocused();
  });

  test("view keeps the list context for the way back", async ({ page }) => {
    await mockApi(page);
    await page.goto("/complaints?status=NEEDS_ACTION");
    await page.getByRole("link", { name: /View complaint/ }).first().click();
    await expect(page.getByRole("navigation", { name: "Breadcrumb" }).getByRole("link", { name: "Complaints" })).toHaveAttribute("href", "/complaints?status=NEEDS_ACTION");
  });

  test("empty filtered results explain and offer reset", async ({ page }) => {
    await mockApi(page, { "GET /complaints": { items: [], total: 0, page: 1, pageSize: 25 } });
    await page.goto("/complaints?q=nothing");
    await expect(page.getByText("No complaints match these filters")).toBeVisible();
    await page.getByRole("button", { name: "Clear filters" }).click();
    await expect(page.getByText("No complaints yet")).toBeVisible();
  });
});

test.describe("complaint detail", () => {
  test("shows evidence, conflicts, hypotheses and the recommended step", async ({ page }) => {
    await mockApi(page);
    await page.goto("/complaints/c-1001");
    await expect(page.getByRole("heading", { level: 1, name: "Card declined repeatedly" })).toBeVisible();
    await expect(page.getByText(/Sources disagree: core banking shows debited/)).toBeVisible();
    await expect(page.getByText("Hypothesis")).toBeVisible();
    await expect(page.getByRole("button", { name: "Forward to team" })).toBeVisible();
    await expect(page.getByText("Send failed")).toBeVisible();
  });

  test("forwarding is reviewed before sending, uses an idempotency key and reports the real state", async ({ page }) => {
    const calls = await mockApi(page);
    await page.goto("/complaints/c-1001");
    await page.getByRole("button", { name: "Forward to team" }).click();
    await expect(page).toHaveURL(/action=forward/);
    await expect(page.getByLabel("Receiving team")).toHaveValue("team-settle");
    await page.getByLabel("Named recipient (optional)").selectOption("Duty lead");
    await page.getByRole("button", { name: "Review handoff" }).click();
    await expect(page.getByText("Masked customer reference")).toBeVisible();
    expect(calls.some((c) => c.method === "POST")).toBeFalsy();
    await page.getByRole("button", { name: "Send to Settlements team" }).click();
    await expect(page.getByText("Handoff recorded · Sent")).toBeVisible();
    await expect(page.getByText("Receipt is not confirmed yet.").first()).toBeVisible();
    const post = calls.find((c) => c.method === "POST" && c.path === "/complaints/c-1001/handoffs")!;
    expect(post.body).toMatchObject({ teamId: "team-settle", recipient: "Duty lead" });
    expect(post.headers["idempotency-key"]).toMatch(/[0-9a-f-]{36}/);
  });

  test("an uncertain send can be retried with the same key and never claims success", async ({ page }) => {
    let attempts = 0;
    const calls = await mockApi(page, {
      "POST /complaints/c-1001/handoffs": (route) => { attempts += 1; return attempts === 1 ? route.abort("timedout").then(() => undefined) : { ...complaints[0], id: "h-x", state: "DELIVERED", team: { id: "team-settle", name: "Settlements team" }, channel: "Queue", createdAt: "", createdBy: "", lastUpdatedAt: "", attempts: [], retryAllowed: false }; },
    });
    await page.goto("/complaints/c-1001?action=forward");
    await page.getByRole("button", { name: "Review handoff" }).click();
    await page.getByRole("button", { name: "Send to Settlements team" }).click();
    await expect(page.getByText("BIIRS couldn’t confirm whether this was saved. Trying again is safe")).toBeVisible();
    await expect(page.getByText("Handoff recorded")).toBeHidden();
    await page.getByRole("button", { name: "Send to Settlements team" }).click();
    await expect(page.getByText("Handoff recorded · Delivered")).toBeVisible();
    const keys = calls.filter((c) => c.path === "/complaints/c-1001/handoffs").map((c) => c.headers["idempotency-key"]);
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]);
  });

  test("adding a note saves, closes the panel and reloads", async ({ page }) => {
    const calls = await mockApi(page);
    await page.goto("/complaints/c-1001");
    await page.getByRole("button", { name: "Add note" }).first().click();
    await page.getByRole("textbox", { name: "Internal note" }).fill("Customer confirmed the recipient account number.");
    await page.getByRole("button", { name: "Add note" }).last().click();
    await expect(page.getByText("Internal note added.")).toBeVisible();
    await expect(page).not.toHaveURL(/action=/);
    expect(calls.filter((c) => c.path === "/complaints/c-1001" && c.method === "GET").length).toBeGreaterThan(1);
  });

  test("validation errors from the server are shown and nothing is claimed", async ({ page }) => {
    await mockApi(page, { "POST /complaints/c-1001/notes": 422 });
    await page.goto("/complaints/c-1001?action=add-note");
    await page.getByRole("textbox", { name: "Internal note" }).fill("x");
    await page.getByRole("button", { name: "Add note" }).last().click();
    await expect(page.getByText("Test failure 422")).toBeVisible();
    await expect(page.getByText("Internal note added.")).toBeHidden();
  });

  test("follow-up rejects past times", async ({ page }) => {
    await mockApi(page);
    await page.goto("/complaints/c-1001?action=set-follow-up");
    await page.getByLabel("Follow up on").fill("2020-01-01T09:00");
    await expect(page.getByText("Choose a time in the future.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Set follow-up" })).toBeDisabled();
  });

  test("an action the case doesn't allow is refused with an explanation", async ({ page }) => {
    await mockApi(page);
    await page.goto("/complaints/c-1001?action=reopen");
    await expect(page.getByText("Reopen case isn’t available for this case in its current state.")).toBeVisible();
    await expect(page).not.toHaveURL(/action=/);
  });

  test("failed handoffs can be retried", async ({ page }) => {
    const calls = await mockApi(page, { "POST /handoffs/h-SEND_FAILED-6/retry": { state: "RETRY_SCHEDULED" } });
    await page.goto("/complaints/c-1001");
    await page.getByRole("button", { name: "Retry send" }).click();
    await expect(page.getByText("Retry recorded · Retry scheduled")).toBeVisible();
    expect(calls.find((c) => c.path.endsWith("/retry"))!.headers["idempotency-key"]).toBeTruthy();
  });
});

test.describe("other pages", () => {
  test("forwarded lists handoffs with distinct states and filters by state", async ({ page }) => {
    await mockApi(page);
    await page.goto("/forwarded");
    await expect(page.getByRole("table").getByText("Sent · delivery unconfirmed")).toBeVisible();
    await page.getByRole("link", { name: /Send failed/ }).first().click();
    await expect(page).toHaveURL(/state=SEND_FAILED/);
  });

  test("reports show one analysis, validate custom ranges and disclose partial data", async ({ page }) => {
    await mockApi(page);
    await page.goto("/reports");
    await expect(page.getByRole("heading", { level: 2, name: "Overview" })).toBeVisible();
    await expect(page.getByText("Median time to verify")).toBeVisible();
    await page.getByRole("combobox", { name: "Report", exact: true }).selectOption("TEAM_RESPONSE_TIMES");
    await expect(page.getByText("Partial data.")).toBeVisible();
    await expect(page.getByText("Not available")).toBeVisible();
    await page.getByRole("combobox", { name: "Date range" }).selectOption("custom");
    await expect(page.getByText("Choose a start and end date, then apply.")).toBeVisible();
    await page.getByLabel("From", { exact: true }).fill("2026-03-10");
    await page.getByLabel("To", { exact: true }).fill("2026-03-01");
    await expect(page.getByText("The start date must be on or before the end date.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Apply" })).toBeDisabled();
    await page.getByLabel("To", { exact: true }).fill("2026-03-31");
    await page.getByRole("button", { name: "Apply" }).click();
    await expect(page).toHaveURL(/from=2026-03-10&to=2026-03-31/);
    await expect(page.getByRole("heading", { level: 2, name: "Team response times" })).toBeVisible();
    await expect(page.getByText("10 Mar 2026 to 31 Mar 2026")).toBeVisible();
  });

  test("notifications: open marks read, mark-all only when unread", async ({ page }) => {
    const calls = await mockApi(page);
    await page.goto("/notifications");
    await page.getByRole("button", { name: "Mark all as read" }).click();
    await expect(page.getByText("All notifications marked as read.")).toBeVisible();
    expect(calls.some((c) => c.path === "/notifications/read-all")).toBeTruthy();
    await page.getByRole("button", { name: /TST-1044 was assigned to you/ }).click();
    await expect(page).toHaveURL(/\/complaints\/c-1001/);
    expect(calls.some((c) => c.path === "/notifications/nt1/read")).toBeTruthy();
  });

  test("settings: managed profile, saved preferences and theme", async ({ page }) => {
    const calls = await mockApi(page);
    await page.goto("/settings");
    await expect(page.getByText("operator@bank.test")).toBeVisible();
    await page.getByRole("link", { name: "Notifications" }).last().click();
    await page.getByRole("switch", { name: /Approaching deadlines/ }).check();
    await page.getByRole("button", { name: "Save preferences" }).click();
    await expect(page.getByText("Notification preferences saved.")).toBeVisible();
    expect(calls.find((c) => c.method === "PUT")!.body).toContainEqual({ key: "deadlines", enabled: true });
    await page.getByRole("link", { name: "Preferences" }).click();
    await page.getByLabel("Dark").check();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  });
});
