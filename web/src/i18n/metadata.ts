import type { Metadata } from "next";

import { LOCALES, localePath, type Locale } from "./locales";
import { MESSAGES } from "./messages";

export const SITE_URL = "https://job.stevelang.net";

/**
 * Métadonnées communes d'une page : titre, description, URL canonique de la langue courante
 * et alternatives hreflang (fr, en, x-default → français). `path` : chemin français.
 */
export function pageMetadata(
  locale: Locale,
  path: string,
  { title, description }: { title: string; description?: string },
): Metadata {
  const languages: Record<string, string> = {};
  for (const l of LOCALES) languages[l] = localePath(l, path);
  languages["x-default"] = path;
  const meta = MESSAGES[locale].meta;
  return {
    title,
    ...(description ? { description } : {}),
    alternates: { canonical: localePath(locale, path), languages },
    openGraph: {
      type: "website",
      locale: meta.ogLocale,
      url: localePath(locale, path),
      siteName: meta.siteName,
      title,
      ...(description ? { description } : {}),
    },
  };
}
