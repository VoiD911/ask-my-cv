import { render, screen } from "@/test/intl";

import { Glossary, Rich } from "@/components/Glossary";

import { glossary, glossaryId, plain, splitTerms } from "./glossary";

describe("glossaire", () => {
  it("couvre les sigles demandés", () => {
    for (const k of ["SSE", "SLSA", "SBOM", "OIDC", "PSI", "ONNX", "cosign", "RAG", "LLM", "IaC", "CI/CD"]) {
      expect(glossary).toHaveProperty([k]);
    }
    expect(glossaryId("CI/CD")).toBe("glossaire-ci-cd");
  });

  it("découpe les marqueurs ; un sigle inconnu est refusé", () => {
    expect(splitTerms("a [[SSE]] b [[LLM]]")).toEqual(["a ", { term: "SSE" }, " b ", { term: "LLM" }]);
    expect(plain("flux [[SSE]].")).toBe("flux SSE.");
    expect(() => splitTerms("[[XYZ]]")).toThrow(/absent du glossaire/);
  });

  it("sigle : abréviation développée, lien vers la définition, infobulle annoncée", () => {
    render(
      <p>
        <Rich text="Réponse en flux ([[SSE]]) et encore [[SSE]]." />
      </p>,
    );
    const links = screen.getAllByRole("link", { name: "SSE" });
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveAttribute("href", "#glossaire-sse");
    expect(links[0]).toHaveAccessibleDescription(/Server-Sent Events/);
    // Identifiants d'infobulle distincts pour deux occurrences.
    expect(links[0]!.getAttribute("aria-describedby")).not.toBe(links[1]!.getAttribute("aria-describedby"));
    expect(screen.getAllByRole("tooltip", { hidden: true })).toHaveLength(2);
  });

  it("section Glossaire : une définition par sigle, ancres uniques", () => {
    const { container } = render(<Glossary />);
    expect(screen.getByRole("heading", { level: 2, name: "Glossaire" })).toBeInTheDocument();
    const entries = container.querySelectorAll(".glossary__entry");
    expect(entries).toHaveLength(Object.keys(glossary).length);
    const ids = [...entries].map((e) => e.id);
    expect(new Set(ids).size).toBe(ids.length);
  });
});
