// Snapshot des liens vers les issues des tâches pour l'export statique : issue
// historique (`<plan> · Tâche N`, plans antérieurs au flux GitHub) ou, à
// défaut, issue de suivi réelle (`<plan> · tâche N[a-z] · …`, plans en flux GitHub).
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
  ["api", "--paginate", "--slurp", `repos/${repository}/issues?state=all&per_page=100`],
  { encoding: "utf8" },
);
const issues = JSON.parse(output).flat().filter((issue) => !issue.pull_request);
const isHistorical = (issue) => issue.labels.some((label) => label.name === "historique");
const byTitle = new Map();
const tracking = new Map();
for (const issue of issues) {
  if (isHistorical(issue)) {
    if (byTitle.has(issue.title)) throw new Error(`Titre d'issue en double : ${issue.title}`);
    byTitle.set(issue.title, issue);
    continue;
  }
  const match = /^(\d[a-z](?:-bis|-\d[a-z]?)?) · tâche (\d+[a-z]?) · /i.exec(issue.title);
  if (!match) continue;
  const key = `${match[1]} · Tâche ${match[2].toLowerCase()}`;
  if (tracking.has(key)) throw new Error(`Issue de suivi en double : ${key}`);
  tracking.set(key, issue);
}

const links = {};
for (const plan of archive.plans) {
  for (const task of plan.tasks) {
    const match = /^Tâches? (\d+)(?:([a-z])|-(\d+))?$/.exec(task.label);
    if (!match) continue;
    const first = Number(match[1]);
    const last = Number(match[3] ?? match[1]);
    for (let number = first; number <= last; number++) {
      const title = `${plan.id} · Tâche ${number}${match[2] ?? ""}`;
      const historical = byTitle.get(title);
      const issue = historical ?? tracking.get(title);
      if (!issue || (historical && issue.state !== "closed")) {
        throw new Error(`Issue de tâche absente : ${title}`);
      }
      links[title] = issue.number;
    }
  }
}
writeFileSync(
  resolve(root, "web/src/lib/issue-links.json"),
  `${JSON.stringify(Object.fromEntries(Object.entries(links).sort()), null, 2)}\n`,
);
process.stdout.write(`${Object.keys(links).length} liens vers les issues de tâches\n`);
