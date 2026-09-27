"""Tests du masquage déterministe (`tools/devlog/redact.py`).

Toutes les valeurs utilisées ici sont fictives (comptes AWS, adresses,
utilisateurs, secrets). Les chaînes ressemblant à des secrets sont
construites par concaténation à l'exécution plutôt qu'écrites en clair, pour
ne jamais ressembler à une véritable fuite aux yeux d'un scanner comme
gitleaks. Ce module ne lit jamais le journal de session réel.
"""

from __future__ import annotations

import base64
import hashlib
import itertools
import json
import random
from pathlib import Path

import pytest

from tools.devlog.redact import (
    ConfigError,
    RedactConfig,
    SecretDetected,
    assert_no_secret,
    load_config,
    redact,
)

FAKE_ACCOUNT_ID = "123456789012"
OTHER_FAKE_ACCOUNT_ID = "210987654321"

EMPTY = RedactConfig.empty()
CONFIGURED = RedactConfig(
    aws_account_ids=frozenset({FAKE_ACCOUNT_ID}),
    email_allowlist=frozenset({"job@work.example.org"}),
    local_usernames=frozenset({"bob"}),
    path_roots=(r"D:\SOME-PROJECT-ROOT", "/d/some-project-root"),
)


def _config(**kwargs: object) -> RedactConfig:
    return RedactConfig(**kwargs)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# Identifiants de compte AWS
# --------------------------------------------------------------------------


@pytest.mark.parametrize("config", [EMPTY, CONFIGURED], ids=["sans-config", "configuré"])
@pytest.mark.parametrize(
    "template",
    [
        "ask-my-cv-tfstate-{id}",
        "s3://ask-my-cv-site-{id}/index.html",
        "arn:aws:s3:::ask-my-cv-site-{id}",
        "arn:aws:iam::{id}:role/deploy",
        "arn:aws:lambda:ca-central-1:{id}:function:f",
        "arn:aws:cloudfront::{id}:distribution/E1",
        "arn:aws:sts::{id}:assumed-role/deploy/session",
        "{id}.dkr.ecr.ca-central-1.amazonaws.com/ask-my-cv:latest",
        "https://{id}.signin.aws.amazon.com",
        "Account: {id}",
        '"Account": "{id}"',
    ],
)
def test_redact_masks_account_id_generic_contexts(template: str, config: RedactConfig) -> None:
    text = template.format(id=FAKE_ACCOUNT_ID)

    result = redact(text, config)

    assert FAKE_ACCOUNT_ID not in result
    assert "<compte-aws>" in result


def test_redact_masks_bare_configured_account_id() -> None:
    text = f"compte de déploiement : {FAKE_ACCOUNT_ID}"

    result = redact(text, CONFIGURED)

    assert FAKE_ACCOUNT_ID not in result


def test_redact_does_not_mask_bare_account_id_without_config() -> None:
    text = f"un nombre à 12 chiffres sans contexte : {FAKE_ACCOUNT_ID}"

    result = redact(text, EMPTY)

    assert FAKE_ACCOUNT_ID in result


def test_redact_masks_configured_account_id_glued_with_underscore() -> None:
    result = redact(f"{FAKE_ACCOUNT_ID}_foo", CONFIGURED)
    assert FAKE_ACCOUNT_ID not in result

    result2 = redact(f"tfstate_{FAKE_ACCOUNT_ID}", CONFIGURED)
    assert FAKE_ACCOUNT_ID not in result2


def test_redact_does_not_mask_unrelated_account_id() -> None:
    text = f"identifiant sans lien : {OTHER_FAKE_ACCOUNT_ID}"

    result = redact(text, CONFIGURED)

    assert OTHER_FAKE_ACCOUNT_ID in result


def test_redact_malformed_arn_without_trailing_colon_needs_configured_id() -> None:
    text = f"arn:aws:iam::{FAKE_ACCOUNT_ID}/x"

    assert FAKE_ACCOUNT_ID in redact(text, EMPTY)
    assert FAKE_ACCOUNT_ID not in redact(text, CONFIGURED)


