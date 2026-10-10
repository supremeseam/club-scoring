import { describe, expect, it } from "vitest";
import { makeBrandScale, parseHex } from "./theme";

describe("brand scale", () => {
  it("parses #rrggbb and rejects junk", () => {
    expect(parseHex("#000767")).toEqual([0, 7, 103]);
    expect(parseHex("navy")).toBeNull();
    expect(parseHex("#12345")).toBeNull();
  });
  it("makes 10 shades with the brand colour at index 7, light to dark", () => {
    const s = makeBrandScale("#000767")!;
    expect(s).toHaveLength(10);
    expect(s[7]).toBe("#000767");
    expect(s[0] > s[6]).toBe(true); // tints get lighter toward index 0 (hex strings compare numerically here)
    expect(s[9] < s[7]).toBe(true); // shades get darker toward index 9
  });
  it("returns null for an invalid colour so the named colour is used", () => {
    expect(makeBrandScale("blue")).toBeNull();
  });
});
