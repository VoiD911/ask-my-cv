import { readFileSync } from "node:fs";

import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";

import { expect, test } from "./csp-fixture";

// Mode rediffusion (#129). Les enregistrements servis ici sont la fixture de test
// (e2e/fixtures/replays, API locale et faux LLM), jamais livrée avec le site : les requêtes
// /replays/*.json sont interceptées. Aucun appel réel à /api/ask n'est nécessaire.

const FIXTURES = {
  fr: readFileSync(new URL("./fixtures/replays/fr.json", import.meta.url), "utf8"),
  en: readFileSync(new URL("./fixtures/replays/en.json", import.meta.url), "utf8"),
};

const BUDGET_SSE = [
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
]
  .map((e) => `data: ${JSON.stringify(e)}\n\n`)
  .join("");

function chip(page: Page, stage: string) {
  return page.locator(`.chip[data-stage="${stage}"]:visible`);
}

async function serveFixtures(page: Page) {
  for (const locale of ["fr", "en"] as const) {
    await page.route(`**/replays/${locale}.json`, (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: FIXTURES[locale] }),
    );
  }
}

async function expectNoA11yViolations(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(results.violations.map((v) => `${v.id} (${v.nodes.length}) : ${v.help}`)).toEqual([]);
}

async function expectReplayed(page: Page) {
  const replayed = page.locator('[data-testid="exchange"][data-replay]').last();
  await expect(replayed).toHaveAttribute("data-status", "done");
  await expect(replayed.getByTestId("reply")).toContainText("[1]");
  await expect(chip(page, "output_guard")).toHaveAttribute("data-status", "ok");
  return replayed;
}

test.beforeEach(async ({ page }) => {
  await serveFixtures(page);
});

test("?replay=1 : rediffusion au chargement, étiquetée, sans appel à l'API, accessible", async ({ page }) => {
  let asked = 0;
  await page.route("**/api/ask", (route) => {
    asked += 1;
    return route.abort();
  });
  await page.goto("/?replay=1");
  const banner = page.getByTestId("replay-banner");
  await expect(banner).toContainText("Rediffusion");
  await expect(banner).toContainText("rediffusion demandée pour la démonstration.");
  const replayed = await expectReplayed(page);
  await expect(replayed).toContainText("rediffusion");

  await page.getByRole("button", { name: "Rejouer un autre échange" }).click();
  await expect(page.locator('[data-testid="exchange"][data-replay]')).toHaveCount(2);
  await expectReplayed(page);
  expect(asked).toBe(0);
  await expectNoA11yViolations(page);
});

test("/en/?replay=1 : rediffusion anglaise", async ({ page }) => {
  await page.goto("/en/?replay=1");
  await expect(page.getByTestId("replay-banner")).toContainText("replay requested for the demo.");
  const replayed = await expectReplayed(page);
  await expect(replayed).toContainText("What is his role at NeoBotiQc?");
  await expectNoA11yViolations(page);
});

test("API en panne (503) : nouvelle tentative, puis rediffusion d'un échange similaire", async ({ page }) => {
  let asked = 0;
  await page.route("**/api/ask", (route) => {
    asked += 1;
    return route.fulfill({ status: 503, body: "" });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Quel est son sujet de doctorat ?" }).click();

  await expect(page.getByTestId("replay-banner")).toContainText("l'API ne répond pas pour le moment.");
  await expect(page.getByTestId("paused")).toContainText("ta question n'a pas reçu de réponse");
  await expectReplayed(page);
  expect(asked).toBe(2);
  await expectNoA11yViolations(page);
});

test("budget du jour atteint : rediffusion sans nouvelle tentative", async ({ page }) => {
  let asked = 0;
  await page.route("**/api/ask", (route) => {
    asked += 1;
    return route.fulfill({ status: 200, contentType: "text/event-stream", body: BUDGET_SSE });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Quel est son rôle chez NeoBotiQc ?" }).click();
  await expect(page.getByTestId("replay-banner")).toContainText("le budget du jour est atteint.");
  await expectReplayed(page);
  expect(asked).toBe(1);
});

test("mouvement réduit : la rediffusion s'affiche d'un coup", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/?replay=1");
  await expectReplayed(page);
});
