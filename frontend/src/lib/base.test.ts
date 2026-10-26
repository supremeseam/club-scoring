import { describe, expect, it } from "vitest";
import { baseFromUrl, joinBase } from "./base";

describe("baseFromUrl", () => {
  it("is empty at the site root", () => {
    expect(baseFromUrl("/")).toBe("");
    expect(baseFromUrl("")).toBe("");
  });
  it("drops the trailing slash of a sub-path", () => {
    expect(baseFromUrl("/results/")).toBe("/results");
    expect(baseFromUrl("/club/results/")).toBe("/club/results");
  });
});

describe("joinBase", () => {
  it("leaves paths alone at the site root", () => {
    expect(joinBase("", "/api/config")).toBe("/api/config");
  });
  it("prefixes site-absolute paths under a sub-path", () => {
    expect(joinBase("/results", "/api/races/3/podium.pdf")).toBe("/results/api/races/3/podium.pdf");
  });
  it("never touches full URLs", () => {
    expect(joinBase("/results", "https://cdn.example/logo.png")).toBe("https://cdn.example/logo.png");
  });
});
