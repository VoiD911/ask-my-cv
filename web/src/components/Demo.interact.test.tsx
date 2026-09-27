import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe as suite, expect, it, vi } from "vitest";

import { SUGGESTIONS } from "./Chat";
import { Demo } from "./Demo";

suite("Demo — chargement différé de /api/models", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("n'appelle /api/models qu'à la première interaction avec la saisie", async () => {
    const payload = { default: "a", models: [{ id: "a", provider: "p" }, { id: "b", provider: "p" }] };
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(payload), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    render(<Demo />);

    // Rien tant que le visiteur n'a pas touché la saisie (page inerte au chargement : voir #6).
    expect(fetchMock).not.toHaveBeenCalled();

    const input = screen.getByLabelText("Ta question");
    fireEvent.focus(input);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(fetchMock).toHaveBeenCalledWith("/api/models", expect.objectContaining({ method: "GET" }));

    // Un second focus ne redemande pas les modèles.
    fireEvent.focus(input);
    await waitFor(() => expect(screen.getByRole("combobox")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("recours : charge les modèles au premier envoi même sans focus préalable de la saisie", async () => {
    const payload = { default: "a", models: [{ id: "a", provider: "p" }] };
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.endsWith("/api/models")) {
        return new Response(JSON.stringify(payload), { status: 200 });
      }
      // /api/ask : flux SSE vide, clos immédiatement (aucun événement à traiter).
      return new Response(new ReadableStream({ start: (controller) => controller.close() }), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<Demo />);
    expect(fetchMock).not.toHaveBeenCalled();

    // Envoi direct d'une suggestion : ne passe jamais par le focus du champ de saisie.
    const suggestion = screen.getByRole("button", { name: SUGGESTIONS[0] });
    fireEvent.click(suggestion);

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith("/api/models", expect.objectContaining({ method: "GET" })),
    );
  });
});
