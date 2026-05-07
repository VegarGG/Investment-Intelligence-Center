import { describe, expect, it } from "vitest";

import { bandLabel, formatPct, formatPnlR, formatTimestamp } from "../lib/format";

describe("format helpers", () => {
  it("formatPct renders percentage with one decimal", () => {
    expect(formatPct(0.1234)).toBe("12.3%");
  });

  it("formatPct handles null", () => {
    expect(formatPct(null)).toBe("—");
    expect(formatPct(undefined)).toBe("—");
  });

  it("formatPnlR keeps signed two decimals + R", () => {
    expect(formatPnlR(1.5)).toBe("+1.50R");
    expect(formatPnlR(-0.7)).toBe("-0.70R");
  });

  it("bandLabel renders ascending range", () => {
    expect(bandLabel([100, 105])).toBe("100.00–105.00");
  });

  it("bandLabel collapses identical bounds", () => {
    expect(bandLabel([100, 100])).toBe("100.00");
  });

  it("formatTimestamp survives bad input", () => {
    expect(formatTimestamp(null)).toBe("—");
    expect(formatTimestamp("not-a-date")).toBe("not-a-date");
  });
});
