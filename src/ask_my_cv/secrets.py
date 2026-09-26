from __future__ import annotations

import os
from collections.abc import Callable, MutableMapping
from typing import Any

SECRET_NAMES = ("VISITOR_SALT", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")


def load_ssm_secrets(prefix: str, client: Any) -> dict[str, str]:
    """Lit les secrets connus sous `prefix` (SecureString déchiffrés) ; ignore les autres."""
    values: dict[str, str] = {}
    paginator = client.get_paginator("get_parameters_by_path")
    for page in paginator.paginate(Path=prefix.rstrip("/"), WithDecryption=True):
        for parameter in page.get("Parameters", []):
            name = parameter["Name"].rsplit("/", 1)[-1]
            if name in SECRET_NAMES:
                values[name] = parameter["Value"]
    return values


def _ssm_client() -> Any:
    import boto3
    from botocore.config import Config

    return boto3.client(
        "ssm",
        region_name=os.environ.get("AWS_REGION", "ca-central-1"),
        config=Config(connect_timeout=2, read_timeout=3, retries={"max_attempts": 2}),
    )


def apply_ssm_secrets(
    environ: MutableMapping[str, str] | None = None,
    client_factory: Callable[[], Any] = _ssm_client,
) -> None:
    """Si `ASK_SSM_PREFIX` est défini, complète l'environnement (une valeur déjà définie gagne).

    Une erreur SSM empêche le démarrage : mieux vaut aucune API qu'une API sans secret.
    """
    env = os.environ if environ is None else environ
    prefix = env.get("ASK_SSM_PREFIX")
    if not prefix:
        return
    for name, value in load_ssm_secrets(prefix, client_factory()).items():
        env.setdefault(name, value)
