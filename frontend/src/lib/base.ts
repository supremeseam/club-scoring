/** The sub-path the app is served under ("" at the site root), fixed at build time by BASE_PATH. */
export function baseFromUrl(baseUrl: string): string {
  return baseUrl.replace(/\/+$/, "");
}

export const BASE = baseFromUrl(import.meta.env.BASE_URL);

/** Prefix a site-absolute path ("/api/...") with the base; full URLs pass through. */
export function joinBase(base: string, path: string): string {
  return path.startsWith("/") && !path.startsWith("//") ? base + path : path;
}

export const withBase = (path: string) => joinBase(BASE, path);
