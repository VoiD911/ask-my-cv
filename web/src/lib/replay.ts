/**
 * Mode rediffusion : quand l'API ne peut pas répondre (budget du jour atteint, panne, 5xx,
 * réseau, délai dépassé), la page d'accueil rejoue des échanges réels enregistrés sur le site
 * en production (`scripts/record-replays.mjs`), au lieu d'afficher une erreur.
 *
 * Ce module est pur (aucun React) : détection de l'indisponibilité, validation des
 * enregistrements, choix d'un échange « similaire » et calendrier de lecture.
 */

import { MESSAGES } from "@/i18n/messages";
import type { Locale } from "@/i18n/locales";

import { AskError } from "./ask";
import { isAskEvent, type AskEvent } from "./events";

/** Nature de l'échange enregistré : question de recruteur, annonce collée, attaque bloquée. */
export type ReplayKind = "question" | "job_ad" | "attack";

export interface ReplayFrame {
  /** Délai depuis l'envoi de la question, en ms, mesuré à l'enregistrement. */
  readonly t: number;
  readonly event: AskEvent;
}

export interface Replay {
  readonly id: string;
  readonly locale: Locale;
  readonly kind: ReplayKind;
  readonly question: string;
  /** Date ISO de l'enregistrement. */
  readonly recordedAt: string;
  readonly frames: readonly ReplayFrame[];
}

export interface ReplaySet {
  readonly version: 1;
  /** `prod` : enregistré sur le site en production ; `fixture` : API locale (tests seulement). */
  readonly source: "prod" | "fixture";
  readonly replays: readonly Replay[];
}

/** Pourquoi le service en direct est en pause. */
export type OutageReason = "budget" | "unavailable";

/** Message de blocage « budget atteint » de l'API (`pipeline.BLOCK_MESSAGES`). */
const BUDGET_MESSAGE = MESSAGES.fr.overrides.budget_exceeded;

/**
 * L'événement signale-t-il le budget du jour atteint ? L'API répond 200 et bloque l'étape
 * `quota` avec la raison `budget_exceeded` (puis `done.answer_override`).
 */
export function isBudgetEvent(event: AskEvent): boolean {
  if (event.type === "stage.end") {
    return event.status === "blocked" && event.attrs["reason"] === "budget_exceeded";
  }
  if (event.type === "done") return event.answer_override === BUDGET_MESSAGE;
  return false;
}

/**
 * L'erreur est-elle une indisponibilité du service (réseau, délai dépassé, 5xx, flux coupé) ?
 * Une question invalide (422) ou une signature refusée (403) n'en est pas une : la rediffusion
 * masquerait un vrai problème.
 */
export function isOutageError(error: unknown): boolean {
  if (!(error instanceof AskError) || error.kind !== "unavailable") return false;
  return error.status === undefined || error.status >= 500 || error.status === 429;
}

const KINDS: ReadonlySet<string> = new Set(["question", "job_ad", "attack"]);

function isFrame(value: unknown): value is ReplayFrame {
  if (typeof value !== "object" || value === null) return false;
  const record = value as Record<string, unknown>;
  return typeof record["t"] === "number" && record["t"] >= 0 && isAskEvent(record["event"]);
}

function isReplay(value: unknown): value is Replay {
  if (typeof value !== "object" || value === null) return false;
  const r = value as Record<string, unknown>;
  const frames = r["frames"];
  return (
    typeof r["id"] === "string" &&
    (r["locale"] === "fr" || r["locale"] === "en") &&
    typeof r["kind"] === "string" &&
    KINDS.has(r["kind"]) &&
    typeof r["question"] === "string" &&
    r["question"].length > 0 &&
    typeof r["recordedAt"] === "string" &&
    Array.isArray(frames) &&
    frames.length > 0 &&
    frames.every(isFrame) &&
    (frames.at(-1) as ReplayFrame).event.type === "done"
  );
}

