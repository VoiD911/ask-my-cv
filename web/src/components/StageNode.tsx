import { STATUS_LABELS, formatNumberFr, stageLabel, type StageState } from "@/lib/pipeline";

/** Attributs mis en avant par étape (noms émis par `src/ask_my_cv/pipeline.py`). */
const KEY_ATTRS: Record<string, readonly string[]> = {
  reception: ["model"],
  quota: ["spent_today_usd"],
  injection: ["score", "model_version"],
  embedding: ["dim"],
  retrieval: ["hits", "top_score"],
  prompt: ["template"],
  llm: ["tokens_out", "cost_usd"],
  output_guard: ["reason"],
};

const MAX_ATTRS = 2;

/** Durée lisible : millisecondes sous la seconde, secondes au-delà. */
export function formatDuration(ms: number): string {
  if (ms < 1000) return `${formatNumberFr(Math.round(ms))} ms`;
  return `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 }).format(ms / 1000)} s`;
}

/**
 * Deux attributs au plus, dans l'ordre : cause d'un blocage ou d'une erreur,
 * attributs clés de l'étape, puis les autres dans l'ordre d'émission.
 */
export function keyAttrs(
  name: string,
  stage: StageState,
  liveTokens = 0,
): Array<[string, string]> {
  if (stage.status === "active") {
    return name === "llm" && liveTokens > 0 ? [["tokens", formatNumberFr(liveTokens)]] : [];
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
};

/** Une étape du pipeline dessinée comme une puce : repère, nom, statut, durée, attributs. */
export function StageNode({ name, index, stage, liveTokens = 0 }: StageNodeProps) {
  const attrs = keyAttrs(name, stage, liveTokens);
  return (
    <div className="chip" data-status={stage.status} data-stage={name}>
      <div className="chip__head">
        <span className="chip__ref">U{index + 1}</span>
        <span className="chip__status">
          <span className="led" aria-hidden="true" />
          {STATUS_LABELS[stage.status]}
        </span>
      </div>
      <div className="chip__label">{stageLabel(name)}</div>
      <div className="chip__id">
        <span>{name}</span>
        {stage.durationMs !== undefined && (
          <span className="chip__duration">{formatDuration(stage.durationMs)}</span>
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
};

const TERMINAL_TEXT: Record<TerminalProps["kind"], { ref: string; label: string }> = {
  in: { ref: "J1", label: "question" },
  out: { ref: "J2", label: "réponse" },
};

/** Connecteur d'entrée (question) ou de sortie (réponse) du circuit. */
export function Terminal({ kind, state }: TerminalProps) {
  const text = TERMINAL_TEXT[kind];
  return (
    <div className="terminal" data-kind={kind} data-state={state}>
      <span className="led" aria-hidden="true" />
      <span className="terminal__ref">{text.ref}</span>
      <span className="terminal__label">{text.label}</span>
    </div>
  );
}
