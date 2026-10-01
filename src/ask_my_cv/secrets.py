from __future__ import annotations

import os
from collections.abc import Callable, MutableMapping
from typing import Any

from ask_my_cv.settings import ConfigError

SECRET_NAMES = ("VISITOR_SALT", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")
# chargés s'ils existent sous le préfixe, sans erreur s'ils sont absents
OPTIONAL_SECRET_NAMES = ("EVAL_TOKEN", "INTERNAL_TOKEN")


def load_ssm_secrets(prefix: str, client: Any) -> dict[str, str]:
    """Lit les secrets connus (obligatoires ou facultatifs) sous `prefix` ; ignore les autres."""
    values: dict[str, str] = {}
    paginator = client.get_paginator("get_parameters_by_path")
    for page in paginator.paginate(Path=prefix.rstrip("/"), WithDecryption=True):
        for parameter in page.get("Parameters", []):
            name = parameter["Name"].rsplit("/", 1)[-1]
            if name in SECRET_NAMES or name in OPTIONAL_SECRET_NAMES:
                values[name] = parameter["Value"]
    return values


def _ssm_client() -> Any:
    import boto3
    from botocore.config import Config

    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "ca-central-1"
    return boto3.client(
        "ssm",
        region_name=region,
        config=Config(
            connect_timeout=2,
            read_timeout=3,
            retries={"total_max_attempts": 2, "mode": "standard"},
        ),
    )


def apply_ssm_secrets(
    environ: MutableMapping[str, str] | None = None,
    client_factory: Callable[[], Any] = _ssm_client,
) -> None:
    """Si `ASK_SSM_PREFIX` est défini, complète l'environnement (une valeur déjà définie gagne).

    Une erreur SSM empêche le démarrage : mieux vaut aucune API qu'une API sans secret.
    De même, si un secret attendu n'est ni dans SSM ni déjà dans l'environnement, on
    échoue explicitement plutôt que de démarrer avec un secret manquant. Les secrets
    facultatifs (`OPTIONAL_SECRET_NAMES`) sont chargés s'ils existent, sans contrôle.
    """
    env = os.environ if environ is None else environ
    prefix = env.get("ASK_SSM_PREFIX")
    if not prefix:
        return
    values = load_ssm_secrets(prefix, client_factory())
    for name, value in values.items():
        env.setdefault(name, value)
    missing = [name for name in SECRET_NAMES if not env.get(name)]
    if missing:
        raise ConfigError(f"SSM {prefix} : paramètres absents : {', '.join(missing)}")
