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
import re
import secrets
import time
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


def test_redact_arn_followed_by_non_colon_separator_is_masked_generically() -> None:
    # N8 a élargi le motif ARN (`\b` au lieu de `(?=:)`) : un compte précédé
    # d'un `:` est désormais masqué même s'il n'est pas suivi d'un `:`
    # (`arn:aws:iam::<id>/x`, ou toute autre forme malformée), sans
    # configuration.
    text = f"arn:aws:iam::{FAKE_ACCOUNT_ID}/x"

    assert FAKE_ACCOUNT_ID not in redact(text, EMPTY)


@pytest.mark.parametrize("text", ["arn:aws:iam::{id}", "arn:aws:iam::{id}\n"])
def test_redact_masks_arn_ending_right_after_account_id(text: str) -> None:
    result = redact(text.format(id=FAKE_ACCOUNT_ID), EMPTY)

    assert FAKE_ACCOUNT_ID not in result
    assert "<compte-aws>" in result


def test_redact_does_not_mask_timestamp_or_phone_number_lookalikes() -> None:
    # N7 : le motif de compartiment exige un préfixe alphabétique (2 lettres
    # minimum) avant le tiret, pour ne pas masquer un horodatage ou un
    # numéro de téléphone qui ressemble à un identifiant de compte à 12
    # chiffres.
    assert redact("x-202609271230 build", EMPTY) == "x-202609271230 build"
    assert redact("tel +1-514555123456", EMPTY) == "tel +1-514555123456"


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


def test_redact_masks_only_first_word_of_spaced_name_without_config() -> None:
    # Sans configuration, le nom générique s'arrête au premier espace : "Bob"
    # est masqué, "Smith" reste (documenté ; masquer le nom complet exige de
    # le configurer explicitement dans `local_usernames`, voir le test
    # suivant).
    result = redact(r"C:\Users\Bob Smith\x", EMPTY)

    assert "Bob" not in result
    assert result == r"~ Smith\x"


def test_redact_masks_full_spaced_name_when_configured() -> None:
    config = RedactConfig(local_usernames=frozenset({"Bob Smith"}))
    result = redact(r"C:\Users\Bob Smith\x", config)

    assert "Bob" not in result
    assert "Smith" not in result
    assert result == r"~\x"


def test_redact_username_generic_stops_at_whitespace_preserving_sentence() -> None:
    text = r"C:\Users\bob est le dossier"

    result = redact(text, EMPTY)

    assert result == r"~ est le dossier"


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
# Performance (N1, N2) : pas de retour arrière catastrophique
# --------------------------------------------------------------------------


def test_redact_backslash_run_is_linear_not_exponential() -> None:
    # N1 : `[\\/]+` (classe unique quantifiée), jamais `(?:\+|/)+` (quantificateurs
    # imbriqués, exponentiel). Sans le correctif, ceci ne termine pas en un temps
    # raisonnable dès n≈24.
    text = "C:" + "\\" * 5000 + "x"

    start = time.perf_counter()
    redact(text, EMPTY)
    assert time.perf_counter() - start < 2.0


def test_redact_backslash_run_is_linear_with_configured_root() -> None:
    config = RedactConfig(path_roots=("D:\\DEV",))
    text = "D:" + "\\" * 5000 + "x"

    start = time.perf_counter()
    redact(text, config)
    assert time.perf_counter() - start < 2.0


def test_redact_posix_home_slash_run_is_linear() -> None:
    text = "/c" + "/" * 5000

    start = time.perf_counter()
    redact(text, EMPTY)
    assert time.perf_counter() - start < 2.0


def test_redact_email_scan_is_linear_not_quadratic() -> None:
    # N2 : la partie locale de l'adresse e-mail est ancrée (lookbehind de
    # début), donc chaque position n'est essayée qu'une fois. Sans le
    # correctif, ceci prend plusieurs secondes voire dizaines de secondes.
    text = "a." * 500_000  # 1 Mo, jamais d'arobase

    start = time.perf_counter()
    redact(text, EMPTY)
    assert time.perf_counter() - start < 2.0


