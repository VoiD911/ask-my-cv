"""Second avis du garde-fou Bedrock « annonces » sur les annonces collées (tâche 4c, #118).

Règle décidée le 2026-09-29 sur la mesure `ml.guardrail_eval` (160 annonces légitimes, 80
injectées, 50 questions du domaine) : une annonce est bloquée si le classifieur v1.4.0 donne
un score ≥ 0,5 OU si le garde-fou intervient. Mesuré : 13 % d'annonces légitimes bloquées,
71 % des injections arrêtées, aucun faux positif sur les questions du domaine. Les questions
courtes gardent le classifieur seul.

Échec du garde-fou (délai dépassé, erreur) : on garde la décision du classifieur (échec
OUVERT). Le classifieur reste la porte principale et a déjà laissé passer le texte ; le
garde-fou n'est qu'un second avis payant. Échouer fermé rendrait le service indisponible pour
toute annonce dès que Bedrock ralentit, pour un gain limité (le prompt et le garde-fou de sortie
restent actifs). L'échec est tracé (`xops.guardrail = error`) et journalisé
(`guardrail_status=error`, filtre de métrique CloudWatch) pour être vu et corrigé.
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from typing import Any, Literal, Protocol

GuardrailStatus = Literal["pass", "block", "error", "skipped"]

# Seuil « annonce » : les 240 annonces mesurées font de 447 à 7 527 caractères (aucune sous
# 400), les 50 questions du domaine au plus 54. À 400, la mesure s'applique à toutes les
# annonces évaluées ; les questions, même longues, restent loin sous le seuil. Les annonces
# courtes (< 400, ex. les cas manuscrits des évaluations de nuit) gardent le classifieur seul,
# faute de mesure du garde-fou sur ce format.
AD_MIN_CHARS = 400

# Tarif du filtre de contenu (2026-09-29) : 0,15 $ les 1 000 unités de texte (≤ 1 000 caractères).
UNIT_CHARS = 1_000
USD_PER_UNIT = 0.15 / 1_000

# Poste de dépense du registre (même plafond journalier que les LLM).
GUARDRAIL_PROVIDER_ID = "bedrock:guardrail-annonces"


def text_units(text: str) -> int:
    """Unités facturées par le filtre de contenu : une par tranche de 1 000 caractères."""
    return max(1, math.ceil(len(text) / UNIT_CHARS))


def is_ad_like(text: str, min_chars: int = AD_MIN_CHARS) -> bool:
    return len(text) >= min_chars


def guardrail_request(guardrail_id: str, version: str, text: str) -> dict[str, Any]:
    """Requête ApplyGuardrail : entrée, contenu qualifié `guard_content`, portée FULL.

    Forme partagée avec la mesure (`ml.guardrail_eval`) : le service appelle le garde-fou
    exactement comme il a été évalué.
    """
    return {
        "guardrailIdentifier": guardrail_id,
        "guardrailVersion": version,
        "source": "INPUT",
        "outputScope": "FULL",
        "content": [{"text": {"text": text, "qualifiers": ["guard_content"]}}],
    }


@dataclass(frozen=True)
class GuardrailResult:
    intervened: bool
    units: int


class GuardrailChecker(Protocol):
    async def check(self, text: str) -> GuardrailResult: ...


class FakeGuardrail:
    """Garde-fou factice (tests, développement local) : réponse fixe, délai ou erreur."""

    def __init__(
        self, intervene: bool = False, delay_s: float = 0.0, error: Exception | None = None
    ) -> None:
        self.intervene = intervene
        self.delay_s = delay_s
        self.error = error
        self.calls = 0

    async def check(self, text: str) -> GuardrailResult:
        self.calls += 1
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        if self.error is not None:
            raise self.error
        return GuardrailResult(intervened=self.intervene, units=text_units(text))
