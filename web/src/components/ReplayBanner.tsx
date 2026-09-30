"use client";

import { useLocale, useTranslations } from "next-intl";
import { useId } from "react";

import { FORMAT_LOCALE } from "@/i18n/locales";

/** Pourquoi la page rejoue : budget du jour, API injoignable, ou `?replay=1`. */
export type ReplayReason = "budget" | "unavailable" | "forced";

const REASON_KEY = {
  budget: "reasonBudget",
  unavailable: "reasonUnavailable",
  forced: "reasonForced",
} as const;

type Props = {
  reason: ReplayReason;
  /** Date ISO de l'enregistrement en cours de lecture. */
  recordedAt: string;
  busy: boolean;
  onNext: () => void;
};

/** Bandeau du mode rediffusion : le visiteur sait que le direct est en pause et pourquoi. */
export function ReplayBanner({ reason, recordedAt, busy, onNext }: Props) {
  const t = useTranslations("replay");
  const locale = useLocale();
  const id = useId();
  const recorded = new Date(recordedAt);
  const date = Number.isNaN(recorded.getTime())
    ? recordedAt
    : new Intl.DateTimeFormat(FORMAT_LOCALE[locale as keyof typeof FORMAT_LOCALE] ?? "fr-FR", {
        dateStyle: "long",
        timeZone: "UTC",
      }).format(recorded);
  return (
    <section className="replay-banner" aria-labelledby={`${id}-title`} data-testid="replay-banner">
      <h2 id={`${id}-title`} className="replay-banner__title">
        <span className="led" aria-hidden="true" />
        {t("title")}
      </h2>
      <p className="replay-banner__text" role="status">
        {t("explain", { reason: t(REASON_KEY[reason]), date })}
      </p>
      <button type="button" className="btn replay-banner__next" disabled={busy} onClick={onNext}>
        {t("next")}
      </button>
    </section>
  );
}
