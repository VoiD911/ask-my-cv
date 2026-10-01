/**
 * Client de `POST /api/ask` : corps signé (SHA-256 des octets exacts, requis
 * par l'OAC Lambda derrière CloudFront) et lecture incrémentale du flux SSE
 * de réponse.
 */

import { createSseParser } from "./sse";
import { isAskEvent, type AskEvent } from "./events";

export type AskErrorKind = "invalid_question" | "signature" | "unavailable";

export class AskError extends Error {
  readonly kind: AskErrorKind;
  readonly status: number | undefined;

  constructor(kind: AskErrorKind, message: string, status?: number) {
    super(message);
    this.name = "AskError";
    this.kind = kind;
    this.status = status;
  }
}

export interface AskParams {
  readonly question: string;
  readonly model?: string | null;
  readonly signal?: AbortSignal;
  readonly onEvent: (event: AskEvent) => void;
  readonly baseUrl?: string;
}

function toHex(digest: ArrayBuffer): string {
  const bytes = new Uint8Array(digest);
  let hex = "";
  for (const byte of bytes) {
    hex += byte.toString(16).padStart(2, "0");
  }
  return hex;
}

async function sha256Hex(bytes: Uint8Array<ArrayBuffer>): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return toHex(digest);
}

/**
 * Clé `localStorage` du jeton de trafic interne (#143) : le propriétaire la renseigne une fois
 * dans son navigateur pour que ses propres essais soient exclus du tableau de bord. Le serveur
 * vérifie le jeton ; il ne change que le classement analytique, jamais le quota.
 */
export const INTERNAL_TOKEN_KEY = "ask-my-cv:internal-token";

function internalToken(): string | null {
  try {
    return globalThis.localStorage?.getItem(INTERNAL_TOKEN_KEY) || null;
  } catch {
    return null; // stockage bloqué (navigation privée, cookies refusés) : trafic public
  }
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

/**
 * Envoie la question, signe le corps, et retransmet chaque événement SSE
 * décodé (et validé) à `onEvent` au fil de l'eau. Se résout une fois le flux
 * terminé (après l'événement `done`, ou fermeture du corps par le serveur).
 *
 * Lève une `AskError` typée pour les réponses HTTP non-2xx ; propage
 * l'`AbortError` tel quel si `signal` est déclenché.
 */
export async function ask(params: AskParams): Promise<void> {
  const { question, model, signal, onEvent, baseUrl = "/api" } = params;

  const payload: { question: string; model?: string } = { question };
  if (model) {
    payload.model = model;
  }
  const bodyText = JSON.stringify(payload);
  const bodyBytes: Uint8Array<ArrayBuffer> = new TextEncoder().encode(bodyText);
  const signature = await sha256Hex(bodyBytes);

  const headers: Record<string, string> = {
    "content-type": "application/json",
    "x-amz-content-sha256": signature,
  };
  // jamais vers une autre origine : seulement un chemin relatif (« /api », pas « //hôte »)
  const sameOrigin = baseUrl.startsWith("/") && !baseUrl.startsWith("//");
  const internal = sameOrigin ? internalToken() : null;
  if (internal) {
    headers["x-internal-token"] = internal;
  }

  let response: Response;
  try {
    response = await fetch(`${baseUrl}/ask`, {
      method: "POST",
      headers,
      body: bodyBytes,
      signal,
    });
  } catch (error) {
    if (isAbortError(error)) throw error;
    throw new AskError("unavailable", "service indisponible (réseau)");
  }

  if (!response.ok) {
    if (response.status === 422) {
      throw new AskError("invalid_question", "question invalide", 422);
    }
    if (response.status === 403) {
      throw new AskError("signature", "signature refusée", 403);
    }
    throw new AskError("unavailable", `service indisponible (${response.status})`, response.status);
  }

  const body = response.body;
  if (!body) {
    throw new AskError("unavailable", "réponse sans corps");
  }

  const reader = body.getReader();
  const decoder = new TextDecoder();
  const parser = createSseParser((message) => {
    let parsed: unknown;
    try {
      parsed = JSON.parse(message.data);
    } catch {
      return; // ligne data: non-JSON : ignorée, sse.ts a déjà compté l'anomalie de forme
    }
    if (isAskEvent(parsed)) {
      onEvent(parsed);
    }
  });

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      parser.push(decoder.decode(value, { stream: true }));
    }
    parser.push(decoder.decode());
  } catch (error) {
    if (isAbortError(error)) throw error;
    throw new AskError("unavailable", "flux interrompu");
  } finally {
    reader.releaseLock();
  }
}
