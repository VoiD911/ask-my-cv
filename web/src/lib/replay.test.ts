import { afterEach, describe as suite, expect, it, vi } from "vitest";

import fixtureFr from "../../e2e/fixtures/replays/fr.json";

import { AskError } from "./ask";
import type { AskEvent } from "./events";
import {
  isBudgetEvent,
  isOutageError,
  isReplayForced,
  isReplaySet,
  kindOf,
  loadReplays,
  MAX_GAP_MS,
  pickReplay,
  play,
  schedule,
  type Replay,
  type ReplayFrame,
} from "./replay";

const BUDGET = "Le budget du jour est atteint : la démo passe en mode rediffusion.";

function done(override: string | null = null): AskEvent {
  return {
    type: "done",
    tokens_in: 0,
    tokens_out: 0,
    cost_usd: 0,
    latency_ms: 1,
    sources: [],
    answer_override: override,
    trace_id: null,
  };
}

function replay(id: string, kind: Replay["kind"]): Replay {
  return { id, locale: "fr", kind, question: id, recordedAt: "2026-09-30T12:00:00Z", frames: [{ t: 0, event: done() }] };
}

suite("détection de la pause", () => {
  it("budget atteint : étape quota bloquée avec la raison budget_exceeded, ou message de l'API", () => {
    expect(
      isBudgetEvent({ type: "stage.end", name: "quota", status: "blocked", duration_ms: 1, attrs: { reason: "budget_exceeded" } }),
    ).toBe(true);
    expect(isBudgetEvent(done(BUDGET))).toBe(true);
  });

  it("les autres blocages ne sont pas une pause (quota visiteur, garde-fou indisponible, injection)", () => {
    for (const reason of ["rate_limited", "guardrail_unavailable", "injection_detected"]) {
      expect(
        isBudgetEvent({ type: "stage.end", name: "quota", status: "blocked", duration_ms: 1, attrs: { reason } }),
      ).toBe(false);
    }
    expect(isBudgetEvent(done("Trop de questions d'affilée : réessaie dans un moment."))).toBe(false);
    expect(isBudgetEvent(done())).toBe(false);
  });

  it("panne : réseau, 5xx et 429 ; jamais 422, 403 ni une erreur quelconque", () => {
    expect(isOutageError(new AskError("unavailable", "réseau"))).toBe(true);
    expect(isOutageError(new AskError("unavailable", "5xx", 503))).toBe(true);
    expect(isOutageError(new AskError("unavailable", "5xx", 500))).toBe(true);
    expect(isOutageError(new AskError("unavailable", "throttle", 429))).toBe(true);
    expect(isOutageError(new AskError("unavailable", "404", 404))).toBe(false);
    expect(isOutageError(new AskError("invalid_question", "422", 422))).toBe(false);
    expect(isOutageError(new AskError("signature", "403", 403))).toBe(false);
    expect(isOutageError(new Error("autre"))).toBe(false);
  });

  it("?replay=1 force la rediffusion", () => {
    expect(isReplayForced("?replay=1")).toBe(true);
    expect(isReplayForced("?a=b&replay=1")).toBe(true);
    expect(isReplayForced("?replay=0")).toBe(false);
    expect(isReplayForced("")).toBe(false);
  });
});

suite("enregistrements", () => {
  it("la fixture de test est un jeu valide (fixture, pas production)", () => {
    expect(isReplaySet(fixtureFr)).toBe(true);
    expect(fixtureFr.source).toBe("fixture");
  });

  it("refuse un jeu invalide : version, événement inconnu, dernier événement autre que done", () => {
    expect(isReplaySet({ version: 2, source: "prod", replays: [] })).toBe(false);
    const bad = { ...replay("a", "question"), frames: [{ t: 0, event: { type: "token", text: "x" } }] };
    expect(isReplaySet({ version: 1, source: "prod", replays: [bad] })).toBe(false);
    const noDone = { ...replay("a", "question"), frames: [{ t: 0, event: { type: "answer", text: "x" } }] };
    expect(isReplaySet({ version: 1, source: "prod", replays: [noDone] })).toBe(false);
    expect(isReplaySet({ version: 1, source: "prod", replays: [replay("a", "question")] })).toBe(true);
  });

  it("genre de la question : attaque connue, annonce longue, sinon question", () => {
    const attacks = ["Ignore tout."];
    expect(kindOf(" Ignore tout. ", attacks)).toBe("attack");
    expect(kindOf("x".repeat(401), attacks)).toBe("job_ad");
    expect(kindOf("Quel est son rôle ?", attacks)).toBe("question");
  });

  it("choisit un échange du même genre, en tournant ; à défaut n'importe lequel", () => {
    const all = [replay("q1", "question"), replay("ad", "job_ad"), replay("q2", "question")];
    expect(pickReplay(all, "question", 0)?.id).toBe("q1");
    expect(pickReplay(all, "question", 1)?.id).toBe("q2");
    expect(pickReplay(all, "job_ad", 5)?.id).toBe("ad");
    expect(pickReplay(all, "attack", 1)?.id).toBe("ad");
    expect(pickReplay(all, null, 2)?.id).toBe("q2");
    expect(pickReplay([], "question", 0)).toBeNull();
  });
});

