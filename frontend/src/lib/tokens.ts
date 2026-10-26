/** Cognito mode: the club website's sign-in page keeps the person's tokens in this tab's session storage, as JSON
 * {idToken, accessToken, refreshToken, expiresAt} under keys the server lists in /config. We send the ID token to
 * our own API and, when it has expired, renew it with the refresh token (Cognito ID tokens are short-lived). */
type Store = { getItem(k: string): string | null; setItem(k: string, v: string): void; removeItem(k: string): void };
export type Pool = { pool_id: string; client_id: string };

function claimsOf(jwt: string): Record<string, unknown> | null {
  try {
    const payload = jwt.split(".")[1];
    return JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/")));
  } catch {
    return null;
  }
}

function expiresAtMs(jwt: string): number | null {
  const exp = claimsOf(jwt)?.exp;
  return typeof exp === "number" ? exp * 1000 : null;
}

export function pickIdToken(store: Store, keys: string[], now = Date.now()): string | null {
  for (const key of keys) {
    try {
      const raw = store.getItem(key);
      const idToken = raw ? JSON.parse(raw)?.idToken : null;
      const exp = typeof idToken === "string" ? expiresAtMs(idToken) : null;
      if (typeof idToken === "string" && exp !== null && exp > now) return idToken;
    } catch {
      /* unreadable entry or blocked storage: try the next key */
    }
  }
  return null;
}

export function clearTokens(store: Store, keys: string[]): void {
  for (const key of keys) {
    try { store.removeItem(key); } catch { /* storage unavailable */ }
  }
}

let inflight: Promise<string | null> | null = null;

/** Renew the first stored session that can be renewed, saving the new tokens where the website's page keeps them.
 * Only ever talks to a pool and app client the server listed, and returns null (changing nothing) on any failure.
 * Calls made while a renewal is running share it. */
export function refreshIdToken(store: Store, keys: string[], pools: Pool[], fetchFn: typeof fetch = fetch, now = Date.now()): Promise<string | null> {
  inflight ??= renew(store, keys, pools, fetchFn, now).finally(() => { inflight = null; });
  return inflight;
}

async function renew(store: Store, keys: string[], pools: Pool[], fetchFn: typeof fetch, now: number): Promise<string | null> {
  for (const key of keys) {
    try {
      const saved = JSON.parse(store.getItem(key) ?? "null");
      if (!saved || typeof saved.refreshToken !== "string" || typeof saved.idToken !== "string") continue;
      const claims = claimsOf(saved.idToken);
      const pool = pools.find((p) => claims?.aud === p.client_id
        && claims?.iss === `https://cognito-idp.${p.pool_id.split("_")[0]}.amazonaws.com/${p.pool_id}`);
      if (!pool) continue;
      const res = await fetchFn(`https://cognito-idp.${pool.pool_id.split("_")[0]}.amazonaws.com/`, {
        method: "POST",
        headers: { "Content-Type": "application/x-amz-json-1.1", "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth" },
        body: JSON.stringify({ AuthFlow: "REFRESH_TOKEN_AUTH", ClientId: pool.client_id, AuthParameters: { REFRESH_TOKEN: saved.refreshToken } }),
      });
      if (!res.ok) continue;
      const result = (await res.json())?.AuthenticationResult;
      if (typeof result?.IdToken !== "string") continue;
      store.setItem(key, JSON.stringify({
        ...saved, idToken: result.IdToken, accessToken: result.AccessToken ?? saved.accessToken,
        expiresAt: now + (Number(result.ExpiresIn) || 3600) * 1000,
      }));
      return result.IdToken;
    } catch {
      /* network error, bad JSON or blocked storage: leave this session as it was and try the next */
    }
  }
  return null;
}
