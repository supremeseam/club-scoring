import { describe, expect, it } from "vitest";
import { addDays, buildFinishIso, fmtPoints, needsNextDay, parseTimeInput } from "./time";

describe("parseTimeInput", () => {
  it("accepts common forms", () => {
    expect(parseTimeInput("18:42:07")).toBe("18:42:07");
    expect(parseTimeInput("7:05")).toBe("07:05:00");
    expect(parseTimeInput("184207")).toBe("18:42:07");
    expect(parseTimeInput("1842")).toBe("18:42:00");
  });
  it("rejects junk", () => {
    for (const bad of ["", "25:00:00", "12:61", "abc", "12:3:4:5", "12"]) expect(parseTimeInput(bad)).toBeNull();
  });
});

describe("after midnight", () => {
  const start = "2027-06-02T23:30:00";
  it("flags a finish earlier than the start clock time", () => {
    expect(needsNextDay(start, "01:15:00")).toBe(true);
    expect(needsNextDay(start, "23:59:00")).toBe(false);
  });
  it("builds next-day datetimes, including across month ends", () => {
    expect(buildFinishIso(start, "01:15:00", true)).toBe("2027-06-03T01:15:00");
    expect(addDays("2027-06-30", 1)).toBe("2027-07-01");
    expect(addDays("2027-12-31", 1)).toBe("2028-01-01");
  });
});

describe("fmtPoints", () => {
  it("shows integers plainly and averages to one decimal", () => {
    expect(fmtPoints(3)).toBe("3");
    expect(fmtPoints(1.5)).toBe("1.5");
    expect(fmtPoints(null)).toBe("");
  });
});
