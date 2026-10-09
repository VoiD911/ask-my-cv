"use client";

import { useLocale, useTranslations } from "next-intl";
import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import type { Locale } from "@/i18n/locales";
import { MESSAGES } from "@/i18n/messages";
import { isRefusal, localizeOverride } from "@/lib/api-messages";
import type { ModelInfo } from "@/lib/models";
import { stageLabel, type RunState } from "@/lib/pipeline";

/** Longueur maximale d'une question (`MAX_QUESTION_CHARS` côté API). */
export const MAX_QUESTION = 10_000;

/**
 * Questions suggérées, tirées de `data/cv.md` (catalogue `chat.suggestions`). L'API répond
 * dans la langue de la question : les suggestions anglaises obtiennent une réponse anglaise.
 */
export function suggestionsFor(locale: Locale): readonly string[] {
  return MESSAGES[locale].chat.suggestions;
}

/**
 * Attaques pré-écrites, tirées des lignes `block` de `ml/data/adversarial.jsonl`, dans chaque
 * langue (`chat.attacks`) : le classifieur promu doit toutes les bloquer.
 */
export function attacksFor(locale: Locale): ReadonlyArray<{ label: string; text: string }> {
  return MESSAGES[locale].chat.attacks;
}

export const SUGGESTIONS = suggestionsFor("fr");
export const ATTACKS = attacksFor("fr");

/** `paused` : service en direct en pause, la question du visiteur est suivie d'une rediffusion. */
export type ExchangeStatus = "running" | "done" | "stopped" | "failed" | "paused";

export type Exchange = {
  id: number;
  question: string;
  run: RunState;
  status: ExchangeStatus;
  error?: string;
  /** Échange rejoué (mode rediffusion) : enregistré sur la production à cette date ISO. */
  replayOf?: string;
};

/* ------------------------------------------------------------------ */
/* Réponse : texte brut, marqueurs [n] reliés aux sources              */
/* ------------------------------------------------------------------ */

export type Source = { n: number; label: string };

/** `"[3] Expérience — NeoBotiQc (2025-2026)"` → `{ n: 3, label: "Expérience — …" }`. */
export function parseSources(sources: readonly string[]): Source[] {
  return sources.map((raw, i) => {
    const match = /^\[(\d+)\]\s*(.*)$/.exec(raw);
    return match ? { n: Number(match[1]), label: match[2] ?? "" } : { n: i + 1, label: raw };
  });
}

export type Segment = { kind: "text"; text: string } | { kind: "cite"; n: number; text: string };

