"""Tests du masquage déterministe (`tools/devlog/redact.py`).

Toutes les valeurs utilisées ici sont fictives (comptes AWS, adresses,
utilisateurs, secrets). Les chaînes ressemblant à des secrets sont
construites par concaténation à l'exécution plutôt qu'écrites en clair, pour
ne jamais ressembler à une véritable fuite aux yeux d'un scanner comme
gitleaks. Ce module ne lit jamais le journal de session réel.
"""

from __future__ import annotations

import pytest

from tools.devlog.redact import RedactConfig, SecretDetected, assert_no_secret, redact

FAKE_ACCOUNT_ID = "123456789012"
OTHER_FAKE_ACCOUNT_ID = "210987654321"


def _config(**kwargs: object) -> RedactConfig:
    return RedactConfig(**kwargs)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# Identifiants de compte AWS
# --------------------------------------------------------------------------


def test_redact_masks_bare_configured_account_id() -> None:
    config = _config(aws_account_ids=frozenset({FAKE_ACCOUNT_ID}))
    text = f"Compte de déploiement : {FAKE_ACCOUNT_ID}."

    result = redact(text, config)

    assert FAKE_ACCOUNT_ID not in result
    assert "<compte-aws>" in result


def test_redact_masks_account_id_in_arn_without_config() -> None:
    # Motif générique (n'importe quel ARN à 12 chiffres) : aucune configuration requise.
    text = f"arn:aws:iam::{FAKE_ACCOUNT_ID}:role/deploy"

    result = redact(text)

    assert FAKE_ACCOUNT_ID not in result
    assert result == "arn:aws:iam::<compte-aws>:role/deploy"


def test_redact_masks_account_id_in_ecr_host_without_config() -> None:
    text = f"{FAKE_ACCOUNT_ID}.dkr.ecr.ca-central-1.amazonaws.com/ask-my-cv:latest"

    result = redact(text)

    assert FAKE_ACCOUNT_ID not in result
    assert result == "<compte-aws>.dkr.ecr.ca-central-1.amazonaws.com/ask-my-cv:latest"


@pytest.mark.parametrize(
    "template",
    [
        "compte {id}",
        "arn:aws:iam::{id}:role/deploy",
        "{id}.dkr.ecr.ca-central-1.amazonaws.com/repo:tag",
    ],
)
def test_redact_masks_configured_account_id_in_every_context(template: str) -> None:
    config = _config(aws_account_ids=frozenset({FAKE_ACCOUNT_ID}))
    text = template.format(id=FAKE_ACCOUNT_ID)

    result = redact(text, config)

    assert FAKE_ACCOUNT_ID not in result


def test_redact_does_not_mask_unrelated_account_id() -> None:
    config = _config(aws_account_ids=frozenset({FAKE_ACCOUNT_ID}))
    text = f"autre identifiant sans lien : {OTHER_FAKE_ACCOUNT_ID}"

    result = redact(text, config)

    assert OTHER_FAKE_ACCOUNT_ID in result


# --------------------------------------------------------------------------
# Adresses e-mail
# --------------------------------------------------------------------------


def test_redact_masks_personal_email() -> None:
    text = "Contact : jane.doe@personal-mail.example.net"

    result = redact(text)

    assert "jane.doe@personal-mail.example.net" not in result
    assert "<adresse>" in result


def test_redact_keeps_allowlisted_email() -> None:
    config = _config(email_allowlist=frozenset({"public@work.example.org"}))
    text = "Contact public : public@work.example.org"

    result = redact(text, config)

    assert "public@work.example.org" in result


@pytest.mark.parametrize(
    "address",
    [
        "fixture@example.com",
        "attacker@evil.com",
        "tester@corp.com",
    ],
)
def test_redact_keeps_known_test_domains(address: str) -> None:
    text = f"utilisé dans les tests : {address}"

    result = redact(text)

    assert address in result


def test_redact_keeps_github_noreply_email() -> None:
    text = "co-authored-by 12345678+someone@users.noreply.github.com"

    result = redact(text)

    assert "12345678+someone@users.noreply.github.com" in result


