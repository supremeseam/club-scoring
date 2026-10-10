import { expect, test } from "@playwright/test";

// Local dev demo accounts created by `seed_demo`.
const USER = "editor";
const PASS = "editor";

test("editor sets up a series and race, enters finishes on a phone, public standings update", async ({ page, request }) => {
  const stamp = Date.now() % 100000;
  const seriesName = `E2E Series ${stamp}`;

  // --- log in
  await page.goto("/login");
  await page.getByLabel("Username").fill(USER);
  await page.getByLabel("Password").fill(PASS);
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL(/\/rc$/);

  // --- create a series with two fleets-less setup via the API helpers in the page context
  const csrf = async () => (await page.context().cookies()).find((c) => c.name === "csrftoken")!.value;
  const call = async (method: string, path: string, data?: unknown) => {
    const res = await page.request.fetch(`/api/manage${path}`, {
      method, data, headers: { "X-CSRFToken": await csrf() },
    });
    expect(res.ok(), `${method} ${path}: ${await res.text()}`).toBeTruthy();
    return res.json();
  };
  const fleets = await call("GET", "/fleets");
  const boats = await call("GET", "/boats");
  const fleet = fleets[0];
  const entered = boats.filter((b: { default_fleet_id: number }) => b.default_fleet_id === fleet.id).slice(0, 3);
  const series = await call("POST", "/series", { name: seriesName, season: 2030, fleet_ids: [fleet.id], status: "active" });
  await call("PUT", `/series/${series.id}/entries`, entered.map((b: { id: number }) => ({ boat_id: b.id, fleet_id: fleet.id })));
  const race = await call("POST", `/series/${series.id}/races`, { date: "2030-06-05", status: "sailed" });

  // --- RC race screen on a phone-sized viewport
  await page.goto(`/rc/races/${race.id}`);
  await page.getByRole("button", { name: "Set start" }).waitFor();
  await page.getByLabel("Course").click();
  await page.getByRole("option").first().click();
  await page.getByRole("button", { name: "Set start" }).click();
  await expect(page.getByRole("button", { name: "Update start" })).toBeVisible();

  // enter finish times typed from the paper sheet (start defaults to 18:00:00)
  const times = ["19:10:00", "19:20:00", "19:05:00"];
  for (const [i, b] of entered.entries()) {
    await page.getByLabel(`Finish time ${b.name}`).fill(times[i]);
  }
  await page.getByRole("button", { name: /Save .* finishes/ }).click();
  await expect(page.getByText("Finishes saved")).toBeVisible();

  // --- public standings reflect the result
  const standings = await request.get(`/api/series/${series.id}/standings`);
  expect(standings.ok()).toBeTruthy();
  const body = await standings.json();
  expect(body.fleets[0].standings).toHaveLength(3);
  expect(body.fleets[0].standings.map((r: { rank: number }) => r.rank).sort()).toEqual([1, 2, 3]);

  await page.goto(`/series/${series.id}`);
  await expect(page.getByRole("heading", { name: new RegExp(seriesName) })).toBeVisible();
  await expect(page.getByText(entered[0].name).first()).toBeVisible();
});
