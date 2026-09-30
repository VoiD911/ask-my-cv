"""Diagnostic : réponses brutes du vrai modèle à une annonce, avant le garde-fou de sortie.

En production, l'annonce anglaise de la rediffusion (web/scripts/record-replays.mjs, cas
`en-ad`) est retirée (« elle ne s'appuyait pas sur le CV ») : le garde-fou n'expose pas le
texte retiré. Ce script rejoue la même chaîne (embedding, recherche, rendu du gabarit,
appel du modèle) pour un ou plusieurs gabarits et affiche la réponse brute et le verdict.

Lecture seule côté données (DynamoDB en lecture, aucun registre de coût écrit). Nécessite
des identifiants AWS avec accès Bedrock et à la table des extraits :

    ASK_SETTINGS=settings.aws.yaml uv run python scripts/diagnose_citations.py \\
        --prompt prompts/answer@v7.md --prompt prompts/answer@v8.md --runs 3

Coût indicatif : quelques centimes (Haiku, ~2 000 jetons d'entrée par appel).
"""

from __future__ import annotations

import argparse
import asyncio
import secrets
from pathlib import Path

from ask_my_cv.container import build_embedder, build_provider, build_store
from ask_my_cv.language import detect_language
from ask_my_cv.output_guard import check_output, normalize_refusal
from ask_my_cv.prompting import load_template
from ask_my_cv.settings import load_settings

JOB_AD_EN = """AI Solutions Architect (full-time, Toronto, hybrid)
Our team builds generative assistants for financial services clients.
Responsibilities: design RAG solution architectures on AWS, lead a team of developers,
set up continuous evaluation and LLM guardrails, support clients from pre-sales to production.
Requirements: 10 years of software architecture experience, strong AWS and Python skills,
background in process automation (RPA), fluent English and French."""


async def diagnose(prompts: list[Path], runs: int, text: str) -> None:
    settings = load_settings()
    model = next(m for m in settings.models if m.id == settings.default_model)
    provider = build_provider(model, settings)
    [vector] = await build_embedder(settings).embed([text])
    hits = await build_store(settings).search(vector, settings.top_k)
    language = detect_language(text)
    print(f"modèle={model.id} langue={language} extraits={len(hits)}")
    for path in prompts:
        template = load_template(path)
        for run in range(1, runs + 1):
            canary = secrets.token_hex(8)
            system, user = template.render(text, hits, canary, language=language)
            answer = "".join([c async for c in provider.stream(system, user) if isinstance(c, str)])
            verdict = check_output(
                normalize_refusal(answer),
                canary=canary,
                allowed_contacts=set(settings.allowed_contacts),
                n_sources=len(hits),
            )
            status = "ok" if verdict.ok else f"RETIRÉE ({verdict.reason})"
            print(f"\n--- {template.name}@{template.version} essai {run} : {status}\n{answer}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Réponses brutes du modèle à une annonce.")
    parser.add_argument("--prompt", action="append", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--text-file", type=Path, help="annonce à tester (défaut : en-ad)")
    args = parser.parse_args()
    text = args.text_file.read_text(encoding="utf-8") if args.text_file else JOB_AD_EN
    asyncio.run(diagnose(args.prompt, args.runs, text))


if __name__ == "__main__":
    main()
