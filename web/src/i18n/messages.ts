import en from "../../messages/en.json";
import fr from "../../messages/fr.json";

import type { Locale } from "./locales";

export type Messages = typeof fr;

/** Catalogues complets ; l'égalité des clés FR/EN est vérifiée par `messages.test.ts`. */
export const MESSAGES: Record<Locale, Messages> = { fr, en };

/** Espaces de noms utilisés par les composants client (seuls envoyés au navigateur). */
export const CLIENT_NAMESPACES = ["chat", "overrides", "errors", "circuit", "readout"] as const;

export function clientMessages(locale: Locale): Pick<Messages, (typeof CLIENT_NAMESPACES)[number]> {
  const all = MESSAGES[locale];
  return {
    chat: all.chat,
    overrides: all.overrides,
    errors: all.errors,
    circuit: all.circuit,
    readout: all.readout,
  };
}
