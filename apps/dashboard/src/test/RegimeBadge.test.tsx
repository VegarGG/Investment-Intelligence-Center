import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RegimeBadge } from "../components/RegimeBadge";

describe("RegimeBadge", () => {
  it("renders the upper-cased label for known regimes", () => {
    render(<RegimeBadge regime="rate_cut" />);
    expect(screen.getByText("RATE CUT")).toBeInTheDocument();
  });

  it("falls back to UNKNOWN when regime is missing", () => {
    render(<RegimeBadge regime={undefined} />);
    expect(screen.getByText(/REGIME UNKNOWN/i)).toBeInTheDocument();
  });
});
