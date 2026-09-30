from __future__ import annotations

import json
from pathlib import Path

import boto3
import numpy as np
import pytest
from botocore.stub import Stubber

from ml import drift

DAY = 86400
NOW = 100 * DAY
VERSION = "onnx-v1.4.0"
QUESTIONS = [40, 30, 20, 10, 5]  # compartiments de 0,1 sous le seuil 0,5
ADS = [5, 20, 30, 20, 15]


# --- Statistique ------------------------------------------------------------------------------


def test_psi_nul_pour_des_distributions_identiques() -> None:
    assert drift.psi(QUESTIONS, QUESTIONS) == pytest.approx(0.0, abs=1e-12)


def test_psi_eleve_pour_des_distributions_opposees() -> None:
    assert drift.psi([100, 0, 0, 0, 0], [0, 0, 0, 0, 100]) > 1.0


def test_lissage_de_laplace_borne_l_effet_d_un_compartiment_vide() -> None:
    # un score isolé dans un compartiment vide de la référence ne suffit pas à alerter
    assert drift.psi([30, 0, 0], [29, 1, 0]) < 0.1


def test_psi_refuse_des_longueurs_differentes() -> None:
    with pytest.raises(ValueError, match="même longueur"):
        drift.psi([1, 2, 3], [1, 2])


@pytest.mark.parametrize("threshold, k", [(0.5, 5), (0.3, 3), (1.0, 10)])
def test_seuil_sur_un_bord_de_compartiment(threshold: float, k: int) -> None:
    assert drift.kept_bins(threshold) == k


@pytest.mark.parametrize("threshold", [0.55, 0.0, 0.05])
def test_seuil_hors_bord_refuse(threshold: float) -> None:
    with pytest.raises(ValueError):
        drift.kept_bins(threshold)


def test_scores_au_dessus_du_seuil_exclus_de_l_histogramme() -> None:
    assert drift.counts_below([0.05, 0.15, 0.49, 0.5, 0.97], 0.5).tolist() == [1, 1, 0, 0, 1]


def test_moins_de_compartiments_pour_les_petits_echantillons() -> None:
    counts = np.asarray(QUESTIONS)
    assert drift.coarsen(counts, 50).tolist() == [70, 30, 5]
    assert drift.coarsen(counts, 150).tolist() == QUESTIONS


@pytest.mark.parametrize("n", [30, 60, 150, 400])
def test_echantillon_tire_de_la_reference_n_alerte_pas(n: int) -> None:
    """≥ 99 % des graines : n scores tirés de la base ne dépassent pas le 99e centile nul."""
    base = np.asarray(QUESTIONS)
    probs = base / base.sum()
    alerts = 0
    seeds = 300
    for seed in range(1, seeds + 1):
        sample = np.random.default_rng(1000 + seed).multinomial(n, probs)
        alerts += drift.compare(base, sample).level == "fail"
    assert alerts / seeds <= 0.01, alerts


def test_vraie_derive_detectee_malgre_un_petit_echantillon() -> None:
    assert drift.compare(np.asarray(QUESTIONS), np.asarray([2, 3, 5, 10, 20])).level == "fail"


# --- Analyse des lignes ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value, expected", [("42", 42), ("42.0", 42), (42, 42), (42.0, 42), ("", None), (None, None)]
)
def test_longueur_en_chaine_ou_en_nombre(value: object, expected: int | None) -> None:
    assert drift.parse_chars(value) == expected


@pytest.mark.parametrize("value", ["abc", "4.5", -1, True])
def test_longueur_invalide_refusee(value: object) -> None:
    with pytest.raises(drift.DriftError):
        drift.parse_chars(value)


def test_horodatage_logs_insights_ou_millisecondes() -> None:
    assert drift.parse_timestamp("1970-01-02 00:00:00.000") == DAY
    assert drift.parse_timestamp(str(DAY * 1000)) == DAY


def test_seuil_annonce_lu_dans_les_reglages(tmp_path: Path) -> None:
    path = tmp_path / "settings.yaml"
    path.write_text("guardrail_min_chars: 250\n", encoding="utf-8")
    assert drift.ad_min_chars(path) == 250
    assert drift.ad_min_chars(tmp_path / "absent.yaml") == 400
    assert drift.ad_min_chars(Path("settings.aws.yaml")) >= 1


def test_version_mal_formee_refusee() -> None:
    for bad in ["v1.4.0", 'onnx-v1.4.0" or 1=1', "heuristic-1", ""]:
        with pytest.raises(ValueError):
            drift.validate_version(bad)


# --- Requête Logs Insights --------------------------------------------------------------------


def _response(status: str, rows: list[list[dict[str, str]]]) -> dict:
    return {
        "status": status,
        "results": rows,
        "statistics": {"recordsMatched": 0.0, "recordsScanned": 0.0, "bytesScanned": 0.0},
    }