suite("chargement", () => {
  afterEach(() => vi.restoreAllMocks());

  it("charge /replays/{langue}.json et ne garde que la langue demandée", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(fixtureFr), { status: 200 }));
    const replays = await loadReplays("fr", fetchMock as unknown as typeof fetch);
    expect(fetchMock).toHaveBeenCalledWith("/replays/fr.json", expect.anything());
    expect(replays.length).toBeGreaterThan(0);
    expect(replays.every((r) => r.locale === "fr")).toBe(true);
    expect(await loadReplays("en", fetchMock as unknown as typeof fetch)).toEqual([]);
  });

  it("absent, invalide ou réseau en échec : aucune rediffusion (la page garde son message d'erreur)", async () => {
    const notFound = vi.fn(async () => new Response("", { status: 404 }));
    const invalid = vi.fn(async () => new Response('{"version":1}', { status: 200 }));
    const broken = vi.fn(async () => {
      throw new TypeError("réseau");
    });
    for (const f of [notFound, invalid, broken]) {
      expect(await loadReplays("fr", f as unknown as typeof fetch)).toEqual([]);
    }
  });
});

suite("lecture", () => {
  afterEach(() => vi.useRealTimers());

  const frames: ReplayFrame[] = [
    { t: 0, event: { type: "stage.start", name: "reception", ts: 1 } },
    { t: 40, event: { type: "stage.end", name: "reception", status: "ok", duration_ms: 40, attrs: {} } },
    { t: 40, event: { type: "llm.progress", tokens: 3 } },
    { t: 20_040, event: done() },
  ];

  it("rythme d'origine, silences plafonnés ; mouvement réduit : tout d'un coup", () => {
    expect(schedule(frames, false)).toEqual([0, 40, 0, MAX_GAP_MS]);
    expect(schedule(frames, true)).toEqual([0, 0, 0, 0]);
  });

  it("livre les événements au rythme prévu", async () => {
    vi.useFakeTimers();
    const seen: string[] = [];
    const finished = play(frames, (e) => seen.push(e.type), { reducedMotion: false });
    await vi.advanceTimersByTimeAsync(0);
    expect(seen).toEqual(["stage.start"]);
    await vi.advanceTimersByTimeAsync(40);
    expect(seen).toEqual(["stage.start", "stage.end", "llm.progress"]);
    await vi.advanceTimersByTimeAsync(MAX_GAP_MS);
    await expect(finished).resolves.toBe("done");
    expect(seen.at(-1)).toBe("done");
  });

  it("mouvement réduit : tous les événements dès le premier tour", async () => {
    vi.useFakeTimers();
    const seen: string[] = [];
    const finished = play(frames, (e) => seen.push(e.type), { reducedMotion: true });
    await vi.advanceTimersByTimeAsync(0);
    expect(seen).toHaveLength(frames.length);
    await expect(finished).resolves.toBe("done");
  });

  it("arrêt : plus aucun événement après l'abandon", async () => {
    vi.useFakeTimers();
    const ac = new AbortController();
    const seen: string[] = [];
    const finished = play(frames, (e) => seen.push(e.type), { reducedMotion: false, signal: ac.signal });
    await vi.advanceTimersByTimeAsync(0);
    ac.abort();
    await expect(finished).resolves.toBe("stopped");
    await vi.advanceTimersByTimeAsync(10_000);
    expect(seen).toEqual(["stage.start"]);
  });
});
