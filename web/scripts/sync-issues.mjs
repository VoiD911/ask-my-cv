// Snapshot des liens vers les issues historiques pour l'export statique.
// À relancer après une modification du journal ou des issues :
//   npm --prefix web run history:sync
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const repository = "VoiD911/ask-my-cv";
const root = resolve(import.meta.dirname, "../..");
const archive = JSON.parse(readFileSync(resolve(root, "docs/journal/index.json"), "utf8"));
if (archive.version !== 1 || archive.repository !== repository) {
  throw new Error("Journal public incompatible");
}
const output = execFileSync(
  "gh",
  ["api", "--paginate", "--slurp", `repos/${repository}/issues?state=all&labels=historique&per_page=100`],
  { encoding: "utf8" },
);
const issues = JSON.parse(output).flat().filter((issue) => !issue.pull_request);
const byTitle = new Map();
for (const issue of issues) {
  if (byTitle.has(issue.title)) throw new Error(`Titre d'issue en double : ${issue.title}`);
  byTitle.set(issue.title, issue);
}

const links = {};
for (const plan of archive.plans) {
  for (const task of plan.tasks) {
    const match = /^Tâches? (\d+)(?:-(\d+))?$/.exec(task.label);
    if (!match) continue;
    const first = Number(match[1]);
    const last = Number(match[2] ?? match[1]);
    for (let number = first; number <= last; number++) {
      const title = `${plan.id} · Tâche ${number}`;
      const issue = byTitle.get(title);
      if (!issue || issue.state !== "closed") throw new Error(`Issue historique absente : ${title}`);
      links[title] = issue.number;
    }
  }
}
writeFileSync(
  resolve(root, "web/src/lib/issue-links.json"),
  `${JSON.stringify(Object.fromEntries(Object.entries(links).sort()), null, 2)}\n`,
);
process.stdout.write(`${Object.keys(links).length} liens vers les issues historiques\n`);