def _row(score: str, chars: str | None, version: str = VERSION) -> list[dict[str, str]]:
    row = [
        {"field": "score", "value": score},
        {"field": "model_version", "value": version},
        {"field": "ts", "value": "2026-09-30 01:02:03.000"},
    ]
    if chars is not None:
        row.append({"field": "chars", "value": chars})
    return row


def _stubbed(responses: list[dict]) -> tuple[object, Stubber]:
    client = boto3.client("logs", region_name="ca-central-1")
    stub = Stubber(client)
    stub.add_response(
        "start_query",
        {"queryId": "q1"},
        {
            "logGroupName": "aws/spans",
            "startTime": 1000,
            "endTime": 2000,
            "queryString": drift.LOGS_INSIGHTS_QUERY,
        },
    )
    for response in responses:
        stub.add_response("get_query_results", response, {"queryId": "q1"})
    return client, stub


def test_fetch_scores_lit_score_longueur_version_et_horodatage() -> None:
    client, stub = _stubbed(
        [_response("Running", []), _response("Complete", [_row("0.083", "42"), _row("0.5", None)])]
    )
    sleeps: list[float] = []
    with stub:
        samples = drift.fetch_scores(client, "aws/spans", 1000, 2000, sleep=sleeps.append)
    assert [(s.score, s.chars, s.version) for s in samples] == [
        (0.083, 42, VERSION),
        (0.5, None, VERSION),
    ]
    assert sleeps == [drift.POLL_INTERVAL_S]


