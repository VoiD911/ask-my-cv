"use client";

import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";

import type { Locale } from "@/i18n/locales";

import { AskError } from "@/lib/ask";
import type { AskEvent } from "@/lib/events";
import { fetchModels, type ModelInfo } from "@/lib/models";
import { createInitialState, reduce } from "@/lib/pipeline";
import {
  isReplayForced,
  kindOf,
  loadReplays,
  pickReplay,
  play,
  type Replay,
  type ReplayKind,
} from "@/lib/replay";
import { askResilient } from "@/lib/resilient";

import { attacksFor, Chat, type Exchange, type ExchangeStatus } from "./Chat";
import { Circuit } from "./Circuit";
import { DemoFooter } from "./DemoFooter";
import { ReplayBanner, type ReplayReason } from "./ReplayBanner";
import { prefersReducedMotion } from "./useReducedMotion";

type Action =
  | { type: "start"; id: number; question: string; locale?: Locale; replayOf?: string }
  | { type: "event"; id: number; event: AskEvent }
  | { type: "finish"; id: number; status: Exclude<ExchangeStatus, "running">; error?: string };

/** Réducteur des échanges : chaque événement SSE passe par `reduce` du pipeline. */
export function exchangesReducer(state: Exchange[], action: Action): Exchange[] {
  switch (action.type) {
    case "start":
      return [
        ...state,
        {
          id: action.id,
          question: action.question,
          run: createInitialState(action.locale),
          status: "running",
          ...(action.replayOf ? { replayOf: action.replayOf } : {}),
        },
      ];
    case "event":
      return state.map((x) => (x.id === action.id ? { ...x, run: reduce(x.run, action.event) } : x));
    case "finish":
      return state.map((x) =>
        x.id === action.id && x.status === "running"
          ? { ...x, status: action.status, ...(action.error ? { error: action.error } : {}) }
          : x,
      );
  }
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

/**
 * La démo : console de questions, circuit du pipeline et relevé, reliés au flux SSE. Service
 * en pause (budget du jour, panne) : rediffusion d'un échange réel enregistré en production.
 */
export function Demo() {
  const locale = useLocale();
  const errorText = useTranslations("errors");
  const idle = useMemo(() => createInitialState(locale), [locale]);
  const [exchanges, dispatch] = useReducer(exchangesReducer, []);
  const [models, setModels] = useState<readonly ModelInfo[]>([]);
  const [model, setModel] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  const nextId = useRef(1);
  const modelsRequested = useRef(false);

  // Chargé à la première interaction plutôt qu'au montage : la page reste inerte tant que
  // le visiteur n'a pas commencé à poser une question (Lighthouse sur l'export statique,
  // sans API, ne doit pas voir de requête /api/models échouer dès le chargement).
  const loadModels = useCallback(() => {
    if (modelsRequested.current) return;
    modelsRequested.current = true;
    fetchModels()
      .then((res) => {
        setModels(res.models);
        setModel(res.default);
      })
      .catch(() => {
        // Sélecteur masqué : l'API choisit son modèle par défaut.
      });
  }, []);

  useEffect(() => {
    const ac = new AbortController();
    life.current = ac;
    return () => {
      ac.abort();
      controller.current?.abort();
    };
  }, []);

  const current = exchanges.at(-1);
  const busy = current?.status === "running";

  // Durée de vie du composant : toute lecture s'arrête au démontage.
  const life = useRef<AbortController | null>(null);
  const forced = useRef<boolean | null>(null);
  const [mode, setMode] = useState<{ reason: ReplayReason; recordedAt: string } | null>(null);
  const replays = useRef<Promise<readonly Replay[]> | null>(null);
  const turn = useRef(0);

  // Rediffusions chargées seulement quand le service est en pause (ou `?replay=1`).
  const getReplays = useCallback(() => {
    replays.current ??= loadReplays(locale);
    return replays.current;
  }, [locale]);

  /** Rejoue un échange enregistré, au travers du même réducteur que le direct. */
  const startReplay = useCallback(
    async (kind: ReplayKind | null, reason: ReplayReason): Promise<boolean> => {
      const replay = pickReplay(await getReplays(), kind, turn.current);
      if (!replay || life.current?.signal.aborted) return false;
      turn.current += 1;
      const id = nextId.current++;
      const ac = new AbortController();
      controller.current = ac;
      setMode({ reason, recordedAt: replay.recordedAt });
      dispatch({ type: "start", id, question: replay.question, locale, replayOf: replay.recordedAt });
      const signals = life.current ? [ac.signal, life.current.signal] : [ac.signal];
      const result = await play(replay.frames, (event) => dispatch({ type: "event", id, event }), {
        // Lue au lancement : `?replay=1` démarre avant qu'un rendu ait pu voir la préférence.
        reducedMotion: prefersReducedMotion(),
        signal: AbortSignal.any(signals),
      });
      dispatch({ type: "finish", id, status: result });
      if (controller.current === ac) controller.current = null;
      return true;
    },
    [getReplays, locale],
  );

  useEffect(() => {
    // `?replay=1` (démos, tests) : lu après l'hydratation, l'export statique est commun.
    if (forced.current !== null) return; // une seule fois
    forced.current = isReplayForced(window.location.search);
    if (forced.current) void startReplay(null, "forced");
  }, [startReplay]);

  const onAsk = useCallback(
    async (question: string) => {
      const id = nextId.current++;
      const kind = kindOf(question, attacksFor(locale).map((a) => a.text));
      if (forced.current) {
        dispatch({ type: "start", id, question, locale });
        dispatch({ type: "finish", id, status: "paused" });
        await startReplay(kind, "forced");
        return;
      }
      loadModels();
      const ac = new AbortController();
      controller.current = ac;
      dispatch({ type: "start", id, question, locale });
      try {
        const outcome = await askResilient({
          question,
          model: models.length > 1 ? model : null,
          signal: ac.signal,
          onEvent: (event) => dispatch({ type: "event", id, event }),
        });
        if (outcome.kind === "ok") {
          dispatch({ type: "finish", id, status: "done" });
          setMode(null); // le direct répond de nouveau : fin du mode rediffusion
          return;
        }
        if (controller.current === ac) controller.current = null;
        const reason = outcome.reason;
        // Pas de rediffusion disponible : message habituel (budget : celui de l'API).
        const fallback = () =>
          reason === "budget"
            ? dispatch({ type: "finish", id, status: "done" })
            : dispatch({ type: "finish", id, status: "failed", error: errorText("unavailable") });
        if ((await getReplays()).length === 0) {
          fallback();
          return;
        }
        dispatch({ type: "finish", id, status: "paused" });
        if (!(await startReplay(kind, reason))) fallback();
      } catch (error) {
        if (isAbort(error)) {
          dispatch({ type: "finish", id, status: "stopped" });
        } else {
          const text = errorText(error instanceof AskError ? error.kind : "unavailable");
          dispatch({ type: "finish", id, status: "failed", error: text });
        }
      } finally {
        if (controller.current === ac) controller.current = null;
      }
    },
    [errorText, getReplays, loadModels, locale, model, models.length, startReplay],
  );

  const onNextReplay = useCallback(() => {
    if (mode) void startReplay(null, mode.reason);
  }, [mode, startReplay]);

  const onStop = useCallback(() => controller.current?.abort(), []);

  return (
    <>
      {/* Région annoncée toujours présente : le bandeau inséré est lu par les lecteurs d'écran. */}
      <div aria-live="polite" data-testid="replay-live">
        {mode && <ReplayBanner reason={mode.reason} recordedAt={mode.recordedAt} busy={busy} onNext={onNextReplay} />}
      </div>
      <div className="bench">
      <div className="bench__chat">
        <Chat
          exchanges={exchanges}
          busy={busy}
          onAsk={(q) => void onAsk(q)}
          onStop={onStop}
          onInteract={loadModels}
          models={models}
          model={model}
          onModelChange={setModel}
        />
      </div>
      <div className="bench__circuit">
        <Circuit state={current?.run ?? idle} />
        <DemoFooter done={current?.run.done ?? null} recorded={current?.replayOf !== undefined} />
      </div>
      </div>
    </>
  );
}