# --------------------------------------------------------------------------
# Adresses e-mail
# --------------------------------------------------------------------------


def test_redact_masks_personal_email() -> None:
    text = "Contact : jane.doe@personal-mail.example.net"

    result = redact(text, EMPTY)

    assert "jane.doe@personal-mail.example.net" not in result
    assert "<adresse>" in result


def test_redact_keeps_allowlisted_email_case_insensitively() -> None:
    text = "Contact : JOB@Work.Example.ORG"

    result = redact(text, CONFIGURED)

    assert "JOB@Work.Example.ORG" in result


def test_redact_masks_email_not_on_allowlist() -> None:
    text = "adresse personnelle : private@work.example.org"

    result = redact(text, CONFIGURED)

    assert "private@work.example.org" not in result
    assert "<adresse>" in result


@pytest.mark.parametrize(
    "address",
    [
        "fixture@example.com",
        "attacker@evil.com",
        "tester@corp.com",
        "a@sub.example.com",
        "x@EXAMPLE.COM",
    ],
)
def test_redact_keeps_known_test_domains_case_insensitively(address: str) -> None:
    result = redact(f"utilisé dans les tests : {address}", EMPTY)

    assert address in result


def test_redact_keeps_github_noreply_email() -> None:
    text = "co-authored-by 12345678+someone@users.noreply.github.com"

    result = redact(text, EMPTY)

    assert "12345678+someone@users.noreply.github.com" in result


def test_redact_masks_lookalike_noreply_domain_suffix_attack() -> None:
    text = "x@users.noreply.github.com.attacker.io"

    result = redact(text, EMPTY)

    assert "x@users.noreply.github.com.attacker.io" not in result
    assert "<adresse>" in result


def test_redact_masks_lookalike_test_domain_suffix_attack() -> None:
    text = "x@example.com.evil.net"

    result = redact(text, EMPTY)

    assert "x@example.com.evil.net" not in result
    assert "<adresse>" in result


# --------------------------------------------------------------------------
# Chemins locaux
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (r"C:\Users\bob\x", r"~\x"),
        ("C:/Users/bob/x", "~/x"),
        ("/c/Users/bob/x", "~/x"),
        ("/C/Users/bob/x", "~/x"),
        (r"C:\\Users\\bob\\x", r"~\\x"),  # échappement JSON (.jsonl)
        (r"c:\users\bob\x", r"~\x"),  # minuscules
        ("/mnt/c/Users/bob/x", "~/x"),  # WSL
        ("file:///C:/Users/bob/x", "~/x"),
    ],
)
def test_redact_masks_user_home_path_in_every_notation(text: str, expected: str) -> None:
    assert redact(text, EMPTY) == expected


def test_redact_masks_username_with_space_without_leaking_surname() -> None:
    result = redact(r"C:\Users\Bob Smith\x", EMPTY)

    assert "Bob" not in result
    assert "Smith" not in result
    assert result == r"~\x"


def test_redact_does_not_corrupt_unrelated_wsl_or_windows_paths() -> None:
    assert redact("/home/bob/x", EMPTY) == "/home/bob/x"
    assert redact("/Users/bob/x", EMPTY) == "/Users/bob/x"


@pytest.mark.parametrize(
    "text",
    [
        r"D:\SOME-PROJECT-ROOT\ecc\x",
        "D:/SOME-PROJECT-ROOT/ecc",
        "/d/some-project-root/ecc",
        r"D:\\SOME-PROJECT-ROOT\\ecc",  # échappement JSON
        r"d:\some-project-root\ecc",  # casse différente
    ],
)
def test_redact_masks_configured_path_root_in_every_notation(text: str) -> None:
    result = redact(text, CONFIGURED)

    assert "SOME-PROJECT-ROOT" not in result
    assert "<poste>" in result


def test_redact_does_not_truncate_a_longer_sibling_root() -> None:
    text = r"D:\SOME-PROJECT-ROOT-EXTENDED\x"

    result = redact(text, CONFIGURED)

    assert result == text  # racine configurée non suivie d'une frontière : intacte


