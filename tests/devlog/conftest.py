from pathlib import Path

import pytest

from tools.devlog import redact as redact_module


@pytest.fixture(autouse=True)
def isolated_redact_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Isole `load_config()` de tout fichier ou environnement réel du poste.

    Les tests de `redact.py` passent presque toujours une `RedactConfig`
    explicite construite avec des valeurs fictives (jamais les vraies) ;
    quand un test veut exercer le chemin par défaut de `load_config()`, ce
    chemin est redirigé ici vers un fichier absent dans `tmp_path`, jamais
    vers `~/.claude/devlog-private/redact.json` du poste de développement.
    Les tests qui exercent `DEVLOG_REDACT_CONFIG_PATH` explicitement le
    redéfinissent eux-mêmes.
    """
    for name in (
        "DEVLOG_REDACT_AWS_ACCOUNT_IDS",
        "DEVLOG_REDACT_EMAIL_ALLOWLIST",
        "DEVLOG_REDACT_LOCAL_USERNAMES",
        "DEVLOG_REDACT_PATH_ROOTS",
        "DEVLOG_REDACT_SECRET_ALLOWLIST",
        "DEVLOG_REDACT_CONFIG_PATH",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        redact_module, "_DEFAULT_CONFIG_PATH", tmp_path / "absent-default-redact.json"
    )