def test_redact_does_not_leak_unlisted_email_even_if_similar_domain_allowed() -> None:
    config = _config(email_allowlist=frozenset({"public@work.example.org"}))
    text = "adresse personnelle : private@work.example.org"

    result = redact(text, config)

    assert "private@work.example.org" not in result
    assert "<adresse>" in result


# --------------------------------------------------------------------------
# Chemins locaux
# --------------------------------------------------------------------------


def test_redact_masks_windows_user_path() -> None:
    text = r"log dans C:\Users\testuser\AppData\Roaming\thing"

    result = redact(text)

    assert "testuser" not in result
    assert result == r"log dans ~\AppData\Roaming\thing"


def test_redact_masks_gitbash_user_path() -> None:
    text = "log dans /c/Users/testuser/scratch"

    result = redact(text)

    assert "testuser" not in result
    assert result == "log dans ~/scratch"


def test_redact_masks_configured_path_root() -> None:
    config = _config(path_roots=("D:\\SOME-PROJECT-ROOT",))
    text = r"D:\SOME-PROJECT-ROOT\ask-my-cv\tools\devlog\redact.py"

    result = redact(text, config)

    assert "SOME-PROJECT-ROOT" not in result
    assert result == r"<poste>\ask-my-cv\tools\devlog\redact.py"


def test_redact_masks_configured_local_username_outside_users_path() -> None:
    config = _config(local_usernames=frozenset({"testuser"}))
    text = r"\\host\c$\Users\testuser\shared"

    result = redact(text, config)

    assert "testuser" not in result


# --------------------------------------------------------------------------
# Idempotence
# --------------------------------------------------------------------------


def test_redact_is_idempotent() -> None:
    config = _config(
        aws_account_ids=frozenset({FAKE_ACCOUNT_ID}),
        email_allowlist=frozenset({"public@work.example.org"}),
        local_usernames=frozenset({"testuser"}),
        path_roots=("D:\\SOME-PROJECT-ROOT",),
    )
    text = (
        f"compte {FAKE_ACCOUNT_ID}, arn:aws:iam::{FAKE_ACCOUNT_ID}:role/x, "
        r"C:\Users\testuser\file, jane.doe@personal-mail.example.net, "
        "public@work.example.org, fixture@example.com"
    )

    once = redact(text, config)
    twice = redact(once, config)

    assert once == twice


# --------------------------------------------------------------------------
# Garde-fou des secrets
# --------------------------------------------------------------------------


def test_assert_no_secret_raises_on_langfuse_secret_key() -> None:
    fake_key = "sk" + "-lf-" + "a1b2c3d4e5f6g7h8i9j0"

    with pytest.raises(SecretDetected):
        assert_no_secret(f"LANGFUSE_SECRET_KEY={fake_key}")


def test_assert_no_secret_raises_on_langfuse_public_key() -> None:
    fake_key = "pk" + "-lf-" + "a1b2c3d4e5f6g7h8i9j0"

    with pytest.raises(SecretDetected):
        assert_no_secret(f"LANGFUSE_PUBLIC_KEY={fake_key}")


def test_assert_no_secret_raises_on_aws_access_key_id() -> None:
    fake_access_key = "AK" + "IA" + "X" * 16

    with pytest.raises(SecretDetected):
        assert_no_secret(f"aws_access_key_id = {fake_access_key}")


def test_assert_no_secret_raises_on_unidentified_long_token() -> None:
    long_token = ("Kx9Qz2" * 8)[:44]

    with pytest.raises(SecretDetected):
        assert_no_secret(f"token opaque : {long_token}")


def test_assert_no_secret_allows_commit_sha() -> None:
    fake_commit_sha = "a" * 40

    assert_no_secret(f"voir le commit {fake_commit_sha}")


def test_assert_no_secret_allows_sha256_digest() -> None:
    fake_digest = "sha256:" + "b" * 64

    assert_no_secret(f"image ask-my-cv@{fake_digest}")


def test_assert_no_secret_allows_plain_text() -> None:
    assert_no_secret("Rien de sensible ici, juste du texte de journal normal.")
