import { render, screen, within } from "@/test/intl";

import { CvView } from "./CvView";

describe("page CV", () => {
  it("français : sections du CV, contact et PDF", () => {
    render(<CvView />);
    expect(screen.getByRole("heading", { level: 1, name: "Steve Lang" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Profil" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Expérience — NeoBotiQc (2025-2026)" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 2, name: "Contact" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "job@stevelang.net" })).toHaveAttribute("href", "mailto:job@stevelang.net");
    const linkedin = screen.getByRole("link", { name: "linkedin.com/in/steve-cl-lang" });
    expect(linkedin).toHaveAttribute("href", "https://www.linkedin.com/in/steve-cl-lang/");
    expect(linkedin).toHaveAttribute("rel", "me noopener");
    const pdf = screen.getByRole("link", { name: "Télécharger le CV (PDF)" });
    expect(pdf).toHaveAttribute("href", "/cv/Steve-Lang-CV-fr.pdf");
    expect(pdf).toHaveAttribute("download");
    const nav = screen.getByRole("navigation", { name: "Navigation principale" });
    expect(within(nav).getByRole("link", { name: "CV" })).toHaveAttribute("aria-current", "page");
  });

  it("anglais : texte traduit, PDF anglais, sélecteur vers /cv/", () => {
    render(<CvView />, { locale: "en" });
    expect(screen.getByRole("heading", { level: 2, name: "Profile" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Education" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download the resume (PDF)" })).toHaveAttribute(
      "href",
      "/en/cv/Steve-Lang-CV-en.pdf",
    );
    expect(screen.getByRole("link", { name: "Lire cette page en français" })).toHaveAttribute("href", "/cv/");
  });
});
