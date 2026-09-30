import { expect, test } from "./csp-fixture";

// CSP des scripts : balise meta insérée au build (scripts/csp.mjs) + en-tête de production
// servi par e2e/serve.mjs. La fixture fait échouer tout test qui relève une violation.

const PAGES = [
  { path: "/", status: 200 },
  { path: "/architecture/", status: 200 },
  { path: "/xops/", status: 200 },
  { path: "/404.html", status: 200 },
  { path: "/_not-found/", status: 200 },
  { path: "/page-inexistante/", status: 404 },
];

for (const { path, status } of PAGES) {
  test(`${path} : meta CSP en tête du <head> avant tout script, chaque script en ligne haché, aucune violation`, async ({
    page,
  }) => {
    const response = await page.goto(path);
    expect(response?.status()).toBe(status);
    expect(response?.headers()["content-security-policy"]).toContain("script-src 'self' 'unsafe-inline'");

    const audit = await page.evaluate(async () => {
      const metas = document.querySelectorAll('meta[http-equiv="Content-Security-Policy" i]');
      const meta = metas[0];
      const policy = meta?.getAttribute("content") ?? "";
      // En tête du <head> : premier élément, ou deuxième juste après <meta charset>.
      const first = document.head.firstElementChild;
      const atTop =
        !!meta &&
        (first === meta || (first?.matches("meta[charset]") === true && first.nextElementSibling === meta));
      // Une CSP meta ne couvre que ce qui la suit : aucun <script> ne doit la précéder.
      const scriptsBefore = [...document.scripts].filter(
        (s) => !!meta && !!(s.compareDocumentPosition(meta) & Node.DOCUMENT_POSITION_FOLLOWING),
      ).length;
      const missing: string[] = [];
      const inline = [...document.querySelectorAll("script:not([src])")];
      for (const script of inline) {
        const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(script.textContent ?? ""));
        const hash = btoa(String.fromCharCode(...new Uint8Array(digest)));
        if (!policy.includes(`'sha256-${hash}'`)) missing.push((script.textContent ?? "").slice(0, 60));
      }
      return {
        metas: metas.length,
        atTop,
        scriptsBefore,
        policy,
        inline: inline.length,
        missing,
      };
    });
    expect(audit.metas).toBe(1);
    expect(audit.atTop).toBe(true);
    expect(audit.scriptsBefore).toBe(0);
    expect(audit.policy).toMatch(/^script-src 'self'( 'sha256-[A-Za-z0-9+/]+={0,2}')+$/);
    expect(audit.policy).not.toContain("unsafe-inline");
    expect(audit.inline).toBeGreaterThan(0);
    expect(audit.missing).toEqual([]);
  });
}

test("témoin : un script en ligne non haché est bloqué et la violation est détectée", async ({ page, csp }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Steve Lang" })).toBeVisible();
  const ran = await page.evaluate(() => {
    const s = document.createElement("script");
    s.textContent = "window.__cspCanary = true;";
    document.body.append(s);
    return (window as unknown as { __cspCanary?: boolean }).__cspCanary === true;
  });
  expect(ran).toBe(false);
  // Attendre l'événement ET le message console avant `reset` : un rapport arrivé après
  // ferait échouer la fixture par intermittence.
  await expect
    .poll(() => csp.violations())
    .toEqual(
      expect.arrayContaining([
        expect.stringMatching(/^event script-src-elem /),
        expect.stringMatching(/^console error : .*Content Security Policy/),
      ]),
    );
  // Violation attendue ici seulement : on la retire pour la vérification finale de la fixture.
  await csp.reset();
});