/** Validation du fichier d'enregistrements reçu (un fichier invalide masque la rediffusion). */
export function isReplaySet(value: unknown): value is ReplaySet {
  if (typeof value !== "object" || value === null) return false;
  const r = value as Record<string, unknown>;
  const replays = r["replays"];
  return (
    r["version"] === 1 &&
    (r["source"] === "prod" || r["source"] === "fixture") &&
    Array.isArray(replays) &&
    replays.every(isReplay)
  );
}

/** Chemin public des enregistrements d'une langue (copiés par `scripts/sync-replays.mjs`). */
export function replaysUrl(locale: Locale): string {
  return `/replays/${locale}.json`;
}

/**
 * Charge les enregistrements de la langue : `[]` si absents ou invalides (la page retombe
 * alors sur le message d'erreur habituel).
 */
export async function loadReplays(
  locale: Locale,
  fetchImpl: typeof fetch = fetch,
): Promise<readonly Replay[]> {
  try {
    const response = await fetchImpl(replaysUrl(locale), { headers: { accept: "application/json" } });
    if (!response.ok) return [];
    const data: unknown = await response.json();
    if (!isReplaySet(data)) return [];
    return data.replays.filter((r) => r.locale === locale);
  } catch {
    return [];
  }
}

/** Nature probable de la question du visiteur, pour lui rejouer un échange du même genre. */
export function kindOf(question: string, attacks: readonly string[]): ReplayKind {
  const q = question.trim();
  if (attacks.includes(q)) return "attack";
  return q.length > 400 ? "job_ad" : "question";
}

/**
 * Choisit l'échange à rejouer : du même genre que la question si possible, en tournant pour
 * ne pas rejouer deux fois de suite le même (`turn` = nombre de rediffusions déjà lues).
 */
export function pickReplay(
  replays: readonly Replay[],
  kind: ReplayKind | null,
  turn: number,
): Replay | null {
  if (replays.length === 0) return null;
  const sameKind = kind ? replays.filter((r) => r.kind === kind) : [];
  const pool = sameKind.length > 0 ? sameKind : replays;
  return pool[turn % pool.length] ?? null;
}

/** Plus long silence rejoué entre deux événements (une annonce peut prendre 20 s en direct). */
export const MAX_GAP_MS = 2_500;

/**
 * Délai avant chaque événement, relatif au précédent : les écarts enregistrés, plafonnés à
 * `MAX_GAP_MS`. Mouvement réduit : tout arrive d'un coup (aucune animation temporelle).
 */
export function schedule(frames: readonly ReplayFrame[], reducedMotion: boolean): number[] {
  let previous = 0;
  return frames.map((frame) => {
    const gap = Math.max(0, frame.t - previous);
    previous = frame.t;
    return reducedMotion ? 0 : Math.min(gap, MAX_GAP_MS);
  });
}

/**
 * Lit les événements au rythme de `schedule`. Se résout après le dernier événement, ou tout
 * de suite (sans rien émettre de plus) si `signal` est déclenché.
 */
export function play(
  frames: readonly ReplayFrame[],
  onEvent: (event: AskEvent) => void,
  options: { reducedMotion: boolean; signal?: AbortSignal },
): Promise<"done" | "stopped"> {
  const delays = schedule(frames, options.reducedMotion);
  const { signal } = options;
  return new Promise((resolve) => {
    let i = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const onAbort = () => {
      if (timer !== undefined) clearTimeout(timer);
      resolve("stopped");
    };
    if (signal?.aborted) {
      resolve("stopped");
      return;
    }
    signal?.addEventListener("abort", onAbort, { once: true });
    const step = () => {
      // Tous les événements dus maintenant sont livrés d'un bloc (délais nuls).
      do {
        const frame = frames[i];
        if (frame) onEvent(frame.event);
        i += 1;
      } while (i < frames.length && delays[i] === 0);
      if (i >= frames.length) {
        signal?.removeEventListener("abort", onAbort);
        resolve("done");
        return;
      }
      timer = setTimeout(step, delays[i]);
    };
    timer = setTimeout(step, delays[0] ?? 0);
  });
}

/** `?replay=1` : force la rediffusion (démos, tests), sans appeler l'API. */
export function isReplayForced(search: string): boolean {
  return new URLSearchParams(search).get("replay") === "1";
}
