/**
 * Schémas de la page /architecture : composants serveur, sans JavaScript côté client.
 * Même langage visuel que le circuit de l'accueil (carte, puces, pistes cuivre, impulsion
 * cyan) mais en listes HTML : lisibles au clavier et au lecteur d'écran, empilées sur mobile.
 */
import type { ReactNode } from "react";

import { layers as byLayer, shortType, sourceUrl, type InfraRole, type InfraResource, type Workflow } from "@/lib/architecture";
import { jobText, page, roleText, triggerText, type SourceLink } from "@/lib/architecture-content";

export type Node = { ref: string; label: string; detail: string; key?: string };

/** Cadre de carte électronique : barre de titre + contenu + lecture textuelle. */
export function Board({
  title,
  meta,
  alt,
  children,
}: {
  title: string;
  meta?: string;
  alt: string;
  children: ReactNode;
}) {
  return (
    <figure className="circuit arch-board">
      <div className="circuit__bar">
        <span className="circuit__title">{title}</span>
        {meta ? <span className="circuit__metrics">{meta}</span> : null}
      </div>
      {children}
      <figcaption className="arch-board__alt">
        <span>{page.readingLabel} :</span> {alt}
      </figcaption>
    </figure>
  );
}

function Chip({ node, tone = "ok" }: { node: Node; tone?: "ok" | "active" | "idle" }) {
  return (
    <div className="chip arch-chip" data-status={tone} data-node={node.key}>
      <div className="chip__head">
        <span className="chip__ref">{node.ref}</span>
      </div>
      <span className="chip__label">{node.label}</span>
      <span className="chip__id">{node.detail}</span>
    </div>
  );
}

/** Suite ordonnée de puces reliées par une piste (impulsion animée hors mouvement réduit). */
export function Flow({ nodes, label, tone }: { nodes: Node[]; label: string; tone?: "ok" | "active" | "idle" }) {
  return (
    <ol className="arch-flow" aria-label={label}>
      {nodes.map((node) => (
        <li key={node.key ?? node.ref} className="arch-flow__item">
          <Chip node={node} tone={tone} />
        </li>
      ))}
    </ol>
  );
}

export function InfraBanks({ groups }: { groups: { role: InfraRole; resources: InfraResource[] }[] }) {
  return (
    <ul className="arch-banks">
      {groups.map((group) => {
        const text = roleText[group.role];
        const headingId = `infra-${group.role}`;
        return (
          <li key={group.role} className="arch-bank" data-role={group.role}>
            <h3 id={headingId} className="arch-bank__title">
              {text.label} <span>{group.resources.length}</span>
            </h3>
            <p className="arch-bank__detail">{text.detail}</p>
            <ul className="arch-bank__list" aria-labelledby={headingId}>
              {group.resources.map((r) => (
                <li key={`${r.type}.${r.name}`}>
                  <a href={sourceUrl(r.file)} className="arch-res">
                    <span className="arch-res__type">{shortType(r.type)}</span>
                    <span className="arch-res__name">{r.name}</span>
                  </a>
                </li>
              ))}
            </ul>
          </li>
        );
      })}
    </ul>
  );
}

/** Jobs d'un workflow par rang dans le graphe des `needs`, étapes dépliables. */
export function WorkflowGraph({ wf, layerLabel, stepsLabel }: {
  wf: Workflow;
  layerLabel: (n: number) => string;
  stepsLabel: (id: string) => string;
}) {
  return (
    <ol className="arch-layers">
      {byLayer(wf.jobs).map((jobs, index) => (
        <li key={index} className="arch-layer">
          <p className="arch-layer__label">{layerLabel(index)}</p>
          <ul className="arch-jobs">
            {jobs.map((j) => (
              <li key={j.id} className="chip arch-job" data-status={index === 0 ? "ok" : "active"} data-job={j.id}>
                <div className="chip__head">
                  <span className="chip__ref">{j.needs.length ? `needs · ${j.needs.length}` : "job"}</span>
                </div>
                <span className="chip__label">{j.id}</span>
                <span className="chip__id">{jobText[j.id] ?? ""}</span>
                {j.steps.length ? (
                  <details className="arch-steps">
                    <summary>
                      {j.steps.length} étapes<span className="sr-only"> — {stepsLabel(j.id)}</span>
                    </summary>
                    <ol>
                      {j.steps.map((s, i) => (
                        <li key={`${i}-${s}`}>{s}</li>
                      ))}
                    </ol>
                  </details>
                ) : null}
              </li>
            ))}
          </ul>
        </li>
      ))}
    </ol>
  );
}

export function triggerLabel(triggers: string[]): string {
  return triggers.map((t) => triggerText[t] ?? t).join(" · ");
}

export function Sources({ links }: { links: SourceLink[] }) {
  return (
    <div className="arch-sources">
      <h3 className="arch-sources__title">{page.sourcesLabel}</h3>
      <ul>
        {links.map((l) => (
          <li key={l.path}>
            <a href={sourceUrl(l.path)}>
              {l.label}
              <span aria-hidden="true"> ↗</span>
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
