/**
 * Glossaire des sigles, partagé par /architecture et /xops (français d'abord, prêt pour
 * next-intl). Dans les textes de contenu, `[[CLÉ]]` insère le sigle avec sa définition.
 */
export const glossary = {
  "CI/CD": {
    expansion: "Intégration et déploiement continus",
    definition: "Chaque modification est testée automatiquement, puis mise en production par un pipeline.",
  },
  cosign: {
    expansion: "Outil de signature Sigstore",
    definition:
      "Signe un fichier ou une image sans clé privée à garder : l'identité du workflow GitHub fait foi, inscrite dans un journal public.",
  },
  IaC: {
    expansion: "Infrastructure as Code",
    definition: "L'infrastructure est décrite dans des fichiers versionnés (ici Terraform) plutôt que configurée à la main.",
  },
  LLM: {
    expansion: "Large Language Model",
    definition: "Grand modèle de langage qui rédige la réponse (ici Claude sur Amazon Bedrock).",
  },
  OIDC: {
    expansion: "OpenID Connect",
    definition:
      "GitHub Actions prouve son identité à AWS et reçoit des identifiants temporaires : aucune clé d'accès permanente n'est stockée.",
  },
  ONNX: {
    expansion: "Open Neural Network Exchange",
    definition: "Format ouvert de modèle d'apprentissage automatique, exécuté ici par le détecteur d'injection.",
  },
  PSI: {
    expansion: "Population Stability Index",
    definition: "Indice qui mesure l'écart entre la distribution des scores en production et celle de référence (dérive).",
  },
  RAG: {
    expansion: "Retrieval-Augmented Generation",
    definition: "Le LLM répond à partir de passages du CV retrouvés par recherche vectorielle, pas de sa mémoire.",
  },
  SBOM: {
    expansion: "Software Bill of Materials",
    definition: "Inventaire de tous les composants d'une image logicielle (ici au format CycloneDX).",
  },
  SLSA: {
    expansion: "Supply-chain Levels for Software Artifacts",
    definition: "Cadre de provenance : une attestation signée indique quel workflow a construit l'artefact, depuis quel commit.",
  },
  SSE: {
    expansion: "Server-Sent Events",
    definition: "Flux HTTP par lequel le serveur envoie la réponse au navigateur au fil de l'eau.",
  },
} as const satisfies Record<string, { expansion: string; definition: string }>;

export type GlossaryKey = keyof typeof glossary;

export const glossaryText = {
  title: "Glossaire",
  intro: "Sigles utilisés sur cette page. Survoler ou cibler un sigle souligné en pointillé affiche aussi sa définition.",
};

export function isGlossaryKey(key: string): key is GlossaryKey {
  return Object.hasOwn(glossary, key);
}

/** Ancre de la définition dans la section Glossaire de la page. */
export function glossaryId(key: GlossaryKey): string {
  return `glossaire-${key.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
}

/** Découpe « texte [[SLSA]] texte » ; une clé inconnue fait échouer le rendu (et le build). */
export function splitTerms(text: string): (string | { term: GlossaryKey })[] {
  const out: (string | { term: GlossaryKey })[] = [];
  let last = 0;
  for (const m of text.matchAll(/\[\[([^\]]+)\]\]/g)) {
    const key = m[1]!;
    if (!isGlossaryKey(key)) throw new Error(`Sigle absent du glossaire : ${key}`);
    if (m.index > last) out.push(text.slice(last, m.index));
    out.push({ term: key });
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

/** Texte sans marqueurs (métadonnées, lectures textuelles). */
export function plain(text: string): string {
  return splitTerms(text)
    .map((part) => (typeof part === "string" ? part : part.term))
    .join("");
}
