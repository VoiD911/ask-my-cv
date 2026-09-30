import { createTranslator } from "next-intl";

import type { Locale } from "./locales";
import { MESSAGES } from "./messages";

/**
 * Traducteur hors composant (fonctions pures : résumé aria-live, libellés du circuit). Même
 * catalogue que `useTranslations`, sans contexte React.
 */
export function translator(locale: Locale) {
  return createTranslator({ locale, messages: MESSAGES[locale] });
}
