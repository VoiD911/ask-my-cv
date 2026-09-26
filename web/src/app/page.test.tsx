import { render, screen } from "@testing-library/react";
import Home from "./page";

describe("page d'accueil", () => {
  it("affiche le titre principal", () => {
    render(<Home />);
    expect(screen.getByRole("heading", { level: 1, name: "Interroge mon CV" })).toBeInTheDocument();
  });

  it("montre le circuit au repos", () => {
    render(<Home />);
    expect(screen.getByRole("img", { name: /^Circuit du pipeline en 8 étapes/ })).toBeInTheDocument();
    expect(screen.getByText("En attente de la requête.")).toBeInTheDocument();
  });
});