def test_fetch_scores_echoue_si_le_resultat_est_tronque(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(drift, "QUERY_LIMIT", 2)
    client, stub = _stubbed([_response("Complete", [_row("0.1", "10"), _row("0.2", "10")])])
    with stub, pytest.raises(drift.DriftError, match="tronqué"):
        drift.fetch_scores(client, "aws/spans", 1000, 2000, sleep=lambda _: None)


def test_fetch_scores_echoue_si_la_requete_echoue() -> None:
    client, stub = _stubbed([_response("Failed", [])])
    with stub, pytest.raises(drift.DriftError, match="échouée"):
        drift.fetch_scores(client, "aws/spans", 1000, 2000, sleep=lambda _: None)


def test_fetch_scores_echoue_apres_le_delai_maximal() -> None:
    client, stub = _stubbed([_response("Running", [])] * drift.MAX_POLLS)
    with stub, pytest.raises(drift.DriftError, match="délai"):
        drift.fetch_scores(client, "aws/spans", 1000, 2000, sleep=lambda _: None)


def test_requete_ecarte_eval_et_spans_sans_score() -> None:
    assert "isPresent(`attributes.xops.score`)" in drift.LOGS_INSIGHTS_QUERY
    assert "not isPresent(`attributes.xops.eval`)" in drift.LOGS_INSIGHTS_QUERY
    assert "`attributes.xops.chars` as chars" in drift.LOGS_INSIGHTS_QUERY


# --- Orchestration (scores synthétiques) --------------------------------------------------------


def _reference(tmp_path: Path) -> Path:
    data = {
        "version": "v1.4.0",
        "domain_score_histogram": {"counts": QUESTIONS + [0] * 5},
        "domain_question_score_histogram": {"counts": QUESTIONS + [0] * 5},
        "job_ad_score_histogram": {"counts": ADS + [7, 3, 0, 0, 0]},
    }
    path = tmp_path / "metrics.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _draw(counts: list[int], n: int, chars: int, days_ago: tuple[int, int], seed: int) -> list:
    rng = np.random.default_rng(seed)
    probs = np.asarray(counts) / sum(counts)
    bins = rng.choice(len(counts), size=n, p=probs)
    lo, hi = days_ago
    return [
        drift.Sample(
            b / 10 + rng.uniform(0.001, 0.099), chars, VERSION, NOW - rng.uniform(lo, hi) * DAY
        )
        for b in bins
    ]


def _run(tmp_path: Path, samples: list, *extra: str) -> int:
    settings = tmp_path / "settings.yaml"
    settings.write_text("guardrail_min_chars: 400\n", encoding="utf-8")

    def fetch(client, log_group, start, end, **kwargs):  # noqa: ANN001, ARG001
        return samples

    code = drift.main(
        ["--reference", str(_reference(tmp_path)), "--settings", str(settings), *extra],
        client_factory=lambda region: object(),
        fetch_scores=fetch,
        now=lambda: NOW,
    )
    return code


def _stable(seed: int = 1) -> list:
    return (
        _draw(QUESTIONS, 200, 50, (7, 35), seed)
        + _draw(QUESTIONS, 60, 50, (0, 7), seed + 1)
        + _draw(ADS, 120, 3000, (7, 35), seed + 2)
        + _draw(ADS, 40, 3000, (0, 7), seed + 3)
    )


def test_production_stable_pas_de_derive(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    code = _run(tmp_path, _stable())
    out = capsys.readouterr().out
    assert code == 0, out
    assert out.count("pas de dérive significative") == 2


def test_ecart_a_la_reference_d_evaluation_seulement_avertit(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    # production stable dans le temps mais loin du jeu d'évaluation : jamais un échec
    shifted = [2, 3, 5, 10, 20]
    samples = _draw(shifted, 200, 50, (7, 35), 3) + _draw(shifted, 60, 50, (0, 7), 4)
    samples += _draw(ADS, 120, 3000, (7, 35), 5) + _draw(ADS, 40, 3000, (0, 7), 6)
    code = _run(tmp_path, samples)
    out = capsys.readouterr().out
    assert code == 0, out
    assert "questions : écart à la référence d'évaluation" in out


def test_derive_dans_le_temps_detectee(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    samples = _draw(QUESTIONS, 200, 50, (7, 35), 7) + _draw([2, 3, 5, 10, 20], 60, 50, (0, 7), 8)
    samples += _draw(ADS, 120, 3000, (7, 35), 9) + _draw(ADS, 40, 3000, (0, 7), 10)
    code = _run(tmp_path, samples)
    out = capsys.readouterr().out
    assert code == 1
    assert "dérive détectée, questions" in out


def test_donnees_insuffisantes_reussit_avec_une_note(
    tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    # version en service depuis 10 jours seulement, trafic faible
    samples = _draw(QUESTIONS, 20, 50, (0, 10), 11) + _draw(ADS, 5, 3000, (0, 10), 12)
    code = _run(tmp_path, samples)
    out = capsys.readouterr().out
    assert code == 0, out
    assert out.count("données insuffisantes") == 2
    assert summary.read_text(encoding="utf-8").count("données insuffisantes") == 2


def test_quatorze_jours_sans_evaluation_echoue(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    # en service depuis 30 jours, mais trop peu d'annonces sur les 14 derniers jours
    samples = _stable()
    samples = [s for s in samples if not (s.chars == 3000 and s.ts > NOW - 14 * DAY)]
    samples += _draw(ADS, 5, 3000, (0, 14), 13)
    code = _run(tmp_path, samples)
    out = capsys.readouterr().out
    assert code == 1
    assert "annonces : 5 score(s) exploitable(s) sur 14 jours" in out


def test_version_mal_alignee_echoue(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    samples = [drift.Sample(0.1, 50, "onnx-v1.3.0", NOW - DAY) for _ in range(100)]
    code = _run(tmp_path, samples)
    assert code == 1
    assert "aucun span de onnx-v1.4.0" in capsys.readouterr().out


def test_aucun_span_echoue(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    assert _run(tmp_path, []) == 1
    assert "aucun span `injection`" in capsys.readouterr().out


def test_autre_version_ignoree(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    samples = _stable() + [drift.Sample(0.45, 50, "onnx-v1.3.0", NOW - DAY)] * 500
    assert _run(tmp_path, samples) == 0, capsys.readouterr().out


def test_entrees_bloquees_exclues(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    samples = _stable() + [drift.Sample(0.97, 50, VERSION, NOW - DAY)] * 500
    assert _run(tmp_path, samples) == 0, capsys.readouterr().out


def test_version_mal_formee_refusee_par_main(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    def fetch(*args, **kwargs):  # noqa: ANN002, ANN003, ARG001
        raise AssertionError("aucune requête AWS avec une version invalide")

    code = drift.main(
        ["--reference", str(_reference(tmp_path)), "--model-version", 'onnx-v1" or 1=1'],
        client_factory=lambda region: object(),
        fetch_scores=fetch,
    )
    assert code == 1
    assert "version de modèle invalide" in capsys.readouterr().out


def test_seuil_hors_bord_refuse_par_main(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    code = drift.main(
        ["--reference", str(_reference(tmp_path)), "--threshold", "0.55"],
        client_factory=lambda region: object(),
        fetch_scores=lambda *a, **k: [],
    )
    assert code == 1
    assert "multiple" in capsys.readouterr().out


def test_reference_sans_histogramme_avertit_et_reussit(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    reference = tmp_path / "metrics.json"
    reference.write_text(json.dumps({"deepset_recall": 0.9}), encoding="utf-8")
    code = drift.main(
        ["--reference", str(reference)],
        client_factory=lambda region: object(),
        fetch_scores=lambda *a, **k: [],
    )
    assert code == 0
    assert "référence sans domain_score_histogram" in capsys.readouterr().out
