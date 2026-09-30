import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { MESSAGES } from "./messages";
import { localePath, otherLocale } from "./locales";

type Json = string | number | boolean | null | Json[] | { [key: string]: Json };

/** Chemins des feuilles (clés et indices de tableau) d'un catalogue. */
function leaves(value: Json, prefix = ""): Map<string, string> {
  const out = new Map<string, string>();
  if (Array.isArray(value)) {
    value.forEach((item, i) => leaves(item, `${prefix}[${i}]`).forEach((v, k) => out.set(k, v)));
  } else if (value !== null && typeof value === "object") {
    for (const [key, item] of Object.entries(value)) {
      leaves(item, prefix ? `${prefix}.${key}` : key).forEach((v, k) => out.set(k, v));
    }
  } else {
    out.set(prefix, String(value));
  }
  return out;
}

/** Arguments ICU d'un message (`{stage}`, `{count, plural, …}` → stage, count). */
function args(message: string): string[] {
  return [...message.matchAll(/\{\s*(\w+)\s*[,}]/g)].map((m) => m[1] as string).sort();
}

const fr = leaves(MESSAGES.fr as unknown as Json);
const en = leaves(MESSAGES.en as unknown as Json);

describe("catalogues de messages", () => {
  it("chaque clé française a sa clé anglaise, et inversement", () => {
    expect([...en.keys()].filter((k) => !fr.has(k))).toEqual([]);
    expect([...fr.keys()].filter((k) => !en.has(k))).toEqual([]);
  });

  it("aucun message vide", () => {
    for (const [key, value] of [...fr, ...en]) expect(value.trim(), key).not.toBe("");
  });

  it("mêmes arguments ICU dans les deux langues", () => {
    for (const [key, value] of fr) expect(args(en.get(key) ?? ""), key).toEqual(args(value));
  });

  it("les fichiers JSON sont ceux chargés par l'application", () => {
    for (const locale of ["fr", "en"] as const) {
      const file = resolve(process.cwd(), "messages", `${locale}.json`);
      expect(JSON.parse(readFileSync(file, "utf8"))).toEqual(MESSAGES[locale]);
    }
  });
});

describe("chemins localisés", () => {
  it("le français reste à la racine, l'anglais sous /en", () => {
    expect(localePath("fr", "/")).toBe("/");
    expect(localePath("fr", "/livraison/1a/")).toBe("/livraison/1a/");
    expect(localePath("en", "/")).toBe("/en/");
    expect(localePath("en", "/xops/")).toBe("/en/xops/");
    expect(() => localePath("en", "xops/")).toThrow();
    expect(otherLocale("fr")).toBe("en");
    expect(otherLocale("en")).toBe("fr");
  });
});
