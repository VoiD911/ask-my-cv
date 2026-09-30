import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";

import { expect, test } from "./csp-fixture";

// Version anglaise (/en/…) : langue du document, alternatives hreflang, sélecteur de langue,
// accessibilité (axe) de chaque page, puis parcours de la démo contre l'API locale.

async function expectNoA11yViolations(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(results.violations.map((v) => `${v.id} (${v.nodes.length}) : ${v.help}`)).toEqual([]);
}

async function expectNoOverflow(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
}

const PAGES = [
  { path: "/en/", fr: "/", title: "Ask my CV — Steve Lang", h1: "Steve Lang", tab: "Demo" },
  { path: "/en/architecture/", fr: "/architecture/", title: "Architecture — Ask my CV", h1: "Architecture", tab: "Architecture" },
  { path: "/en/xops/", fr: "/xops/", title: "XOps — Ask my CV", h1: "XOps", tab: "XOps" },
  { path: "/en/cv/", fr: "/cv/", title: "Resume — Steve Lang", h1: "Steve Lang", tab: "CV" },
  { path: "/en/livraison/", fr: "/livraison/", title: "Delivery — Ask my CV", h1: "Delivery", tab: "Delivery" },
  { path: "/en/livraison/1a/", fr: "/livraison/1a/", title: "Plan 1a — Delivery", h1: "Plan 1a", tab: "Delivery" },
];

const SITE = "https://job.stevelang.net";

for (const p of PAGES) {
  test(`${p.path} : anglais, hreflang, sélecteur vers ${p.fr}, accessible (axe)`, async ({ page }) => {
    await page.goto(p.path);
    await expect(page.getByRole("heading", { level: 1, name: p.h1 })).toBeVisible();
    await expect(page).toHaveTitle(p.title);
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute("href", `${SITE}${p.path}`);
    await expect(page.locator('link[rel="alternate"][hreflang="fr"]')).toHaveAttribute("href", `${SITE}${p.fr}`);
    await expect(page.locator('link[rel="alternate"][hreflang="en"]')).toHaveAttribute("href", `${SITE}${p.path}`);
    await expect(page.locator('link[rel="alternate"][hreflang="x-default"]')).toHaveAttribute("href", `${SITE}${p.fr}`);

    const nav = page.getByRole("navigation", { name: "Main navigation" });
    await expect(nav.getByRole("link", { name: p.tab, exact: true })).toHaveAttribute("aria-current", "page");
    await expect(nav.getByRole("link", { name: "Lire cette page en français" })).toHaveAttribute("href", p.fr);

    await expectNoOverflow(page);
    // Détails dépliés : leur contenu entre dans l'audit.
    for (const summary of await page.locator("main details summary").all()) {
      if (await summary.isVisible()) await summary.click();
    }
    await expectNoA11yViolations(page);
  });
}

test("sélecteur de langue : aller-retour français ↔ anglais sur la même page", async ({ page }) => {
  await page.goto("/xops/");
  await expect(page.locator("html")).toHaveAttribute("lang", "fr");
  await page.getByRole("link", { name: "Read this page in English" }).click();
  await expect(page).toHaveURL(/\/en\/xops\/$/);
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.getByRole("heading", { level: 2, name: "Verify it yourself" })).toBeVisible();
  await page.getByRole("link", { name: "Lire cette page en français" }).click();
  await expect(page).toHaveURL(/\/xops\/$/);
  await expect(page.getByRole("heading", { level: 2, name: "Vérifier soi-même" })).toBeVisible();
});

test("onglets anglais : la navigation reste sous /en", async ({ page }) => {
  await page.goto("/en/");
  const nav = page.getByRole("navigation", { name: "Main navigation" });
  await nav.getByRole("link", { name: "Delivery" }).click();
  await expect(page).toHaveURL(/\/en\/livraison\/$/);
  await expect(page.getByTestId("journal-language")).toContainText("Development journal in French");
  await page.getByRole("link", { name: /Plan 1a/ }).first().click();
  await expect(page).toHaveURL(/\/en\/livraison\/1a\/$/);
  await page.getByRole("link", { name: "← All plans" }).click();
  await expect(page).toHaveURL(/\/en\/livraison\/$/);
});

test("404 : page commune, en français d'abord, avec un lien vers l'accueil anglais", async ({ page }) => {
  const response = await page.goto("/en/page-inexistante/");
  expect(response?.status()).toBe(404);
  await expect(page.locator("html")).toHaveAttribute("lang", "fr");
  await expect(page.getByRole("link", { name: "Back to the home page" })).toHaveAttribute("href", "/en/");
  await expectNoA11yViolations(page);
});

test.describe("démo en anglais (API locale)", () => {
  test.beforeAll(async ({ request }) => {
    const health = await request.get("/api/healthz").catch(() => null);
    expect(
      health?.ok(),
      "API locale injoignable sur 127.0.0.1:8000 : lancer uvicorn avec ASK_SETTINGS=settings.ci.yaml",
    ).toBe(true);
  });

  test.beforeEach(async ({ page }) => {
    await page.goto("/en/");
    await expect(page.getByRole("heading", { level: 1, name: "Steve Lang" })).toBeVisible();
  });

  test("question suggérée : réponse citée, relevé en anglais, accessible", async ({ page }) => {
    await page.getByRole("button", { name: "What is his role at NeoBotiQc?" }).click();
    await expect(page.locator('.chip[data-stage="output_guard"]:visible')).toHaveAttribute("data-status", "ok");
    const reply = page.getByTestId("reply").last();
    await expect(reply.getByRole("link", { name: /^source 1: / })).toBeVisible();
    await expect(reply.locator("ol")).toHaveAttribute("lang", "fr");
    await expect(page.getByTestId("readout-cost")).toContainText(/\$\d\.\d{4,6}/);
    await expect(page.locator(".circuit__log")).toContainText("Finished in");
    await expectNoA11yViolations(page);
  });

  test("attaque : bloquée, message de l'API rendu en anglais", async ({ page }) => {
    await page.getByRole("button", { name: "Try to attack me" }).click();
    await page.getByRole("button", { name: /Bypass the instructions/ }).click();
    await expect(page.locator('.chip[data-stage="injection"]:visible')).toHaveAttribute("data-status", "blocked");
    const override = page.getByTestId("override");
    await expect(override).toContainText("Request blocked by the injection detector. Nothing was sent to the LLM.");
    await expect(override).toContainText("blocked at the injection stage");
    await expect(page.locator(".circuit__log")).toContainText("injection stage blocked");
    await expectNoA11yViolations(page);
  });
});
