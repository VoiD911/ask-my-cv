/**
 * Données des pages /cv et /en/cv : générées au build depuis data/cv.md et data/cv.en.md par
 * `scripts/sync-cv.mjs` (la CI refuse un JSON périmé ou des langues désynchronisées).
 */
import type { Locale } from "@/i18n/locales";

import data from "./cv.json";

export type CvSection = { id: string; title: string; paragraphs: string[] };
export type Cv = { name: string; sections: CvSection[] };

if (data.version !== 1) throw new Error("Données du CV non reconnues");

export const CONTACT_EMAIL = "job@stevelang.net";
export const LINKEDIN_URL = "https://www.linkedin.com/in/steve-cl-lang/";

/** PDF générés après le build par `scripts/cv-pdf.mjs`, publiés à côté de la page. */
export const CV_PDF: Record<Locale, string> = {
  fr: "/cv/Steve-Lang-CV-fr.pdf",
  en: "/en/cv/Steve-Lang-CV-en.pdf",
};

export function cvFor(locale: Locale): Cv {
  return data[locale];
}
