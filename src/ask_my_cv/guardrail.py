"""Second avis du garde-fou Bedrock « annonces » sur les annonces collées (tâche 4c, #118).

Règle décidée le 2026-09-29 sur la mesure `ml.guardrail_eval` (160 annonces légitimes, 80
injectées, 50 questions du domaine) : une annonce est bloquée si le classifieur v1.4.0 donne
un score ≥ 0,5 OU si le garde-fou intervient. Mesuré : 13 % d'annonces légitimes bloquées,
71 % des injections arrêtées, aucun faux positif sur les questions du domaine. Les questions
courtes gardent le classifieur seul.

Échec isolé du garde-fou (délai dépassé, erreur, limitation) : on garde la décision du
classifieur (échec OUVERT). Le classifieur reste la porte principale et a déjà laissé passer le
texte ; échouer fermé à chaque incident rendrait les annonces indisponibles dès que Bedrock
ralentit. Mais un échec ouvert répété serait un contournement (saturer le quota Bedrock, ou
allonger l'annonce jusqu'au délai) : un disjoncteur (`GuardrailBreaker`) passe en échec FERMÉ
pour les annonces après N échecs consécutifs (tout le processus) ou M échecs d'un même visiteur,
pendant une période de refroidissement, avec un message « indisponible » distinct du blocage
d'injection. Chaque appel est tracé (`xops.guardrail`, `xops.guardrail_ms`) et journalisé
(ligne `guardrail_metrics <statut> <ms>`, filtres de métrique et alarme CloudWatch).

Limite connue : les textes de moins de `AD_MIN_CHARS` caractères (après `fold_format`) ne
passent pas par le garde-fou. Une injection courte ne rencontre que le classifieur et le
prompt (données encadrées, jamais instructions) ; les 71 % de rappel ne valent que pour les
annonces d'au moins 400 caractères, format de la mesure.
"""

from __future__ import annotations

import asyncio
import logging
import math
import threading
from dataclasses import dataclass
from typing import Any, Literal, Protocol

GuardrailStatus = Literal["pass", "block", "error", "skipped", "unavailable"]

# Ligne de métrique (filtres CloudWatch, infra/prod/observability.tf) : « guardrail_metrics
# <statut> <ms> ». Jamais de texte soumis.
metrics_logger = logging.getLogger("ask_my_cv.guardrail.metrics")
metrics_logger.setLevel(logging.INFO)
if not metrics_logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    metrics_logger.addHandler(_handler)


def log_metric(status: GuardrailStatus, elapsed_ms: float) -> None:
    metrics_logger.info("guardrail_metrics %s %d", status, round(elapsed_ms))


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


class GuardrailBreaker:
    """Disjoncteur du garde-fou, partagé par le processus (thread-safe).

    Ouvert (annonces refusées) pendant `cooldown_s` après `max_failures` échecs consécutifs
    tous visiteurs confondus, ou après `max_visitor_failures` échecs d'un même visiteur dans
    la fenêtre `cooldown_s`. Un succès remet le compteur global à zéro ; après le
    refroidissement, un nouvel échec rouvre aussitôt (demi-ouverture).
    """

    MAX_VISITORS = 10_000  # borne mémoire : les plus anciens sont oubliés au-delà

    def __init__(
        self, max_failures: int = 5, max_visitor_failures: int = 3, cooldown_s: float = 60.0
    ) -> None:
        self.max_failures = max_failures
        self.max_visitor_failures = max_visitor_failures
        self.cooldown_s = cooldown_s
        self._consecutive = 0
        self._open_until = 0.0
        self._visitors: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allows(self, visitor: str, now: float) -> bool:
        with self._lock:
            if now < self._open_until:
                return False
            recent = self._recent(visitor, now)
            return len(recent) < self.max_visitor_failures

    def success(self) -> None:
        with self._lock:
            self._consecutive = 0

    def failure(self, visitor: str, now: float) -> None:
        with self._lock:
            self._consecutive += 1
            if self._consecutive >= self.max_failures:
                self._open_until = now + self.cooldown_s
            recent = self._recent(visitor, now)
            recent.append(now)
            self._visitors[visitor] = recent
            if len(self._visitors) > self.MAX_VISITORS:
                del self._visitors[next(iter(self._visitors))]

    def _recent(self, visitor: str, now: float) -> list[float]:
        return [t for t in self._visitors.get(visitor, []) if now - t < self.cooldown_s]
