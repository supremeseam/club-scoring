import { useQuery } from "@tanstack/react-query";
import { withBase } from "../lib/base";
import { pickIdToken, refreshIdToken, type Pool } from "../lib/tokens";
import type { components } from "./schema";

export type S = components["schemas"];

export type SiteConfig = {
  base_path: string;
  auth_mode: "password" | "cognito";
  sign_in_url: string;
  sign_in_links: { label: string; url: string }[];
  token_storage_keys: string[];
  cognito_pools: Pool[];
  club_name: string;
  club_short_name: string;
  tagline: string;
  website: string;
  logo_url: string;
  brand_color: string;
  brand_hex: string;
  app_name: string;
  burgee_url: string;
  require_2fa: boolean;
  password_min_length: number;
  password_max_length: number;
};

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

function cookie(name: string): string | null {
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return m ? decodeURIComponent(m[1]) : null;
}

async function csrfToken(): Promise<string> {
  const have = cookie("csrftoken");
  if (have) return have;
  const r = await fetch(withBase("/api/auth/csrf"), { credentials: "same-origin" });
  return (await r.json()).csrfToken;
}

type Opts = { method?: string; body?: unknown; form?: FormData };

type AuthSettings = { mode: string; keys: string[]; pools: Pool[] };
let signInConfig: Promise<AuthSettings> | null = null;

/** How people sign in (from /config, fetched once). Cognito mode sends the website's ID token with every request. */
export function authSettings() {
  signInConfig ??= fetch(withBase("/api/config"), { credentials: "same-origin" })
    .then((r) => r.json())
    .then((c: SiteConfig): AuthSettings => ({ mode: c.auth_mode, keys: c.token_storage_keys ?? [], pools: c.cognito_pools ?? [] }))
    .catch((): AuthSettings => ({ mode: "password", keys: [], pools: [] }));
  return signInConfig;
}

/** The ID token to send: a stored one with at least a minute left, else a renewed one, else whatever is left. */
async function bearer(auth: AuthSettings, forceRenew = false): Promise<string | null> {
  if (auth.mode !== "cognito") return null;
  const store = window.sessionStorage;
  const usable = forceRenew ? null : pickIdToken(store, auth.keys, Date.now() + 60_000);
  return usable ?? (await refreshIdToken(store, auth.keys, auth.pools)) ?? pickIdToken(store, auth.keys);
}

export async function api<T>(path: string, opts: Opts = {}): Promise<T> {
  const method = opts.method ?? "GET";
  const auth = await authSettings();
  const headers: Record<string, string> = {};
  if (method !== "GET") headers["X-CSRFToken"] = await csrfToken();
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  const send = async (idToken: string | null) =>
    fetch(withBase(`/api${path}`), {
      method, body, credentials: "same-origin",
      headers: idToken ? { ...headers, Authorization: `Bearer ${idToken}` } : headers,
    });
  let res = await send(await bearer(auth));
  // The server refused the token (it may have just expired or the keys rotated): renew once and try again.
  if (res.status === 401 && auth.mode === "cognito" && !path.startsWith("/auth/")) {
    const renewed = await bearer(auth, true);
    if (renewed) res = await send(renewed);
  }
  if (!res.ok) {
    // Tell the app shell when the login has ended or a temporary password must be replaced.
    if (res.status === 401 && !path.startsWith("/auth/")) window.dispatchEvent(new Event("session-expired"));
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j);
      if (res.status === 403 && detail === "password_change_required") {
        window.dispatchEvent(new Event("password-change-required"));
        detail = "You need to choose a new password first.";
      }
    } catch {
      /* not json */
    }
    throw new ApiError(res.status, detail);
  }
  return (res.headers.get("content-type")?.includes("json") ? res.json() : res.text()) as Promise<T>;
}

export function useGet<T>(path: string, enabled = true) {
  return useQuery<T, ApiError>({ queryKey: [path], queryFn: () => api<T>(path), enabled });
}
