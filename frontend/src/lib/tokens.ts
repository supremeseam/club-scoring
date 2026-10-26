/** Cognito mode: the club website's sign-in page keeps the person's tokens in this tab's session storage, as JSON
 * {idToken, ...} under keys the server lists in /config. We only read the ID token and send it to our own API. */
type Store = { getItem(k: string): string | null; removeItem(k: string): void };

function expiresAtMs(jwt: string): number | null {
  try {
    const payload = jwt.split(".")[1];
    const json = JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/")));
    return typeof json.exp === "number" ? json.exp * 1000 : null;
  } catch {
    return null;
  }
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
