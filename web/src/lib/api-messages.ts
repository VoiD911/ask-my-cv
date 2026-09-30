/**
 * Messages en français renvoyés tels quels par l'API (qui reste inchangée) et leur rendu dans
 * la langue de l'interface. Les valeurs françaises du catalogue sont exactement celles de
 * `src/ask_my_cv/pipeline.py` (BLOCK_MESSAGES, ERROR_MESSAGE) et de `output_guard.py`
 * (REFUSAL) : `api-messages.test.ts` le vérifie en lisant les sources Python.
 */
import type { Locale } from "@/i18n/locales";
import { MESSAGES } from "@/i18n/messages";

/** Phrase de refus exacte du prompt (`output_guard.REFUSAL`), toujours en français. */
export const REFUSAL = MESSAGES.fr.chat.refusal;

// Même normalisation que `output_guard._is_refusal` : guillemets et blancs ignorés.
const DECORATION = /[«»"“”\s]+/g;

/** La réponse est-elle la phrase de refus (reconnue comme le fait le garde-fou de sortie) ? */
export function isRefusal(text: string): boolean {
  return text.replace(DECORATION, " ").trim() === REFUSAL;
}

type OverrideKey = keyof (typeof MESSAGES)["fr"]["overrides"];

/**
 * Message de blocage ou d'erreur de l'API (`answer_override`) dans la langue de l'interface.
 * Un message inconnu (API plus récente) est affiché tel quel.
 */
export function localizeOverride(text: string, locale: Locale): string {
  if (locale === "fr") return text;
  const fr = MESSAGES.fr.overrides;
  const key = (Object.keys(fr) as OverrideKey[]).find((k) => fr[k] === text);
  return key ? MESSAGES[locale].overrides[key] : text;
}
