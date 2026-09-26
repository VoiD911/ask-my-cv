/**
 * Types des événements SSE émis par `POST /api/ask`.
 *
 * Reflète exactement `src/ask_my_cv/events.py` (union discriminée par `type`,
 * sérialisée en JSON par `model_dump_json()`). Ne pas ajouter de champs ni de
 * valeurs par défaut qui n'existent pas côté API : un déficit de compatibilité
 * ici ferait retomber le pipeline visuel silencieusement.
 */

/** `ask_my_cv.events.StageStatus` */
export type StageStatus = "ok" | "blocked" | "error" | "fallback";

/** `ask_my_cv.events.StageStart` */
export interface StageStartEvent {
  type: "stage.start";
  name: string;
  ts: number;
}

/** `ask_my_cv.events.StageEnd` */
export interface StageEndEvent {
  type: "stage.end";
  name: string;
  status: StageStatus;
  duration_ms: number;
  attrs: Record<string, unknown>;
}

/**
 * `ask_my_cv.events.LLMProgress` — un compteur de jetons, jamais de texte.
 */
export interface LlmProgressEvent {
  type: "llm.progress";
  tokens: number;
}

/**
 * `ask_my_cv.events.Answer` — émis uniquement après le garde-fou de sortie.
 */
export interface AnswerEvent {
  type: "answer";
  text: string;
}

/** `ask_my_cv.events.Done` */
export interface DoneEvent {
  type: "done";
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  latency_ms: number;
  sources: string[];
  answer_override: string | null;
  trace_id: string | null;
}

/** `ask_my_cv.events.Event` */
export type AskEvent =
  | StageStartEvent
  | StageEndEvent
  | LlmProgressEvent
  | AnswerEvent
  | DoneEvent;

const EVENT_TYPES: ReadonlySet<AskEvent["type"]> = new Set([
  "stage.start",
  "stage.end",
  "llm.progress",
  "answer",
  "done",
]);

/**
 * Garde de type minimale sur la forme JSON reçue depuis le SSE : vérifie que
 * `type` est l'une des cinq valeurs connues et que les champs attendus pour
 * ce type sont présents avec le bon type primitif. N'exclut pas les champs
 * en trop (l'API n'en émet pas, mais on ne veut pas casser sur un ajout
 * rétrocompatible côté serveur).
 */
export function isAskEvent(value: unknown): value is AskEvent {
  if (typeof value !== "object" || value === null) return false;
  const record = value as Record<string, unknown>;
  const type = record["type"];
  if (typeof type !== "string" || !EVENT_TYPES.has(type as AskEvent["type"])) {
    return false;
  }
  switch (type as AskEvent["type"]) {
    case "stage.start":
      return typeof record["name"] === "string" && typeof record["ts"] === "number";
    case "stage.end":
      return (
        typeof record["name"] === "string" &&
        (record["status"] === "ok" ||
          record["status"] === "blocked" ||
          record["status"] === "error" ||
          record["status"] === "fallback") &&
        typeof record["duration_ms"] === "number" &&
        typeof record["attrs"] === "object" &&
        record["attrs"] !== null
      );
    case "llm.progress":
      return typeof record["tokens"] === "number";
    case "answer":
      return typeof record["text"] === "string";
    case "done":
      return (
        typeof record["tokens_in"] === "number" &&
        typeof record["tokens_out"] === "number" &&
        typeof record["cost_usd"] === "number" &&
        typeof record["latency_ms"] === "number" &&
        Array.isArray(record["sources"]) &&
        (record["answer_override"] === null || typeof record["answer_override"] === "string") &&
        (record["trace_id"] === null || typeof record["trace_id"] === "string")
      );
    default:
      return false;
  }
}
