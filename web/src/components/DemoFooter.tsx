"use client";

import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";

import { DEFAULT_LOCALE, type Locale } from "@/i18n/locales";
import type { DoneEvent } from "@/lib/events";
import { formatNumber, formatUsd } from "@/lib/pipeline";

import { formatDuration } from "./StageNode";

/** Coût en dollars américains, entre 4 et 6 décimales (les montants sont minuscules). */
export function formatCost(usd: number, locale: Locale = DEFAULT_LOCALE): string {
  return formatUsd(usd, locale, { min: 4, max: 6 });
}

/** Un identifiant de trace nul (32 zéros) signifie « pas de traçage » (API locale). */
export function usableTraceId(id: string | null | undefined): string | null {
  if (!id || /^0+$/.test(id)) return null;
  return id;
}

function TraceId({ id }: { id: string | null }) {
  const t = useTranslations("readout");
  const [copied, setCopied] = useState(false);
  if (!id) return <dd className="readout__value readout__value--dim">{t("untraced")}</dd>;

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
      <button type="button" className="copy" onClick={() => void copy(id)} aria-label={t("copyLabel")}>
        {copied ? t("copied") : t("copy")}
      </button>
    </dd>
  );
}

type DemoFooterProps = { done: DoneEvent | null };

/** Relevé de la dernière question : latence, jetons, coût, identifiant de trace. */
export function DemoFooter({ done }: DemoFooterProps) {
  const t = useTranslations("readout");
  const locale = useLocale();
  const dash = <dd className="readout__value readout__value--dim">—</dd>;
  return (
    <section className="readout" aria-label={t("label")} data-testid="demo-footer">
      <dl className="readout__grid">
        <div className="readout__cell" data-testid="readout-latency">
          <dt>{t("latency")}</dt>
          {done ? <dd className="readout__value">{formatDuration(done.latency_ms, locale)}</dd> : dash}
        </div>
        <div className="readout__cell" data-testid="readout-tokens-in">
          <dt>{t("tokensIn")}</dt>
          {done ? <dd className="readout__value">{formatNumber(done.tokens_in, locale)}</dd> : dash}
        </div>
        <div className="readout__cell" data-testid="readout-tokens-out">
          <dt>{t("tokensOut")}</dt>
          {done ? <dd className="readout__value">{formatNumber(done.tokens_out, locale)}</dd> : dash}
        </div>
        <div className="readout__cell" data-testid="readout-cost">
          <dt>{t("cost")}</dt>
          {done ? <dd className="readout__value">{formatCost(done.cost_usd, locale)}</dd> : dash}
        </div>
        <div className="readout__cell readout__cell--trace" data-testid="readout-trace">
          <dt>{t("trace")}</dt>
          {done ? <TraceId id={usableTraceId(done.trace_id)} /> : dash}
        </div>
      </dl>
    </section>
  );
}
