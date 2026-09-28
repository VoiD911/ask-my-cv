import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe as suite, expect, it, vi } from "vitest";

import { createInitialState, reduce, type PipelineEvent, type RunState } from "@/lib/pipeline";

import { ATTACKS, Chat, MAX_QUESTION, SUGGESTIONS, parseSources, segments, type Exchange } from "./Chat";

function run(events: PipelineEvent[]): RunState {
  return events.reduce(reduce, createInitialState());
}

const DONE = {
  type: "done",
  tokens_in: 10,
  tokens_out: 5,
  cost_usd: 0.00012,
  latency_ms: 42,
  answer_override: null,
  trace_id: null,
} as const;

function renderChat(exchanges: Exchange[] = [], overrides: Partial<Parameters<typeof Chat>[0]> = {}) {
  const props = {
    exchanges,
    busy: false,
    onAsk: vi.fn(),
    onStop: vi.fn(),
    onInteract: vi.fn(),
    models: [],
    model: null,
    onModelChange: vi.fn(),
    ...overrides,
  };
  render(<Chat {...props} />);
  return props;
}

suite("segments et sources", () => {
  it("découpe les marqueurs [n] sans interpréter le reste", () => {
    expect(segments("A [1] et [12].")).toEqual([
      { kind: "text", text: "A " },
      { kind: "cite", n: 1, text: "[1]" },
      { kind: "text", text: " et " },
      { kind: "cite", n: 12, text: "[12]" },
      { kind: "text", text: "." },
    ]);
  });

  it("lit le numéro et la section de chaque source", () => {
    expect(parseSources(["[3] Formation", "sans numéro"])).toEqual([
      { n: 3, label: "Formation" },
      { n: 2, label: "sans numéro" },
    ]);
  });
});

suite("Chat", () => {
  it("propose 4 questions tirées du CV et les envoie telles quelles", () => {
    const props = renderChat();
    expect(SUGGESTIONS).toHaveLength(4);
    fireEvent.click(screen.getByRole("button", { name: SUGGESTIONS[0] }));
    expect(props.onAsk).toHaveBeenCalledWith(SUGGESTIONS[0]);
  });

  it("ouvre le menu des 3 attaques", () => {
    const props = renderChat();
    expect(ATTACKS).toHaveLength(3);
    const toggle = screen.getByRole("button", { name: /Essaie de m'attaquer/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const attack = ATTACKS[1];
    if (!attack) throw new Error("attaque manquante");
    fireEvent.click(screen.getByRole("button", { name: new RegExp(attack.label) }));
    expect(props.onAsk).toHaveBeenCalledWith(attack.text);
  });

  it("limite la saisie à 10 000 caractères et affiche le compteur", () => {
    renderChat();
    const input = screen.getByRole("textbox", { name: "Votre question ou annonce" });
    expect(input).toHaveAttribute("maxLength", String(MAX_QUESTION));
    fireEvent.change(input, { target: { value: "Bonjour" } });
    expect(screen.getByText(/^7\/10000/)).toBeInTheDocument();
  });

  it("masque le sélecteur de modèle s'il n'y en a qu'un", () => {
    renderChat([], { models: [{ id: "a", provider: "fake" }] });
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("montre le sélecteur s'il y a plusieurs modèles", () => {
    const props = renderChat([], {
      models: [
        { id: "a", provider: "fake" },
        { id: "b", provider: "fake" },
      ],
      model: "a",
    });
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "b" } });
    expect(props.onModelChange).toHaveBeenCalledWith("b");
  });

  it("remplace Envoyer par Arrêter pendant une requête", () => {
    const props = renderChat([], { busy: true });
    expect(screen.queryByRole("button", { name: "Envoyer" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Arrêter" }));
    expect(props.onStop).toHaveBeenCalled();
  });

  it("affiche la réponse en texte et relie [n] à sa source", () => {
    const state = run([
      { type: "answer", text: "<b>Architecte</b> [2]" },
      { ...DONE, sources: ["[1] Profil", "[2] Expérience — NeoBotiQc (2025-2026)"] },
    ]);
    renderChat([{ id: 7, question: "Rôle ?", run: state, status: "done" }]);
    const reply = screen.getByTestId("reply");
    expect(reply).toHaveTextContent("<b>Architecte</b> [2]");
    expect(reply.querySelector("b")).toBeNull();
    const cite = within(reply).getByRole("link", { name: /^source 2 : / });
    expect(cite).toHaveAttribute("href", "#src-7-2");
    expect(cite).toHaveAttribute("title", "Expérience — NeoBotiQc (2025-2026)");
    expect(reply.querySelector("#src-7-2")).toHaveAttribute("data-cited", "true");
  });

  it("affiche le message imposé par l'API tel quel, sans réponse", () => {
    const message = "Requête bloquée par le détecteur d'injection. Rien n'a été envoyé au LLM.";
    const state = run([
      { type: "stage.end", name: "injection", status: "blocked", duration_ms: 1, attrs: {} },
      { ...DONE, sources: [], answer_override: message },
    ]);
    renderChat([{ id: 1, question: "Ignore…", run: state, status: "done" }]);
    const notice = screen.getByTestId("override");
    expect(notice).toHaveTextContent(message);
    expect(notice).toHaveTextContent("bloquée à l'étape injection");
    expect(notice).toHaveAttribute("data-tone", "blocked");
  });

  it("signale une question arrêtée et une erreur réseau", () => {
    renderChat([
      { id: 1, question: "a", run: createInitialState(), status: "stopped" },
      { id: 2, question: "b", run: createInitialState(), status: "failed", error: "Le service ne répond pas." },
    ]);
    const replies = screen.getAllByTestId("reply");
    expect(replies[0]).toHaveTextContent("arrêtée");
    expect(replies[1]).toHaveTextContent("Le service ne répond pas.");
  });
});
