/** Time parsing/formatting only. No scoring logic lives in the front end. */

/** Parse "H:MM:SS", "HH:MM", or digits like "183045" into "HH:MM:SS" (24h). Returns null if invalid. */
export function parseTimeInput(raw: string): string | null {
  const s = raw.trim();
  if (!s) return null;
  let h: number, m: number, sec: number;
  if (s.includes(":")) {
    const p = s.split(":").map((x) => x.trim());
    if (p.length < 2 || p.length > 3 || p.some((x) => !/^\d{1,2}$/.test(x))) return null;
    [h, m, sec] = [Number(p[0]), Number(p[1]), Number(p[2] ?? 0)];
  } else {
    if (!/^\d{3,6}$/.test(s)) return null;
    const d = s.padStart(s.length <= 4 ? 4 : 6, "0");
    if (d.length === 4) [h, m, sec] = [Number(d.slice(0, 2)), Number(d.slice(2)), 0];
    else [h, m, sec] = [Number(d.slice(0, 2)), Number(d.slice(2, 4)), Number(d.slice(4))];
  }
  if (h > 23 || m > 59 || sec > 59) return null;
  return [h, m, sec].map((n) => String(n).padStart(2, "0")).join(":");
}

/** "2027-06-02T18:00:00" -> "18:00:00" */
export function timeOf(iso: string): string {
  return iso.slice(11, 19);
}

export function dateOf(iso: string): string {
  return iso.slice(0, 10);
}

export function addDays(date: string, days: number): string {
  const d = new Date(`${date}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/**
 * Combine the start's date with a finish time. A finish clock time earlier than the start's is
 * assumed to be the next day (needs the RC's confirmation in the UI).
 */
export function buildFinishIso(startIso: string, hms: string, nextDay: boolean): string {
  return `${addDays(dateOf(startIso), nextDay ? 1 : 0)}T${hms}`;
}

export function needsNextDay(startIso: string, hms: string): boolean {
  return hms < timeOf(startIso);
}

export function nowHms(d = new Date()): string {
  return [d.getHours(), d.getMinutes(), d.getSeconds()].map((n) => String(n).padStart(2, "0")).join(":");
}

export function fmtPoints(p: number | null | undefined): string {
  if (p === null || p === undefined) return "";
  return Number.isInteger(p) ? String(p) : p.toFixed(1);
}

export function fmtDate(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
