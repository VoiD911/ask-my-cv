/**
 * Langues du site. Le français reste à la racine (`/`, `/architecture/`…) : ces URL sont déjà
 * partagées publiquement et ne changent pas. L'anglais vit sous `/en/…`.
 */
export const LOCALES = ["fr", "en"] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "fr";

export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && (LOCALES as readonly string[]).includes(value);
}

/** Chemin d'une page (forme française, avec barre finale) dans la langue voulue. */
export function localePath(locale: Locale, path: string): string {
  if (!path.startsWith("/")) throw new Error(`Chemin relatif inattendu : ${path}`);
  return locale === DEFAULT_LOCALE ? path : `/${locale}${path}`;
}

/** L'autre langue, pour le sélecteur (deux langues seulement). */
export function otherLocale(locale: Locale): Locale {
  return locale === "fr" ? "en" : "fr";
}

/** Locale BCP 47 utilisée pour les nombres, montants et dates. */
export const FORMAT_LOCALE: Record<Locale, string> = { fr: "fr-FR", en: "en-US" };
