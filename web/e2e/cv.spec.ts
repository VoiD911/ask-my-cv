import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";

import { expect, test } from "./csp-fixture";

// Pages statiques /cv/ et /en/cv/ : CV lisible, contact, PDF (généré par `npm run pdf`).

async function expectAccessible(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(results.violations.map((v) => `${v.id} (${v.nodes.length}) : ${v.help}`)).toEqual([]);
}

const CASES = [
  {
    path: "/cv/",
    title: "CV — Steve Lang",
    nav: "Navigation principale",
    sections: ["Profil", "Compétences", "Formation", "Langues"],
    download: "Télécharger le CV (PDF)",
    pdf: "/cv/Steve-Lang-CV-fr.pdf",
  },
  {
    path: "/en/cv/",
    title: "Resume — Steve Lang",
    nav: "Main navigation",
    sections: ["Profile", "Skills", "Education", "Languages"],
    download: "Download the resume (PDF)",
    pdf: "/en/cv/Steve-Lang-CV-en.pdf",
  },
];

for (const c of CASES) {
  test(`${c.path} : sections, contact, PDF téléchargeable, accessible (axe)`, async ({ page }) => {
    await page.goto(c.path);
    await expect(page).toHaveTitle(c.title);
    await expect(page.getByRole("heading", { level: 1, name: "Steve Lang" })).toBeVisible();
    for (const name of c.sections) {
      await expect(page.getByRole("heading", { level: 2, name, exact: true })).toBeVisible();
    }
    const nav = page.getByRole("navigation", { name: c.nav });
    await expect(nav.getByRole("link", { name: "CV", exact: true })).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("link", { name: "job@stevelang.net" })).toHaveAttribute("href", "mailto:job@stevelang.net");
    const linkedin = page.getByRole("link", { name: "linkedin.com/in/steve-cl-lang" });
    await expect(linkedin).toHaveAttribute("href", "https://www.linkedin.com/in/steve-cl-lang/");
    await expect(linkedin).toHaveAttribute("rel", "me noopener");

    const link = page.getByRole("link", { name: c.download });
    await expect(link).toHaveAttribute("href", c.pdf);
    const response = await page.request.get(c.pdf);
    expect(response.status()).toBe(200);
    expect(response.headers()["content-type"]).toBe("application/pdf");
    const body = await response.body();
    expect(body.subarray(0, 5).toString("latin1")).toBe("%PDF-");
    expect(body.length).toBeGreaterThan(10_000);

    await expectAccessible(page);
  });
}

test("impression : navigation et bouton masqués, contenu du CV conservé", async ({ page }) => {
  await page.goto("/cv/");
  await page.emulateMedia({ media: "print" });
  await expect(page.getByRole("navigation", { name: "Navigation principale" })).toBeHidden();
  await expect(page.getByRole("link", { name: "Télécharger le CV (PDF)" })).toBeHidden();
  await expect(page.getByRole("heading", { level: 2, name: "Formation" })).toBeVisible();
  await expect(page.getByRole("link", { name: "job@stevelang.net" })).toBeVisible();
});

test("l'onglet CV est accessible depuis l'accueil, qui affiche aussi LinkedIn", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("link", { name: "steve-cl-lang" })).toHaveAttribute("rel", "me noopener");
  await page.getByRole("navigation", { name: "Navigation principale" }).getByRole("link", { name: "CV", exact: true }).click();
  await expect(page).toHaveURL(/\/cv\/$/);
});