def test_redact_masks_configured_username_outside_users_path() -> None:
    result = redact(r"\\host\c$\Users\bob\shared", CONFIGURED)
    assert "bob" not in result

    result2 = redact("bobby and bob", CONFIGURED)
    assert result2 == "bobby and <utilisateur>"  # pas de sur-correspondance dans "bobby"


def test_redact_username_masking_does_not_corrupt_allowed_email() -> None:
    # "bob" est configuré comme nom d'utilisateur ; une adresse autorisée qui
    # contient ce nom ne doit pas être altérée (masquage en une seule passe).
    config = RedactConfig(
        email_allowlist=frozenset({"bob@work.example.org"}),
        local_usernames=frozenset({"bob"}),
    )
    result = redact("contact : bob@work.example.org", config)

    assert result == "contact : bob@work.example.org"


def test_redact_username_masking_does_not_corrupt_configured_root() -> None:
    # Un nom d'utilisateur configuré ne doit pas empêcher une racine de
    # chemin qui contient ce nom de correspondre.
    config = RedactConfig(local_usernames=frozenset({"bob"}), path_roots=(r"D:\bob-projects",))
    result = redact(r"D:\bob-projects\x", config)

    assert result == r"<poste>\x"


# --------------------------------------------------------------------------
# Idempotence
# --------------------------------------------------------------------------


def test_redact_is_idempotent() -> None:
    text = (
        f"compte {FAKE_ACCOUNT_ID}, arn:aws:iam::{FAKE_ACCOUNT_ID}:role/x, "
        r"C:\Users\bob\file, jane.doe@personal-mail.example.net, "
        "job@work.example.org, fixture@example.com, "
        r"D:\SOME-PROJECT-ROOT\x"
    )

    once = redact(text, CONFIGURED)
    twice = redact(once, CONFIGURED)

    assert once == twice


_CORPUS = [
    f"compte {FAKE_ACCOUNT_ID}",
    f"arn:aws:iam::{FAKE_ACCOUNT_ID}:role/x",
    f"arn:aws:s3:::ask-my-cv-site-{FAKE_ACCOUNT_ID}",
    f"{FAKE_ACCOUNT_ID}.dkr.ecr.ca-central-1.amazonaws.com",
    f'"Account": "{FAKE_ACCOUNT_ID}"',
    r"C:\Users\bob\x",
    "C:/Users/bob/x",
    "/mnt/c/Users/bob/x",
    r"D:\SOME-PROJECT-ROOT\ecc",
    "jane.doe@personal-mail.example.net",
    "job@work.example.org",
    "fixture@example.com",
    "12345678+someone@users.noreply.github.com",
    "bobby and bob",
    "texte ordinaire sans rien de sensible",
]


def test_redact_idempotent_on_many_generated_combinations() -> None:
    """Test de type « propriété » : idempotence sur de nombreuses combinaisons
    générées à partir d'un corpus fictif, plutôt que sur des cas isolés.
    """
    checked = 0
    for combo in itertools.combinations(_CORPUS, 3):
        text = " | ".join(combo)

        once = redact(text, CONFIGURED)
        twice = redact(once, CONFIGURED)

        assert once == twice, f"non idempotent pour : {combo!r}"
        assert_no_secret(once)  # jamais de faux jeton recollé par le masquage
        checked += 1

    assert checked == len(list(itertools.combinations(range(len(_CORPUS)), 3)))


# --------------------------------------------------------------------------
# Configuration : chargement et validation
# --------------------------------------------------------------------------


