"""CLI du journal public : `python -m tools.devlog render …`.

Lit les sous-agents, les plans et la table de correspondance des SHA, rend le
journal en mémoire (`render.render`), puis écrit les fichiers dans `--out` et
le rapport local (suspects, agents non rattachés) dans `--report`, qui ne doit
jamais se trouver dans le dépôt.

Codes de sortie : 0 succès ; 1 erreur d'usage ou de configuration ; 2 secret
détecté (aucun fichier écrit, la valeur n'est jamais affichée).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from tools.devlog.extract import load_agents, load_commit_map, load_published_shas
from tools.devlog.redact import ConfigError, SecretDetected, load_config
from tools.devlog.render import load_plan_docs, render

_DEFAULT_REPORT = Path.home() / ".claude" / "devlog-private" / "render-report.json"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m tools.devlog")
    commands = parser.add_subparsers(dest="command", required=True)
    cmd = commands.add_parser("render", help="rend le journal public et index.json")
    cmd.add_argument("--subagents", type=Path, required=True)
    cmd.add_argument("--commit-map", type=Path, required=True)
    cmd.add_argument("--plans-dir", type=Path, required=True)
    cmd.add_argument("--out", type=Path, required=True)
    cmd.add_argument("--repo", type=Path, default=Path("."))
    cmd.add_argument("--assignments", type=Path, default=None)
    cmd.add_argument("--github-flow-plans", default="")
    cmd.add_argument("--report", type=Path, default=_DEFAULT_REPORT)
    return parser


def _load_assignments(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in data.items()
    ):
        raise ValueError(f"{path.name} : objet JSON {{identifiant d'agent: plan}} attendu")
    return data


def _render_command(args: argparse.Namespace) -> int:
    repo = args.repo.resolve()
    report_path = args.report.expanduser().resolve()
    if report_path.is_relative_to(repo):
        print(
            f"refusé : le rapport local ({report_path}) ne doit pas se trouver dans le dépôt",
            file=sys.stderr,
        )
        return 1
    try:
        config = load_config(require_account_ids=True)
        assignments = _load_assignments(args.assignments)
        agents = load_agents(args.subagents)
        plan_docs = load_plan_docs(args.plans_dir)
        commit_map = load_commit_map(args.commit_map)
        published = load_published_shas(repo)
    except (ConfigError, ValueError, OSError, RuntimeError) as exc:
        print(f"erreur : {exc}", file=sys.stderr)
        return 1
    flow = frozenset(p.strip() for p in args.github_flow_plans.split(",") if p.strip())
    try:
        result = render(
            agents,
            plan_docs,
            commit_map,
            published,
            config,
            assignments=assignments,
            github_flow_plans=flow,
        )
    except SecretDetected as exc:
        # Le message de SecretDetected donne le type et la position, jamais la valeur.
        print(f"secret détecté, rendu annulé, aucun fichier écrit : {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"erreur : {exc}", file=sys.stderr)
        return 1

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    for name, content in result.files.items():
        (out / name).write_text(content, encoding="utf-8", newline="\n")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "unknown": [asdict(u) for u in result.unknown],
        "suspects": [asdict(s) for s in result.suspects],
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    index = json.loads(result.files["index.json"])
    counts = Counter[str]()
    for plan in index["plans"]:
        counts[plan["id"]] = sum(len(task["events"]) for task in plan["tasks"])
    for plan_id, count in counts.items():
        print(f"{plan_id} : {count} agent(s)")
    print(f"non rattachés : {len(result.unknown)}")
    print(f"suspects : {len(result.suspects)} (détail dans {report_path})")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "render":
        return _render_command(args)
    return 1  # pragma: no cover - sous-commande obligatoire


if __name__ == "__main__":
    raise SystemExit(main())
