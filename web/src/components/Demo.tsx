"use client";

import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";

import type { Locale } from "@/i18n/locales";

import { AskError, ask } from "@/lib/ask";
import type { AskEvent } from "@/lib/events";
import { fetchModels, type ModelInfo } from "@/lib/models";
import { createInitialState, reduce } from "@/lib/pipeline";

import { Chat, type Exchange, type ExchangeStatus } from "./Chat";
import { Circuit } from "./Circuit";
import { DemoFooter } from "./DemoFooter";

type Action =
  | { type: "start"; id: number; question: string; locale?: Locale }
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

/** La démo : console de questions, circuit du pipeline et relevé, reliés au flux SSE. */
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

  useEffect(() => () => controller.current?.abort(), []);

  const current = exchanges.at(-1);
  const busy = current?.status === "running";

  const onAsk = useCallback(
    async (question: string) => {
      loadModels();
      const id = nextId.current++;
      const ac = new AbortController();
      controller.current = ac;
      dispatch({ type: "start", id, question, locale });
      try {
        await ask({
          question,
          model: models.length > 1 ? model : null,
          signal: ac.signal,
          onEvent: (event) => dispatch({ type: "event", id, event }),
        });
        dispatch({ type: "finish", id, status: "done" });
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
    [errorText, loadModels, locale, model, models.length],
  );

  const onStop = useCallback(() => controller.current?.abort(), []);

  return (
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
        <DemoFooter done={current?.run.done ?? null} />
      </div>
    </div>
  );
}
