import { defineConfig, devices } from "@playwright/test";

// Expects the dev stack to be up (`npm run dev`) with demo data seeded (`npm run seed`).
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  retries: 0,
  use: { baseURL: process.env.E2E_URL ?? "http://localhost:5173", trace: "retain-on-failure" },
  projects: [{ name: "phone", use: { ...devices["Pixel 7"] } }],
});
