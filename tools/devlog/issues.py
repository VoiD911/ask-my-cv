"""Prepare historical issues; GitHub writes require an explicit --apply.

Only the public journal index is consumed, never private conversation logs.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess  # noqa: S404
from datetime import date
from pathlib import Path
from typing import Any

from tools.devlog.redact import RedactConfig, assert_no_secret, load_config, redact
from tools.devlog.render import REPOSITORY

_TASK = re.compile(r"^Tâches? (\d+)(?:-(\d+))?$")
_PLAN = re.compile(r"^\d[a-z](?:-bis|-\d[a-z]?)?$")
_SHA = re.compile(r"^[0-9a-f]{40}$")


def build_issues(
    index: dict[str, Any],
    config: RedactConfig,
    *,
    reconstructed: date,
    skip_plans: frozenset[str] = frozenset(),
) -> list[dict[str, Any]]:
    """One issue per numbered task, merging overlapping task groups.

    Final reviews and unclassified work remain in the journal. Grouped reports
    are identified as shared evidence rather than attributed to one task alone.
    Plans in `skip_plans` (run with real GitHub issues and PRs) get none.
    """
    if index.get("version") != 1 or index.get("repository") != REPOSITORY:
        raise ValueError("unsupported journal version or repository")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for plan in index["plans"]:
        plan_id = plan["id"]
        if not _PLAN.fullmatch(plan_id):
            raise ValueError("invalid plan identifier")
        if plan_id in skip_plans:
            continue
        grouped: dict[int, list[tuple[str, dict[str, Any]]]] = {}
        for task in plan["tasks"]:
            match = _TASK.fullmatch(task["label"])
            if match is None:
                continue
            first, last = int(match[1]), int(match[2] or match[1])
            if not 0 <= first <= last <= 1000:
                raise ValueError("invalid task range")
            for number in range(first, last + 1):
                grouped.setdefault(number, []).extend(
                    (task["label"], event) for event in task["events"]
                )
        for number, events in sorted(grouped.items()):
            if not events:
                continue
            title = f"{plan_id} · Tâche {number}"
            if title in seen:
                raise ValueError("duplicate plan/task")
            seen.add(title)
            dates = sorted({event["date"] for _, event in events})
            base = f"https://github.com/{REPOSITORY}/blob/main"
            # Paths in an input index are not trusted to define arbitrary links.
            plan_doc = plan["plan_doc"]
            if not re.fullmatch(r"docs/plans/[\w.-]+\.md", plan_doc):
                raise ValueError("invalid plan document path")
            lines = [
                f"Issue reconstituée le {reconstructed.isoformat()} depuis le journal "
                f"de développement (date réelle : {dates[0]} à {dates[-1]}).",
                "",
                f"[Plan]({base}/{plan_doc}) · [Journal]({base}/docs/journal/{plan_id}.md)",
                "",
                "## Rapports et revues",
                "",
            ]
            commits: set[str] = set()
            for label, event in events:
                description = " ".join(event["description"].split())
                verdict = event.get("verdict")
                suffix = f" — verdict : {verdict}" if verdict else ""
                lines.append(
                    f"- {event['date']} · {event['type']} · {description}{suffix}"
                    f" (source : {label})."
                )
                if event.get("summary"):
                    summary = " ".join(event["summary"].split())
                    lines.append(f"  Résumé (extrait du rapport) : {summary}")
                for sha in event["commits"]:
                    if not _SHA.fullmatch(sha):
                        raise ValueError("invalid commit SHA")
                    commits.add(sha)
            lines += ["", "Les rapports complets et les groupes de tâches sont dans le journal."]
            if commits:
                lines += ["", "## Commits cités", ""]
                lines.extend(
                    f"- [{sha[:7]}](https://github.com/{REPOSITORY}/commit/{sha})"
                    for sha in sorted(commits)
                )
            body = redact("\n".join(lines) + "\n", config)
            assert_no_secret(body)
            result.append(
                {
                    "title": title,
                    "body": body,
                    "labels": ["historique", f"plan:{plan_id}"],
                    "state": "closed",
                }
            )
    return result


def _gh(*args: str, payload: dict[str, Any] | None = None) -> str:
    command = ["gh", *args]
    if payload is not None:
        command += ["--input", "-"]
    completed = subprocess.run(  # noqa: S603 -- argument list, no shell
        command,
        input=json.dumps(payload) if payload is not None else None,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        # GitHub errors can echo the request body: do not expose it.
        raise RuntimeError("GitHub operation failed; rerun after checking access")
    return completed.stdout


def apply_issues(issues: list[dict[str, Any]]) -> None:
    """Resume partial runs by exact title, including already closed issues.

    GitHub cannot create an issue directly closed; a successful create is
    immediately followed by a close. A failed close is retried on the next run.
    """
    pages = json.loads(
        _gh("api", "--paginate", "--slurp", f"repos/{REPOSITORY}/issues?state=all&per_page=100")
    )
    existing = {
        issue["title"]: issue for page in pages for issue in page if "pull_request" not in issue
    }
    for label in sorted({label for issue in issues for label in issue["labels"]}):
        _gh("label", "create", label, "--repo", REPOSITORY, "--force")
    for issue in issues:
        current = existing.get(issue["title"])
        if current is None:
            current = json.loads(
                _gh(
                    "api",
                    f"repos/{REPOSITORY}/issues",
                    "--method",
                    "POST",
                    payload={key: issue[key] for key in ("title", "body", "labels")},
                )
            )
            existing[issue["title"]] = current
        if current["state"] != "closed":
            _gh(
                "api",
                f"repos/{REPOSITORY}/issues/{current['number']}",
                "--method",
                "PATCH",
                payload={"state": "closed"},
            )
            current["state"] = "closed"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=Path("docs/journal/index.json"))
    parser.add_argument("--date", type=date.fromisoformat, default=date.today())
    parser.add_argument(
        "--github-flow-plans",
        default="",
        help="plans run with real GitHub issues and PRs: no historical issue",
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    issues = build_issues(
        json.loads(args.index.read_text(encoding="utf-8")),
        load_config(require_account_ids=True),
        reconstructed=args.date,
        skip_plans=frozenset(p.strip() for p in args.github_flow_plans.split(",") if p.strip()),
    )
    if args.apply:
        apply_issues(issues)
    else:
        print(json.dumps(issues, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
