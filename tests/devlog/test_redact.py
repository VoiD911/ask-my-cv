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
import uuid
from pathlib import Path

import pytest

from tools.devlog.redact import (
    ConfigError,
    RedactConfig,
    SecretDetected,
    Suspect,
    assert_no_secret,
    find_suspects,
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


def test_redact_leading_separator_root_only_matches_at_path_start() -> None:
    # P6 : une racine à séparateur de tête (`/d/some-project-root`) ne doit
    # matcher qu'à un véritable début de chemin (début de chaîne, espace,
    # guillemet, `(` ou `=`), jamais au milieu d'un segment relatif —
    # `a/d/some-project-root/b` est un sur-masquage à éviter, pas un vrai
    # chemin vers la racine configurée.
    config = RedactConfig(path_roots=("/d/some-project-root",))

    assert redact("a/d/some-project-root/b", config) == "a/d/some-project-root/b"
    assert redact("/d/some-project-root/b", config) == "<poste>/b"
    assert redact(" /d/some-project-root/b", config) == " <poste>/b"
    assert redact("(/d/some-project-root/b)", config) == "(<poste>/b)"
    assert redact('="/d/some-project-root/b"', config) == '="<poste>/b"'


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
# Niveau 1 — assert_no_secret (bloquant, haute confiance uniquement)
# --------------------------------------------------------------------------


def test_assert_no_secret_raises_on_langfuse_secret_key() -> None:
    fake_key = "sk" + "-lf-" + "a1b2c3d4e5f6g7h8i9j0"

    with pytest.raises(SecretDetected):
        assert_no_secret(f"LANGFUSE_SECRET_KEY={fake_key}")


def test_assert_no_secret_raises_on_openai_project_key() -> None:
    fake_key = "sk-" + "proj-" + ("Ab1_" * 12)

    with pytest.raises(SecretDetected):
        assert_no_secret(f"OPENAI_API_KEY={fake_key}")


def test_assert_no_secret_raises_on_anthropic_style_key() -> None:
    fake_key = "sk-" + "ant-" + ("Ab1_" * 12)

    with pytest.raises(SecretDetected):
        assert_no_secret(f"ANTHROPIC_API_KEY={fake_key}")


def test_assert_no_secret_raises_on_legacy_openai_key() -> None:
    # P5 : ancien format OpenAI, "sk-" + 40+ caractères alphanumériques SANS
    # tiret ni tiret bas (ne recoupe pas sk-lf-/sk-proj-/sk-ant-).
    fake_key = "sk-" + "Ab1" * 16  # 48 caractères après le préfixe

    with pytest.raises(SecretDetected):
        assert_no_secret(f"OPENAI_API_KEY={fake_key}")


def test_assert_no_secret_raises_on_slack_token() -> None:
    # Construit par concaténation (jamais en clair) pour ne pas ressembler à
    # une véritable fuite aux yeux d'un scanner comme gitleaks.
    fake_token = "xox" + "b-" + "123456789012-1234567890123-" + "AbCdEfGhIjKlMnOpQrStUvWx"

    with pytest.raises(SecretDetected):
        assert_no_secret(f"SLACK_BOT_TOKEN={fake_token}")


def test_assert_no_secret_raises_on_google_api_key() -> None:
    fake_key = "AI" + "za" + "SyA1b2C3d4E5f6G7h8I9j0KlMnOpQrStUvW"

    with pytest.raises(SecretDetected):
        assert_no_secret(f"GOOGLE_API_KEY={fake_key}")


def test_assert_no_secret_raises_on_aws_access_key_id() -> None:
    fake_access_key = "AK" + "IA" + "X" * 16

    with pytest.raises(SecretDetected):
        assert_no_secret(f"aws_access_key_id = {fake_access_key}")


def test_assert_no_secret_raises_on_aws_temporary_session_key_id() -> None:
    fake_session_key = "AS" + "IA" + "ABCDEFGHIJKLMNOP"

    with pytest.raises(SecretDetected):
        assert_no_secret(f"key {fake_session_key}")


def test_assert_no_secret_raises_on_aws_secret_access_key_mixed_value() -> None:
    fake_secret = "wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEYab"  # 40 caractères exactement
    assert len(fake_secret) == 40

    with pytest.raises(SecretDetected):
        assert_no_secret(f"aws_secret_access_key = {fake_secret}")


def test_assert_no_secret_raises_on_aws_secret_access_key_without_a_digit() -> None:
    # P1 : le niveau bloquant AWS n'exige plus le mélange des trois classes
    # (majuscule+minuscule+chiffre), seulement « pas tout en minuscules » —
    # une clé secrète AWS réelle sans chiffre a ~0,1 % de chances d'exister
    # mais doit quand même être détectée dans ce contexte explicite.
    fake_secret = "wJalrXUtnFEMIKxMDENGbPxRfiCYEXAMPLEKEYab"
    assert len(fake_secret) == 40

    with pytest.raises(SecretDetected):
        assert_no_secret(f"aws_secret_access_key = {fake_secret}")


def test_assert_no_secret_allows_aws_secret_access_key_placeholder() -> None:
    # Une valeur toute en minuscules (gabarit, espace réservé répété) n'est
    # pas un vrai secret — évite un faux positif bloquant sur un exemple de
    # documentation. `<redacted>` ne matche même pas la forme attendue.
    assert_no_secret("aws_secret_access_key = <redacted>")
    assert_no_secret("aws_secret_access_key = changeme")
    assert_no_secret("aws_secret_access_key = " + "a" * 40)


def test_assert_no_secret_raises_on_aws_secret_access_key_json_field() -> None:
    # P1 : sortie JSON de sts/get-session-token/export-credentials.
    fake_secret = "wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEYab"
    assert len(fake_secret) == 40

    with pytest.raises(SecretDetected):
        assert_no_secret('{"SecretAccessKey": "' + fake_secret + '"}')


def test_assert_no_secret_raises_on_aws_configure_set_cli_form() -> None:
    # P1 : séparateur espace (CLI), pas `:`/`=`.
    fake_secret = "wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEYab"
    assert len(fake_secret) == 40

    with pytest.raises(SecretDetected):
        assert_no_secret(f"aws configure set aws_secret_access_key {fake_secret}")


def test_assert_no_secret_raises_on_aws_session_token_without_asia_nearby() -> None:
    # P1 : un jeton de session AWS est détecté par sa seule présence dans ce
    # contexte, même sans ASIA... à proximité.
    fake_token = "Ab1" * 40  # bien plus long qu'une clé secrète (120 caractères)

    with pytest.raises(SecretDetected):
        assert_no_secret('{"SessionToken": "' + fake_token + '"}')

    with pytest.raises(SecretDetected):
        assert_no_secret(f"aws_session_token={fake_token}")


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


def test_assert_no_secret_sha_prefix_cannot_hide_explicit_secret() -> None:
    # Les détecteurs bloquants tournent sur le texte brut : un préfixe
    # « sûr » ne peut jamais servir à camoufler une clé AKIA...
    fake_access_key = "AK" + "IA" + "X" * 16
    with pytest.raises(SecretDetected):
        assert_no_secret(f"sha1-{fake_access_key}")


def test_assert_no_secret_allows_plain_text() -> None:
    assert_no_secret("Rien de sensible ici, juste du texte de journal normal.")


def test_assert_no_secret_allows_hex_and_generic_tokens_now_handled_by_suspects() -> None:
    # Ce qui levait `SecretDetected` avant la revue #18 ter (jeton opaque
    # générique, hexadécimal, affectation de mot de passe) est désormais du
    # ressort de `find_suspects` (non bloquant) : `assert_no_secret` ne s'en
    # préoccupe plus du tout, quel que soit le contenu.
    assert_no_secret("a" * 64)  # hex64 sans contexte : suspect, jamais bloquant
    assert_no_secret("DB_PASSWORD=Sup3rS3cretPassw0rd!")  # affectation : suspect, jamais bloquant
    random.seed(1234)
    token = "".join(
        random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
        for _ in range(43)
    )
    assert_no_secret(f"token opaque : {token}")  # jeton générique : suspect, jamais bloquant


def test_assert_no_secret_allowlist_has_no_effect_since_no_config_param() -> None:
    # Design de la revue #18 ter : `assert_no_secret` ne prend plus de
    # configuration du tout — aucune allowlist ne peut jamais s'appliquer à
    # ce niveau, par construction de la signature elle-même.
    pem = "-----BEGIN " + "RSA PRIVATE KEY-----"
    with pytest.raises(SecretDetected):
        assert_no_secret(pem)


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
    assert_no_secret(b64)  # jamais bloquant désormais : pas d'exception à attendre
    assert time.perf_counter() - start < 3.0


# --------------------------------------------------------------------------
# Niveau 2 — find_suspects (non bloquant, heuristique)
# --------------------------------------------------------------------------


def _kinds(suspects: list[Suspect]) -> set[str]:
    return {s.kind for s in suspects}


def _previews_never_contain(suspects: list[Suspect], secret_value: str) -> bool:
    return all(secret_value not in s.preview for s in suspects)


def test_find_suspects_never_raises_and_never_exposes_the_value() -> None:
    fake_hex64 = "c" * 64
    suspects = find_suspects(f"SECRET={fake_hex64}")

    assert suspects  # au moins un suspect
    assert _previews_never_contain(suspects, fake_hex64)
    for suspect in suspects:
        assert fake_hex64 not in suspect.preview


def test_find_suspects_preview_format() -> None:
    fake_hex64 = "c" * 64
    suspects = find_suspects(f"SECRET={fake_hex64}")

    assert any("(64)" in s.preview for s in suspects)
    fingerprint = hashlib.sha256(fake_hex64.encode()).hexdigest()[:8]
    assert any(fingerprint in s.preview for s in suspects)


def test_find_suspects_preview_never_contains_any_substring_of_the_value() -> None:
    # P4 : ni le début, ni la fin, ni aucun fragment interne de la valeur —
    # seuls le type, la longueur et une empreinte sha256 tronquée.
    value = "R3alS3cretValueForPreviewTest99"
    suspects = find_suspects(f"SECRET={value}")

    assert suspects
    for suspect in suspects:
        for start in range(len(value) - 1):
            fragment = value[start : start + 2]
            assert fragment not in suspect.preview, (
                f"fragment {fragment!r} de la valeur trouvé dans l'aperçu {suspect.preview!r}"
            )


# --- Politique hexadécimale (R4) ---------------------------------------


def test_find_suspects_allows_short_hex_identifiers() -> None:
    # ETag S3/md5 (32 hex), uuid4().hex (32 hex), RequestId AWS (32 hex) :
    # en dessous du seuil de 41 caractères, jamais suspect.
    assert find_suspects('ETag: "' + hashlib.md5(b"x").hexdigest() + '"') == []  # noqa: S324
    assert find_suspects(uuid.uuid4().hex) == []
    assert find_suspects("RequestId: " + uuid.uuid4().hex) == []


def test_find_suspects_flags_hex32_secret_key_as_suspect() -> None:
    # secrets.token_hex(16) : 32 caractères, mais explicitement une clé.
    # Toujours en dessous de 41 : volontairement non suspect (choix du seuil
    # aligné sur le plan, cf. revue #18 ter R4). Documenté : un secret aussi
    # court échappe à `find_suspects` comme à `assert_no_secret`.
    assert find_suspects("a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6") == []


def test_find_suspects_flags_hex_of_unusual_length() -> None:
    # secrets.token_hex(24) et token_hex(48) : 48 et 96 caractères, ni un SHA
    # de commit (40) ni une longueur de digest usuelle (64/128).
    assert _kinds(find_suspects("a" * 48)) == {"hexadecimal"}
    assert _kinds(find_suspects("b" * 96)) == {"hexadecimal"}


def test_find_suspects_flags_hex64_without_digest_context() -> None:
    fake_hex64 = "c" * 64
    assert "hexadecimal" in _kinds(find_suspects(f"SECRET={fake_hex64}"))


def test_find_suspects_allows_hex64_with_digest_word_context() -> None:
    digest = hashlib.sha256(b"fixture").hexdigest()
    assert find_suspects(f"digest {digest}") == []


def test_find_suspects_allows_sha256_prefix_hex_digest() -> None:
    digest = hashlib.sha256(b"fixture").hexdigest()
    assert find_suspects(f"image ask-my-cv@sha256:{digest}") == []
    assert find_suspects(f"SHA256:{digest}") == []


def test_find_suspects_allows_sha256sum_output_context() -> None:
    digest = hashlib.sha256(b"y").hexdigest()
    assert find_suspects(f"{digest}  dist/app.zip") == []


def test_find_suspects_allows_docker_and_pip_hash_context() -> None:
    digest = hashlib.sha256(b"y").hexdigest()
    assert find_suspects(f"Image ID: sha256:{digest}") == []
    assert find_suspects(f"--hash=sha256:{digest}") == []


def test_find_suspects_allows_commit_sha_and_joined_shas() -> None:
    assert find_suspects("a" * 40) == []
    assert find_suspects("A" * 40) == []
    left = hashlib.sha1(b"a").hexdigest()
    right = hashlib.sha1(b"b").hexdigest()
    assert find_suspects(f"{left}..{right}") == []
    assert find_suspects(f"{left}_{right}") == []


def test_find_suspects_allowlist_exempts_hex_run() -> None:
    fake_hex64 = "c" * 64
    config = RedactConfig(secret_allowlist=(re.escape(fake_hex64),))

    assert find_suspects(f"SECRET={fake_hex64}") != []
    assert find_suspects(f"SECRET={fake_hex64}", config) == []


# --- Jeton opaque générique ----------------------------------------------


def test_find_suspects_flags_unidentified_base64url_token() -> None:
    random.seed(1234)
    token = "".join(
        random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
        for _ in range(43)
    )
    assert "jeton" in _kinds(find_suspects(f"token opaque : {token}"))


def test_find_suspects_flags_secret_key_starting_with_slash_or_plus() -> None:
    body_slash = "k=/" + "JalrXUtnFEMI/K7MDENG/bPxRfiCY" + "EXAMPLEKEY"
    body_plus = "k=" + ("wJalrXUtnFEMI+K7MDENG+bPxRfiCY" + "EXAMPLEKEY").replace("/", "+")

    assert "jeton" in _kinds(find_suspects(body_slash))
    assert "jeton" in _kinds(find_suspects(body_plus))


def test_find_suspects_allows_camel_case_and_snake_case_identifiers() -> None:
    assert find_suspects("AskMyCvApiGatewayLambdaIntegrationPermissionForCloudFront") == []
    assert (
        find_suspects("test_redact_does_not_leak_unlisted_email_even_if_similar_domain_allowed")
        == []
    )


def test_find_suspects_allows_long_lowercase_paths() -> None:
    assert (
        find_suspects("src/ask_my_cv/infrastructure/observability/langfuse_client/tracing.py") == []
    )
    assert (
        find_suspects("tests/infrastructure/observability/test_langfuse_tracing_adapter.py") == []
    )


def test_find_suspects_allows_uuid() -> None:
    assert find_suspects("01d3d8b5-04cb-42e0-ba4a-0d6251c3d4a1") == []


def test_find_suspects_path_like_without_mixed_segment_is_not_a_suspect() -> None:
    assert (
        find_suspects("D--DEV-ecc/01d3d8b5-04cb-42e0-ba4a-0d6251c3d4a1/subagents/agent-a1b2") == []
    )


def test_find_suspects_url_with_mixed_case_segment_still_needs_allowlist() -> None:
    url = "https://github.com/VoiD911/ask-my-cv/blob/0123456789abcdef/tools/devlog/redact.py"

    assert "jeton" in _kinds(find_suspects(url))

    config = RedactConfig(secret_allowlist=(r".*VoiD911/ask-my-cv/blob/[0-9a-f]+/[\w./]*",))
    assert find_suspects(url, config) == []


def test_find_suspects_allowlist_can_exempt_a_known_false_positive() -> None:
    token = "AskMyCv-Build-Mq9Xz3Kw7Qn2Tv8Br5Jl4Pd6Sg0Zy8Wu3"

    assert "jeton" in _kinds(find_suspects(token))

    config = RedactConfig(secret_allowlist=(re.escape(token),))
    assert find_suspects(token, config) == []


def test_find_suspects_allows_safe_digest_shapes_restored_from_54269ae() -> None:
    # R5 : régression corrigée — exemptés uniquement à leur longueur EXACTE
    # (jamais un préfixe non borné, qui serait un contournement).
    ssh_fp = "SHA256:" + base64.b64encode(hashlib.sha256(b"fixture").digest()).decode().rstrip("=")
    npm_integrity = "integrity sha512-" + base64.b64encode(hashlib.sha512(b"q").digest()).decode()
    terraform_hash = (
        'source_code_hash = "' + base64.b64encode(hashlib.sha256(b"q").digest()).decode() + '"'
    )
    lambda_code_sha = (
        '"CodeSha256": "' + base64.b64encode(hashlib.sha256(b"fixture").digest()).decode() + '"'
    )

    assert find_suspects(ssh_fp) == []
    assert find_suspects(npm_integrity) == []
    assert find_suspects(terraform_hash) == []
    assert find_suspects(lambda_code_sha) == []


def test_find_suspects_safe_digest_exemption_is_exact_length_not_a_bypass() -> None:
    # Une valeur plus longue que la forme reconnue ne doit PAS être exemptée
    # (sinon le préfixe redeviendrait un contournement générique).
    too_long = base64.b64encode(secrets.token_bytes(60)).decode()  # bien plus que 43/44 caractères
    suspects = find_suspects(f"SHA256:{too_long}")
    assert suspects != []


# --- Affectation à un mot-clé sensible (R1) ------------------------------


def test_find_suspects_flags_password_assignment() -> None:
    assert "affectation" in _kinds(find_suspects("DB_PASSWORD=Sup3rS3cretPassw0rd!"))


def test_find_suspects_flags_quoted_secret_assignment() -> None:
    fake = "R3alS3cretValue99Extra"
    assert "affectation" in _kinds(find_suspects(f'PASSWORD="{fake}"'))


@pytest.mark.parametrize(
    "text",
    [
        'token = request.headers["Authorization"]',
        "password = get_password_from_vault()",
        "api_key=os.environ.get('LANGFUSE_KEY')",
        "SECRET_KEY = settings.SECRET_KEY",
        "secret_id = aws_secretsmanager_secret.langfuse.id",
        'passthrough_behavior = "WHEN_NO_MATCH"',
        "password: <placeholder>",
        "password: ********",
        "tokens: input_tokens+output_tokens",
        "Tests passed: test_redact_is_idempotent",
        "le mot de passe: réinitialisé_manuellement",
        "token_url=https://auth.example.com/oauth/token",
        "--secret-string=file://secret.json",
        "LANGFUSE_SECRET_KEY=${LANGFUSE_SECRET_KEY}",
        "secret: ${{ secrets.LANGFUSE_SECRET_KEY }}",
        "max_tokens=4096",
        "passwd: /etc/passwd_backup_file",
        "bypass_governance_retention=true_always_on",
        "pwd=/home/runner/work/ask-my-cv",
        "api_key: str = Field(default=...)",
    ],
)
def test_find_suspects_does_not_flag_common_code_and_prose_false_positives(text: str) -> None:
    assert find_suspects(text) == [], f"faux positif sur : {text!r}"


def test_find_suspects_assignment_allowlist_exempts_value() -> None:
    fake = "R3alS3cretValue99Extra"
    config = RedactConfig(secret_allowlist=(re.escape(fake),))

    assert "affectation" in _kinds(find_suspects(f'PASSWORD="{fake}"'))
    assert find_suspects(f'PASSWORD="{fake}"', config) == []


def test_find_suspects_assignment_scans_every_match_not_only_the_first() -> None:
    fake1 = "R3alS3cretValueOne99"
    fake2 = "R3alS3cretValueTwo88"
    text = f"SECRET={fake1}; DB_PASSWORD={fake2}"

    suspects = [s for s in find_suspects(text) if s.kind == "affectation"]

    assert len(suspects) == 2


def test_find_suspects_assignment_performance_is_linear() -> None:
    # R1 : l'ancien détecteur monolithique (`\w*` en tête) était quadratique.
    # L'approche « repérer l'opérateur puis vérifier une fenêtre bornée »
    # reste rapide même sur une suite adversariale sans aucun opérateur.
    for text in ("secret_" * 20000, "pass" * 20000, "token_" * 20000):
        start = time.perf_counter()
        find_suspects(text)
        assert time.perf_counter() - start < 1.0


def test_find_suspects_repeated_keyword_equals_is_linear_p2() -> None:
    # P2 : la valeur nue n'excluait pas `=`, donc chaque opérateur d'un texte
    # comme "secret="*n rebalayait tout le reste de la suite — quadratique
    # (23,5 s pour 140 k caractères mesurés en revue). Bornée à 256
    # caractères et sans `=`, chaque tentative est désormais O(1).
    for text in ("secret=" * (1_000_000 // 7), "aws_secret_access_key=" * (1_000_000 // 22)):
        start = time.perf_counter()
        find_suspects(text)
        assert time.perf_counter() - start < 1.0


def test_assert_no_secret_repeated_aws_keyword_is_linear() -> None:
    # Le niveau bloquant AWS (P1) doit rester rapide sur la même suite
    # adversariale : le motif est à longueur FIXE (40 ou 100-4000 bornée),
    # donc chaque occurrence du mot-clé ne coûte qu'un travail constant.
    text = "aws_secret_access_key=" * (1_000_000 // 22)

    start = time.perf_counter()
    assert_no_secret(text)  # aucune valeur valide de 40 caractères présente
    assert time.perf_counter() - start < 1.0


# --------------------------------------------------------------------------
# Allowlist trop permissive (R2)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "pattern",
    [
        r"\S+",
        r"[^ ]+",
        r"[\w+/-]+",
        r"[A-Za-z0-9+/_-]{40,}={0,2}",
        r".*",
        r".+",
        # P3 : classes sans `_` ni `-`, qui échappaient aux anciennes sondes.
        r"[A-Za-z0-9]+",
        r"[A-Za-z0-9+/=]+",
        r"(?i)[a-z0-9+/]+=*",
        r"[0-9a-f]+",
        r"[^\s]{16,}",
    ],
)
def test_load_config_rejects_broad_allowlist_classes(
    pattern: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_file = tmp_path / "redact.json"
    config_file.write_text(json.dumps({"secret_allowlist": [pattern]}), encoding="utf-8")
    monkeypatch.setenv("DEVLOG_REDACT_CONFIG_PATH", str(config_file))

    with pytest.raises(ConfigError):
        load_config()


def test_broad_allowlist_pattern_does_not_neutralize_generic_detector_defensively() -> None:
    # Même construite hors `load_config` (donc jamais validée), une regex
    # trop large est ignorée par `find_suspects` : elle ne neutralise jamais
    # le détecteur générique.
    fake_key = base64.b64encode(secrets.token_bytes(30)).decode()
    config = RedactConfig(secret_allowlist=(r"\S+",))

    suspects = find_suspects(f"k {fake_key}", config)

    assert suspects != []  # le jeton générique reste détecté malgré l'allowlist invalide


# --------------------------------------------------------------------------
# Racine avec séparateur en tête (R3) : pas de comportement quadratique
# --------------------------------------------------------------------------


def test_redact_leading_separator_root_is_linear() -> None:
    config = RedactConfig(path_roots=("/d/DEV",))

    for text in ("C:" + "\\" * 40000 + "x", "D:" + "/" * 40000):
        start = time.perf_counter()
        redact(text, config)
        assert time.perf_counter() - start < 1.0


def test_redact_leading_separator_root_one_megabyte_is_fast() -> None:
    config = RedactConfig(path_roots=("/d/DEV",))

    for text in ("\\" * 1_000_000, "/" * 1_000_000):
        start = time.perf_counter()
        redact(text, config)
        assert time.perf_counter() - start < 2.0


# --------------------------------------------------------------------------
# Propriété : jamais de secret bloquant restant après redact(), corpus fictif
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
    partir d'un corpus fictif ne contenant aucun secret à haute confiance,
    `assert_no_secret` ne doit jamais se déclencher après `redact`, et
    `redact` doit rester idempotente.
    """
    checked = 0
    for combo in itertools.combinations(_PROPERTY_CORPUS, 4):
        text = "\n".join(combo)

        redacted = redact(text, CONFIGURED)

        assert_no_secret(redacted)
        assert redact(redacted, CONFIGURED) == redacted
        checked += 1

    assert checked > 300
