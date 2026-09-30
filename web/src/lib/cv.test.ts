import { CV_PDF, cvFor } from "./cv";

describe("données du CV (FR/EN)", () => {
  const fr = cvFor("fr");
  const en = cvFor("en");

  it("mêmes sections, dans le même ordre, dans les deux langues", () => {
    expect(fr.sections.length).toBeGreaterThanOrEqual(10);
    expect(en.sections.map((s) => s.id)).toEqual(fr.sections.map((s) => s.id));
    fr.sections.forEach((s, i) => {
      expect(en.sections[i]?.paragraphs.length).toBe(s.paragraphs.length);
    });
  });

  it("commence par le profil et omet la section Contact (affichée à part)", () => {
    expect(fr.name).toBe("Steve Lang");
    expect(en.name).toBe("Steve Lang");
    expect(fr.sections[0]?.title).toBe("Profil");
    expect(en.sections[0]?.title).toBe("Profile");
    expect(fr.sections.some((s) => s.id === "contact")).toBe(false);
  });

  it("mêmes années citées de part et d'autre (aucun fait ajouté ni retiré)", () => {
    const years = (text: string) => [...text.matchAll(/\b(19|20)\d{2}\b/g)].map((m) => m[0]);
    fr.sections.forEach((s, i) => {
      expect(years(en.sections[i]!.paragraphs.join(" "))).toEqual(years(s.paragraphs.join(" ")));
    });
  });

  it("PDF : un fichier par langue, à côté de la page", () => {
    expect(CV_PDF.fr).toMatch(/^\/cv\/.+-fr\.pdf$/);
    expect(CV_PDF.en).toMatch(/^\/en\/cv\/.+-en\.pdf$/);
  });
});
