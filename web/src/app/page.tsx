import { Demo } from "@/components/Demo";

const CONTACT = "job@stevelang.net";

export default function Home() {
  return (
    <div className="page">
      <header className="titleblock">
        <div className="titleblock__main">
          <p className="titleblock__eyebrow">Interroge mon CV · démo en direct</p>
          <h1 className="titleblock__name">Steve Lang</h1>
          <p className="titleblock__role">
            Architecte principal — hyperautomatisation, IA générative et cloud
          </p>
        </div>
        <dl className="titleblock__fields">
          <div>
            <dt>source</dt>
            <dd>CV public, en français</dd>
          </div>
          <div>
            <dt>modèle</dt>
            <dd>Claude Haiku 4.5 · Amazon Bedrock</dd>
          </div>
          <div>
            <dt>contact</dt>
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
        <p>
          Les questions sont traitées aux États-Unis par Amazon Bedrock. Les traces ne conservent
          ni le texte de ta question ni ton adresse IP ; le quota par visiteur repose sur un
          pseudonyme salé.
        </p>
      </footer>
    </div>
  );
}
