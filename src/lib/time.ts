// Converts a `datetime-local` value ("2026-03-10T14:05"), read as wall-clock time in `timeZone`, to an ISO instant.
export function zonedWallTimeToIso(value: string, timeZone: string): string | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value);
  if (!match) return null;
  const [, y, mo, d, h, mi] = match.map(Number);
  const asUtc = Date.UTC(y, mo - 1, d, h, mi);
  // Offset of the zone at that moment; a second pass settles DST boundaries.
  let guess = asUtc - offsetMs(asUtc, timeZone);
  guess = asUtc - offsetMs(guess, timeZone);
  return new Date(guess).toISOString();
}

function offsetMs(instant: number, timeZone: string) {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-US", { timeZone, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" })
      .formatToParts(instant).filter((p) => p.type !== "literal").map((p) => [p.type, Number(p.value)]),
  );
  return Date.UTC(parts.year, parts.month - 1, parts.day, parts.hour, parts.minute, parts.second) - Math.floor(instant / 1000) * 1000;
}
