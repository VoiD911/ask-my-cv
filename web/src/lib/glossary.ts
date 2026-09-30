import type { Locale } from "@/i18n/locales";

/**
 * Glossaire des sigles, partagé par /architecture et /xops (français et anglais). Dans les textes de contenu, `[[CLÉ]]` insère le sigle avec sa définition.
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

type Entry = { expansion: string; definition: string };

/** Glossaire anglais : mêmes clés que le français (vérifié par le typage). */
export const glossaryEn: Record<GlossaryKey, Entry> = {
  "CI/CD": {
    expansion: "Continuous integration and delivery",
    definition: "Every change is tested automatically, then shipped to production by a pipeline.",
  },
  cosign: {
    expansion: "Sigstore signing tool",
    definition:
      "Signs a file or an image with no private key to safeguard: the GitHub workflow identity is the proof, recorded in a public log.",
  },
  IaC: {
    expansion: "Infrastructure as Code",
    definition: "Infrastructure is described in versioned files (Terraform here) rather than configured by hand.",
  },
  LLM: {
    expansion: "Large Language Model",
    definition: "The large language model that writes the answer (Claude on Amazon Bedrock here).",
  },
  OIDC: {
    expansion: "OpenID Connect",
    definition:
      "GitHub Actions proves its identity to AWS and receives temporary credentials: no long-lived access key is stored.",
  },
  ONNX: {
    expansion: "Open Neural Network Exchange",
    definition: "Open format for machine learning models, run here by the injection detector.",
  },
  PSI: {
    expansion: "Population Stability Index",
    definition: "Measures how far the distribution of production scores has moved from the reference (drift).",
  },
  RAG: {
    expansion: "Retrieval-Augmented Generation",
    definition: "The LLM answers from CV passages found by vector search, not from its own memory.",
  },
  SBOM: {
    expansion: "Software Bill of Materials",
    definition: "Inventory of every component in a software image (CycloneDX format here).",
  },
  SLSA: {
    expansion: "Supply-chain Levels for Software Artifacts",
    definition: "Provenance framework: a signed attestation states which workflow built the artifact, and from which commit.",
  },
  SSE: {
    expansion: "Server-Sent Events",
    definition: "HTTP stream through which the server sends the answer to the browser as it is produced.",
  },
};

export const glossaryText = {
  title: "Glossaire",
  intro: "Sigles utilisés sur cette page. Survoler ou cibler un sigle souligné en pointillé affiche aussi sa définition.",
};

const glossaryTextEn: typeof glossaryText = {
  title: "Glossary",
  intro: "Acronyms used on this page. Hovering over or focusing a dotted-underlined acronym also shows its definition.",
};

export function glossaryFor(locale: Locale): Record<GlossaryKey, Entry> {
  return locale === "en" ? glossaryEn : glossary;
}

export function glossaryTextFor(locale: Locale): typeof glossaryText {
  return locale === "en" ? glossaryTextEn : glossaryText;
}

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
