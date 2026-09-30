from __future__ import annotations

import json
from pathlib import Path

import boto3
import pytest
from botocore.stub import Stubber

from ml import drift


def test_psi_est_nul_pour_des_distributions_identiques() -> None:
    counts = [1, 2, 3, 4, 5, 5, 4, 3, 2, 1]
    assert drift.psi(counts, counts) == pytest.approx(0.0, abs=1e-9)


def test_psi_est_eleve_pour_des_distributions_tres_differentes() -> None:
    reference = [100, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    production = [0, 0, 0, 0, 0, 0, 0, 0, 0, 100]
    assert drift.psi(reference, production) > 0.25


def test_psi_lisse_les_compartiments_vides_sans_division_par_zero() -> None:
    reference = [10, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    production = [0, 10, 0, 0, 0, 0, 0, 0, 0, 0]
    value = drift.psi(reference, production)
    assert value > 0
    assert value != float("inf")


def test_psi_leve_value_error_si_longueurs_differentes() -> None:
    with pytest.raises(ValueError, match="même longueur"):
        drift.psi([1, 2, 3], [1, 2])


def test_histogram_a_dix_compartiments_sur_0_1() -> None:
    counts = drift.histogram([0.0, 0.05, 0.5, 0.95, 1.0])
    assert len(counts) == 10
    assert sum(counts) == 5


def test_histogram_place_un_score_de_1_dans_le_dernier_compartiment() -> None:
    counts = drift.histogram([1.0])
    assert counts[-1] == 1
    assert sum(counts[:-1]) == 0


def _query_results_response(status: str, rows: list[list[dict[str, str]]]) -> dict:
    return {
        "status": status,
        "results": rows,
        "statistics": {"recordsMatched": 0.0, "recordsScanned": 0.0, "bytesScanned": 0.0},
    }


VERSION = "onnx-v1.4.0"


def _stub_start(stub: Stubber) -> None:
    stub.add_response(
        "start_query",
        {"queryId": "q1"},
        {
            "logGroupName": "aws/spans",
            "startTime": 1000,
            "endTime": 2000,
            "queryString": drift.logs_insights_query(VERSION),
        },
    )


def test_fetch_scores_interroge_logs_insights_et_renvoie_score_et_longueur() -> None:
    client = boto3.client("logs", region_name="ca-central-1")
    stub = Stubber(client)
    _stub_start(stub)
    stub.add_response(
        "get_query_results", _query_results_response("Running", []), {"queryId": "q1"}
    )
    stub.add_response(
        "get_query_results",
        _query_results_response(
            "Complete",
            [
                [{"field": "score", "value": "0.083"}, {"field": "chars", "value": "42"}],
                [{"field": "score", "value": "0.5"}],  # span antérieur à xops.chars
            ],
        ),
        {"queryId": "q1"},
    )
    sleeps: list[float] = []
    with stub:
        samples = drift.fetch_scores(client, "aws/spans", 1000, 2000, VERSION, sleep=sleeps.append)
    stub.assert_no_pending_responses()
    assert samples == [drift.Sample(0.083, 42), drift.Sample(0.5, None)]
    assert sleeps == [drift.POLL_INTERVAL_S]


def test_fetch_scores_leve_une_exception_si_la_requete_echoue() -> None:
    client = boto3.client("logs", region_name="ca-central-1")
    stub = Stubber(client)
    _stub_start(stub)
    stub.add_response("get_query_results", _query_results_response("Failed", []), {"queryId": "q1"})
    with stub, pytest.raises(drift.DriftError, match="échouée"):
        drift.fetch_scores(client, "aws/spans", 1000, 2000, VERSION, sleep=lambda _: None)
    stub.assert_no_pending_responses()


def test_fetch_scores_leve_une_exception_si_le_delai_maximal_est_depasse() -> None:
    client = boto3.client("logs", region_name="ca-central-1")
    stub = Stubber(client)
    _stub_start(stub)
    for _ in range(drift.MAX_POLLS):
        stub.add_response(
            "get_query_results", _query_results_response("Running", []), {"queryId": "q1"}
        )
    with stub, pytest.raises(drift.DriftError, match="délai"):
        drift.fetch_scores(client, "aws/spans", 1000, 2000, VERSION, sleep=lambda _: None)
    stub.assert_no_pending_responses()


def test_requete_filtre_la_version_et_ecarte_les_spans_sans_score() -> None:
    query = drift.logs_insights_query(VERSION)
    assert "isPresent(`attributes.xops.score`)" in query
    assert "not isPresent(`attributes.xops.eval`)" in query
    assert '`attributes.xops.model_version` = "onnx-v1.4.0"' in query
    assert "`attributes.xops.chars` as chars" in query


@pytest.mark.parametrize("bad", ["v1.4.0", 'onnx-v1.4.0" or 1=1', "heuristic-1", ""])
def test_requete_refuse_une_version_mal_formee(bad: str) -> None:
    with pytest.raises(ValueError):
        drift.logs_insights_query(bad)


QUESTIONS = [40, 30, 20, 10, 0, 0, 0, 0, 0, 0]
ADS = [5, 20, 30, 20, 15, 5, 3, 2, 0, 0]  # compartiments ≥ 0,5 ignorés (entrées bloquées)


def _reference_file(tmp_path: Path, split: bool = True, version: str = "v1.4.0") -> Path:
    data: dict = {"version": version, "domain_score_histogram": {"bins": [], "counts": QUESTIONS}}
    if split:
        data["domain_question_score_histogram"] = {"bins": [], "counts": QUESTIONS}
        data["job_ad_score_histogram"] = {"bins": [], "counts": ADS}
    path = tmp_path / "metrics.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _from(counts: list[int], chars: int | None, scale: int = 1) -> list[drift.Sample]:
    """Échantillons synthétiques reproduisant un histogramme (milieu de chaque compartiment)."""
    return [
        drift.Sample(i / 10 + 0.05, chars) for i, c in enumerate(counts) for _ in range(c * scale)
    ]


def _run(reference: Path, samples: list[drift.Sample], *extra: str) -> tuple[int, list[str]]:
    seen: list[str] = []

    def fetch(client, log_group, start, end, model_version, **kwargs):  # noqa: ANN001, ARG001
        seen.append(model_version)
        return samples

    code = drift.main(
        ["--reference", str(reference), *extra],
        client_factory=lambda region: object(),
        fetch_scores=fetch,
    )
    return code, seen


def test_version_promue_lue_dans_la_reference(tmp_path: Path) -> None:
    samples = _from(QUESTIONS, 50) + _from(ADS[:5], 3000, 2)
    code, seen = _run(_reference_file(tmp_path), samples)
    assert code == 0 and seen == ["onnx-v1.4.0"]
    _, seen = _run(_reference_file(tmp_path), samples, "--model-version", "onnx-v1.3.0")
    assert seen == ["onnx-v1.3.0"]


def test_populations_stables_pas_de_derive(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    samples = _from(QUESTIONS, 50) + _from(ADS[:5], 3000, 2)
    code, _ = _run(_reference_file(tmp_path), samples)
    out = capsys.readouterr().out
    assert code == 0
    assert "questions : pas de dérive significative" in out
    assert "annonces : pas de dérive significative" in out


def test_annonces_collees_ne_font_pas_deriver_les_questions(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    # beaucoup d'annonces aux scores plus hauts que les questions : normal, population à part
    samples = _from(QUESTIONS, 60) + _from(ADS[:5], 5000, 3)
    code, _ = _run(_reference_file(tmp_path), samples)
    assert code == 0
    assert "::warning::" not in capsys.readouterr().out


def test_derive_des_annonces_detectee(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    samples = _from(QUESTIONS, 60) + [drift.Sample(0.45, 4000)] * 80
    code, _ = _run(_reference_file(tmp_path), samples)
    out = capsys.readouterr().out
    assert code == 1
    assert "annonces : dérive du classifieur détectée" in out
    assert "questions : pas de dérive significative" in out


def test_population_trop_petite_reussit_avec_une_note(
    tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    # 51 scores au total (comme la nuit du 2026-09-30) mais anormaux et trop peu par population
    samples = [drift.Sample(0.45, 60)] * (drift.MIN_SAMPLES - 1) + [drift.Sample(0.45, 900)] * 22
    code, _ = _run(_reference_file(tmp_path), samples)
    out = capsys.readouterr().out
    assert code == 0
    assert "questions : données insuffisantes" in out
    assert "annonces : données insuffisantes" in out
    assert summary.read_text(encoding="utf-8").count("données insuffisantes") == 2


def test_minimum_applique_apres_exclusion_des_entrees_bloquees(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    samples = [drift.Sample(0.05, 50)] * (drift.MIN_SAMPLES - 1) + [drift.Sample(0.99, 50)] * 151
    code, _ = _run(_reference_file(tmp_path, split=False), samples)
    out = capsys.readouterr().out
    assert code == 0
    assert "domaine : données insuffisantes" in out
    assert "151 exclu(s)" in out


def test_vague_d_attaques_bloquees_exclue(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    samples = _from(QUESTIONS, 50) + [drift.Sample(0.97, 50)] * 500 + _from(ADS[:5], 3000, 2)
    code, _ = _run(_reference_file(tmp_path), samples)
    out = capsys.readouterr().out
    assert code == 0
    assert "500 bloqué(s) exclu(s)" in out


def test_spans_sans_longueur_hors_populations_separees(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    samples = _from(QUESTIONS, 50) + _from(ADS[:5], 3000, 2) + [drift.Sample(0.45, None)] * 200
    code, _ = _run(_reference_file(tmp_path), samples)
    out = capsys.readouterr().out
    assert code == 0
    assert "dont 200 sans longueur" in out


def test_reference_sans_populations_une_seule_comparaison(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    samples = [drift.Sample(0.45, None)] * 60
    code, _ = _run(_reference_file(tmp_path, split=False), samples)
    assert code == 1
    assert "domaine : dérive du classifieur détectée" in capsys.readouterr().out


def test_avertissement_si_psi_intermediaire(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    reference = tmp_path / "metrics.json"
    reference.write_text(
        json.dumps({"version": "v1.4.0", "domain_score_histogram": {"counts": [100] + [0] * 9}}),
        encoding="utf-8",
    )
    samples = [drift.Sample(0.01, 20)] * 98 + [drift.Sample(0.45, 20)] * 2
    code, _ = _run(reference, samples)
    assert code == 0
    assert "::warning::domaine" in capsys.readouterr().out


def test_compartiments_de_reference_au_dessus_du_seuil_ignores() -> None:
    assert drift.below_threshold(ADS, 0.5) == [5, 20, 30, 20, 15, 0, 0, 0, 0, 0]
    assert drift.below_threshold(ADS, 0.9) == [5, 20, 30, 20, 15, 5, 3, 2, 0, 0]


def test_reference_sans_histogramme_avertit_et_reussit(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    reference = tmp_path / "metrics.json"
    reference.write_text(json.dumps({"deepset_recall": 0.9}), encoding="utf-8")

    def fetch(*args, **kwargs):  # noqa: ANN002, ANN003, ARG001
        raise AssertionError("aucune requête sans histogramme de référence")

    code = drift.main(
        ["--reference", str(reference)],
        client_factory=lambda region: object(),
        fetch_scores=fetch,
    )
    assert code == 0
    assert "référence sans domain_score_histogram" in capsys.readouterr().out
