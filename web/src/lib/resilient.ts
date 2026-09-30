/**
 * Appel de `POST /api/ask` tolérant aux pannes : délai maximal avant le premier événement,
 * une nouvelle tentative si rien n'est arrivé, puis verdict « en pause » que la page traduit en
 * rediffusion. Le budget du jour atteint (réponse 200 bloquée à l'étape `quota`) est aussi une
 * pause, sans nouvelle tentative : réessayer ne changerait rien avant minuit.
 */

import { ask, type AskParams } from "./ask";
import type { AskEvent } from "./events";
import { isBudgetEvent, isOutageError, type OutageReason } from "./replay";

export type AskOutcome = { readonly kind: "ok" } | { readonly kind: "paused"; readonly reason: OutageReason };

export interface ResilientParams {
  readonly question: string;
  readonly model?: string | null;
  /** Arrêt demandé par le visiteur : l'`AbortError` est propagée telle quelle. */
  readonly signal: AbortSignal;
  readonly onEvent: (event: AskEvent) => void;
  /** Délai avant le premier événement SSE (la réception l'émet tout de suite). */
  readonly firstEventTimeoutMs?: number;
  /** Attente avant la seconde tentative. */
  readonly retryDelayMs?: number;
  readonly askImpl?: (params: AskParams) => Promise<void>;
}

export const FIRST_EVENT_TIMEOUT_MS = 20_000;
export const RETRY_DELAY_MS = 1_000;

function wait(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(signal.reason);
      return;
    }
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(timer);
      reject(signal.reason);
    };
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

class FirstEventTimeout extends Error {}

/** Une tentative ; `onFirst` signale chaque événement reçu (le délai ne court plus ensuite). */
async function attempt(
  params: ResilientParams,
  onFirst: () => void,
): Promise<void> {
  const { signal, firstEventTimeoutMs = FIRST_EVENT_TIMEOUT_MS, askImpl = ask } = params;
  const local = new AbortController();
  const forward = () => local.abort(signal.reason);
  signal.addEventListener("abort", forward, { once: true });
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    local.abort();
  }, firstEventTimeoutMs);
  try {
    await askImpl({
      question: params.question,
      model: params.model ?? null,
      signal: local.signal,
      onEvent: (event) => {
        clearTimeout(timer);
        onFirst();
        params.onEvent(event);
      },
    });
  } catch (error) {
    if (timedOut && !signal.aborted) throw new FirstEventTimeout("aucun événement reçu à temps");
    throw error;
  } finally {
    clearTimeout(timer);
    signal.removeEventListener("abort", forward);
  }
}

function isUserAbort(error: unknown, signal: AbortSignal): boolean {
  return signal.aborted && error instanceof DOMException && error.name === "AbortError";
}

/**
 * Pose la question. Résout `ok` quand l'API a répondu (réponse, blocage ou erreur métier),
 * `paused` quand le service en direct est indisponible. Les erreurs non liées à une panne
 * (422, 403) sont propagées, comme l'arrêt demandé par le visiteur.
 */
export async function askResilient(params: ResilientParams): Promise<AskOutcome> {
  const { signal, retryDelayMs = RETRY_DELAY_MS } = params;
  let budget = false;
  const watched: ResilientParams = {
    ...params,
    onEvent: (event) => {
      if (isBudgetEvent(event)) budget = true;
      params.onEvent(event);
    },
  };

  for (let tries = 1; ; tries += 1) {
    let received = false;
    try {
      await attempt(watched, () => {
        received = true;
      });
      return budget ? { kind: "paused", reason: "budget" } : { kind: "ok" };
    } catch (error) {
      if (isUserAbort(error, signal)) throw error;
      if (!(error instanceof FirstEventTimeout) && !isOutageError(error)) throw error;
      if (budget) return { kind: "paused", reason: "budget" };
      // Flux coupé en cours de route, ou seconde tentative ratée : rediffusion. Réessayer
      // après des événements déjà affichés dupliquerait les étapes du circuit.
      if (received || tries >= 2) return { kind: "paused", reason: "unavailable" };
      await wait(retryDelayMs, signal);
    }
  }
}
