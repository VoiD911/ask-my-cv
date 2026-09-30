import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";

import { SiteNav } from "@/components/SiteNav";
import { localePath } from "@/i18n/locales";
import { deliveryPlans, documentUrl } from "@/lib/delivery";

const totalEvents = deliveryPlans.reduce(
  (sum, plan) => sum + plan.tasks.reduce((count, task) => count + task.events.length, 0),
  0,
);

/** Titre court d'un plan : sans le préfixe du projet ni le suffixe « plan d'implémentation ». */
function shortTitle(title: string): string {
  return title
    .replace(/^« Interroge mon CV » — plan [^:]+ : /, "")
    .replace(/ — plan d’implémentation$| — plan d'implémentation$/, "");
}

/**
 * Page /livraison, commune aux deux langues. Le journal (titres, objectifs, rapports) est
 * généré depuis les documents français du dépôt : il reste en français, balisé `lang="fr"`
 * dans l'interface anglaise.
 */
export function DeliveryView() {
  const t = useTranslations("delivery");
  const locale = useLocale();
  const journalLang = locale === "fr" ? undefined : "fr";
  const chain: string[] = t.raw("chain");
  return (
    <div className="page delivery-page">
      <SiteNav current="/livraison/" />
      <header className="titleblock delivery-hero">
        <div>
          <p className="titleblock__eyebrow">{t("eyebrow")}</p>
          <h1 className="titleblock__name">{t("heading")}</h1>
          <p className="titleblock__role">{t("lede")}</p>
        </div>
        <dl className="delivery-stats">
          <div><dt>{t("statPlans")}</dt><dd>{deliveryPlans.length}</dd></div>
          <div><dt>{t("statReports")}</dt><dd>{totalEvents}</dd></div>
          <div><dt>{t("statSource")}</dt><dd>{t("statSourceValue")}</dd></div>
        </dl>
      </header>

      <main className="delivery-main">
        <section className="delivery-intro" aria-labelledby="delivery-method">
          <h2 id="delivery-method">{t("methodTitle")}</h2>
          <ol className="delivery-chain">
            {chain.map((step, index) => (
              <li key={step}><span>{String(index + 1).padStart(2, "0")}</span>{step}</li>
            ))}
          </ol>
          <p>{t("method")}</p>
          {journalLang ? <p data-testid="journal-language">{t("journalLanguage")}</p> : null}
          <p className="delivery-intro__links">
            <a href={documentUrl("docs/spec/2026-09-25-xops-kit-design.md")}>{t("readSpec")}</a>
            <a href={`${documentUrl("docs/journal/index.json")}?raw=1`}>{t("journalData")}</a>
          </p>
        </section>

        <section aria-labelledby="delivery-plans">
          <div className="delivery-heading">
            <p className="titleblock__eyebrow">{t("indexEyebrow", { count: deliveryPlans.length })}</p>
            <h2 id="delivery-plans">{t("plansTitle")}</h2>
          </div>
          <ol className="delivery-plan-grid">
            {deliveryPlans.map((plan, index) => {
              const reports = plan.tasks.reduce((count, task) => count + task.events.length, 0);
              return (
                <li key={plan.id} className="delivery-plan">
                  <Link href={localePath(locale, `/livraison/${plan.id}/`)} className="delivery-plan__link">
                    <span className="delivery-plan__top"><span>{String(index + 1).padStart(2, "0")}</span><span>{t("planLabel", { id: plan.id })}</span></span>
                    <h3 lang={journalLang}>{shortTitle(plan.title)}</h3>
                    <p lang={journalLang}>{plan.goal}</p>
                    <span className="delivery-plan__bottom">{t("planStats", { tasks: plan.tasks.length, reports })} <span aria-hidden="true">↗</span></span>
                  </Link>
                </li>
              );
            })}
          </ol>
        </section>
      </main>
    </div>
  );
}
