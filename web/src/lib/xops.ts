/**
 * Données de la page /xops : générées au build depuis les vraies sources du dépôt par
 * `scripts/sync-xops.mjs` (la CI refuse un JSON périmé). Toutes les URL externes sont
 * construites ici depuis ces données : aucune version, empreinte ni étiquette écrite en dur.
 */
import { sourceUrl } from "./architecture";
import data from "./xops.json";
import type { External, Proof } from "./xops-content";

export type Xops = {
  version: 1;
  repository: string;
  site: string;
  image: string;
  model: { version: string; tag: string; assets: string[] };
  signing: {
    issuer: string;
    modelIdentity: string;
    imageIdentity: string;
    signerWorkflow: string;
    sbomType: string;
    sbomPredicate: string;
  };
  prompts: { current: string; versions: string[] };
  production: {
    dailyCapUsd: number;
    perVisitorLimit: number;
    visitorWindowS: number;
    fallbackChain: string[];
    tracing: string[];
  };
  budget: { monthlyUsdDefault: number };
  dependabot: string[];
  paths: Record<string, "file" | "dir">;
  anchors: Record<string, { path: string; line: number }>;
};

const REPOSITORY = "VoiD911/ask-my-cv";

if (data.version !== 1 || data.repository !== REPOSITORY) {
  throw new Error("Données XOps non reconnues");
}

export const xops = data as Xops;

const GITHUB = `https://github.com/${xops.repository}`;

function segment(value: string): string {
  if (!/^[\w.@-]+$/.test(value)) throw new Error(`Segment d'URL inattendu : ${value}`);
  return value;
}

/** URL publique construite depuis les données du dépôt. */
export function externalUrl(kind: External, x: Xops = xops): string {
  const gh = `https://github.com/${x.repository}`;
  const asset = (name: string) => {
    if (!x.model.assets.includes(name)) throw new Error(`Fichier absent de la release : ${name}`);
    return `${gh}/releases/download/${segment(x.model.tag)}/${segment(name)}`;
  };
  switch (kind) {
    case "modelRelease":
      return `${gh}/releases/tag/${segment(x.model.tag)}`;
    case "modelCard":
      return asset("model_card.md");
    case "modelMetrics":
      return asset("metrics.json");
    case "releases":
      return `${gh}/releases`;
    case "ghcrPackage":
      return `${gh}/pkgs/container/${segment(x.image.split("/").pop() ?? "")}`;
    case "attestations":
      return `${gh}/attestations`;
    case "ciRuns":
      return `${gh}/actions/workflows/ci.yml`;
    case "nightlyRuns":
      return `${gh}/actions/workflows/nightly.yml`;
    case "trainRuns":
      return `${gh}/actions/workflows/train.yml`;
    case "rules":
      return `${gh}/rules`;
    case "dependabotPulls":
      return `${gh}/pulls?q=${encodeURIComponent("is:pr author:app/dependabot")}`;
    case "site":
      return `${x.site}/`;
  }
}

export function pullUrl(n: number): string {
  if (!Number.isInteger(n) || n <= 0) throw new Error(`Numéro de PR invalide : ${n}`);
  return `${GITHUB}/pull/${n}`;
}

/** Lien d'une preuve ; un chemin ou une ancre non vérifiés au build lèvent une erreur. */
export function proofHref(proof: Proof, x: Xops = xops): string {
  if ("path" in proof) {
    const kind = x.paths[proof.path];
    if (!kind) throw new Error(`Chemin non vérifié au build : ${proof.path}`);
    const url = sourceUrl(proof.path);
    return kind === "dir" ? url.replace("/blob/main/", "/tree/main/") : url;
  }
  if ("anchor" in proof) {
    const anchor = x.anchors[proof.anchor];
    if (!anchor) throw new Error(`Ancre non vérifiée au build : ${proof.anchor}`);
    return sourceUrl(anchor.path, anchor.line);
  }
  if ("external" in proof) return externalUrl(proof.external, x);
  if ("pull" in proof) return pullUrl(proof.pull);
  return proof.internal;
}

/** Ligne de la preuve (ancres seulement), pour l'afficher à côté du lien. */
export function proofLine(proof: Proof, x: Xops = xops): number | undefined {
  return "anchor" in proof ? x.anchors[proof.anchor]?.line : undefined;
}

export function isExternal(href: string): boolean {
  return /^https:\/\//.test(href);
}

/** Commandes de vérification du modèle promu (release signée par train.yml sur main). */
export function modelCommands(x: Xops = xops): string[] {
  const { tag } = x.model;
  return [
    `gh release download ${tag} -R ${x.repository} -p model.onnx -p model.onnx.sigstore.json`,
    [
      "cosign verify-blob model.onnx --bundle model.onnx.sigstore.json \\",
      `  --certificate-identity ${x.signing.modelIdentity} \\`,
      `  --certificate-oidc-issuer ${x.signing.issuer}`,
    ].join("\n"),
    `gh attestation verify model.onnx -R ${x.repository}`,
  ];
}

/** Commandes de vérification de l'image publique (signée par ci.yml sur main). */
export function imageCommands(x: Xops = xops): string[] {
  const strict = [
    `  --certificate-identity ${x.signing.imageIdentity} \\`,
    `  --certificate-oidc-issuer ${x.signing.issuer}`,
  ];
  return [
    `IMAGE=${x.image}:$(gh api repos/${x.repository}/commits/main -q .sha)`,
    ['cosign verify "$IMAGE" \\', ...strict].join("\n"),
    ['cosign verify-attestation "$IMAGE" --type slsaprovenance1 \\', ...strict].join("\n"),
    [`cosign verify-attestation "$IMAGE" --type ${x.signing.sbomType} \\`, ...strict].join("\n"),
    [
      `gh attestation verify "oci://$IMAGE" -R ${x.repository} \\`,
      `  --signer-workflow ${x.signing.signerWorkflow} \\`,
      `  --predicate-type ${x.signing.sbomPredicate}`,
    ].join("\n"),
  ];
}
