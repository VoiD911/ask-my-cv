from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_redact_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Isole `load_config()` de tout fichier ou environnement réel du poste.

    Les tests de `redact.py` passent presque toujours une `RedactConfig`
    explicite construite avec des valeurs fictives ; les quelques appels sans
    configuration (motifs génériques) doivent malgré tout ne jamais lire
    `~/.claude/devlog-private/redact.json` ni des variables d'environnement
    laissées par le poste de développement.
    """
    for name in (
        "DEVLOG_REDACT_AWS_ACCOUNT_IDS",
        "DEVLOG_REDACT_EMAIL_ALLOWLIST",
        "DEVLOG_REDACT_LOCAL_USERNAMES",
        "DEVLOG_REDACT_PATH_ROOTS",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DEVLOG_REDACT_CONFIG_PATH", str(tmp_path / "absent-redact.json"))
