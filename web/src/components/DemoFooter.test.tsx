import { render, screen } from "@testing-library/react";
import { describe as suite, expect, it } from "vitest";

import { DemoFooter, formatCost, usableTraceId } from "./DemoFooter";

/** Intl fr-FR sépare par des espaces insécables : on les normalise pour comparer. */
const plain = (s: string | null) => (s ?? "").replace(/[  ]/g, " ");

suite("DemoFooter", () => {
  it("formate le coût en dollars avec 4 à 6 décimales", () => {
    expect(plain(formatCost(0))).toBe("0,0000 $");
    expect(plain(formatCost(0.00123456))).toBe("0,001235 $");
    expect(plain(formatCost(0.0125))).toBe("0,0125 $");
  });

  it("ignore un identifiant de trace nul", () => {
    expect(usableTraceId(null)).toBeNull();
    expect(usableTraceId("0".repeat(32))).toBeNull();
    expect(usableTraceId("4bf92f3577b34da6a3ce929d0e0e4736")).toBe("4bf92f3577b34da6a3ce929d0e0e4736");
  });

  it("affiche des tirets avant toute question", () => {
    render(<DemoFooter done={null} />);
    expect(screen.getByTestId("readout-latency")).toHaveTextContent("—");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("remplit le relevé et propose de copier la trace", () => {
    render(
      <DemoFooter
        done={{
          type: "done",
          tokens_in: 1234,
          tokens_out: 56,
          cost_usd: 0.000789,
          latency_ms: 1520,
          sources: [],
          answer_override: null,
          trace_id: "4bf92f3577b34da6a3ce929d0e0e4736",
        }}
      />,
    );
    expect(plain(screen.getByTestId("readout-latency").textContent)).toContain("1,52 s");
    expect(plain(screen.getByTestId("readout-tokens-in").textContent)).toContain("1 234");
    expect(plain(screen.getByTestId("readout-cost").textContent)).toContain("0,000789 $");
    expect(screen.getByText("4bf92f3577b34da6a3ce929d0e0e4736")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copier l'identifiant de trace" })).toBeInTheDocument();
  });
});
