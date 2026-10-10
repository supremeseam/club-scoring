import { createTheme, type MantineColorsTuple, type MantineThemeOverride } from "@mantine/core";
import type { SiteConfig } from "./api/client";

/**
 * The whole look hangs off ONE colour (BRAND_COLOR_HEX in .env). Everything else, from buttons to the
 * hero banner, table headers and badges, is derived from the 10-step scale below. To restyle the app,
 * change the colour, the two fonts, or the radius here; nothing else needs to be touched.
 */
type RGB = [number, number, number];

export function parseHex(hex: string): RGB | null {
  const m = /^#([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return null;
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

const toHex = (c: RGB) => "#" + c.map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, "0")).join("");
const mix = (a: RGB, b: RGB, t: number): RGB => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];

/** 10 shades, lightest to darkest. Index 7 is the brand colour itself (buttons, headers). */
export function makeBrandScale(hex: string): MantineColorsTuple | null {
  const base = parseHex(hex);
  if (!base) return null;
  const white: RGB = [255, 255, 255];
  const black: RGB = [0, 0, 0];
  const tints = [0.95, 0.88, 0.76, 0.6, 0.42, 0.26, 0.12].map((t) => toHex(mix(base, white, t)));
  return [...tints, toHex(base), toHex(mix(base, black, 0.28)), toHex(mix(base, black, 0.5))] as unknown as MantineColorsTuple;
}

export function makeTheme(cfg?: Pick<SiteConfig, "brand_hex" | "brand_color">): MantineThemeOverride {
  const scale = cfg?.brand_hex ? makeBrandScale(cfg.brand_hex) : null;
  return createTheme({
    ...(scale
      ? { colors: { brand: scale }, primaryColor: "brand", primaryShade: { light: 7, dark: 4 } }
      : { primaryColor: cfg?.brand_color ?? "blue" }),
    fontFamily: '"Inter Variable", system-ui, -apple-system, "Segoe UI", sans-serif',
    headings: { fontFamily: '"Source Serif 4 Variable", Georgia, "Times New Roman", serif', fontWeight: "600" },
    defaultRadius: "md",
    components: {
      Card: { defaultProps: { radius: "lg", shadow: "sm" } },
      Button: { defaultProps: { radius: "xl" } },
      Badge: { defaultProps: { radius: "sm" } },
    },
  });
}
