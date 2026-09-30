import type { Metadata } from "next";
import Link from "next/link";

import { SiteNav } from "@/components/SiteNav";
import { deliveryPlans, documentUrl } from "@/lib/delivery";

export const metadata: Metadata = {
  title: "Livraison — Interroge mon CV",
  description: "Plans, tâches, revues et preuves publiques du développement d'Interroge mon CV.",
};

const totalEvents = deliveryPlans.reduce(
  (sum, plan) => sum + plan.tasks.reduce((count, task) => count + task.events.length, 0),
  0,
);

export default function Livraison() {
  return (
    <div className="page delivery-page">
      <SiteNav current="/livraison/" />
      <header className="titleblock delivery-hero">
        <div>
          <p className="titleblock__eyebrow">Archives publiques · travaux vérifiables</p>
          <h1 className="titleblock__name">Livraison</h1>
          <p className="titleblock__role">
            De la décision au déploiement : les plans, les tâches, les revues et les corrections
            qui ont construit ce projet.
          </p>
        </div>
        <dl className="delivery-stats">
          <div><dt>Plans</dt><dd>{deliveryPlans.length}</dd></div>
          <div><dt>Rapports</dt><dd>{totalEvents}</dd></div>
          <div><dt>Source</dt><dd>Journal public</dd></div>
        </dl>
      </header>

      <main className="delivery-main">
        <section className="delivery-intro" aria-labelledby="delivery-method">
          <h2 id="delivery-method">Une méthode lisible de bout en bout</h2>
          <ol className="delivery-chain">
            {[
              "Objectifs",
              "Plan",
              "Tâche",
              "Implémentation",
              "Revue",
              "CI",
              "Déploiement",
            ].map((step, index) => <li key={step}><span>{String(index + 1).padStart(2, "0")}</span>{step}</li>)}
          </ol>
          <p>
            L’architecte fixe les objectifs et arbitre. Des agents implémentent et révisent ; la
            CI, les signatures et les évaluations vérifient les résultats. Les dates de travail
            précèdent parfois la création des issues, reconstituées après coup.
          </p>
          <p className="delivery-intro__links">
            <a href={documentUrl("docs/spec/2026-09-25-xops-kit-design.md")}>Lire la spec ↗</a>
            <a href={`${documentUrl("docs/journal/index.json")}?raw=1`}>Données du journal ↗</a>
          </p>
        </section>

        <section aria-labelledby="delivery-plans">
          <div className="delivery-heading">
            <p className="titleblock__eyebrow">Index · 12 plans</p>
            <h2 id="delivery-plans">Parcours du projet</h2>
          </div>
          <ol className="delivery-plan-grid">
            {deliveryPlans.map((plan, index) => {
              const reports = plan.tasks.reduce((count, task) => count + task.events.length, 0);
              return (
                <li key={plan.id} className="delivery-plan">
                  <Link href={`/livraison/${plan.id}/`} className="delivery-plan__link">
                    <span className="delivery-plan__top"><span>{String(index + 1).padStart(2, "0")}</span><span>Plan {plan.id}</span></span>
                    <h3>{plan.title.replace(/^« Interroge mon CV » — plan [^:]+ : /, "").replace(/ — plan d’implémentation$| — plan d'implémentation$/, "")}</h3>
                    <p>{plan.goal}</p>
                    <span className="delivery-plan__bottom">{plan.tasks.length} étapes · {reports} rapports <span aria-hidden="true">↗</span></span>
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
