import { describe as suite, expect, it } from "vitest";
import {
  createInitialState,
  describe,
  reduce,
  STAGES,
  type PipelineEvent,
  type RunState,
} from "./pipeline";

function run(events: PipelineEvent[]): RunState {
  return events.reduce(reduce, createInitialState());
}

suite("pipeline reduce", () => {
  it("état initial : toutes les étapes connues sont idle, dans l'ordre", () => {
    const state = createInitialState();
    expect(state.order).toEqual([...STAGES]);
    for (const name of STAGES) {
      expect(state.stages[name]).toEqual({ status: "idle", attrs: {} });
    }
    expect(state.tokens).toBe(0);
    expect(state.answer).toBeNull();
    expect(state.blockedAt).toBeNull();
  });

  it("parcours nominal : start puis end ok pour chaque étape, jusqu'à done", () => {
    const events: PipelineEvent[] = [];
    for (const name of STAGES) {
      events.push({ type: "stage.start", name, ts: 1 });
      events.push({
        type: "stage.end",
        name,
        status: "ok",
        duration_ms: 12.5,
        attrs: {},
      });
    }
    events.push({ type: "llm.progress", tokens: 42 });
    events.push({ type: "answer", text: "Voici la réponse." });
    events.push({
      type: "done",
      tokens_in: 10,
      tokens_out: 42,
      cost_usd: 0.002,
      latency_ms: 987,
      sources: ["cv.md"],
      answer_override: null,
      trace_id: "abc123",
    });

    const state = run(events);

    for (const name of STAGES) {
      expect(state.stages[name]?.status).toBe("ok");
      expect(state.stages[name]?.durationMs).toBe(12.5);
    }
    expect(state.tokens).toBe(42);
    expect(state.answer).toBe("Voici la réponse.");
    expect(state.blockedAt).toBeNull();
    expect(state.done?.trace_id).toBe("abc123");
    expect(state.override).toBeNull();

    expect(describe(state)).toContain("Terminé en 987 ms");
  });

  it("blocage à l'étape injection", () => {
    const events: PipelineEvent[] = [
      { type: "stage.start", name: "reception", ts: 1 },
      { type: "stage.end", name: "reception", status: "ok", duration_ms: 1, attrs: {} },
      { type: "stage.start", name: "quota", ts: 2 },
      { type: "stage.end", name: "quota", status: "ok", duration_ms: 1, attrs: {} },
      { type: "stage.start", name: "injection", ts: 3 },
      {
        type: "stage.end",
        name: "injection",
        status: "blocked",
        duration_ms: 4.2,
        attrs: { score: 0.97 },
      },
    ];

    const state = run(events);

    expect(state.blockedAt).toBe("injection");
    expect(state.stages.injection).toEqual({
      status: "blocked",
      durationMs: 4.2,
      attrs: { score: "0,97" },
    });
    expect(describe(state)).toBe("Étape injection : bloquée, score 0,97.");
  });

  it("bascule fallback", () => {
    const state = run([
      { type: "stage.start", name: "retrieval", ts: 1 },
      {
        type: "stage.end",
        name: "retrieval",
        status: "fallback",
        duration_ms: 5,
        attrs: { reason: "index_vide" },
      },
    ]);

    expect(state.stages.retrieval?.status).toBe("fallback");
    expect(state.blockedAt).toBeNull();
    expect(describe(state)).toBe("Étape recherche : en repli.");
  });

  it("erreur sur une étape", () => {
    const state = run([
      { type: "stage.start", name: "llm", ts: 1 },
      { type: "stage.end", name: "llm", status: "error", duration_ms: 3, attrs: {} },
    ]);

    expect(state.stages.llm?.status).toBe("error");
    expect(describe(state)).toBe("Étape LLM : en erreur.");
  });

  it("étape inconnue : ajoutée à la fin de l'ordre d'affichage", () => {
    const state = run([
      { type: "stage.start", name: "reception", ts: 1 },
      { type: "stage.end", name: "reception", status: "ok", duration_ms: 1, attrs: {} },
      { type: "stage.start", name: "cache", ts: 2 },
      {
        type: "stage.end",
        name: "cache",
        status: "ok",
        duration_ms: 0.5,
        attrs: { hit: true },
      },
    ]);

    expect(state.order).toEqual([...STAGES, "cache"]);
    expect(state.stages.cache).toEqual({
      status: "ok",
      durationMs: 0.5,
      attrs: { hit: "vrai" },
    });
  });

  it("idempotence d'un done répété", () => {
    const doneEvent: PipelineEvent = {
      type: "done",
      tokens_in: 1,
      tokens_out: 2,
      cost_usd: 0.001,
      latency_ms: 100,
      sources: [],
      answer_override: "réponse de repli",
      trace_id: null,
    };

    const once = run([doneEvent]);
    const twice = run([doneEvent, doneEvent]);

    expect(once).toEqual(twice);
    expect(once.override).toBe("réponse de repli");
  });
});
