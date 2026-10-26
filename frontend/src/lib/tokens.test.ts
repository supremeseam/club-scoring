import { describe, expect, it, vi } from "vitest";
import { clearTokens, pickIdToken, refreshIdToken } from "./tokens";

const POOL = "us-west-2_AbCdEf123";
const CLIENT = "clientmembers1a2b3c";
const ISS = `https://cognito-idp.us-west-2.amazonaws.com/${POOL}`;
const jwt = (exp: number, claims: Record<string, unknown> = {}) =>
  `h.${btoa(JSON.stringify({ exp, ...claims })).replace(/=+$/, "")}.s`;
const NOW = 1_800_000_000_000;
const fresh = jwt(NOW / 1000 + 600);
const stale = jwt(NOW / 1000 - 600);
const staleOurs = jwt(NOW / 1000 - 600, { iss: ISS, aud: CLIENT });

const store = (items: Record<string, string>) => ({
  getItem: (k: string) => items[k] ?? null,
  setItem: (k: string, v: string) => void (items[k] = v),
  removeItem: (k: string) => void delete items[k],
});
const session = (idToken: string, refreshToken: string | null = null) =>
  JSON.stringify({ idToken, accessToken: "a", refreshToken, expiresAt: 0 });

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
    const broken = { getItem: () => { throw new Error("blocked"); }, setItem: () => {}, removeItem: () => {} };
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

describe("refreshIdToken", () => {
  const pools = [{ pool_id: POOL, client_id: CLIENT }];
  const renewed = jwt(NOW / 1000 + 900, { iss: ISS, aud: CLIENT });
  const ok = () => vi.fn(async () => new Response(JSON.stringify({ AuthenticationResult: { IdToken: renewed, AccessToken: "newaccess", ExpiresIn: 900 } })));

  it("asks Cognito for a new ID token with the refresh token and stores it beside the other fields", async () => {
    const items = { member: session(staleOurs, "refresh-1") };
    const fetchFn = ok();
    expect(await refreshIdToken(store(items), ["admin", "member"], pools, fetchFn, NOW)).toBe(renewed);
    const [url, init] = fetchFn.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("https://cognito-idp.us-west-2.amazonaws.com/");
    expect((init.headers as Record<string, string>)["X-Amz-Target"]).toBe("AWSCognitoIdentityProviderService.InitiateAuth");
    expect(JSON.parse(init.body as string)).toEqual({
      AuthFlow: "REFRESH_TOKEN_AUTH", ClientId: CLIENT, AuthParameters: { REFRESH_TOKEN: "refresh-1" },
    });
    expect(JSON.parse(items.member)).toMatchObject({
      idToken: renewed, accessToken: "newaccess", refreshToken: "refresh-1", expiresAt: NOW + 900_000,
    });
  });

  it("does nothing when there is no refresh token", async () => {
    const fetchFn = ok();
    expect(await refreshIdToken(store({ member: session(staleOurs, null) }), ["member"], pools, fetchFn, NOW)).toBeNull();
    expect(fetchFn).not.toHaveBeenCalled();
  });

  it("never sends a refresh token to a pool or client the server did not list", async () => {
    const fetchFn = ok();
    const otherPool = jwt(NOW / 1000 - 600, { iss: "https://cognito-idp.us-west-2.amazonaws.com/us-west-2_Other", aud: CLIENT });
    const otherClient = jwt(NOW / 1000 - 600, { iss: ISS, aud: "someoneelse" });
    const evil = jwt(NOW / 1000 - 600, { iss: "https://evil.example/" + POOL, aud: CLIENT });
    for (const t of [otherPool, otherClient, evil, stale]) {
      expect(await refreshIdToken(store({ member: session(t, "r") }), ["member"], pools, fetchFn, NOW)).toBeNull();
    }
    expect(fetchFn).not.toHaveBeenCalled();
  });

  it("leaves storage alone and returns null when Cognito refuses or the network fails", async () => {
    const items = { member: session(staleOurs, "refresh-1") };
    const before = items.member;
    const refused = vi.fn(async () => new Response(JSON.stringify({ __type: "NotAuthorizedException" }), { status: 400 }));
    expect(await refreshIdToken(store(items), ["member"], pools, refused, NOW)).toBeNull();
    const down = vi.fn(async () => { throw new TypeError("offline"); });
    expect(await refreshIdToken(store(items), ["member"], pools, down, NOW)).toBeNull();
    expect(items.member).toBe(before);
  });

  it("tries the next stored session when the first cannot be renewed", async () => {
    const items = { admin: session(staleOurs, null), member: session(staleOurs, "refresh-2") };
    expect(await refreshIdToken(store(items), ["admin", "member"], pools, ok(), NOW)).toBe(renewed);
  });

  it("makes one request when several calls arrive together", async () => {
    const fetchFn = ok();
    const s = store({ member: session(staleOurs, "refresh-1") });
    const all = await Promise.all([1, 2, 3].map(() => refreshIdToken(s, ["member"], pools, fetchFn, NOW)));
    expect(all).toEqual([renewed, renewed, renewed]);
    expect(fetchFn).toHaveBeenCalledTimes(1);
  });
});