def test_load_config_merges_file_and_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_file = tmp_path / "redact.json"
    config_file.write_text(
        json.dumps({"aws_account_ids": [FAKE_ACCOUNT_ID], "local_usernames": ["bob"]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("DEVLOG_REDACT_CONFIG_PATH", str(config_file))
    monkeypatch.setenv("DEVLOG_REDACT_EMAIL_ALLOWLIST", "job@work.example.org")

    config = load_config()

    assert config.aws_account_ids == frozenset({FAKE_ACCOUNT_ID})
    assert config.local_usernames == frozenset({"bob"})
    assert config.email_allowlist == frozenset({"job@work.example.org"})


def test_load_config_missing_default_path_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    # DEVLOG_REDACT_CONFIG_PATH non défini (nettoyé par le fixture autouse) et
    # chemin par défaut redirigé vers un fichier absent : configuration vide,
    # sans erreur.
    config = load_config()

    assert config == RedactConfig.empty()


def test_load_config_explicit_path_missing_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEVLOG_REDACT_CONFIG_PATH", str(tmp_path / "does-not-exist.json"))

    with pytest.raises(ConfigError):
        load_config()


def test_load_config_malformed_json_raises_json_decode_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_file = tmp_path / "redact.json"
    config_file.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setenv("DEVLOG_REDACT_CONFIG_PATH", str(config_file))

    with pytest.raises(json.JSONDecodeError):
        load_config()


@pytest.mark.parametrize(
    "payload",
    [
        {"local_usernames": "bob"},  # chaîne au lieu d'une liste
        {"path_roots": "D:"},
        {"local_username": ["bob"]},  # clé mal orthographiée -> inconnue
        {"unexpected_key": ["x"]},
        {"local_usernames": [""]},  # chaîne vide
        {"local_usernames": [123]},  # mauvais type d'élément
        {"aws_account_ids": ["not-twelve-digits"]},
        {"aws_account_ids": ["12345678901"]},  # 11 chiffres
        {"aws_account_ids": ["1234567890123"]},  # 13 chiffres
    ],
)
def test_load_config_rejects_invalid_payloads(
    payload: dict[str, object], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_file = tmp_path / "redact.json"
    config_file.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("DEVLOG_REDACT_CONFIG_PATH", str(config_file))

    with pytest.raises(ConfigError):
        load_config()


def test_load_config_require_account_ids_raises_when_absent() -> None:
    with pytest.raises(ConfigError):
        load_config(require_account_ids=True)


def test_load_config_require_account_ids_passes_when_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_file = tmp_path / "redact.json"
    config_file.write_text(json.dumps({"aws_account_ids": [FAKE_ACCOUNT_ID]}), encoding="utf-8")
    monkeypatch.setenv("DEVLOG_REDACT_CONFIG_PATH", str(config_file))

    config = load_config(require_account_ids=True)

    assert config.aws_account_ids == frozenset({FAKE_ACCOUNT_ID})


# --------------------------------------------------------------------------
# Garde-fou des secrets
# --------------------------------------------------------------------------


def test_assert_no_secret_raises_on_langfuse_secret_key() -> None:
    fake_key = "sk" + "-lf-" + "a1b2c3d4e5f6g7h8i9j0"

    with pytest.raises(SecretDetected):
        assert_no_secret(f"LANGFUSE_SECRET_KEY={fake_key}")


def test_assert_no_secret_raises_on_openai_project_key() -> None:
    fake_key = "sk-" + "proj-" + ("Ab1_" * 12)

    with pytest.raises(SecretDetected):
        assert_no_secret(f"OPENAI_API_KEY={fake_key}")


def test_assert_no_secret_raises_on_aws_access_key_id() -> None:
    fake_access_key = "AK" + "IA" + "X" * 16

    with pytest.raises(SecretDetected):
        assert_no_secret(f"aws_access_key_id = {fake_access_key}")


def test_assert_no_secret_raises_on_aws_temporary_session_key_id() -> None:
    fake_session_key = "AS" + "IA" + "ABCDEFGHIJKLMNOP"

    with pytest.raises(SecretDetected):
        assert_no_secret(f"key {fake_session_key}")


def test_assert_no_secret_raises_on_aws_secret_access_key_regardless_of_length() -> None:
    fake_secret = "wJalrXUtnFEMI" + "K7MDENGbPxRfiCY" + "EXAMPLE"  # court, sans '/'

    with pytest.raises(SecretDetected):
        assert_no_secret(f"aws_secret_access_key = {fake_secret}")


def test_assert_no_secret_raises_on_secret_key_starting_with_slash() -> None:
    body = "JalrXUtnFEMI/K7MDENG/bPxRfiCY" + "EXAMPLEKEY"  # 40 caractères, commence par '/'

    with pytest.raises(SecretDetected):
        assert_no_secret(f"k=/{body}")


def test_assert_no_secret_raises_on_secret_key_with_plus() -> None:
    body = ("wJalrXUtnFEMI+K7MDENG+bPxRfiCY" + "EXAMPLEKEY").replace("/", "+")

    with pytest.raises(SecretDetected):
        assert_no_secret(f"k={body}")


@pytest.mark.parametrize("infix", ["p", "o", "s", "u", "r"])
def test_assert_no_secret_raises_on_github_tokens(infix: str) -> None:
    fake_token = f"gh{infix}_" + "A" * 36

    with pytest.raises(SecretDetected):
        assert_no_secret(f"token {fake_token}")


def test_assert_no_secret_raises_on_github_pat() -> None:
    fake_pat = "github_pat_" + "11ABCDEFG0" + "x" * 72

    with pytest.raises(SecretDetected):
        assert_no_secret(f"token {fake_pat}")


def test_assert_no_secret_raises_on_jwt() -> None:
    jwt = (
        "eyJhbGciOiJIUzI1NiJ9"
        + "."
        + "eyJzdWIiOiIxMjM0NTY3ODkwIn0"
        + "."
        + "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
    )

    with pytest.raises(SecretDetected):
        assert_no_secret(f"Authorization: Bearer {jwt}")


def test_assert_no_secret_raises_on_pem_private_key() -> None:
    with pytest.raises(SecretDetected):
        assert_no_secret(
            "-----BEGIN " + "RSA PRIVATE KEY-----\nMIIEow==\n-----END RSA PRIVATE KEY-----"
        )


def test_assert_no_secret_raises_on_openssh_private_key() -> None:
    with pytest.raises(SecretDetected):
        assert_no_secret("-----BEGIN " + "OPENSSH PRIVATE KEY-----")


def test_assert_no_secret_raises_on_unidentified_base64url_token() -> None:
    random.seed(1234)
    token = "".join(
        random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
        for _ in range(43)
    )

    with pytest.raises(SecretDetected):
        assert_no_secret(f"token opaque : {token}")


def test_assert_no_secret_allows_commit_sha_40_hex() -> None:
    assert_no_secret(f"voir le commit {'a' * 40}")


def test_assert_no_secret_allows_commit_sha_uppercase() -> None:
    assert_no_secret(f"voir le commit {'A' * 40}")


def test_assert_no_secret_allows_sha256_digest_lowercase_prefix() -> None:
    digest = hashlib.sha256(b"fixture").hexdigest()
    assert_no_secret(f"image ask-my-cv@sha256:{digest}")


def test_assert_no_secret_allows_sha256_digest_uppercase_prefix() -> None:
    digest = hashlib.sha256(b"fixture").hexdigest()
    assert_no_secret(f"SHA256:{digest}")


def test_assert_no_secret_allows_sha256_ssh_fingerprint_base64() -> None:
    fp = base64.b64encode(hashlib.sha256(b"fixture").digest()).decode().rstrip("=")
    assert_no_secret(f"SHA256:{fp}")


def test_assert_no_secret_allows_sha1_uppercase_hex() -> None:
    assert_no_secret(hashlib.sha1(b"fixture").hexdigest().upper())


def test_assert_no_secret_allows_sha512_hex() -> None:
    assert_no_secret(hashlib.sha512(b"fixture").hexdigest())


def test_assert_no_secret_allows_two_commit_shas_joined_by_dotdot() -> None:
    left = hashlib.sha1(b"a").hexdigest()
    right = hashlib.sha1(b"b").hexdigest()
    assert_no_secret(f"{left}..{right}")


def test_assert_no_secret_allows_two_commit_shas_joined_by_underscore() -> None:
    left = hashlib.sha1(b"a").hexdigest()
    right = hashlib.sha1(b"b").hexdigest()
    assert_no_secret(f"{left}_{right}")


def test_assert_no_secret_allows_code_sha256_lambda_field() -> None:
    fake_code_sha = base64.b64encode(hashlib.sha256(b"fixture").digest()).decode()
    assert_no_secret(f'"CodeSha256": "{fake_code_sha}"')


def test_assert_no_secret_allows_camel_case_identifier() -> None:
    assert_no_secret("AskMyCvApiGatewayLambdaIntegrationPermissionForCloudFront")


def test_assert_no_secret_allows_snake_case_long_identifier() -> None:
    assert_no_secret("test_redact_does_not_leak_unlisted_email_even_if_similar_domain_allowed")


def test_assert_no_secret_allows_long_lowercase_paths() -> None:
    assert_no_secret("src/ask_my_cv/infrastructure/observability/langfuse_client/tracing.py")
    assert_no_secret("tests/infrastructure/observability/test_langfuse_tracing_adapter.py")


def test_assert_no_secret_allows_uuid() -> None:
    assert_no_secret("01d3d8b5-04cb-42e0-ba4a-0d6251c3d4a1")


def test_assert_no_secret_allows_hex32_api_key_below_length_threshold() -> None:
    assert_no_secret("a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6")


def test_assert_no_secret_allows_plain_text() -> None:
    assert_no_secret("Rien de sensible ici, juste du texte de journal normal.")


def test_assert_no_secret_secret_allowlist_can_exempt_a_known_false_positive() -> None:
    # Un identifiant public du dépôt (nom d'utilisateur + chiffres dans une URL
    # GitHub) peut, par coïncidence, mélanger majuscule/minuscule/chiffre et
    # dépasser 40 caractères une fois le chemin concaténé. Plutôt que
    # d'affaiblir la détection générique, `secret_allowlist` exempte
    # explicitement ce motif connu et sûr pour ce dépôt.
    url = "https://github.com/VoiD911/ask-my-cv/blob/0123456789abcdef/tools/devlog/redact.py"

    with pytest.raises(SecretDetected):
        assert_no_secret(url)

    config = RedactConfig(secret_allowlist=(r"VoiD911/ask-my-cv/blob/[0-9a-f]+/[\w/.]+",))
    assert_no_secret(url, config)


# --------------------------------------------------------------------------
# Propriété : jamais de secret restant après redact(), pour un corpus fictif
# --------------------------------------------------------------------------

_PROPERTY_CORPUS = [
    "texte ordinaire, rien de sensible",
    f"compte {FAKE_ACCOUNT_ID} dans arn:aws:iam::{FAKE_ACCOUNT_ID}:role/x",
    r"C:\Users\bob\AppData\Local\Temp\x",
    "/mnt/c/Users/bob/scratch",
    "jane.doe@personal-mail.example.net a écrit ceci",
    "job@work.example.org (adresse publique)",
    "fixture@example.com et attacker@evil.com (fixtures de test)",
    f"{hashlib.sha1(b'x').hexdigest()} est un commit valide",
    f"sha256:{hashlib.sha256(b'x').hexdigest()} est un digest valide",
    "AskMyCvApiGatewayLambdaIntegrationPermissionForCloudFront",
    r"D:\SOME-PROJECT-ROOT\ecc\redact.py",
]


def test_property_redact_then_assert_no_secret_never_raises() -> None:
    """Test de type « propriété » : sur de nombreuses combinaisons générées à
    partir d'un corpus fictif ne contenant aucun secret, `assert_no_secret`
    ne doit jamais se déclencher après `redact`, et `redact` doit rester
    idempotente.
    """
    checked = 0
    for combo in itertools.combinations(_PROPERTY_CORPUS, 4):
        text = "\n".join(combo)

        redacted = redact(text, CONFIGURED)

        assert_no_secret(redacted)
        assert redact(redacted, CONFIGURED) == redacted
        checked += 1

    assert checked > 300
