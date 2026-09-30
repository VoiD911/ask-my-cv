import { vi } from "vitest";

import { Chat, type Exchange } from "@/components/Chat";
import { SiteNav } from "@/components/SiteNav";
import { MESSAGES } from "@/i18n/messages";
import { REFUSAL } from "@/lib/api-messages";
import { deliveryPlans } from "@/lib/delivery";
import { createInitialState, describe as summary, reduce, type PipelineEvent } from "@/lib/pipeline";
import { render, screen, within } from "@/test/intl";

import { ArchitectureView } from "./ArchitectureView";
import { DeliveryView } from "./DeliveryView";
import { HomeView } from "./HomeView";
import { PlanView } from "./PlanView";
import { XopsView } from "./XopsView";

const en = { locale: "en" as const };

const DONE = {
  type: "done",
  tokens_in: 10,
  tokens_out: 5,
  cost_usd: 0.00012,
  latency_ms: 42,
  answer_override: null,
  trace_id: null,
} as const;

function runEn(events: PipelineEvent[]) {
  return events.reduce(reduce, createInitialState("en"));
}

function renderChat(exchanges: Exchange[]) {
  render(
    <Chat
      exchanges={exchanges}
      busy={false}
      onAsk={vi.fn()}
      onStop={vi.fn()}
      onInteract={vi.fn()}
      models={[]}
      model={null}
      onModelChange={vi.fn()}
    />,
    en,
  );
}

describe("interface anglaise", () => {
  it("accueil : textes anglais, CV en français signalé, circuit et relevé traduits", () => {
    render(<HomeView />, en);
    expect(screen.getByRole("heading", { level: 1, name: "Steve Lang" })).toBeInTheDocument();
    expect(screen.getByText(MESSAGES.en.home.role)).toBeInTheDocument();
    expect(screen.getByText(/written in French/)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /^8-stage pipeline circuit: intake waiting/ })).toBeInTheDocument();
    expect(screen.getByText("Waiting for a request.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "What is his role at NeoBotiQc?" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Your question or job posting" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Readout of the last question" })).toHaveTextContent("latency");
  });

  it("navigation : onglets sous /en, lien vers la même page en français", () => {
    render(<SiteNav current="/livraison/" path="/livraison/1a/" />, en);
    const nav = screen.getByRole("navigation", { name: "Main navigation" });
    expect(within(nav).getByRole("link", { name: "Delivery" })).toHaveAttribute("href", expect.stringMatching(/^\/en\/livraison\/?$/));
    expect(within(nav).getByRole("link", { name: "Delivery" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: "Demo" })).toHaveAttribute("href", expect.stringMatching(/^\/en\/?$/));
    const french = within(nav).getByRole("link", { name: "Lire cette page en français" });
    expect(french).toHaveAttribute("href", "/livraison/1a/");
    expect(french).toHaveAttribute("hreflang", "fr");
    expect(french).toHaveAttribute("lang", "fr");
  });

  it("navigation française : lien vers la même page en anglais", () => {
    render(<SiteNav current="/xops/" />);
    const english = screen.getByRole("link", { name: "Read this page in English" });
    expect(english).toHaveAttribute("href", "/en/xops/");
    expect(english).toHaveAttribute("hreflang", "en");
  });

  it("refus de l'API (phrase française exacte) : rendu anglais, original conservé", () => {
    const run = runEn([{ type: "answer", text: REFUSAL }, { ...DONE, sources: ["[1] Profil"] }]);
    renderChat([{ id: 1, question: "Does he speak Klingon?", run, status: "done" }]);
    expect(screen.getByTestId("refusal")).toHaveTextContent("I can't find this information in the CV.");
    const original = screen.getByText(REFUSAL);
    expect(original).toHaveAttribute("lang", "fr");
  });

  it("message de blocage de l'API : traduit, étape en anglais", () => {
    const run = runEn([
      { type: "stage.end", name: "injection", status: "blocked", duration_ms: 1, attrs: { score: 0.97 } },
      { ...DONE, sources: [], answer_override: MESSAGES.fr.overrides.injection_detected },
    ]);
    renderChat([{ id: 1, question: "Ignore…", run, status: "done" }]);
    const notice = screen.getByTestId("override");
    expect(notice).toHaveTextContent("blocked at the injection stage");
    expect(notice).toHaveTextContent(MESSAGES.en.overrides.injection_detected);
    expect(summary(run)).toBe("Finished: injection stage blocked.");
  });

  it("réponse ordinaire : sources du CV balisées en français, nombres à l'anglaise", () => {
    const run = runEn([
      { type: "stage.end", name: "retrieval", status: "ok", duration_ms: 1, attrs: { top_score: 0.812, hit: true } },
      { type: "answer", text: "Principal architect [1]" },
      { ...DONE, sources: ["[1] Expérience — NeoBotiQc"] },
    ]);
    expect(run.stages.retrieval?.attrs).toEqual({ top_score: "0.812", hit: "true" });
    renderChat([{ id: 3, question: "Role?", run, status: "done" }]);
    const reply = screen.getByTestId("reply");
    expect(within(reply).getByRole("link", { name: "source 1: Expérience — NeoBotiQc" })).toBeInTheDocument();
    expect(reply.querySelector("ol")).toHaveAttribute("lang", "fr");
    expect(reply).toHaveTextContent("1 CV passage consulted · 1 cited");
  });

  it("architecture et XOps : titres et glossaire en anglais, onglets internes sous /en", () => {
    render(<ArchitectureView />, en);
    expect(screen.getByRole("heading", { level: 2, name: "The path of a request" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Glossary" })).toBeInTheDocument();
    render(<XopsView />, en);
    expect(screen.getByRole("heading", { level: 2, name: "Verify it yourself" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Delivery tab" })).toHaveAttribute("href", expect.stringMatching(/^\/en\/livraison\/?$/));
  });

  it("livraison : habillage anglais, journal en français balisé comme tel", () => {
    render(<DeliveryView />, en);
    expect(screen.getByRole("heading", { level: 1, name: "Delivery" })).toBeInTheDocument();
    expect(screen.getByTestId("journal-language")).toHaveTextContent("Development journal in French");
    const first = deliveryPlans[0]!;
    expect(screen.getByText(first.goal)).toHaveAttribute("lang", "fr");
    expect(screen.getAllByRole("link", { name: /Plan 1a/ })[0]).toHaveAttribute("href", expect.stringMatching(/^\/en\/livraison\/1a\/?$/));
  });

  it("plan : étapes et verdicts traduits, retour vers /en/livraison", () => {
    const plan = deliveryPlans.find((p) => p.tasks.some((t) => t.events.some((e) => e.verdict === "approuvé")))!;
    render(<PlanView plan={plan} />, en);
    expect(screen.getByRole("link", { name: "← All plans" })).toHaveAttribute("href", expect.stringMatching(/^\/en\/livraison\/?$/));
    expect(screen.getAllByText("Verdict: approved").length).toBeGreaterThan(0);
    expect(screen.queryByText(/^Tâche/)).toBeNull();
  });
});
