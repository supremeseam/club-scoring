// Interactive first-run wizard: writes .env for your club.   npm run setup
import { randomBytes } from "node:crypto";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { createInterface } from "node:readline/promises";

const rl = createInterface({ input: process.stdin, output: process.stdout });
const ask = async (q, d = "") => ((await rl.question(d ? `${q} [${d}]: ` : `${q}: `)).trim() || d);

if (existsSync(".env") && (await ask(".env already exists. Overwrite? (y/N)", "N")).toLowerCase() !== "y") {
  console.log("Left .env unchanged.");
  process.exit(0);
}

const colors = "blue cyan teal green lime yellow orange red pink grape violet indigo";
const name = await ask("Club name", "Your Yacht Club");
const short = await ask("Short name (e.g. HYC)", name);
const app = await ask("Site name for the header", `${short} Race Results`);
const tagline = await ask("Tagline (optional)");
const hex = await ask("Brand colour as #rrggbb (optional; blank = use a named colour)");
const color = hex ? "blue" : await ask(`Named brand colour (${colors})`, "blue");
const logo = await ask("Full logo path or URL (optional, e.g. /brand/logo.png with the file in frontend/public/brand)");
const burgee = await ask("Burgee/flag alone (optional, e.g. /brand/burgee.png)");
const tz = await ask("Time zone (IANA name, e.g. America/Los_Angeles)", "America/New_York");
const domain = await ask("Public domain for production (blank = local development only)");
rl.close();

const prod = Boolean(domain);
const vals = {
  DEBUG: prod ? "0" : "1",
  REQUIRE_2FA: "0",
  SECRET_KEY: prod ? randomBytes(48).toString("base64url") : "dev-insecure-secret-key-change-me",
  ALLOWED_HOSTS: prod ? domain : "localhost,127.0.0.1",
  CSRF_TRUSTED_ORIGINS: prod ? `https://${domain}` : "",
  CLUB_NAME: name,
  CLUB_SHORT_NAME: short,
  APP_NAME: app,
  CLUB_TAGLINE: tagline,
  BRAND_COLOR: color,
  BRAND_COLOR_HEX: hex,
  CLUB_LOGO_URL: logo,
  CLUB_BURGEE_URL: burgee,
  TIME_ZONE: tz,
  PUBLIC_URL: prod ? `https://${domain}` : "http://localhost:5173",
  SITE_ADDRESS: prod ? domain : "localhost",
};

// Work line by line (and normalise Windows line endings) so no line can ever swallow its neighbour.
const lines = readFileSync(".env.example", "utf8").split(/\r?\n/);
const done = new Set();
const out = lines.map((line) => {
  const m = /^#?[ \t]*([A-Z][A-Z0-9_]*)=/.exec(line);
  if (m && m[1] in vals && !done.has(m[1])) {
    done.add(m[1]);
    return `${m[1]}=${vals[m[1]]}`;
  }
  return line;
});
for (const [k, v] of Object.entries(vals)) if (!done.has(k)) out.push(`${k}=${v}`);
writeFileSync(".env", out.join("\n") + "\n", { mode: 0o600 });
console.log(`\nWrote .env (${prod ? "production" : "local development"} settings).`);
console.log("Next:\n  npm run setup:py\n  npm run migrate\n  npm run setup:club     (creates your first admin login)\n  npm run dev");
