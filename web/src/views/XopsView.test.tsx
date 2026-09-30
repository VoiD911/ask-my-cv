import { render, screen, within } from "@testing-library/react";

import { externalUrl, imageCommands, modelCommands, proofHref, pullUrl, xops, type Xops } from "@/lib/xops";
import { disciplines, type External } from "@/lib/xops-content";

import XOps from "./page";

const GH = "https://github.com/VoiD911/ask-my-cv";

describe("données XOps", () => {
  it("cinq disciplines, 4 à 6 pratiques chacune, chaque pratique a au moins une preuve", () => {
    expect(disciplines.map((d) => d.name)).toEqual(["DevOps", "DevSecOps", "MLOps", "LLMOps", "FinOps"]);
    for (const d of disciplines) {
      expect(d.practices.length).toBeGreaterThanOrEqual(4);
      expect(d.practices.length).toBeLessThanOrEqual(6);
      for (const p of d.practices) {
        expect(p.proofs.length, p.id).toBeGreaterThan(0);
        // Une case partielle dit ce qui manque ; une case couverte n'a pas de réserve.
        expect(Boolean(p.gap), p.id).toBe(p.status === "partiel");
      }
    }
  });

  it("les cases partielles connues le disent", () => {
    const status = Object.fromEntries(disciplines.flatMap((d) => d.practices.map((p) => [p.id, p.status])));
    expect(status.derive).toBe("partiel");
    expect(status.deploiement).toBe("partiel");
  });

  it("chaque preuve se résout en lien vérifié au build", () => {
    for (const d of disciplines) {
      for (const p of d.practices) {
        for (const proof of p.proofs) {
          const href = proofHref(proof);
          expect(href, proof.label).toMatch(
            /^(https:\/\/github\.com\/VoiD911\/ask-my-cv\/|https:\/\/job\.stevelang\.net\/|\/[a-z]+\/$|#[a-z-]+$)/,
          );
        }
      }
    }
  });

  it("un chemin ou une ancre absents des données du build lèvent une erreur", () => {
    expect(() => proofHref({ label: "x", path: "src/absent.py" })).toThrow(/non vérifié/);
    expect(() => proofHref({ label: "x", anchor: "job:ci.yml:absent" })).toThrow(/non vérifiée/);
  });

  it("dossiers en /tree/, fichiers en /blob/, ancres avec ligne", () => {
    expect(proofHref({ label: "x", path: "prompts" })).toBe(`${GH}/tree/main/prompts`);
    expect(proofHref({ label: "x", path: "ml/drift.py" })).toBe(`${GH}/blob/main/ml/drift.py`);
    expect(proofHref({ label: "x", anchor: "job:ci.yml:deploy" })).toMatch(
      new RegExp(`^${GH}/blob/main/\\.github/workflows/ci\\.yml#L\\d+$`),
    );
    expect(pullUrl(125)).toBe(`${GH}/pull/125`);
    expect(() => pullUrl(0)).toThrow();
  });
});

describe("URL construites depuis les données du dépôt", () => {
  const sample: Xops = {
    ...xops,
    repository: "acme/demo",
    site: "https://demo.test",
    image: "ghcr.io/acme/demo",
    model: { version: "v9.8.7", tag: "model-v9.8.7", assets: ["model.onnx", "model_card.md", "metrics.json"] },
  };

  it.each<[External, string]>([
    ["modelRelease", "https://github.com/acme/demo/releases/tag/model-v9.8.7"],
    ["modelCard", "https://github.com/acme/demo/releases/download/model-v9.8.7/model_card.md"],
    ["modelMetrics", "https://github.com/acme/demo/releases/download/model-v9.8.7/metrics.json"],
    ["releases", "https://github.com/acme/demo/releases"],
    ["ghcrPackage", "https://github.com/acme/demo/pkgs/container/demo"],
    ["attestations", "https://github.com/acme/demo/attestations"],
    ["ciRuns", "https://github.com/acme/demo/actions/workflows/ci.yml"],
    ["nightlyRuns", "https://github.com/acme/demo/actions/workflows/nightly.yml"],
    ["trainRuns", "https://github.com/acme/demo/actions/workflows/train.yml"],
    ["rules", "https://github.com/acme/demo/rules"],
    ["dependabotPulls", "https://github.com/acme/demo/pulls?q=is%3Apr%20author%3Aapp%2Fdependabot"],
    ["site", "https://demo.test/"],
  ])("%s", (kind, url) => {
    expect(externalUrl(kind, sample)).toBe(url);
  });

  it("fichier absent de la release ou tag inattendu : erreur", () => {
    expect(() => externalUrl("modelCard", { ...sample, model: { ...sample.model, assets: [] } })).toThrow();
    expect(() => externalUrl("modelRelease", { ...sample, model: { ...sample.model, tag: "../x" } })).toThrow();
  });

  it("données réelles : release du modèle promu", () => {
    expect(externalUrl("modelRelease")).toBe(`${GH}/releases/tag/${xops.model.tag}`);
    expect(xops.model.tag).toBe(`model-${xops.model.version}`);
  });
});

describe("commandes de vérification", () => {
  it("modèle : release promue, identité train.yml@main, émetteur GitHub", () => {
    const text = modelCommands().join("\n");
    expect(text).toContain(`gh release download ${xops.model.tag} -R VoiD911/ask-my-cv`);
    expect(text).toContain("cosign verify-blob model.onnx --bundle model.onnx.sigstore.json");
    expect(text).toContain(
      "--certificate-identity https://github.com/VoiD911/ask-my-cv/.github/workflows/train.yml@refs/heads/main",
    );
    expect(text).toContain("--certificate-oidc-issuer https://token.actions.githubusercontent.com");
    expect(text).toContain("gh attestation verify model.onnx -R VoiD911/ask-my-cv");
  });

  it("image : GHCR, identité ci.yml@main, provenance SLSA et SBOM", () => {
    const text = imageCommands().join("\n");
    expect(text).toContain("IMAGE=ghcr.io/void911/ask-my-cv:$(gh api repos/VoiD911/ask-my-cv/commits/main -q .sha)");
    expect(text).toContain('cosign verify "$IMAGE"');
    expect(text).toContain("--type slsaprovenance1");
    expect(text).toContain("--type cyclonedx");
    expect(text).toContain(
      "--certificate-identity https://github.com/VoiD911/ask-my-cv/.github/workflows/ci.yml@refs/heads/main",
    );
    expect(text).toContain("--signer-workflow VoiD911/ask-my-cv/.github/workflows/ci.yml");
    expect(text).toContain("--predicate-type https://cyclonedx.org/bom");
  });

  it("aucun numéro de compte AWS", () => {
    expect([...modelCommands(), ...imageCommands()].join("\n")).not.toMatch(/\b\d{12}\b/);
  });
});

describe("page XOps", () => {
  it("titre, onglet courant, une section par discipline, vérification et glossaire", () => {
    render(<XOps />);
    expect(screen.getByRole("heading", { level: 1, name: "XOps" })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Navigation principale" });
    expect(within(nav).getByRole("link", { name: "XOps" })).toHaveAttribute("aria-current", "page");
    for (const name of ["DevOps", "DevSecOps", "MLOps", "LLMOps", "FinOps", "Vérifier soi-même", "Glossaire"]) {
      expect(screen.getByRole("heading", { level: 2, name })).toBeInTheDocument();
    }
  });

  it("matrice : une ligne par discipline, statut en texte", () => {
    render(<XOps />);
    const table = screen.getByRole("table", { name: "Pratiques par discipline, avec leur statut" });
    expect(within(table).getAllByRole("row")).toHaveLength(disciplines.length + 1);
    const total = disciplines.reduce((n, d) => n + d.practices.length, 0);
    expect(screen.getAllByText(/^(Couvert|Partiel)$/)).toHaveLength(total);
    expect(screen.getAllByText("Partiel").length).toBeGreaterThanOrEqual(2);
  });

  it("commandes copiables présentes, sans numéro de compte", () => {
    const { container } = render(<XOps />);
    const code = [...container.querySelectorAll(".xops-cmd code")].map((c) => c.textContent).join("\n");
    expect(code).toContain("cosign verify-blob");
    expect(code).toContain("gh attestation verify");
    expect(container.innerHTML).not.toMatch(/\b\d{12}\b/);
  });

  it("sigles définis dans le texte, reliés au glossaire", () => {
    render(<XOps />);
    const slsa = screen.getAllByRole("link", { name: "SLSA" })[0]!;
    expect(slsa).toHaveAttribute("href", "#glossaire-slsa");
    expect(slsa).toHaveAccessibleDescription(/Supply-chain Levels for Software Artifacts/);
  });
});
