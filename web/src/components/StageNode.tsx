import { DEFAULT_LOCALE, FORMAT_LOCALE, type Locale } from "@/i18n/locales";
import { MESSAGES } from "@/i18n/messages";
import { formatNumber, stageLabel, statusLabel, type StageState } from "@/lib/pipeline";

/** Attributs mis en avant par étape (noms émis par `src/ask_my_cv/pipeline.py`). */
const KEY_ATTRS: Record<string, readonly string[]> = {
  reception: ["model"],
  quota: ["spent_today_usd"],
  // blocked_by : présent seulement si le garde-fou Bedrock (second avis) a bloqué l'annonce
  injection: ["blocked_by", "score", "model_version"],
  embedding: ["dim"],
  retrieval: ["hits", "top_score"],
  prompt: ["template"],
  llm: ["tokens_out", "cost_usd"],
  output_guard: ["reason"],
};

const MAX_ATTRS = 2;

/** Durée lisible : millisecondes sous la seconde, secondes au-delà. */
export function formatDuration(ms: number, locale: Locale = DEFAULT_LOCALE): string {
  if (ms < 1000) return `${formatNumber(Math.round(ms), locale)} ms`;
  return `${new Intl.NumberFormat(FORMAT_LOCALE[locale], { maximumFractionDigits: 2 }).format(ms / 1000)} s`;
}

/**
 * Deux attributs au plus, dans l'ordre : cause d'un blocage ou d'une erreur,
 * attributs clés de l'étape, puis les autres dans l'ordre d'émission.
 */
export function keyAttrs(
  name: string,
  stage: StageState,
  liveTokens = 0,
  locale: Locale = DEFAULT_LOCALE,
): Array<[string, string]> {
  if (stage.status === "active") {
    return name === "llm" && liveTokens > 0 ? [["tokens", formatNumber(liveTokens, locale)]] : [];
  }
  const preferred = ["reason", "error", ...(KEY_ATTRS[name] ?? [])];
  const keys = [
    ...preferred.filter((k) => k in stage.attrs),
    ...Object.keys(stage.attrs).filter((k) => !preferred.includes(k)),
  ];
  return [...new Set(keys)]
    .slice(0, MAX_ATTRS)
    .map((k): [string, string] => [k, stage.attrs[k] ?? ""]);
}

type StageNodeProps = {
  name: string;
  /** Position dans le pipeline (0 pour la première étape) : repère « U1 », « U2 »… */
  index: number;
  stage: StageState;
  /** Jetons reçus pendant que le LLM génère. */
  liveTokens?: number;
  locale?: Locale;
};

/** Une étape du pipeline dessinée comme une puce : repère, nom, statut, durée, attributs. */
export function StageNode({ name, index, stage, liveTokens = 0, locale = DEFAULT_LOCALE }: StageNodeProps) {
  const attrs = keyAttrs(name, stage, liveTokens, locale);
  return (
    <div className="chip" data-status={stage.status} data-stage={name}>
      <div className="chip__head">
        <span className="chip__ref">U{index + 1}</span>
        <span className="chip__status">
          <span className="led" aria-hidden="true" />
          {statusLabel(stage.status, locale)}
        </span>
      </div>
      <div className="chip__label">{stageLabel(name, locale)}</div>
      <div className="chip__id">
        <span>{name}</span>
        {stage.durationMs !== undefined && (
          <span className="chip__duration">{formatDuration(stage.durationMs, locale)}</span>
        )}
      </div>
      <dl className="chip__attrs">
        {attrs.length === 0 ? (
          <div className="chip__attr chip__attr--empty">
            <dt>—</dt>
          </div>
        ) : (
          attrs.map(([k, v]) => (
            <div key={k} className="chip__attr">
              <dt>{k}</dt>
              <dd title={v}>{v}</dd>
            </div>
          ))
        )}
      </dl>
    </div>
  );
}

export type TerminalState = "standby" | "live" | "ok" | "blocked";

type TerminalProps = {
  kind: "in" | "out";
  state: TerminalState;
  locale?: Locale;
};

/** Connecteur d'entrée (question) ou de sortie (réponse) du circuit. */
export function Terminal({ kind, state, locale = DEFAULT_LOCALE }: TerminalProps) {
  const circuit = MESSAGES[locale].circuit;
  const text =
    kind === "in" ? { ref: "J1", label: circuit.terminalIn } : { ref: "J2", label: circuit.terminalOut };
  return (
    <div className="terminal" data-kind={kind} data-state={state}>
      <span className="led" aria-hidden="true" />
      <span className="terminal__ref">{text.ref}</span>
      <span className="terminal__label">{text.label}</span>
    </div>
  );
}
