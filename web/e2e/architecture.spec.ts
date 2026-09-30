import AxeBuilder from "@axe-core/playwright";

import { expect, test } from "./csp-fixture";

// Page statique /architecture : aucune dépendance à l'API locale.

test.beforeEach(async ({ page }) => {
  await page.goto("/architecture/");
  await expect(page.getByRole("heading", { level: 1, name: "Architecture" })).toBeVisible();
});

test("quatre sections, schémas lisibles et accessibles (axe)", async ({ page }) => {
  await expect(page).toHaveTitle("Architecture — Interroge mon CV");
  for (const name of ["Chemin d'une requête", "Infrastructure", "Du code à la production", "Cycle de vie du modèle"]) {
    await expect(page.getByRole("heading", { level: 2, name })).toBeVisible();
  }
  const stages = page.getByRole("list", { name: "Étapes du pipeline, dans l'ordre" }).getByRole("listitem");
  await expect(stages).toHaveCount(8);
  await expect(page.getByText(/^Lecture du schéma/)).toHaveCount(4);

  // Rien ne déborde horizontalement, y compris sur mobile.
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);

  // Étapes dépliées (contenu masqué inclus dans l'audit).
  for (const summary of await page.locator(".arch-steps summary").all()) await summary.click();
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(results.violations.map((v) => `${v.id} (${v.nodes.length}) : ${v.help}`)).toEqual([]);
});

test("navigation au clavier : le sommaire mène aux sections, l'onglet est marqué courant", async ({ page }) => {
  const nav = page.getByRole("navigation", { name: "Navigation principale" });
  await expect(nav.getByRole("link", { name: "Architecture" })).toHaveAttribute("aria-current", "page");
  const toc = page.getByRole("navigation", { name: "Sommaire de la page" });
  await toc.getByRole("link", { name: /Infrastructure/ }).focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#infrastructure$/);
  await expect(page.getByRole("heading", { level: 2, name: "Infrastructure" })).toBeInViewport();
});

test("mouvement réduit : aucune impulsion animée", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const display = await page
    .locator(".arch-flow__item")
    .nth(1)
    .evaluate((el) => getComputedStyle(el, "::after").display);
  expect(display).toBe("none");
});

test("l'accueil mène à l'onglet Architecture", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("navigation", { name: "Navigation principale" }).getByRole("link", { name: "Architecture" }).click();
  await expect(page).toHaveURL(/\/architecture\/$/);
});