/** Découpe la réponse en texte et marqueurs `[n]` ; jamais d'HTML interprété. */
export function segments(text: string): Segment[] {
  const out: Segment[] = [];
  const re = /\[(\d+)\]/g;
  let last = 0;
  for (let m = re.exec(text); m !== null; m = re.exec(text)) {
    if (m.index > last) out.push({ kind: "text", text: text.slice(last, m.index) });
    out.push({ kind: "cite", n: Number(m[1]), text: m[0] });
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push({ kind: "text", text: text.slice(last) });
  return out;
}

function Answer({ exchangeId, text, sources }: { exchangeId: number; text: string; sources: Source[] }) {
  const t = useTranslations("chat");
  const locale = useLocale();
  const byN = new Map(sources.map((s) => [s.n, s]));
  const cited = new Set(segments(text).flatMap((s) => (s.kind === "cite" ? [s.n] : [])));
  // Le CV et les passages consultés sont en français : balisés comme tels hors de /.
  const sourceLang = locale === "fr" ? undefined : "fr";
  if (locale !== "fr" && isRefusal(text)) {
    // L'API garde la phrase de refus exacte, en français : rendu traduit, original conservé.
    return (
      <>
        <p className="answer__text" data-testid="refusal">
          {t("refusal")}
        </p>
        <p className="answer__original">
          {t("originalLabel")} <q lang="fr">{text.trim()}</q>
        </p>
      </>
    );
  }
  return (
    <>
      <p className="answer__text">
        {segments(text).map((seg, i) => {
          if (seg.kind === "text") return <span key={i}>{seg.text}</span>;
          const source = byN.get(seg.n);
          if (!source) return <span key={i}>{seg.text}</span>;
          return (
            <a
              key={i}
              className="cite"
              href={`#src-${exchangeId}-${seg.n}`}
              title={source.label}
              aria-label={t("sourceAria", { n: seg.n, label: source.label })}
            >
              {seg.text}
            </a>
          );
        })}
      </p>
      {sources.length > 0 && (
        <details className="sources" open={cited.size > 0}>
          <summary>
            {t("sourcesSummary", { count: sources.length })}
            {cited.size > 0 && t("citedSummary", { count: cited.size })}
          </summary>
          <ol lang={sourceLang}>
            {sources.map((s) => (
              <li key={s.n} id={`src-${exchangeId}-${s.n}`} data-cited={cited.has(s.n) || undefined}>
                <span className="sources__n">[{s.n}]</span> {s.label}
              </li>
            ))}
          </ol>
        </details>
      )}
    </>
  );
}

function Reply({ exchange }: { exchange: Exchange }) {
  const t = useTranslations("chat");
  const replay = useTranslations("replay");
  const locale = useLocale();
  const { run, status } = exchange;
  if (status === "paused") {
    // Jamais la réponse d'une autre question : le visiteur sait que la sienne attend.
    return (
      <p className="notice" data-tone="muted" data-testid="paused">
        <span className="notice__tag">{replay("pausedTag")}</span>
        {replay("paused")}
      </p>
    );
  }
  if (status === "failed") {
    return (
      <p className="notice" data-tone="error">
        <span className="notice__tag">{t("errorTag")}</span>
        {exchange.error}
      </p>
    );
  }
  if (run.override) {
    const where = run.blockedAt
      ? t("blockedAt", { stage: stageLabel(run.blockedAt, locale) })
      : t("apiMessage");
    return (
      <p className="notice" data-tone="blocked" data-testid="override">
        <span className="notice__tag">{where}</span>
        {localizeOverride(run.override, locale)}
      </p>
    );
  }
  if (run.answer !== null) {
    return <Answer exchangeId={exchange.id} text={run.answer} sources={parseSources(run.done?.sources ?? [])} />;
  }
  if (status === "stopped") {
    return (
      <p className="notice" data-tone="muted">
        <span className="notice__tag">{t("stoppedTag")}</span>
        {t("stoppedText")}
      </p>
    );
  }
  if (status === "done") {
    return (
      <p className="notice" data-tone="muted">
        {t("noAnswer")}
      </p>
    );
  }
  return (
    <p className="pending">
      <span className="led" aria-hidden="true" />
      {run.tokens > 0 ? t("generating", { tokens: run.tokens }) : t("processing")}
    </p>
  );
}

/* ------------------------------------------------------------------ */
/* Console de questions                                                */
/* ------------------------------------------------------------------ */

type ChatProps = {
  exchanges: readonly Exchange[];
  busy: boolean;
  onAsk: (question: string) => void;
  onStop: () => void;
  /** Première interaction du visiteur avec la saisie (charge `/api/models`, une seule fois). */
  onInteract: () => void;
  models: readonly ModelInfo[];
  model: string | null;
  onModelChange: (id: string) => void;
};

export function Chat({ exchanges, busy, onAsk, onStop, onInteract, models, model, onModelChange }: ChatProps) {
  const t = useTranslations("chat");
  const replay = useTranslations("replay");
  const locale = useLocale();
  const suggestions = suggestionsFor(locale);
  const attacks = attacksFor(locale);
  const [draft, setDraft] = useState("");
  const [attacksOpen, setAttacksOpen] = useState(false);
  const threadRef = useRef<HTMLOListElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const ids = useId();

  const last = exchanges.at(-1);
  useEffect(() => {
    // Le début du dernier échange (sa question) reste visible, même si la réponse est longue.
    const el = threadRef.current;
    const item = el?.lastElementChild;
    if (el && item instanceof HTMLElement && typeof el.scrollTo === "function") {
      el.scrollTo({ top: Math.max(0, item.offsetTop - 12) });
    }
  }, [exchanges.length, last?.run, last?.status]);

  const trimmed = draft.trim();

  function send(question: string) {
    const q = question.trim();
    if (!q || busy || q.length > MAX_QUESTION) return;
    onAsk(q);
    setDraft("");
    setAttacksOpen(false);
    // Le bouton cliqué se désactive pendant la requête : le focus revient à la saisie.
    inputRef.current?.focus();
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    send(draft);
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send(draft);
    }
  }

  return (
    <section className="console" aria-labelledby={`${ids}-title`}>
      <header className="console__bar">
        <h2 id={`${ids}-title`} className="console__title">
          {t("title")}
        </h2>
        {models.length > 1 && (
          <label className="console__model">
            <span>{t("modelLabel")}</span>
            <select value={model ?? ""} onChange={(e) => onModelChange(e.target.value)} disabled={busy}>
              {models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.id}
                </option>
              ))}
            </select>
          </label>
        )}
      </header>

      {exchanges.length === 0 ? (
        <div className="console__empty">
          <p className="console__lede">{t("lede")}</p>
        </div>
      ) : (
        <ol className="thread" ref={threadRef} aria-label={t("threadLabel")}>
          {exchanges.map((x) => (
            <li
              key={x.id}
              className="exchange"
              data-status={x.status}
              data-replay={x.replayOf ? true : undefined}
              data-testid="exchange"
            >
              <div className="exchange__q">
                <span className="exchange__ref" aria-hidden="true">
                  J1
                </span>
                <span className="sr-only">{t("questionPrefix")}</span>
                <div className="exchange__qtext">
                  {x.replayOf && <span className="replay-tag">{replay("tag")}</span>}
                  {x.question.length > 500 ? (
                    <details className="exchange__long-question">
                      <summary>
                        {x.question.slice(0, 220).replace(/\s+/g, " ").trim()}…
                        <span>{t("showFull")}</span>
                      </summary>
                      <p>{x.question}</p>
                    </details>
                  ) : (
                    x.question
                  )}
                </div>
              </div>
              <div
                className="exchange__a"
                aria-live={x === last ? "polite" : undefined}
                data-testid="reply"
              >
                <span className="exchange__ref" aria-hidden="true">
                  J2
                </span>
                <div className="exchange__body">
                  <Reply exchange={x} />
                </div>
              </div>
            </li>
          ))}
        </ol>
      )}

      <div className="prompts" data-compact={exchanges.length > 0 || undefined}>
        <p className="prompts__label" id={`${ids}-suggest`}>
          {t("suggestionsLabel")}
        </p>
        <ul className="prompts__list" aria-labelledby={`${ids}-suggest`}>
          {suggestions.map((q) => (
            <li key={q}>
              <button type="button" className="prompt" disabled={busy} onClick={() => send(q)}>
                {q}
              </button>
            </li>
          ))}
        </ul>
        <div className="attacks">
          <button
            type="button"
            className="attacks__toggle"
            aria-expanded={attacksOpen}
            aria-controls={`${ids}-attacks`}
            disabled={busy}
            onClick={() => setAttacksOpen((o) => !o)}
          >
            {t("attacksToggle")}
            <span aria-hidden="true" className="attacks__chevron">
              ▾
            </span>
          </button>
          {attacksOpen && (
            <ul className="attacks__menu" id={`${ids}-attacks`}>
              {attacks.map((a) => (
                <li key={a.label}>
                  <button type="button" className="attack" onClick={() => send(a.text)}>
                    <span className="attack__label">{a.label}</span>
                    <span className="attack__text">{a.text}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <form className="composer" onSubmit={submit}>
        <label htmlFor={`${ids}-q`} className="sr-only">
          {t("inputLabel")}
        </label>
        <textarea
          id={`${ids}-q`}
          ref={inputRef}
          className="composer__input"
          value={draft}
          maxLength={MAX_QUESTION}
          rows={4}
          placeholder={t("placeholder")}
          aria-describedby={`${ids}-count`}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          onFocus={onInteract}
        />
        <p className="composer__hint">{t("hint")}</p>
        <p className="composer__hint">{t("retention")}</p>
        <div className="composer__row">
          <span id={`${ids}-count`} className="composer__count" data-full={draft.length >= MAX_QUESTION || undefined}>
            {draft.length}/{MAX_QUESTION}
            <span className="sr-only">{t("charsSuffix")}</span>
          </span>
          {busy ? (
            <button type="button" className="btn btn--stop" onClick={onStop}>
              {t("stop")}
            </button>
          ) : (
            <button type="submit" className="btn" disabled={trimmed.length === 0}>
              {t("send")}
            </button>
          )}
        </div>
      </form>
    </section>
  );
}
