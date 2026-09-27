"use client";

import { useState } from "react";

import type { DoneEvent } from "@/lib/events";
import { formatNumberFr } from "@/lib/pipeline";

import { formatDuration } from "./StageNode";

/** Coût en dollars américains, entre 4 et 6 décimales (les montants sont minuscules). */
export function formatCost(usd: number): string {
  return `${new Intl.NumberFormat("fr-FR", {
    minimumFractionDigits: 4,
    maximumFractionDigits: 6,
  }).format(usd)} $`;
}

/** Un identifiant de trace nul (32 zéros) signifie « pas de traçage » (API locale). */
export function usableTraceId(id: string | null | undefined): string | null {
  if (!id || /^0+$/.test(id)) return null;
  return id;
}

function TraceId({ id }: { id: string | null }) {
  const [copied, setCopied] = useState(false);
  if (!id) return <dd className="readout__value readout__value--dim">non tracée</dd>;

  async function copy(value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }

  return (
    <dd className="readout__value readout__trace">
      <code title={id}>{id}</code>
      <button type="button" className="copy" onClick={() => void copy(id)} aria-label="Copier l'identifiant de trace">
        {copied ? "copié" : "copier"}
      </button>
    </dd>
  );
}

type DemoFooterProps = { done: DoneEvent | null };

/** Relevé de la dernière question : latence, jetons, coût, identifiant de trace. */
export function DemoFooter({ done }: DemoFooterProps) {
  const dash = <dd className="readout__value readout__value--dim">—</dd>;
  return (
    <section className="readout" aria-label="Relevé de la dernière question" data-testid="demo-footer">
      <dl className="readout__grid">
        <div className="readout__cell" data-testid="readout-latency">
          <dt>latence</dt>
          {done ? <dd className="readout__value">{formatDuration(done.latency_ms)}</dd> : dash}
        </div>
        <div className="readout__cell" data-testid="readout-tokens-in">
          <dt>jetons entrée</dt>
          {done ? <dd className="readout__value">{formatNumberFr(done.tokens_in)}</dd> : dash}
        </div>
        <div className="readout__cell" data-testid="readout-tokens-out">
          <dt>jetons sortie</dt>
          {done ? <dd className="readout__value">{formatNumberFr(done.tokens_out)}</dd> : dash}
        </div>
        <div className="readout__cell" data-testid="readout-cost">
          <dt>coût</dt>
          {done ? <dd className="readout__value">{formatCost(done.cost_usd)}</dd> : dash}
        </div>
        <div className="readout__cell readout__cell--trace" data-testid="readout-trace">
          <dt>trace</dt>
          {done ? <TraceId id={usableTraceId(done.trace_id)} /> : dash}
        </div>
      </dl>
    </section>
  );
}
