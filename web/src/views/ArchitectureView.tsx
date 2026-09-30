import { useLocale } from "next-intl";
import type { ReactNode } from "react";

import {
  Board,
  Flow,
  InfraBanks,
  Sources,
  triggerLabel,
  WorkflowGraph,
  type Node,
} from "@/components/ArchitectureDiagrams";
import { Glossary, Rich } from "@/components/Glossary";
import { SiteNav } from "@/components/SiteNav";
import { architecture, workflow } from "@/lib/architecture";
import { architectureContent } from "@/lib/architecture-content.en";

const { pipeline, model } = architecture;
const ci = workflow("ci.yml");
const others = architecture.workflows.filter((w) => w !== ci);
const resourceCount = architecture.infra.reduce((n, g) => n + g.resources.length, 0);
const jobCount = architecture.workflows.reduce((n, w) => n + w.jobs.length, 0);

type SectionText = { id: string; title: string; paragraphs: string[]; sources: { label: string; path: string }[] };

function Section({
  section,
  index,
  children,
}: {
  section: SectionText;
  index: number;
  children: ReactNode;
}) {
  return (
    <section className="arch-section" aria-labelledby={`${section.id}-titre`} id={section.id}>
      <div className="arch-section__text">
        <p className="titleblock__eyebrow">{String(index).padStart(2, "0")}</p>
        <h2 id={`${section.id}-titre`}>{section.title}</h2>
        {section.paragraphs.map((p, i) => (
          <p key={i}>
            <Rich text={p} />
          </p>
        ))}
        <Sources links={section.sources} />
      </div>
      {children}
    </section>
  );
}

/** Page /architecture, commune aux racines française et anglaise. */
export function ArchitectureView() {
  const locale = useLocale();
  const { page, stageText, request, roleText, infra, jobText, delivery, lifecycle } = architectureContent(locale);
  const stageNodes: Node[] = pipeline.stages.map((name, i) => ({
    key: name,
    ref: `U${i + 1}`,
    label: stageText[name]?.label ?? name,
    detail: stageText[name]?.detail ?? "",
  }));
  const sections: SectionText[] = [request, infra, delivery, lifecycle];
  const deploy = ci.jobs.find((j) => j.id === "deploy");
  return (
    <div className="page delivery-page arch-page">
      <SiteNav current="/architecture/" />
      <header className="titleblock delivery-hero">
        <div>
          <p className="titleblock__eyebrow">{page.eyebrow}</p>
          <h1 className="titleblock__name">{page.heading}</h1>
          <p className="titleblock__role">
            <Rich text={page.lede} />
          </p>
        </div>
        <dl className="delivery-stats">
          <div><dt>{page.statsLabels.stages}</dt><dd>{pipeline.stages.length}</dd></div>
          <div><dt>{page.statsLabels.resources}</dt><dd>{resourceCount}</dd></div>
          <div><dt>{page.statsLabels.jobs}</dt><dd>{jobCount}</dd></div>
        </dl>
      </header>

      <main className="delivery-main">
        <nav className="arch-toc" aria-label={page.tocLabel}>
          <ol>
            {sections.map((s, i) => (
              <li key={s.id}>
                <a href={`#${s.id}`}>
                  <span>{String(i + 1).padStart(2, "0")}</span>
                  {s.title}
                </a>
              </li>
            ))}
          </ol>
          <p>{page.generated}</p>
        </nav>

        <Section section={request} index={1}>
          <Board
            title={request.boardTitle}
            meta={page.requestMeta(pipeline.stages.length, model.version)}
            alt={request.alt(stageNodes.map((n) => n.label))}
          >
            <div className="arch-request">
              <Flow nodes={request.edgeIn} label={page.flowIn} tone="idle" />
              <Flow nodes={stageNodes} label={page.flowStages} />
              <Flow nodes={request.edgeOut} label={page.flowOut} tone="idle" />
            </div>
            <ul className="arch-notes">
              <li>{request.guardrailNote(pipeline.guardrailMinChars)}</li>
              <li>{request.modelNote(model.version)}</li>
            </ul>
          </Board>
        </Section>

        <Section section={infra} index={2}>
          <Board
            title={page.infraBoardTitle}
            meta={page.resourcesMeta(resourceCount)}
            alt={infra.alt(
              architecture.infra.map((g) => ({ label: roleText[g.role].label, count: g.resources.length })),
            )}
          >
            <InfraBanks groups={architecture.infra} />
          </Board>
        </Section>

        <Section section={delivery} index={3}>
          <Board
            title={page.workflowTitle(ci.name)}
            meta={triggerLabel(ci.triggers, locale)}
            alt={delivery.alt(
              ci.jobs.filter((j) => j.layer === 0).map((j) => j.id),
              deploy?.needs ?? [],
            )}
          >
            <WorkflowGraph wf={ci} layerLabel={delivery.layerLabel} stepsLabel={delivery.stepsLabel} />
          </Board>
          <ul className="arch-side">
            {others.map((w) => (
              <li key={w.file} className="arch-side__item">
                <p className="arch-side__name">
                  {page.workflowTitle(w.name)} <span>{triggerLabel(w.triggers, locale)}</span>
                </p>
                <ul>
                  {w.jobs.map((j) => (
                    <li key={j.id}>
                      <strong>{j.id}</strong> — {jobText[j.id] ?? ""}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </Section>

        <Section section={lifecycle} index={4}>
          <Board
            title={page.modelsBoardTitle}
            meta={`ONNX ${model.version} · prompt ${model.promptVersion}`}
            alt={lifecycle.alt(model.version, model.promptVersion)}
          >
            <div className="arch-lifecycle">
              <div>
                <h3 className="arch-lane__title">{lifecycle.classifierTitle}</h3>
                <Flow
                  nodes={lifecycle.classifierSteps(model.version).map((s) => ({ ...s, key: s.ref }))}
                  label={lifecycle.classifierTitle}
                />
              </div>
              <div>
                <h3 className="arch-lane__title">{lifecycle.llmTitle}</h3>
                <Flow
                  nodes={lifecycle
                    .llmSteps(model.prompt.replace(/^prompts\//, ""), model.promptVersions.length)
                    .map((s) => ({ ...s, key: s.ref }))}
                  label={lifecycle.llmTitle}
                />
              </div>
            </div>
          </Board>
        </Section>

        <Glossary />
      </main>
    </div>
  );
}
