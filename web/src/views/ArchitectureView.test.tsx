import { render, screen, within } from "@/test/intl";

import { architecture, layers, sourceUrl } from "@/lib/architecture";
import { jobText, roleText, stageText } from "@/lib/architecture-content";
import { STAGES } from "@/lib/pipeline";

import { ArchitectureView as Architecture } from "./ArchitectureView";

describe("données d'architecture", () => {
  it("les étapes publiées sont celles du circuit de l'accueil, chacune décrite", () => {
    expect(architecture.pipeline.stages).toEqual([...STAGES]);
    for (const stage of architecture.pipeline.stages) expect(stageText[stage]).toBeDefined();
  });

  it("chaque rôle d'infrastructure et chaque job a un texte", () => {
    for (const group of architecture.infra) expect(roleText[group.role]).toBeDefined();
    for (const wf of architecture.workflows) for (const j of wf.jobs) expect(jobText[j.id]).toBeTruthy();
  });

  it("liens GitHub : chemins du dépôt seulement", () => {
    expect(sourceUrl("src/ask_my_cv/pipeline.py")).toBe(
      "https://github.com/VoiD911/ask-my-cv/blob/main/src/ask_my_cv/pipeline.py",
    );
    expect(sourceUrl(".github/workflows/ci.yml", 12)).toMatch(/ci\.yml#L12$/);
    for (const bad of ["../secret", "https://evil.test/x", "/abs", "a b"]) {
      expect(() => sourceUrl(bad)).toThrow();
    }
  });

  it("regroupe les jobs par rang", () => {
    const grouped = layers([
      { id: "a", needs: [], steps: [], layer: 0 },
      { id: "c", needs: ["a"], steps: [], layer: 1 },
      { id: "b", needs: [], steps: [], layer: 0 },
    ]);
    expect(grouped.map((l) => l.map((j) => j.id))).toEqual([["a", "b"], ["c"]]);
  });
});

describe("page Architecture", () => {
  it("titre, navigation courante et les quatre sections", () => {
    render(<Architecture />);
    expect(screen.getByRole("heading", { level: 1, name: "Architecture" })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Navigation principale" });
    expect(within(nav).getByRole("link", { name: "Architecture" })).toHaveAttribute("aria-current", "page");
    for (const name of [
      "Chemin d'une requête",
      "Infrastructure",
      "Du code à la production",
      "Cycle de vie du modèle",
    ]) {
      expect(screen.getByRole("heading", { level: 2, name })).toBeInTheDocument();
    }
  });

  it("le schéma de requête liste les étapes réelles dans l'ordre, avec une lecture textuelle", () => {
    render(<Architecture />);
    const list = screen.getByRole("list", { name: "Étapes du pipeline, dans l'ordre" });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(architecture.pipeline.stages.length);
    expect(items[0]).toHaveTextContent("U1");
    expect(items[0]).toHaveTextContent(stageText.reception!.label);
    expect(screen.getAllByText(/Lecture du schéma/)).toHaveLength(4);
    expect(screen.getByText(/400 caractères ou plus/)).toBeInTheDocument();
  });

  it("chaque ressource Terraform et chaque job CI apparaît", () => {
    const { container } = render(<Architecture />);
    const total = architecture.infra.reduce((n, g) => n + g.resources.length, 0);
    expect(container.querySelectorAll(".arch-res")).toHaveLength(total);
    const ci = architecture.workflows.find((w) => w.file.endsWith("ci.yml"))!;
    for (const j of ci.jobs) expect(container.querySelector(`[data-job="${j.id}"]`)).not.toBeNull();
  });

  it("sigles définis (SSE, OIDC, SLSA…) reliés au glossaire de la page", () => {
    render(<Architecture />);
    expect(screen.getByRole("heading", { level: 2, name: "Glossaire" })).toBeInTheDocument();
    for (const k of ["SSE", "OIDC", "SLSA", "SBOM", "PSI", "ONNX"]) {
      const link = screen.getAllByRole("link", { name: k })[0]!;
      expect(link.getAttribute("href")).toMatch(/^#glossaire-/);
      expect(document.querySelector(link.getAttribute("href")!)).not.toBeNull();
    }
    expect(screen.queryByText(/\[\[/)).toBeNull();
  });

  it("les liens de source pointent vers le dépôt public", () => {
    render(<Architecture />);
    const links = screen.getAllByRole("link").filter((a) => a.getAttribute("href")?.startsWith("https://"));
    expect(links.length).toBeGreaterThan(20);
    for (const a of links) {
      expect(a.getAttribute("href")).toMatch(/^https:\/\/github\.com\/VoiD911\/ask-my-cv\/blob\/main\//);
    }
  });
});
