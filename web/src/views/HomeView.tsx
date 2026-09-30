import { useTranslations } from "next-intl";

import { Demo } from "@/components/Demo";
import { SiteNav } from "@/components/SiteNav";

const CONTACT = "job@stevelang.net";

/** Page d'accueil (démo), commune aux racines française et anglaise. */
export function HomeView() {
  const t = useTranslations("home");
  return (
    <div className="page">
      <SiteNav current="/" />
      <header className="titleblock">
        <div className="titleblock__main">
          <p className="titleblock__eyebrow">{t("eyebrow")}</p>
          <h1 className="titleblock__name">Steve Lang</h1>
          <p className="titleblock__role">{t("role")}</p>
        </div>
        <dl className="titleblock__fields">
          <div>
            <dt>{t("sourceTerm")}</dt>
            <dd>{t("sourceValue")}</dd>
          </div>
          <div>
            <dt>{t("modelTerm")}</dt>
            <dd>Claude Haiku 4.5 · Amazon Bedrock</dd>
          </div>
          <div>
            <dt>{t("contactTerm")}</dt>
            <dd>
              <a href={`mailto:${CONTACT}`}>{CONTACT}</a>
            </dd>
          </div>
        </dl>
      </header>

      <main>
        <Demo />
      </main>

      <footer className="colophon">
        <p>{t("privacy")}</p>
      </footer>
    </div>
  );
}
