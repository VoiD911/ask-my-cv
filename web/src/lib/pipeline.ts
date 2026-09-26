/**
 * Réducteur pur : transforme les événements SSE de l'API en état du pipeline.
 *
 * Les types d'événements viennent de `./events` (miroir de
 * `src/ask_my_cv/events.py`), la même définition que celle validée par
 * `isAskEvent` dans le client `ask.ts` : une seule source de vérité.
 */

import type { AskEvent, DoneEvent, StageStatus as ApiStageStatus } from "./events";

export type { DoneEvent } from "./events";

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

/** Statut affiché d'une étape : les statuts de l'API, plus « au repos » et « en cours ». */
export type StageStatus = "idle" | "active" | ApiStageStatus;

export type StageState = {
  status: StageStatus;
  durationMs?: number;
  attrs: Record<string, string>;
};

/** Événements consommés par le réducteur : exactement ceux de l'API. */
export type PipelineEvent = AskEvent;

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
