import AxeBuilder from "@axe-core/playwright";
import type { Page, TestInfo } from "@playwright/test";

import { expect, test } from "./csp-fixture";

// Parcours de la page d'accueil contre l'API locale (faux LLM, classifieur ONNX promu).
// La fixture CSP fait échouer tout parcours qui déclenche une violation CSP.

const STAGES = [
  "reception",
  "quota",
  "injection",
  "embedding",
  "retrieval",
  "prompt",
  "llm",
  "output_guard",
];

/** Puces visibles : la carte (bureau) ou la colonne (mobile), jamais les deux. */
function chip(page: Page, stage: string) {
  return page.locator(`.chip[data-stage="${stage}"]:visible`);
}

/** Mode capture (vérification visuelle) : `E2E_CAPTURE_DIR=... npm run e2e`. */
async function capture(page: Page, info: TestInfo, state: string) {
  const dir = process.env.E2E_CAPTURE_DIR;
  if (!dir) return;
  const device = info.project.name === "mobile" ? "mobile" : "desktop";
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: `${dir}/home-${device}-${state}.png`, fullPage: true });
}

async function expectNoA11yViolations(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  const summary = results.violations.map((v) => `${v.id} (${v.nodes.length}) : ${v.help}`);
  expect(summary).toEqual([]);
}

test.beforeAll(async ({ request }) => {
  const health = await request.get("/api/healthz").catch(() => null);
  expect(
    health?.ok(),
    "API locale injoignable sur 127.0.0.1:8000 : lancer uvicorn avec ASK_SETTINGS=settings.ci.yaml",
  ).toBe(true);
});

test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Steve Lang" })).toBeVisible();
});

test("au repos : cartouche, circuit en attente, relevé vide, accessible", async ({ page }, info) => {
  await expect(page).toHaveTitle("Interroge mon CV — Steve Lang");
  await expect(page.getByRole("link", { name: "job@stevelang.net" })).toHaveAttribute(
    "href",
    "mailto:job@stevelang.net",
  );
  for (const stage of STAGES) {
    await expect(chip(page, stage)).toHaveAttribute("data-status", "idle");
  }
  await expect(page.getByTestId("readout-latency")).toContainText("—");
  await expect(page.getByText(/traitées aux États-Unis par Amazon Bedrock/)).toBeVisible();
  await expectNoA11yViolations(page);
  await capture(page, info, "idle");
});

test("question suggérée : 8 étapes ok, réponse citée, relevé rempli", async ({ page }, info) => {
  await page.getByRole("button", { name: "Quel est son rôle chez NeoBotiQc ?" }).click();

  for (const stage of STAGES) {
    await expect(chip(page, stage)).toHaveAttribute("data-status", "ok");
  }

  const reply = page.getByTestId("reply").last();
  await expect(reply).toContainText("[1]");
  const cite = reply.getByRole("link", { name: /^source 1 : / });
  await expect(cite).toHaveAttribute("href", /^#src-\d+-1$/);
  await expect(reply.locator("li[data-cited]")).toHaveCount(1);
  await expect(page.getByTestId("override")).toHaveCount(0);

  await expect(page.getByTestId("readout-latency")).toContainText(/\d\s?(ms|s)$/);
  await expect(page.getByTestId("readout-tokens-in")).toContainText(/\d/);
  await expect(page.getByTestId("readout-tokens-out")).not.toContainText("—");
  await expect(page.getByTestId("readout-cost")).toContainText(/\d,\d{4,6}\s\$/);
  await expect(page.locator(".circuit__log")).toContainText("Terminé en");

  await expectNoA11yViolations(page);
  await capture(page, info, "answered");
});

test("attaque : injection bloquée, rien n'atteint le LLM, message de l'API tel quel", async ({
  page,
}, info) => {
  await page.getByRole("button", { name: "Essaie de m'attaquer" }).click();
  await page.getByRole("button", { name: /Contourner les consignes/ }).click();

  await expect(chip(page, "injection")).toHaveAttribute("data-status", "blocked");
  await expect(chip(page, "reception")).toHaveAttribute("data-status", "ok");
  for (const stage of ["embedding", "retrieval", "prompt", "llm", "output_guard"]) {
    await expect(chip(page, stage)).toHaveAttribute("data-status", "idle");
  }

  const override = page.getByTestId("override");
  await expect(override).toContainText(
    "Requête bloquée par le détecteur d'injection. Rien n'a été envoyé au LLM.",
  );
  await expect(override).toContainText("bloquée à l'étape injection");
  await expect(page.locator(".answer__text")).toHaveCount(0);
  await expect(page.getByTestId("readout-tokens-out")).toContainText("0");
  await expect(page.locator(".circuit__log")).toContainText("étape injection bloquée");

  await capture(page, info, "blocked");
});

test("saisie : 10 000 caractères au plus, compteur, envoi au clavier", async ({ page }) => {
  const input = page.getByRole("textbox", { name: "Votre question ou annonce" });
  await input.fill("a".repeat(10_050));
  await expect(input).toHaveValue("a".repeat(10_000));
  await expect(page.getByText("10000/10000")).toBeVisible();

  await input.fill("Quelles langues parle-t-il ?");
  await input.press("Enter");
  await expect(page.getByTestId("exchange")).toHaveCount(1);
  await expect(chip(page, "output_guard")).toHaveAttribute("data-status", "ok");
  await expect(input).toHaveValue("");
});

test("arrêt : le bouton Arrêter interrompt la requête en cours", async ({ page }) => {
  // Réponse retenue indéfiniment : la requête reste en cours jusqu'à l'arrêt.
  await page.route("**/api/ask", () => new Promise(() => {}));
  await page.getByRole("button", { name: "Quel est son sujet de doctorat ?" }).click();
  const stop = page.getByRole("button", { name: "Arrêter" });
  await expect(stop).toBeVisible();
  await stop.click();
  await expect(page.getByTestId("reply").last()).toContainText("arrêtée");
  await expect(page.getByRole("button", { name: "Envoyer" })).toBeVisible();
});
