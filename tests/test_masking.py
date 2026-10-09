import time

import pytest

from ask_my_cv.masking import mask, truncate

ALLOWED = ["job@stevelang.net"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("écris à jean.dupont@acme.fr", "écris à [e-mail]"),
        ("Contact : job@stevelang.net", "Contact : job@stevelang.net"),
        ("Contact : JOB@stevelang.net", "Contact : JOB@stevelang.net"),
        ("appelle le 06 12 34 56 78", "appelle le [téléphone]"),
        ("ou le 06.12.34.56.78.", "ou le [téléphone]."),
        ("tél. +33 6 12 34 56 78", "tél. [téléphone]"),
        ("Montréal : (514) 555-1234", "Montréal : [téléphone]"),
        ("cell +1 514 555 1234", "cell [téléphone]"),
        ("UK +44 20 7946 0958", "UK [téléphone]"),
        ("voir https://acme.example/offre?id=42 svp", "voir [url] svp"),
        ("site www.acme.ca/jobs", "site [url]"),
        (
            "clé " + "AKIA" + "ABCDEFGHIJKLMNOP" + " ici",
            "clé [secret] ici",
        ),  # assemblé : pas de faux positif
        ("jeton ghp_" + "a" * 36, "jeton [secret]"),
        ("clé sk-ant-api03-abc_DEF", "clé [secret]"),
    ],
)
def test_masks_personal_data_and_secrets(text: str, expected: str) -> None:
    assert mask(text, ALLOWED) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Expérience de 2019-2023 chez NeoBotiQc",
        "Salaire 120000 $ ?",
        "Combien d'années, 15 ans ?",
        "Quel est son rôle chez NeoBotiQc [1] ?",
    ],
)
def test_keeps_ordinary_text(text: str) -> None:
    assert mask(text, ALLOWED) == text


def test_url_wins_over_the_email_it_contains() -> None:
    assert mask("https://x.example/?to=a@b.fr", ALLOWED) == "[url]"


def test_masking_is_fast_on_pathological_input() -> None:
    started = time.perf_counter()
    mask("1 " * 50_000 + "@" * 50_000 + "a." * 50_000)
    assert time.perf_counter() - started < 2.0


def test_truncate() -> None:
    assert truncate("abc", 3) == "abc"
    assert truncate("abcdef", 4) == "abc…"


ZW = "\u200b"


@pytest.mark.parametrize(
    "text",
    [
        f"jean{ZW}.dupont@acme.fr",
        f"jean.dupont@ac{ZW}me.fr",
        "jean.dupont\uff20acme.fr",  # arobase pleine chasse
        "jean.dupont [at] acme [dot] fr",
        "jean.dupont(at)acme(dot)fr",
        "jean.dupont at acme dot fr",
        "jean.dupont at acme.fr",
    ],
)
def test_obfuscated_emails_are_masked(text: str) -> None:
    assert mask(text, ALLOWED) == "[e-mail]"


def test_obfuscated_phone_and_urls_are_masked() -> None:
    assert mask(f"06{ZW} 12 34 56{ZW}78", ALLOWED) == "[téléphone]"
    assert mask("hxxps://evil.example/x", ALLOWED) == "[url]"
    assert mask("hxxp://evil[.]example/x", ALLOWED) == "[url]"


def test_allowed_contact_survives_obfuscation_handling() -> None:
    assert mask("job [at] stevelang [dot] net", ALLOWED) == "job@stevelang.net"


def test_plain_at_in_prose_is_kept() -> None:
    text = "Il a travaillé at NeoBotiQc en 2020"
    assert mask(text, ALLOWED) == text
