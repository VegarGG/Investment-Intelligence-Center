import type { MacroRegime } from "../types/iic";
import { Badge } from "./ui/Card";

const TONE: Record<MacroRegime, "default" | "good" | "warn" | "bad"> = {
  rate_cut: "good",
  risk_on: "good",
  risk_off: "warn",
  stagflation: "warn",
  recession: "bad",
  crisis: "bad",
  unknown: "default",
};

const LABEL: Record<MacroRegime, string> = {
  rate_cut: "RATE CUT",
  risk_on: "RISK ON",
  risk_off: "RISK OFF",
  stagflation: "STAGFLATION",
  recession: "RECESSION",
  crisis: "CRISIS",
  unknown: "REGIME UNKNOWN",
};

export function RegimeBadge({ regime }: { regime: MacroRegime | undefined }) {
  const r = regime ?? "unknown";
  return <Badge tone={TONE[r]}>{LABEL[r]}</Badge>;
}
