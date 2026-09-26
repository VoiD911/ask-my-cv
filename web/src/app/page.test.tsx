import { render, screen } from "@testing-library/react";
import Home from "./page";

describe("page d'accueil", () => {
  it("affiche le titre principal", () => {
    render(<Home />);
    expect(screen.getByRole("heading", { level: 1, name: "Interroge mon CV" })).toBeInTheDocument();
  });
});
