/** Shapes returned by /api/crew/* (those endpoints return plain JSON, so the types live here). */
export type Posting = {
  id: number; race_id: number | null; race: string; race_date?: string | null;
  role: string; spots: number; experience: string; notes: string; interested?: number; is_open?: boolean;
};
export type BoardBoat = { boat_id: number; name: string; sail_number: string; design: string; fleet: string; notes: string; postings: Posting[] };
export type BoardRace = { race_id: number; label: string; date: string; volunteers: number };
export type Board = { boats: BoardBoat[]; races: BoardRace[]; open_to_any: number };
export type Options = { boats: { id: number; name: string; sail_number: string }[]; all_boats: { id: number; name: string; sail_number: string }[]; races: { id: number; label: string }[] };
export type SignupStatus = {
  id: number; status: "pending" | "accepted" | "declined" | "withdrawn"; boat: string; boat_id: number | null;
  race: string; race_id: number | null; role: string; message: string; created: string;
  skipper_contact?: { name?: string; email?: string; phone?: string; note?: string };
};
export type SignupFull = SignupStatus & { name: string; email: string; phone: string; experience: string; seen: boolean };
export type CrewInfo = { notes: string; contact_name: string; contact_email: string; contact_phone: string; contact_preference: "app" | "email" | "phone" };
export type SkipperOverview = {
  boats: { id: number; name: string; sail_number: string; design: string; info: CrewInfo; postings: Posting[] }[];
  unseen: number;
  races: { id: number; label: string }[];
};
export type SkipperAccount = { user_id: number; username: string; name: string; email: string; active: boolean; boats: { id: number; name: string }[] };
export type SkipperRequestRow = { id: number; name: string; email: string; boat_id: number | null; boat: string; message: string; created: string };

export const STATUS_COLOR: Record<string, string> = { pending: "yellow", accepted: "green", declined: "gray", withdrawn: "gray" };

/** Sign-up tokens for people without an account live only in this browser. */
const KEY = "crew-signup-tokens";
export function savedTokens(): string[] {
  try { return JSON.parse(localStorage.getItem(KEY) ?? "[]"); } catch { return []; }
}
export function saveToken(token: string) {
  try { localStorage.setItem(KEY, JSON.stringify([...savedTokens(), token].slice(-20))); } catch { /* private mode */ }
}
export function forgetToken(token: string) {
  try { localStorage.setItem(KEY, JSON.stringify(savedTokens().filter((t) => t !== token))); } catch { /* private mode */ }
}
