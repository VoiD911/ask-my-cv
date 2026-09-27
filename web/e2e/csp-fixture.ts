import { expect, test as base } from "@playwright/test";

// Surveillance CSP de chaque test : tout événement `securitypolicyviolation` (écouté dans chaque
// document, avant tout script de la page) et tout message console de refus CSP fait échouer le
// test. Aucun événement toléré. Le serveur e2e sert l'en-tête CSP de production : les violations
// observées sont celles de l'intersection réelle en-tête + meta.

export type CspWatch = {
  /** Violations relevées depuis le début du test (ou le dernier `reset`). */
  violations: () => Promise<string[]>;
  reset: () => Promise<void>;
};

type Report = { directive: string; blocked: string; sample: string; source: string };

export const test = base.extend<{ csp: CspWatch }>({
  csp: [
    async ({ page }, use) => {
      const seen: string[] = [];
      await page.exposeBinding("__reportCspViolation", (_source, r: Report) => {
        seen.push(`event ${r.directive} bloqué=${r.blocked} extrait=${JSON.stringify(r.sample)} (${r.source})`);
      });
      await page.addInitScript(() => {
        document.addEventListener("securitypolicyviolation", (e) => {
          const report = (window as unknown as { __reportCspViolation: (r: Report) => void })
            .__reportCspViolation;
          report({
            directive: e.effectiveDirective,
            blocked: e.blockedURI,
            sample: e.sample,
            source: `${e.sourceFile}:${e.lineNumber}`,
          });
        });
      });
      page.on("console", (msg) => {
        if (/content security policy/i.test(msg.text())) seen.push(`console ${msg.type()} : ${msg.text()}`);
      });
      const flush = async () => {
        // Laisse arriver les rapports encore en vol (binding asynchrone).
        await page.evaluate(() => new Promise((r) => setTimeout(r, 50))).catch(() => undefined);
      };

      await use({
        violations: async () => {
          await flush();
          return [...seen];
        },
        reset: async () => {
          await flush();
          seen.length = 0;
        },
      });

      await flush();
      expect(seen, "violations CSP").toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };
