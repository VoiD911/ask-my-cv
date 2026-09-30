import { render, screen, within } from "@/test/intl";
import { afterEach, vi } from "vitest";
import { createInitialState, reduce, type PipelineEvent, type RunState } from "@/lib/pipeline";
import { Circuit, IN, OUT, circuitLabel, terminalStates, traces } from "./Circuit";

const ok = (name: string): PipelineEvent[] => [
  { type: "stage.start", name, ts: 1 },
  { type: "stage.end", name, status: "ok", duration_ms: 5, attrs: {} },
];

const run = (events: PipelineEvent[]): RunState => events.reduce(reduce, createInitialState());

const midRun = () =>
  run([...ok("reception"), ...ok("quota"), { type: "stage.start", name: "injection", ts: 2 }]);

const blocked = () =>
  run([
    ...ok("reception"),
    ...ok("quota"),
    { type: "stage.start", name: "injection", ts: 2 },
    {
      type: "stage.end",
      name: "injection",
      status: "blocked",
      duration_ms: 41,
      attrs: { reason: "injection_detected", score: 0.974 },
    },
  ]);

function mockReducedMotion(reduce: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: reduce && query.includes("prefers-reduced-motion"),
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("traces", () => {
  it("est au repos avant toute question", () => {
    const state = createInitialState();
    expect(traces(state).every((t) => t.state === "idle")).toBe(true);
    expect(terminalStates(state)).toEqual({ in: "standby", out: "standby" });
  });

  it("allume les pistes franchies et fait voyager l'impulsion vers l'étape active", () => {
    const t = traces(midRun());
    expect(t.slice(0, 4).map((x) => [x.from, x.to, x.state])).toEqual([
      [IN, "reception", "lit"],
      ["reception", "quota", "lit"],
      ["quota", "injection", "live"],
      ["injection", "embedding", "idle"],
    ]);
  });

  it("s'arrête sur l'étape bloquée", () => {
    const state = blocked();
    const t = traces(state);
    expect(t.find((x) => x.to === "injection")?.state).toBe("halted");
    expect(t.filter((x) => x.state === "live")).toHaveLength(0);
    const done = reduce(state, {
      type: "done",
      tokens_in: 0,
      tokens_out: 0,
      cost_usd: 0,
      latency_ms: 60,
      sources: [],
      answer_override: "…",
      trace_id: null,
    });
    expect(terminalStates(done).out).toBe("blocked");
    expect(traces(done).at(-1)).toMatchObject({ to: OUT, state: "idle" });
  });

  it("ajoute les étapes inconnues avant la sortie", () => {
    const state = run(ok("rerank"));
    expect(traces(state).at(-2)).toMatchObject({ from: "output_guard", to: "rerank" });
    expect(traces(state).at(-1)).toMatchObject({ from: "rerank", to: OUT });
  });
});

describe("Circuit", () => {
  it("décrit le circuit comme une image accessible", () => {
    mockReducedMotion(false);
    render(<Circuit state={midRun()} />);
    const img = screen.getByRole("img");
    expect(img).toHaveAccessibleName(circuitLabel(midRun()));
    expect(img.getAttribute("aria-label")).toContain("injection en cours");
  });

  it("annonce le dernier changement dans une région aria-live", () => {
    mockReducedMotion(false);
    const { rerender } = render(<Circuit state={createInitialState()} />);
    const log = screen.getByText("En attente de la requête.");
    expect(log).toHaveAttribute("aria-live", "polite");
    rerender(<Circuit state={blocked()} />);
    expect(log).toHaveTextContent("Étape injection : bloquée, score 0,974.");
  });

  it("dessine chaque étape avec son statut dans la colonne mobile", () => {
    mockReducedMotion(false);
    render(<Circuit state={blocked()} />);
    const column = screen.getByTestId("circuit-column");
    const chips = column.querySelectorAll("[data-stage]");
    expect([...chips].map((c) => c.getAttribute("data-status"))).toEqual([
      "ok",
      "ok",
      "blocked",
      "idle",
      "idle",
      "idle",
      "idle",
      "idle",
    ]);
    expect(within(column).getAllByTestId("pulse-halt")).toHaveLength(1);
  });

  it("fait voyager l'impulsion sans réduction de mouvement", () => {
    mockReducedMotion(false);
    render(<Circuit state={midRun()} />);
    const column = screen.getByTestId("circuit-column");
    expect(within(column).getAllByTestId("pulse")).toHaveLength(1);
  });

  it("n'anime rien quand le visiteur réduit les animations", () => {
    mockReducedMotion(true);
    render(<Circuit state={midRun()} />);
    expect(screen.queryAllByTestId("pulse")).toHaveLength(0);
    // L'état reste lisible : la piste vers l'étape active est marquée.
    const column = screen.getByTestId("circuit-column");
    expect(column.querySelectorAll('.trace[data-state="live"]')).toHaveLength(1);
  });

  it("affiche les mesures du run terminé", () => {
    mockReducedMotion(false);
    const state = reduce(midRun(), {
      type: "done",
      tokens_in: 100,
      tokens_out: 412,
      cost_usd: 0.00213,
      latency_ms: 2519,
      sources: [],
      answer_override: null,
      trace_id: null,
    });
    render(<Circuit state={state} />);
    expect(screen.getByText("2,52 s · 412 jetons · 0,0021 $")).toBeInTheDocument();
  });
});
