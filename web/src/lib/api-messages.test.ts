import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { MESSAGES } from "@/i18n/messages";

import { REFUSAL, isRefusal, localizeOverride } from "./api-messages";

// Vitest tourne depuis web/ : les sources de l'API sont à la racine du dépôt.
const repo = (path: string) => readFileSync(resolve(process.cwd(), "..", path), "utf8");

/** Chaînes Python d'un bloc (concaténation implicite des littéraux entre parenthèses). */
function pythonStrings(block: string): Map<string, string> {
  const out = new Map<string, string>();
  for (const m of block.matchAll(/"(\w+)":\s*\(?((?:\s*"[^"]*"\s*)+)\)?,/g)) {
    const text = [...(m[2] ?? "").matchAll(/"([^"]*)"/g)].map((s) => s[1]).join("");
    out.set(m[1] as string, text);
  }
  return out;
}

describe("messages de l'API", () => {
  const pipeline = repo("src/ask_my_cv/pipeline.py");

  it("les messages français du catalogue sont exactement ceux de pipeline.py", () => {
    const block = /BLOCK_MESSAGES = \{([\s\S]*?)\n\}/.exec(pipeline)?.[1] ?? "";
    const api = pythonStrings(block);
    expect(api.size).toBeGreaterThan(5);
    const { error, ...blocks } = MESSAGES.fr.overrides;
    expect(Object.fromEntries(api)).toEqual(blocks);
    expect(/ERROR_MESSAGE = "([^"]+)"/.exec(pipeline)?.[1]).toBe(error);
  });

  it("la phrase de refus est celle du garde-fou de sortie", () => {
    expect(/REFUSAL = "([^"]+)"/.exec(repo("src/ask_my_cv/output_guard.py"))?.[1]).toBe(REFUSAL);
  });

  it("reconnaît le refus comme output_guard (guillemets et blancs ignorés)", () => {
    expect(isRefusal(REFUSAL)).toBe(true);
    expect(isRefusal(`« ${REFUSAL} »`)).toBe(true);
    expect(isRefusal(`  "${REFUSAL}"\n`)).toBe(true);
    expect(isRefusal(`${REFUSAL} [1]`)).toBe(false);
    expect(isRefusal("I can't find this information in the CV.")).toBe(false);
  });

  it("traduit les messages connus en anglais, garde tel quel un message inconnu ou en français", () => {
    const fr = MESSAGES.fr.overrides.injection_detected;
    expect(localizeOverride(fr, "fr")).toBe(fr);
    expect(localizeOverride(fr, "en")).toBe(MESSAGES.en.overrides.injection_detected);
    expect(localizeOverride("Nouveau message.", "en")).toBe("Nouveau message.");
  });
});

describe("attaques pré-écrites", () => {
  it("chaque attaque, en français comme en anglais, est une ligne `block` de adversarial.jsonl", () => {
    const blocked = new Set(
      repo("ml/data/adversarial.jsonl")
        .split("\n")
        .filter(Boolean)
        .map((line) => JSON.parse(line) as { text: string; expect: string })
        .filter((row) => row.expect === "block")
        .map((row) => row.text),
    );
    for (const locale of ["fr", "en"] as const) {
      for (const attack of MESSAGES[locale].chat.attacks) expect(blocked.has(attack.text), attack.text).toBe(true);
    }
  });
});
