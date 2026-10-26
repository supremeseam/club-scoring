import { useQuery } from "@tanstack/react-query";
import { withBase } from "../lib/base";
import { pickIdToken } from "../lib/tokens";
import type { components } from "./schema";

export type S = components["schemas"];

export type SiteConfig = {
  base_path: string;
  auth_mode: "password" | "cognito";
  sign_in_url: string;
  token_storage_keys: string[];
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

let signInConfig: Promise<{ mode: string; keys: string[] }> | null = null;

/** How people sign in (from /config, fetched once). Cognito mode sends the website's ID token with every request. */
export function authSettings() {
  signInConfig ??= fetch(withBase("/api/config"), { credentials: "same-origin" })
    .then((r) => r.json())
    .then((c: SiteConfig) => ({ mode: c.auth_mode, keys: c.token_storage_keys ?? [] }))
    .catch(() => ({ mode: "password", keys: [] }));
  return signInConfig;
}

export async function api<T>(path: string, opts: Opts = {}): Promise<T> {
  const method = opts.method ?? "GET";
  const headers: Record<string, string> = {};
  const auth = await authSettings();
  const idToken = auth.mode === "cognito" ? pickIdToken(window.sessionStorage, auth.keys) : null;
  if (idToken) headers.Authorization = `Bearer ${idToken}`;
  if (method !== "GET") headers["X-CSRFToken"] = await csrfToken();
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  const res = await fetch(withBase(`/api${path}`), { method, headers, body, credentials: "same-origin" });
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
