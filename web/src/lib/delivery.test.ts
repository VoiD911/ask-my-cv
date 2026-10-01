import { describe, expect, it } from "vitest";

import { issueLinksFor, taskLabel } from "./delivery";

describe("taskLabel", () => {
  it("traduit les tâches, sous-tâches et groupes", () => {
    expect(taskLabel("Tâche 3", "en")).toBe("Task 3");
    expect(taskLabel("Tâche 4b", "en")).toBe("Task 4b");
    expect(taskLabel("Tâches 1-2", "en")).toBe("Tasks 1-2");
    expect(taskLabel("Tâche 4b", "fr")).toBe("Tâche 4b");
  });
});

describe("issueLinksFor", () => {
  it("relie une sous-tâche à son issue de suivi", () => {
    expect(issueLinksFor("1e-2d", "Tâche 4b")).toEqual([
      { label: "Issue #108", href: "https://github.com/VoiD911/ask-my-cv/issues/108" },
    ]);
  });

  it("ignore les étapes hors tâche", () => {
    expect(issueLinksFor("1e-2d", "Hors tâche")).toEqual([]);
  });
});
