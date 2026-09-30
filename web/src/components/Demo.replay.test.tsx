import { fireEvent, render, screen, waitFor, within } from "@/test/intl";
import { afterEach, beforeEach, describe as suite, expect, it, vi } from "vitest";

import fixtureFr from "../../e2e/fixtures/replays/fr.json";

import { SUGGESTIONS } from "./Chat";
import { Demo } from "./Demo";

const FIRST = fixtureFr.replays[0] as { question: string };

function sse(events: object[]): Response {
  const text = events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");
  return new Response(text, { status: 200, headers: { "content-type": "text/event-stream" } });
}

const BUDGET_EVENTS = [
  { type: "stage.start", name: "reception", ts: 1 },
  { type: "stage.end", name: "reception", status: "ok", duration_ms: 1, attrs: {} },
  { type: "stage.start", name: "quota", ts: 2 },
  { type: "stage.end", name: "quota", status: "blocked", duration_ms: 1, attrs: { reason: "budget_exceeded" } },
  {
    type: "done",
    tokens_in: 0,
    tokens_out: 0,
    cost_usd: 0,
    latency_ms: 3,
    sources: [],
    answer_override: "Le budget du jour est atteint : la démo passe en mode rediffusion.",
    trace_id: null,
  },
];

type Handler = (url: string) => Response | Promise<Response>;

function stubFetch(handlers: { ask: Handler; replays?: Handler }) {
  const mock = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input.toString();
    if (url.endsWith("/api/models")) {
      return new Response(JSON.stringify({ default: "a", models: [{ id: "a", provider: "p" }] }));
    }
    if (url.startsWith("/replays/")) {
      return handlers.replays ? handlers.replays(url) : new Response(JSON.stringify(fixtureFr));
    }
    return handlers.ask(url);
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

function askCalls(mock: ReturnType<typeof stubFetch>) {
  return mock.mock.calls.filter(([input]) => String(input).endsWith("/api/ask")).length;
}

suite("Demo — mode rediffusion", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/");
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("API en panne (503, puis 503 à la nouvelle tentative) : question en pause, puis rediffusion étiquetée", async () => {
    const mock = stubFetch({ ask: () => new Response("", { status: 503 }) });
    render(<Demo />);
    fireEvent.click(screen.getByRole("button", { name: SUGGESTIONS[1] }));

    const banner = await screen.findByTestId("replay-banner", {}, { timeout: 5_000 });
    expect(banner).toHaveTextContent("Rediffusion");
    expect(banner).toHaveTextContent("l'API ne répond pas pour le moment.");
    expect(askCalls(mock)).toBe(2);

    const exchanges = screen.getAllByTestId("exchange");
    expect(exchanges).toHaveLength(2);
    // La question du visiteur n'a pas de réponse inventée : elle est marquée en pause.
    expect(within(exchanges[0] as HTMLElement).getByTestId("paused")).toHaveTextContent(
      "ta question n'a pas reçu de réponse",
    );
    const replayed = exchanges[1] as HTMLElement;
    expect(replayed).toHaveAttribute("data-replay", "true");
    expect(replayed).toHaveTextContent("rediffusion");
    await waitFor(() => expect(replayed).toHaveAttribute("data-status", "done"));
    expect(within(replayed).getByRole("link", { name: /^source 1 : / })).toBeInTheDocument();
  });

  it("le direct répond de nouveau : fin du mode rediffusion, bandeau retiré, relevé non marqué", async () => {
    let down = true;
    const answered = [
      { type: "stage.start", name: "reception", ts: 1 },
      { type: "answer", text: "Réponse en direct." },
      { ...BUDGET_EVENTS[4], answer_override: null },
    ];
    stubFetch({ ask: () => (down ? sse(BUDGET_EVENTS) : sse(answered)) });
    render(<Demo />);
    fireEvent.click(screen.getByRole("button", { name: SUGGESTIONS[0] }));
    await screen.findByTestId("replay-banner");
    await waitFor(() => expect(screen.getByTestId("demo-footer")).toHaveAttribute("data-recorded", "true"));
    await waitFor(() => expect(screen.getByRole("button", { name: SUGGESTIONS[1] })).toBeEnabled());
    down = false;
    fireEvent.click(screen.getByRole("button", { name: SUGGESTIONS[1] }));
    await screen.findByText("Réponse en direct.");
    await waitFor(() => expect(screen.queryByTestId("replay-banner")).toBeNull());
    expect(screen.getByTestId("demo-footer")).not.toHaveAttribute("data-recorded");
    // Région annoncée persistante, vide hors rediffusion.
    expect(screen.getByTestId("replay-live")).toHaveAttribute("aria-live", "polite");
  });

  it("démontage pendant la lecture : plus aucun événement rejoué", async () => {
    window.history.replaceState(null, "", "/?replay=1");
    stubFetch({ ask: () => sse([]) });
    const { unmount } = render(<Demo />);
    await screen.findByTestId("replay-banner");
    expect(() => unmount()).not.toThrow();
  });

  it("budget du jour atteint : rediffusion immédiate, sans nouvelle tentative", async () => {
    const mock = stubFetch({ ask: () => sse(BUDGET_EVENTS) });
    render(<Demo />);
    fireEvent.click(screen.getByRole("button", { name: SUGGESTIONS[0] }));
    const banner = await screen.findByTestId("replay-banner");
    expect(banner).toHaveTextContent("le budget du jour est atteint.");
    expect(askCalls(mock)).toBe(1);
  });

  it("aucune rediffusion disponible : message d'erreur habituel, pas de bandeau", async () => {
    stubFetch({ ask: () => new Response("", { status: 502 }), replays: () => new Response("", { status: 404 }) });
    render(<Demo />);
    fireEvent.click(screen.getByRole("button", { name: SUGGESTIONS[0] }));
    expect(await screen.findByText("Le service ne répond pas. Réessaie dans un instant.", {}, { timeout: 5_000 })).toBeInTheDocument();
    expect(screen.queryByTestId("replay-banner")).toBeNull();
  });

  it("?replay=1 : rediffusion au chargement, jamais d'appel à /api/ask", async () => {
    window.history.replaceState(null, "", "/?replay=1");
    const mock = stubFetch({ ask: () => sse([]) });
    render(<Demo />);
    const banner = await screen.findByTestId("replay-banner");
    expect(banner).toHaveTextContent("rediffusion demandée pour la démonstration.");
    await waitFor(() => expect(screen.getByTestId("exchange")).toHaveTextContent(FIRST.question));

    await waitFor(() => expect(screen.getByTestId("exchange")).toHaveAttribute("data-status", "done"));
    fireEvent.click(screen.getByRole("button", { name: SUGGESTIONS[2] }));
    await waitFor(() => expect(screen.getAllByTestId("exchange")).toHaveLength(3));
    expect(askCalls(mock)).toBe(0);
  });
});
