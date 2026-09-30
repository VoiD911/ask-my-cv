"""Diagnostic : réponses brutes du vrai modèle à une annonce, avant le garde-fou de sortie.

En production, l'annonce anglaise de la rediffusion (web/scripts/record-replays.mjs, cas
`en-ad`) est retirée (« elle ne s'appuyait pas sur le CV ») : le garde-fou n'expose pas le
texte retiré. Ce script rejoue la même chaîne (embedding, recherche, rendu du gabarit,
appel du modèle) et affiche la réponse brute, la raison d'arrêt du modèle et deux
verdicts : celui du garde-fou tel qu'en production avant ce correctif (`brut`) et après
normalisation d'un refus traduit (`normalisé`).

`--language-line main` rend la consigne de langue telle qu'elle est servie en production
avant ce correctif (sans rappel des citations) ; `actuelle` (défaut) rend celle du dépôt.
Comparer les deux isole l'effet de la consigne de langue à gabarit égal.

Lecture seule côté données (DynamoDB en lecture, aucun registre de coût écrit). Nécessite
des identifiants AWS avec accès Bedrock et à la table des extraits :

    ASK_SETTINGS=settings.aws.yaml uv run python scripts/diagnose_citations.py \\
        --prompt prompts/answer@v7.md --language-line main --language-line actuelle --runs 3

Coût indicatif : quelques centimes (Haiku, ~2 000 jetons d'entrée par appel).
"""

from __future__ import annotations

import argparse
import asyncio
import secrets
from pathlib import Path

import ask_my_cv.prompting as prompting
from ask_my_cv.container import build_embedder, build_provider, build_store
from ask_my_cv.language import LABELS, Language, detect_language
from ask_my_cv.llm import TokenUsage
from ask_my_cv.output_guard import check_output, normalize_refusal
from ask_my_cv.prompting import load_template
from ask_my_cv.settings import load_settings

JOB_AD_EN = """AI Solutions Architect (full-time, Toronto, hybrid)
Our team builds generative assistants for financial services clients.
Responsibilities: design RAG solution architectures on AWS, lead a team of developers,
set up continuous evaluation and LLM guardrails, support clients from pre-sales to production.
Requirements: 10 years of software architecture experience, strong AWS and Python skills,
background in process automation (RPA), fluent English and French."""

CURRENT_LANGUAGE_LINE = prompting.language_line


def main_language_line(language: Language) -> str:
    """Consigne de langue servie en production avant ce correctif (main, #116)."""
    return (
        f"Langue de la réponse : {LABELS[language]} (réponds entièrement dans cette langue ; "
        "seule la phrase de refus reste en français, telle quelle)."
    )


LANGUAGE_LINES = {"actuelle": CURRENT_LANGUAGE_LINE, "main": main_language_line}


async def diagnose(prompts: list[Path], lines: list[str], runs: int, text: str) -> None:
    settings = load_settings()
    model = next(m for m in settings.models if m.id == settings.default_model)
    provider = build_provider(model, settings)
    [vector] = await build_embedder(settings).embed([text])
    hits = await build_store(settings).search(vector, settings.top_k)
    language = detect_language(text)
    print(f"modèle={model.id} langue={language} extraits={len(hits)}")
    for path in prompts:
        template = load_template(path)
        for line in lines:
            prompting.language_line = LANGUAGE_LINES[line]
            for run in range(1, runs + 1):
                canary = secrets.token_hex(8)
                system, user = template.render(text, hits, canary, language=language)
                parts: list[str] = []
                stop = ""
                async for chunk in provider.stream(system, user):
                    if isinstance(chunk, TokenUsage):
                        stop = chunk.stop_reason or ""
                    else:
                        parts.append(chunk)
                answer = "".join(parts)
                verdicts = []
                for label, text_checked in (
                    ("brut", answer),
                    ("normalisé", normalize_refusal(answer)),
                ):
                    v = check_output(
                        text_checked,
                        canary=canary,
                        allowed_contacts=set(settings.allowed_contacts),
                        n_sources=len(hits),
                    )
                    verdicts.append(f"{label}={'ok' if v.ok else f'RETIRÉE ({v.reason})'}")
                print(
                    f"\n--- {template.name}@{template.version} consigne={line} essai {run} : "
                    f"{', '.join(verdicts)}, arrêt={stop or '?'}\n{answer}"
                )
    prompting.language_line = CURRENT_LANGUAGE_LINE


def main() -> None:
    parser = argparse.ArgumentParser(description="Réponses brutes du modèle à une annonce.")
    parser.add_argument("--prompt", action="append", type=Path, required=True)
    parser.add_argument(
        "--language-line", action="append", choices=sorted(LANGUAGE_LINES), default=None
    )
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--text-file", type=Path, help="annonce à tester (défaut : en-ad)")
    args = parser.parse_args()
    text = args.text_file.read_text(encoding="utf-8") if args.text_file else JOB_AD_EN
    asyncio.run(diagnose(args.prompt, args.language_line or ["actuelle"], args.runs, text))


if __name__ == "__main__":
    main()
