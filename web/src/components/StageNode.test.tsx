import { render, screen } from "@testing-library/react";
import type { StageState } from "@/lib/pipeline";
import { StageNode, Terminal, formatDuration, keyAttrs } from "./StageNode";

const stage = (s: Partial<StageState>): StageState => ({ status: "idle", attrs: {}, ...s });

describe("StageNode", () => {
  it.each([
    ["idle", "en attente"],
    ["active", "en cours"],
    ["ok", "terminée"],
    ["blocked", "bloquée"],
    ["error", "en erreur"],
    ["fallback", "en repli"],
  ] as const)("expose le statut %s", (status, label) => {
    const { container } = render(<StageNode name="quota" index={1} stage={stage({ status })} />);
    expect(container.firstChild).toHaveAttribute("data-status", status);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it("affiche repère, libellé français, identifiant, durée et attributs clés", () => {
    render(
      <StageNode
        name="retrieval"
        index={4}
        stage={stage({
          status: "ok",
          durationMs: 18,
          attrs: { top_score: "0,812", extra: "x", hits: "6" },
        })}
      />,
    );
    expect(screen.getByText("U5")).toBeInTheDocument();
    expect(screen.getByText("recherche")).toBeInTheDocument();
    expect(screen.getByText("retrieval")).toBeInTheDocument();
    expect(screen.getByText("18 ms")).toBeInTheDocument();
    const keys = screen.getAllByRole("term").map((el) => el.textContent);
    expect(keys).toEqual(["hits", "top_score"]);
  });
});

describe("keyAttrs", () => {
  it("met la cause du blocage en premier", () => {
    const attrs = keyAttrs("injection", stage({
      status: "blocked",
      attrs: { model_version: "v1.2.0", score: "0,974", reason: "injection_detected" },
    }));
    expect(attrs).toEqual([
      ["reason", "injection_detected"],
      ["score", "0,974"],
    ]);
  });

  it("désigne le garde-fou Bedrock quand c'est lui qui bloque l'annonce", () => {
    const attrs = keyAttrs("injection", stage({
      status: "blocked",
      attrs: {
        model_version: "onnx-v1.4.0",
        score: "0,12",
        guardrail: "block",
        reason: "injection_detected",
        blocked_by: "guardrail",
      },
    }));
    expect(attrs).toEqual([
      ["reason", "injection_detected"],
      ["blocked_by", "guardrail"],
    ]);
  });

  it("montre les jetons reçus pendant la génération", () => {
    expect(keyAttrs("llm", stage({ status: "active" }), 1234)).toEqual([["tokens", "1 234"]]);
    expect(keyAttrs("llm", stage({ status: "active" }), 0)).toEqual([]);
  });

  it("retombe sur les premiers attributs d'une étape inconnue", () => {
    expect(keyAttrs("rerank", stage({ status: "ok", attrs: { a: "1", b: "2", c: "3" } }))).toEqual([
      ["a", "1"],
      ["b", "2"],
    ]);
  });
});

describe("formatDuration", () => {
  it("passe en secondes au-delà de 1 000 ms", () => {
    expect(formatDuration(41)).toBe("41 ms");
    expect(formatDuration(2519)).toBe("2,52 s");
  });
});

describe("Terminal", () => {
  it("expose son type et son état", () => {
    const { container } = render(<Terminal kind="out" state="ok" />);
    expect(container.firstChild).toHaveAttribute("data-kind", "out");
    expect(container.firstChild).toHaveAttribute("data-state", "ok");
    expect(screen.getByText("réponse")).toBeInTheDocument();
  });
});
