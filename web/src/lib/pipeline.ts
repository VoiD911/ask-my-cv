/**
 * Réducteur pur : transforme les événements SSE de l'API en état du pipeline.
 *
 * NOTE : `PipelineEvent` ci-dessous est une redéfinition locale et minimale
 * des événements consommés ici, dérivée de `src/ask_my_cv/events.py`. Le
 * fichier `web/src/lib/events.ts` (écrit en parallèle par un autre agent)
 * doit à terme satisfaire — ou remplacer — ce type ; le contrôleur du flux
 * SSE (`sse.ts`/`ask.ts`) est responsable de la réconciliation.
 */

/** Les 8 étapes du pipeline, dans l'ordre où l'API les traverse. */
export const STAGES = [
  "reception",
  "quota",
  "injection",
  "embedding",
  "retrieval",
  "prompt",
  "llm",
  "output_guard",
] as const;

export type KnownStage = (typeof STAGES)[number];

export type StageStatus =
  | "idle"
  | "active"
  | "ok"
  | "blocked"
  | "error"
  | "fallback";

export type StageState = {
  status: StageStatus;
  durationMs?: number;
  attrs: Record<string, string>;
};

export type DoneEvent = {
  type: "done";
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  latency_ms: number;
  sources: string[];
  answer_override: string | null;
  trace_id: string | null;
};

export type StageStartEvent = { type: "stage.start"; name: string; ts: number };

export type StageEndEvent = {
  type: "stage.end";
  name: string;
  status: Exclude<StageStatus, "idle" | "active">;
  duration_ms: number;
  attrs: Record<string, unknown>;
};

export type LlmProgressEvent = { type: "llm.progress"; tokens: number };

export type AnswerEvent = { type: "answer"; text: string };

/** Union minimale des événements consommés par le réducteur du pipeline. */
export type PipelineEvent =
  | StageStartEvent
  | StageEndEvent
  | LlmProgressEvent
  | AnswerEvent
  | DoneEvent;

export type RunState = {
  stages: Record<string, StageState>;
  /** Ordre d'affichage des étapes : les 8 connues, puis les inconnues dans l'ordre d'apparition. */
  order: string[];
  tokens: number;
  answer: string | null;
  override: string | null;
  done: DoneEvent | null;
  blockedAt: string | null;
  startedAt: number | null;
};

export const STATUS_LABELS: Record<StageStatus, string> = {
  idle: "en attente",
  active: "en cours",
  ok: "terminée",
  blocked: "bloquée",
  error: "en erreur",
  fallback: "en repli",
};

const STAGE_LABELS: Record<KnownStage, string> = {
  reception: "réception",
  quota: "quota",
  injection: "injection",
  embedding: "embedding",
  retrieval: "recherche",
  prompt: "prompt",
  llm: "LLM",
  output_guard: "garde-fou de sortie",
};

export function stageLabel(name: string): string {
  return STAGE_LABELS[name as KnownStage] ?? name;
}

/** Formate un nombre pour l'affichage en français (fr-FR), sans décimales inutiles. */
export function formatNumberFr(n: number): string {
  return new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 3 }).format(n);
}

/** Convertit une valeur d'attribut quelconque en chaîne affichable. */
function formatAttrValue(value: unknown): string {
  if (typeof value === "number") {
    return formatNumberFr(value);
  }
  if (typeof value === "boolean") {
    return value ? "vrai" : "faux";
  }
  if (value === null || value === undefined) {
    return "—";
  }
  if (typeof value === "string") {
    return value;
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function formatAttrs(attrs: Record<string, unknown>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(attrs)) {
    out[key] = formatAttrValue(value);
  }
  return out;
}

function initStages(): Record<string, StageState> {
  const stages: Record<string, StageState> = {};
  for (const name of STAGES) {
    stages[name] = { status: "idle", attrs: {} };
  }
  return stages;
}

/** État initial du pipeline, avant tout événement. */
export function createInitialState(): RunState {
  return {
    stages: initStages(),
    order: [...STAGES],
    tokens: 0,
    answer: null,
    override: null,
    done: null,
    blockedAt: null,
    startedAt: null,
  };
}

function ensureStage(state: RunState, name: string): RunState {
  if (state.stages[name]) return state;
  return {
    ...state,
    stages: { ...state.stages, [name]: { status: "idle", attrs: {} } },
    // Étape inconnue : ajoutée à la fin de l'ordre d'affichage.
    order: [...state.order, name],
  };
}

/**
 * Réducteur pur : `(état, événement) → nouvel état`.
 *
 * Aucune logique métier sur les noms d'étapes : une étape inconnue côté API
 * est simplement ajoutée à la fin de l'ordre d'affichage (spec §3).
 */
export function reduce(state: RunState, event: PipelineEvent): RunState {
  switch (event.type) {
    case "stage.start": {
      const withStage = ensureStage(state, event.name);
      const previous = withStage.stages[event.name] ?? { status: "idle", attrs: {} };
      return {
        ...withStage,
        startedAt: withStage.startedAt ?? event.ts,
        stages: {
          ...withStage.stages,
          [event.name]: {
            ...previous,
            status: "active",
          },
        },
      };
    }

    case "stage.end": {
      const withStage = ensureStage(state, event.name);
      const blockedAt =
        withStage.blockedAt ?? (event.status === "blocked" ? event.name : null);
      return {
        ...withStage,
        blockedAt,
        stages: {
          ...withStage.stages,
          [event.name]: {
            status: event.status,
            durationMs: event.duration_ms,
            attrs: formatAttrs(event.attrs),
          },
        },
      };
    }

    case "llm.progress":
      return { ...state, tokens: event.tokens };

    case "answer":
      return { ...state, answer: event.text };

    case "done": {
      // Idempotent : un `done` répété ne fait que réappliquer les mêmes valeurs.
      const blockedAt = state.blockedAt ?? findFirstBlocked(state);
      return {
        ...state,
        done: event,
        override: event.answer_override ?? null,
        blockedAt,
      };
    }

    default: {
      const _exhaustive: never = event;
      return _exhaustive;
    }
  }
}

function findFirstBlocked(state: RunState): string | null {
  for (const name of state.order) {
    if (state.stages[name]?.status === "blocked") return name;
  }
  return null;
}

/** Phrase française pour la zone `aria-live`, résumant le dernier changement pertinent. */
export function describe(state: RunState): string {
  if (state.done) {
    if (state.blockedAt) {
      return `Terminé : étape ${stageLabel(state.blockedAt)} bloquée.`;
    }
    return `Terminé en ${formatNumberFr(state.done.latency_ms)} ms, ${formatNumberFr(state.done.tokens_out)} jetons générés.`;
  }

  if (state.blockedAt) {
    const stage = state.stages[state.blockedAt];
    const score = stage?.attrs.score;
    if (score !== undefined) {
      return `Étape ${stageLabel(state.blockedAt)} : bloquée, score ${score}.`;
    }
    return `Étape ${stageLabel(state.blockedAt)} : bloquée.`;
  }

  // Dernière étape active ou terminée, dans l'ordre d'affichage (la plus avancée en premier).
  for (let i = state.order.length - 1; i >= 0; i -= 1) {
    const name = state.order[i];
    if (name === undefined) continue;
    const stage = state.stages[name];
    if (!stage || stage.status === "idle") continue;
    if (stage.status === "active") {
      return `Étape ${stageLabel(name)} : en cours.`;
    }
    return `Étape ${stageLabel(name)} : ${STATUS_LABELS[stage.status]}.`;
  }

  return "En attente de la requête.";
}
