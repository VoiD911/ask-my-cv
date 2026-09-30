import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";

import { SiteNav } from "@/components/SiteNav";
import { localePath } from "@/i18n/locales";
import { CONTACT_EMAIL, CV_PDF, cvFor, LINKEDIN_URL } from "@/lib/cv";

/**
 * Page /cv, commune aux racines française et anglaise : le CV public en HTML (source
 * data/cv.md ou data/cv.en.md), le contact et le lien vers le PDF. La même page, en média
 * `print`, sert de gabarit au PDF (scripts/cv-pdf.mjs) : la feuille d'impression masque la
 * navigation et les éléments interactifs.
 */
export function CvView() {
  const t = useTranslations("cv");
  const locale = useLocale();
  const cv = cvFor(locale);
  const pdf = CV_PDF[locale];
  return (
    <div className="page cv-page">
      <SiteNav current="/cv/" />
      <header className="titleblock cv-head">
        <div className="titleblock__main">
          <p className="titleblock__eyebrow">{t("eyebrow")}</p>
          <h1 className="titleblock__name">{cv.name}</h1>
          <p className="titleblock__role">{t("role")}</p>
        </div>
        <div className="cv-head__side">
          <dl className="titleblock__fields" aria-label={t("contactLabel")}>
            <div>
              <dt>{t("emailTerm")}</dt>
              <dd>
                <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>
              </dd>
            </div>
            <div>
              <dt>{t("linkedinTerm")}</dt>
              <dd>
                <a href={LINKEDIN_URL} rel="me noopener">
                  {t("linkedinText")}
                </a>
              </dd>
            </div>
          </dl>
          <a className="cv-download" href={pdf} download type="application/pdf" hrefLang={locale}>
            <span aria-hidden="true">↓ </span>
            {t("download")}
          </a>
        </div>
      </header>

      <main className="cv-main">
        {cv.sections.map((section) => (
          <section key={section.id} id={section.id} className="cv-section" aria-labelledby={`${section.id}-titre`}>
            <h2 id={`${section.id}-titre`}>{section.title}</h2>
            {section.paragraphs.map((p) => (
              <p key={p}>{p}</p>
            ))}
          </section>
        ))}
        <aside className="cv-ask" aria-labelledby="cv-ask-titre">
          <h2 id="cv-ask-titre">{t("askTitle")}</h2>
          <p>
            {t("ask")} <Link href={localePath(locale, "/")}>{t("askLink")}</Link>
          </p>
        </aside>
      </main>

      <footer className="colophon">
        <p>{t("source")}</p>
      </footer>
    </div>
  );
}
