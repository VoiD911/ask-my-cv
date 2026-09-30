/**
 * Réducteur pur : transforme les événements SSE de l'API en état du pipeline.
 *
 * Les types d'événements viennent de `./events` (miroir de
 * `src/ask_my_cv/events.py`), la même définition que celle validée par
 * `isAskEvent` dans le client `ask.ts` : une seule source de vérité.
 */

import { DEFAULT_LOCALE, FORMAT_LOCALE, type Locale } from "@/i18n/locales";
import { MESSAGES } from "@/i18n/messages";
import { translator } from "@/i18n/translator";

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
  /** Langue de l'interface : libellés, nombres et résumé aria-live. */
  locale: Locale;
};

/** Libellés des statuts (catalogue `circuit.status`). */
export function statusLabel(status: StageStatus, locale: Locale = DEFAULT_LOCALE): string {
  return MESSAGES[locale].circuit.status[status];
}

/** Libellés français des statuts, conservés pour les appelants existants. */
export const STATUS_LABELS: Record<StageStatus, string> = MESSAGES.fr.circuit.status;

export function stageLabel(name: string, locale: Locale = DEFAULT_LOCALE): string {
  const labels: Record<string, string> = MESSAGES[locale].circuit.stages;
  return Object.hasOwn(labels, name) ? (labels[name] as string) : name;
}

/** Formate un nombre dans la langue voulue, sans décimales inutiles. */
export function formatNumber(n: number, locale: Locale = DEFAULT_LOCALE): string {
  return new Intl.NumberFormat(FORMAT_LOCALE[locale], { maximumFractionDigits: 3 }).format(n);
}

/** Formate un nombre pour l'affichage en français (fr-FR), sans décimales inutiles. */
export function formatNumberFr(n: number): string {
  return formatNumber(n, "fr");
}

/** Montant en dollars américains : « 0,0012 $ » en français, « $0.0012 » en anglais. */
export function formatUsd(
  usd: number,
  locale: Locale,
  digits: { min?: number; max: number },
): string {
  const text = new Intl.NumberFormat(FORMAT_LOCALE[locale], {
    minimumFractionDigits: digits.min ?? 0,
    maximumFractionDigits: digits.max,
  }).format(usd);
  return locale === "fr" ? `${text} $` : `$${text}`;
}

/** Convertit une valeur d'attribut quelconque en chaîne affichable. */
function formatAttrValue(value: unknown, locale: Locale): string {
  if (typeof value === "number") {
    return formatNumber(value, locale);
  }
  if (typeof value === "boolean") {
    return MESSAGES[locale].circuit[value ? "true" : "false"];
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

function formatAttrs(attrs: Record<string, unknown>, locale: Locale): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(attrs)) {
    out[key] = formatAttrValue(value, locale);
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
export function createInitialState(locale: Locale = DEFAULT_LOCALE): RunState {
  return {
    stages: initStages(),
    order: [...STAGES],
    tokens: 0,
    answer: null,
    override: null,
    done: null,
    blockedAt: null,
    startedAt: null,
    locale,
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
            attrs: formatAttrs(event.attrs, withStage.locale),
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

/** Phrase pour la zone `aria-live`, résumant le dernier changement pertinent. */
export function describe(state: RunState): string {
  const { locale } = state;
  const t = translator(locale);
  const stage = (name: string) => stageLabel(name, locale);
  if (state.done) {
    if (state.blockedAt) {
      return t("circuit.doneBlocked", { stage: stage(state.blockedAt) });
    }
    return t("circuit.done", {
      ms: formatNumber(state.done.latency_ms, locale),
      tokens: formatNumber(state.done.tokens_out, locale),
    });
  }

  if (state.blockedAt) {
    const score = state.stages[state.blockedAt]?.attrs.score;
    if (score !== undefined) {
      return t("circuit.blockedScore", { stage: stage(state.blockedAt), score });
    }
    return t("circuit.blocked", { stage: stage(state.blockedAt) });
  }

  // Dernière étape active ou terminée, dans l'ordre d'affichage (la plus avancée en premier).
  for (let i = state.order.length - 1; i >= 0; i -= 1) {
    const name = state.order[i];
    if (name === undefined) continue;
    const current = state.stages[name];
    if (!current || current.status === "idle") continue;
    if (current.status === "active") {
      return t("circuit.active", { stage: stage(name) });
    }
    return t("circuit.stageStatus", { stage: stage(name), status: statusLabel(current.status, locale) });
  }

  return t("circuit.waiting");
}
