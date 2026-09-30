import AxeBuilder from "@axe-core/playwright";

import { expect, test } from "./csp-fixture";

// Page statique /xops : aucune dépendance à l'API locale.

const DISCIPLINES = ["DevOps", "DevSecOps", "MLOps", "LLMOps", "FinOps"];

test.beforeEach(async ({ page }) => {
  await page.goto("/xops/");
  await expect(page.getByRole("heading", { level: 1, name: "XOps" })).toBeVisible();
});

test("matrice, disciplines, preuves et commandes, accessibles (axe)", async ({ page }) => {
  await expect(page).toHaveTitle("XOps — Interroge mon CV");
  for (const name of [...DISCIPLINES, "Vérifier soi-même", "Glossaire"]) {
    await expect(page.getByRole("heading", { level: 2, name })).toBeVisible();
  }
  const table = page.getByRole("table", { name: "Pratiques par discipline, avec leur statut" });
  await expect(table.getByRole("row")).toHaveCount(DISCIPLINES.length + 1);
  await expect(page.getByText("Partiel", { exact: true }).first()).toBeVisible();
  await expect(page.locator(".xops-cmd code").first()).toContainText("cosign verify-blob");

  // Chaque case a au moins une preuve cliquable.
  for (const cell of await page.locator(".xops-cell").all()) {
    expect(await cell.locator(".xops-proofs a").count()).toBeGreaterThan(0);
  }

  // Rien ne déborde horizontalement, y compris sur mobile.
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);

  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(results.violations.map((v) => `${v.id} (${v.nodes.length}) : ${v.help}`)).toEqual([]);
});

test("sigle : définition au focus clavier, lien vers le glossaire", async ({ page }) => {
  const term = page.getByRole("link", { name: "SLSA" }).first();
  await term.focus();
  const tip = page.locator(`#${await term.getAttribute("aria-describedby")}`.replace(/:/g, "\\:"));
  await expect(tip).toBeVisible();
  await expect(tip).toContainText("Supply-chain Levels for Software Artifacts");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#glossaire-slsa$/);
  await expect(page.locator("#glossaire-slsa")).toBeInViewport();
});

test("navigation : onglet courant, sommaire vers une discipline, lien vers la vérification", async ({ page }) => {
  const nav = page.getByRole("navigation", { name: "Navigation principale" });
  await expect(nav.getByRole("link", { name: "XOps" })).toHaveAttribute("aria-current", "page");
  const toc = page.getByRole("navigation", { name: "Sommaire de la page" });
  await toc.getByRole("link", { name: /MLOps/ }).focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#mlops$/);
  await expect(page.getByRole("heading", { level: 2, name: "MLOps" })).toBeInViewport();
  await page.getByRole("link", { name: "Commandes de vérification" }).first().click();
  await expect(page).toHaveURL(/#verifier-/);
});

test("l'accueil et l'onglet Architecture mènent à l'onglet XOps", async ({ page }) => {
  for (const from of ["/", "/architecture/"]) {
    await page.goto(from);
    await page.getByRole("navigation", { name: "Navigation principale" }).getByRole("link", { name: "XOps" }).click();
    await expect(page).toHaveURL(/\/xops\/$/);
  }
});
