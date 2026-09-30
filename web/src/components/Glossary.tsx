/**
 * Sigles avec définition : composants serveur, sans JavaScript. Chaque sigle est un lien vers
 * sa définition dans la section Glossaire de la page ; la définition s'affiche aussi en
 * infobulle au survol et au focus clavier, et est annoncée par `aria-describedby`.
 */
import { useLocale } from "next-intl";
import { useId } from "react";

import { glossary, glossaryFor, glossaryId, glossaryTextFor, splitTerms, type GlossaryKey } from "@/lib/glossary";

export function Term({ k }: { k: GlossaryKey }) {
  const tipId = useId();
  const locale = useLocale();
  const entry = glossaryFor(locale)[k];
  return (
    <span className="term">
      <a href={`#${glossaryId(k)}`} className="term__link" aria-describedby={tipId}>
        <abbr title={entry.expansion}>{k}</abbr>
      </a>
      <span role="tooltip" id={tipId} className="term__tip">
        {entry.expansion}
        {locale === "fr" ? " : " : ": "}
        {entry.definition}
      </span>
    </span>
  );
}

/** Texte de contenu avec marqueurs `[[CLÉ]]` remplacés par des sigles définis. */
export function Rich({ text }: { text: string }) {
  return (
    <>
      {splitTerms(text).map((part, i) =>
        typeof part === "string" ? part : <Term key={`${i}-${part.term}`} k={part.term} />,
      )}
    </>
  );
}

export function Glossary({ keys }: { keys?: GlossaryKey[] }) {
  const locale = useLocale();
  const entriesText = glossaryFor(locale);
  const text = glossaryTextFor(locale);
  const entries = (keys ?? (Object.keys(glossary) as GlossaryKey[]))
    .slice()
    .sort((a, b) => a.localeCompare(b, locale, { sensitivity: "base" }));
  return (
    <section className="glossary" aria-labelledby="glossaire-titre" id="glossaire">
      <h2 id="glossaire-titre">{text.title}</h2>
      <p>{text.intro}</p>
      <dl>
        {entries.map((k) => (
          <div key={k} id={glossaryId(k)} className="glossary__entry">
            <dt>
              <abbr title={entriesText[k].expansion}>{k}</abbr> <span>{entriesText[k].expansion}</span>
            </dt>
            <dd>{entriesText[k].definition}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
