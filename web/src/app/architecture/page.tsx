import type { Metadata } from "next";
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
import {
  delivery,
  infra,
  jobText,
  lifecycle,
  page,
  request,
  roleText,
  stageText,
} from "@/lib/architecture-content";

export const metadata: Metadata = {
  title: page.title,
  description: page.description,
};

const { pipeline, model } = architecture;
const ci = workflow("ci.yml");
const others = architecture.workflows.filter((w) => w !== ci);
const resourceCount = architecture.infra.reduce((n, g) => n + g.resources.length, 0);
const jobCount = architecture.workflows.reduce((n, w) => n + w.jobs.length, 0);

const stageNodes: Node[] = pipeline.stages.map((name, i) => ({
  key: name,
  ref: `U${i + 1}`,
  label: stageText[name]?.label ?? name,
  detail: stageText[name]?.detail ?? "",
}));

const SECTIONS: SectionText[] = [request, infra, delivery, lifecycle];

type SectionText = { id: string; title: string; paragraphs: string[]; sources: { label: string; path: string }[] };

function Section({
  section,
  children,
}: {
  section: SectionText;
  children: ReactNode;
}) {
  const index = SECTIONS.indexOf(section) + 1;
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

export default function Architecture() {
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
          <div><dt>Étapes</dt><dd>{pipeline.stages.length}</dd></div>
          <div><dt>Ressources</dt><dd>{resourceCount}</dd></div>
          <div><dt>Jobs CI/CD</dt><dd>{jobCount}</dd></div>
        </dl>
      </header>

      <main className="delivery-main">
        <nav className="arch-toc" aria-label={page.tocLabel}>
          <ol>
            {SECTIONS.map((s, i) => (
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

        <Section section={request}>
          <Board
            title={request.boardTitle}
            meta={`${pipeline.stages.length} étapes · ONNX ${model.version}`}
            alt={request.alt(stageNodes.map((n) => n.label))}
          >
            <div className="arch-request">
              <Flow nodes={request.edgeIn} label="Aller : du navigateur à la Lambda" tone="idle" />
              <Flow nodes={stageNodes} label="Étapes du pipeline, dans l'ordre" />
              <Flow nodes={request.edgeOut} label="Retour : flux vers l'interface" tone="idle" />
            </div>
            <ul className="arch-notes">
              <li>{request.guardrailNote(pipeline.guardrailMinChars)}</li>
              <li>{request.modelNote(model.version)}</li>
            </ul>
          </Board>
        </Section>

        <Section section={infra}>
          <Board
            title="Terraform · infra/"
            meta={`${resourceCount} ressources`}
            alt={infra.alt(
              architecture.infra.map((g) => ({ label: roleText[g.role].label, count: g.resources.length })),
            )}
          >
            <InfraBanks groups={architecture.infra} />
          </Board>
        </Section>

        <Section section={delivery}>
          <Board
            title={`workflow ${ci.name}`}
            meta={triggerLabel(ci.triggers)}
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
                  workflow {w.name} <span>{triggerLabel(w.triggers)}</span>
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

        <Section section={lifecycle}>
          <Board
            title="Modèles"
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