def test_redact_million_digits_without_at_sign_is_linear() -> None:
    text = "1" * 1_000_000

    start = time.perf_counter()
    redact(text, EMPTY)
    assert time.perf_counter() - start < 2.0


def test_redact_one_megabyte_mixed_text_is_fast() -> None:
    config = RedactConfig(
        local_usernames=frozenset({"bob"}),
        path_roots=("D:\\DEV",),
        aws_account_ids=frozenset({FAKE_ACCOUNT_ID}),
    )
    line = (
        r"Lorem ipsum C:\\Users\\bob\\x arn:aws:iam::"
        f"{FAKE_ACCOUNT_ID}"
        r":role/x a@gmail.com D:\DEV\x mot "
    ) * 100
    big = line * (1_000_000 // max(len(line), 1))

    start = time.perf_counter()
    redact(big, config)
    duration = time.perf_counter() - start
    assert duration < 3.0


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


@pytest.mark.parametrize(
    "payload",
    [
        {"local_usernames": ["ab"]},  # 2 caractères, minimum 3
        {"path_roots": ["D"]},  # 1 caractère, minimum 2
        {"local_usernames": ["   "]},  # espaces uniquement
        {"secret_allowlist": ["("]},  # regex invalide
        {"secret_allowlist": [".*"]},  # accepte la chaîne vide
        {"secret_allowlist": [".+"]},  # accepte un texte arbitraire
    ],
)
def test_load_config_rejects_invalid_semantic_payloads(
    payload: dict[str, object], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_file = tmp_path / "redact.json"
    config_file.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("DEVLOG_REDACT_CONFIG_PATH", str(config_file))

    with pytest.raises(ConfigError):
        load_config()


def test_load_config_accepts_narrow_secret_allowlist_pattern(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_file = tmp_path / "redact.json"
    config_file.write_text(
        json.dumps({"secret_allowlist": [r"AskMyCv-Build-[0-9A-Za-z]+"]}), encoding="utf-8"
    )
    monkeypatch.setenv("DEVLOG_REDACT_CONFIG_PATH", str(config_file))

    config = load_config()

    assert config.secret_allowlist == (r"AskMyCv-Build-[0-9A-Za-z]+",)


def test_load_config_secret_allowlist_env_var_is_not_split_on_commas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEVLOG_REDACT_SECRET_ALLOWLIST", r"AskMyCv-Build-[0-9A-Za-z]{1,3}-x")

    config = load_config()

    assert config.secret_allowlist == (r"AskMyCv-Build-[0-9A-Za-z]{1,3}-x",)


def test_load_config_secret_allowlist_env_var_accepts_json_array(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "DEVLOG_REDACT_SECRET_ALLOWLIST", json.dumps(["AskMyCv-One-[a-z]+", "AskMyCv-Two-[a-z]+"])
    )

    config = load_config()

    assert config.secret_allowlist == ("AskMyCv-One-[a-z]+", "AskMyCv-Two-[a-z]+")


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


def test_assert_no_secret_rejects_sha256_prefixed_base64_secret() -> None:
    # Durci volontairement (revue #18 bis, N3/N4) : un préfixe `sha256:` ne
    # peut exempter que de l'hexadécimal (un vrai digest), jamais du base64
    # arbitraire — sinon n'importe quel secret pourrait se faire passer pour
    # une empreinte SSH en se préfixant de `sha256:`. Un cas légitime précis
    # se gère via `secret_allowlist`, jamais par un affaiblissement générique.
    secret_like = base64.b64encode(hashlib.sha256(b"not-actually-a-digest").digest()).decode()
    with pytest.raises(SecretDetected):
        assert_no_secret(f"SHA256:{secret_like}")


def test_assert_no_secret_allows_sha1_uppercase_hex() -> None:
    assert_no_secret(hashlib.sha1(b"fixture").hexdigest().upper())


def test_assert_no_secret_allows_sha512_hex_with_digest_context() -> None:
    # Un hex de 128 caractères (longueur sha512) exige désormais un contexte
    # de digest reconnu, comme le hex64 (N4) — sans contexte, il serait
    # indétectable d'un vrai secret hexadécimal de même longueur.
    assert_no_secret(f"sha512:{hashlib.sha512(b'fixture').hexdigest()}")


def test_assert_no_secret_rejects_bare_sha512_length_hex_without_context() -> None:
    with pytest.raises(SecretDetected):
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


def test_assert_no_secret_allows_short_hex_below_policy_threshold() -> None:
    # En dessous de 32 caractères, la politique hexadécimale ne s'applique
    # pas (ex. un digest court, une couleur, un identifiant tronqué).
    assert_no_secret("a1b2c3d4e5f6a7b8")


def test_assert_no_secret_rejects_hex32_secret_key() -> None:
    # secrets.token_hex(16) : 32 caractères hexadécimaux, ni un SHA de commit
    # (40) ni un digest reconnu (64/128) : doit être détecté.
    with pytest.raises(SecretDetected):
        assert_no_secret("a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6")


def test_assert_no_secret_rejects_hex48_and_hex96_regardless_of_context() -> None:
    # secrets.token_hex(24) et token_hex(48) : 48 et 96 caractères
    # hexadécimaux, ni un SHA de commit (40) ni un digest reconnu (64/128).
    with pytest.raises(SecretDetected):
        assert_no_secret("a" * 48)
    with pytest.raises(SecretDetected):
        assert_no_secret("b" * 96)


def test_assert_no_secret_rejects_hex64_without_digest_context() -> None:
    fake_hex64 = "c" * 64
    with pytest.raises(SecretDetected):
        assert_no_secret(f"SECRET={fake_hex64}")
    with pytest.raises(SecretDetected):
        assert_no_secret(f"LANGFUSE_SECRET_KEY={fake_hex64}")


def test_assert_no_secret_allows_hex64_with_digest_word_context() -> None:
    digest = hashlib.sha256(b"fixture").hexdigest()
    assert_no_secret(f"digest {digest}")


def test_assert_no_secret_rejects_password_assignment() -> None:
    with pytest.raises(SecretDetected):
        assert_no_secret("DB_PASSWORD=Sup3rS3cretPassw0rd!")


def test_assert_no_secret_allows_placeholder_assignment() -> None:
    assert_no_secret("aws_secret_access_key = <redacted>")
    assert_no_secret("API_KEY=changeme")
    assert_no_secret("DB_PASSWORD=xxx")


def test_assert_no_secret_sha_prefix_cannot_hide_explicit_secret() -> None:
    # N4 : un préfixe « sûr » ne doit jamais servir à camoufler un détecteur
    # explicite (les motifs dangereux tournent sur le texte brut, avant toute
    # suppression).
    fake_access_key = "AK" + "IA" + "X" * 16
    with pytest.raises(SecretDetected):
        assert_no_secret(f"sha1-{fake_access_key}")


def test_assert_no_secret_allows_plain_text() -> None:
    assert_no_secret("Rien de sensible ici, juste du texte de journal normal.")


def test_assert_no_secret_one_megabyte_camel_words_is_fast() -> None:
    words = ("CamelCaseIdentifierWithoutDigitsLongEnough ") * 25000

    start = time.perf_counter()
    assert_no_secret(words)
    assert time.perf_counter() - start < 3.0


def test_assert_no_secret_one_megabyte_of_commit_shas_is_fast() -> None:
    text = "".join(hashlib.sha1(str(i).encode()).hexdigest() + " " for i in range(24000))

    start = time.perf_counter()
    assert_no_secret(text)
    assert time.perf_counter() - start < 3.0


def test_assert_no_secret_one_megabyte_base64_line_is_fast() -> None:
    b64 = base64.b64encode(secrets.token_bytes(750_000)).decode()

    start = time.perf_counter()
    try:
        assert_no_secret(b64)
    except SecretDetected:
        pass  # attendu : un si long jeton base64 est détecté ; seule la durée nous importe ici
    assert time.perf_counter() - start < 3.0


def test_assert_no_secret_path_like_without_mixed_segment_is_not_a_false_positive() -> None:
    # N5 : un chemin/URL décomposé en segments courts (`/`), dont aucun
    # segment ne mélange lui-même majuscule+minuscule+chiffre, n'est plus un
    # faux positif générique.
    assert_no_secret("D--DEV-ecc/01d3d8b5-04cb-42e0-ba4a-0d6251c3d4a1/subagents/agent-a1b2")
    assert_no_secret("src/ask_my_cv/infrastructure/observability/langfuse_client/tracing")


def test_assert_no_secret_url_with_mixed_case_segment_still_needs_allowlist() -> None:
    # Choix assumé (voir docstring de `_looks_like_path_or_url`) : quand UN
    # segment est lui-même « aléatoire » (ex. un nom d'utilisateur GitHub tel
    # que `VoiD911`), le candidat n'est PAS exempté automatiquement — on ne
    # peut pas le distinguer de façon fiable d'un vrai secret base64 dont les
    # classes de caractères seraient réparties sur plusieurs segments
    # (voir `test_assert_no_secret_raises_on_secret_key_starting_with_slash`,
    # qui doit continuer à lever). La détection d'un vrai secret prime
    # toujours sur l'esthétique d'un rendu ponctuel ; `secret_allowlist` est
    # le mécanisme explicite prévu pour ce cas précis.
    url = "https://github.com/VoiD911/ask-my-cv/blob/0123456789abcdef/tools/devlog/redact.py"

    with pytest.raises(SecretDetected):
        assert_no_secret(url)

    config = RedactConfig(secret_allowlist=(r".*VoiD911/ask-my-cv/blob/[0-9a-f]+/[\w./]*",))
    assert_no_secret(url, config)


def test_assert_no_secret_secret_allowlist_can_exempt_a_known_false_positive() -> None:
    # Un identifiant public propre au dépôt peut, par coïncidence, mélanger
    # majuscule/minuscule/chiffre et dépasser 40 caractères, sans être
    # découpé en segments de chemin (donc pas couvert par l'exclusion N5).
    # Plutôt que d'affaiblir la détection générique, `secret_allowlist`
    # exempte explicitement ce motif connu et sûr pour ce dépôt.
    # Lettres hors de la plage hexadécimale (M, X, K, w, Q, n, T, v, B, r, J,
    # l, P, S, g, Z, y, W, u) entre les chiffres, pour ne jamais former de
    # suite hexadécimale pure (sinon la politique hex — indépendante de
    # `secret_allowlist` — se déclencherait avant même le détecteur générique).
    token = "AskMyCv-Build-Mq9Xz3Kw7Qn2Tv8Br5Jl4Pd6Sg0Zy8Wu3"

    with pytest.raises(SecretDetected):
        assert_no_secret(token)

    config = RedactConfig(secret_allowlist=(re.escape(token),))
    assert_no_secret(token, config)


def test_assert_no_secret_secret_allowlist_never_suppresses_explicit_detectors() -> None:
    # N3 : l'allowlist ne s'applique qu'au détecteur générique, jamais aux
    # motifs dangereux explicites (PEM, clés AWS, jetons GitHub...), même
    # avec un motif volontairement très large.
    ghp = "ghp_" + "Ab1" * 12
    url_with_token = f"https://github.com/VoiD911/x?t={ghp}"
    broad_config = RedactConfig(secret_allowlist=(r"VoiD911/\S*",))

    with pytest.raises(SecretDetected):
        assert_no_secret(url_with_token, broad_config)

    pem = "-----BEGIN " + "RSA PRIVATE KEY-----"
    catch_all_config = RedactConfig(
        secret_allowlist=(r".*",)
    )  # non validée (contournement de load_config)
    with pytest.raises(SecretDetected):
        assert_no_secret(pem, catch_all_config)


def test_assert_no_secret_ignores_invalid_allowlist_pattern_defensively() -> None:
    # Une regex invalide construite hors de `load_config` (qui l'aurait
    # rejetée) ne doit jamais faire planter le garde-fou : elle est ignorée,
    # au pire l'exemption n'a pas lieu (ce qui ne peut jamais faire fuiter un
    # secret).
    config = RedactConfig(secret_allowlist=("(",))
    assert_no_secret("texte tout à fait normal", config)


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
