import { getRequestConfig } from "next-intl/server";

import { DEFAULT_LOCALE, isLocale } from "./locales";
import { MESSAGES } from "./messages";

// Export statique : pas de middleware. La langue vient de `setRequestLocale`, appelé par
// chaque layout et chaque page (arborescences (fr) et (en)).
export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  const locale = isLocale(requested) ? requested : DEFAULT_LOCALE;
  return { locale, messages: MESSAGES[locale] };
});
