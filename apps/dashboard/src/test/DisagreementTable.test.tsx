import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DisagreementTable } from "../components/DisagreementTable";
import type { AdviceV1 } from "../types/iic";

function advice(over: Partial<AdviceV1>): AdviceV1 {
  return {
    schema: "advice.v1",
    id: over.id ?? "01HXAAAAAAAAAAAAAAAAAAAAAB",
    agent: "quant",
    issued_at: new Date().toISOString(),
    asset: { kind: "equity", ticker: "INTC", venue: "NASDAQ" },
    thesis: "Default thesis",
    direction: "long",
    confidence: 0.6,
    entry_band: [100, 100],
    target_band: [110, 115],
    stop_loss: 95,
    horizon_days: 30,
    max_drawdown_pct: 10,
    sizing_hint_pct_nav: 2,
    expires_at: new Date(Date.now() + 30 * 86400_000).toISOString(),
    evidence: [{ kind: "factor", ref: "x" }],
    ...over,
  };
}

describe("DisagreementTable", () => {
  it("hides table when all directions agree", () => {
    render(
      <DisagreementTable
        ticker="INTC"
        advices={[
          advice({ id: "01HXAAAAAAAAAAAAAAAAAAAAA1", agent: "quant", direction: "long" }),
          advice({ id: "01HXAAAAAAAAAAAAAAAAAAAAA2", agent: "fundamental", direction: "long" }),
        ]}
      />,
    );
    expect(screen.getByText(/No disagreement/i)).toBeInTheDocument();
  });

  it("renders rows when directions conflict", () => {
    render(
      <DisagreementTable
        ticker="INTC"
        advices={[
          advice({ id: "01HXAAAAAAAAAAAAAAAAAAAAA1", agent: "quant", direction: "long" }),
          advice({
            id: "01HXAAAAAAAAAAAAAAAAAAAAA2",
            agent: "persona.burry",
            direction: "short",
            entry_band: [100, 100],
            target_band: [85, 90],
            stop_loss: 105,
          }),
        ]}
      />,
    );
    expect(screen.getByText("quant")).toBeInTheDocument();
    expect(screen.getByText("persona.burry")).toBeInTheDocument();
    expect(screen.getByText("long")).toBeInTheDocument();
    expect(screen.getByText("short")).toBeInTheDocument();
  });
});
