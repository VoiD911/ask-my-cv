import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { SiteNav } from "@/components/SiteNav";
import {
  commitUrl,
  deliveryPlans,
  documentUrl,
  eventLinks,
  formatDate,
  issueLinksFor,
} from "@/lib/delivery";

const KIND: Record<string, string> = {
  implementation: "Implémentation",
  review: "Revue",
  fix: "Correction",
  other: "Autre",
};

export function generateStaticParams() {
  return deliveryPlans.map((plan) => ({ plan: plan.id }));
}

export async function generateMetadata({ params }: { params: Promise<{ plan: string }> }): Promise<Metadata> {
  const { plan: id } = await params;
  const plan = deliveryPlans.find((item) => item.id === id);
  return { title: plan ? `Plan ${plan.id} — Livraison` : "Plan introuvable" };
}

export default async function PlanPage({ params }: { params: Promise<{ plan: string }> }) {
  const { plan: id } = await params;
  const plan = deliveryPlans.find((item) => item.id === id);
  if (!plan) notFound();

  return (
    <div className="page delivery-page">
      <SiteNav current="/livraison/" />
      <header className="titleblock delivery-hero">
        <div>
          <p className="titleblock__eyebrow">Livraison · plan {plan.id}</p>
          <h1 className="titleblock__name">Plan {plan.id}</h1>
          <p className="titleblock__role">{plan.goal}</p>
        </div>
        <div className="delivery-hero__links">
          <Link href="/livraison/">← Tous les plans</Link>
          <a href={documentUrl(plan.plan_doc)}>Plan complet ↗</a>
          <a href={documentUrl(plan.journal)}>Journal complet ↗</a>
        </div>
      </header>

      <main className="delivery-main">
        <p className="delivery-note">
          Chronologie des rapports des agents. Les consignes, les échanges privés et les valeurs
          masquées ne sont pas publiés. Les issues historiques indiquent la date réelle du travail.
        </p>
        {plan.tasks.map((task, taskIndex) => (
          <section className="delivery-task" key={task.label} aria-labelledby={`task-${taskIndex}`}>
            <div className="delivery-task__head">
              <div><p className="titleblock__eyebrow">Étape {String(taskIndex + 1).padStart(2, "0")}</p><h2 id={`task-${taskIndex}`}>{task.label}</h2></div>
              <div className="delivery-task__issues">
                {issueLinksFor(plan.id, task.label).map((issue) => <a href={issue.href} key={issue.href}>{issue.label} ↗</a>)}
              </div>
            </div>
            <ol className="delivery-events">
              {task.events.map((event, eventIndex) => (
                <li className="delivery-event" key={`${event.date}-${eventIndex}`}>
                  <div className="delivery-event__rail" aria-hidden="true" />
                  <div className="delivery-event__body">
                    <div className="delivery-event__meta">
                      <span className={`delivery-event__kind delivery-event__kind--${event.type}`}>{KIND[event.type] ?? "Autre"}</span>
                      <time dateTime={event.date}>{formatDate(event.date)} UTC</time>
                      <span>{event.model}</span>
                    </div>
                    <h3>{event.description}</h3>
                    {event.verdict && <p className="delivery-event__verdict">Verdict : {event.verdict}</p>}
                    {event.summary && <details className="delivery-event__summary"><summary>Extrait du rapport</summary><p>{event.summary}</p></details>}
                    {(event.commits.length > 0 || event.links.length > 0) && (
                      <div className="delivery-event__links">
                        {event.commits.map((sha) => <a key={sha} href={commitUrl(sha)}>Commit {sha.slice(0, 7)} ↗</a>)}
                        {eventLinks(event.links).map((url) => <a key={url} href={url}>{url.includes("/pull/") ? "PR" : "Issue"} #{url.split("/").at(-1)} ↗</a>)}
                      </div>
                    )}
                  </div>
                </li>
              ))}
            </ol>
          </section>
        ))}
      </main>
    </div>
  );
}
