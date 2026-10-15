import { expect, test } from "@playwright/test";
import { zonedWallTimeToIso } from "../src/lib/time";

test("wall-clock times convert in the institution's time zone", () => {
  expect(zonedWallTimeToIso("2026-03-10T14:05", "Africa/Lagos")).toBe("2026-03-10T13:05:00.000Z");
  expect(zonedWallTimeToIso("2026-03-10T14:05", "UTC")).toBe("2026-03-10T14:05:00.000Z");
  // Across a DST change: London is UTC+1 from 29 March 2026.
  expect(zonedWallTimeToIso("2026-03-28T12:00", "Europe/London")).toBe("2026-03-28T12:00:00.000Z");
  expect(zonedWallTimeToIso("2026-03-30T12:00", "Europe/London")).toBe("2026-03-30T11:00:00.000Z");
  expect(zonedWallTimeToIso("not a date", "UTC")).toBeNull();
});
