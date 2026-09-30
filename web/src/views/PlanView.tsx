import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";

import { MESSAGES } from "@/i18n/messages";

import { SiteNav } from "@/components/SiteNav";
import { localePath } from "@/i18n/locales";
import {
  commitUrl,
  documentUrl,
  eventLinks,
  formatDate,
  issueLinksFor,
  taskLabel,
  type DeliveryPlan,
} from "@/lib/delivery";

const KINDS = ["implementation", "review", "fix", "other"] as const;

/**
 * Page d'un plan du journal (/livraison/<id>/), commune aux deux langues. Les textes du
 * journal restent tels quels : objectifs en français (`lang="fr"` dans l'interface anglaise),
 * rapports des agents dans leur langue d'origine ; seuls les verdicts connus sont traduits.
 */
export function PlanView({ plan }: { plan: DeliveryPlan }) {
  const t = useTranslations("delivery");
  const locale = useLocale();
  const journalLang = locale === "fr" ? undefined : "fr";
  const kind = (type: string) => t(`kinds.${KINDS.find((k) => k === type) ?? "other"}`);
  const verdicts = MESSAGES[locale].delivery.verdicts;
  // Verdicts du journal, écrits en français : traduits s'ils sont connus, sinon tels quels.
  const verdict = (text: string) => {
    const fr = MESSAGES.fr.delivery.verdicts;
    const key = (Object.keys(fr) as (keyof typeof fr)[]).find((k) => fr[k] === text);
    return key ? verdicts[key] : text;
  };
  return (
    <div className="page delivery-page">
      <SiteNav current="/livraison/" path={`/livraison/${plan.id}/`} />
      <header className="titleblock delivery-hero">
        <div>
          <p className="titleblock__eyebrow">{t("planEyebrow", { id: plan.id })}</p>
          <h1 className="titleblock__name">{t("planLabel", { id: plan.id })}</h1>
          <p className="titleblock__role" lang={journalLang}>{plan.goal}</p>
        </div>
        <div className="delivery-hero__links">
          <Link href={localePath(locale, "/livraison/")}>{t("back")}</Link>
          <a href={documentUrl(plan.plan_doc)}>{t("fullPlan")}</a>
          <a href={documentUrl(plan.journal)}>{t("fullJournal")}</a>
        </div>
      </header>

      <main className="delivery-main">
        <p className="delivery-note">{t("planNote")}</p>
        {journalLang ? <p className="delivery-note" data-testid="journal-language">{t("journalLanguage")}</p> : null}
        {plan.tasks.map((task, taskIndex) => (
          <section className="delivery-task" key={task.label} aria-labelledby={`task-${taskIndex}`}>
            <div className="delivery-task__head">
              <div><p className="titleblock__eyebrow">{t("step", { n: String(taskIndex + 1).padStart(2, "0") })}</p><h2 id={`task-${taskIndex}`}>{taskLabel(task.label, locale)}</h2></div>
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
                      <span className={`delivery-event__kind delivery-event__kind--${event.type}`}>{kind(event.type)}</span>
                      <time dateTime={event.date}>{formatDate(event.date, locale)} {t("utc")}</time>
                      <span>{event.model}</span>
                    </div>
                    <h3>{event.description}</h3>
                    {event.verdict && <p className="delivery-event__verdict">{t("verdict", { verdict: verdict(event.verdict) })}</p>}
                    {event.summary && (
                      <details className="delivery-event__summary">
                        <summary>{t("excerpt")}</summary>
                        <p>{event.summary}</p>
                      </details>
                    )}
                    {(event.commits.length > 0 || event.links.length > 0) && (
                      <div className="delivery-event__links">
                        {event.commits.map((sha) => <a key={sha} href={commitUrl(sha)}>{t("commit", { sha: sha.slice(0, 7) })}</a>)}
                        {eventLinks(event.links).map((url) => (
                          <a key={url} href={url}>
                            {t(url.includes("/pull/") ? "pull" : "issue", { n: url.split("/").at(-1) ?? "" })}
                          </a>
                        ))}
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
