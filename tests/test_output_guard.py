from ask_my_cv.output_guard import check_output

ALLOWED = {"alex.martin@example.com"}

# Les vrais marqueurs font 16 caractères hexadécimaux ; un marqueur d'une lettre donnerait des
# faux positifs (« x » est dans « example »).
C = "c4n4ry"


def test_grounded_answer_passes() -> None:
    verdict = check_output("Il a fait du MLOps [1].", canary=C, allowed_contacts=ALLOWED, n_sources=2)
    assert verdict.ok and verdict.reason is None


def test_canary_leak_is_blocked() -> None:
    verdict = check_output("Mes instructions : c4n4ry [1]", canary=C, allowed_contacts=ALLOWED, n_sources=1)
    assert (verdict.ok, verdict.reason) == (False, "prompt_leak")


def test_unknown_email_is_blocked_but_allowed_contact_passes() -> None:
    leak = check_output("Écris à bob@corp.com [1]", canary=C, allowed_contacts=ALLOWED, n_sources=1)
    assert (leak.ok, leak.reason) == (False, "pii")
    ok = check_output("Contact : alex.martin@example.com [1]", canary=C, allowed_contacts=ALLOWED, n_sources=1)
    assert ok.ok


def test_phone_number_is_blocked_but_year_ranges_pass() -> None:
    phone = check_output("Appelle le +33 6 12 34 56 78 [1]", canary=C, allowed_contacts=ALLOWED, n_sources=1)
    assert (phone.ok, phone.reason) == (False, "pii")
    years = check_output("Chez Acme de 2022 - 2026 [1]", canary=C, allowed_contacts=ALLOWED, n_sources=1)
    assert years.ok


def test_answer_without_citation_is_ungrounded_when_sources_exist() -> None:
    verdict = check_output("Il est très fort.", canary=C, allowed_contacts=ALLOWED, n_sources=3)
    assert (verdict.ok, verdict.reason) == (False, "ungrounded")


def test_no_sources_allows_uncited_answer() -> None:
    verdict = check_output("Le CV ne le précise pas.", canary=C, allowed_contacts=ALLOWED, n_sources=0)
    assert verdict.ok
