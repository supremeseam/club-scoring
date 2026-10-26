import { describe, expect, it } from "vitest";
import { clearTokens, pickIdToken } from "./tokens";

const jwt = (exp: number) => `h.${btoa(JSON.stringify({ exp })).replace(/=+$/, "")}.s`;
const NOW = 1_800_000_000_000;
const fresh = jwt(NOW / 1000 + 600);
const stale = jwt(NOW / 1000 - 600);

const store = (items: Record<string, string>) => ({
  getItem: (k: string) => items[k] ?? null,
  removeItem: (k: string) => void delete items[k],
});
const session = (idToken: string) => JSON.stringify({ idToken, accessToken: "a", refreshToken: null, expiresAt: 0 });

describe("pickIdToken", () => {
  it("returns the first unexpired token in the order the keys are listed", () => {
    const s = store({ admin: session(fresh), member: session(jwt(NOW / 1000 + 900)) });
    expect(pickIdToken(s, ["admin", "member"], NOW)).toBe(fresh);
  });
  it("skips expired, missing and malformed entries", () => {
    const s = store({ admin: session(stale), junk: "{not json", member: session(fresh) });
    expect(pickIdToken(s, ["admin", "nothing", "junk", "member"], NOW)).toBe(fresh);
  });
  it("returns null when nothing usable is stored", () => {
    expect(pickIdToken(store({}), ["admin"], NOW)).toBeNull();
    expect(pickIdToken(store({ admin: session(stale) }), ["admin"], NOW)).toBeNull();
    expect(pickIdToken(store({ admin: JSON.stringify({ idToken: "not-a-jwt" }) }), ["admin"], NOW)).toBeNull();
  });
  it("never throws when storage is unavailable", () => {
    const broken = { getItem: () => { throw new Error("blocked"); }, removeItem: () => {} };
    expect(pickIdToken(broken, ["admin"], NOW)).toBeNull();
  });
});

describe("clearTokens", () => {
  it("removes every listed key", () => {
    const items = { admin: session(fresh), member: session(fresh), other: "keep" };
    clearTokens(store(items), ["admin", "member"]);
    expect(Object.keys(items)).toEqual(["other"]);
  });
});
