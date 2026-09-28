import archive from "./delivery-archive.json";
import issueNumbers from "./issue-links.json";

export type DeliveryEvent = {
  type: "implementation" | "review" | "fix" | "other";
  date: string;
  agent_type: string;
  model: string;
  description: string;
  summary: string;
  verdict: string | null;
  commits: string[];
  links: string[];
};

export type DeliveryTask = { label: string; events: DeliveryEvent[] };
export type DeliveryPlan = {
  id: string;
  title: string;
  goal: string;
  plan_doc: string;
  journal: string;
  tasks: DeliveryTask[];
};

const REPOSITORY = "VoiD911/ask-my-cv";
const BASE = `https://github.com/${REPOSITORY}`;

if (archive.version !== 1 || archive.repository !== REPOSITORY) {
  throw new Error("Version du journal public non reconnue");
}

export const deliveryPlans = archive.plans as DeliveryPlan[];

export function documentUrl(path: string): string {
  if (!/^docs\/(?:spec|plans|journal)\/[\w.-]+\.(?:md|json)$/.test(path)) {
    throw new Error("Lien de document inattendu");
  }
  return `${BASE}/blob/main/${path}`;
}

export function commitUrl(sha: string): string {
  if (!/^[0-9a-f]{40}$/.test(sha)) throw new Error("SHA inattendu");
  return `${BASE}/commit/${sha}`;
}

export function issueLinksFor(plan: string, task: string): { label: string; href: string }[] {
  const match = /^Tâches? (\d+)(?:-(\d+))?$/.exec(task);
  if (!match) return [];
  const first = Number(match[1]);
  const last = Number(match[2] ?? match[1]);
  const links: { label: string; href: string }[] = [];
  for (let number = first; number <= last; number++) {
    const key = `${plan} · Tâche ${number}`;
    const id = (issueNumbers as Record<string, number>)[key];
    if (typeof id === "number" && Number.isInteger(id) && id > 0) {
      links.push({ label: `Issue #${id}`, href: `${BASE}/issues/${id}` });
    }
  }
  return links;
}

export function eventLinks(links: string[]): string[] {
  return links.filter((url) =>
    /^https:\/\/github\.com\/VoiD911\/ask-my-cv\/(?:pull|issues)\/\d+$/.test(url),
  );
}

export function formatDate(iso: string): string {
  return new Intl.DateTimeFormat("fr-CA", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
  }).format(new Date(iso));
}
