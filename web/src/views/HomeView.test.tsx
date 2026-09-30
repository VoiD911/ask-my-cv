import { render, screen } from "@/test/intl";
import { HomeView as Home } from "./HomeView";

describe("page d'accueil", () => {
  it("affiche le nom, le titre du profil et le contact", () => {
    render(<Home />);
    expect(screen.getByRole("heading", { level: 1, name: "Steve Lang" })).toBeInTheDocument();
    expect(
      screen.getByText("Architecte principal — hyperautomatisation, IA générative et cloud"),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "job@stevelang.net" })).toHaveAttribute(
      "href",
      "mailto:job@stevelang.net",
    );
  });

  it("montre le circuit au repos et le relevé vide", () => {
    render(<Home />);
    expect(screen.getByRole("img", { name: /^Circuit du pipeline en 8 étapes/ })).toBeInTheDocument();
    expect(screen.getByText("En attente de la requête.")).toBeInTheDocument();
    expect(screen.getByTestId("demo-footer")).toHaveTextContent("—");
  });

  it("précise où les questions sont traitées et ce que les traces ne gardent pas", () => {
    render(<Home />);
    expect(screen.getByText(/traitées aux États-Unis par Amazon Bedrock/)).toBeInTheDocument();
    expect(screen.getByText(/ni le texte de ta question ni ton adresse IP/)).toBeInTheDocument();
  });
});
