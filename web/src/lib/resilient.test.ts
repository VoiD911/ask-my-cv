import { afterEach, describe as suite, expect, it, vi } from "vitest";

import { AskError, type AskParams } from "./ask";
import type { AskEvent } from "./events";
import { askResilient } from "./resilient";

const START: AskEvent = { type: "stage.start", name: "reception", ts: 1 };
const BUDGET_END: AskEvent = {
  type: "stage.end",
  name: "quota",
  status: "blocked",
  duration_ms: 3,
  attrs: { reason: "budget_exceeded" },
};

type Script = (params: AskParams) => Promise<void>;

/** Faux `ask` : une réponse scriptée par tentative. */
function fakeAsk(...attempts: Script[]) {
  let i = 0;
  const impl = vi.fn(async (params: AskParams) => {
    const script = attempts[Math.min(i, attempts.length - 1)] as Script;
    i += 1;
    await script(params);
  });
  return impl;
}

const DONE: AskEvent = {
  type: "done",
  tokens_in: 1,
  tokens_out: 1,
  cost_usd: 0,
  latency_ms: 1,
  sources: [],
  answer_override: null,
  trace_id: null,
};
const ok: Script = async ({ onEvent }) => {
  onEvent(START);
  onEvent(DONE);
};
const outage: Script = async () => {
  throw new AskError("unavailable", "service indisponible (503)", 503);
};

function run(askImpl: ReturnType<typeof fakeAsk>, signal = new AbortController().signal) {
  const events: AskEvent[] = [];
  const outcome = askResilient({
    question: "q",
    signal,
    onEvent: (e) => events.push(e),
    retryDelayMs: 0,
    askImpl,
  });
  return { outcome, events };
}

suite("askResilient", () => {
  afterEach(() => vi.useRealTimers());

  it("réponse normale : ok, une seule tentative", async () => {
    const impl = fakeAsk(ok);
    const { outcome, events } = run(impl);
    await expect(outcome).resolves.toEqual({ kind: "ok" });
    expect(impl).toHaveBeenCalledTimes(1);
    expect(events).toEqual([START, DONE]);
  });

  it("budget atteint (réponse 200 bloquée au quota) : pause « budget », sans nouvelle tentative", async () => {
    const impl = fakeAsk(async ({ onEvent }) => {
      onEvent(START);
      onEvent(BUDGET_END);
      onEvent({ ...DONE, answer_override: "Le budget du jour est atteint : la démo passe en mode rediffusion." });
    });
    const { outcome } = run(impl);
    await expect(outcome).resolves.toEqual({ kind: "paused", reason: "budget" });
    expect(impl).toHaveBeenCalledTimes(1);
  });

  it("503 puis succès : une nouvelle tentative suffit", async () => {
    const impl = fakeAsk(outage, ok);
    await expect(run(impl).outcome).resolves.toEqual({ kind: "ok" });
    expect(impl).toHaveBeenCalledTimes(2);
  });

  it("5xx ou réseau deux fois : pause « unavailable » après une seule nouvelle tentative", async () => {
    const network: Script = async () => {
      throw new AskError("unavailable", "service indisponible (réseau)");
    };
    const impl = fakeAsk(outage, network);
    await expect(run(impl).outcome).resolves.toEqual({ kind: "paused", reason: "unavailable" });
    expect(impl).toHaveBeenCalledTimes(2);
  });

  it("flux coupé après des événements : pause sans nouvelle tentative (pas d'étapes en double)", async () => {
    const impl = fakeAsk(async ({ onEvent }) => {
      onEvent(START);
      throw new AskError("unavailable", "flux interrompu");
    });
    await expect(run(impl).outcome).resolves.toEqual({ kind: "paused", reason: "unavailable" });
    expect(impl).toHaveBeenCalledTimes(1);
  });

  it("flux clos proprement sans done ni événement : nouvelle tentative, puis pause", async () => {
    const empty: Script = async () => {};
    const impl = fakeAsk(empty);
    await expect(run(impl).outcome).resolves.toEqual({ kind: "paused", reason: "unavailable" });
    expect(impl).toHaveBeenCalledTimes(2);
    const recovered = fakeAsk(empty, ok);
    await expect(run(recovered).outcome).resolves.toEqual({ kind: "ok" });
  });

  it("flux clos sans done après des événements : pause sans nouvelle tentative", async () => {
    const truncated: Script = async ({ onEvent }) => onEvent(START);
    const impl = fakeAsk(truncated);
    await expect(run(impl).outcome).resolves.toEqual({ kind: "paused", reason: "unavailable" });
    expect(impl).toHaveBeenCalledTimes(1);
  });

  it("aucun événement dans le délai : abandon, nouvelle tentative, puis pause", async () => {
    vi.useFakeTimers();
    const hang: Script = ({ signal }) =>
      new Promise((_, reject) => {
        signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
      });
    const impl = fakeAsk(hang);
    const outcome = askResilient({
      question: "q",
      signal: new AbortController().signal,
      onEvent: () => {},
      firstEventTimeoutMs: 1_000,
      retryDelayMs: 0,
      askImpl: impl,
    });
    await vi.advanceTimersByTimeAsync(2_100);
    await expect(outcome).resolves.toEqual({ kind: "paused", reason: "unavailable" });
    expect(impl).toHaveBeenCalledTimes(2);
  });

  it("question invalide (422) ou signature (403) : erreur propagée, pas de rediffusion", async () => {
    const invalid: Script = async () => {
      throw new AskError("invalid_question", "question invalide", 422);
    };
    await expect(run(fakeAsk(invalid)).outcome).rejects.toMatchObject({ kind: "invalid_question" });
    const signature: Script = async () => {
      throw new AskError("signature", "signature refusée", 403);
    };
    await expect(run(fakeAsk(signature)).outcome).rejects.toMatchObject({ kind: "signature" });
  });

  it("arrêt du visiteur : AbortError propagée, jamais de pause ni de nouvelle tentative", async () => {
    const ac = new AbortController();
    const impl = fakeAsk(
      ({ signal }) =>
        new Promise((_, reject) => {
          signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
        }),
    );
    const { outcome } = run(impl, ac.signal);
    ac.abort();
    await expect(outcome).rejects.toMatchObject({ name: "AbortError" });
    expect(impl).toHaveBeenCalledTimes(1);
  });
});
