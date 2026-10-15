// Captures every workspace route at desktop and mobile widths: node scripts/screens.mjs [outDir] [baseUrl]
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";

const out = process.argv[2] ?? "screens";
const base = process.argv[3] ?? "http://localhost:3000";
const routes = ["/", "/complaints", "/my-cases", "/forwarded", "/reports", "/notifications", "/settings", "/complaints/unknown"];
const viewports = { desktop: { width: 1440, height: 900 }, mobile: { width: 390, height: 844 } };

mkdirSync(out, { recursive: true });
const browser = await chromium.launch();
for (const [name, viewport] of Object.entries(viewports)) {
  const page = await browser.newPage({ viewport });
  const errors = [];
  page.on("pageerror", (e) => errors.push(`${page.url()} ${e.message.split("\n")[0]}`));
  page.on("console", (m) => m.type() === "error" && errors.push(`${page.url()} ${m.text().split("\n")[0]}`));
  for (const route of routes) {
    await page.goto(base + route, { waitUntil: "networkidle" });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
    const file = `${out}/${name}${route === "/" ? "-home" : route.replaceAll("/", "-")}.png`;
    await page.screenshot({ path: file, fullPage: true });
    console.log(file, overflow ? "HORIZONTAL OVERFLOW" : "");
  }
  if (errors.length) console.log(name, "errors:", errors);
  await page.close();
}
await browser.close();
