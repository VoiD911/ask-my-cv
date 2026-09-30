import { architecture } from "./architecture";
import { fr } from "./architecture-content";
import { en } from "./architecture-content.en";
import { glossary, glossaryEn, splitTerms } from "./glossary";
import { xops } from "./xops";
import { disciplines } from "./xops-content";
import { disciplinesEn, localizedDisciplines } from "./xops-content.en";

/** Structure (clés, longueurs de tableaux, types) d'une valeur, sans le texte. */
function shape(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(shape);
  if (typeof value === "function") return "function";
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([k, v]) => [k, shape(v)]));
  }
  return typeof value;
}

/** Sigles `[[CLÉ]]` d'un texte, dans l'ordre. */
const terms = (text: string) => splitTerms(text).flatMap((p) => (typeof p === "string" ? [] : [p.term]));

describe("contenu anglais de /architecture", () => {
  it("même structure que le français", () => {
    expect(shape(en)).toEqual(shape(fr));
  });

  it("mêmes sources (chemins) et mêmes ancres que le français", () => {
    for (const key of ["request", "infra", "delivery", "lifecycle"] as const) {
      expect(en[key].id).toBe(fr[key].id);
      expect(en[key].sources.map((s) => s.path)).toEqual(fr[key].sources.map((s) => s.path));
      expect(en[key].paragraphs.flatMap(terms)).toEqual(fr[key].paragraphs.flatMap(terms));
    }
  });

  it("chaque étape, rôle et job publiés a un texte anglais", () => {
    for (const stage of architecture.pipeline.stages) expect(en.stageText[stage]?.label).toBeTruthy();
    for (const group of architecture.infra) expect(en.roleText[group.role].label).toBeTruthy();
    for (const wf of architecture.workflows) for (const j of wf.jobs) expect(en.jobText[j.id]).toBeTruthy();
  });
});

describe("contenu anglais de /xops", () => {
  it("chaque discipline et chaque pratique a sa traduction, sans surplus", () => {
    expect(Object.keys(disciplinesEn).sort()).toEqual(disciplines.map((d) => d.id).sort());
    for (const d of disciplines) {
      expect(Object.keys(disciplinesEn[d.id]?.practices ?? {}).sort(), d.id).toEqual(d.practices.map((p) => p.id).sort());
    }
  });

  it("les preuves restent identiques, seuls les libellés changent", () => {
    const local = localizedDisciplines("en");
    local.forEach((d, i) => {
      const source = disciplines[i]!;
      d.practices.forEach((p, j) => {
        const original = source.practices[j]!;
        expect(p.status).toBe(original.status);
        const target = (proof: object) => JSON.stringify(Object.entries(proof).filter(([k]) => k !== "label"));
        expect(p.proofs.map(target)).toEqual(original.proofs.map(target));
        expect(terms(p.claim(xops))).toEqual(terms(original.claim(xops)));
        expect(p.claim(xops)).not.toBe(original.claim(xops));
      });
    });
    expect(localizedDisciplines("fr")).toBe(disciplines);
  });
});

describe("glossaire anglais", () => {
  it("mêmes sigles que le français", () => {
    expect(Object.keys(glossaryEn).sort()).toEqual(Object.keys(glossary).sort());
  });
});
