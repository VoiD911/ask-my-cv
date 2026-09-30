import type { Metadata } from "next";
import Link from "next/link";

import { Board } from "@/components/ArchitectureDiagrams";
import { Glossary, Rich } from "@/components/Glossary";
import { SiteNav } from "@/components/SiteNav";
import { imageCommands, isExternal, modelCommands, proofHref, proofLine, xops } from "@/lib/xops";
import { disciplines, page, verify, type Practice, type Proof } from "@/lib/xops-content";

export const metadata: Metadata = {
  title: page.title,
  description: page.description,
};

const practiceCount = disciplines.reduce((n, d) => n + d.practices.length, 0);
const proofCount = disciplines.reduce((n, d) => n + d.practices.reduce((m, p) => m + p.proofs.length, 0), 0);

function ProofLink({ proof }: { proof: Proof }) {
  const href = proofHref(proof);
  const line = proofLine(proof);
  const content = (
    <>
      {proof.label}
      {line ? <span className="xops-proof__line"> · {page.lineLabel(line)}</span> : null}
      {isExternal(href) ? <span aria-hidden="true"> ↗</span> : null}
    </>
  );
  // Liens internes à la page (#…) : ancre simple ; autres onglets : navigation Next.
  if (isExternal(href) || href.startsWith("#")) return <a href={href}>{content}</a>;
  return <Link href={href}>{content}</Link>;
}

function PracticeCard({ practice, discipline }: { practice: Practice; discipline: string }) {
  const tone = practice.status === "couvert" ? "ok" : "fallback";
  const headingId = `${discipline}-${practice.id}`;
  return (
    <li className="chip xops-cell" data-status={tone} data-practice={practice.id}>
      <div className="chip__head">
        <span className="xops-status" data-status={practice.status}>
          {page.statusText[practice.status]}
        </span>
      </div>
      <h3 id={headingId} className="chip__label">
        {practice.title}
      </h3>
      <p className="xops-cell__claim">
        <Rich text={practice.claim(xops)} />
      </p>
      {practice.gap ? (
        <p className="xops-cell__gap">
          <strong>{page.gapLabel} :</strong> {practice.gap(xops)}
        </p>
      ) : null}
      <div className="xops-proofs">
        <p className="xops-proofs__title">{page.proofsLabel}</p>
        <ul>
          {practice.proofs.map((proof) => (
            <li key={proof.label}>
              <ProofLink proof={proof} />
            </li>
          ))}
        </ul>
      </div>
    </li>
  );
}

function Commands({ id, title, detail, commands }: { id: string; title: string; detail: string; commands: string[] }) {
  return (
    <section className="xops-verify" aria-labelledby={`${id}-titre`} id={id}>
      <h3 id={`${id}-titre`}>{title}</h3>
      <p>{detail}</p>
      <pre className="xops-cmd" role="region" aria-label={`${verify.commandLabel} : ${title}`} tabIndex={0}>
        <code>{commands.join("\n\n")}</code>
      </pre>
    </section>
  );
}

export default function XOps() {
  const covered = disciplines.reduce((n, d) => n + d.practices.filter((p) => p.status === "couvert").length, 0);
  return (
    <div className="page delivery-page arch-page xops-page">
      <SiteNav current="/xops/" />
      <header className="titleblock delivery-hero">
        <div>
          <p className="titleblock__eyebrow">{page.eyebrow}</p>
          <h1 className="titleblock__name">{page.heading}</h1>
          <p className="titleblock__role">{page.lede}</p>
        </div>
        <dl className="delivery-stats">
          <div><dt>{page.statsLabels.disciplines}</dt><dd>{disciplines.length}</dd></div>
          <div><dt>{page.statsLabels.practices}</dt><dd>{practiceCount}</dd></div>
          <div><dt>{page.statsLabels.proofs}</dt><dd>{proofCount}</dd></div>
        </dl>
      </header>

      <main className="delivery-main">
        <nav className="arch-toc" aria-label={page.tocLabel}>
          <ol>
            {disciplines.map((d, i) => (
              <li key={d.id}>
                <a href={`#${d.id}`}>
                  <span>{String(i + 1).padStart(2, "0")}</span>
                  {d.name}
                </a>
              </li>
            ))}
            <li>
              <a href={`#${verify.model.id}`}>
                <span>{String(disciplines.length + 1).padStart(2, "0")}</span>
                {verify.title}
              </a>
            </li>
          </ol>
          <p>{page.generated}</p>
        </nav>

        <section className="arch-section" aria-labelledby="vue-ensemble-titre">
          <h2 id="vue-ensemble-titre" className="sr-only">
            {page.matrixTitle}
          </h2>
          <Board
            title={page.matrixTitle}
            meta={`${covered}/${practiceCount} ${page.statusText.couvert.toLowerCase()}s`}
            alt={disciplines
              .map((d) => `${d.name} : ${d.practices.map((p) => `${p.title} (${page.statusText[p.status].toLowerCase()})`).join(", ")}`)
              .join(". ")}
          >
            <div className="xops-matrix-wrap">
              <table className="xops-matrix">
                <caption className="sr-only">{page.matrixCaption}</caption>
                <thead>
                  <tr>
                    <th scope="col">{page.matrixCols.discipline}</th>
                    <th scope="col">{page.matrixCols.practices}</th>
                    <th scope="col">{page.matrixCols.covered}</th>
                    <th scope="col">{page.matrixCols.partial}</th>
                  </tr>
                </thead>
                <tbody>
                  {disciplines.map((d) => (
                    <tr key={d.id}>
                      <th scope="row">
                        <a href={`#${d.id}`}>{d.name}</a>
                      </th>
                      <td>
                        <ul className="xops-matrix__practices">
                          {d.practices.map((p) => (
                            <li key={p.id} data-status={p.status}>
                              <a href={`#${d.id}-${p.id}`}>{p.title}</a>
                              {p.status === "partiel" ? (
                                <span className="xops-matrix__flag"> ({page.statusText.partiel.toLowerCase()})</span>
                              ) : null}
                            </li>
                          ))}
                        </ul>
                      </td>
                      <td>{d.practices.filter((p) => p.status === "couvert").length}</td>
                      <td>{d.practices.filter((p) => p.status === "partiel").length}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Board>
        </section>

        {disciplines.map((d, i) => (
          <section key={d.id} className="arch-section" aria-labelledby={`${d.id}-titre`} id={d.id}>
            <div className="arch-section__text">
              <p className="titleblock__eyebrow">{String(i + 1).padStart(2, "0")}</p>
              <h2 id={`${d.id}-titre`}>{d.name}</h2>
              <p>
                <Rich text={d.summary} />
              </p>
            </div>
            <ul className="xops-grid" aria-label={`Pratiques ${d.name}`}>
              {d.practices.map((p) => (
                <PracticeCard key={p.id} practice={p} discipline={d.id} />
              ))}
            </ul>
          </section>
        ))}

        <section className="arch-section" aria-labelledby="verifier-titre">
          <div className="arch-section__text">
            <p className="titleblock__eyebrow">{String(disciplines.length + 1).padStart(2, "0")}</p>
            <h2 id="verifier-titre">{verify.title}</h2>
            <p>{verify.intro}</p>
          </div>
          <div className="xops-verify-grid">
            <Commands
              id={verify.model.id}
              title={verify.model.title(xops.model.tag)}
              detail={verify.model.detail}
              commands={modelCommands()}
            />
            <Commands id={verify.image.id} title={verify.image.title} detail={verify.image.detail} commands={imageCommands()} />
          </div>
        </section>

        <Glossary />
      </main>
    </div>
  );
}
