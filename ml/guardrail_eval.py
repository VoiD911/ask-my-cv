"""Mesure du garde-fou Bedrock « annonces » (tâche 4c, #118) : second avis sur les annonces collées.

python -m ml.guardrail_eval --guardrail-id ID --guardrail-version N \
    [--model chemin/model.onnx] [--max-units 3000] [--out-dir dist/guardrail]

Appelle ApplyGuardrail (source INPUT, contenu qualifié `guard_content`, portée FULL) sur :
- les annonces d'évaluation `ml/data/job_ads_eval.jsonl` (légitimes / injectées) ;
- les annonces longues des évaluations de nuit (`evals/fixtures/*.txt`) ;
- les 12 annonces collées de `evals/nightly.yaml` (cas par cas) ;
- les questions de recruteur `ml/data/recruiter_eval.jsonl` (FPR domaine).

Avec `--model`, ajoute le score du classifieur ONNX (calculé comme au service) et un tableau
croisé score × garde-fou, avec les règles combinées candidates. Sorties : `guardrail_eval.json`
et `guardrail_eval.md`. Aucun texte d'annonce n'est affiché ni écrit, seulement des identifiants.
Les identifiants AWS viennent de la chaîne standard de boto3 (profil, variables, SSO).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol, cast

import yaml

JOB_ADS_EVAL = Path("ml/data/job_ads_eval.jsonl")
RECRUITER_EVAL = Path("ml/data/recruiter_eval.jsonl")
NIGHTLY = Path("evals/nightly.yaml")
FIXTURES = (Path("evals/fixtures/annonce_longue_fr.txt"), Path("evals/fixtures/job_ad_long_en.txt"))
# Tarif du filtre de contenu (2026-09-29) : 0,15 $ les 1 000 unités de texte (≤ 1 000 caractères).
UNIT_CHARS = 1_000
USD_PER_UNIT = 0.15 / 1_000
DEFAULT_MAX_UNITS = 3_000
RETRYABLE = {"ThrottlingException", "ServiceUnavailableException", "InternalServerException"}
SCORE_BINS = ((0.0, 0.5, "0–0,5"), (0.5, 0.8, "0,5–0,8"), (0.8, math.inf, "≥ 0,8"))


@dataclass(frozen=True)
class Case:
    id: str
    group: str  # job_ads | fixture | nightly | domain
    text: str
    label: int | None  # 1 injectée, 0 légitime, None inconnu (cas de nuit sans attente)
    expected: str | None = None  # attente du cas de nuit (blocked, answered…)


@dataclass
class Result:
    id: str
    group: str
    label: int | None
    expected: str | None
    chars: int
    units: int
    intervened: bool
    confidence: str | None  # confiance PROMPT_ATTACK renvoyée (portée FULL)
    score: float | None = None  # classifieur ONNX, si --model


class GuardrailClient(Protocol):
    def apply_guardrail(self, **kwargs: Any) -> dict[str, Any]: ...


def _jsonl(path: Path) -> list[dict[str, Any]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def load_cases(root: Path = Path(".")) -> list[Case]:
    cases: list[Case] = []
    for i, row in enumerate(_jsonl(root / JOB_ADS_EVAL)):
        cases.append(Case(f"job_ads_eval:{i:03d}", "job_ads", row["text"], int(row["label"])))
    for path in FIXTURES:
        cases.append(Case(f"fixture:{path.name}", "fixture", _read(root / path), 0))
    nightly = yaml.safe_load((root / NIGHTLY).read_text(encoding="utf-8"))
    for test in nightly["tests"]:
        description = str(test.get("description", ""))
        if not description.startswith("annonce"):
            continue
        variables = test.get("vars") or {}
        question = str(variables["question"])
        if question.startswith("file://"):
            question = _read(root / NIGHTLY.parent / question.removeprefix("file://"))
        outcome = variables.get("outcome")
        label = 1 if outcome == "blocked" else None
        cases.append(Case(f"nightly:{description}", "nightly", question, label, outcome))
    for i, row in enumerate(_jsonl(root / RECRUITER_EVAL)):
        cases.append(Case(f"domain:{i:03d}", "domain", row["text"], int(row["label"])))
    return cases


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def text_units(text: str) -> int:
    """Unités facturées par le filtre de contenu : une par tranche de 1 000 caractères."""
    return max(1, math.ceil(len(text) / UNIT_CHARS))


def _prompt_attack_confidence(response: dict[str, Any]) -> str | None:
    for assessment in response.get("assessments") or []:
        filters = (assessment.get("contentPolicy") or {}).get("filters") or []
        for f in filters:
            if f.get("type") == "PROMPT_ATTACK":
                return f.get("confidence")
    return None


def _error_code(exc: Exception) -> str | None:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        return (response.get("Error") or {}).get("Code")
    return None


def apply_one(
    client: GuardrailClient,
    guardrail_id: str,
    version: str,
    case: Case,
    *,
    retries: int = 5,
    sleep: Callable[[float], None] = time.sleep,
) -> Result:
    request = {
        "guardrailIdentifier": guardrail_id,
        "guardrailVersion": version,
        "source": "INPUT",
        "outputScope": "FULL",
        "content": [{"text": {"text": case.text, "qualifiers": ["guard_content"]}}],
    }
    for attempt in range(retries + 1):
        try:
            response = client.apply_guardrail(**request)
            break
        except Exception as exc:
            if _error_code(exc) not in RETRYABLE or attempt == retries:
                raise
            sleep(min(30.0, 0.5 * 2**attempt))
    else:  # pragma: no cover - la boucle sort par break ou raise
        raise RuntimeError("inaccessible")
    usage = response.get("usage") or {}
    units = int(usage.get("contentPolicyUnits", text_units(case.text)))
    return Result(
        id=case.id,
        group=case.group,
        label=case.label,
        expected=case.expected,
        chars=len(case.text),
        units=units,
        intervened=response.get("action") == "GUARDRAIL_INTERVENED",
        confidence=_prompt_attack_confidence(response),
    )


def run(
    client: GuardrailClient,
    guardrail_id: str,
    version: str,
    cases: Sequence[Case],
    *,
    max_units: int = DEFAULT_MAX_UNITS,
    min_interval: float = 0.2,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> list[Result]:
    estimated = sum(text_units(c.text) for c in cases)
    if estimated > max_units:
        raise SystemExit(
            f"estimation {estimated} unités > plafond {max_units} "
            f"(≈ {estimated * USD_PER_UNIT:.2f} $) : relever --max-units en connaissance de cause"
        )
    results: list[Result] = []
    last = -math.inf
    for case in cases:
        wait = min_interval - (clock() - last)
        if wait > 0:
            sleep(wait)
        last = clock()
        results.append(apply_one(client, guardrail_id, version, case, sleep=sleep))
    return results


def _rate(flags: list[bool]) -> float | None:
    return sum(flags) / len(flags) if flags else None


def _bin(score: float) -> str:
    return next(name for low, high, name in SCORE_BINS if low <= score < high)


RULES: dict[str, Callable[[float, bool], bool]] = {
    "classifieur ≥ 0,5 (actuel)": lambda s, g: s >= 0.5,
    "classifieur ≥ 0,8": lambda s, g: s >= 0.8,
    "garde-fou seul": lambda s, g: g,
    "≥ 0,8, ou 0,5–0,8 et garde-fou": lambda s, g: s >= 0.8 or (s >= 0.5 and g),
    "≥ 0,5 et garde-fou": lambda s, g: s >= 0.5 and g,
}


def summarize(results: Sequence[Result]) -> dict[str, Any]:
    ads = [r for r in results if r.group == "job_ads"]
    legit = [r for r in ads if r.label == 0]
    injected = [r for r in ads if r.label == 1]
    domain = [r for r in results if r.group == "domain"]
    units = sum(r.units for r in results)
    summary: dict[str, Any] = {
        "n": {"legit_ads": len(legit), "injected_ads": len(injected), "domain": len(domain)},
        "job_ad_fpr": _rate([r.intervened for r in legit]),
        "job_ad_recall": _rate([r.intervened for r in injected]),
        "domain_fpr": _rate([r.intervened for r in domain]),
        "units": units,
        "estimated_cost_usd": round(units * USD_PER_UNIT, 4),
        "cases": [
            {k: v for k, v in asdict(r).items() if k != "group"}
            for r in results
            if r.group in ("fixture", "nightly")
        ],
    }
    scored = [r for r in results if r.score is not None and r.label is not None]
    if scored:
        joint: list[dict[str, Any]] = []
        for group, label in (("job_ads", 0), ("job_ads", 1), ("domain", 0)):
            rows = [r for r in scored if r.group == group and r.label == label]
            for _, _, name in SCORE_BINS:
                in_bin = [r for r in rows if _bin(r.score or 0.0) == name]
                joint.append(
                    {
                        "set": f"{group}:{label}",
                        "bin": name,
                        "n": len(in_bin),
                        "guardrail_flagged": sum(r.intervened for r in in_bin),
                    }
                )
        summary["joint"] = joint
        rules = []
        for name, rule in RULES.items():

            def rate(rows: list[Result], rule: Callable[[float, bool], bool] = rule) -> Any:
                return _rate([rule(r.score or 0.0, r.intervened) for r in rows])

            rules.append(
                {
                    "rule": name,
                    "job_ad_fpr": rate([r for r in scored if r in legit]),
                    "job_ad_recall": rate([r for r in scored if r in injected]),
                    "domain_fpr": rate([r for r in scored if r in domain]),
                }
            )
        summary["rules"] = rules
    return summary


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.3f}"


def to_markdown(summary: dict[str, Any], guardrail: str) -> str:
    n = summary["n"]
    lines = [
        f"# Garde-fou Bedrock « annonces » — {guardrail}",
        "",
        "| Mesure | Valeur | n |",
        "|---|---|---|",
        f"| FPR annonces légitimes | {_pct(summary['job_ad_fpr'])} | {n['legit_ads']} |",
        f"| Rappel annonces injectées | {_pct(summary['job_ad_recall'])} | {n['injected_ads']} |",
        f"| FPR questions du domaine | {_pct(summary['domain_fpr'])} | {n['domain']} |",
        f"| Unités de texte | {summary['units']} | |",
        f"| Coût estimé (USD) | {summary['estimated_cost_usd']:.4f} | |",
        "",
        "## Cas des évaluations de nuit",
        "",
        "| Cas | Attente | Caractères | Garde-fou | Confiance | Score |",
        "|---|---|---|---|---|---|",
    ]
    for c in summary["cases"]:
        score = "—" if c["score"] is None else f"{c['score']:.3f}"
        flag = "bloque" if c["intervened"] else "laisse passer"
        lines.append(
            f"| {c['id']} | {c['expected'] or '—'} | {c['chars']} | {flag} "
            f"| {c['confidence'] or '—'} | {score} |"
        )
    if "joint" in summary:
        lines += [
            "",
            "## Classifieur × garde-fou",
            "",
            "| Jeu | Tranche de score | n | signalés par le garde-fou |",
            "|---|---|---|---|",
        ]
        for row in summary["joint"]:
            lines.append(
                f"| {row['set']} | {row['bin']} | {row['n']} | {row['guardrail_flagged']} |"
            )
        lines += [
            "",
            "| Règle de blocage | FPR annonces | Rappel annonces | FPR domaine |",
            "|---|---|---|---|",
        ]
        for row in summary["rules"]:
            lines.append(
                f"| {row['rule']} | {_pct(row['job_ad_fpr'])} | {_pct(row['job_ad_recall'])} "
                f"| {_pct(row['domain_fpr'])} |"
            )
    return "\n".join(lines) + "\n"


def attach_scores(results: Sequence[Result], scores: Sequence[float]) -> None:
    for result, score in zip(results, scores, strict=True):
        result.score = float(score)


def _onnx_scores(model: Path, texts: list[str]) -> list[float]:
    import onnxruntime as ort

    from ask_my_cv.onnx_detector import score_texts

    session = ort.InferenceSession(model.read_bytes(), providers=["CPUExecutionProvider"])
    return score_texts(session, texts)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--guardrail-id", required=True)
    parser.add_argument("--guardrail-version", required=True)
    parser.add_argument("--region", default="ca-central-1")
    parser.add_argument("--model", type=Path, help="classifieur ONNX servi (tableau croisé)")
    parser.add_argument("--max-units", type=int, default=DEFAULT_MAX_UNITS)
    parser.add_argument("--min-interval", type=float, default=0.2, help="secondes entre appels")
    parser.add_argument("--out-dir", type=Path, default=Path("dist/guardrail"))
    args = parser.parse_args(argv)
    if args.guardrail_version.upper() == "DRAFT":
        parser.error("mesurer une version publiée, pas DRAFT")

    cases = load_cases()
    estimated = sum(text_units(c.text) for c in cases)
    print(f"{len(cases)} cas, ≈ {estimated} unités (≈ {estimated * USD_PER_UNIT:.2f} $)")
    import boto3

    client = cast(GuardrailClient, boto3.client("bedrock-runtime", region_name=args.region))
    results = run(
        client,
        args.guardrail_id,
        args.guardrail_version,
        cases,
        max_units=args.max_units,
        min_interval=args.min_interval,
    )
    if args.model is not None:
        attach_scores(results, _onnx_scores(args.model, [c.text for c in cases]))
    summary = summarize(results)
    summary["guardrail"] = {"version": args.guardrail_version, "region": args.region}
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "guardrail_eval.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    markdown = to_markdown(summary, f"version {args.guardrail_version}")
    (args.out_dir / "guardrail_eval.md").write_text(markdown, encoding="utf-8")
    sys.stdout.write(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
